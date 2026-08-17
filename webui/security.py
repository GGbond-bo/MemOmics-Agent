"""Small, dependency-free security helpers for WebUI filesystem access."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


class UnsafePathError(ValueError):
    """Raised when a user supplied path escapes its allowed root."""


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def resolve_within_roots(path: str | Path, roots: Iterable[str | Path]) -> Path:
    """Resolve *path* and require it to be contained by one of *roots*.

    ``Path.relative_to`` is deliberately used instead of string ``startswith``;
    the latter treats sibling paths such as ``results-old`` as children of
    ``results`` and is unsafe on Windows path boundaries.
    """
    candidate = _resolved(path)
    for root in roots:
        resolved_root = _resolved(root)
        try:
            candidate.relative_to(resolved_root)
            return candidate
        except ValueError:
            continue
    raise UnsafePathError(f"Path is outside the allowed roots: {candidate}")


def resolve_relative_path(root: str | Path, relative_path: str | Path = "") -> Path:
    """Resolve an untrusted relative path below a single trusted root."""
    supplied = Path(relative_path)
    if supplied.is_absolute():
        raise UnsafePathError("Absolute paths are not allowed")
    return resolve_within_roots(_resolved(root) / supplied, [root])
