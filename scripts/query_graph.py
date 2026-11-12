#!/usr/bin/env python3
"""Query provenance, resolve measurements, or separately inspect annotations."""
import json
from pathlib import Path
import sys

try:
    from . import graph
except ImportError:
    import graph


def main(argv=None):
    parser = graph.JSONArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("batches", "variables", "batch-variables", "reference", "measurements", "annotations", "counts", "check"):
        sub = subs.add_parser(name)
        sub.add_argument("--dataset-id", default=graph.DEFAULT_DATASET)
        if name in ("batch-variables", "reference", "measurements", "annotations"):
            sub.add_argument("--batch-ref", type=int, required=name != "annotations")
        if name in ("variables", "batch-variables", "reference", "measurements"):
            sub.add_argument("--include-summaries", action="store_true")
        if name in ("reference", "measurements"):
            sub.add_argument("--variable", required=True, help="Contract output_column or variable_id")
        if name == "measurements":
            sub.add_argument("--processed-dir", type=Path, default=graph.DEFAULT_OUTPUT)
            sub.add_argument("--start-tick", type=int)
            sub.add_argument("--end-tick", type=int)
            sub.add_argument("--limit", type=int, default=20)
    try:
        args = parser.parse_args(argv)
        database = graph.environment().get("NEO4J_DATABASE", "neo4j")
        with graph.driver_from_env() as driver:
            if args.command == "batches":
                result = graph.list_batches(driver, args.dataset_id, database)
            elif args.command == "variables":
                result = graph.list_variables(driver, args.dataset_id, database, not args.include_summaries)
            elif args.command == "batch-variables":
                result = graph.batch_variables(driver, args.dataset_id, args.batch_ref, database, not args.include_summaries)
            elif args.command in ("reference", "measurements"):
                result = graph.get_reference(driver, args.dataset_id, args.batch_ref, args.variable,
                                             database, not args.include_summaries)
                if args.command == "measurements":
                    result = graph.resolve_reference(result, args.processed_dir, args.start_tick, args.end_tick, args.limit)
            elif args.command == "annotations":
                result = graph.published_annotations(driver, args.dataset_id, args.batch_ref, database)
            elif args.command == "counts":
                result = graph.graph_counts(driver, args.dataset_id, database)
            else:
                result = graph.check_graph_integrity(driver, args.dataset_id, database)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 1 if args.command == "check" and not result["ok"] else 0
    except Exception as error:
        print(json.dumps(graph.cli_error(error), sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
