"""Versioned provenance graph; numerical measurements remain in verified Parquet.

Detector queries use explicit property lists and never traverse annotations.
The loader accepts historical writer fingerprints, but requires the pinned data
contract and intact local outputs. It never opens the source archive.
"""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re

import pyarrow.compute as pc
import pyarrow.parquet as pq

try:
    from . import ingest_indpensim as ingestion
except ImportError:
    import ingest_indpensim as ingestion

ROOT = ingestion.ROOT
DEFAULT_CONTRACT = ingestion.DEFAULT_CONTRACT
DEFAULT_OUTPUT = ingestion.DEFAULT_OUTPUT
DEFAULT_DATASET = "indpensim:pdnjz7zz5x:v2"
MODEL_VERSION = 1
IDS = {"Dataset": "dataset_id", "SourceFile": "source_file_id",
       "ProcessedArtifact": "artifact_id", "Batch": "batch_id",
       "Variable": "variable_id", "FaultAnnotation": "annotation_id"}
BATCH_FIELDS = ("dataset_id", "batch_id", "batch_ref", "source_file_id",
                "source_row_number", "sample_count", "time_start_h", "time_end_h",
                "timeseries_first_source_row", "timeseries_last_source_row")
VARIABLE_FIELDS = ("dataset_id", "variable_id", "output_table", "output_column",
                   "source_file_id", "source_column_index", "source_header",
                   "unit_reported", "unit_status", "measurement_kind")
REL_TYPES = ("HAS_SOURCE", "HAS_ARTIFACT", "HAS_BATCH", "HAS_VARIABLE",
             "FROM_SOURCE", "HAS_DATA", "DERIVED_FROM", "HAS_ANNOTATION")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _digest(value):
    return hashlib.sha256(ingestion._canonical(value)).hexdigest()


def _safe_path(value):
    return (isinstance(value, str) and bool(value) and "\\" not in value
            and not PurePosixPath(value).is_absolute()
            and ".." not in PurePosixPath(value).parts and ":" not in value
            and "\x00" not in value)


