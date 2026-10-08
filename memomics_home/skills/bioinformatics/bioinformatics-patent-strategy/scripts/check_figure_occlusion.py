#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""附图质检探针：遮挡 / 边缘裁切 / 空白 / 关键标签命中 / docx 内嵌图与磁盘图一致性。

用法
----
# 1) 单图质检（推荐：把你期望图上出现的数值标签全列出来）
python check_figure_occlusion.py fig_three_baseline_comparison.png \
       --expect "58.7%" "827/1409" "60.1%" "34.2%" "52.2%"

# 2) 整套图批量质检
python check_figure_occlusion.py --dir E:/专利/patent/figures --expect "357" "16"

# 3) 核验 docx 内嵌图 == 磁盘源图（SHA256 逐字节）
python check_figure_occlusion.py --docx 技术交底书_v12.docx \
       --figdir E:/专利/patent/figures \
       --order fig_pipeline_v10.png fig_permutation_null.png \
               fig_core_elements_357.png fig_three_baseline_comparison.png \
               fig_unified_grid_pertile_gate.png

退出码：0 = 全部通过；1 = 有 FAIL（可直接接进 CI 式验证脚本）。

依赖：Pillow + rapidocr_onnxruntime（缺 OCR 时自动降级为仅做边缘/空白检查）。
"""
import argparse
import hashlib
import itertools
import os
import sys

# ─────────────────────────── 基础图像工具 ───────────────────────────

def _load(path):
    from PIL import Image
    return Image.open(path)


def edge_crop_check(img, margin=2, white_thresh=245):
    """非白像素是否触碰到画布边缘 → 内容被裁出画布。"""
    w, h = img.size
    px = img.convert("L").load()
    hits = {"top": 0, "bottom": 0, "left": 0, "right": 0}
    for x in range(w):
        for y in list(range(margin)) + list(range(h - margin, h)):
            if px[x, y] < white_thresh:
                hits["top" if y < margin else "bottom"] += 1
    for y in range(h):
        for x in list(range(margin)) + list(range(w - margin, w)):
            if px[x, y] < white_thresh:
                hits["left" if x < margin else "right"] += 1
    return hits


def blank_check(img, white_thresh=245):
    """近白像素占比；1.0 = 全白（历史失败出图）。"""
    g = img.convert("L")
    hist = g.histogram()
    total = sum(hist)
    near_white = sum(hist[white_thresh:])
    return near_white / total if total else 1.0


def ocr_boxes(path):
    """返回 [(x1, y1, x2, y2, text, conf), ...]；OCR 不可用时返回 None。"""
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as exc:                                    # pragma: no cover
        print("  [!] OCR 不可用（%s）→ 跳过文字相关检查" % type(exc).__name__)
        return None
    res = RapidOCR()(path)
    items = res[0] if isinstance(res, tuple) else res
    boxes = []
    for it in items or []:
        try:
            poly, txt, conf = it[0], it[1], it[2]
        except Exception:
            continue
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        boxes.append((min(xs), min(ys), max(xs), max(ys), str(txt), float(conf)))
    return boxes


# ─────────────────────── 遮挡判定（含假阳性抑制） ───────────────────────

def _iou_over_smaller(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    if ix * iy <= 0:
        return 0.0
    inter = ix * iy
    aa = (a[2] - a[0]) * (a[3] - a[1])
    ab = (b[2] - b[0]) * (b[3] - b[1])
    small = min(aa, ab)
    return inter / small if small else 0.0


def _looks_like_multiline_label(a, b):
    """多行刻度标签的上下行 → 天然相交，必须排除，否则全是假阳性。

    判据：两框水平范围高度重合，且垂直间距 < 1.2 × 平均字高。
    """
    ox = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    narrow = min(a[2] - a[0], b[2] - b[0])
    if narrow <= 0 or ox / narrow < 0.7:
        return False
    ha, hb = (a[3] - a[1]), (b[3] - b[1])
    if ha <= 0 or hb <= 0:
        return False
    gap = max(b[1], a[1]) - min(b[3], a[3])          # 上下叠置时为正
    if gap > 0 and gap > 1.2 * (ha + hb) / 2:
        return False
    # 文本前缀相同（'基线①a' / '对称min+同向' 这类同一刻度标签的两行）也默认视为一体
    top, bot = (a, b) if a[1] <= b[1] else (b, a)
    return True


def occlusion_scan(boxes, iou_thresh=0.05):
    suspects, suppressed = [], []
    for a, b in itertools.combinations(boxes, 2):
        v = _iou_over_smaller(a, b)
        if v <= iou_thresh:
            continue
        (suppressed if _looks_like_multiline_label(a, b) else suspects).append((v, a[4], b[4]))
    return suspects, suppressed


# ─────────────────────────── 单图全检 ───────────────────────────

def check_image(path, expect=(), iou_thresh=0.05):
    print("\n=== %s ===" % os.path.basename(path))
    failures = []
    try:
        img = _load(path)
    except Exception as exc:
        print("  [FAIL] 无法打开：%s" % exc)
        return 1
    print("  尺寸 %s  大小 %s B" % (img.size, format(os.path.getsize(path), ",")))

    blank = blank_check(img)
    if blank > 0.995:
        print("  [FAIL] 近白占比 %.4f → 疑似空白图" % blank)
        failures += 1
    else:
        print("  [ OK ] 近白占比 %.4f" % blank)

    hits = edge_crop_check(img)
    tot = sum(hits.values())
    if tot:
        print("  [FAIL] 非白像素触边 %d 处 %s → 内容可能被裁出画布" % (tot, hits))
        failures += 1
    else:
        print("  [ OK ] 无内容触边")

    boxes = ocr_boxes(path)
    if boxes is None:
        return 1 if failures else 0

    print("  OCR 文本框 %d 个" % len(boxes))
    joined = " | ".join(b[4] for b in boxes)
    missing = [e for e in expect if e not in joined]
    if expect:
        if missing:
            print("  [FAIL] 关键标签缺失：%s  ← 该数字在图上可能被遮住/没画" % missing)
            failures += 1
        else:
            print("  [ OK ] 关键标签全部命中（%d/%d）" % (len(expect), len(expect)))

    suspects, suppressed = occlusion_scan(boxes, iou_thresh)
    if suspects:
        print("  [FAIL] 疑似遮挡 %d 对：" % len(suspects))
        for v, ta, tb in suspects[:12]:
            print("         %.2f  %r  <->  %r" % (v, ta, tb))
        failures += 1
    else:
        print("  [ OK ] 无遮挡（已抑制 %d 对多行刻度标签假阳性）" % len(suppressed))
    return 1 if failures else 0


# ─────────────────── docx 内嵌图 vs 磁盘源图（SHA256） ───────────────────

def check_docx_vs_figdir(docx, figdirs, order):
    import zipfile
    print("\n=== docx 内嵌图 vs 磁盘源图 ===")
    figdirs = figdirs if isinstance(figdirs, (list, tuple)) else [figdirs]
    fail = 0
    with zipfile.ZipFile(docx) as z:
        media = sorted((n for n in z.namelist() if n.startswith("word/media/")))
        print("  docx 内媒体 %d 个；待比对图 %d 个" % (len(media), len(order)))
        if len(media) != len(order):
            print("  [FAIL] 数量不等：docx=%d order=%d → 附录顺序或图注数对不上" % (len(media), len(order)))
            fail += 1
        for m, name in zip(media, order):
            want = None
            for d in figdirs:
                p = os.path.join(d, name)
                if os.path.exists(p):
                    want = p
                    break
            if want is None:
                print("  [FAIL] 磁盘找不到 %s（查过 %s）" % (name, figdirs))
                fail += 1
                continue
            h_docx = hashlib.sha256(z.read(m)).hexdigest()
            h_disk = hashlib.sha256(open(want, "rb").read()).hexdigest()
            ok = h_docx == h_disk
            print("  %s %-42s %s" % ("[ OK ]" if ok else "[FAIL]", name,
                                     "SHA256 一致" if ok else "不一致 ← docx 里是旧图！"))
            fail += 0 if ok else 1
    return fail


def main(argv=None):
    ap = argparse.ArgumentParser(description="附图质检探针（遮挡/裁切/空白/标签/docx 一致性）")
    ap.add_argument("image", nargs="?", help="单张图路径")
    ap.add_argument("--dir", help="批量模式：目录（只查 *.png）")
    ap.add_argument("--expect", nargs="*", default=[], help="期望在图上出现的文字标签")
    ap.add_argument("--iou", type=float, default=0.05, help="遮挡判定 IoU 阈值（默认 0.05）")
    ap.add_argument("--docx", help="额外核验 docx 内嵌图")
    ap.add_argument("--figdir", nargs="*", default=[], help="源图目录（可多个，按序查找）")
    ap.add_argument("--order", nargs="*", default=[], help="图注顺序的源图文件名（配合 --docx）")
    args = ap.parse_args(argv)

    fail = 0
    if args.image:
        fail += check_image(args.image, args.expect, args.iou)
    elif args.dir:
        files = sorted(f for f in os.listdir(args.dir) if f.lower().endswith(".png"))
        if not files:
            print("目录内无 PNG：%s" % args.dir)
            return 1
        for f in files:
            fail += check_image(os.path.join(args.dir, f), args.expect, args.iou)
    elif not args.docx:
        ap.print_help()
        return 1

    if args.docx:
        fail += check_docx_vs_figdir(args.docx, args.figdir or ["."], args.order)

    print("\n==================================")
    print("结果：%s" % ("全部通过" if fail == 0 else "%d 项 FAIL" % fail))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
