"""Deterministic descriptive deviations against compatible elapsed-tick peers.

Only the four configured process channels reach scoring. Published annotations
are neither queried nor used to select a cohort. Numerical evidence remains
bound to the graph's checked Parquet references and original source records.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math

import pyarrow as pa
import pyarrow.compute as pc

try:
    from . import graph
except ImportError:
    import graph


DEFAULT_VARIABLES = ("aeration_rate", "sugar_feed_rate", "ph", "temperature")
DETECTOR_ID = "elapsed_tick_peer_median_mad"
DETECTOR_VERSION = "1.0.0"
MAD_FACTOR = 1.4826
KNOWN_GROUPS = ("recipe_driven", "operator_controlled", "apc_raman")
MEASUREMENT_FIELDS = ("batch_id", "sample_id", "time_tick", "time_h", "value", "source_file_id", "source_row_number")
IDENTITY_FIELDS = tuple(k for k in MEASUREMENT_FIELDS if k != "value")
BATCH_FIELDS = ("batch_id", "batch_ref", "sample_count", "time_start_h", "time_end_h")
COHORT_POLICY = "same documented control_regime, overlapping elapsed time, target excluded"
LIMITATIONS = (
    "Compatibility uses published control-regime grouping only; it does not establish identical recipes, conditions or process phases.",
    "Peer batches may contain atypical behavior; no annotation-based filtering or clean-reference guarantee is applied.",
    "Equal elapsed-time ticks do not establish biological or process-phase alignment between batches.",
    "Deviation scores and thresholds are descriptive heuristics with no calibrated accuracy, probability or severity interpretation.",
    "Insufficient finite peer coverage and zero-MAD differences are unscorable; missing values break runs without imputation.",
    "Selection is limited to aeration_rate, sugar_feed_rate, ph and temperature; unselected channels are not assessed.",
    "Values are published simulation measurements with source-reported units; units and physical plant behavior are not independently validated.",
    "Derived intervals do not establish a named fault, root cause, causal relationship, quality decision or operating specification.",
)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value):
    return type(value) in (int, float)


@dataclass(frozen=True)
class DetectorConfig:
    variables: tuple[str, ...] = DEFAULT_VARIABLES
    min_peers: int = 10
    threshold: float = 6.0
    min_consecutive: int = 5
    peer_batch_ids: tuple[str, ...] | None = None

    def __post_init__(self):
        _require(type(self.variables) is tuple and bool(self.variables) and
                 all(type(v) is str and v in DEFAULT_VARIABLES for v in self.variables) and
                 len(set(self.variables)) == len(self.variables), "variables must be a nonempty unique tuple from the four-channel allowlist")
        _require(type(self.min_peers) is int and self.min_peers >= 2, "min_peers must be an integer >= 2")
        _require(_number(self.threshold) and math.isfinite(self.threshold) and self.threshold > 0,
                 "threshold must be a positive finite number")
        _require(type(self.min_consecutive) is int and self.min_consecutive >= 1,
                 "min_consecutive must be a positive integer")
        object.__setattr__(self, "threshold", float(self.threshold))
        if self.peer_batch_ids is not None:
            _require(type(self.peer_batch_ids) is tuple and
                     all(type(v) is str and bool(v.strip()) for v in self.peer_batch_ids) and
                     len(set(self.peer_batch_ids)) == len(self.peer_batch_ids),
                     "peer_batch_ids must be a unique tuple of nonempty strings or null")
            object.__setattr__(self, "peer_batch_ids", tuple(sorted(self.peer_batch_ids)))


def _config(config):
    _require(config is None or type(config) is DetectorConfig, "config must be DetectorConfig or null")
    return DetectorConfig() if config is None else config


def _clean_measurements(rows, expected_batch_id=None):
    """Validate coordinates and copy only the numerical evidence allowlist."""
    _require(type(rows) is list, "measurement records must be a list")
    cleaned, ticks, sample_ids = [], set(), set()
    observed_batch = expected_batch_id
    for row in rows:
        _require(isinstance(row, dict) and set(MEASUREMENT_FIELDS).issubset(row), "Incomplete measurement record")
        for key in ("batch_id", "sample_id", "source_file_id"):
            _require(type(row[key]) is str and bool(row[key].strip()), f"{key} must be a nonempty string")
        if observed_batch is None:
            observed_batch = row["batch_id"]
        _require(row["batch_id"] == observed_batch, "Measurements mix batch identities")
        tick, time_h, source_row = row["time_tick"], row["time_h"], row["source_row_number"]
        _require(type(tick) is int and tick >= 0, "time_tick must be a nonnegative integer")
        _require(_number(time_h) and math.isfinite(time_h) and time_h >= 0, "time_h must be a finite nonnegative number")
        _require(type(source_row) is int and source_row > 0, "source_row_number must be a positive integer")
        _require(tick not in ticks, "Duplicate measurement tick")
        _require(row["sample_id"] not in sample_ids, "Duplicate sample identity")
        _require(row["value"] is None or _number(row["value"]), "value must be numeric or null")
        ticks.add(tick)
        sample_ids.add(row["sample_id"])
        cleaned.append({key: row[key] for key in MEASUREMENT_FIELDS})
    return sorted(cleaned, key=lambda row: row["time_tick"]), observed_batch


def _median(values):
    """Equivalent median, avoiding addition overflow for two large middles."""
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    left, right = ordered[middle - 1], ordered[middle]
    return left + (right - left) / 2 if (left >= 0) == (right >= 0) else left / 2 + right / 2


def score_variable(target_measurements, peer_measurements, config=None):
    """Pure, reproducible median/MAD scores and same-direction tick intervals."""
    config = _config(config)
    target, target_id = _clean_measurements(target_measurements)
    _require(type(peer_measurements) is dict and
             all(type(key) is str and bool(key.strip()) for key in peer_measurements),
             "peer_measurements must map nonempty batch IDs to measurement lists")
    peers = {}
    for batch_id in sorted(peer_measurements):
        if batch_id == target_id:
            continue
        rows, _ = _clean_measurements(peer_measurements[batch_id], batch_id)
        peers[batch_id] = {row["time_tick"]: row for row in rows}
    points = []
    skipped = Counter()
    for row in target:
        tick = row["time_tick"]
        peer_rows = [peers[batch_id][tick] for batch_id in peers if tick in peers[batch_id]]
        finite = [r for r in peer_rows if r["value"] is not None and math.isfinite(r["value"])]
        value = row["value"]
        point = {key: row[key] for key in IDENTITY_FIELDS}
        point.update(observed_value=value if value is not None and math.isfinite(value) else None,
                     reference_median=None, reference_mad=None, reference_spread=None, deviation_score=None,
                     peer_count=len(finite), peer_row_count=len(peer_rows),
                     peer_batch_ids=[r["batch_id"] for r in finite], peer_measurements=finite,
                     status=None, exceeds=False, direction=None)
        if value is None:
            point["status"] = "missing_target"
        elif not math.isfinite(value):
            point["status"] = "nonfinite_target"
        elif not peer_rows:
            point["status"] = "unmatched_tick"
        elif len(finite) < config.min_peers:
            point["status"] = "insufficient_peers"
        else:
            median = _median([r["value"] for r in finite])
            mad = _median([abs(r["value"] - median) for r in finite])
            spread = MAD_FACTOR * mad
            point["direction"] = "above" if value > median else "below" if value < median else "equal"
            if not all(math.isfinite(v) for v in (median, mad, spread)):
                point["status"] = "nonfinite_reference"
            else:
                point.update(reference_median=median, reference_mad=mad, reference_spread=spread)
                if mad == 0:
                    point["status"] = "zero_mad_equal" if value == median else "zero_mad_unscorable"
                    point["deviation_score"] = 0.0 if value == median else None
                else:
                    score = abs(value - median) / spread
                    if not math.isfinite(score):
                        point["status"] = "nonfinite_score"
                    else:
                        point.update(status="scored", deviation_score=score, exceeds=score > config.threshold)
        if point["deviation_score"] is None:
            skipped[point["status"]] += 1
        points.append(point)
    intervals, run = [], []

    def finish_run():
        if len(run) >= config.min_consecutive:
            scores = [p["deviation_score"] for p in run]
            intervals.append({"start_tick": run[0]["time_tick"], "end_tick": run[-1]["time_tick"],
                              "start_time_h": run[0]["time_h"], "end_time_h": run[-1]["time_h"],
                              "direction": run[0]["direction"], "point_count": len(run),
                              "statistical_deviation_score": math.fsum(s / len(scores) for s in scores),
                              "peak_deviation_score": max(scores), "evidence": list(run)})
        run.clear()

    for point in points:
        continues = (run and point["time_tick"] == run[-1]["time_tick"] + 1 and
                     point["direction"] == run[-1]["direction"])
        if not point["exceeds"] or (run and not continues):
            finish_run()
        if point["exceeds"]:
            run.append(point)
    finish_run()
    intervals.sort(key=lambda interval: (-interval["statistical_deviation_score"],
                                       -interval["peak_deviation_score"], interval["start_tick"]))
    return {"points": points, "intervals": intervals, "skipped_tick_counts": dict(sorted(skipped.items())),
            "target_point_count": len(points),
            "scored_point_count": sum(p["deviation_score"] is not None for p in points),
            "exceeding_point_count": sum(p["exceeds"] for p in points)}


def _configuration(config):
    return {"variables": list(config.variables), "min_peers": config.min_peers, "threshold": config.threshold,
            "min_consecutive": config.min_consecutive,
            "peer_batch_ids": None if config.peer_batch_ids is None else list(config.peer_batch_ids),
            "mad_factor": MAD_FACTOR, "cohort_policy": COHORT_POLICY,
            "threshold_rule": "strictly greater than threshold",
            "zero_mad_policy": "equal: score 0; different: unscorable; no epsilon or floor",
            "missing_data_policy": "omit nonfinite peers; missing targets and unscorable ticks break runs; no imputation"}


def _artifact_records(bundle):
    dataset_id = bundle["manifest"]["dataset"]["id"]
    return [{"artifact_id": f"{dataset_id}:artifact:{name}:sha256:{item['sha256']}",
             "filename": name, "sha256": item["sha256"], "bytes": item["bytes"], "rows": item["rows"],
             "record_kind": "derived_artifact"}
            for name, item in sorted(bundle["manifest"]["outputs"].items())]


def _recheck_bundle(bundle):
    root = bundle["processed_dir"]
    _require(graph.ingestion._sha256(root / "manifest.json") == bundle["manifest_sha256"],
             "Processed manifest changed during investigation")
    for filename, item in bundle["manifest"]["outputs"].items():
        path = root / filename
        _require(path.stat().st_size == item["bytes"] and graph.ingestion._sha256(path) == item["sha256"],
                 "Processed artifact changed during investigation")


def _check_graph_pins(driver, bundle, database):
    """Check release pins even when no selected variable reference is available."""
    dataset_id = bundle["manifest"]["dataset"]["id"]
    query = """
    MATCH (d:Dataset {dataset_id: $dataset_id})
    OPTIONAL MATCH (d)-[:HAS_ARTIFACT]->(a:ProcessedArtifact)
    RETURN d.dataset_id AS dataset_id, d.load_state AS load_state,
           d.graph_model_version AS graph_model_version,
           d.manifest_sha256 AS manifest_sha256, d.cache_key AS cache_key,
           collect({dataset_id: a.dataset_id, artifact_id: a.artifact_id,
                    filename: a.filename, sha256: a.sha256, bytes: a.bytes,
                    rows: a.rows, output_table: a.output_table, record_kind: a.record_kind}) AS artifacts
    """
    with driver.session(database=database) as session:
        rows = session.execute_read(lambda tx: [r.data() for r in tx.run(query, dataset_id=dataset_id)])
    _require(len(rows) == 1, "Graph dataset release is missing or ambiguous")
    expected = {"dataset_id": dataset_id, "load_state": "complete", "graph_model_version": graph.MODEL_VERSION,
                "manifest_sha256": bundle["manifest_sha256"], "cache_key": bundle["manifest"]["cache_key"]}
    _require({key: rows[0].get(key) for key in expected} == expected,
             "Graph dataset pins differ from complete processed release")
    artifacts = rows[0]["artifacts"]
    expected_artifacts = [{**a, "dataset_id": dataset_id, "output_table": a["filename"].removesuffix(".parquet")}
                          for a in _artifact_records(bundle)]
    _require(len(artifacts) == 3 and all(isinstance(a.get("filename"), str) for a in artifacts) and
             sorted(artifacts, key=lambda a: a["filename"]) == expected_artifacts,
             "Graph artifact pins differ from processed release")


def _references(driver, dataset_id, batch_ref, variables, bundle, database):
    inventory = graph.batch_variables(driver, dataset_id, batch_ref, database=database, detector_only=True)
    references = {}
    for reference in inventory:
        variable = reference.get("output_column")
        if variable not in variables:
            continue
        _require(variable not in references, "Duplicate graph variable reference")
        authoritative = graph._local_reference(bundle, batch_ref, variable)
        _require(reference == authoritative, "Graph reference differs from pinned processed bundle")
        references[variable] = reference
    return references


def investigate_batch(driver, batch_id, processed_dir=graph.DEFAULT_OUTPUT, database="neo4j", config=None,
                      contract_path=graph.DEFAULT_CONTRACT):
    """Read graph-resolved, compatible process channels and return derived evidence."""
    config = _config(config)
    _require(type(batch_id) is str and bool(batch_id), "batch_id must be an exact nonempty stable ID")
    bundle = graph.validate_processed(processed_dir, contract_path=contract_path)
    dataset_id = bundle["manifest"]["dataset"]["id"]
    _check_graph_pins(driver, bundle, database)
    local_batches = {b["batch_id"]: b for b in bundle["tables"]["batches"].select(BATCH_FIELDS).to_pylist()}
    _require(batch_id in local_batches, "Unknown stable batch ID in processed dataset")
    batches = graph.list_batches(driver, dataset_id, database=database)
    _require(len(batches) == len(local_batches) and len({b["batch_id"] for b in batches}) == len(batches),
             "Graph/processed batch identity or count mismatch")
    for batch in batches:
        _require(batch == local_batches.get(batch.get("batch_id")), "Graph/processed batch metadata mismatch")
    by_id = {b["batch_id"]: b for b in batches}
    target = by_id[batch_id]
    if config.peer_batch_ids is not None:
        _require(set(config.peer_batch_ids).issubset(by_id), "Unknown requested peer batch ID")
    compatibility = {b["batch_id"]: b for b in bundle["tables"]["batches"].select([
        "batch_id", "batch_ref", "control_regime"]).to_pylist()}
    group = compatibility[batch_id]["control_regime"]
    cohort, exclusions = [], []
    for candidate_id in sorted(by_id):
        candidate = by_id[candidate_id]
        reason = None
        if candidate_id == batch_id:
            reason = "target_excluded"
        elif config.peer_batch_ids is not None and candidate_id not in config.peer_batch_ids:
            reason = "not_requested"
        elif group not in KNOWN_GROUPS or compatibility[candidate_id]["control_regime"] not in KNOWN_GROUPS:
            reason = "undocumented_process_compatibility"
        elif compatibility[candidate_id]["control_regime"] != group:
            reason = "incompatible_process_compatibility"
        elif candidate["time_start_h"] > target["time_end_h"] or candidate["time_end_h"] < target["time_start_h"]:
            reason = "no_overlapping_elapsed_time"
        if reason:
            exclusions.append({"batch_id": candidate_id, "batch_ref": candidate["batch_ref"], "reason": reason})
        else:
            cohort.append({"batch_id": candidate_id, "batch_ref": candidate["batch_ref"]})
    local_variables = {v["output_column"]: v for v in bundle["tables"]["variables"].to_pylist()}
    inventory = graph.list_variables(driver, dataset_id, database=database, detector_only=True)
    graph_variables = {}
    for variable in inventory:
        name = variable.get("output_column")
        if name not in config.variables:
            continue
        _require(name not in graph_variables, "Duplicate graph variable definition")
        _require(variable == local_variables.get(name), "Graph variable definition differs from pinned bundle")
        graph_variables[name] = variable
    for name in config.variables:
        local = local_variables[name]
        _require(local["output_table"] == "samples" and local["measurement_kind"] == "process_value" and
                 local["unit_status"] == "reported_only", "Selected variable lacks agreed process/units metadata")
    available = tuple(name for name in config.variables if name in graph_variables)
    target_references = _references(driver, dataset_id, target["batch_ref"], available, bundle, database)
    peer_references = {}
    if group in KNOWN_GROUPS:
        for peer in cohort:
            peer_references[peer["batch_id"]] = _references(driver, dataset_id, peer["batch_ref"], available, bundle, database)
    selected_ids = [batch_id] + [p["batch_id"] for p in cohort]
    # This is the sole numerical feature projection. Raw flags, harvest values
    # and compatibility metadata never enter measurement records or scoring.
    numerical = bundle["tables"]["samples"].select([
        "batch_id", "sample_id", "time_tick", "time_h", "source_file_id", "source_row_number", *config.variables])
    numerical = numerical.filter(pc.is_in(numerical["batch_id"], value_set=pa.array(selected_ids)))
    rows_by_batch = defaultdict(list)
    for row in numerical.to_pylist():
        rows_by_batch[row["batch_id"]].append(row)
    for rows in rows_by_batch.values():
        rows.sort(key=lambda row: row["time_tick"])

    def measurements(identity, variable):
        return [{**{key: row[key] for key in IDENTITY_FIELDS}, "value": row[variable]}
                for row in rows_by_batch[identity]]

    result = {"schema_version": 1, "record_kind": "derived_investigation",
              "detector": {"id": DETECTOR_ID, "version": DETECTOR_VERSION,
                  "method": "same elapsed-tick peer median and scaled median absolute deviation",
                  "score_description": "abs(target - peer median) / (1.4826 * peer MAD); interval score is mean point score",
                  "measurement_evidence_kind": "published_simulation_measurement"},
              "dataset": {"dataset_id": dataset_id, "graph_model_version": graph.MODEL_VERSION,
                  "manifest_sha256": bundle["manifest_sha256"], "cache_key": bundle["manifest"]["cache_key"],
                  "processed_artifacts": _artifact_records(bundle)},
              "batch": dict(target), "configuration": _configuration(config),
              "reference_cohort": {"compatibility_group": group, "members": cohort, "exclusions": exclusions,
                  "target_exclusion": {"batch_id": batch_id, "reason": "target_excluded",
                      "explicitly_requested": config.peer_batch_ids is not None and batch_id in config.peer_batch_ids},
                  "compatibility_metadata_provenance": {
                      "artifact_id": next(a["artifact_id"] for a in _artifact_records(bundle) if a["filename"] == "batches.parquet"),
                      "filename": "batches.parquet", "sha256": bundle["manifest"]["outputs"]["batches.parquet"]["sha256"],
                      "field": "control_regime", "role": "cohort_selection_only",
                      "basis": "existing ingestion metadata from published batch ranges; no annotation filtering"}},
              "variable_results": [], "findings": [], "limitations": list(LIMITATIONS)}
    for name in config.variables:
        reference = target_references.get(name)
        target_rows = measurements(batch_id, name)
        peer_refs = {identity: refs[name] for identity, refs in peer_references.items() if name in refs}
        variable_result = {"variable": name, "output_column": name, "variable_id": local_variables[name]["variable_id"],
            "reference": reference, "status": "skipped", "skipped_reason": None,
            "target_point_count": len(target_rows), "scored_point_count": 0, "exceeding_point_count": 0,
            "retained_interval_count": 0, "skipped_tick_counts": {}, "skipped_ticks": [],
            "peer_references": peer_refs,
            "peer_exclusions": [{**p, "reason": "peer_variable_unavailable"} for p in cohort if p["batch_id"] not in peer_refs]}
        reason = None
        if group not in KNOWN_GROUPS:
            reason = "undocumented_process_compatibility"
        elif name not in graph_variables:
            reason = "selected_variable_unavailable"
        elif reference is None:
            reason = "target_variable_unavailable"
        if reason:
            variable_result.update(skipped_reason=reason, skipped_tick_counts={reason: len(target_rows)},
                skipped_ticks=[{"time_tick": row["time_tick"], "status": reason} for row in target_rows])
        else:
            scored = score_variable(target_rows, {identity: measurements(identity, name) for identity in peer_refs}, config)
            points = scored["points"]
            skipped_points = [p for p in points if p["deviation_score"] is None]
            variable_result.update(status="analyzed" if scored["scored_point_count"] else "skipped",
                skipped_reason=None if scored["scored_point_count"] else "no_scoreable_ticks",
                scored_point_count=scored["scored_point_count"], exceeding_point_count=scored["exceeding_point_count"],
                retained_interval_count=len(scored["intervals"]), skipped_tick_counts=scored["skipped_tick_counts"],
                skipped_ticks=[{"time_tick": p["time_tick"], "status": p["status"]} for p in skipped_points],
                finite_peer_count_min=min((p["peer_count"] for p in points), default=0),
                finite_peer_count_max=max((p["peer_count"] for p in points), default=0))
            for interval in scored["intervals"]:
                identity = {"detector_id": DETECTOR_ID, "detector_version": DETECTOR_VERSION,
                    "manifest_sha256": bundle["manifest_sha256"], "batch_id": batch_id, "variable": name,
                    "configuration": result["configuration"], "start_tick": interval["start_tick"],
                    "end_tick": interval["end_tick"], "direction": interval["direction"]}
                digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
                result["findings"].append({**interval, "variable": name, "variable_id": local_variables[name]["variable_id"],
                    "batch_id": batch_id, "finding_id": "investigation:" + digest,
                    "record_kind": "derived_statistical_deviation", "reference": reference,
                    "score": interval["statistical_deviation_score"]})
        result["variable_results"].append(variable_result)
    order = {name: index for index, name in enumerate(config.variables)}
    result["findings"].sort(key=lambda finding: (-finding["statistical_deviation_score"],
        -finding["peak_deviation_score"], order[finding["variable"]], finding["start_tick"]))
    for rank, finding in enumerate(result["findings"], 1):
        finding["rank"] = rank
    _recheck_bundle(bundle)
    _check_graph_pins(driver, bundle, database)
    return result
