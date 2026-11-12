# Ingestion milestone validation

Observed by the implementation lead on **30 October 2026 (Asia/Kolkata)**. These results come from commands run against the original downloaded archive, plus the lead's focused test execution and output checks. Agent completion messages were not used as acceptance evidence.

## Delivered scope and coordination

The lead defined [contract v1](data_contract.md) and [the exact schemas](../config/indpensim_contract.json) before delegation. Three agents worked in separate files: ingestion implementation; dictionary/graph design; independent tests. The lead owned the contract, dependency setup, integration, and acceptance runs. No agent changed the agreed contract. Code and tests were frozen before the final checks.

The result is local ingestion/caching, three Parquet tables, provenance/manifest metadata, a data dictionary, and a graph design. No application, graph database, anomaly scoring, or additional dataset was built.

Environment: **Python 3.11.17, PyArrow 21.0.0**, with the only runtime dependency pinned in `requirements.txt`.

## Actual commands and observed results

| Run | Command | Status | Elapsed | Observed behavior |
| --- | --- | --- | ---: | --- |
| First full original-data run | `.venv/bin/python scripts/ingest_indpensim.py` | `built`, exit 0 | 14.905 s | Output directory initially absent; cache-miss reason `manifest missing` |
| Cached second run | `.venv/bin/python scripts/ingest_indpensim.py` | `cached`, exit 0 | 0.268 s | All four artifact hashes, sizes and modification times unchanged |
| Forced rebuild | `.venv/bin/python scripts/ingest_indpensim.py --force` | `built`, exit 0 | 14.898 s | Reason `forced rebuild`; all four files replaced; every hash identical to first build |
| Lead's focused tests | `.venv/bin/python -m unittest discover -s tests -v` | **22 tests passed**, exit 0 | 0.413 s reported by test runner | Includes subcases for malformed data, cache corruption, and publication failures |

The full runs used the default local original ZIP and output directory `data/processed/indpensim/`. The source was checked against SHA-256 `bc434c6cf96444fee3c915d434ac84e2a9c6492be4daebcfa4aed9cdff181f00`. A cached run rehashes the source and validates the manifest, all output hashes, readable Parquet schemas and row counts; it does not merely check file existence.

Build/cache fingerprint:

```text
45f2c8f41cfe178202a53a56676d15abcaa24cf7ffba2af99ab7bc626b93cca7
```

All three runs produced the following exact bytes. This comparison includes `manifest.json`, which has no build timestamp or absolute output path.

| Output | Rows | Bytes | SHA-256, identical across first/cached/forced runs |
| --- | ---: | ---: | --- |
| `batches.parquet` | 100 | 6,930 | `aa760562a140e033f84ab699ad4f151e51eb4ee19bb4ce5aca908a2e94dac4da` |
| `samples.parquet` | 113,935 | 6,900,852 | `3479fb11c22462c396e957ed099287c2f19147649814751776d552cf5bab90d5` |
| `variables.parquet` | 33 | 4,752 | `860bad3baa9c0b5c07a85d23bcf90fb83fa6bcc684b61280b96ed2c1104a5781` |
| `manifest.json` | — | 11,266 | `5f5d6f0b4c552fcaeae9834bd8216c9d67e6dd407b398c1a9b2805cbca7d6e63` |

Machine-readable run statuses, elapsed times, hashes, modification times and stderr are retained in [ingestion_acceptance.json](evidence/indpensim/ingestion_acceptance.json). A copy of the actual generated manifest is [ingestion_manifest.json](evidence/indpensim/ingestion_manifest.json). Raw and processed data stay local and are excluded from Git; the schema, code, tests and compact evidence remain reviewable.

## Independent checks on full normalized outputs

The lead checked the actual output files after the forced rebuild, independently of the ingestion module's validation helpers:

