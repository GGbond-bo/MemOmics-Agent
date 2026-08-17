"""Durable supervised-job ledger with crash/interruption recovery."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    """Atomically persist bounded job history and recover unclean shutdowns."""

    LIVE_STATES = frozenset({"running", "cancelling"})

    def __init__(self, path: str | Path, *, history_limit: int = 1000) -> None:
        self.path = Path(path)
        self.history_limit = max(10, int(history_limit))
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records = self._load()
        self.recover_interrupted()

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        records = payload.get("jobs", []) if isinstance(payload, dict) else []
        return [dict(item) for item in records if isinstance(item, dict)]

    def _write(self) -> None:
        fd, temporary = tempfile.mkstemp(prefix="jobs-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    {"schema_version": 1, "jobs": self._records[-self.history_limit :]},
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def start(self, session_id: str, label: str) -> dict[str, Any]:
        record = {
            "job_id": f"job-{uuid.uuid4().hex[:16]}",
            "session_id": session_id,
            "label": label,
            "state": "running",
            "created_at": _now(),
            "finished_at": None,
            "error": None,
            "termination_source": None,
        }
        with self._lock:
            self._records.append(record)
            self._records[:] = self._records[-self.history_limit :]
            self._write()
        return dict(record)

    def finish(self, job_id: str, state: str, *, error: str | None = None,
               termination_source: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            record = next(
                (item for item in reversed(self._records) if item.get("job_id") == job_id),
                None,
            )
            if record is None:
                return None
            record.update(
                state=state,
                finished_at=_now(),
                error=error,
                termination_source=termination_source,
            )
            self._write()
            return dict(record)

    def recover_interrupted(self) -> int:
        recovered = 0
        with self._lock:
            for record in self._records:
                if record.get("state") in self.LIVE_STATES:
                    record.update(
                        state="interrupted",
                        finished_at=_now(),
                        error="MemOmics stopped before the task reached a terminal state",
                        termination_source="runtime_restart",
                    )
                    recovered += 1
            if recovered:
                self._write()
        return recovered

    def list(self, *, session_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            records = self._records
            if session_id:
                records = [item for item in records if item.get("session_id") == session_id]
            return [dict(item) for item in records[-max(1, limit) :]]
