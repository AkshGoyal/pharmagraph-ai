# Double-click launcher and local database recovery

Open **PharmaGraph.app** from the project folder. No Terminal command is needed. The launcher:

1. Connects using the existing server-side `.env` settings. A rejected password produces a distinct error and is not reset.
2. If the configured loopback database is stopped, starts the pinned project-local Neo4j runtime against `data/neo4j/standalone-data` using project-local Java 21.
3. Waits for an authenticated connection and verifies graph/processed-file compatibility. A genuinely absent dataset can be loaded from the verified processed bundle; an existing incompatible dataset is never automatically replaced.
4. Starts or reuses its local Streamlit server and opens the browser only after the database is ready.
5. On **Quit PharmaGraph**, stops its web server and only the database process it started. Database files and credentials remain in place. Process ownership is checked before termination; unrelated services are not stopped.

## Cause of the connection error

The previous Neo4j/Java runtime was under `/private/tmp/pharmagraph-runtime`. Those temporary binaries disappeared while the project-local database and verified Parquet files remained intact. The original launcher started only Streamlit, so live investigations could not connect to Neo4j.

The runtimes have now been restored under ignored `data/runtime`, rather than temporary storage. The downloaded official distributions match the previously recorded SHA-256 pins:

| Runtime | SHA-256 |
| --- | --- |
| Neo4j Community 5.26.32 | `d279ae6a9b38034280681a558b0cd222dce89f87cc3d9867f1f7bd28ef5ebc30` |
| Amazon Corretto 21.0.13.0.11, macOS arm64 | `f4ee9236ffc3ddcd37da877e04a1ab74b3d3376cf9e4287b5426f4749cc869a9` |

The recovery reuses the saved database and existing password. It does not reinitialize authentication, replace the dataset or change system Java. Database listeners bind to loopback; Neo4j usage reporting and Streamlit usage statistics are disabled in the managed runtime settings.

## Local files

Launcher state, generated Neo4j configuration and logs are under ignored `.local/launcher/`. The two diagnostic logs are `neo4j-console.log` and `server.log`. Passwords are neither passed as command-line arguments nor copied into the launch state. Runtime archives/binaries, the saved database and `.env` remain ignored by Git.

The launcher expects the existing project environment and prepared database. Keep the app inside this project folder; a Dock shortcut may point to it. The original manual launch instructions remain available in the README for development.

## Recovery verification

The full suite ran with `PHARMAGRAPH_NEO4J_INTEGRATION=1`: **92 tests passed, no skips**, including actual Neo4j/Parquet investigations and Streamlit AppTest coverage. A real launcher lifecycle check confirmed that reopening reuses both service PIDs, quitting stops the managed web server and Neo4j, and restarting authenticates with the unchanged `.env` contents. The saved graph remained at **239 nodes and 708 relationships** after restart. A stale-PID check confirmed that database shutdown leaves an unrelated process running.

Browser verification on the restarted service completed a fresh Batch 031 investigation, displayed one retained temperature interval at 86–87 h, six supporting observations and actual graph provenance. The screenshot in [evidence/launcher/live-investigation.jpg](evidence/launcher/live-investigation.jpg) shows the successful live result and its partial-coverage warning. Native Finder/window automation was not repeated; the rebuilt app bundle passed compilation and property-list checks, and its exact Python helper was used for the service lifecycle check.
