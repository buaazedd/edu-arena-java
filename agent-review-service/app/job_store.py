from __future__ import annotations

from datetime import datetime
from threading import Lock
from typing import Dict, Optional

from app.models import ReviewJobRequest, ReviewResult, ReviewStatus


class JobStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._requests: Dict[str, ReviewJobRequest] = {}
        self._results: Dict[str, ReviewResult] = {}
        self._status: Dict[str, ReviewStatus] = {}
        self._error: Dict[str, str] = {}

    def create_job(self, job_id: str, req: ReviewJobRequest) -> None:
        with self._lock:
            self._requests[job_id] = req
            self._status[job_id] = ReviewStatus.QUEUED

    def mark_completed(self, result: ReviewResult) -> None:
        with self._lock:
            self._results[result.jobId] = result
            self._status[result.jobId] = ReviewStatus.COMPLETED

    def mark_failed(self, job_id: str, message: str) -> None:
        with self._lock:
            self._status[job_id] = ReviewStatus.FAILED
            self._error[job_id] = message

    def get_status(self, job_id: str) -> Optional[ReviewStatus]:
        with self._lock:
            return self._status.get(job_id)

    def get_result(self, job_id: str) -> Optional[ReviewResult]:
        with self._lock:
            return self._results.get(job_id)

    def get_error(self, job_id: str) -> Optional[str]:
        with self._lock:
            return self._error.get(job_id)


job_store = JobStore()
