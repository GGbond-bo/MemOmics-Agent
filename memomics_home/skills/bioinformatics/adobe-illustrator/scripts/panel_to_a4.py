# -*- coding: utf-8 -*-
"""panel_to_a4.py — 把 PDF/SVG 面板导入 Illustrator，放进 A4 上半区并规范字号。

配方来源：2026-10-05 `boxplot_16_O_ex (2).pdf` 实测（端到端 ×3 + PyMuPDF 复核）。
链路：open → artboard-set(A4) → bounds → move(all, 居中上半区) → 分组改字号
      → 标题居中 → text-list/bounds 复验 → export PNG/PDF → close-doc（不保存）。

约定（与 SKILL.md「面板导入配方」一致）：
  * 字号分组：最大字号帧 → 标题；`--annot-pattern` 命中 → 注释字号；其余 → 正文字号。
  * 所有布局数学用 bounds_screen（屏幕语义：x 距左，y 距顶）。
  * 绝不保存用户文档；只操作本脚本 open 出来的副本，收尾 close-doc --force。

用法：
  python panel_to_a4.py --pdf "D:/path/panel.pdf" --out "E:/out/dir"
  python panel_to_a4.py --pdf ... --out ... --title 7 --body 6 --annot 5 --annot-pattern "FDR="
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

A4_W, A4_H = 595.28, 841.89          # A4 纵向（pt）
SKILL_DIR = Path(__file__).resolve().parent.parent
BUNDLED = SKILL_DIR / "scripts" / "harness_bundle"
REPO_EXE = Path(r"E:\MemOmics-Agent\.venv\Scripts\cli-anything-illustrator.exe")


def resolve_exe() -> str:
    env = os.environ.get("CLI_ANYTHING_ILLUSTRATOR")
    if env and Path(env).exists():
        return env
    if REPO_EXE.exists():
        return str(REPO_EXE)
    which = shutil.which("cli-anything-illustrator")
    if which:
        return which
    # 自带快照（零安装回退）
    for cand in BUNDLED.rglob("__main__.py"):
        return f"{sys.executable} -m cli_anything.illustrator"
    raise SystemExit("找不到 cli-anything-illustrator（env / venv / PATH / 快照 均未命中）")


def run(exe: str, args: list[str]) -> dict:
    if exe.endswith("cli_anything.illustrator"):
        cmd = [sys.executable, "-m", "cli_anything.illustrator"] + args
        env = dict(os.environ)
        env["PYTHONPATH"] = str(BUNDLED) + os.pathsep + env.get("PYTHONPATH", "")
    else:
        cmd = [exe] + args
        env = None
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    t = (p.stdout or "").strip()
    s = t.find("{")
    d = json.loads(t[s:]) if s >= 0 else {}
    if p.returncode != 0 and not d:
        d = {"error": (p.stdout or p.stderr or "")[:200]}
    return d


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True, help="输入面板文件（.pdf/.svg/.ai）")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--title", type=float, default=7.0)
    ap.add_argument("--body", type=float, default=6.0)
    ap.add_argument("--annot", type=float, default=5.0)
    ap.add_argument("--annot-pattern", default="FDR=", help="注释帧匹配子串（大小写不敏感）")
    ap.add_argument("--title-pattern", default=None, help="标题帧匹配子串（默认=最大字号帧）")
    ap.add_argument("--keep-open", action="store_true", help="调试用：不关文档")
    a = ap.parse_args()

    exe = resolve_exe()
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    log = {"tool": "panel_to_a4", "exe": exe, "input": a.pdf, "out": out, "steps": []}
    print("harness:", exe)

    def rec(name, d, keys):
        log["steps"].append({"step": name, **{k: d.get(k) for k in keys}})
        print("-- %-18s %s" % (name, json.dumps({k: d.get(k) for k in keys}, ensure_ascii=False)[:180]))
        return d

    d = run(exe, ["--json", "open", a.pdf])
    rec("open", d, ["opened", "active_doc", "text_frame_count"])
    if not d.get("opened"):
        print("open 失败:", d)
        return 2

    d = run(exe, ["--json", "artboard-set", "--w", str(A4_W), "--h", str(A4_H)])
    rec("artboard-set", d, ["ok", "after"])

    d = run(exe, ["--json", "bounds"])
    b = d["bounds"]                              # 原生 [L,T,R,B]
    ab_top = (d.get("artboard_rect") or [0, 0, 0, 0])[1]
    cx, cy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
    dx = A4_W / 2.0 - cx
    dy = -((ab_top - A4_H / 4.0) - cy)           # 屏幕语义：正=向下
    rec("bounds", d, ["bounds", "bounds_screen"])

    d = run(exe, ["--json", "move", "--target", "all", "--dx", "%.2f" % dx, "--dy", "%.2f" % dy])
    rec("move all", d, ["ok", "moved", "nested_skipped"])

    d = run(exe, ["--json", "text-list"])
    items = d.get("items", [])
    if not items:
        print("警告：文档没有文字帧，跳过字号与标题步骤")
    else:
        title = None
        if a.title_pattern:
            title = next((x for x in items if a.title_pattern.lower() in x["contents"].lower()), None)
        if title is None:
            title = max(items, key=lambda x: float(x.get("size") or 0))
        annots = [x for x in items if a.annot_pattern.lower() in x["contents"].lower()]
        body = [x for x in items if x is not title and x not in annots]
        # 正文按"当前字号"分组批量改（--from-size），每组一次
        body_sizes = sorted({round(float(x["size"] or 0), 1) for x in body})
        for s in body_sizes:
            d = run(exe, ["--json", "text-set", "--from-size", str(s), "--size", str(a.body)])
            rec("text-set %s>%s" % (s, a.body), d, ["changed", "touched"])
        if annots:
            d = run(exe, ["--json", "text-set", "--pattern", a.annot_pattern,
                          "--size", str(a.annot)])
            rec("text-set annots", d, ["changed", "touched"])
        # 标题：字号 + 居中 + 水平居中
        d = run(exe, ["--json", "text-set", "--index", str(title["index"]),
                      "--size", str(a.title), "--align", "center"])
        rec("text-set title", d, ["changed", "touched", "align"])
        d = run(exe, ["--json", "text-list"])
        t2 = next((x for x in d.get("items", []) if x["contents"] == title["contents"]), None)
        if t2:
            tcx = (t2["bounds"][0] + t2["bounds"][2]) / 2.0
            d = run(exe, ["--json", "move", "--target", "text", "--index", str(t2["index"]),
                          "--dx", "%.2f" % (A4_W / 2.0 - tcx), "--dy", "0"])
            rec("title center", d, ["ok", "bounds"])

    d = run(exe, ["--json", "text-list"])
    hist = {}
    for x in d.get("items", []):
        k = round(float(x.get("size") or 0), 1)
        hist[k] = hist.get(k, 0) + 1
    log["size_histogram"] = hist
    rec("verify text", d, ["count"])

    d = run(exe, ["--json", "bounds"])
    bs = d.get("bounds_screen")
    half_ok = bool(bs and bs[3] <= A4_H / 2.0 + 1.0)
    log["top_half_ok"] = half_ok
    rec("verify bounds", d, ["bounds_screen"])

    png = os.path.join(out, "panel_A4_top.png")
    d = run(exe, ["--json", "export", png, "-f", "png", "--bg", "white"])
    rec("export png", d, ["exists", "bytes"])
    pdf = os.path.join(out, "panel_A4_top.pdf")
    d = run(exe, ["--json", "export", pdf, "-f", "pdf"])
    rec("export pdf", d, ["exists", "bytes"])
    if os.path.exists(png):
        log["png_sha256"] = sha256(png)
    if os.path.exists(pdf):
        log["pdf_sha256"] = sha256(pdf)

    if not a.keep_open:
        run(exe, ["--json", "close-doc", "--dry-run"])
        d = run(exe, ["--json", "close-doc", "--force"])
        rec("close-doc", d, ["closed", "docs_after"])
    d = run(exe, ["--json", "doctor"])
    rec("doctor", d, ["illustrator"])

    rep = os.path.join(out, "panel_to_a4_report.json")
    with open(rep, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    ok = half_ok and (hist.get(a.body, 0) >= 0)
    print("报告:", rep)
    print("VERDICT:", "PASS" if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())