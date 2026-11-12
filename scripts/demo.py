"""Presentation and live-version helpers for the local evidence demo.

These helpers read only the existing graph and processed outputs. They do not
change the investigation result, numerical method, graph model or source data.
"""
import hashlib
import json
import math
from pathlib import Path

import plotly.graph_objects as go
import pyarrow as pa
import pyarrow.compute as pc

from . import graph, investigation


def canonical_json_bytes(result):
    return (json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def content_identity(processed_dir=graph.DEFAULT_OUTPUT):
    """Rehash local content every rerun, independently of any reusable cache."""
    root = Path(processed_dir).expanduser().resolve()
    raw = (root / "manifest.json").read_bytes()
    manifest = json.loads(raw)
    if not isinstance(manifest, dict):
        raise ValueError("Processed manifest must be an object")
    contract_sha256 = _file_hash(graph.DEFAULT_CONTRACT)
    if manifest.get("cache_inputs", {}).get("contract_sha256") != contract_sha256:
        raise ValueError("Processed manifest is incompatible with the current pinned contract")
    outputs = manifest.get("outputs", {})
    expected = {name + ".parquet" for name in ("batches", "samples", "variables")}
    if not isinstance(outputs, dict) or set(outputs) != expected:
        raise ValueError("Processed manifest output entries are incompatible")
    hashes = {}
    for filename in sorted(expected):
        path = root / filename
        item = outputs[filename]
        digest = _file_hash(path)
        if path.stat().st_size != item["bytes"] or digest != item["sha256"]:
            raise ValueError("Processed artifact integrity mismatch")
        hashes[filename] = digest
    if (root / "manifest.json").read_bytes() != raw:
        raise ValueError("Processed manifest changed while reading")
    identity = {"processed_dir": str(root), "dataset_id": manifest["dataset"]["id"],
                "graph_model_version": graph.MODEL_VERSION, "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                "contract_sha256": contract_sha256, "output_hashes": hashes, "manifest": manifest}
    identity["content_key"] = _hash({key: value for key, value in identity.items() if key != "manifest"})
    return identity


def connection_fingerprint(values=None):
    """A private cache key; credentials never become a displayed value or key."""
    values = graph.environment() if values is None else values
    return _hash({"uri": values.get("NEO4J_URI", "bolt://127.0.0.1:7687"),
                  "user": values.get("NEO4J_USER", "neo4j"), "password": values.get("NEO4J_PASSWORD", ""),
                  "database": values.get("NEO4J_DATABASE", "neo4j")})


def result_cache_key(identity, batch_id, connection_key, config=None):
    config = investigation.DetectorConfig() if config is None else config
    return _hash({"content_key": identity["content_key"], "dataset_id": identity["dataset_id"],
                  "model": graph.MODEL_VERSION, "batch_id": batch_id, "connection": connection_key,
                  "detector_id": investigation.DETECTOR_ID, "detector_version": investigation.DETECTOR_VERSION,
                  "configuration": investigation._configuration(config)})


def live_context(driver, bundle, database="neo4j"):
    """Never cached: connection, release pins, artifacts and batch metadata."""
    driver.verify_connectivity()
    investigation._check_graph_pins(driver, bundle, database)
    dataset_id = bundle["manifest"]["dataset"]["id"]
    batches = graph.list_batches(driver, dataset_id, database=database)
    local = bundle["tables"]["batches"].select(investigation.BATCH_FIELDS).to_pylist()
    if sorted(batches, key=lambda b: b["batch_id"]) != sorted(local, key=lambda b: b["batch_id"]):
        raise ValueError("Graph batch metadata differs from processed artifacts")
    return sorted(batches, key=lambda b: b["batch_ref"])


def reference_inventory(driver, bundle, batch_id, database="neo4j"):
    """Resolve the four trend references and reject missing or altered metadata."""
    local_batches = bundle["tables"]["batches"].select(["batch_id", "batch_ref"]).to_pylist()
    targets = [b for b in local_batches if b["batch_id"] == batch_id]
    if len(targets) != 1:
        raise ValueError("Unknown stable batch ID")
    dataset_id = bundle["manifest"]["dataset"]["id"]
    variable_inventory = graph.list_variables(driver, dataset_id, database=database, detector_only=True)
    local_variables = {v["output_column"]: v for v in bundle["tables"]["variables"].to_pylist()}
    variables = {}
    for v in variable_inventory:
        name = v.get("output_column")
        if name in investigation.DEFAULT_VARIABLES:
            if name in variables or v != local_variables.get(name):
                raise ValueError("Graph variable metadata differs from processed artifacts")
            variables[name] = v
    if set(variables) != set(investigation.DEFAULT_VARIABLES):
        raise ValueError("Selected graph variable definitions are unavailable")
    inventory = graph.batch_variables(driver, dataset_id, targets[0]["batch_ref"], database=database, detector_only=True)
    refs = {}
    for reference in inventory:
        name = reference.get("output_column")
        if name not in investigation.DEFAULT_VARIABLES:
            continue
        if name in refs or reference != graph._local_reference(bundle, targets[0]["batch_ref"], name):
            raise ValueError("Graph reference differs from processed artifacts")
        refs[name] = reference
    if set(refs) != set(investigation.DEFAULT_VARIABLES):
        raise ValueError("Selected graph variable references are unavailable")
    return {name: refs[name] for name in investigation.DEFAULT_VARIABLES}


def _measurement_groups(bundle, batch_ids, variables):
    table = bundle["tables"]["samples"].select([
        "batch_id", "sample_id", "time_tick", "time_h", "source_file_id", "source_row_number", *variables])
    table = table.filter(pc.is_in(table["batch_id"], value_set=pa.array(sorted(batch_ids))))
    grouped = {batch_id: {name: [] for name in variables} for batch_id in batch_ids}
    for row in table.to_pylist():
        identity = {key: row[key] for key in investigation.IDENTITY_FIELDS}
        for name in variables:
            grouped[row["batch_id"]][name].append({**identity, "value": row[name]})
    for per_batch in grouped.values():
        for rows in per_batch.values():
            rows.sort(key=lambda row: row["time_tick"])
    return grouped


def load_trends(driver, bundle, batch_id, database="neo4j"):
    refs = reference_inventory(driver, bundle, batch_id, database)
    batch = next(b for b in bundle["tables"]["batches"].select(investigation.BATCH_FIELDS).to_pylist()
                 if b["batch_id"] == batch_id)
    return {"batch": batch, "references": refs,
            "measurements": _measurement_groups(bundle, [batch_id], investigation.DEFAULT_VARIABLES)[batch_id]}


def plotting_points(driver, bundle, result, finding, database="neo4j"):
    """Recompute only one variable's plot context using the existing pure scorer."""
    investigation._check_graph_pins(driver, bundle, database)
    expected_dataset = {"dataset_id": bundle["manifest"]["dataset"]["id"],
                        "graph_model_version": graph.MODEL_VERSION, "manifest_sha256": bundle["manifest_sha256"],
                        "cache_key": bundle["manifest"]["cache_key"]}
    if any(result["dataset"].get(key) != value for key, value in expected_dataset.items()):
        raise ValueError("Investigation result belongs to an incompatible dataset")
    name = finding["variable"]
    if name not in investigation.DEFAULT_VARIABLES:
        raise ValueError("Unapproved plot variable")
    target_id = result["batch"]["batch_id"]
    target_ref = graph.get_reference(driver, expected_dataset["dataset_id"], result["batch"]["batch_ref"],
                                     name, database=database, detector_only=True)
    if target_ref != finding["reference"] or target_ref != graph._local_reference(bundle, result["batch"]["batch_ref"], name):
        raise ValueError("Current graph reference differs from investigation evidence")
    variable_result = next(v for v in result["variable_results"] if v["variable"] == name)
    peer_refs = variable_result["peer_references"]
    for peer_id, reference in peer_refs.items():
        if reference["batch_id"] != peer_id or reference != graph._local_reference(bundle, reference["batch_ref"], name):
            raise ValueError("Peer reference differs from investigation evidence")
    config_values = result["configuration"]
    config = investigation.DetectorConfig(variables=tuple(config_values["variables"]),
        min_peers=config_values["min_peers"], threshold=config_values["threshold"],
        min_consecutive=config_values["min_consecutive"],
        peer_batch_ids=None if config_values["peer_batch_ids"] is None else tuple(config_values["peer_batch_ids"]))
    grouped = _measurement_groups(bundle, [target_id, *peer_refs], (name,))
    return investigation.score_variable(grouped[target_id][name],
        {peer_id: grouped[peer_id][name] for peer_id in peer_refs}, config=config)["points"]


def result_state(result):
    variables = result.get("variable_results", [])
    skipped = sum(sum(v.get("skipped_tick_counts", {}).values()) for v in variables)
    assessed = sum(v.get("scored_point_count", 0) > 0 for v in variables)
    findings = len(result.get("findings", []))
    if findings:
        kind = "findings"
        message = f"{findings} retained statistical deviation interval{'s' if findings != 1 else ''}. These are derived comparisons of published simulation measurements."
    elif variables and all(v.get("skipped_reason") == "undocumented_process_compatibility" for v in variables):
        kind = "undocumented"
        message = "Not assessed: process compatibility is undocumented for this batch, so no compatible reference cohort was assigned."
    elif assessed:
        kind = "no_findings"
        message = "Assessed with no retained statistical deviation intervals. This is not proof of normal or safe operation."
    else:
        kind = "unscorable"
        message = "Not assessed: no scoreable data remained after finite-peer coverage and zero-MAD checks. This is not proof of normal or safe operation."
    return {"kind": kind, "message": message, "skipped_tick_count": skipped,
            "assessed_variable_count": assessed, "finding_count": findings}


def evidence_rows(finding):
    reference = finding["reference"]
    keys = ("sample_id", "batch_id", "time_tick", "time_h", "observed_value", "reference_median",
            "reference_mad", "reference_spread", "deviation_score", "peer_count", "source_file_id", "source_row_number")
    return [{**{key: p[key] for key in keys}, "source_column_index": reference["source_column_index"],
             "source_header": reference["source_header"]} for p in finding["evidence"]]


def trend_figure(measurements, variable, unit_reported):
    figure = go.Figure(go.Scatter(x=[r["time_h"] for r in measurements], y=[r["value"] for r in measurements],
        name="Observed", mode="lines", connectgaps=False, line={"color": "#087f82", "width": 1.7},
        hovertemplate="%{x:.1f} h<br>%{y}<extra>Published simulation</extra>"))
    figure.update_layout(title=variable.replace("_", " ").capitalize(), height=240, template="plotly_white",
        margin={"l": 20, "r": 15, "t": 45, "b": 25}, xaxis_title="Elapsed time (h)",
        yaxis_title=unit_reported, showlegend=False, font={"family": "Arial, sans-serif", "color": "#617187", "size": 11},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    figure.update_xaxes(gridcolor="#edf1f5", zeroline=False)
    figure.update_yaxes(gridcolor="#edf1f5", zeroline=False)
    return figure


def finding_figure(finding, points, threshold=6.0, unit_reported=None):
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("Plot threshold must be positive and finite")
    x, median, lower, upper, observed, tick_values = [], [], [], [], [], []
    for point in points:
        if tick_values and point["time_tick"] != tick_values[-1] + 1:
            x.append(None)
            median.append(None)
            lower.append(None)
            upper.append(None)
            observed.append(None)
        x.append(point["time_h"])
        observed.append(point["observed_value"])
        tick_values.append(point["time_tick"])
        valid = (point.get("status") in ("scored", "zero_mad_equal") and point.get("reference_median") is not None and
                 point.get("reference_spread") is not None)
        center = point["reference_median"] if valid else None
        median.append(center)
        lower.append(center - threshold * point["reference_spread"] if valid else None)
        upper.append(center + threshold * point["reference_spread"] if valid else None)
    figure = go.Figure()
    # Separate closed polygons keep the shaded reference itself from bridging
    # missing/unscoreable runs; connectgaps=False alone governs line drawing.
    segments, segment = [], []
    for index in range(len(x)):
        if lower[index] is None or upper[index] is None:
            if segment:
                segments.append(segment)
                segment = []
        else:
            segment.append(index)
    if segment:
        segments.append(segment)
    for segment in segments:
        figure.add_trace(go.Scatter(x=[x[i] for i in segment] + [x[i] for i in reversed(segment)],
            y=[upper[i] for i in segment] + [lower[i] for i in reversed(segment)], mode="lines",
            name="Statistical reference envelope", line={"width": 0}, fill="toself",
            fillcolor="rgba(88,125,134,0.12)", showlegend=False, hoverinfo="skip", connectgaps=False))
    figure.add_trace(go.Scatter(x=x, y=lower, name="Lower statistical reference", mode="lines",
        line={"color": "rgba(88,125,134,0.4)", "width": 0.7}, connectgaps=False))
    figure.add_trace(go.Scatter(x=x, y=upper, name="Upper statistical reference", mode="lines",
        line={"color": "rgba(88,125,134,0.4)", "width": 0.7}, connectgaps=False))
    figure.add_trace(go.Scatter(x=x, y=median, name="Peer median", mode="lines",
        line={"color": "#75869f", "width": 1.8, "dash": "dash"}, connectgaps=False))
    figure.add_trace(go.Scatter(x=x, y=observed, name="Observed", mode="lines",
        line={"color": "#087f82", "width": 2.5}, connectgaps=False))
    figure.add_vrect(x0=finding["start_time_h"], x1=finding["end_time_h"], fillcolor="#d89b3c", opacity=0.17,
                     line_width=0, layer="below")
    figure.update_layout(height=410, template="plotly_white", margin={"l": 25, "r": 20, "t": 25, "b": 35},
        xaxis_title="Elapsed time (h)", yaxis_title=unit_reported or finding["reference"]["unit_reported"],
        legend={"orientation": "h", "y": 1.05, "x": 0}, hovermode="x unified")
    available_times = [value for value in x if value is not None]
    if available_times:
        start = max(min(available_times), finding["start_time_h"] - 5)
        end = min(max(available_times), finding["end_time_h"] + 5)
        if start < end:
            figure.update_xaxes(range=[start, end])
    return figure


def graph_provenance(driver, reference, database="neo4j"):
    """Return actual directed relationships, matched with fixed parameterized Cypher."""
    query = """
    MATCH (d:Dataset {dataset_id: $dataset_id, load_state: 'complete', graph_model_version: $model})
      -[:HAS_BATCH]->(b:Batch {batch_id: $batch_id})
    MATCH (d)-[:HAS_VARIABLE]->(v:Variable {variable_id: $variable_id})
    MATCH (b)-[batch_data:HAS_DATA]->(a:ProcessedArtifact {artifact_id: $artifact_id})
      <-[variable_data:HAS_DATA]-(v)
    MATCH (v)-[variable_source:FROM_SOURCE]->(s:SourceFile {source_file_id: $source_file_id})
      <-[artifact_source:DERIVED_FROM]-(a)
    WHERE b.dataset_id = $dataset_id AND v.dataset_id = $dataset_id
      AND a.dataset_id = $dataset_id AND s.dataset_id = $dataset_id
      AND d.manifest_sha256 = $manifest_sha256 AND d.cache_key = $cache_key
      AND a.sha256 = $artifact_sha256 AND a.filename = $artifact_filename
      AND s.source_member_path = $source_member_path AND s.archive_sha256 = $source_archive_sha256
      AND v.source_file_id = $source_file_id AND v.source_column_index = $source_column_index
      AND v.source_header = $source_header
    RETURN b.batch_id AS batch_id, v.variable_id AS variable_id, a.artifact_id AS artifact_id,
      s.source_file_id AS source_file_id, type(batch_data) AS batch_data,
      type(variable_data) AS variable_data, type(variable_source) AS variable_source,
      type(artifact_source) AS artifact_source
    """
    names = ("dataset_id", "batch_id", "variable_id", "artifact_id", "source_file_id", "manifest_sha256", "cache_key",
             "artifact_sha256", "artifact_filename", "source_member_path", "source_archive_sha256", "source_column_index", "source_header")
    params = {name: reference[name] for name in names}
    with driver.session(database=database) as session:
        rows = session.execute_read(lambda tx: [r.data() for r in tx.run(query, model=graph.MODEL_VERSION, **params)])
    if len(rows) != 1:
        raise ValueError("The current graph provenance path is missing, ambiguous or incompatible")
    row = rows[0]
    return [{"from_label": left, "from_id": row[left_id], "relationship": row[relationship],
             "to_label": right, "to_id": row[right_id]}
            for left, left_id, relationship, right, right_id in (
                ("Batch", "batch_id", "batch_data", "ProcessedArtifact", "artifact_id"),
                ("Variable", "variable_id", "variable_data", "ProcessedArtifact", "artifact_id"),
                ("Variable", "variable_id", "variable_source", "SourceFile", "source_file_id"),
                ("ProcessedArtifact", "artifact_id", "artifact_source", "SourceFile", "source_file_id"))]


def safe_error_message(error):
    """Map internal failures to fixed actionable UI text; never echo exceptions."""
    name = type(error).__name__
    message = str(error).lower()
    if name in ("AuthError", "ServiceUnavailable", "SessionExpired", "ConfigurationError") or any(
            text in message for text in ("neo4j_password", "credentials", "connection", "connectivity", ".env")):
        return "Neo4j is unavailable or credentials were rejected. Start the local Neo4j service and check the server-side NEO4J settings."
    if isinstance(error, FileNotFoundError):
        return "Processed data are missing. Restore the verified manifest and three Parquet files, then reload the matching graph."
    if any(text in message for text in ("graph", "reference", "release", "pins", "version")):
        return "The graph and processed artifacts are incompatible or incomplete. Restore the verified dataset and reload its matching graph."
    if isinstance(error, (ValueError, OSError)) or name.startswith("Arrow"):
        return "Processed artifacts failed integrity checks. Restore the verified manifest and three Parquet files before continuing."
    return "The investigation is temporarily unavailable. Check the local Neo4j service and verified processed dataset."
