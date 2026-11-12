#!/usr/bin/env python3
"""Normalize the verified IndPenSim archive without inventing source semantics.

The production CLI uses the pinned contract. ``ingest`` also accepts a complete
contract path for small isolated test fixtures. It never downloads data.
"""
import argparse
from contextlib import contextmanager
import csv
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import zipfile

import pyarrow as pa
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "config/indpensim_contract.json"
DEFAULT_ARCHIVE = ROOT / "data/raw/indpensim/100_Batches_IndPenSim.zip"
DEFAULT_OUTPUT = ROOT / "data/processed/indpensim"
OUTPUT_TABLES = ("batches", "samples", "variables")
WARNINGS = [
    "Malformed time-series header: positions 37 onward are excluded; no repaired Raman axis is asserted.",
    "Metadata headers are misleading; batch identity uses documented raw position 35 and other metadata stay explicitly raw.",
    "Reported units are not independently validated; PAA, NH3, off-gas O2 and raw harvest quantities have unresolved units or aggregation.",
    "Batch fault evidence is binary only; raw fault-reference transitions do not establish a named fault type or physical onset/clearance.",
    "Offline assays lack separate collection and result-availability timestamps; no availability delay is reconstructed.",
]


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _arrow_schema(fields):
    return pa.schema([pa.field(f["name"], pa.type_for_alias(f["type"]), nullable=f["nullable"]) for f in fields])


def _member_specs(contract):
    members = contract["source"]["members"]
    by_kind = {m["source_file_id"].rsplit(":", 1)[-1]: m for m in members}
    if len(members) != 2 or set(by_kind) != {"statistics", "timeseries"}:
        raise ValueError("Contract must define exactly statistics and timeseries source members")
    return by_kind


def _validate_archive(archive, contract):
    source = contract["source"]
    actual_size = archive.stat().st_size
    if actual_size != source["expected_bytes"]:
        raise ValueError(f"Archive size mismatch: expected {source['expected_bytes']}, found {actual_size}")
    actual_hash = _sha256(archive)
    if actual_hash != source["expected_sha256"]:
        raise ValueError(f"Archive SHA-256 mismatch: expected {source['expected_sha256']}, found {actual_hash}")
    specs = _member_specs(contract)
    with zipfile.ZipFile(archive) as zipped:
        infos = zipped.infolist()
        names = [i.filename for i in infos]
        if len(set(names)) != len(names):
            raise ValueError("Archive has duplicate ZIP member names")
        expected = {m["path"] for m in specs.values()}
        files = {i.filename for i in infos if not i.is_dir()}
        if files != expected:
            raise ValueError(f"Archive member mismatch: expected {sorted(expected)}, found {sorted(files)}")
        allowed_dirs = {str(parent).rstrip("/") + "/" for name in expected for parent in Path(name).parents if str(parent) != "."}
        if any(i.is_dir() and i.filename not in allowed_dirs for i in infos):
            raise ValueError("Archive contains an unexpected directory member")
        for spec in specs.values():
            info = zipped.getinfo(spec["path"])
            if info.file_size != spec["expected_bytes"] or f"{info.CRC:08x}" != spec["expected_crc32"]:
                raise ValueError(f"ZIP member size/CRC mismatch: {spec['path']}")
    return actual_hash


@contextmanager
def _writer_lock(output_dir):
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    lock = output_dir.parent / f".{output_dir.name}.lock"
    try:
        descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise RuntimeError(f"Writer lock already exists: {lock}; another ingestion may be running. Remove only after confirming no writer is active.") from error
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(str(os.getpid()) + "\n")
        yield
    finally:
        lock.unlink()


def _manifest_base(contract, cache_inputs, cache_key):
    return {
        "manifest_version": 1,
        "contract_version": contract["contract_version"],
        "dataset": contract["dataset"],
        "cache_key": cache_key,
        "cache_inputs": cache_inputs,
        "source": {
            "archive_filename": contract["source"]["archive_filename"],
            "bytes": contract["source"]["expected_bytes"],
            "sha256": cache_inputs["archive_sha256"],
            "members": [{
                "source_file_id": m["source_file_id"], "path": m["path"],
                "bytes": m["expected_bytes"], "crc32": m["expected_crc32"],
                "rows": m["expected_rows"], "header_fields": len(m["expected_header"]),
                "row_fields": m["expected_row_width"],
            } for m in contract["source"]["members"]],
        },
        "normalization": contract["normalization"],
        "writer": contract["writer"],
        "warnings": WARNINGS,
    }


