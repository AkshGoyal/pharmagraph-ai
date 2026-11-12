# IndPenSim ingestion contract v1

The machine-readable authority is [config/indpensim_contract.json](../config/indpensim_contract.json). It pins the verified original archive, exact CSV headers (including defects), row widths, batch references, selected variables, ordered Arrow schemas, and Parquet writer settings. Changes require lead approval before implementation. The earlier verification report remains the evidence baseline.

## Scope and ownership

- Lead: this contract, `config/indpensim_contract.json`, dependencies/environment, `.gitignore`, README, integration and actual-data verification report. Lead integrates fixes only after coordinating ownership.
- Agent 1: `scripts/ingest_indpensim.py` and any ingestion-only helper files agreed with the lead. No dependency/config/doc/test edits.
- Agent 2: `docs/data_dictionary.md` and `docs/graph_model.md` only. Graph design only; no database or application implementation.
- Agent 3: focused files under `tests/` only. Report implementation defects to the lead; do not edit ingestion code.

No extra agents. No application, anomaly detector, graph database, fault-type labels, quality outcomes, equipment records, source-unit corrections, or repaired Raman schema.

## Tables, stable IDs, and selected variables

Outputs: `batches.parquet` (100 rows), `samples.parquet` (113,935 rows), `variables.parquet` (33 rows), and `manifest.json`. Parquet field order, exact types and nullability are the `schemas` entries in the JSON contract. No pandas index column or implicit schema inference.

- Dataset ID: `indpensim:pdnjz7zz5x:v2`.
- Batch ID: `{dataset_id}:batch:{batch_ref:03d}`, e.g. `indpensim:pdnjz7zz5x:v2:batch:091`.
- Time tick: exact integer `Decimal(raw_time_h) / Decimal('0.2')`; nonintegral or nonpositive values fail. Preserve `time_h` as float64 for convenience. Require strictly increasing ticks within each batch, spaced by one, and unique `(batch_ref, time_tick)`.
- Sample ID: `{batch_id}:tick:{time_tick:06d}`. IDs do not depend on row order, output location, wall-clock time, or random UUIDs.
- Variable ID: `{dataset_id}:variable:{output_column}`. Variables reference their source member, zero-based raw position, exact header and reported unit.
- Source file IDs: `{dataset_id}:timeseries` and `{dataset_id}:statistics`. `source_row_number` is the one-based **data record number excluding the header**, globally within that CSV. Row number is provenance, not identity.

`samples` is wide: source positions 1–30 become the 30 explicitly named float64 fields in the contract. Preserve numeric values without rescaling, interpolation, smoothing, imputation, or derived quality decisions. Exactly the five sparse offline columns may map literal `NaN` to null; reject infinities and unexpected blanks/nonnumeric tokens. Keep negative values as published. Preserve positions 31–34 and 36 as raw metadata, separately from process variables. Position 35 is the publisher-documented batch key. Exclude positions 37 onward from normalized outputs; do not reinterpret `Batch ID` or `Fault flag` as labels.

`batches` joins statistics `Batch ref` to raw position 35. `fault_present` comes exclusively from the explicit statistics binary field, with 0/1 validated. Preserve all three harvest summaries under `_raw` names without unit correction. Add sample count, observed start/end time, and first/last time-series data row numbers. `control_regime` comes from the publisher's batch ranges: 1–30 `recipe_driven`, 31–60 `operator_controlled`, 61–90 `apc_raman`, 91–100 `not_documented` (fault-containing is not a control strategy).

`variables` contains 30 process variables plus the three raw harvest summaries. `unit_status=reported_only` means copied from a source label, not physically validated. `unresolved` marks PAA, NH3, O2 off-gas and the three harvest summaries. `measurement_kind` is `process_value`, `offline_sparse`, or `raw_summary`; it does not claim an online sensor or assay result-availability time.

Keep batches in ascending batch_ref, samples in `(batch_ref, time_tick)` order, and variables in contract order. Require source batch-set agreement, one statistics row per batch, raw metadata 34 equal to the documented batch reference, and raw metadata 36 agree with the statistics label. Binary fields at 31, 32 and 36 must be 0/1. Do not assign a fault type or assert that raw 31 is definitive physical onset/clearance truth.

