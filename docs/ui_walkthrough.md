# Redesigned interface

The app opens on **Project overview**. Its three tabs explain what PharmaGraph does, the business problem and review use cases, and how the data pipeline and detector work. No database connection is attempted by the overview, recorded walkthrough or glossary.

## Start locally

```sh
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8510 --server.headless true --browser.gatherUsageStats false
```

Open http://127.0.0.1:8510. Port 8510 avoids another local application that was using 8501 during this UI work. The existing configuration and original launch commands continue to default to 8501.

## Explore

1. **Project overview → The product:** inspect the annotated six-observation temperature finding. The chart shows only the retained interval, with observed values, peer median and the statistical envelope explicitly explained.
2. **Business & use cases:** read the intended user, evidence-assembly problem, practical review scenario and proposed measures of business usefulness. No measured ROI, cost saving or detection accuracy is claimed.
3. **Technical architecture:** inspect the source → Parquet / Neo4j → Python → UI / JSON flow, comparison arithmetic, missing-data policy and two-store trade-off. The AI-model expander clarifies that the implemented detector is deterministic statistics.
4. **Recorded walkthrough:** select Batch 031, move the observation slider from 86 to 87 h, and inspect how both measurements and source-row coordinates change. Download the complete recorded JSON. Switch to 001 and 091 to understand the distinct no-interval and not-assessed outcomes.
5. **Data & glossary:** search terms such as peer, MAD, provenance or control regime. Review compatibility groups and source units.
6. **Investigate a batch:** use the matching local graph/data described in the README. Four process channels have plain-English descriptions, and the explicit Run investigation button sits beside the batch selector. Results explain assessment coverage, rankings, units and source indexing. If local services are unavailable, an actionable error and a route to the recorded example remain available.

## Verification for this change

` .venv/bin/python -m unittest discover -s tests -v ` ran **92 tests: 63 passed and 29 live integration tests skipped**, with no failures. The live integration tests require the actual Neo4j runtime and were not claimed as passed. New AppTest checks cover offline views without live-data access or detector invocation, navigation, recorded-case switching, slider-driven evidence and unchanged JSON bytes, glossary search and its empty state. Existing integrity, numerical-method and presentation checks also pass. The original workspace tests now select the workspace explicitly because the opening page is the overview.

Browser inspection verified the overview and its business and technical tabs, the recorded walkthrough, all three recorded outcomes, slider selection through 87 h and source row 34760, and the real database-unavailable recovery screen. A browser-triggered Batch 031 recorded JSON download was saved and compared byte-for-byte with the checked-in engine result. Its SHA-256 is `441ba54225bc4b04beadb4d9b50b7a2ea9d2661ea461f4850b38b7dff6020264`.

The overview was also inspected at a 390 × 844 phone viewport: the page and main content widths were both 390 pixels, with no horizontal page overflow. Navigation remains available through the sidebar toggle, the scope strip becomes two columns and the workflow becomes a vertical sequence.

This change does not establish a fresh live-database end-to-end result, live graph provenance result or live investigation download result. The original numerical engine, graph schema and ingestion contracts are unchanged. Historical browser-verification gaps in the older validation records still describe that earlier run; the new browser checks above apply specifically to the redesigned explanatory screens and recorded workflow.

**Subsequent launcher recovery:** the project-local Neo4j and Java runtimes were restored and the launcher was extended to start the database automatically. All 92 tests subsequently passed with live integration enabled and no skips, and a fresh Batch 031 investigation and graph provenance were verified in the browser. See [launcher recovery and its verification](launcher.md). The earlier verification scope above describes the initial UI change, before that recovery.
