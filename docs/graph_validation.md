# Milestone 3 graph validation

Observed by the lead on **30 October 2026 (Asia/Kolkata)**. The implementation and independent tests were split between two agents under [graph_contract.md](graph_contract.md); the lead owned shared interfaces, setup, documentation, integration and execution. Agent completion reports were not used as database acceptance evidence.

**Implemented and verified against real local Neo4j:** repeated loads, exact counts, six uniqueness constraints, edge integrity, safe measurement resolution, separate annotations, dataset replacement/version guards, and persistence across a standalone Neo4j process restart. **Container restart and Docker health/volume behavior are unverified:** Docker is not installed in this environment.

## Actual schema check and final model

Before integration, the lead read the actual three Parquet schemas and compared every ordered field name, type and nullability with `config/indpensim_contract.json`. All matched:

| Processed table | Observed rows | Graph use |
| --- | ---: | --- |
| `batches.parquet` | 100 | Batch identity/provenance and derived count/time bounds; published binary label becomes a separate annotation |
| `samples.parquet` | 113,935 | Remains in Parquet; graph references resolve by artifact hash, batch ID and approved variable |
| `variables.parquet` | 33 | 30 process definitions plus 3 raw harvest-summary definitions |

The earlier graph proposal copied wide samples and label fields onto graph nodes. The implemented model removes `Sample`/per-cell nodes and keeps fault labels separate. See [graph_model.md](graph_model.md) for identities, property boundaries and parameterized Cypher examples. No ingestion implementation or source contract was changed. The ingestion implementation still hashes to `306f3e7b70fefd8645a9951c2a973943f73fb7e4756c96ed160c7f09a47790d6`.

The final labels are `Dataset`, `SourceFile`, `ProcessedArtifact`, `Batch`, `Variable`, and `FaultAnnotation`. The relationship types are `HAS_SOURCE`, `HAS_ARTIFACT`, `HAS_BATCH`, `HAS_VARIABLE`, `FROM_SOURCE`, `HAS_DATA`, `DERIVED_FROM`, and `HAS_ANNOTATION`.

## Runtime and setup

Execution environment: Python **3.11.17**, PyArrow **21.0.0**, Neo4j Python driver **5.28.2**, Neo4j Community server **5.26.32**, Amazon Corretto **21.0.13.0.11**, macOS arm64.

The project provides [compose.yaml](../compose.yaml), persistent named data/log volumes, loopback-only ports, a `cypher-shell` health check, [.env.example](../.env.example), and ignored `.env`/local database files. The Compose image tag is `neo4j:5.26.32-community`.

The lead executed both commands below. Each exited **127** with `zsh:1: command not found: docker`:

```sh
docker --version
docker compose version
```

