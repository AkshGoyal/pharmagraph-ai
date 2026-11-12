#!/usr/bin/env python3
"""Write a deterministic, graph-resolved batch investigation as atomic JSON."""
import json
import os
from pathlib import Path
import sys
import tempfile

try:
    from . import graph, investigation
except ImportError:
    import graph
    import investigation


def _guard_output(output, processed_dir, contract_path=graph.DEFAULT_CONTRACT, manifest=None):
    """Reject paths and hardlinks that would replace protected input bytes."""
    output = Path(output).expanduser().resolve()
    root = Path(processed_dir).expanduser().resolve()
    protected = [root / "manifest.json", *(root / f"{name}.parquet" for name in ("batches", "samples", "variables")),
                 Path(contract_path).resolve(), graph.DEFAULT_CONTRACT.resolve(), graph.ingestion.DEFAULT_ARCHIVE.resolve(),
                 (graph.ROOT / ".env").resolve()]
    if manifest is not None:
        raw_root = graph.ROOT / "data/raw/indpensim"
        protected.append((raw_root / manifest["source"]["archive_filename"]).resolve())
        protected.extend((raw_root / member["path"]).resolve() for member in manifest["source"]["members"])
    for path in protected:
        if output == path or (output.exists() and path.exists() and output.samefile(path)):
            raise ValueError("Output would overwrite a protected processed/source/contract/credential input")
    if output.exists() and not output.is_file():
        raise ValueError("Output must be a file path")
    return output


def write_result(result, output, processed_dir=graph.DEFAULT_OUTPUT, contract_path=graph.DEFAULT_CONTRACT):
    """Atomically publish sorted UTF-8 JSON; an error preserves prior output."""
    manifest_path = Path(processed_dir) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output = _guard_output(output, processed_dir, contract_path, manifest)
    payload = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", prefix=f".{output.name}.",
                                         suffix=".tmp", dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _guard_output(output, processed_dir, contract_path, manifest)
        os.replace(temporary, output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = graph.JSONArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--processed-dir", type=Path, default=graph.DEFAULT_OUTPUT)
    parser.add_argument("--min-peers", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=6.0)
    parser.add_argument("--min-consecutive", type=int, default=5)
    parser.add_argument("--variable", action="append", dest="variables")
    parser.add_argument("--peer-batch-id", action="append", dest="peer_batch_ids")
    try:
        args = parser.parse_args(argv)
        config = investigation.DetectorConfig(
            variables=tuple(args.variables) if args.variables is not None else investigation.DEFAULT_VARIABLES,
            min_peers=args.min_peers, threshold=args.threshold, min_consecutive=args.min_consecutive,
            peer_batch_ids=tuple(args.peer_batch_ids) if args.peer_batch_ids is not None else None)
        _guard_output(args.output, args.processed_dir)
        with graph.driver_from_env() as driver:
            result = investigation.investigate_batch(driver, args.batch_id, args.processed_dir,
                database=graph.environment().get("NEO4J_DATABASE", "neo4j"), config=config)
        write_result(result, args.output, args.processed_dir)
        print(json.dumps({"status": "complete", "batch_id": result["batch"]["batch_id"],
                          "finding_count": len(result["findings"])}, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps(graph.cli_error(error), sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
