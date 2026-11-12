# Three-minute PharmaGraph walkthrough

Start the matching Neo4j graph and Streamlit app using the exact [README setup/launch commands](../README.md#5-load-the-graph-and-launch-the-demo), then open **http://127.0.0.1:8501**. The UI uses published simulation measurements and separately identified derived analysis. It does not diagnose faults or decide product quality.

## 0:00–1:45 — Batch 031: finding → trend → measurement → original source

1. Select **Batch 031** and click **Run investigation**. Select the **temperature / above** finding: **86–87 h**, ticks **430–435**, **6 observations**, mean statistical deviation score **11.8036**.
2. Inspect the finding trend. The published observed series is shown against the derived peer median and median ± threshold × scaled MAD, with the retained interval highlighted. This envelope is a statistical reference, **not an operating specification or confidence interval**. The four full-batch trends above provide context.
3. Read the first evidence measurement: sample `indpensim:pdnjz7zz5x:v2:batch:031:tick:000430`, **86.0 h**, **298.38 K**, peer median **297.99 K**, raw MAD about **0.02 K**, scaled spread **0.029652 K**, point score **13.1526**, **29 finite peers**.
4. Follow the actual graph relationship table: Batch → samples artifact (`HAS_DATA`); Variable → the same artifact (`HAS_DATA`); Variable → SourceFile (`FROM_SOURCE`); artifact → SourceFile (`DERIVED_FROM`). The measurement resolves to member `Mendeley_data/100_Batches_IndPenSim_V3.csv`, data row **34755** excluding the header, zero-based column **17**, exact header `Temperature(T:K)`. The reference pins the artifact/source checksums; the CSV is not reparsed in the UI.
5. Expand **Method, reference cohort and limitations**. Check target exclusion, 29 eligible peers, at least 10 finite peers per tick, strict score >6 and five consecutive same-direction observations. Five observations span 0.8 h between endpoints. Download the structured JSON if demonstrating manually.

**Demonstrates:** a retained statistical deviation can be inspected and traced to published measurement coordinates, without turning it into a causal or quality claim.

## 1:45–2:20 — Batch 001: assessed, no retained intervals

Switch to **Batch 001**. The previous result/download disappears, trends update, and analysis does not run automatically. Click **Run investigation**. The result says **assessed with no retained statistical deviation intervals**. Isolated exceedances did not satisfy persistence; this does not prove normal or safe operation.

**Demonstrates:** a negative retained-interval result is distinct from a process acceptance decision.

## 2:20–3:00 — Batch 091: explicitly not assessed

Switch to **Batch 091** and run. The result says **not assessed: process compatibility is undocumented**, with zero assessed variables and explicit skipped reasons. It does not assign a guessed reference cohort or show an assessed no-findings state.

**Demonstrates:** the system stops where supporting compatibility evidence is absent. The 091–100 group is unsupported because its operating regime is undocumented, not because the detector reads its published annotations.

## Verified behavior and manual limits

Real Neo4j/Parquet plus Streamlit **AppTest** checks verified all three framework-rendered states, the evidence row/column/value, actual provenance edges and no full-engine rerun on finding/rerender/download interactions. Bytes bound to the download button matched a fresh engine CLI result exactly (batch031 SHA-256 `441ba54225bc4b04beadb4d9b50b7a2ea9d2661ea461f4850b38b7dff6020264`). Actual connection refusal, missing data and incompatible artifact generation produced actionable messages. HTTP health/frontend checks passed.

**AppTest is not browser verification.** Chrome computer-use access was denied, so browser visual layout, Plotly hover/zoom and a browser-triggered file save remain unverified. **No screenshots were captured or fabricated.** Confirm those actions manually when browser access is available. Docker Compose startup/healthcheck/volume behavior and container restart also remain outstanding; standalone restart persistence does not prove container persistence.

See [final portfolio checks](portfolio_validation.md), [detailed engine validation](investigation_validation.md), [historical demo acceptance](evidence/demo/acceptance.json), [test output](evidence/demo/test_results.txt), and sanitized AppTest text captures for [031](evidence/demo/ui_batch031.txt), [001](evidence/demo/ui_batch001.txt), [091](evidence/demo/ui_batch091.txt). Text captures are not screenshots. The result files and detailed setup history remain available without expanding this walkthrough beyond the three-minute script.
