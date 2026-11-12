# Milestone 4 deterministic investigation validation

The lead defined [investigation_contract.md](investigation_contract.md) before assigning two agents: Agent 1 owns the engine/CLI, Agent 2 independent tests; the lead owns integration, documentation and real-data execution. This milestone uses the existing graph and processed Parquet interfaces without changing ingestion, graph schema or dependencies.

## Selected variables

The detector uses four documented continuous simulation process channels from [data_dictionary.md](data_dictionary.md): `aeration_rate` (L/h, raw column 1), `sugar_feed_rate` (L/h, column 3), `ph` (literal source unit pH, column 16), and `temperature` (K, column 17). These represent two process flows and two process states, share verified positive integer elapsed-time ticks of 0.2 h, have `measurement_kind=process_value`, and do not have the dictionary's known sparse-assay or unresolved-unit categories. Units remain source-reported, not independently calibrated. Selection was fixed before inspecting detector findings and did not use fault annotations.

The selection avoids constant agitator/ammonia-shot channels, sparse offline measurements, unresolved PAA/NH3/O2 scales, harvest outcomes and Raman data. The chosen aeration and sugar-feed channels can themselves be constant across compatible peers; those cases are handled explicitly rather than silently discarded. Configuration can restrict the four-channel allowlist.

## Method and fixed defaults

