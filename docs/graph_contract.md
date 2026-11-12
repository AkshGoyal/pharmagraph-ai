# Milestone 3 graph implementation contract

This lead-owned contract follows inspection of the actual three Parquet schemas and manifest on 30 October 2026. It supersedes the sample-node projection in the milestone-2 graph proposal, without changing ingestion or its contract. Graph model version: `1`.

## Ownership and shared interface

- Lead owns this contract, `docs/graph_model.md`, `docs/graph_validation.md`, README, Docker Compose, `.env.example`, credentials/environment, dependencies, and actual execution/integration.
- Agent 1 owns `scripts/graph.py`, `scripts/load_graph.py`, and `scripts/query_graph.py` only: graph validation, loader, query functions and CLI. No ingestion, contract, dependency, Docker or test edits.
- Agent 2 owns `tests/test_graph.py` and `tests/test_graph_integration.py` only: independent focused/offline and real-instance tests. No edits to Agent 1's files.
- No further agents. Coordinate proposed contract changes with the lead first.

Use stdlib + existing PyArrow + Neo4j Python driver. Lead will add `neo4j==5.28.2`. Tests use unittest. No raw archive access, decompression, ingestion reruns, detector/model/UI/LLM/visualization work.

## Model and exact expected counts

Labels: **Dataset, SourceFile, ProcessedArtifact, Batch, Variable, FaultAnnotation**. No Sample nodes or per-cell nodes; all 113,935 time-series rows stay in Parquet. Require uniqueness constraints on each label's ID property below.

Every node has `dataset_id` so replacement can be restricted to one logical dataset. The Dataset's primary ID is also `dataset_id`. Other IDs:

- SourceFile: `source_file_id` from manifest members.
- ProcessedArtifact: `artifact_id = {dataset_id}:artifact:{filename}:sha256:{output_sha256}`. Filename is one of the three fixed Parquet outputs. Store relative `filename`, SHA-256, bytes, rows, output table, and `record_kind=derived_artifact`. Never store an absolute client path.
- Batch: existing `batch_id`. Store `batch_ref`, `source_file_id`, `source_row_number`, `sample_count`, `time_start_h`, `time_end_h`, `timeseries_first_source_row`, `timeseries_last_source_row`. Store `record_kind=published_simulation_record`; the count/time/source-row summaries are explicitly normalization-derived metadata. Do not copy `fault_present`, raw flag values, control campaign, or harvest values onto Batch.
- Variable: existing `variable_id`; store all variable metadata fields, `record_kind=published_variable_definition`.
- FaultAnnotation: `annotation_id={batch_id}:annotation:published_fault_present`. Store `fault_present` from the explicit statistics field, exact source header `Fault ref(0-NoFault 1-Fault)`, source column index 4, statistics source file ID/data row, `annotation_kind=published_batch_fault_presence`, `record_kind=published_annotation`. Create all 100 binary annotations including false, not just the ten true ones. Do not derive time-window annotations or fault types from raw time-series flags.
- Dataset stores manifest dataset metadata, `manifest_sha256` (exact manifest bytes), `cache_key`, `graph_model_version=1`, `load_state` (`loading` or `complete`) and `record_kind=published_simulation_dataset`.
- SourceFile stores member metadata/path, original archive SHA-256/filename, `record_kind=published_source`. Source hash is copied from the processed manifest; loader does not reopen the archive.

Relationships (direction and counts for original data):

| Type | From → To | Count |
| --- | --- | ---: |
| HAS_SOURCE | Dataset → SourceFile | 2 |
| HAS_ARTIFACT | Dataset → ProcessedArtifact | 3 |
| HAS_BATCH | Dataset → Batch | 100 |
| HAS_VARIABLE | Dataset → Variable | 33 |
| FROM_SOURCE | Batch → statistics SourceFile; Variable → corresponding SourceFile; FaultAnnotation → statistics SourceFile | 233 (100+33+100) |
| HAS_DATA | Batch → batches and samples artifacts; Variable → its `output_table` artifact | 233 (200+33) |
| DERIVED_FROM | batches artifact → statistics; samples artifact → timeseries; variables artifact → both sources | 4 |
| HAS_ANNOTATION | Batch → FaultAnnotation | 100 |