def _expected_rows(contract):
    specs = _member_specs(contract)
    return {"batches": specs["statistics"]["expected_rows"],
            "samples": specs["timeseries"]["expected_rows"],
            "variables": len(contract["variables"])}


def _validate_table(table, fields, expected_rows, label):
    expected_schema = _arrow_schema(fields)
    if not table.schema.equals(expected_schema, check_metadata=True):
        raise ValueError(f"{label} schema mismatch")
    if table.num_rows != expected_rows:
        raise ValueError(f"{label} row count mismatch: expected {expected_rows}, found {table.num_rows}")
    table.validate(full=True)
    for field in expected_schema:
        if not field.nullable and table[field.name].null_count:
            raise ValueError(f"{label}.{field.name} contains unexpected nulls")


def _cache_miss(output_dir, base, contract):
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.is_file():
        return "manifest missing"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or set(manifest) != set(base) | {"outputs"}:
            return "manifest structure mismatch"
        if any(manifest.get(key) != value for key, value in base.items()):
            return "manifest metadata/cache inputs mismatch"
        outputs = manifest["outputs"]
        if not isinstance(outputs, dict) or set(outputs) != {name + ".parquet" for name in OUTPUT_TABLES}:
            return "manifest output entries mismatch"
        expected_rows = _expected_rows(contract)
        for name in OUTPUT_TABLES:
            filename = name + ".parquet"
            path = output_dir / filename
            item = outputs[filename]
            if not isinstance(item, dict) or set(item) != {"bytes", "sha256", "rows", "schema"}:
                return f"{filename}: manifest output structure mismatch"
            if item["schema"] != contract["schemas"][name] or item["rows"] != expected_rows[name]:
                return f"{filename}: manifest schema/row count mismatch"
            if not path.is_file():
                return f"{filename}: output missing"
            if path.stat().st_size != item["bytes"] or _sha256(path) != item["sha256"]:
                return f"{filename}: output size/hash mismatch"
            table = pq.read_table(path)
            _validate_table(table, contract["schemas"][name], expected_rows[name], filename)
    except (OSError, ValueError, TypeError, KeyError, pa.ArrowException) as error:
        return f"invalid cache: {type(error).__name__}: {error}"
    return None


@contextmanager
def _csv_rows(zipped, spec):
    with zipped.open(spec["path"]) as raw:
        with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
            reader = csv.reader(text, strict=True)
            try:
                header = next(reader)
            except StopIteration as error:
                raise ValueError(f"Missing header in {spec['path']}") from error
            if header != spec["expected_header"]:
                raise ValueError(f"CSV header mismatch: {spec['path']}")
            yield reader


def _integer(value, location):
    try:
        number = Decimal(value)
        if not number.is_finite() or number != number.to_integral_value():
            raise ValueError()
        return int(number)
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"Expected finite integer at {location}: {value!r}") from error


def _number(value, location, nullable=False):
    if nullable and value == "NaN":
        return None
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError(f"Expected numeric value at {location}: {value!r}") from error
    if not math.isfinite(number):
        raise ValueError(f"Nonfinite value at {location}: {value!r}")
    return number


def _control_regime(batch_ref):
    if 1 <= batch_ref <= 30:
        return "recipe_driven"
    if 31 <= batch_ref <= 60:
        return "operator_controlled"
    if 61 <= batch_ref <= 90:
        return "apc_raman"
    return "not_documented"


def _check_width(row, spec, row_number):
    if len(row) != spec["expected_row_width"]:
        raise ValueError(f"CSV row width mismatch: {spec['path']} data row {row_number}; expected {spec['expected_row_width']}, found {len(row)}")


