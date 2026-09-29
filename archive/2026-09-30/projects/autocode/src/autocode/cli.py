"""Installed command-line adapter for the autocode application service."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from autocode.application import AutocodeApplication
from autocode.artifacts import LocalArtifactStore
from autocode.runner import runner_for_mode
from autocode.store.repository import SessionRepository

VERSION = "0.2.0"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autocode", description="A local-first coding-agent product")
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run one task through the application service")
    run.add_argument("message")
    run.add_argument("--db", type=Path, default=Path(".autocode/sessions.db"))
    run.add_argument("--json", action="store_true", help="emit machine-readable events")
    run.add_argument("--agent", choices=("demo", "harness"), default=_agent_mode())

    resume = sub.add_parser("resume", help="show a saved session")
    resume.add_argument("session_id")
    resume.add_argument("--db", type=Path, default=Path(".autocode/sessions.db"))

    serve = sub.add_parser("serve", help="serve the browser application and API")
    serve.add_argument("--db", type=Path, default=Path(".autocode/sessions.db"))
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--agent", choices=("demo", "harness"), default=_agent_mode())

    config = sub.add_parser("config", help="show effective local configuration")
    config.add_argument("--json", action="store_true")
    sub.add_parser("doctor", help="check the local installation")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "doctor":
        print(f"autocode {VERSION}: ready")
        return 0
    if args.command == "config":
        value = {
            "version": VERSION,
            "agent_mode": _agent_mode(),
            "data_dir": os.environ.get("AUTOCODE_DATA_DIR", ".autocode"),
        }
        print(json.dumps(value) if args.json else _config_text(value))
        return 0
    if args.command == "serve":
        return _serve(args)

    application = AutocodeApplication(
        SessionRepository(args.db),
        runner_for_mode(getattr(args, "agent", "demo"), cwd=Path.cwd()),
        artifact_store=LocalArtifactStore(args.db.parent / "artifacts"),
    )
    if args.command == "run":
        session = application.create_session(title=args.message[:60])
        events = asyncio.run(_collect_run(application, session.session_id, args.message))
        if args.json or not sys.stdout.isatty():
            for event in events:
                print(json.dumps(event, sort_keys=True))
        else:
            answer = next(
                (
                    event["payload"]["content"]
                    for event in reversed(events)
                    if event["kind"] == "assistant_message"
                ),
                "Run finished without an assistant message.",
            )
            print(f"session {session.session_id}")
            print(answer)
        return 0
    if args.command == "resume":
        session = application.repository.get(args.session_id)
        if session is None:
            print(f"unknown session: {args.session_id}", file=sys.stderr)
            return 2
        print(json.dumps(session.to_dict(), indent=2, sort_keys=True))
        return 0
    return 1


async def _collect_run(
    application: AutocodeApplication, session_id: str, message: str
) -> list[dict[str, Any]]:
    return [event.to_dict() async for event in application.stream_message(session_id, message)]


def _serve(args: argparse.Namespace) -> int:
    try:
        uvicorn = importlib.import_module("uvicorn")
        api = importlib.import_module("autocode_service.api")
    except ImportError as exc:
        raise RuntimeError("install autocode[service] to run the web application") from exc

    application = AutocodeApplication(
        SessionRepository(args.db),
        runner_for_mode(args.agent, cwd=Path.cwd()),
        artifact_store=LocalArtifactStore(args.db.parent / "artifacts"),
    )
    uvicorn.run(
        api.create_app(application, agent_mode=args.agent),
        host=args.host,
        port=args.port,
    )
    return 0


def _agent_mode() -> str:
    return os.environ.get("AUTOCODE_AGENT_MODE", "demo")


def _config_text(value: dict[str, str]) -> str:
    return "\n".join(f"{key}={item}" for key, item in value.items())


if __name__ == "__main__":
    raise SystemExit(main())