For each variable and each observed target tick, use only available finite peer values at exactly that elapsed-time tick. Calculate the median `m`, raw median absolute deviation `MAD = median(abs(peer_value - m))`, reference spread `s = 1.4826 * MAD`, and point score `abs(target_value - m)/s` when `s > 0`. The [NIST definition of MAD](https://www.itl.nist.gov/div898/software/dataplot/refman2/auxillar/mad.htm) describes the robust spread measure; the detector fixes the conventional approximate scaling factor at 1.4826. This is a statistical deviation score, not a probability, confidence level, clinical severity, operating limit or quality specification.

Defaults were fixed before real findings were inspected:

| Setting | Default |
| --- | --- |
| Detector | `elapsed_tick_peer_median_mad`, version `1.0.0` |
| Variables | aeration_rate, sugar_feed_rate, ph, temperature |
| Reference policy | Same documented control regime; target excluded |
| Minimum finite peers per variable/tick | 10 |
| Exceedance rule | Point score strictly greater than 6.0 |
| Minimum consecutive exceedances | 5 observations, consecutive integer ticks, same direction |
| Interval ranking | Descending mean point score, descending peak score, configured variable order, start tick |
| Interpolation / imputation / extrapolation | None |

Five observations on the 0.2 h grid span **0.8 h between their endpoints**. A direction change breaks a run. Intervals retain every supporting target point, peer support, observed/reference values, scores and original source coordinates. Their mean point score is named `statistical_deviation_score`; the peak is reported separately. Scores across variables are descriptive ratios to each channel's own peer spread, not calibrated comparative severity.

## Reference membership and compatibility

Existing Parquet `control_regime` metadata encodes the publisher's documented groups: recipe-driven batches 1–30, operator-controlled 31–60, and APC/Raman 61–90. The engine uses these groups only for compatibility, not as numerical features. Membership additionally requires graph-resolved availability and overlapping observed elapsed-time data. The target is excluded even when explicitly requested as a peer. `--peer-batch-id` may restrict the compatible cohort but cannot broaden it. Final members/exclusions and per-tick finite support are recorded.

Batches 91–100 are `not_documented`; an identical unknown label is not evidence of compatible operation. Their results explicitly skip variables with `undocumented_process_compatibility`, without guessing peers. This rule follows process documentation, not published fault labels. Known regime groups are a coarse compatibility proxy: unrecorded batch differences and different elapsed-time phase timing may remain.

## Missing data and unscoreable ticks

- Missing/nonfinite target values break intervals and are reported.
- Missing/nonfinite peer values are omitted only at that tick; finite peer coverage is counted explicitly.
- No peer rows at a target tick is `unmatched_tick`; rows with fewer than the configured finite-peer minimum are `insufficient_peers`.
- Zero MAD with target exactly equal to the median gives score 0 (`zero_mad_equal`). Zero MAD with a different target is `zero_mad_unscorable`, with null score and no exceedance. No epsilon, arbitrary spread floor, infinity or division by zero is introduced.
- Missing ticks, nonexceedances, unscoreable points and direction changes break runs. No smoothing, fill, resampling, phase alignment or endpoint extension is performed.

Unexpected nonfinite production values already fail the existing processed-bundle validator. The pure detector additionally exercises missing/nonfinite handling on clearly identified synthetic inputs. Duplicate sample ticks and invalid coordinates/configuration fail rather than silently coerce.

## Provenance and separation of findings from measurements

The engine resolves graph-available batches, variables and source/artifact references using the existing detector-facing graph interfaces. It verifies complete/model state and compares each used reference with the authoritative metadata in one validated processed bundle. Analysis projects only approved process values and identity/time/source coordinates. Compatibility reads only batch identity/ref/regime metadata; no fault annotation query or global graph integrity query is part of the detector input path.

The existing graph validator verifies full-bundle integrity, including the historical ingestion metadata. This validation does not make label columns features: neither numerical scoring nor cohort selection consumes published labels, raw flags or harvest values. Mismatched manifest/artifact/model metadata causes a clear failure; there is no fallback from incompatible graph references to unpinned local data. Output hashes/manifest are checked again before returning.

Results are schema-versioned JSON with dataset/artifact identity, effective configuration, cohort membership, per-variable coverage/skips, ranked findings, full evidence coordinates, detector version and explicit limitations. Published simulation measurement evidence remains distinct from derived reference medians/spreads and findings (`derived_statistical_deviation`). No investigation nodes or relationships are written to Neo4j. No timestamp, random ID, absolute machine path or execution timing enters the deterministic result.

## Commands actually executed and real results

The local standalone Neo4j Community 5.26.32 instance from milestone 3 was already running; no Docker work or graph rebuild was needed. Dependencies remain Python 3.11.17, PyArrow 21.0.0 and Neo4j driver 5.28.2. The lead ran these commands against the original processed dataset:

```sh
.venv/bin/python scripts/investigate_batch.py --batch-id indpensim:pdnjz7zz5x:v2:batch:001 --output docs/evidence/investigation/batch001.json
.venv/bin/python scripts/investigate_batch.py --batch-id indpensim:pdnjz7zz5x:v2:batch:031 --output docs/evidence/investigation/batch031.json
.venv/bin/python scripts/investigate_batch.py --batch-id indpensim:pdnjz7zz5x:v2:batch:061 --output docs/evidence/investigation/batch061.json
.venv/bin/python scripts/investigate_batch.py --batch-id indpensim:pdnjz7zz5x:v2:batch:091 --output docs/evidence/investigation/batch091.json
.venv/bin/python scripts/investigate_batch.py --batch-id indpensim:pdnjz7zz5x:v2:batch:031 --output /private/tmp/pharmagraph_investigation_batch031_repeat.json
PHARMAGRAPH_NEO4J_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
```

Every command exited 0. CLI elapsed times including startup, bundle validation and graph queries were 1.208 s, 1.264 s, 1.262 s and 0.890 s for the four first runs, respectively. Timings are retained only in acceptance evidence, not detector results.

| Batch | Documented group and fixed eligible cohort | Actual outcome with default configuration |
| --- | --- | --- |
| 001 | Recipe-driven; batches 002–030, 29 peers | **No retained intervals** across all four variables. There were 1 isolated pH and 14 temperature point exceedances, none forming a qualifying run. This is not a normal/healthy classification. |
| 031 | Operator-controlled; batches 032–060, 29 peers | **One temperature interval above peers**, ticks 430–435, **86.0–87.0 h**, 6 points. Mean statistical deviation score **11.80358829085064**, peak **19.560232024836598**. No retained intervals for the other three channels. |
| 061 | APC/Raman; batches 062–090, 29 peers | **One pH interval below peers**, ticks 387–449, **77.4–89.8 h**, 63 points. Mean statistical deviation score **26.398741531099027**, peak **55.4402078604574**. No retained intervals for the other three channels. |
| 091 | Undocumented compatibility; no eligible cohort | **Not assessed**: all four variables skipped with `undocumented_process_compatibility`. Empty findings must not be read as absence of deviations. |

Coverage was variable/tick specific. Batch 001 had 1,130 scoreable observations per variable. Batch 031 had 1,150 scoreable observations of 1,250, with **100 insufficient-peer ticks per variable**. Batch 061 had 1,150 of 1,205, with **55 insufficient-peer ticks per variable**. These late ticks were not extended or filled. Equal zero-MAD comparisons count as scoreable zero-score observations; an independent calculation found these for all 1,130 aeration/sugar-feed ticks in batch 001 and all 1,150 covered aeration ticks in batch 031. No target was included in its reference cohort at any point.

The lead independently calculated per-tick peer medians, MAD, threshold exceedances and same-direction runs from an explicit process-only Parquet projection, separate from the engine. All real interval coordinates/counts/directions and scores matched (scores compared at relative tolerance 1e-12 because the engine uses overflow-resistant summation). Every retained target measurement and every finite supporting peer measurement was compared with actual Parquet identity, tick/time, value and source-row/file fields. The numerical calculation did not read fault, raw-flag, harvest or annotation fields.

Saved artifacts:

- [Batch 001: no retained intervals](evidence/investigation/batch001.json)
- [Batch 031: temperature deviation](evidence/investigation/batch031.json)
- [Batch 061: pH deviation](evidence/investigation/batch061.json)
- [Batch 091: compatibility skip](evidence/investigation/batch091.json)
- [Lead's independent numerical check](evidence/investigation/independent_reference_check.json)
- [Commands, hashes, comparisons and source trace](evidence/investigation/acceptance.json)

## One graph-to-artifact-to-source evidence trace

The first reported point in batch 031's temperature interval is:

| Field | Observed result |
| --- | --- |
| Stable sample ID | `indpensim:pdnjz7zz5x:v2:batch:031:tick:000430` |
| Elapsed coordinate | tick 430 / 86.0 h |
| Observed temperature | **298.38 K** as published |
| Finite peers | **29**, excluding batch 031 |
| Peer median | **297.99 K** |
| Raw MAD | **0.01999999999998181 K** |
| Scaled reference spread | **0.02965199999997303 K** |
| Point statistical deviation score | **13.152569809805108** |
| Original source-file ID | `indpensim:pdnjz7zz5x:v2:timeseries` |
| Member path | `Mendeley_data/100_Batches_IndPenSim_V3.csv` |
| One-based data-record number, excluding header | **34755** |
| Zero-based source column | **17**, exact header `Temperature(T:K)` |

The lead independently called the existing `graph.get_reference` for batch 31/temperature and required it to equal the finding's saved reference. Existing `graph.resolve_reference` for tick 430 returned the same sample, value and source row from actual Parquet. The reference binds `samples.parquet` to SHA-256 `3479fb11c22462c396e957ed099287c2f19147649814751776d552cf5bab90d5`, under manifest SHA-256 `5f5d6f0b4c552fcaeae9834bd8216c9d67e6dd407b398c1a9b2805cbca7d6e63` and graph model version 1. Its archive pin is `bc434c6cf96444fee3c915d434ac84e2a9c6492be4daebcfa4aed9cdff181f00`.

The 29 original peer values and their source coordinates reproduce the displayed median/MAD and score. This traces a finding through the real graph/artifact reference to an original source location; it does not claim a new raw-archive parse or independent physical temperature calibration. The ZIP was not reopened.

## Determinism and result schema

The batch 031 CLI was run twice with identical graph/artifact inputs and defaults, writing different output files. The JSON bytes were identical, SHA-256 **`441ba54225bc4b04beadb4d9b50b7a2ea9d2661ea461f4850b38b7dff6020264`**. Pure tests also permute target, peer and measurement ordering and require identical results. Effective configuration normalizes peer restrictions deterministically; finding IDs derive from detector/version/manifest/configuration/batch/variable/interval identity.

The JSON schema is suitable for direct consumption by a later UI, with no UI built here:

| Path | Purpose |
| --- | --- |
| `schema_version`, `record_kind`, `detector` | Schema 1, derived-investigation type, method/version and published-simulation measurement evidence kind |
| `dataset` | Dataset ID, graph model version, exact manifest/cache key, three processed artifact identities/hashes |
| `batch` | Graph-resolved identity and observed sample/time bounds |
| `configuration` | Effective variables, peer restrictions, coverage/threshold/run length, MAD factor and missing/zero-MAD policies |
| `reference_cohort` | Compatibility basis/provenance, members, target exclusion and exclusion reasons |
| `variable_results[]` | Available target graph reference, status/reason, scoreable/exceeding counts, skipped ticks/reasons, finite coverage bounds, peer references/exclusions |
| `findings[]` | Deterministically ranked interval coordinates, direction, mean/peak scores, stable finding ID and graph reference |
| `findings[].evidence[]` | Original target identity/value/source coordinates plus clearly named derived reference statistics/scores and finite peer support |
| `findings[].evidence[].peer_measurements[]` | Original peer IDs, ticks/times, values, source file and data-row coordinates; source column/member/artifact metadata bound by the corresponding variable's peer graph reference |
| `limitations` | Explicit method, compatibility, provenance and interpretation boundaries |

The CLI emits a compact JSON status to stdout and writes the full result as sorted-key UTF-8 JSON with a final newline. Temporary-file/fsync/atomic replacement preserves a previous output if publication fails. Protected processed/source/contract/credential paths are rejected as output destinations. Errors are JSON, nonzero and credential-redacted. Use `--help` for exact options; repeated `--variable` and `--peer-batch-id` restrict approved variables and compatible membership, respectively.

## Test execution and annotation independence

The lead ran the full suite against the actual local Neo4j instance:

```sh
PHARMAGRAPH_NEO4J_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
```

**72 tests passed, zero skipped, exit 0, 5.217 s.** The [full test output](evidence/investigation/test_results.txt) and final implementation/test SHA-256 values are retained with acceptance evidence. Breakdown:

- **46 existing regression tests:** 22 ingestion, 15 offline graph and 9 real graph-integration tests.
- **12 new pure method tests:** clearly synthetic injected deviations with independently known median 0/MAD 1; even-peer median; strict threshold boundary; target exclusion; deterministic reordering; constant references; missing/nonfinite values; insufficient/unmatched ticks; duplicate/invalid coordinates; direction/gap grouping; and consecutive-observation duration.
- **13 new real-instance engine tests:** independent schema-complete synthetic fixture with 8 batches/64 samples; injected interval/value/source trace; compatible/restricted cohorts; target exclusion; unknown regime skips; insufficient coverage; graph/model/artifact/source failures; unavailable variables; deterministic ranking and source-file immutability; numerical-feature allowlist; and annotation independence. Lead-added regression cases verify dataset/artifact pins are checked even when all selected variable inventory edges are missing.
- **1 new CLI test:** invalid configuration cannot create or replace an output and returns a JSON error.

The annotation-independence test used a distinctly identified synthetic dataset in the real Neo4j instance. It first obtained a complete investigation result, then flipped the dataset's published graph annotation values and required the complete result bytes to remain identical. It then removed those annotation nodes and repeated the same check. No production annotations were modified. An explicit engine/scorer input assertion permitted only identity/time/value/source coordinates; no fault, control flag, raw metadata or harvest fields reached scoring. Control regime was used solely in the compatibility projection.

Tests isolate and clean up only their own fixture datasets. The original-data engine runs and all tests left the production graph at **239 nodes / 708 relationships**; investigation output remains JSON, without new graph nodes. Fingerprints confirm that existing ingestion code, graph scripts, source contract, processed manifest and dependencies are unchanged.

## Limitations and blockers

No implementation/runtime blocker remained in this milestone's exercised paths. Docker availability was not changed or investigated; the existing standalone instance supplied the required graph context. A later environment still needs the processed bundle, matching complete Neo4j dataset and credentials.

These checks establish deterministic implementation behavior, graph/artifact consistency and traceability, **not detection accuracy**. Threshold 6, minimum peers 10 and five consecutive observations are conservative configurable heuristics fixed before the reported findings; they were not calibrated against a fault label or quality outcome. Four batches do not estimate sensitivity, specificity, false-positive rate or detection delay.

Cohorts may contain unusual behavior because there is no annotation-based filtering. The documented control regimes are coarse and do not prove identical recipes/conditions. Matching elapsed time does not align biological phases. Small positive MAD, source quantization and tightly controlled channels can produce large scores for small absolute changes; zero-MAD differences are deliberately unscoreable rather than assigned arbitrary large values. Late batch times may have insufficient surviving peers. An empty finding list can reflect no qualifying runs, insufficient data, or undocumented compatibility; variable diagnostics distinguish them.

The four selected channels leave other process behavior unassessed. Source values describe simulations and retain reported units and uncertainty. No causal explanation, named fault, physical operating limit, product-quality failure, probability or clinical severity is inferred. No Streamlit, LLM integration, additional detector, causal analysis or graph visualization was built.