Expected totals **239 nodes, 708 relationships**: Dataset1 + SourceFile2 + ProcessedArtifact3 + Batch100 + Variable33 + FaultAnnotation100. Graph schema constraints are not graph nodes. Relationships are structural provenance, not causal claims. No additional derived evidence nodes are required; future detector evidence must have its own explicit provenance and is outside this milestone.

## Processed bundle validation and lifecycle

`validate_processed(processed_dir, contract_path=DEFAULT_CONTRACT)` returns a bundle dict with keys `manifest`, `manifest_sha256`, `tables` (PyArrow tables keyed batches/samples/variables), `processed_dir`. Verify manifest structure/cache-key inputs, exact expected table names, file size/SHA, exact Arrow schema/nullability, row counts and dataset ID. Compare contract/schema/source metadata with pinned ingestion contract but do not require the current ingestion source code hash or installed writer version to equal the recorded historical writer; an intact bundle remains usable. Never open the raw ZIP. Validate stable batch/variable IDs, batch-set/source joins and safe output/source fields. Source metadata is provenance, not a new source download.

`load_graph(driver, processed_dir, database='neo4j', batch_size=100, replace=False, contract_path=DEFAULT_CONTRACT)` returns a JSON-compatible status with dataset ID, manifest SHA, expected counts, actual counts and status. Driver is an official Neo4j Driver object. Use parameterized Cypher, uniqueness constraints, `UNWIND $rows` batched writes, and MERGE on stable IDs/relationships. Fixed Cypher identifiers are permitted; never interpolate user data as Cypher text. All queries must consume results.

Pin one processed manifest/model version per logical Dataset. An existing dataset with different manifest SHA/cache key/model version must be rejected before changing graph data, unless `replace=True`. Explicit replace deletes **only** nodes with matching dataset_id, preserving other datasets. A new logical release has a distinct dataset ID, so it cannot overwrite the old release. Repeated same-manifest loads must not accumulate nodes or relationships. Partial loads remain `load_state=loading`; query helpers reject/hide incomplete datasets. Re-run same manifest to finish. Mark complete only after count and structural integrity checks. Protect the initial manifest guard with a write transaction/lock on the Dataset to prevent two incompatible loads passing the guard simultaneously. Document single-loader operation while replacing; no cross-process global import orchestration required.

`graph_counts(driver, dataset_id, database='neo4j')` returns `nodes` and `relationships` dicts by label/type plus `total_nodes`, `total_relationships`.

`check_graph_integrity(driver, dataset_id, database='neo4j')` returns a dict containing boolean `ok`, `duplicate_ids`, and `missing_relationships` (zero counts for a complete graph), plus any useful detailed checks. Check all required parent/source/artifact/annotation cardinalities and ID consistency. This must detect missing edges, not just total counts.

## Query functions and safe measurement resolution

All graph query functions parameterize dataset_id, batch_ref and variable names. Require Dataset.load_state=complete and the expected model version. Return explicit fields, never `properties(b)` or wildcard properties that could leak annotations.

