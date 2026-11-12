# PharmaGraph

**Open without Terminal on this Mac:** double-click **PharmaGraph.app** in this project folder. It starts the project-local Neo4j database, verifies the existing credentials and matching data, starts the interface and opens your browser. Keep the launcher open while using the project; choose **Quit PharmaGraph** in its window or menu to stop its web server and any database it started. Saved database files are retained. You can also drag the app to the Dock for convenient access. Keep the app itself beside `app.py`, the installed `.venv` folder and `data/runtime`. It automatically chooses an available web port and reuses healthy services when reopened. Existing external databases are checked but never started or stopped automatically. The launcher is compiled for this Mac's Apple Silicon architecture; its editable sources are `scripts/launcher.swift`, `scripts/launch.py` and `scripts/local_database.py`. See [launcher recovery details](docs/launcher.md).

A local, evidence-backed investigation demo for simulated penicillin fermentation batches. It helps a reviewer move from an unusual process interval to the measurements, peer comparison and original source coordinates that support it. The business problem is the time spent assembling that evidence across process data and metadata during a batch investigation.

**Implemented workflow:** select a graph-listed batch → inspect four process trends → explicitly run an investigation → select a statistical finding → inspect measurements and graph provenance → download deterministic JSON. This is a portfolio MVP using published simulation data. Findings describe statistical deviations; they do not establish root causes, operating-limit violations or product-quality failures.

**New explanatory interface:** the app now opens on a **Project overview**, with product, business/use-case and technical-architecture tabs. A **Recorded walkthrough** lets you inspect the checked-in results for batches 031, 001 and 091, select individual temperature readings, trace source coordinates and download the recorded JSON without starting Neo4j. **Data & glossary** explains the terminology, units and comparison groups. **Investigate a batch** retains the live, explicit-run workflow, with clearer chart descriptions and coverage indicators. See the [UI walkthrough and verification](docs/ui_walkthrough.md).

To explore the overview and recorded cases using the existing environment:

```sh
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8510
```

