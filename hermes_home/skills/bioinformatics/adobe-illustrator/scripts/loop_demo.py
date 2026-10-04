#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""loop_demo.py — Adobe Illustrator 全链路闭环演示（画 → 导出 → 清场）。

产出：<out>/r1.png（红矩形+40pt 标题）、r2.png（变绿+60pt）、r3.png（位移+加蓝字）、
      一份 sha256 摘要 JSON，以及"下一步看图"提示（vision_describe 在 MemOmics 会话里调）。

用法：
  python loop_demo.py --out D:\\scratch\\ai_demo
  python loop_demo.py --out .\\ai_demo --keep-open   # 跳过清场（调试；事后手动 close-untitled）
安全：只操作新建的「未标题-*」文档；结束自动 close-untitled（除非 --keep-open）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai  # noqa: E402 — 同目录统一入口


def jrun(args):
    rc, out, err = ai.run_capture(args)
    if rc != 0:
        raise SystemExit("命令失败 (rc=%d): %s\n%s\n%s" % (rc, " ".join(args), out, err))
    text = out.strip()
    start = text.find("{")
    return json.loads(text[start:]) if start >= 0 else {}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def export_step(out, name):
    path = os.path.join(out, name)
    r = jrun(["--json", "export", path, "-f", "png", "--bg", "white"])
    return {"cmd": "export %s" % name, "bytes": r.get("bytes"), "sha256": sha256(path)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="输出目录（PNG + 摘要）")
    ap.add_argument("--width", type=float, default=800)
    ap.add_argument("--height", type=float, default=600)
    ap.add_argument("--keep-open", action="store_true", help="跳过 close-untitled")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    summary = {"tool": "adobe-illustrator / loop_demo", "out": out, "steps": []}

    doc0 = jrun(["--json", "doctor"])
    summary["doctor_before"] = doc0.get("illustrator", doc0)
    if (doc0.get("illustrator") or {}).get("doc_count"):
        print("[warn] Illustrator 里已有打开的文档；本演示只新建/关闭自己的「未标题-*」，不碰其它文档。")

    try:
        r = jrun(["--json", "new-doc", "--width", str(args.width), "--height", str(args.height)])
        summary["steps"].append({"cmd": "new-doc", "doc_count": r.get("doc_count"),
                                 "artboard_rect": r.get("artboard_rect")})

        r = jrun(["--json", "rect", "--x", "60", "--y", "60", "--w", "300", "--h", "180",
                  "--color", "#e04040"])
        summary["steps"].append({"cmd": "rect", "bounds": r.get("bounds"), "fill": r.get("fill")})

        r = jrun(["--json", "text-add", "--content", "闭环演示 第1轮", "--x", "70", "--y", "300",
                  "--size", "40"])
        summary["steps"].append({"cmd": "text-add", "size": r.get("size"), "fill": r.get("fill")})

        summary["steps"].append(export_step(out, "r1.png"))

        r = jrun(["--json", "recolor", "--color", "#00aa55", "--index", "0"])
        summary["steps"].append({"cmd": "recolor", "changed": r.get("changed"), "fill": r.get("fill")})
        r = jrun(["--json", "text-set", "--size", "60"])
        summary["steps"].append({"cmd": "text-set", "changed": r.get("changed"), "size": r.get("size")})

        summary["steps"].append(export_step(out, "r2.png"))

        r = jrun(["--json", "move", "--index", "0", "--dx", "200", "--dy", "120"])
        summary["steps"].append({"cmd": "move", "bounds": r.get("bounds")})
        r = jrun(["--json", "text-add", "--content", "第3轮新增：看图后调整", "--x", "260",
                  "--y", "420", "--size", "28", "--color", "#0044cc"])
        summary["steps"].append({"cmd": "text-add#2", "size": r.get("size")})

        summary["steps"].append(export_step(out, "r3.png"))

        r = jrun(["--json", "items"])
        summary["items"] = {"pathitems": r.get("pathitems_count"),
                            "textframes": r.get("textframes_count")}
    finally:
        if not args.keep_open:
            r = jrun(["--json", "close-untitled"])
            summary["cleanup"] = {"closed": r.get("closed"), "docs_after": r.get("docs_after")}
        doc1 = jrun(["--json", "doctor"])
        summary["doctor_after"] = doc1.get("illustrator", doc1)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print()
    print("下一步（看图；在 MemOmics 会话里调）：")
    for name in ("r1.png", "r2.png", "r3.png"):
        print('  vision_describe(image_path=r"%s", question="OCR 读出什么？主色有哪些？")'
              % os.path.join(out, name))
    return 0


if __name__ == "__main__":
    sys.exit(main())