def _normalize(zipped, contract):
    specs = _member_specs(contract)
    dataset_id = contract["dataset"]["id"]
    normalization = contract["normalization"]
    batch_ids = {ref: normalization["batch_id_template"].format(dataset_id=dataset_id, batch_ref=ref)
                 for ref in contract["source"]["expected_batch_refs"]}
    statistics = {}
    spec = specs["statistics"]
    summary_variables = [v for v in contract["variables"] if v["output_table"] == "batches"]
    with _csv_rows(zipped, spec) as reader:
        count = 0
        for count, row in enumerate(reader, 1):
            _check_width(row, spec, count)
            ref = _integer(row[0], f"statistics row {count} batch ref")
            if ref not in batch_ids or ref in statistics:
                raise ValueError(f"Unknown/duplicate statistics batch ref {ref} at data row {count}")
            fault = _integer(row[4], f"statistics row {count} fault label")
            if fault not in (0, 1):
                raise ValueError(f"Nonbinary statistics fault label at data row {count}")
            item = {"dataset_id": dataset_id, "batch_id": batch_ids[ref], "batch_ref": ref,
                    "source_file_id": spec["source_file_id"], "source_row_number": count,
                    "fault_present": bool(fault), "control_regime": _control_regime(ref),
                    "sample_count": 0}
            for variable in summary_variables:
                index = variable["source_column_index"]
                item[variable["output_column"]] = _number(row[index], f"statistics row {count} column {index}")
            statistics[ref] = item
        if count != spec["expected_rows"] or set(statistics) != set(batch_ids):
            raise ValueError("Statistics row count/batch set does not match the contract")
    spec = specs["timeseries"]
    sample_fields = contract["schemas"]["samples"]
    columns = {f["name"]: [] for f in sample_fields}
    variables = [v for v in contract["variables"] if v["output_table"] == "samples"]
    nullable = {f["name"]: f["nullable"] for f in sample_fields}
    last_ticks = {}
    step = Decimal(normalization["time_step_h"])
    if not step.is_finite() or step <= 0:
        raise ValueError("Contract time step must be finite and positive")
    with _csv_rows(zipped, spec) as reader:
        count = 0
        for count, row in enumerate(reader, 1):
            _check_width(row, spec, count)
            ref = _integer(row[normalization["batch_key_raw_index"]], f"timeseries row {count} batch ref")
            if ref not in statistics:
                raise ValueError(f"Unknown timeseries batch ref {ref} at data row {count}")
            time_h = _number(row[0], f"timeseries row {count} time")
            try:
                with localcontext() as context:
                    context.prec = 50
                    tick_decimal = Decimal(row[0]) / step
                    if tick_decimal <= 0 or tick_decimal != tick_decimal.to_integral_value():
                        raise ValueError()
                    tick = int(tick_decimal)
            except (InvalidOperation, ValueError) as error:
                raise ValueError(f"Time is not a positive integral {step}-hour tick at timeseries row {count}") from error
            if ref in last_ticks and tick != last_ticks[ref] + 1:
                raise ValueError(f"Duplicate, unsorted, or nonconsecutive time tick in batch {ref} at data row {count}")
            last_ticks[ref] = tick
            item = {"dataset_id": dataset_id, "sample_id": normalization["sample_id_template"].format(batch_id=batch_ids[ref], time_tick=tick),
                    "batch_id": batch_ids[ref], "batch_ref": ref, "source_file_id": spec["source_file_id"],
                    "source_row_number": count, "time_h": time_h, "time_tick": tick}
            for name, index in normalization["raw_metadata_indices"].items():
                item[name] = _integer(row[index], f"timeseries row {count} column {index}")
            for name in ("fault_reference_raw", "control_reference_raw", "batch_fault_flag_raw"):
                if item[name] not in (0, 1):
                    raise ValueError(f"Nonbinary {name} at timeseries row {count}")
            if item["metadata_34_raw"] != ref:
                raise ValueError(f"Raw metadata 34 disagrees with batch ref at timeseries row {count}")
            batch = statistics[ref]
            if item["batch_fault_flag_raw"] != int(batch["fault_present"]):
                raise ValueError(f"Time-series batch fault flag disagrees with statistics at data row {count}")
            for variable in variables:
                name, index = variable["output_column"], variable["source_column_index"]
                item[name] = _number(row[index], f"timeseries row {count} column {index}", nullable[name])
            for name in columns:
                columns[name].append(item[name])
            if not batch["sample_count"]:
                batch["time_start_h"] = time_h
                batch["timeseries_first_source_row"] = count
            batch["sample_count"] += 1
            batch["time_end_h"] = time_h
            batch["timeseries_last_source_row"] = count
        if count != spec["expected_rows"] or set(last_ticks) != set(statistics):
            raise ValueError("Time-series row count/batch set does not match the contract")
    samples = pa.Table.from_pydict(columns, schema=_arrow_schema(sample_fields))
    samples = samples.sort_by([("batch_ref", "ascending"), ("time_tick", "ascending")])
    batches = pa.Table.from_pylist([statistics[k] for k in sorted(statistics)], schema=_arrow_schema(contract["schemas"]["batches"]))
    variable_rows = [{"dataset_id": dataset_id, **v} for v in contract["variables"]]
    variable_table = pa.Table.from_pylist(variable_rows, schema=_arrow_schema(contract["schemas"]["variables"]))
    return {"batches": batches, "samples": samples, "variables": variable_table}


