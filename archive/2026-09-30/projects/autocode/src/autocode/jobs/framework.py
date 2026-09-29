"""A small durable-shaped job runner for indexing, export, and retention."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    RETRY = "retry"
    DEAD = "dead"


@dataclass
class Job:
    job_id: str
    kind: str
    payload: dict[str, Any]
    checkpoint: int = 0
    attempts: int = 0
    status: JobStatus = JobStatus.QUEUED
    error: str = ""
    history: list[int] = field(default_factory=list)


class JobQueue:
    def __init__(self, max_attempts: int = 3) -> None:
        self.max_attempts = max_attempts
        self.jobs: dict[str, Job] = {}
        self.dead_letters: list[Job] = []

    def enqueue(self, job_id: str, kind: str, payload: dict[str, Any]) -> Job:
        if job_id in self.jobs:
            return self.jobs[job_id]
        job = Job(job_id, kind, payload)
        self.jobs[job_id] = job
        return job

    def run(self, job_id: str, worker: Callable[[Job], int | None]) -> Job:
        job = self.jobs[job_id]
        if job.status == JobStatus.COMPLETE:
            return job
        job.status = JobStatus.RUNNING
        job.attempts += 1
        try:
            next_checkpoint = worker(job)
            if next_checkpoint is not None:
                job.checkpoint = next_checkpoint
                job.history.append(next_checkpoint)
            job.status = JobStatus.COMPLETE
        except Exception as exc:  # a failed attempt is a persisted state transition
            job.error = str(exc)
            if job.attempts >= self.max_attempts:
                job.status = JobStatus.DEAD
                self.dead_letters.append(job)
            else:
                job.status = JobStatus.RETRY
        return job

    def retry(self, job_id: str) -> Job:
        job = self.jobs[job_id]
        if job.status == JobStatus.DEAD:
            job.status = JobStatus.RETRY
            job.attempts = 0
            job.error = ""
            if job in self.dead_letters:
                self.dead_letters.remove(job)
        return job
