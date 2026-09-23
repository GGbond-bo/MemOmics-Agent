"""Small, dependency-free security helpers for WebUI filesystem access.

P2-3：路径判定在保留原有语义的前提下多挂了一层 SandboxProvider。
默认是**观察模式**——沙箱照常判定、照常记账，但不拦人，老行为一个字节都不变；
显式设置 MEMOMICS_SANDBOX_ENFORCE=1 之后，沙箱拒绝的路径会转成 UnsafePathError
（调用方捕获的异常类型不变，所以对上层仍然只是"这个路径不允许"）。
沙箱自身的任何异常都被吞掉：安全组件宁可少拦，也绝不能把正常读写打挂。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


class UnsafePathError(ValueError):
    """Raised when a user supplied path escapes its allowed root."""


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _sandbox_gate(action: str, path: Any, roots: Iterable[str | Path]) -> None:
    """把一次路径判定交给沙箱（观察模式只记账；强制模式会抛 UnsafePathError）。"""
    try:
        from webui import sandbox as _sandbox
        decision = _sandbox.gate(action, str(path), roots=[str(r) for r in roots],
                                 source="security.resolve_within_roots")
        if decision.blocked:
            raise UnsafePathError("sandbox denied: %s (%s)" % (decision.code, decision.reason))
    except UnsafePathError:
        raise
    except Exception:
        pass          # 沙箱坏了也绝不影响老的读写路径


def resolve_within_roots(path: str | Path, roots: Iterable[str | Path],
                         action: str = "fs.read") -> Path:
    """Resolve *path* and require it to be contained by one of *roots*.

    ``Path.relative_to`` is deliberately used instead of string ``startswith``;
    the latter treats sibling paths such as ``results-old`` as children of
    ``results`` and is unsafe on Windows path boundaries.
    """
    candidate = _resolved(path)
    _sandbox_gate(action, candidate, roots)
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