Open [PharmaGraph on port 8510](http://127.0.0.1:8510). Only the live investigation workspace requires matching processed data and a running Neo4j database.

Start with the [three-minute walkthrough](docs/demo_walkthrough.md), [compact architecture/trade-offs](docs/architecture.md), and [complete technical architecture with data and execution diagrams](docs/architecture_detailed.md). Feature scope is frozen: no LLM, chatbot, authentication, deployment, additional detector or generic graph explorer is included.

A [beginner video lesson](docs/video/beginners-v3/README.md) explains the project for a college student with basic maths: one use case, simple definitions, worked arithmetic, animated diagrams and Indian-English neural narration. The full lesson is 25 minutes with 17 chapters and a [plain-English learning guide](docs/video/beginners-v3/learning_guide.md). Its MP4 is generated locally under ignored `artifacts/video/beginners-v3/`; the UI is illustrated schematically.

## What has been demonstrated

| Case | Observed result with unchanged defaults |
| --- | --- |
| Batch 031 | Temperature above peer reference at **86–87 h**, ticks 430–435, 6 observations; mean deviation score **11.8036** |
| Source trace | At 86 h: **298.38 K**, peer median **297.99 K**; original time-series CSV data row **34755**, zero-based column **17**, `Temperature(T:K)` |
| Batch 001 | Assessed, **no retained intervals**; this is not proof of normal or safe operation |
| Batch 091 | **Not assessed** because process compatibility is undocumented |

Real Neo4j loads were idempotent at **239 nodes / 708 relationships**, and data survived a standalone server restart. The UI flow and download payload were checked using Streamlit AppTest with real Neo4j/Parquet; live HTTP checks passed. Browser visual inspection, browser-triggered file saving and screenshots remain unverified because Chrome computer-use access was denied. Docker Compose startup/healthcheck/volume behavior and container restart remain unverified; the documented successful runtime was standalone Neo4j. See [validation records](#validation-and-repository-contents).

## 1. Install Python dependencies

Run from the repository root. Prerequisites: Python **3.11**, `uv`, `curl`, and enough disk for the original ~504 MB archive plus local runtime/data. Create the virtual environment once; skip its creation if already prepared.

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

Direct dependencies are pinned: PyArrow 21.0.0, Neo4j driver 5.28.2, Streamlit 1.66.1 and Plotly 7.1.0. The tested host was macOS arm64 with Python 3.11.17. Transitive dependencies are not lockfile-pinned; other hosts have not been independently validated.

## 2. Prepare the verified data

Source: Stephen Goldrick's [IndPenSim Mendeley Data V2 release](https://data.mendeley.com/datasets/pdnjz7zz5x/2), DOI **10.17632/pdnjz7zz5x.2**. Obtain the original `100_Batches_IndPenSim.zip`, rather than Mendeley's differently packaged “Download All” archive. The authoritative archive SHA-256 is:

```text
bc434c6cf96444fee3c915d434ac84e2a9c6492be4daebcfa4aed9cdff181f00
```

If the original archive is absent, this command resolves the verified release's file API and downloads it without overwriting an existing file. Storage URLs can change; [verification details and access alternatives](docs/data_verification.md#2-download-availability-sizes-integrity-and-usage-terms) retain the source evidence.

```sh
.venv/bin/python - <<'PY'
import hashlib, json, subprocess
from pathlib import Path
archive = Path('data/raw/indpensim/100_Batches_IndPenSim.zip')
archive.parent.mkdir(parents=True, exist_ok=True)
if not archive.exists():
    api = 'https://data.mendeley.com/public-api/datasets/pdnjz7zz5x/files/e7007dff-4061-494f-a9f5-16c20f457d1d/file_downloaded'
    metadata = json.loads(subprocess.check_output([
        'curl', '-fsSL', '-H', 'Accept: application/vnd.mendeley-public-dataset.1+json', api]))
    if metadata.get('status') != 'OK' or not metadata['url'].startswith('https://'):
        raise SystemExit('Download API did not return a valid HTTPS location')
    with archive.open('xb') as output:
        subprocess.run(['curl', '-fL', metadata['url']], stdout=output, check=True)
digest = hashlib.sha256()
with archive.open('rb') as source:
    for block in iter(lambda: source.read(1024 * 1024), b''):
        digest.update(block)
if digest.hexdigest() != 'bc434c6cf96444fee3c915d434ac84e2a9c6492be4daebcfa4aed9cdff181f00':
    raise SystemExit('Archive checksum mismatch; do not ingest this file')
print('Original archive checksum verified')
PY
.venv/bin/python scripts/ingest_indpensim.py
.venv/bin/python scripts/ingest_indpensim.py
```

The first ingestion builds the cache; the second validates/reuses it. Ingestion streams CSVs from the ZIP without extracting them to disk. It preserves source scales/nulls and rejects an unrecognized archive even with `--force`. Only ingestion/inspection reads the original archive; graph loading, investigation and the UI use processed files.

| Output under `data/processed/indpensim/` | Contents |
| --- | --- |
| `batches.parquet` | 100 batch records, provenance, published labels and documented control-regime metadata |
| `samples.parquet` | 113,935 samples, 30 selected process channels and source coordinates |
| `variables.parquet` | 33 definitions: 30 process variables plus 3 raw harvest summaries |
| `manifest.json` | Exact schemas, source/output checksums, cache fingerprint and normalization warnings |

Raw archives, local caches and databases are ignored by Git. Full-data ingestion checks and the manifest-last publication/recovery limits are documented in [ingestion_validation.md](docs/ingestion_validation.md).

## 3. Configure credentials

```sh
cp -n .env.example .env
chmod 600 .env
```

Edit `.env` and replace `NEO4J_PASSWORD` with a local password of at least eight characters. Keep `NEO4J_URI=bolt://127.0.0.1:7687`, `NEO4J_USER=neo4j` and `NEO4J_DATABASE=neo4j` for the commands below. `.env` is ignored. Python reads simple assignments without executing shell text; environment variables override file values. Do not `source .env` or put credentials into the UI. Changing the file does not rotate a password in an initialized database.

<a id="local-neo4j-setup"></a>

## 4. Start one Neo4j runtime

Choose **A or B**; both use ports 7474/7687, so do not run them simultaneously. The tested server version is **Neo4j Community 5.26.32**, with Java **21.0.13** for standalone execution.

### A. Standalone — tested runtime path

The successful validation used a standalone Neo4j process on macOS arm64, loopback-only listeners, 256–512 MiB heap, 256 MiB page cache, and project-local persistent data/logs. The following fresh-install recipe uses the same verified distribution bytes with repository-relative runtime locations. Do not reinitialize an existing database. On another platform, obtain its Java 21 distribution and adjust `JAVA_HOME`; that platform is not claimed as tested.

```sh
mkdir -p data/runtime
curl -fL https://dist.neo4j.org/neo4j-community-5.26.32-unix.tar.gz -o data/runtime/neo4j.tar.gz
curl -fL https://corretto.aws/downloads/resources/21.0.13.0.11/amazon-corretto-21.0.13.0.11-macosx-aarch64.tar.gz -o data/runtime/java.tar.gz
.venv/bin/python - <<'PY'
import hashlib, tarfile
from pathlib import Path
root = Path.cwd()
runtime = root / 'data/runtime'
checks = {'neo4j.tar.gz': 'd279ae6a9b38034280681a558b0cd222dce89f87cc3d9867f1f7bd28ef5ebc30',
          'java.tar.gz': 'f4ee9236ffc3ddcd37da877e04a1ab74b3d3376cf9e4287b5426f4749cc869a9'}
for name, expected in checks.items():
    path = runtime / name
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit(f'Runtime checksum mismatch: {name}')
    with tarfile.open(path) as archive:
        archive.extractall(runtime, filter='data')
conf = runtime / 'neo4j-community-5.26.32/conf/neo4j.conf'
settings = {'server.default_listen_address': '127.0.0.1',
            'server.memory.heap.initial_size': '256m', 'server.memory.heap.max_size': '512m',
            'server.memory.pagecache.size': '256m',
            'server.directories.data': str(root / 'data/neo4j/standalone-data'),
            'server.directories.logs': str(root / 'data/neo4j/standalone-logs')}
conf.write_text(conf.read_text() + '\n' + '\n'.join(f'{k}={v}' for k, v in settings.items()) + '\n')
PY
export JAVA_HOME="$PWD/data/runtime/amazon-corretto-21.jdk/Contents/Home"
export PHARMAGRAPH_NEO4J_HOME="$PWD/data/runtime/neo4j-community-5.26.32"
```

Before the **first** server start only, initialize the password from the ignored environment configuration without placing it literally in shell history:

```sh
.venv/bin/python - <<'PY'
import os, subprocess
from pathlib import Path
from scripts.graph import environment
values = environment()
password = values.get('NEO4J_PASSWORD', '')
if len(password) < 8 or password == 'replace-with-a-local-password':
    raise SystemExit('Set a non-placeholder NEO4J_PASSWORD in .env first')
command = Path(os.environ['PHARMAGRAPH_NEO4J_HOME']) / 'bin/neo4j-admin'
result = subprocess.run([str(command), 'dbms', 'set-initial-password', password], capture_output=True)
if result.returncode:
    raise SystemExit('Initial-password setup failed; check the fresh database and local credentials')
print('Initial password configured')
PY
"$PHARMAGRAPH_NEO4J_HOME/bin/neo4j" console
```

Leave the server terminal running; run the remaining commands in a second terminal at the repository root. For a later restart, reuse the same `JAVA_HOME`, runtime home and data directory; no reload should be needed:

```sh
"$PHARMAGRAPH_NEO4J_HOME/bin/neo4j" stop
"$PHARMAGRAPH_NEO4J_HOME/bin/neo4j" console
```
 The historical acceptance runtime lived under a temporary directory; its exact commands remain in [graph_validation.md](docs/graph_validation.md). The relocatable recipe above has been checked against those binaries/configuration; this finalization does not claim another clean-host installation or restart test.

### B. Docker Compose — provided, not runtime-verified

Requires Docker Engine/Desktop and Compose v2:

```sh
docker compose up -d --wait
docker compose ps
```

[compose.yaml](compose.yaml) pins the same server version, binds loopback, defines a `cypher-shell` healthcheck and named data/log volumes. **Docker was unavailable during validation** (`command not found: docker`, exit 127). Compose startup, healthcheck execution, named-volume persistence and container restart remain outstanding; standalone persistence does not prove them. No Docker availability work was done during finalization.

## 5. Load the graph and launch the demo

With either runtime ready:

```sh
.venv/bin/python scripts/load_graph.py
.venv/bin/python scripts/load_graph.py
.venv/bin/python scripts/query_graph.py counts
.venv/bin/python scripts/query_graph.py check
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

Open **http://127.0.0.1:8501**. The second load must stay at **239 nodes / 708 relationships**. The Streamlit configuration is local-only and disables usage statistics. Stop the UI with Ctrl+C. `PHARMAGRAPH_PROCESSED_DIR` optionally selects another processed root, but its generation must match the graph.

The UI exposes published simulation trends, an explicit **Run investigation** button, ranked derived findings, a median/threshold envelope, complete interval evidence, actual directed graph relationships and JSON download. It caches reusable data/resources while checking current content/contract hashes and live graph pins before cached display. Unrelated UI interactions do not rerun the full engine.

For a reproducible CLI-only result:

```sh
.venv/bin/python scripts/investigate_batch.py --batch-id indpensim:pdnjz7zz5x:v2:batch:031 --output data/investigations/batch031.json
```

A changed manifest/cache key/model is refused for an existing graph dataset. After checking the intended new processed generation, use `scripts/load_graph.py --replace` explicitly; replacement affects only that dataset. A different published release needs a distinct dataset ID/contract. Old references fail against changed artifacts. Use one loader during replacement. Docker `down` retains named volumes; `down -v` deletes them and is not part of this setup.

## Architecture and detector assumptions

**Neo4j holds identities, definitions and provenance; Parquet holds full numerical time series.** Graph references bind a batch/variable to a fixed artifact hash and source coordinates. This avoids per-sample graph nodes and keeps numerical scans columnar. The graph navigates evidence and validates references; it does not calculate scores, infer causality or supply extra operational records. SQL tables and joins could implement the same relationships; the graph is a deliberate navigation/modeling choice with an extra-store consistency cost. See [architecture.md](docs/architecture.md).

The single detector uses `aeration_rate`, `sugar_feed_rate`, `ph` and `temperature`. At each exact 0.2-hour tick it compares the target with available peers in the **same documented control regime**, excluding the target:

```text
median = median(peer values)
MAD = median(abs(peer values - median))
reference_spread = 1.4826 * MAD
point_score = abs(observed - median) / reference_spread
```

Defaults are **10 finite peers**, score **strictly above 6**, and **5 consecutive same-direction observations**. Five observations span 0.8 h between endpoints. Intervals rank by mean point score. These configurable CLI heuristics are fixed in the UI and have not been calibrated for detection accuracy. The envelope is a statistical reference, not a confidence interval or operating specification.

Missing/unmatched/insufficient ticks break runs; there is no interpolation, fill or extrapolation. Zero MAD gives score 0 for an equal target and an explicitly unscoreable comparison otherwise. Small positive MAD can amplify small absolute changes. Recipe-driven (001–030), operator-controlled (031–060) and APC/Raman (061–090) groups are coarse compatibility proxies; matching time does not align biological phases. **Batches 091–100 have undocumented compatibility and are not assessed.** No result is a safety or quality classification.

Published fault annotations remain separate graph records/evaluation queries. The detector and UI never query them, and neither labels, raw flag fields nor harvest values enter scoring. Existing bundle validation checks integrity independently of feature selection. Tests changing/removing graph annotations leave complete investigation results unchanged. Source-unit uncertainty, malformed Raman mapping and missing operational/quality records remain explicit limits in the [data dictionary](docs/data_dictionary.md).

## Dataset attribution and terms

Goldrick, Stephen (2019), *Data for: Modern day monitoring and control challenges outlined on an industrial-scale benchmark fermentation process*, Mendeley Data, **V2**, DOI [10.17632/pdnjz7zz5x.2](https://doi.org/10.17632/pdnjz7zz5x.2), published 8 October 2019. This is simulated fermentation data, not GMP production records.

The dataset is [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/): sharing/adaptation, including commercial use, require appropriate attribution, a license link, and an indication of changes; do not imply endorsement or add restrictions prohibited by the license. PharmaGraph changes representation by selecting/renaming documented fields, preserving source scales/nulls, deriving identifiers/summary metadata, and adding separately identified statistical findings. Raw source bytes are unchanged. Dataset terms do not establish a license for this repository's code, the notebook, or the differently licensed paper.

The publisher requests the [2015 simulator paper](https://doi.org/10.1016/j.jbiotec.2014.10.029) and [2019 benchmark paper](https://doi.org/10.1016/j.compchemeng.2019.05.037) be cited. [data_verification.md](docs/data_verification.md) records attribution, exact source bytes, access failures and unresolved semantics.

## Validation and repository contents

Run all checks against matching local Neo4j and processed data:

```sh
PHARMAGRAPH_NEO4J_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
```

Without the flag, live database/UI integration tests skip; skips are not acceptance evidence. Historical validation recorded **89 passing tests with no skips**, plus real-data investigations, deterministic JSON, source tracing, actionable error states and HTTP health checks. Finalization results and hygiene findings are in [portfolio_validation.md](docs/portfolio_validation.md).

- [Architecture and trade-offs](docs/architecture.md)
- [Complete technical architecture, data shapes and execution diagrams](docs/architecture_detailed.md)
- [Three-minute demo and remaining manual checks](docs/demo_walkthrough.md)
- [Ingestion validation](docs/ingestion_validation.md), [graph validation](docs/graph_validation.md), [investigation validation](docs/investigation_validation.md)
- [Data contract](docs/data_contract.md), [exact schemas](config/indpensim_contract.json), [graph model](docs/graph_model.md)
- [Evidence inventory and portability notes](docs/evidence/README.md)

No clean-host/end-to-end installation, browser rendering/file-save verification, screenshot capture or Docker container-restart result is claimed beyond the recorded checks. This is a local demonstration, not a validated manufacturing or regulated decision system.
