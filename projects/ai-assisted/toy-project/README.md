# Habit Tracker (toy project)

A small command-line habit tracker. It exists to demonstrate the AI-assisted development
process documented in [`../WHITEPAPER.md`](../WHITEPAPER.md). The application is simple on
purpose. The *record* of how it was built is the point: see [`journal/`](journal/).

## Run it

Requires Python 3.9 or later. No third-party packages.

```
python3 -m habits add "Read"
python3 -m habits checkin 1                    # today
python3 -m habits checkin 1 --date 2026-10-08  # a past day
python3 -m habits list                         # id, current streak, name
python3 -m habits export                       # all data as JSON
```

The database is `habits.sqlite3` in the current directory. Set `HABITS_DB` to choose another file.

## Test it

```
python3 -m unittest discover -s tests -t . -v
```

## Where to look

| Path | What it is |
|------|------------|
| `ARCHITECTURE.md` | The layers, the dependency rule, and the key decisions (ADRs). Read first. |
| `AGENTS.md` | Rules any AI agent must follow when working on this project. |
| `habits/` | The code, in four layers: `domain`, `application`, `adapters`, `cli`, plus the composition root `main.py`. |
| `tests/test_architecture.py` | Enforces the dependency rule and the clock rule mechanically. |
| `journal/` | One file per build step: plan, approval, changes, verification, review, drift check, lessons. |
