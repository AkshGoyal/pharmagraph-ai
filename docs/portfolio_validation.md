# Portfolio MVP finalization

Finalized locally on **30 October 2026**. Feature scope is frozen. Work was limited to reviewer documentation, architecture explanation, evidence portability and ignore rules. No application feature, detector default, dependency or graph/ingestion contract was changed. No data was deleted, Git history rewritten, commit created, publication made or remote push performed.

## Files changed and issues corrected

| File | Correction |
| --- | --- |
| `README.md` | Reviewer problem/workflow; ordered exact install/download/ingest/credential/runtime/load/launch commands; complete tested standalone description alongside unverified Compose; attribution/terms; detector assumptions and honest verification boundaries |
| `docs/architecture.md` | Compact implemented diagram; actual graph role and SQL alternative; ontology-inspired vocabulary without formal/causal claims; limitations and exactly three future improvements |
| `docs/architecture_detailed.md` | Complete component/data-flow, graph and execution diagrams; actual raw/processed data shapes; component/function responsibilities; achieved outcomes and unsupported claims |
| `docs/demo_walkthrough.md` | Timed three-minute 031 finding→trend→measurement→source example, 001 assessed-empty case and 091 unassessed case; browser/download caveats retained |
| `.gitignore` | Runtime downloads, local tool/database/configuration directories, Streamlit secrets, archives, Parquet exports and private key material covered |
| `docs/evidence/README.md` | Bounded evidence inventory, fixture dependencies and historical machine-path context |
| `docs/evidence/indpensim/ingestion_acceptance.json` | Six occurrences of the original personal repository prefix normalized to `<repo>/`, with an explicit metadata note; measurements/hashes/counts/timings unchanged |
| This report and `docs/evidence/portfolio/` | Final check record and full test output |

The earlier README assumed a prepared workspace, linked standalone use to a historical temporary directory, duplicated setup sections and incorrectly described only nine flag-gated database tests after later milestones added more. Those assumptions were removed. A final URL check also found that plain Python urllib access to the download API returned HTTP403; the documented command now uses the tested curl request with the public API Accept header. It resolved the official object, whose HEAD returned HTTP200 and the expected 503,792,426-byte size. Source data, data licensing and code licensing are explicitly distinguished. Setup now places fresh runtime files under ignored `data/runtime`, while preserving historical evidence as historical rather than claiming a newly tested installation.

## Final executed checks

- **Full suite:** `PHARMAGRAPH_NEO4J_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v` → **89 passed, zero skipped, exit0, 18.453s** against real local Neo4j/processed data. [Full output](evidence/portfolio/test_results.txt).
- **Data cache:** `.venv/bin/python scripts/ingest_indpensim.py` → `cached`, exit0; no full archive parse/rebuild was requested.
- **Graph integrity:** `scripts/query_graph.py check` → `ok: true`, zero duplicate IDs, missing edges, unexpected relationships or invalid entities. Counts remain **239 nodes / 708 relationships**.
- **Live demo:** Streamlit `/_stcore/health` returned **HTTP200 / `ok`**. Prior real-data AppTest/source/download evidence remains separately recorded; no new browser verification is claimed.
- **Setup review:** documented Python snippets parsed; shell blocks passed `zsh -n`; CLI flags compared with actual `--help`, pinned runtime hashes compared with the downloaded distributions, and the official data-download API resolved without redownloading the dataset. These are documentation checks, not execution of a clean-host setup.
- **Freeze check:** source/tests/configuration and dependency fingerprints match the pre-finalization snapshot.
- **Hygiene:** current local password/private-key/token patterns and personal repository paths checked across versionable candidate files; ignored locations checked explicitly; `.env.example` retains a placeholder and remains eligible for version control. [Machine-readable results](evidence/portfolio/checks.json).

The Git index contains **no tracked files** at audit time. The hygiene scan therefore includes all unignored candidate files; files were not staged or committed. Raw archives, local Parquet, Neo4j stores/logs, JDK/runtime archives, credentials and generated investigation exports stay local. Small metadata and four result examples are retained intentionally because existing tests consume them. No rule was added that hides application source or the public example environment file.

## Outstanding manual checks

1. A new reviewer/clean host should execute the complete setup recipe, including the relocated standalone runtime paths; the original tested process used a temporary binary location. Other operating systems/architectures are not claimed as tested.
2. Browser visual layout, Plotly hover/zoom and a browser-triggered JSON file save remain unverified. Chrome computer-use access was denied, and no screenshots were fabricated. AppTest and payload equality do not replace this check.
3. Docker Compose startup, healthcheck execution, named-volume persistence and container restart remain outstanding. Standalone process persistence was verified earlier and is a different claim.

Detection accuracy, named fault diagnosis, causal effects, quality outcomes, regulated manufacturing use, deployment and multi-user security are outside this MVP's demonstrated scope.

## Factual 60-second interview explanation

> PharmaGraph explores how to make a batch investigation traceable. I used a published penicillin-fermentation simulation, verified its source bytes and normalized selected measurements into Parquet. Neo4j stores a small model of batches, variable definitions, processed artifacts and source provenance; the time series remain in Parquet for numerical analysis. A transparent detector compares four channels with compatible peer batches at the same elapsed-time tick, excludes the target and uses median/MAD with a persistence rule. A local Streamlit demo lets a reviewer inspect a finding and follow its supporting measurements back to source coordinates. For batch031 it shows a temperature deviation at86–87hours; the first point is298.38K, traceable to source row34755, column17. I also demonstrate an assessed empty result and an explicitly unsupported regime. These are statistical deviations, not root causes or quality decisions. The local data/graph/framework tests pass; browser and Docker persistence checks remain open.
