"""Persistent registry for reference genomes and analysis databases."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from webui.security import resolve_within_roots


class ReferenceRegistry:
    def __init__(self, path: str | Path, allowed_roots) -> None:
        self.path = Path(path)
        self.allowed_roots = tuple(Path(item).resolve() for item in allowed_roots)
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.is_file():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload.get("references", {}) if isinstance(payload, dict) else {}

    def _write(self, records: dict[str, dict[str, Any]]) -> None:
        fd, temporary = tempfile.mkstemp(prefix="references-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"schema_version": 1, "references": records}, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def register(self, name: str, kind: str, path: str, *, version: str = "", organism: str = "") -> dict[str, Any]:
        if not name or not name.replace("-", "_").replace(".", "_").isalnum():
            raise ValueError("Invalid reference name")
        if kind not in {"genome", "annotation", "transcriptome", "index", "database"}:
            raise ValueError("Unsupported reference kind")
        resolved = resolve_within_roots(path, self.allowed_roots)
        if not resolved.exists():
            raise ValueError("Reference path does not exist")
        stat = resolved.stat()
        record = {
            "name": name,
            "kind": kind,
            "path": str(resolved),
            "version": version,
            "organism": organism,
            "size_bytes": stat.st_size if resolved.is_file() else None,
            "modified_ns": stat.st_mtime_ns,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            records = self._load()
            records[name] = record
            self._write(records)
        return record

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            records = self._load()
        result = []
        for record in records.values():
            item = dict(record)
            item["available"] = Path(item["path"]).exists()
            result.append(item)
        return sorted(result, key=lambda item: item["name"].lower())

    def remove(self, name: str) -> bool:
        with self._lock:
            records = self._load()
            removed = records.pop(name, None) is not None
            if removed:
                self._write(records)
            return removed
