"""Command-line front end. Parses arguments and calls HabitService. Holds no business rules."""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from typing import List, Optional, TextIO

from habits.application.habit_service import HabitService
from habits.domain.errors import DomainError

EXIT_OK = 0
EXIT_DOMAIN_ERROR = 1  # usage errors exit 2 through argparse


def _parse_date(text: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid date {text!r}, expected YYYY-MM-DD")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="habits", description="Track daily habits.")
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="add a habit")
    add.add_argument("name", help="habit name, 1 to 60 characters")

    checkin = commands.add_parser("checkin", help="check a habit in")
    checkin.add_argument("habit_id", type=int)
    checkin.add_argument("--date", type=_parse_date, default=None, help="YYYY-MM-DD (default: today)")

    commands.add_parser("list", help="list habits with their current streaks")
    commands.add_parser("export", help="print all habits and check-ins as JSON")
    return parser


EXPORT_FORMAT_VERSION = 1


def export_document(service: HabitService) -> str:
    """Serialise all data as a JSON document. The format is versioned so it can evolve."""
    document = {
        "version": EXPORT_FORMAT_VERSION,
        "habits": [
            {
                "id": item.habit.id,
                "name": item.habit.name,
                "check_ins": [day.isoformat() for day in item.check_in_days],
            }
            for item in service.export_all()
        ],
    }
    return json.dumps(document, indent=2)


def run(
    argv: List[str],
    service: HabitService,
    today: datetime.date,
    out: Optional[TextIO] = None,
    err: Optional[TextIO] = None,
) -> int:
    """Run one command and return an exit code. Streams default to sys.stdout and sys.stderr."""
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    args = build_parser().parse_args(argv)
    try:
        if args.command == "add":
            habit = service.add_habit(args.name)
            print(f"added habit {habit.id}: {habit.name}", file=out)
        elif args.command == "checkin":
            day = args.date or today
            service.check_in(args.habit_id, day)
            print(f"checked in habit {args.habit_id} for {day.isoformat()}", file=out)
        elif args.command == "list":
            summaries = service.list_habits(today)
            if not summaries:
                print("No habits yet.", file=out)
            for summary in summaries:
                print(f"{summary.habit.id:>3}  streak {summary.streak:>3}  {summary.habit.name}", file=out)
        elif args.command == "export":
            print(export_document(service), file=out)
    except DomainError as exc:
        print(f"error: {exc}", file=err)
        return EXIT_DOMAIN_ERROR
    return EXIT_OK