- `list_batches(driver, dataset_id, database='neo4j')`: batch identity + observed sample count/time bounds only; no fault, campaign or harvest values.
- `list_variables(driver, dataset_id, database='neo4j', detector_only=True)`: variable definitions, default 30 samples-table variables; investigation inventory with false includes all33. No fault fields.
- `batch_variables(driver, dataset_id, batch_ref, database='neo4j', detector_only=True)`: variable metadata plus correct original source provenance, processed artifact identity/checksum and batch/time coordinates. Resolve through shared HAS_DATA artifact; source-column source ID must agree with artifact's table. Summary variables are available only with detector_only=False.
- `get_reference(driver, dataset_id, batch_ref, variable_name, database='neo4j', detector_only=True)`: exactly one dict from batch_variables, adding manifest SHA/cache key as needed. Required fields: `dataset_id`, `batch_id`, `batch_ref`, `variable_id`, `output_column`, `output_table`, `artifact_id`, `artifact_filename`, `artifact_sha256`, `manifest_sha256`, `cache_key`, `source_file_id`, `source_member_path`, `source_archive_sha256`, `source_column_index`, `source_header`, `unit_reported`, `unit_status`, `source_row_number` (statistics row, only for summary variables; null for time-series reference). Include the variable's remaining metadata and observed batch bounds as useful. Unknown/unallowed variable raises ValueError; no user-controlled file path/property interpolation.
- `resolve_reference(reference, processed_dir, start_tick=None, end_tick=None, limit=None, contract_path=DEFAULT_CONTRACT)`: revalidate local bundle and graph-pinned manifest/artifact IDs/hashes, compare metadata to the authoritative tables, filter actual Parquet by batch_id and variable output_column. Return `{'reference': reference, 'measurements': [...]}`. Time-series measurement records contain **only** sample_id, batch_id, time_h, time_tick, value, source_file_id, source_row_number. Summary record contains batch_id,value,source_file_id,source_row_number. Preserve null values. No raw fault/control/metadata flags, labels or control campaigns in detector-facing results. `limit=None` returns full batch; CLI default limit20. Tick endpoints inclusive. Check bounds/limit types and values; no silently truncated or coerced wrong batch. Resolve via provided processed root + validated fixed filename, not stored absolute paths. Return failure if artifact/bundle changed after graph loading.
- `published_annotations(driver, dataset_id, batch_ref=None, database='neo4j')`: explicit separate evaluation query returning only published binary annotation values and source coordinates. Do not join this path in detector APIs. No sample-level flag interpretation.

## CLI/env

`python scripts/load_graph.py [--processed-dir PATH] [--batch-size 100] [--replace]` loads the default dataset. `python scripts/query_graph.py {batches,variables,reference,measurements,annotations,counts,check}` accepts `--dataset-id`, `--batch-ref`, `--variable`, `--processed-dir`, `--start-tick`, `--end-tick`, `--limit`, `--include-summaries` where relevant. Agent may use conventional subparser placement; document exact --help syntax to lead. Default dataset ID pinned from contract. All output JSON, errors nonzero, no credentials in output.

Environment: NEO4J_URI (`bolt://127.0.0.1:7687` default), NEO4J_USER (`neo4j` default), NEO4J_PASSWORD (required), NEO4J_DATABASE (`neo4j` default). Minimal stdlib `.env` parser for repo-root `.env` (KEY=VALUE, optional matching quotes, comments/blank lines); never execute/source shell text. Environment overrides file values. Do not commit local credentials. A helper `driver_from_env()` can return a driver; use `with`/close in CLI and tests. Agent2 may import `scripts.graph` via namespace package or importlib; public functions above are frozen.

## Independent testing and acceptance

Offline tests validate bundle corruption rejection, safe references/no label leakage, schema agreement and changed manifests. Integration tests run against actual Neo4j only when `PHARMAGRAPH_NEO4J_INTEGRATION=1`, otherwise skip with explicit prerequisite text. Use a distinct fixture dataset ID, created by transforming processed contract/manifest metadata and recomputing valid hashes; never clear the real database. Test double load stable counts/IDs, constraints, structure, queries/reference trace, separate annotations, mismatch refusal/replacement scoped to fixture, detector purity, incomplete-load guard and reference tampering. Clean up only test dataset nodes in teardown. Use no mock as evidence of database behavior.

Lead will run actual original-data first/second loads, count/integrity queries, an actual graph-to-Parquet lookup and annotation query, focused/integration tests and persistence after restart if runtime permits. Report exact Docker/Neo4j blockers, distinguish real-process restart from container restart, and never report skipped checks as passed.