- Exact Arrow field order, types, nullability and row counts for all three tables; all non-nullable columns have zero nulls.
- Every one of the 113,935 sample IDs, batch IDs, time ticks, elapsed times, source-file IDs and source-row numbers; IDs are unique and rows follow the documented 12-minute grid.
- All 100 batch statistics records and their three raw harvest values against the original inspection; counts, start/end times, first/last source rows, control regimes and binary labels match.
- First and last samples of every batch: **6,000 process values** compared with the earlier original-archive inspection, preserving numeric scales and offline missing values.
- Each of the five sparse offline columns has **111,873 nulls**; other selected process fields have none. No unit conversion or imputation occurred.
- All raw fault-reference windows match the original inspection, totaling **1,256 samples** with raw value 1. Exactly **10 batches** have the authoritative statistics fault label true.
- All 33 variable metadata records match the agreed source positions, original headers, reported units and unit-status categories. No fault-type or equipment-ID column was introduced.
- The proposed graph query's Parquet bindings select batch 91's first raw flag-1 tick at **20.0 h**, and **11 samples from 19.0 to 21.0 h**, source rows 102,505–102,515. Five selected variables would yield 55 rows in the proposed projection. This checks field/time bindings only; the Cypher query was not run against a graph database.

These checks do not claim a complete independent cell-by-cell comparison of every process value or any validation of the excluded Raman tail.

## Independent test coverage

The focused [test suite](../tests/test_ingest_indpensim.py) uses small, distinctly named synthetic fixtures with complete pinned fixture contracts, retaining the source's 2,239-header/2,237-value structural defect. Fixtures are never presented as original IndPenSim observations. The production CLI rejects them because it retains the real dataset's pinned contract.

The lead's 22-test execution covered:

- Original-source hash/size/member/header/row-width checks, rejection on cached and forced paths, and preservation of existing outputs on integrity failure.
- Exact schemas and values, sparse nulls, raw metadata, row/column provenance, stable IDs when source batch-record order changes, and preserved signs/unit scales.
- Same-byte independent builds and forced rebuilds; cached reuse without output writes.
- Missing and corrupt Parquet files/manifests, same-size byte corruption, changed contracts and manifest metadata, unreadable Parquet even with an updated hash, and wrong Parquet schema even with an updated hash.
- Failed staging writes leave existing artifacts intact and clean up only their own staging/lock files.
- File publication uses `os.replace`, with manifest last; an existing writer lock is respected without deleting another invocation's lock.
- An injected interruption immediately before manifest publication leaves mixed files with an old manifest; the next run detects the invalid cache, rebuilds, and then reuses it successfully.

## Unresolved limitations and defects

**No blocking implementation defect was observed in the exercised paths.** The following remain explicit limits:

1. **Source semantics:** unresolved PAA/NH3/O2 units, harvest scales/aggregation, Raman mapping, missing named fault-type ground truth and assay result-availability times remain as documented in [dataset verification](data_verification.md). Ingestion preserves these uncertainties; it does not resolve them.
2. **Publication guarantee:** atomic replacement applies per file. Manifest-last publication detects an incomplete generation; it is not a transactional directory swap. Readers must validate the manifest before accepting outputs. A killed process can leave a writer lock that requires checking for an active writer before manual removal.
3. **Environment warning:** PyArrow printed `sysctlbyname failed` / `Operation not permitted` for sandbox-restricted CPU-capability queries (`hw.l1dcachesize`, `hw.l2cachesize`, `hw.l3cachesize`, `hw.optional.neon`). All required commands exited 0 and output checks passed. The warning is retained in the evidence; its performance impact was not measured.
4. **Reproducibility boundary:** identical artifact hashes were observed with the same pinned code, contract and environment. Different Python/PyArrow versions invalidate the cache, and identical Parquet bytes across other architectures or dependency versions have not been established.
5. **Graph status at this ingestion milestone:** the graph was then a proposal; no loader or database had been tested. Milestone 3 subsequently implemented and exercised the simplified model. See [graph_validation.md](graph_validation.md) for current graph evidence and the Docker verification blocker.
