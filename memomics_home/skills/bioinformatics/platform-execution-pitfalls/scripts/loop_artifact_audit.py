#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""loop_artifact_audit.py —— 闭环 before/after 图的硬证据审计 + 产物清单

用途：
  对"看图找茬→修复→复看"闭环产出的 PNG 做**不依赖 OCR 的**客观核验，并落
  artifact_manifest.json（带 role / expected_blank / sha256 / 像素计数），
  用于抵御 rail_review(post) 对"刻意缺陷态对照图"的假阳性（<5KB=疑似空白）。

为什么需要：
  rail_review 的「图片太小(<5KB)=疑似空白，必须重新生成」判据面向交付图(after)，
  遇到刻意造出的 before 缺陷图（如白字白底）必然误判；重生成会摧毁 before/after
  差分基线。本脚本给出可复核证据 + 角色标签，让复核者按 role 区分"物证"与"交付图"。

用法：
  python loop_artifact_audit.py --dir <outdir> \
      --pair loop_B_v1.png:before_negative_control loop_B_v2.png:after_deliverable \
      --box 60,86,348,146 [--box-auto v2] [--no-manifest]

  --box      文本/目标区域 PIL box "x0,y0,x1,y1"（屏幕坐标，y 向下）
  --box-auto <file> 用该文件的非背景像素自动框定区域（不知坐标时用）
  --dark-threshold  暗像素阈值，默认 100

坐标换算（图形软件 bounds 多为 y 向上，导出 PNG y 向下）：
  screen_y_top = artboard_height - bounds[1]
  screen_y_bot = artboard_height - bounds[3]
  box = (x0, screen_y_top - pad, x1, screen_y_bot + pad)   # pad≈5

退出码：0 = 全部 PNG 有效且被审计；2 = 有文件缺失/非有效 PNG（此时不要声称"图是坏的"，
        先看是否路径写错——"No result files"类假警告多由路径/cwd 口径造成）。
"""
import argparse
import hashlib
import json
import os
import sys

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("需要 Pillow：<项目venv>/Scripts/python.exe -m pip install Pillow")


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def audit_one(path, role, box=None, dark_threshold=100):
    """返回单张 PNG 的事实清单；`valid=False` 表示文件缺失/非有效 PNG。"""
    rec = {"file": os.path.basename(path), "role": role,
           "expected_blank": role == "before_negative_control", "path": os.path.abspath(path)}
    if not os.path.exists(path):
        rec.update(valid=False, error="file not found")
        return rec
    try:
        with Image.open(path) as im:
            im.verify()                      # 完整性校验（不消耗句柄）
            w, h = im.size
            fmt = im.format
        gray = Image.open(path).convert("L")
    except Exception as exc:                 # 非有效 PNG
        rec.update(valid=False, error=f"invalid PNG: {exc}",
                   bytes=os.path.getsize(path))
        return rec

    rec.update(valid=True, bytes=os.path.getsize(path), size=[w, h],
               png_verify="OK", png_format=fmt, sha256=file_sha256(path))

    if box:
        x0, y0, x1, y1 = box
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(w, x1), min(h, y1)
        px = list(gray.crop((x0, y0, x1, y1)).getdata())
        dark = sum(1 for v in px if v < dark_threshold)
        rec.update(box=[x0, y0, x1, y1], box_px=len(px), dark_px=dark,
                   dark_ratio=round(dark / len(px), 4) if px else 0.0)
    # 全图非背景占比：与"疑似空白"判据对齐（不只看体积）
    allpx = list(gray.getdata())
    bg = max(set(allpx), key=allpx.count)
    nonbg = sum(1 for v in allpx if abs(v - bg) > 8)
    rec.update(bg_gray=bg, non_bg_ratio=round(nonbg / len(allpx), 4))
    return rec


def auto_box(path, dark_threshold=100, pad=6):
    """按非背景像素自动框定目标区域（不知道 bounds 时用）。"""
    gray = Image.open(path).convert("L")
    w, h = gray.size
    px = gray.load()
    allv = list(gray.getdata())
    bg = max(set(allv), key=allv.count)
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            if abs(px[x, y] - bg) > 40:
                xs.append(x); ys.append(y)
    if not xs:
        return None
    return (max(0, min(xs) - pad), max(0, min(ys) - pad),
            min(w, max(xs) + pad), min(h, max(ys) + pad))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="产物目录")
    ap.add_argument("--pair", nargs="+", required=True,
                    help="file:role 列表，如 loop_B_v1.png:before_negative_control")
    ap.add_argument("--box", default="", help='PIL box "x0,y0,x1,y1"（屏幕坐标）')
    ap.add_argument("--box-from", default="", help="用该文件名自动推导 box（按非背景像素）")
    ap.add_argument("--dark-threshold", type=int, default=100)
    ap.add_argument("--name", default="artifact_manifest.json")
    ap.add_argument("--no-manifest", action="store_true")
    args = ap.parse_args()

    box = None
    if args.box:
        box = tuple(int(v) for v in args.box.split(","))
    elif args.box_from:
        p = os.path.join(args.dir, args.box_from)
        if os.path.exists(p):
            box = auto_box(p, args.dark_threshold)
            print(f"[auto-box] {args.box_from} -> {box}")

    arts, bad = [], 0
    for item in args.pair:
        name, _, role = item.partition(":")
        rec = audit_one(os.path.join(args.dir, name), role or "unspecified",
                        box=box, dark_threshold=args.dark_threshold)
        if not rec.get("valid"):
            bad += 1
        arts.append(rec)

    man = {"test": os.path.basename(os.path.abspath(args.dir)),
           "generator": "loop_artifact_audit.py",
           "doc_saved": False,
           "artifacts": arts}
    print(json.dumps(man, ensure_ascii=False, indent=2))

    if not args.no_manifest:
        out = os.path.join(args.dir, args.name)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(man, f, ensure_ascii=False, indent=2)
        print(f"\n[manifest] {os.path.abspath(out)}")
    print("\n[提示] before_negative_control 是刻意缺陷物证，禁止重生成/覆盖；"
          "dark_ratio 由 0 → 显著>0 即修复被像素证据确认。")
    return 2 if bad else 0


if __name__ == "__main__":
    sys.exit(main())