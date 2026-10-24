#!/usr/bin/env python
"""Pixel-level color audit for exported PNGs — the tie-breaker for "is this
color actually in the image?".

WHY THIS EXISTS (measured 2026-10-04, Illustrator COM harness / 3-round loop):
  The local vision pipeline (vision_describe) reports a *top-N by area* palette.
  A 28pt blue caption covering 0.435% of an 800x600 canvas never entered the
  top-5 list, and the palette's colors are quantized clusters (it printed
  #00a040 while the document's exact fill was #00aa55). Reading "absent from the
  palette" as "color missing" is a false negative. This script answers the
  ground-truth question directly from the pixels.

USAGE
  python verify_png_colors.py out/loop_A_r3.png --core 0044cc:blue --core 00aa55:green
  python verify_png_colors.py out/*.png                 # sha256 + cluster table only
  python verify_png_colors.py out/*.png --core 0044cc:blue --tol 12 --top 8

OUTPUT per file:
  sha256 (first 16) | bytes | mode | WxH
  for each --core : exact px, near(+-tol) px, pct, bbox     <- use THIS to judge presence
  chromatic (saturation>40) cluster top-N: hex + px + pct   <- what the viewer actually sees

Exit code 0 = every --core color present (exact or near); 1 = some color missing
(usable as a pass/fail gate inside a closed loop). Requires Pillow only.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import os
import sys

from PIL import Image


def audit(path: str, cores: list[tuple[str, str]], tol: int, top: int) -> bool:
    raw = open(path, "rb").read()
    im = Image.open(path)
    rgb = im.convert("RGB")
    buf, w, h = rgb.tobytes(), rgb.size[0], rgb.size[1]
    n = w * h
    print(
        f"== {os.path.basename(path)}  sha256={hashlib.sha256(raw).hexdigest()[:16]}"
        f"  bytes={len(raw)}  mode={im.mode}  size={w}x{h}  info_keys={list(im.info)}"
    )

    ok = True
    for hexcode, label in cores:
        cr, cg, cb = (int(hexcode[i : i + 2], 16) for i in (0, 2, 4))
        exact = near = 0
        xs: list[int] = []
        ys: list[int] = []
        for i in range(0, len(buf), 3):
            r, g, b = buf[i], buf[i + 1], buf[i + 2]
            if abs(r - cr) <= tol and abs(g - cg) <= tol and abs(b - cb) <= tol:
                near += 1
                if (r, g, b) == (cr, cg, cb):
                    exact += 1
                px = i // 3
                xs.append(px % w)
                ys.append(px // w)
        bbox = f"x{min(xs)}-{max(xs)} y{min(ys)}-{max(ys)}" if xs else "—"
        if not near:
            ok = False
        print(
            f"   [{'OK' if near else 'MISSING':7s}] {label:8s} #{hexcode}"
            f"  exact={exact}  near(+-{tol})={near}  ({near / n * 100:.3f}%)  bbox={bbox}"
        )

    cnt: collections.Counter[tuple[int, int, int]] = collections.Counter()
    chroma = 0
    for i in range(0, len(buf), 3):
        px = (buf[i], buf[i + 1], buf[i + 2])
        if max(px) - min(px) > 40:
            cnt[px] += 1
            chroma += 1
    print(f"   chromatic_px={chroma} ({chroma / n * 100:.3f}%)  top{top} clusters:")
    for px, c in cnt.most_common(top):
        print(f"      #{px[0]:02x}{px[1]:02x}{px[2]:02x}  {c:7d}  {c / n * 100:.3f}%")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("png", nargs="+", help="PNG file(s) to audit")
    ap.add_argument(
        "--core",
        action="append",
        default=[],
        metavar="RRGGBB[:label]",
        help="exact core color to test for presence (repeatable)",
    )
    ap.add_argument("--tol", type=int, default=12, help="per-channel tolerance (default 12)")
    ap.add_argument("--top", type=int, default=8, help="chromatic clusters to list (default 8)")
    a = ap.parse_args()

    cores: list[tuple[str, str]] = []
    for spec in a.core:
        hexcode, _, label = spec.partition(":")
        hexcode = hexcode.lstrip("#").lower()
        if len(hexcode) != 6:
            print(f"bad --core value: {spec}", file=sys.stderr)
            return 2
        cores.append((hexcode, label or hexcode))

    return 0 if all(audit(p, cores, a.tol, a.top) for p in a.png) else 1


if __name__ == "__main__":
    raise SystemExit(main())