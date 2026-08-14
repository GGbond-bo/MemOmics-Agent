# -*- coding: utf-8 -*-
"""refresh_lock.py — 生成/刷新依赖锁文件（批 C，2026-08-15）。

用法:
    python scripts/refresh_lock.py            # 从当前 Python 环境生成 requirements-lock.txt
    python scripts/refresh_lock.py --with-r   # 同时生成 R-packages.lock.txt（需 Rscript 可用）

- requirements-lock.txt : pip freeze 全量精确锁（pip install -r 即可完整复现环境）
- R-packages.lock.txt  : 已安装 R 包名+版本（复现环境参考）
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADER = (
    "# MemOmics-Agent 依赖锁文件（精确版本）\n"
    "# 由 scripts/refresh_lock.py 生成 — 不要手工编辑\n"
    "# 完整复现环境: pip install -r requirements-lock.txt\n"
    "# 生成时间: {ts}\n"
)

_EDITABLE = re.compile(r"^\s*(-e\s+|.*\.git@|.*@\s*https?://|.*@\s*file:)", re.IGNORECASE)


def lock_python() -> int:
    try:
        out = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True, text=True, timeout=180, encoding="utf-8",
        )
        if out.returncode != 0:
            print("[refresh_lock] pip freeze failed:", out.stderr[:300])
            return 1
    except FileNotFoundError:
        print("[refresh_lock] 当前解释器无 pip:", sys.executable)
        return 1
    lines = []
    for ln in out.stdout.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        if _EDITABLE.match(ln):
            continue  # editable/git 源依赖不锁
        lines.append(ln)
    from datetime import datetime
    target = ROOT / "requirements-lock.txt"
    target.write_text(
        HEADER.format(ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S")) + "\n".join(sorted(lines)) + "\n",
        encoding="utf-8",
    )
    print(f"[refresh_lock] 已写 {target} ({len(lines)} 个包)")
    return 0


def lock_r() -> int:
    rscript = "Rscript"
    try:
        r = subprocess.run(
            [rscript, "-e",
             'ip <- installed.packages(); writeLines(sprintf("%s==%s", ip[,1], ip[,3]), con=".rpack.tmp")'],
            capture_output=True, text=True, timeout=300, encoding="utf-8",
            cwd=str(ROOT),
        )
    except FileNotFoundError:
        print("[refresh_lock] Rscript 不在 PATH，跳过 R 锁（可先运行 R 环境）")
        return 0
    tmp = ROOT / ".rpack.tmp"
    if r.returncode != 0 or not tmp.is_file():
        print("[refresh_lock] R 锁生成失败:", (r.stderr or "")[:200])
        return 1
    pkgs = sorted(set(l.strip() for l in tmp.read_text(encoding="utf-8", errors="replace").splitlines() if "==" in l))
    tmp.unlink()
    from datetime import datetime
    (ROOT / "R-packages.lock.txt").write_text(
        HEADER.format(ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S")) + "\n".join(pkgs) + "\n",
        encoding="utf-8",
    )
    print(f"[refresh_lock] 已写 R-packages.lock.txt ({len(pkgs)} 个 R 包)")
    return 0


if __name__ == "__main__":
    rc = lock_python()
    if "--with-r" in sys.argv:
        rc |= lock_r()
    sys.exit(rc)