def _write_parquet(table, path, writer_settings):
    pq.write_table(table, path, compression=writer_settings["compression"],
                   row_group_size=writer_settings["row_group_size"],
                   use_dictionary=writer_settings["use_dictionary"],
                   version=writer_settings["parquet_version"],
                   write_statistics=writer_settings["write_statistics"])
    with Path(path).open("rb") as stream:
        os.fsync(stream.fileno())


def _publish(staging_dir, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in OUTPUT_TABLES:
        filename = name + ".parquet"
        os.replace(staging_dir / filename, output_dir / filename)
    os.replace(staging_dir / "manifest.json", output_dir / "manifest.json")


def ingest(archive=DEFAULT_ARCHIVE, output_dir=DEFAULT_OUTPUT, force=False, contract_path=DEFAULT_CONTRACT):
    """Validate source, reuse an intact cache or stage and publish a rebuild.

    Returns run-specific status. Manifest bytes and Parquet metadata contain no
    timestamps, random IDs, or absolute paths. Validation failures raise errors.
    """
    archive, output_dir, contract_path = Path(archive), Path(output_dir), Path(contract_path)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    # Parsing schemas here catches unsupported field types before any publication.
    for name in OUTPUT_TABLES:
        _arrow_schema(contract["schemas"][name])
    with _writer_lock(output_dir):
        archive_hash = _validate_archive(archive, contract)
        cache_inputs = {"contract_sha256": _sha256(contract_path), "archive_sha256": archive_hash,
                        "normalizer_sha256": _sha256(Path(__file__)),
                        "python_version": platform.python_version(), "pyarrow_version": pa.__version__}
        cache_key = hashlib.sha256(_canonical(cache_inputs)).hexdigest()
        base = _manifest_base(contract, cache_inputs, cache_key)
        reason = "forced rebuild" if force else _cache_miss(output_dir, base, contract)
        status = {"status": "cached" if reason is None else "built", "cache_key": cache_key,
                  "manifest_path": str(output_dir / "manifest.json"), "cache_miss_reason": reason}
        if reason is None:
            return status
        stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=str(output_dir.parent)))
        try:
            with zipfile.ZipFile(archive) as zipped:
                tables = _normalize(zipped, contract)
            expected_rows = _expected_rows(contract)
            outputs = {}
            for name in OUTPUT_TABLES:
                filename = name + ".parquet"
                _validate_table(tables[name], contract["schemas"][name], expected_rows[name], filename)
                path = stage / filename
                _write_parquet(tables[name], path, contract["writer"])
                # Validate serialized schema and data before promotion as well.
                _validate_table(pq.read_table(path), contract["schemas"][name], expected_rows[name], filename)
                outputs[filename] = {"bytes": path.stat().st_size, "sha256": _sha256(path),
                                     "rows": tables[name].num_rows, "schema": contract["schemas"][name]}
            if archive.stat().st_size != contract["source"]["expected_bytes"] or _sha256(archive) != archive_hash:
                raise ValueError("Source archive changed during ingestion; refusing to publish")
            manifest = {**base, "outputs": outputs}
            with (stage / "manifest.json").open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(manifest, stream, sort_keys=True, indent=2, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            _publish(stage, output_dir)
        finally:
            shutil.rmtree(stage)
        return status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true", help="Rebuild even when the verified cache is valid")
    args = parser.parse_args(argv)
    try:
        result = ingest(args.archive, args.output_dir, force=args.force)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, csv.Error, pa.ArrowException) as error:
        print(json.dumps({"status": "error", "error": f"{type(error).__name__}: {error}"}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
