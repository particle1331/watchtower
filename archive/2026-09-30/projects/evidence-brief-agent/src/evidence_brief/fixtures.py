"""Load the deterministic corpus and held-out question suite."""

import json
from pathlib import Path
from typing import Any

from evidence_brief.schemas import BriefRequest, EvaluationCase, PublicBarRecord, SourceRecord

DATA_DIR = Path(__file__).with_name("data")


def _load(name: str) -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def load_corpus() -> list[SourceRecord]:
    return [SourceRecord.model_validate(row) for row in _load("corpus.json")]


def load_questions() -> list[EvaluationCase]:
    return [EvaluationCase.model_validate(row) for row in _load("questions.json")]


def load_public_bar_records() -> list[PublicBarRecord]:
    return [PublicBarRecord.model_validate(row) for row in _load("public_bar_regression.json")]


def question_record(question_id: str) -> EvaluationCase:
    return next(row for row in load_questions() if row.id == question_id)


def request_for(question_id: str) -> BriefRequest:
    row = question_record(question_id)
    return BriefRequest(question_id=question_id, question=row.question, facts=row.facts)
