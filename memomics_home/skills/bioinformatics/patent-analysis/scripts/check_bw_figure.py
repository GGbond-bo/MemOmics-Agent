#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""黑白附图合规 + 可读性探针（patent-analysis skill）

用途：出完黑白线条版专利附图后一次跑完，回答三个问题
  1. 是否真的纯黑白（《审查指南》2.4「不得着色」）→ 彩色像素占比必须 0.0000%
  2. 墨迹密度（非白像素占比）→ 作为「去填充图案前后」的对照指标，应下降
  3. 尺寸是否偏小 → 入 docx 被压到 ~850 px 时的可读性风险提示

用法：
    python check_bw_figure.py <a.png> [b.png ...]
    python check_bw_figure.py --dir E:/专利/patent/figures_bw
    python check_bw_figure.py --dir <目录> --baseline 18.6     # 给出去图案前的墨迹占比做对照

依赖：PIL + numpy（无需 matplotlib）
"""
import argparse
import glob
import os
import sys

import numpy as np
from PIL import Image

COLOR_TOL = 6        # |max-min| 超过该值即视为「有颜色」
INK_THRESH = 720     # R+G+B < 该值算「非白」（墨）


def probe(path, baseline=None):
    im = Image.open(path)
    mode, size = im.mode, im.size
    a = np.asarray(im.convert('RGB')).astype(int)
    colored = float(((a.max(2) - a.min(2)) > COLOR_TOL).mean() * 100)
    ink = float((a.sum(2) < INK_THRESH).mean() * 100)
    name = os.path.basename(path)
    flag = 'OK ' if colored == 0 else '❌ '
    line = ('%s%-42s %-10s %8d B  彩色像素 %6.4f%%  墨迹 %5.2f%%'
            % (flag, name, '%dx%d' % size, os.path.getsize(path), colored, ink))
    if baseline is not None:
        line += '  (去图案前 %.2f%% → %+.2f pp)' % (baseline, ink - baseline)
    print(line)
    warn = []
    if colored > 0:
        warn.append('不合规：含彩色像素，专利附图必须纯黑白')
    if size[0] < 1500:
        warn.append('图宽 %d px 偏小，入 docx 缩印后可读性风险（框内正文需 ≥9 pt）' % size[0])
    if ink > 30:
        warn.append('墨迹 %.1f%% 偏高，疑似仍有密集填充图案/网格' % ink)
    for w in warn:
        print('     ⚠️ ' + w)
    return colored, ink


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='*', help='PNG 路径（可多个）')
    ap.add_argument('--dir', help='目录：自动收集其下 *.png')
    ap.add_argument('--baseline', type=float, default=None,
                    help='去图案前的墨迹占比（%%），给出则打前后对照')
    args = ap.parse_args()

    paths = list(args.paths)
    if args.dir:
        paths += sorted(glob.glob(os.path.join(args.dir, '*.png')))
    if not paths:
        print('未指定图片：用法 python check_bw_figure.py --dir <目录>'); return 2

    print('黑白附图探针 · 彩色像素必须 0.0000%\n')
    bad = 0
    for p in paths:
        if not os.path.exists(p):
            print('❌ 不存在:', p); bad += 1; continue
        c, _ = probe(p, args.baseline)
        if c > 0:
            bad += 1
    print('\n结果: %d 张，%d 张不合格' % (len(paths), bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
