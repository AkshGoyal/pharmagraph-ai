#!/usr/bin/env python3
"""Load a verified processed bundle into Neo4j, keeping measurements in Parquet."""
import json
from pathlib import Path
import sys

try:
    from . import graph
except ImportError:
    import graph


def main(argv=None):
    parser = graph.JSONArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, default=graph.DEFAULT_OUTPUT)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--replace", action="store_true", help="Replace only the selected logical dataset")
    try:
        args = parser.parse_args(argv)
        with graph.driver_from_env() as driver:
            result = graph.load_graph(driver, args.processed_dir,
                database=graph.environment().get("NEO4J_DATABASE", "neo4j"),
                batch_size=args.batch_size, replace=args.replace)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except Exception as error:
        print(json.dumps(graph.cli_error(error), sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
