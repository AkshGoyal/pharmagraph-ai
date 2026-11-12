"""Background-server lifecycle for the double-click macOS launcher."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".local" / "launcher"
BASE_PATH = "pharmagraph"


def database_runtime():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts import local_database
    return local_database


def read_state():
    try:
        value = json.loads((RUNTIME / "server.json").read_text())
        if (type(value.get("pid")) is int and value["pid"] > 0
                and type(value.get("port")) is int and 1024 <= value["port"] <= 65535):
            return value
    except (OSError, ValueError, AttributeError):
        pass
    return None


def owned_server(state):
    """Never reuse or stop another app, even if a stale PID was recycled."""
    if state is None:
        return False
    try:
        command = subprocess.check_output(
            ["/bin/ps", "-p", str(state["pid"]), "-o", "command="],
            text=True, stderr=subprocess.DEVNULL, timeout=3,
        )
        return all(part in command for part in (
            "-m streamlit run", str(ROOT / "app.py"),
            f"--server.port={state['port']}", f"--server.baseUrlPath={BASE_PATH}",
        ))
    except (OSError, subprocess.SubprocessError):
        return False


def ready(port):
    # Local health checks bypass proxy settings and do not transmit any credentials.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/{BASE_PATH}/_stcore/health", timeout=1) as response:
            return response.status == 200 and response.read(16).strip() == b"ok"
    except (OSError, urllib.error.URLError):
        return False


def free_port():
    for port in range(8510, 8531):
        with socket.socket() as listener:
            try:
                listener.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No local preview port is available. Close another local preview and try again.")


def stop_server():
    state = read_state()
    if owned_server(state):
        try:
            os.kill(state["pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass
        for _ in range(30):
            if not owned_server(state):
                break
            time.sleep(.1)
    (RUNTIME / "server.json").unlink(missing_ok=True)


def start_server():
    database_runtime().ensure_database()
    state = read_state()
    if owned_server(state) and ready(state["port"]):
        return f"http://127.0.0.1:{state['port']}/{BASE_PATH}/"
    # Restart only a server previously created by this launcher.
    stop_server()
    if not (ROOT / "app.py").is_file():
        raise RuntimeError("Keep PharmaGraph.app in the project folder beside app.py, then try again.")
    try:
        import streamlit  # noqa: F401
    except ImportError:
        raise RuntimeError("The project's Python environment is missing Streamlit. Restore the project's installed environment, then try again.") from None
    port = free_port()
    with (RUNTIME / "server.log").open("w") as log:
        process = subprocess.Popen([
            sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
            "--server.address=127.0.0.1", f"--server.port={port}",
            f"--server.baseUrlPath={BASE_PATH}", "--server.headless=true",
            "--browser.gatherUsageStats=false", "--server.fileWatcherType=none",
        ], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    state = {"pid": process.pid, "port": port}
    (RUNTIME / "server.json").write_text(json.dumps(state))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        if ready(port):
            return f"http://127.0.0.1:{port}/{BASE_PATH}/"
        time.sleep(.2)
    stop_server()
    raise RuntimeError("PharmaGraph could not start. Try opening the launcher again. Details are saved in .local/launcher/server.log inside the project folder.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with (RUNTIME / "server.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            if args.stop:
                stop_server()
                database_runtime().stop_database()
            else:
                print(start_server(), flush=True)
        except Exception as error:
            message = str(error) if isinstance(error, RuntimeError) else "The local launcher could not complete. Close PharmaGraph and try opening it again."
            print(message, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
