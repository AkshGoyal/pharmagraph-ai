"""Start the project-local Neo4j runtime without changing stored credentials."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
from urllib.parse import urlsplit

from neo4j import GraphDatabase
from neo4j.exceptions import AuthError

try:
    from . import demo, graph
except ImportError:
    import demo
    import graph

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".local" / "launcher"
HOME = ROOT / "data/runtime/neo4j-community-5.26.32"
JAVA = ROOT / "data/runtime/amazon-corretto-21.jdk/Contents/Home"
CONF = STATE / "neo4j-conf"


def owned_database(pid):
    if type(pid) is not int or pid <= 0:
        return False
    try:
        command = subprocess.check_output(["/bin/ps", "-p", str(pid), "-o", "command="],
                                          text=True, stderr=subprocess.DEVNULL, timeout=3)
        return str(HOME) in command and "org.neo4j" in command
    except (OSError, subprocess.SubprocessError):
        return False


def stop_database():
    path = STATE / "neo4j.json"
    try:
        state = json.loads(path.read_text())
        pid = state.get("pid")
    except (OSError, ValueError, AttributeError):
        return
    if owned_database(pid):
        try:
            if os.getpgid(pid) == pid:
                os.killpg(pid, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + 20
        while owned_database(pid) and time.monotonic() < deadline:
            time.sleep(.2)
        if owned_database(pid):
            raise RuntimeError("Neo4j is still finishing shutdown. Wait a moment before reopening PharmaGraph.")
    path.unlink(missing_ok=True)


def driver(values):
    return GraphDatabase.driver(values.get("NEO4J_URI", "bolt://127.0.0.1:7687"),
        auth=(values.get("NEO4J_USER", "neo4j"), values["NEO4J_PASSWORD"]),
        connection_timeout=2, connection_acquisition_timeout=4, max_transaction_retry_time=2)


def connected(values):
    try:
        with driver(values) as connection:
            connection.verify_connectivity()
        return True
    except AuthError:
        raise RuntimeError("Neo4j is running, but the configured password was rejected. The saved database and credentials have been preserved; check the project's .env configuration.") from None
    except Exception:
        return False


def prepare_config():
    if not (HOME / "bin/neo4j").is_file() or not (JAVA / "bin/java").is_file():
        raise RuntimeError("The project-local Neo4j or Java runtime is missing from data/runtime. Restore the pinned project runtimes before opening PharmaGraph.")
    if not (ROOT / "data/neo4j/standalone-data/databases/system").is_dir():
        raise RuntimeError("The saved local database is missing. Restore its data directory before starting PharmaGraph; the launcher will not reset existing credentials.")
    CONF.mkdir(parents=True, exist_ok=True)
    (STATE / "neo4j-run").mkdir(parents=True, exist_ok=True)
    settings = {
        "dbms.usage_report.enabled": "false",
        "server.default_listen_address": "127.0.0.1",
        "server.default_advertised_address": "127.0.0.1",
        "server.bolt.enabled": "true",
        "server.bolt.listen_address": "127.0.0.1:7687",
        "server.http.enabled": "true",
        "server.http.listen_address": "127.0.0.1:7474",
        "server.https.enabled": "false",
        "server.memory.heap.initial_size": "256m",
        "server.memory.heap.max_size": "512m",
        "server.memory.pagecache.size": "256m",
        "server.directories.data": str(ROOT / "data/neo4j/standalone-data"),
        "server.directories.logs": str(ROOT / "data/neo4j/standalone-logs"),
        "server.directories.run": str(STATE / "neo4j-run"),
    }
    (CONF / "neo4j.conf").write_text("\n".join(f"{key}={value}" for key, value in settings.items()) + "\n")


def ensure_database():
    values = graph.environment()
    if not values.get("NEO4J_PASSWORD") or values["NEO4J_PASSWORD"] == "replace-with-a-local-password":
        raise RuntimeError("The project's server-side Neo4j password is not configured. Restore the existing .env configuration; no password has been reset.")
    if not connected(values):
        endpoint = urlsplit(values.get("NEO4J_URI", "bolt://127.0.0.1:7687"))
        if endpoint.hostname not in ("127.0.0.1", "localhost") or (endpoint.port or 7687) != 7687:
            raise RuntimeError("The configured external Neo4j database is unavailable. Automatic startup only manages this project's local database.")
        try:
            with socket.create_connection((endpoint.hostname, 7687), timeout=1):
                occupied = True
        except OSError:
            occupied = False
        if not occupied:
            prepare_config()
            env = {**os.environ, "JAVA_HOME": str(JAVA), "NEO4J_CONF": str(CONF)}
            with (STATE / "neo4j-console.log").open("a") as log:
                process = subprocess.Popen([str(HOME / "bin/neo4j"), "console"], cwd=ROOT,
                    env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            (STATE / "neo4j.json").write_text(json.dumps({"pid": process.pid}))
        deadline = time.monotonic() + 75
        while time.monotonic() < deadline:
            if connected(values):
                break
            if not occupied and process.poll() is not None:
                raise RuntimeError("The local database could not start. Details are saved in .local/launcher/neo4j-console.log; the saved database has been preserved.")
            time.sleep(.5)
        else:
            raise RuntimeError("Neo4j did not become ready in time. Quit PharmaGraph and try opening it again; the saved database has been preserved.")
    # The browser only opens after credentials and the graph/data generation agree.
    try:
        processed = Path(os.environ.get("PHARMAGRAPH_PROCESSED_DIR", str(graph.DEFAULT_OUTPUT)))
        bundle = graph.validate_processed(processed)
        database = values.get("NEO4J_DATABASE", "neo4j")
        with driver(values) as connection:
            dataset_id = bundle["manifest"]["dataset"]["id"]
            with connection.session(database=database) as session:
                exists = session.run("MATCH (d:Dataset {dataset_id: $id}) RETURN count(d) AS count", id=dataset_id).single()["count"]
            if not exists:
                graph.load_graph(connection, processed, database=database)
            demo.live_context(connection, bundle, database)
    except Exception:
        raise RuntimeError("Neo4j is connected, but the saved graph and processed data do not match. Restore the matching dataset; no automatic replacement was performed.") from None