def validate_processed(processed_dir, contract_path=DEFAULT_CONTRACT):
    """Validate provenance, hashes, exact schemas, identities and source joins."""
    root = Path(processed_dir)
    contract_path = Path(contract_path)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    raw = (root / "manifest.json").read_bytes()
    manifest = json.loads(raw)
    _require(isinstance(manifest, dict), "Manifest must be an object")
    inputs = manifest.get("cache_inputs", {})
    _require(isinstance(inputs, dict) and set(inputs) == {"archive_sha256", "contract_sha256", "normalizer_sha256",
                             "python_version", "pyarrow_version"}, "Invalid cache inputs")
    for key in ("archive_sha256", "contract_sha256", "normalizer_sha256"):
        _require(isinstance(inputs[key], str) and re.fullmatch(r"[0-9a-f]{64}", inputs[key]),
                 "Invalid cache fingerprint")
    for key in ("python_version", "pyarrow_version"):
        _require(isinstance(inputs[key], str) and bool(inputs[key]), "Invalid writer version")
    _require(inputs["contract_sha256"] == ingestion._sha256(contract_path), "Pinned contract mismatch")
    _require(inputs["archive_sha256"] == contract["source"]["expected_sha256"], "Source hash mismatch")
    _require(manifest.get("cache_key") == _digest(inputs), "Cache key mismatch")
    base = ingestion._manifest_base(contract, inputs, _digest(inputs))
    reason = ingestion._cache_miss(root, base, contract)
    _require(reason is None, f"Invalid processed bundle: {reason}")
    _require(all(_safe_path(m["path"]) for m in manifest["source"]["members"]), "Unsafe source path")
    _require(_safe_path(manifest["source"]["archive_filename"]), "Unsafe archive filename")
    tables = {name: pq.read_table(root / f"{name}.parquet") for name in ingestion.OUTPUT_TABLES}
    dataset_id = contract["dataset"]["id"]
    for name, table in tables.items():
        _require(set(table["dataset_id"].to_pylist()) == {dataset_id}, f"{name}: dataset mismatch")
        for field in table.schema:
            if str(field.type) == "double":
                _require(all(v is None or math.isfinite(v) for v in table[field.name].to_pylist()),
                         f"{name}.{field.name}: nonfinite value")
    variables = tables["variables"].to_pylist()
    expected_variables = [{"dataset_id": dataset_id, **v} for v in contract["variables"]]
    _require(sorted(variables, key=lambda r: r["variable_id"]) ==
             sorted(expected_variables, key=lambda r: r["variable_id"]), "Variable definitions differ from contract")
    specs = ingestion._member_specs(contract)
    normalization = contract["normalization"]
    batches = tables["batches"].to_pylist()
    refs = contract["source"].get("expected_batch_refs", list(range(1, 101)))
    _require(len(batches) == len(refs) and {b["batch_ref"] for b in batches} == set(refs),
             "Batch set mismatch")
    by_id = {}
    for b in batches:
        expected = normalization["batch_id_template"].format(dataset_id=dataset_id, batch_ref=b["batch_ref"])
        _require(b["batch_id"] == expected and expected not in by_id, "Invalid/duplicate batch ID")
        _require(b["source_file_id"] == specs["statistics"]["source_file_id"], "Batch source mismatch")
        by_id[expected] = b
    _require({b["source_row_number"] for b in batches} == set(range(1, len(batches) + 1)),
             "Invalid statistics source rows")
    grouped = defaultdict(list)
    sample_ids, source_rows = set(), set()
    sample_metadata = tables["samples"].select([
        "sample_id", "batch_id", "batch_ref", "source_file_id", "source_row_number", "time_h", "time_tick",
        "fault_reference_raw", "control_reference_raw", "batch_fault_flag_raw", "metadata_34_raw"])
    step = Decimal(normalization["time_step_h"])
    for s in sample_metadata.to_pylist():
        b = by_id.get(s["batch_id"])
        _require(b is not None and s["batch_ref"] == b["batch_ref"], "Sample batch join mismatch")
        expected = normalization["sample_id_template"].format(batch_id=s["batch_id"], time_tick=s["time_tick"])
        _require(s["sample_id"] == expected and expected not in sample_ids, "Invalid/duplicate sample ID")
        _require(s["time_tick"] > 0 and Decimal(str(s["time_h"])) == s["time_tick"] * step,
                 "Sample tick/time mismatch")
        _require(all(s[k] in (0, 1) for k in ("fault_reference_raw", "control_reference_raw", "batch_fault_flag_raw")),
                 "Nonbinary raw metadata")
        _require(s["batch_fault_flag_raw"] == int(b["fault_present"]) and
                 s["metadata_34_raw"] == s["batch_ref"], "Raw metadata batch join mismatch")
        _require(s["source_file_id"] == specs["timeseries"]["source_file_id"], "Sample source mismatch")
        _require(s["source_row_number"] not in source_rows, "Duplicate time-series source row")
        sample_ids.add(expected)
        source_rows.add(s["source_row_number"])
        grouped[s["batch_id"]].append(s)
    _require(source_rows == set(range(1, tables["samples"].num_rows + 1)), "Invalid time-series source rows")
    for key, b in by_id.items():
        rows = grouped[key]
        _require(bool(rows), "Batch has no samples")
        ticks = sorted(s["time_tick"] for s in rows)
        _require(ticks == list(range(ticks[0], ticks[-1] + 1)), "Noncontiguous batch ticks")
        summaries = {"sample_count": len(rows), "time_start_h": min(s["time_h"] for s in rows),
                     "time_end_h": max(s["time_h"] for s in rows),
                     "timeseries_first_source_row": min(s["source_row_number"] for s in rows),
                     "timeseries_last_source_row": max(s["source_row_number"] for s in rows)}
        _require(all(b[k] == v for k, v in summaries.items()), "Batch summary mismatch")
    # A bundle changed during reading is rejected rather than resolved against mixed files.
    _require((root / "manifest.json").read_bytes() == raw, "Manifest changed during validation")
    for filename, item in manifest["outputs"].items():
        _require(ingestion._sha256(root / filename) == item["sha256"], "Artifact changed during validation")
    return {"manifest": manifest, "manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "tables": tables, "processed_dir": root}


def _artifact_id(dataset_id, filename, sha):
    return f"{dataset_id}:artifact:{filename}:sha256:{sha}"


def _project(bundle):
    m = bundle["manifest"]
    dataset_id = m["dataset"]["id"]
    batches = bundle["tables"]["batches"].to_pylist()
    variables = bundle["tables"]["variables"].to_pylist()
    dataset = {k: v for k, v in m["dataset"].items() if k != "id"}
    dataset.update(dataset_id=dataset_id, manifest_sha256=bundle["manifest_sha256"],
                   cache_key=m["cache_key"], graph_model_version=MODEL_VERSION, load_state="loading",
                   record_kind="published_simulation_dataset", expected_batch_count=len(batches),
                   expected_variable_count=len(variables))
    nodes = {label: [] for label in IDS}
    nodes["Dataset"] = [dataset]
    nodes["SourceFile"] = [{**s, "dataset_id": dataset_id, "source_member_path": s["path"],
                             "archive_sha256": m["source"]["sha256"],
                             "archive_filename": m["source"]["archive_filename"],
                             "record_kind": "published_source"} for s in m["source"]["members"]]
    nodes["ProcessedArtifact"] = [{"dataset_id": dataset_id,
        "artifact_id": _artifact_id(dataset_id, filename, item["sha256"]),
        "filename": filename, "sha256": item["sha256"], "bytes": item["bytes"], "rows": item["rows"],
        "output_table": filename.removesuffix(".parquet"), "record_kind": "derived_artifact"}
        for filename, item in m["outputs"].items()]
    nodes["Batch"] = [{**{k: b[k] for k in BATCH_FIELDS},
                       "record_kind": "published_simulation_record"} for b in batches]
    nodes["Variable"] = [{**v, "record_kind": "published_variable_definition"} for v in variables]
    nodes["FaultAnnotation"] = [{"dataset_id": dataset_id,
        "annotation_id": b["batch_id"] + ":annotation:published_fault_present",
        "batch_id": b["batch_id"], "fault_present": b["fault_present"],
        "source_file_id": b["source_file_id"], "source_row_number": b["source_row_number"],
        "source_header": "Fault ref(0-NoFault 1-Fault)", "source_column_index": 4,
        "annotation_kind": "published_batch_fault_presence", "record_kind": "published_annotation"}
        for b in batches]
    return nodes, _expected_edges(nodes, dataset_id)


def _expected_edges(nodes, dataset_id):
    """Edges described by fixed label/type/key tuples; no user Cypher fragments."""
    edges = []
    def add(left, a, rel, right, b):
        edges.append((left, a, rel, right, b))
    for label, rel in (("SourceFile", "HAS_SOURCE"), ("ProcessedArtifact", "HAS_ARTIFACT"),
                       ("Batch", "HAS_BATCH"), ("Variable", "HAS_VARIABLE")):
        for n in nodes[label]:
            add("Dataset", dataset_id, rel, label, n[IDS[label]])
    artifacts = {n["output_table"]: n["artifact_id"] for n in nodes["ProcessedArtifact"]}
    sources = {n["source_file_id"].rsplit(":", 1)[-1]: n["source_file_id"] for n in nodes["SourceFile"]}
    for label in ("Batch", "Variable", "FaultAnnotation"):
        for n in nodes[label]:
            add(label, n[IDS[label]], "FROM_SOURCE", "SourceFile", n["source_file_id"])
    for b in nodes["Batch"]:
        for name in ("batches", "samples"):
            add("Batch", b["batch_id"], "HAS_DATA", "ProcessedArtifact", artifacts.get(name))
    for v in nodes["Variable"]:
        add("Variable", v["variable_id"], "HAS_DATA", "ProcessedArtifact", artifacts.get(v["output_table"]))
    for a in nodes["FaultAnnotation"]:
        add("Batch", a["batch_id"], "HAS_ANNOTATION", "FaultAnnotation", a["annotation_id"])
    for a in nodes["ProcessedArtifact"]:
        kinds = {"batches": ("statistics",), "samples": ("timeseries",),
                 "variables": ("statistics", "timeseries")}.get(a["output_table"], ())
        for kind in kinds:
            add("ProcessedArtifact", a["artifact_id"], "DERIVED_FROM", "SourceFile", sources.get(kind))
    return edges


def _run(driver, query, database="neo4j", **params):
    with driver.session(database=database) as session:
        return session.execute_read(lambda tx: [r.data() for r in tx.run(query, **params)])


def _write(driver, query, database="neo4j", **params):
    with driver.session(database=database) as session:
        session.execute_write(lambda tx: tx.run(query, **params).consume())


def graph_counts(driver, dataset_id, database="neo4j"):
    rows = _run(driver, "MATCH (n {dataset_id: $dataset_id}) RETURN labels(n) AS labels, count(*) AS count",
                database, dataset_id=dataset_id)
    counts = {label: 0 for label in IDS}
    total = 0
    for row in rows:
        total += row["count"]
        for label in row["labels"]:
            counts[label] = counts.get(label, 0) + row["count"]
    rels = {rel: 0 for rel in REL_TYPES}
    rows = _run(driver, "MATCH (n)-[r]->(m) WHERE n.dataset_id = $dataset_id OR m.dataset_id = $dataset_id "
                "RETURN type(r) AS type, count(*) AS count", database, dataset_id=dataset_id)
    for row in rows:
        rels[row["type"]] = row["count"]
    return {"nodes": counts, "relationships": rels, "total_nodes": total,
            "total_relationships": sum(rels.values())}


def check_graph_integrity(driver, dataset_id, database="neo4j"):
    """Compare endpoint identities and edge multiplicity, not merely totals."""
    rows = _run(driver, "MATCH (n {dataset_id: $dataset_id}) RETURN labels(n) AS labels, properties(n) AS node",
                database, dataset_id=dataset_id)
    nodes = {label: [] for label in IDS}
    invalid = 0
    for row in rows:
        if len(row["labels"]) != 1 or row["labels"][0] not in IDS:
            invalid += 1
        else:
            nodes[row["labels"][0]].append(row["node"])
    duplicates = {label: sum(n - 1 for n in Counter(r.get(key) for r in nodes[label]).values())
                  for label, key in IDS.items()}
    errors = []
    try:
        _require(len(nodes["Dataset"]) == 1, "Dataset missing")
        d = nodes["Dataset"][0]
        _require(d["graph_model_version"] == MODEL_VERSION, "Model version mismatch")
        _require(d["load_state"] in ("loading", "complete"), "Invalid load state")
        kinds = {"Dataset": "published_simulation_dataset", "SourceFile": "published_source",
                 "ProcessedArtifact": "derived_artifact", "Batch": "published_simulation_record",
                 "Variable": "published_variable_definition", "FaultAnnotation": "published_annotation"}
        _require(all(n.get("record_kind") == kinds[label] for label, records in nodes.items() for n in records),
                 "Record provenance kind mismatch")
        for key in ("manifest_sha256", "cache_key"):
            _require(isinstance(d[key], str) and re.fullmatch(r"[0-9a-f]{64}", d[key]), "Invalid dataset fingerprint")
        expected_counts = {"Dataset": 1, "SourceFile": 2, "ProcessedArtifact": 3,
                           "Batch": d["expected_batch_count"], "Variable": d["expected_variable_count"],
                           "FaultAnnotation": d["expected_batch_count"]}
        _require(all(len(nodes[k]) == v for k, v in expected_counts.items()), "Node counts mismatch")
        source_ids = {n["source_file_id"] for n in nodes["SourceFile"]}
        _require(source_ids == {dataset_id + ":statistics", dataset_id + ":timeseries"}, "Source IDs mismatch")
        sources = {s["source_file_id"].rsplit(":", 1)[-1]: s for s in nodes["SourceFile"]}
        _require(len({s["archive_sha256"] for s in sources.values()}) == 1, "Source archive disagreement")
        for source in sources.values():
            _require(_safe_path(source["source_member_path"]) and
                     source["source_member_path"] == source["path"] and _safe_path(source["archive_filename"]) and
                     re.fullmatch(r"[0-9a-f]{64}", source["archive_sha256"]), "Invalid source provenance")
        _require(sources["statistics"]["rows"] == d["expected_batch_count"], "Statistics count mismatch")
        _require({a["output_table"] for a in nodes["ProcessedArtifact"]} == set(ingestion.OUTPUT_TABLES),
                 "Artifact tables mismatch")
        for a in nodes["ProcessedArtifact"]:
            _require(a["filename"] == a["output_table"] + ".parquet" and
                     a["artifact_id"] == _artifact_id(dataset_id, a["filename"], a["sha256"]), "Artifact ID mismatch")
            _require(re.fullmatch(r"[0-9a-f]{64}", a["sha256"]) and a["bytes"] > 0, "Invalid artifact fingerprint")
            expected_rows = {"batches": sources["statistics"]["rows"], "samples": sources["timeseries"]["rows"],
                             "variables": d["expected_variable_count"]}
            _require(a["rows"] == expected_rows[a["output_table"]], "Artifact row count mismatch")
        for b in nodes["Batch"]:
            _require(b["batch_id"] == f"{dataset_id}:batch:{b['batch_ref']:03d}" and
                     b["source_file_id"] == dataset_id + ":statistics", "Batch identity/source mismatch")
            _require(set(b) == set(BATCH_FIELDS) | {"record_kind"}, "Unexpected Batch properties")
            _require(b["sample_count"] > 0 and 0 < b["time_start_h"] <= b["time_end_h"] and
                     0 < b["timeseries_first_source_row"] <= b["timeseries_last_source_row"] <= sources["timeseries"]["rows"],
                     "Invalid batch bounds")
        _require(len({b["batch_ref"] for b in nodes["Batch"]}) == d["expected_batch_count"] and
                 {b["source_row_number"] for b in nodes["Batch"]} == set(range(1, d["expected_batch_count"] + 1)) and
                 sum(b["sample_count"] for b in nodes["Batch"]) == sources["timeseries"]["rows"],
                 "Batch source/count coverage mismatch")
        for v in nodes["Variable"]:
            _require(v["output_table"] in ("samples", "batches"), "Invalid variable table")
            _require(v["variable_id"] == f"{dataset_id}:variable:{v['output_column']}" and
                     v["source_file_id"] == dataset_id + (":timeseries" if v["output_table"] == "samples" else ":statistics"),
                     "Variable identity/source mismatch")
            _require(set(v) == set(VARIABLE_FIELDS) | {"record_kind"}, "Unexpected Variable properties")
            source_kind = "timeseries" if v["output_table"] == "samples" else "statistics"
            _require(0 <= v["source_column_index"] < sources[source_kind]["row_fields"], "Variable column out of bounds")
        batch_map = {b["batch_id"]: b for b in nodes["Batch"]}
        for a in nodes["FaultAnnotation"]:
            b = batch_map[a["batch_id"]]
            _require(a["annotation_id"] == a["batch_id"] + ":annotation:published_fault_present" and
                     a["source_row_number"] == b["source_row_number"] and
                     a["source_file_id"] == b["source_file_id"] and type(a["fault_present"]) is bool and
                     a["source_column_index"] == 4 and a["source_header"] == "Fault ref(0-NoFault 1-Fault)" and
                     a["annotation_kind"] == "published_batch_fault_presence",
                     "Annotation identity/provenance mismatch")
        expected = Counter(_expected_edges(nodes, dataset_id))
    except (ValueError, KeyError, TypeError) as error:
        errors.append(str(error))
        expected = Counter()
    rel_rows = _run(driver, "MATCH (n)-[r]->(m) WHERE n.dataset_id = $dataset_id OR m.dataset_id = $dataset_id "
                    "RETURN labels(n) AS left_labels, properties(n) AS left_node, type(r) AS type, "
                    "labels(m) AS right_labels, properties(m) AS right_node", database, dataset_id=dataset_id)
    actual = Counter()
    for r in rel_rows:
        if (len(r["left_labels"]) != 1 or len(r["right_labels"]) != 1 or
                r["left_labels"][0] not in IDS or r["right_labels"][0] not in IDS or
                r["left_node"].get("dataset_id") != dataset_id or r["right_node"].get("dataset_id") != dataset_id):
            invalid += 1
            continue
        left, right = r["left_labels"][0], r["right_labels"][0]
        actual[(left, r["left_node"].get(IDS[left]), r["type"], right, r["right_node"].get(IDS[right]))] += 1
    missing = {rel: 0 for rel in REL_TYPES}
    for edge, count in (expected - actual).items():
        missing[edge[2]] += count
    extra = sum((actual - expected).values())
    return {"ok": not (errors or invalid or any(duplicates.values()) or any(missing.values()) or extra),
            "duplicate_ids": duplicates, "missing_relationships": missing, "unexpected_relationships": extra,
            "invalid_entities": invalid, "errors": errors}


def load_graph(driver, processed_dir, database="neo4j", batch_size=100, replace=False,
               contract_path=DEFAULT_CONTRACT):
    _require(type(batch_size) is int and batch_size > 0, "batch_size must be a positive integer")
    bundle = validate_processed(processed_dir, contract_path)
    nodes, edges = _project(bundle)
    dataset = nodes["Dataset"][0]
    dataset_id = dataset["dataset_id"]
    for label, key in IDS.items():
        _write(driver, f"CREATE CONSTRAINT pharmagraph_{label.lower()}_id IF NOT EXISTS "
               f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE", database)

    def guard(tx):
        record = tx.run("MERGE (d:Dataset {dataset_id: $dataset_id}) "
                        "SET d._graph_guard = true REMOVE d._graph_guard RETURN properties(d) AS node",
                        dataset_id=dataset_id).single(strict=True)
        existing = record["node"]
        pin_keys = ("manifest_sha256", "cache_key", "graph_model_version")
        initialized = bool(set(existing) - {"dataset_id"})
        different = initialized and any(existing.get(k) != dataset[k] for k in pin_keys)
        _require(not different or replace, "Dataset pins a different manifest/model; use explicit --replace")
        if replace:
            tx.run("MATCH (d:Dataset {dataset_id: $dataset_id}), (n {dataset_id: $dataset_id}) "
                   "WHERE n <> d DETACH DELETE n",
                   dataset_id=dataset_id).consume()
        tx.run("MATCH (d:Dataset {dataset_id: $dataset_id}) SET d = $properties",
               dataset_id=dataset_id, properties=dataset).consume()
    with driver.session(database=database) as session:
        session.execute_write(guard)
    for label, records in nodes.items():
        if label == "Dataset":
            continue
        key = IDS[label]
        query = (f"UNWIND $rows AS row MERGE (n:{label} {{{key}: row.{key}}}) "
                 "ON CREATE SET n.dataset_id = $dataset_id WITH n, row "
                 "WHERE n.dataset_id = $dataset_id SET n = row RETURN count(n) AS count")
        for offset in range(0, len(records), batch_size):
            chunk = records[offset:offset + batch_size]
            def write_chunk(tx):
                count = tx.run(query, rows=chunk, dataset_id=dataset_id).single(strict=True)["count"]
                _require(count == len(chunk), "ID belongs to a different dataset")
            with driver.session(database=database) as session:
                session.execute_write(write_chunk)
    grouped = defaultdict(list)
    for left, a, rel, right, b in edges:
        grouped[(left, rel, right)].append({"left": a, "right": b})
    for (left, rel, right), records in grouped.items():
        query = (f"UNWIND $rows AS row MATCH (a:{left} {{{IDS[left]}: row.left}}) "
                 f"MATCH (b:{right} {{{IDS[right]}: row.right}}) "
                 "WHERE a.dataset_id = $dataset_id AND b.dataset_id = $dataset_id "
                 f"MERGE (a)-[:{rel}]->(b)")
        for offset in range(0, len(records), batch_size):
            _write(driver, query, database, rows=records[offset:offset + batch_size], dataset_id=dataset_id)
    actual = graph_counts(driver, dataset_id, database)
    expected = {"nodes": {label: len(records) for label, records in nodes.items()},
                "relationships": dict(Counter(e[2] for e in edges)),
                "total_nodes": sum(map(len, nodes.values())), "total_relationships": len(edges)}
    integrity = check_graph_integrity(driver, dataset_id, database)
    _require(actual == expected and integrity["ok"], f"Graph validation failed: {integrity}")
    def complete(tx):
        result = tx.run("MATCH (d:Dataset {dataset_id: $dataset_id, manifest_sha256: $sha, "
                        "cache_key: $cache_key, graph_model_version: $model_version}) "
                        "SET d.load_state = 'complete' RETURN count(d) AS count",
                        dataset_id=dataset_id, sha=bundle["manifest_sha256"],
                        cache_key=dataset["cache_key"], model_version=MODEL_VERSION)
        _require(result.single(strict=True)["count"] == 1, "Dataset changed while loading")
    with driver.session(database=database) as session:
        session.execute_write(complete)
    return {"status": "complete", "dataset_id": dataset_id, "manifest_sha256": bundle["manifest_sha256"],
            "expected_counts": expected, "actual_counts": actual, "integrity": integrity}


def _complete(driver, dataset_id, database):
    rows = _run(driver, "MATCH (d:Dataset {dataset_id: $dataset_id}) "
                "RETURN d.load_state AS state, d.graph_model_version AS version", database, dataset_id=dataset_id)
    _require(len(rows) == 1 and rows[0] == {"state": "complete", "version": MODEL_VERSION},
             "Dataset is missing, incomplete, or uses an unsupported model")


def list_batches(driver, dataset_id, database="neo4j"):
    _complete(driver, dataset_id, database)
    return _run(driver, "MATCH (d:Dataset {dataset_id: $dataset_id, load_state: 'complete', "
                "graph_model_version: $model_version})-[:HAS_BATCH]->(b:Batch) "
                "WHERE b.dataset_id = $dataset_id "
                "RETURN b.batch_id AS batch_id, b.batch_ref AS batch_ref, b.sample_count AS sample_count, "
                "b.time_start_h AS time_start_h, b.time_end_h AS time_end_h ORDER BY batch_ref",
                database, dataset_id=dataset_id, model_version=MODEL_VERSION)


def _fields(alias, fields):
    return ", ".join(f"{alias}.{key} AS {key}" for key in fields)


def list_variables(driver, dataset_id, database="neo4j", detector_only=True):
    _require(type(detector_only) is bool, "detector_only must be boolean")
    _complete(driver, dataset_id, database)
    return _run(driver, "MATCH (d:Dataset {dataset_id: $dataset_id, load_state: 'complete', "
                "graph_model_version: $model_version})-[:HAS_VARIABLE]->(v:Variable) "
                "WHERE v.dataset_id = $dataset_id AND (NOT $detector_only OR v.output_table = 'samples') RETURN " +
                _fields("v", VARIABLE_FIELDS) + " ORDER BY output_table, source_column_index",
                database, dataset_id=dataset_id, detector_only=detector_only, model_version=MODEL_VERSION)


def _batch_variables(driver, dataset_id, batch_ref, database, detector_only, variable_name=None):
    _require(type(batch_ref) is int and batch_ref > 0, "batch_ref must be a positive integer")
    _require(type(detector_only) is bool, "detector_only must be boolean")
    _complete(driver, dataset_id, database)
    query = """
    MATCH (d:Dataset {dataset_id: $dataset_id, load_state: 'complete', graph_model_version: $model_version})
      -[:HAS_BATCH]->(b:Batch {batch_ref: $batch_ref})
    MATCH (d)-[:HAS_VARIABLE]->(v:Variable)-[:HAS_DATA]->(a:ProcessedArtifact)<-[:HAS_DATA]-(b)
    MATCH (v)-[:FROM_SOURCE]->(s:SourceFile)<-[:DERIVED_FROM]-(a)
    WHERE (NOT $detector_only OR v.output_table = 'samples') AND a.output_table = v.output_table
      AND ($variable_name IS NULL OR v.output_column = $variable_name OR v.variable_id = $variable_name)
      AND s.source_file_id = v.source_file_id AND b.dataset_id = d.dataset_id
      AND v.dataset_id = d.dataset_id AND a.dataset_id = d.dataset_id AND s.dataset_id = d.dataset_id
    RETURN """ + _fields("v", VARIABLE_FIELDS) + """,
      b.batch_id AS batch_id, b.batch_ref AS batch_ref, b.sample_count AS sample_count,
      b.time_start_h AS time_start_h, b.time_end_h AS time_end_h,
      b.timeseries_first_source_row AS timeseries_first_source_row,
      b.timeseries_last_source_row AS timeseries_last_source_row,
      CASE WHEN v.output_table = 'batches' THEN b.source_row_number ELSE null END AS source_row_number,
      a.artifact_id AS artifact_id, a.filename AS artifact_filename, a.sha256 AS artifact_sha256,
      s.source_member_path AS source_member_path, s.archive_sha256 AS source_archive_sha256,
      d.manifest_sha256 AS manifest_sha256, d.cache_key AS cache_key
    ORDER BY output_table, source_column_index
    """
    return _run(driver, query, database, dataset_id=dataset_id, batch_ref=batch_ref,
                detector_only=detector_only, variable_name=variable_name, model_version=MODEL_VERSION)


def batch_variables(driver, dataset_id, batch_ref, database="neo4j", detector_only=True):
    return _batch_variables(driver, dataset_id, batch_ref, database, detector_only)


def get_reference(driver, dataset_id, batch_ref, variable_name, database="neo4j", detector_only=True):
    _require(isinstance(variable_name, str) and bool(variable_name), "variable_name must be a nonempty string")
    rows = _batch_variables(driver, dataset_id, batch_ref, database, detector_only, variable_name)
    _require(len(rows) == 1, "Unknown batch or unknown/unallowed variable")
    return rows[0]


def _local_reference(bundle, batch_ref, variable_name):
    """Authoritative reference reconstructed from verified tables, never client metadata."""
    m = bundle["manifest"]
    batches = [b for b in bundle["tables"]["batches"].to_pylist() if b["batch_ref"] == batch_ref]
    variables = [v for v in bundle["tables"]["variables"].to_pylist() if v["output_column"] == variable_name]
    _require(len(batches) == len(variables) == 1, "Unknown reference batch/variable")
    b, v = batches[0], variables[0]
    filename = v["output_table"] + ".parquet"
    a = m["outputs"][filename]
    s = next(s for s in m["source"]["members"] if s["source_file_id"] == v["source_file_id"])
    return {**v, **{k: b[k] for k in ("batch_id", "batch_ref", "sample_count", "time_start_h", "time_end_h",
                                     "timeseries_first_source_row", "timeseries_last_source_row")},
            "source_row_number": b["source_row_number"] if v["output_table"] == "batches" else None,
            "artifact_id": _artifact_id(m["dataset"]["id"], filename, a["sha256"]), "artifact_filename": filename,
            "artifact_sha256": a["sha256"], "source_member_path": s["path"],
            "source_archive_sha256": m["source"]["sha256"], "manifest_sha256": bundle["manifest_sha256"],
            "cache_key": m["cache_key"]}


def resolve_reference(reference, processed_dir, start_tick=None, end_tick=None, limit=None,
                      contract_path=DEFAULT_CONTRACT):
    for name, value in (("start_tick", start_tick), ("end_tick", end_tick), ("limit", limit)):
        _require(value is None or (type(value) is int and value >= (1 if name == "limit" else 0)),
                 f"{name} must be {'positive' if name == 'limit' else 'nonnegative'} integer or null")
    _require(start_tick is None or end_tick is None or start_tick <= end_tick, "Tick endpoints are reversed")
    _require(isinstance(reference, dict) and type(reference.get("batch_ref")) is int, "Invalid reference")
    bundle = validate_processed(processed_dir, contract_path)
    expected = _local_reference(bundle, reference["batch_ref"], reference.get("output_column"))
    _require(reference == expected, "Reference differs from pinned bundle metadata")
    table_name = expected["output_table"]
    _require(table_name == "samples" or (start_tick is None and end_tick is None), "Summary variables have no ticks")
    table = bundle["tables"][table_name]
    mask = pc.equal(table["batch_id"], expected["batch_id"])
    if start_tick is not None:
        mask = pc.and_(mask, pc.greater_equal(table["time_tick"], start_tick))
    if end_tick is not None:
        mask = pc.and_(mask, pc.less_equal(table["time_tick"], end_tick))
    columns = ["batch_id", "source_file_id", "source_row_number"]
    if table_name == "samples":
        columns = ["sample_id", "batch_id", "time_h", "time_tick", "source_file_id", "source_row_number"]
    selected = table.filter(mask).select(columns + [expected["output_column"]])
    if table_name == "samples":
        selected = selected.sort_by([("time_tick", "ascending")])
    if limit is not None:
        selected = selected.slice(0, limit)
    measurements = []
    for row in selected.to_pylist():
        row["value"] = row.pop(expected["output_column"])
        measurements.append(row)
    return {"reference": expected, "measurements": measurements}


def published_annotations(driver, dataset_id, batch_ref=None, database="neo4j"):
    _require(batch_ref is None or (type(batch_ref) is int and batch_ref > 0), "Invalid batch_ref")
    _complete(driver, dataset_id, database)
    return _run(driver, "MATCH (d:Dataset {dataset_id: $dataset_id, load_state: 'complete', "
                "graph_model_version: $model_version})-[:HAS_BATCH]->(b:Batch)"
                "-[:HAS_ANNOTATION]->(a:FaultAnnotation)-[:FROM_SOURCE]->(s:SourceFile) "
                "WHERE b.dataset_id = $dataset_id AND a.dataset_id = $dataset_id AND s.dataset_id = $dataset_id "
                "AND ($batch_ref IS NULL OR b.batch_ref = $batch_ref) "
                "RETURN b.batch_id AS batch_id, b.batch_ref AS batch_ref, a.annotation_id AS annotation_id, "
                "a.fault_present AS fault_present, a.annotation_kind AS annotation_kind, "
                "a.source_file_id AS source_file_id, a.source_row_number AS source_row_number, "
                "a.source_header AS source_header, a.source_column_index AS source_column_index, "
                "s.source_member_path AS source_member_path, s.archive_sha256 AS source_archive_sha256 "
                "ORDER BY batch_ref", database, dataset_id=dataset_id, batch_ref=batch_ref, model_version=MODEL_VERSION)


def environment(env_path=None):
    """Parse simple dotenv data without executing shell syntax; environment wins."""
    values = {}
    path = Path(env_path) if env_path is not None else ROOT / ".env"
    if path.is_file():
        for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            _require(bool(sep) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key.strip()),
                     f"Invalid .env assignment at line {number}")
            value = value.strip()
            if value.startswith(("'", '"')):
                _require(len(value) >= 2 and value[-1] == value[0], f"Unmatched .env quote at line {number}")
                value = value[1:-1]
            values[key.strip()] = value
    values.update(os.environ)
    return values


def driver_from_env():
    from neo4j import GraphDatabase
    values = environment()
    password = values.get("NEO4J_PASSWORD")
    _require(bool(password), "NEO4J_PASSWORD is required in environment or repo-root .env")
    return GraphDatabase.driver(values.get("NEO4J_URI", "bolt://127.0.0.1:7687"),
                                auth=(values.get("NEO4J_USER", "neo4j"), password), connection_timeout=10)


def cli_error(error):
    # Connection errors may include endpoint/user information. Never echo credentials.
    try:
        values = environment()
    except (OSError, ValueError):
        values = os.environ
    message = str(error)
    if values.get("NEO4J_PASSWORD"):
        message = message.replace(values["NEO4J_PASSWORD"], "[redacted]")
    message = re.sub(r"([A-Za-z][A-Za-z0-9+.-]*://)[^/\s]*@", r"\1[redacted]@", message)
    return {"status": "error", "error": f"{type(error).__name__}: {message}"}


class JSONArgumentParser(argparse.ArgumentParser):
    """Keep CLI errors machine-readable, while conventional --help stays text."""

    def error(self, message):
        raise ValueError(message)
