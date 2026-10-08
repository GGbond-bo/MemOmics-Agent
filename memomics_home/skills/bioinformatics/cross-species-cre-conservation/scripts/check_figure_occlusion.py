# -*- coding: utf-8 -*-
"""
附图体检（交付前）：边缘裁切检测 + 文字框遮挡检测。

用法:
    python check_figure_occlusion.py <图片目录> [--min-overlap 0.15]

输出:
    [裁切] 每张图最外 2px 边框上的非白像素数（>0 = 内容被切出画布）
    [遮挡] 交叠占较小框 > min-overlap 的文本框对

⚠️ 假阳性判读（必读）:
    同一个 y 轴刻度标签的"两行文字"（如 '本方法' + '(主-参考非对称)'）
    OCR 边界框天然交叠 17~20%，但 IoU 仅 0.07~0.09 —— 这不是遮挡。
    判据: IoU < 0.1 且两文本同属一个标签 → 忽略。
    其余命中必须用 crop-zoom 放大 3x 重 OCR 复核后再定性（见
    references/deliverable-consistency-and-figure-qa.md 步骤 3）。
"""
import argparse
import glob
import itertools
import os
import sys

import numpy as np
from PIL import Image


def edge_clip_report(path):
    im = Image.open(path).convert('RGB')
    a = np.array(im)
    h, w, _ = a.shape
    nonwhite = (a.min(axis=2) < 235)
    return {
        'size': f'{w}x{h}',
        'ink_frac': round(float(nonwhite.sum()) / (h * w), 4),
        'top': int(nonwhite[0:2, :].sum()),
        'bottom': int(nonwhite[-2:, :].sum()),
        'left': int(nonwhite[:, 0:2].sum()),
        'right': int(nonwhite[:, -2:].sum()),
    }


def bbox(box):
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return min(xs), min(ys), max(xs), max(ys)


def overlap(b1, b2):
    """返回 (占较小框的比例, IoU)"""
    x1 = max(b1[0], b2[0]); y1 = max(b1[1], b2[1])
    x2 = min(b1[2], b2[2]); y2 = min(b1[3], b2[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0, 0.0
    inter = (x2 - x1) * (y2 - y1)
    a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    return inter / min(a1, a2), inter / (a1 + a2 - inter)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('figdir')
    ap.add_argument('--min-overlap', type=float, default=0.15)
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.figdir, '*.png')))
    if not files:
        print('未找到 PNG'); return 2

    print('=' * 62)
    print('步骤 1 · 边缘裁切检测（非白像素触边 > 0 ⇒ 内容被切出画布）')
    print('=' * 62)
    clipped = []
    for f in files:
        r = edge_clip_report(f)
        flag = any(r[k] for k in ('top', 'bottom', 'left', 'right'))
        if flag:
            clipped.append(f)
        print(f"  {os.path.basename(f):32s} {r['size']:>11s} 墨占比={r['ink_frac']:.4f} "
              f"触边: 上{r['top']} 下{r['bottom']} 左{r['left']} 右{r['right']}"
              f"{'  ⚠️ 疑似裁切' if flag else ''}")
    print(f"  -> 疑似裁切图: {len(clipped)}/{len(files)}")

    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        print('\n[跳过遮挡检测] 未安装 rapidocr_onnxruntime（pip install rapidocr_onnxruntime）')
        return 0

    engine = RapidOCR()
    print()
    print('=' * 62)
    print(f'步骤 2 · 文字框遮挡检测（交叠占较小框 > {args.min_overlap:.0%}）')
    print('=' * 62)
    for f in files:
        res, _ = engine(f)
        if not res:
            print(f'  {os.path.basename(f)}: OCR 无结果')
            continue
        items = [(bbox(b), t) for b, t, s in res]
        hits = []
        for (b1, t1), (b2, t2) in itertools.combinations(items, 2):
            ratio, iou = overlap(b1, b2)
            if ratio > args.min_overlap:
                hits.append((ratio, iou, t1, t2))
        print(f'\n  {os.path.basename(f)} : {len(items)} 个文本框')
        if not hits:
            print('    -> 无相交命中 ✓')
            continue
        for ratio, iou, t1, t2 in sorted(hits, reverse=True):
            verdict = '（疑似同一标签两行，IoU<0.1 → 通常非遮挡，需 crop 复核）' if iou < 0.10 else '⚠️ 需 crop-zoom 复核'
            print(f'    [相交] "{t1}" × "{t2}"  占小框 {ratio:.0%}  IoU={iou:.2f}  {verdict}')
    print('\n提醒：命中项必须放大 3x 重 OCR 复核后再定性；报告图内文字错误前，'
          '先用同字体重渲染同一字符串做 OCR 反证。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