There was no available Docker executable, Compose plugin or container runtime to execute this configuration. Installing Docker system-wide was outside this run. A standalone server was downloaded from [Neo4j's distribution](https://dist.neo4j.org/neo4j-community-5.26.32-unix.tar.gz) and Java from [Amazon Corretto's official downloads](https://docs.aws.amazon.com/corretto/latest/corretto-21-ug/downloads-list.html), with both downloads checked against their published SHA-256 files before extraction:

| Download | Observed/published SHA-256 |
| --- | --- |
| Neo4j 5.26.32 Unix tarball | `d279ae6a9b38034280681a558b0cd222dce89f87cc3d9867f1f7bd28ef5ebc30` |
| Corretto 21 macOS arm64 tarball | `f4ee9236ffc3ddcd37da877e04a1ab74b3d3376cf9e4287b5426f4749cc869a9` |

Binaries were extracted under `/private/tmp/pharmagraph-runtime/`. The standalone configuration binds `127.0.0.1`, uses 256–512 MiB heap/256 MiB page cache, and stores database/logs under ignored `data/neo4j/standalone-data` and `data/neo4j/standalone-logs`. Local random credentials were written to ignored `.env` with mode 0600; the password is absent from this report and tracked evidence. The password was initialized using `neo4j-admin dbms set-initial-password` with a programmatically supplied value.

The first sandboxed server start failed on socket binding with `bind(..) failed with error(-1): Operation not permitted`; the sandboxed driver likewise received `PermissionError: [Errno 1] Operation not permitted`. After authorized execution outside the sandbox, the real server started and client connections succeeded. This was a sandbox networking restriction, not a Neo4j code failure.

The runtime command actually executed was:

```sh
JAVA_HOME=/private/tmp/pharmagraph-runtime/amazon-corretto-21.jdk/Contents/Home /private/tmp/pharmagraph-runtime/neo4j-community-5.26.32/bin/neo4j console
```

The server remains available at `bolt://127.0.0.1:7687` / `http://127.0.0.1:7474` with local `.env` credentials. Stop it before using the Compose service on those ports. Temporary runtime binaries are not a durable installation; the project-local standalone database is separate from Docker's named volume.

## Commands and observed graph counts

The lead's acceptance runner executed the following public commands as subprocesses against the original verified processed release; every command below exited **0**. It also queried Neo4j directly for constraints and server identity, compared stable node element IDs across loads, and independently compared resolved measurements with PyArrow reads. Compact full results are saved in [acceptance.json](evidence/graph/acceptance.json).

```sh
.venv/bin/python scripts/load_graph.py
.venv/bin/python scripts/load_graph.py
.venv/bin/python scripts/query_graph.py counts
.venv/bin/python scripts/query_graph.py check
.venv/bin/python scripts/query_graph.py batches
.venv/bin/python scripts/query_graph.py variables
.venv/bin/python scripts/query_graph.py batch-variables --batch-ref 91
.venv/bin/python scripts/query_graph.py reference --batch-ref 91 --variable ph
.venv/bin/python scripts/query_graph.py measurements --batch-ref 91 --variable ph --start-tick 95 --end-tick 105 --limit 20
.venv/bin/python scripts/query_graph.py annotations --batch-ref 91
PHARMAGRAPH_NEO4J_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
```

The graph for `indpensim:pdnjz7zz5x:v2` was initially empty. The first load took **2.145 s**; the second **0.951 s**, including CLI startup, bundle validation and database operations.

| Node label | Expected from processed data | First load | Second load | After process restart |
| --- | ---: | ---: | ---: | ---: |
| Dataset | 1 | 1 | 1 | 1 |
| SourceFile | 2 | 2 | 2 | 2 |
| ProcessedArtifact | 3 | 3 | 3 | 3 |
| Batch | 100 | 100 | 100 | 100 |
| Variable | 33 | 33 | 33 | 33 |
| FaultAnnotation | 100 | 100 | 100 | 100 |
| **Total** | **239** | **239** | **239** | **239** |

| Relationship type | Expected | First load | Second load | After process restart |
| --- | ---: | ---: | ---: | ---: |
| HAS_SOURCE | 2 | 2 | 2 | 2 |
| HAS_ARTIFACT | 3 | 3 | 3 | 3 |
| HAS_BATCH | 100 | 100 | 100 | 100 |
| HAS_VARIABLE | 33 | 33 | 33 | 33 |
| FROM_SOURCE | 233 | 233 | 233 | 233 |
| HAS_DATA | 233 | 233 | 233 | 233 |
| DERIVED_FROM | 4 | 4 | 4 | 4 |
| HAS_ANNOTATION | 100 | 100 | 100 | 100 |
| **Total** | **708** | **708** | **708** | **708** |

Neo4j reported all six identity uniqueness constraints. Node element IDs were unchanged across the second load. The integrity query returned `ok: true`, zero duplicate IDs for every label, zero missing required relationships of every type, zero unexpected relationships and zero invalid entities. Tests also removed an edge and redirected another without changing the total, proving the integrity check examines endpoint identities rather than only aggregate counts.

The pinned processed manifest SHA-256 is `5f5d6f0b4c552fcaeae9834bd8216c9d67e6dd407b398c1a9b2805cbca7d6e63`; its cache key is `45f2c8f41cfe178202a53a56676d15abcaa24cf7ffba2af99ab7bc626b93cca7`. The loader read the processed files only; no original ZIP was opened or decompressed.

## Successful graph-to-Parquet evidence lookup

The real graph query for **batch 91, `ph`**, resolved through the shared samples artifact. The graph reference matched the authoritative variable definition and carried:

- Batch ID `indpensim:pdnjz7zz5x:v2:batch:091` and variable ID `indpensim:pdnjz7zz5x:v2:variable:ph`.
- Artifact `samples.parquet`, SHA-256 `3479fb11c22462c396e957ed099287c2f19147649814751776d552cf5bab90d5`; its full stable artifact ID includes the dataset, filename and this hash.
- Original source member `Mendeley_data/100_Batches_IndPenSim_V3.csv`, source-file ID `indpensim:pdnjz7zz5x:v2:timeseries`, zero-based source column **16**, exact header `pH(pH:pH)`, reported unit `pH`, status `reported_only`.
- Original archive SHA-256 `bc434c6cf96444fee3c915d434ac84e2a9c6492be4daebcfa4aed9cdff181f00`, copied from the validated manifest rather than obtained by reopening the archive.

Inclusive ticks **95–105** returned **11 measurements**, exactly equal to an independent PyArrow selection from the real samples table:

| Sample tick | Time (h) | Value as published | One-based CSV data row |
| --- | ---: | ---: | ---: |
| 95 | 19.0 | 6.4956 | 102505 |
| 105 | 21.0 | 6.4563 | 102515 |

For example, the first measurement was:

```json
{"sample_id":"indpensim:pdnjz7zz5x:v2:batch:091:tick:000095","batch_id":"indpensim:pdnjz7zz5x:v2:batch:091","time_h":19.0,"time_tick":95,"value":6.4956,"source_file_id":"indpensim:pdnjz7zz5x:v2:timeseries","source_row_number":102505}
```

The source-row convention excludes the CSV header. This establishes a trace through the processed artifact and pinned source coordinates; it is not a new raw-archive comparison or physical interpretation of pH. All 11 rows and the complete reference are retained in the evidence JSON.

## Detector purity and separate evaluation

The production `batches` query returned **100** records with identity/sample-count/time bounds only. `variables` and batch 91's `batch-variables` returned **30** process definitions each. The lead recursively checked detector-facing responses, references and measurement rows for forbidden fault/control/raw-metadata/harvest fields. None were present. Measurements contained only sample ID, batch ID, time/tick, value and original source-row/file provenance.

Published annotations were queried independently. The production graph returned **100 annotations: 10 true and 90 false**. Batch 91 returned `fault_present: true`, `annotation_kind: published_batch_fault_presence`, statistics source row **91**, zero-based column **4**, and exact header `Fault ref(0-NoFault 1-Fault)`. These values do not appear in process references or measurement responses. No fault type, time-window annotation, causal relationship, or quality specification was inferred.

## Independent tests

The lead executed:

```sh
PHARMAGRAPH_NEO4J_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
```

**46 tests passed, zero skipped, exit 0, 3.662 s.** The breakdown was 15 offline graph tests, 9 real-Neo4j integration tests, and the existing 22 ingestion regression tests. The ingestion regression tests used their own tiny synthetic archives; no full-data ingestion was rerun.

Graph tests build schema-complete, distinctly identified synthetic processed bundles from the pinned contract and retained manifest evidence, without parsing raw data. Real-instance tests create random fixture dataset IDs, mutate/clean only those datasets, and never clear the database. Their independently calculated fixture projection is 43 nodes/120 relationships.

Coverage includes manifest/hash/schema corruption; dataset/ID/source joins; historical writer fingerprints; exact values and sparse nulls; bounds/limit typing; tampered artifact/batch/source references; explicit summary opt-in; injection-shaped variable names; all six enforced constraints; idempotent loads; missing and wrongly directed edges; incomplete/model-version guards; manifest mismatch refusal without data changes; and explicit replacement that preserves another dataset. The flag-free run skips the 9 integration tests explicitly; those skips are not counted as database acceptance.

## Persistence and remaining blocker

After both production loads and the integration suite, the lead gracefully stopped the real standalone server and restarted it against the same data directory:

```sh
JAVA_HOME=/private/tmp/pharmagraph-runtime/amazon-corretto-21.jdk/Contents/Home /private/tmp/pharmagraph-runtime/neo4j-community-5.26.32/bin/neo4j stop
JAVA_HOME=/private/tmp/pharmagraph-runtime/amazon-corretto-21.jdk/Contents/Home /private/tmp/pharmagraph-runtime/neo4j-community-5.26.32/bin/neo4j console
```

No loader was run after restart. Reconnection returned **239 nodes / 708 relationships**, a passing integrity result, and exactly the same 11-row graph-to-Parquet lookup. This verifies persistence across a real server process restart.

**A container restart was not run.** The exact blocker is the missing `docker` executable (exit 127), so Compose startup, image execution, the container health check and named-volume persistence remain unverified. On a Docker-capable host, stop the standalone instance, follow [README setup](../README.md#local-neo4j-setup), load twice, and run:

```sh
.venv/bin/python scripts/query_graph.py counts
docker compose restart neo4j
docker compose up -d --wait
.venv/bin/python scripts/query_graph.py counts
.venv/bin/python scripts/query_graph.py check
.venv/bin/python scripts/query_graph.py measurements --batch-ref 91 --variable ph --start-tick 95 --end-tick 105
```

Do not reload between the before/after persistence checks. `docker compose down` preserves named volumes; `down -v` removes them. Standalone data and Docker named volumes are different stores and do not migrate automatically.

## Rebuild/version policy and limits

One logical dataset pins one exact processed manifest/cache key/model version. A changed manifest or artifact is refused until explicit replacement:

```sh
.venv/bin/python scripts/load_graph.py --processed-dir data/processed/indpensim --replace
.venv/bin/python scripts/query_graph.py check
```

The processed bundle must first pass validation against the pinned contract. Replacement affects only that logical dataset's nodes. Other datasets remain intact. A different published release requires its own dataset ID/contract. Re-run the same manifest to repair an interrupted load; input queries reject `load_state=loading`. Use a single loader during replacement and avoid concurrent processed-file changes. Existing graph references fail resolution when their pinned local manifest/artifact no longer matches.

The graph preserves unresolved units, sparse nulls, source-label limits and absence of assay availability timestamps. It creates no detector evidence, equipment/material/specification records, fault diagnoses or causal claims. Authentication and project-local persistence were exercised; deployment hardening, backups, high concurrency and performance at other dataset sizes are outside this milestone. The initial sandboxed PyArrow runs emitted CPU-capability warnings already documented during ingestion; outside-sandbox real-instance acceptance and the full test run exited successfully.
