# Milestone 5 local demo interface and ownership

Lead-defined before delegation. Reuse the existing ingestion, graph and investigation modules without edits or changed defaults. This scopes milestone 5; prior scope restrictions are historical.

## Ownership and dependencies

- Agent 1: `app.py` and `scripts/demo.py` only: Streamlit UI and small presentation/cache/data helpers.
- Agent 2: `tests/test_demo.py` and `tests/test_demo_integration.py` only: independent helper, Streamlit AppTest and actual-Neo4j smoke checks. Coordinate helper interfaces before tests depend on them.
- Lead: this contract, requirements.txt, `.streamlit/config.toml`, README, docs/demo_walkthrough.md, evidence/screenshots under docs/evidence/demo, integration and actual launch/browser execution.
- Two agents only, no extra agents. No changes to ingestion, graph, investigation, config schemas, engine results or defaults. No Docker fixes, LLM/chat/auth/deployment/generic graph explorer.
- Dependencies: existing PyArrow21.0.0/neo4j5.28.2 plus Streamlit1.66.1 and Plotly7.1.0. Lead installs. Pandas arrives through Streamlit; no numerical algorithm dependency is needed.

## Required complete flow

Graph batch selector -> four published simulation trends -> explicit Run investigation -> ranked results -> finding selector -> detailed observed/peer/envelope chart, evidence/provenance -> JSON download. Default batch031 is convenient; graph.list_batches populates the 100 choices with labels Batch001 etc. Stable widget keys batch_selector, run_investigation, finding_selector, download_investigation (labels may contain spaces; preferred batch label `Batch 031`). No engine call until explicit Run button. Do not expose annotation queries/fields.

State messages must distinguish findings, assessed/no retained intervals, undocumented compatibility/not assessed, and insufficient coverage/zero-MAD/unscoreable ticks. A no-interval message explicitly says it is not proof of normal or safe operation. Partial coverage is visible even with findings. No-found and unassessed cannot share a success/normal state. Runtime failures present concise actionable messages for Neo4j/credentials, missing/corrupt artifacts, or incompatible graph/artifact versions; no raw stack trace, password, credential URI or exception logging in the UI.

Use visually clear published-simulation versus derived-analysis labels. Plotly trends use the four DEFAULT_VARIABLES only and verified unit_reported strings from current graph references. Show observed elapsed hours and source-reported units without conversion. Results columns: variable, direction, start/end elapsed hours (ticks available), observation count, mean statistical deviation score. Finding chart: observed line, peer median, median +/- threshold*reference_spread envelope and highlighted interval. Explicit caption: this is a statistical reference, not an operating specification or confidence interval. Missing/unscoreable reference points are gaps, never fill or extrapolate. Reuse investigation.score_variable for reference computation; do not duplicate scoring math.

An evidence table includes sample_id, batch_id, time_tick, time_h, observed_value, reference_median, reference_mad, reference_spread, deviation_score, peer_count, source_file_id, source_row_number, source_column_index, source_header. Use all interval target evidence; peer support can be an optional expanded view. Show a compact actual graph provenance path/table connecting Batch, Variable, ProcessedArtifact and SourceFile with directed relationship names. Query the real graph path with parameters; do not manufacture edges from JSON alone. No generic graph explorer.

A method expander includes eligible cohort size/membership, target exclusion, min10 finite peers per tick, threshold6 strict >, persistence5 same-direction consecutive observations (0.8h endpoint span), MAD1.4826, ranking by mean point score and all engine limitations. No threshold/config editing is needed. JSON download bytes are the engine result serialized as sorted-key UTF8/indent2/ensure_ascii=False/allow_nan=False/newline, matching existing CLI output. Do not inject UI state, paths, timestamps or presentation fields into the engine result.

## Helpers and caching

Agent1 owns helper design in scripts/demo.py but must announce exact public signatures to Agent2 before integration tests. Useful helpers include canonical download bytes, result state classification, evidence rows, chart construction, graph path verification and live/cache context identity. Keep pure presentation helpers separate from Streamlit rendering where practical so tests can assert data and figure traces.

Each rerun checks local manifest/output content identity and live graph compatibility/connection before displaying cached results or trends; a healthy cache cannot mask a missing file, changed artifact or unavailable/incompatible graph. Cache validated reusable Parquet/graph-reference data by manifest SHA + output hashes and path, dataset/model identity; resource-cache the official Neo4j driver by a private connection fingerprint (credential rotation invalidates without displaying secrets). Use cached/session investigation results keyed by dataset/model/manifest/artifact identity, target batch, detector ID/version and effective canonical config plus connection identity as needed. No raw credential strings in data cache keys, output, logs, exception messages or downloadable JSON.

Store current result in session state so unrelated widget interactions never invoke investigate_batch. An explicit repeated Run may reuse a version-keyed result cache. Changing batch or dataset/graph/artifact/config identity clears/hides an obsolete result. Selecting a finding may compute/cache its variable's plotting context using existing score_variable over approved numerical columns and peer references; this must not rerun full investigation. No archive access.

For trends/context reuse graph.validate_processed once per content-key generation, graph.list_batches/list_variables/batch_variables, and investigation._check_graph_pins/_local_reference comparisons where needed. A lightweight live graph pin/availability check each rerun is allowed; never call published_annotations or full graph integrity (annotation-independent). Use PHARMAGRAPH_PROCESSED_DIR as optional environment override for failure tests/local alternative root, otherwise graph.DEFAULT_OUTPUT. Existing NEO4J_* settings stay server-only; no credential fields in UI.

## Verification and delivery

Use real Neo4j/processed data with PHARMAGRAPH_NEO4J_INTEGRATION=1 for actual data AppTest/engine checks; otherwise clear prerequisite skip for live tests. Independent fixture-only tests may mock I/O for error state paths but cannot substitute for live acceptance. Verify batch031 one temperature interval430–435/86–87h, batch001 assessed with no retained intervals, batch091 undocumented not-assessed, evidence temp298.38/median297.99/sample tick430/source row34755/column17, download exact engine JSON. Assert full investigation is not automatically rerun on finding/batch UI rerenders; batch change clears prior result. Test correct envelope formula from existing returned stats and no annotation UI path.

Lead launches `.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false`, inspects the actual rendered flow using available browser/native browser tooling and captures screenshots when possible. Browser verification and AppTest are distinct evidence. Do not claim downloads/browser interactions tested if only their helper payload was verified; record limits precisely. Keep Docker/container restart verification outstanding.
