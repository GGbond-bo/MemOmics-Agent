#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""D3 · 自动 PTR 检查器（零人工）——对任意 agent 产物目录输出「过程可追溯率」。

设计依据：`plans/closed-loop-agent-roadmap-20261012.md` §3.3（协议冻结口径）
  五要件 = 数据版本 / 代码 / 参数 / 环境 / 日志，各 0.2 分，全有 = 1.0。
  PTR ≥0.90 为该设计的通过线；缺哪一件会在 missing 里给出补救提示。

用法：
    python scripts/check_ptr.py <results_dir> [more_dirs...] [--json] [--out FILE] [--min-score 0.9]
    python scripts/check_ptr.py --glob "results/memomics-*" --json --out ptr_all.json

退出码：0 = 全部达到 --min-score；1 = 有目录未达标；2 = 用法/路径错误。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _load():
    from memomics.bio_tools.claim_ledger import ptr_report   # noqa: WPS433
    return ptr_report


def _fmt_one(rep: dict) -> str:
    lines = [f"PTR {rep.get('score'):.2f}  {rep.get('verdict'):<7} {rep.get('results_dir')}"]
    for k, c in (rep.get("checks") or {}).items():
        mark = "[ok]  " if c.get("ok") else "[MISS]"     # 用 ASCII 标记：GBK 控制台不会因 emoji 崩
        detail = ""
        if k == "code" and c.get("detail"):
            d = c["detail"]
            detail = f"{len(d.get('scripts') or [])} 个脚本 · commit {d.get('repo_commit') or '-'}"
        elif k == "data_version" and c.get("detail"):
            detail = f"{len(c['detail'])} 个数据文件"
        elif k == "logs" and c.get("detail"):
            detail = f"{len(c['detail'])} 个日志"
        elif k == "params" and c.get("detail"):
            detail = f"来源 {c['detail'].get('source')}"
        elif k == "env" and c.get("detail"):
            detail = f"来源 {c['detail'].get('source')}"
        lines.append(f"   {mark} {k:<13} {detail}")
    for m in (rep.get("missing") or []):
        lines.append(f"   · {m}")
    return "\n".join(lines)


def main(argv=None) -> int:
    # Windows 中文控制台默认 GBK：显式把 stdout 切 UTF-8 + replace，避免 benchmarker 管道里报错
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="MemOmics PTR（过程可追溯）检查器")
    ap.add_argument("dirs", nargs="*", help="results 目录（可多个）")
    ap.add_argument("--glob", default="", help="用通配符批量选目录，如 'results/memomics-*'")
    ap.add_argument("--json", action="store_true", help="输出 JSON（给 benchmarker 吃）")
    ap.add_argument("--out", default="", help="把 JSON 写到文件")
    ap.add_argument("--min-score", type=float, default=0.9, help="通过线（默认 0.9）")
    args = ap.parse_args(argv)

    targets = list(args.dirs)
    if args.glob:
        targets.extend(sorted(p for p in glob.glob(args.glob) if os.path.isdir(p)))
    targets = [os.path.abspath(p) for p in targets if os.path.isdir(p)]
    if not targets:
        print(__doc__.strip().splitlines()[0])
        print("错误：没有可检查的目录（给 <results_dir> 或 --glob）", file=sys.stderr)
        return 2

    ptr_report = _load()
    reports = []
    for d in targets:
        try:
            reports.append(ptr_report(d))
        except Exception as exc:      # 单个目录失败不影响其它
            reports.append({"results_dir": d.replace("\\", "/"), "score": 0.0,
                            "verdict": "error", "error": str(exc)[:200], "checks": {}, "missing": []})

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"schema": "memomics.ptr_batch.v1", "min_score": args.min_score,
                       "reports": reports}, f, ensure_ascii=False, indent=2)
    if args.json:
        print(json.dumps({"min_score": args.min_score, "reports": reports}, ensure_ascii=False, indent=2))
    else:
        for r in reports:
            print(_fmt_one(r))
            print()
        ok = sum(1 for r in reports if float(r.get("score") or 0) >= args.min_score)
        print(f"达标 {ok}/{len(reports)}（通过线 {args.min_score}）")
        if args.out:
            print(f"JSON 已写入：{args.out}")

    return 0 if all(float(r.get("score") or 0) >= args.min_score for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())