## Provenance and manifest

The deterministic JSON manifest (sorted keys, UTF-8, final newline; no run timestamp or absolute machine path) contains:

- `manifest_version: 1`, `contract_version: 1`, the exact `dataset` object from the contract.
- `cache_key`: SHA-256 of canonical compact sorted JSON containing contract SHA-256, archive SHA-256, normalizer source SHA-256 and writer environment (`python_version`, `pyarrow_version`). Name these exact fields in a `cache_inputs` object and calculate the key from that object.
- `cache_inputs`: `contract_sha256`, `archive_sha256`, `normalizer_sha256`, `python_version`, `pyarrow_version`.
- `source`: `archive_filename`, `bytes`, `sha256`, and `members`; each member records `source_file_id`, `path`, `bytes`, `crc32`, `rows`, `header_fields`, `row_fields`. Archive SHA pins every raw value including excluded data. Validate expected ZIP members, sizes, CRCs, headers, row counts and row widths; do not accept alternate source bytes, even with `--force`.
- `outputs`: keys `batches.parquet`, `samples.parquet`, `variables.parquet`; each records `bytes`, `sha256`, `rows`, `schema` (the matching contract field list).
- `normalization`: the contract's normalization rules, plus explicit warning strings covering malformed header/excluded tail, misleading metadata, unresolved units/harvest quantities, binary-only fault evidence and missing assay availability timestamps. An array `warnings` at manifest top level is sufficient for these warning strings.
- `writer`: the contract writer settings.

Cache reuse requires the original archive hash, complete expected manifest structure and metadata, matching cache inputs, exactly the expected output entries, correct output bytes/hashes, readable Parquet, exact schema/nullability and expected row counts. Never trust existence alone or return a success for a partial/corrupt cache. Missing/malformed manifests, missing/corrupt outputs, metadata mismatch, or a changed normalizer/contract/environment trigger a rebuild from the verified source. Unknown/corrupt source fails, leaving existing outputs untouched. Recompute the source hash on each invocation, including cached runs.

`--force` bypasses reuse and rebuilds, while retaining source/integrity checks. With unchanged bytes, contract, normalizer and environment, output and manifest hashes must match across independent and forced builds. No nondeterministic Parquet metadata.

## CLI and atomic writes

```sh
python scripts/ingest_indpensim.py
python scripts/ingest_indpensim.py --force
```

Defaults: source `data/raw/indpensim/100_Batches_IndPenSim.zip`, output directory `data/processed/indpensim`. Options: `--archive PATH`, `--output-dir PATH`, `--force`. The CLI uses the pinned production contract; no unverified-source override or downloader. Programmatic `ingest(archive, output_dir, force=False, contract_path=...)` may accept a complete alternate contract for small isolated test fixtures; every supplied integrity check still applies. Tests must use distinct fixture dataset IDs.

Build outputs in a temporary sibling staging directory on the same filesystem. Finish parsing, schema validation and all writes before promoting any staged files. Close Parquet writers before hashing. Publish files with `os.replace`, and publish manifest **last**, so interrupted publication cannot be accepted as a valid cache. Failed builds clean up their staging directory and preserve existing outputs until publication begins. A crash between file replacements can invalidate the prior cache; the next run must detect and rebuild it. This is manifest-based completeness, not a transactional directory swap. Use a single-writer sibling lock; a concurrent invocation fails clearly. Remove only staging files/locks created by this invocation, never unrelated paths.

Print structured JSON status with `status: built` or `status: cached`, `cache_key`, `manifest_path` and an actionable cache-miss reason. Errors exit nonzero and explain the failed check. Keep run-specific status out of the deterministic manifest.

## Required acceptance evidence

The lead must run the production command, a cached second run, a forced rebuild, and the focused tests. Record elapsed times, rows, output sizes, hashes across rebuilds, cache behavior, and unresolved defects in `docs/ingestion_validation.md`. Independent tests cover row/source traceability, schema/null handling, stable identity, deterministic rebuilds, reuse without writes, missing/corrupt outputs/manifests, changed contract, source-integrity rejection, failure atomicity, and `--force`. Fixture tests do not substitute for the lead's full original-data runs.
