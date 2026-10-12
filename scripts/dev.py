"""Start the author CMS and working preview together; own both server processes."""

import argparse
import http.client
import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from contextlib import suppress
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[1]


def check_ports(port: int, cms_port: int) -> None:
    if not all(1 <= value <= 65535 for value in (port, cms_port)):
        raise ValueError("PORT and CMS_PORT must be between 1 and 65535")
    if port == cms_port:
        raise ValueError("PORT and CMS_PORT must be different")
    for value in (port, cms_port):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", value))
            except OSError as error:
                raise ValueError(
                    f"Port {value} is unavailable. Stop its server or choose other ports with "
                    "make dev PORT=4300 CMS_PORT=5300."
                ) from error


def ready(port: int, path: str) -> bool:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=0.25)
    try:
        connection.request("GET", path)
        return 200 <= connection.getresponse().status < 400
    except (OSError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def stop(processes: list[subprocess.Popen]) -> None:
    # Each server has its own process group, including its foreground render tools.
    for process in processes:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def run_workspace(port: int, cms_port: int, *, open_browser: bool = True) -> int:
    check_ports(port, cms_port)
    servers = [("CMS", "serve", cms_port, "/cms/"), ("Preview", "preview", port, "/")]
    processes: list[subprocess.Popen] = []
    previous_term = signal.getsignal(signal.SIGTERM)

    def interrupted(signum: int, frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        for label, command, value, path in servers:
            processes.append(subprocess.Popen(
                [sys.executable, "-m", "watchtower.cli", command, "--port", str(value)],
                cwd=ROOT_PATH, start_new_session=True,
            ))
            print(f"{label}: http://127.0.0.1:{value}{path}", flush=True)
        print("Building the preview from saved content. Ctrl+C stops both servers.", flush=True)
        pending = list(servers) if open_browser else []
        while True:
            for (label, *_), process in zip(servers, processes, strict=True):
                code = process.poll()
                if code is not None:
                    print(f"{label} stopped; shutting down both servers.", file=sys.stderr)
                    return code if code > 0 else 128 - code if code < 0 else 1
            for server in pending[:]:
                label, _, value, path = server
                if ready(value, path):
                    webbrowser.open_new_tab(f"http://127.0.0.1:{value}{path}")
                    pending.remove(server)
            time.sleep(0.2)
    except KeyboardInterrupt:
        return 130
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        stop(processes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=4200, help="Working preview port (default: 4200)")
    parser.add_argument("--cms-port", type=int, default=5200, help="CMS port (default: 5200)")
    parser.add_argument("--no-browser", action="store_true", help="Start servers without opening tabs")
    args = parser.parse_args()
    try:
        return run_workspace(args.port, args.cms_port, open_browser=not args.no_browser)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
