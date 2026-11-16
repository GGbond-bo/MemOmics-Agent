#!/usr/bin/env python
"""反推参考图（PDF）的精确规格 —— 按参考图复刻出图的第一步。

用法:
    python probe_reference_figure.py "<reference.pdf>" [--out spec.json]

给出（stdout + 可选 JSON）:
    page_inches           画布英寸 (pt / 72) —— 直接喂 ggsave(width=, height=)
    y_order_top2bottom    y 轴标签真实显示顺序（自上而下）—— 用坐标算，不用文本流顺序
    x_order_left2right    x 轴标签真实显示顺序（自左向右）
    label_rotation_deg    x 轴标签旋转角（45 = Seurat RotatedAxis()；90 = theme angle=90）
    label_size_pt         标签字号
    palette               色条两端颜色（优先读**内嵌位图**）—— 对应 cols = c(浅, 深)
    dot_diameter_pt       圆点直径范围 -> ggplot dot.scale ≈ max / 2.8346

⚠️ 色条/渐变在图里通常是内嵌位图，get_drawings() 抓不到 —— 本脚本会走 get_images()。
⚠️ 若同页有多张位图，palette.source 会标出用的是第几张，请人工确认哪张是色条。
"""
import argparse
import io
import json
import math
import sys

try:
    import pymupdf  # 新版
except ImportError:  # pragma: no cover
    import fitz as pymupdf


def _hex(t):
    return "#%02X%02X%02X" % (int(t[0]), int(t[1]), int(t[2]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--out", default=None, help="把规格另存为 JSON")
    ap.add_argument("--row-gap", type=float, default=4.0,
                    help="y 标签同一行的 y0 容差(pt)，超过即视为新行（默认 4)")
    ap.add_argument("--x-band", type=float, default=0.90,
                    help="底部 band 判定：y0 > 页高*该比例 视为 x 轴标签（默认 0.90）")
    a = ap.parse_args()

    doc = pymupdf.open(a.pdf)
    page = doc[0]
    W, H = page.rect.width, page.rect.height
    spec = {"pdf": a.pdf,
            "page_pt": [round(W, 1), round(H, 1)],
            "page_inches": [round(W / 72.0, 2), round(H / 72.0, 2)]}

    # ---- 文字 span（带坐标 + 方向）----
    spans = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for line in b["lines"]:
            for s in line["spans"]:
                t = s["text"].strip()
                if not t:
                    continue
                x0, y0, x1, y1 = s["bbox"]
                spans.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "t": t,
                              "size": round(s.get("size", 0), 1),
                              "dir": line.get("dir", (1.0, 0.0))})

    # ---- 圆点（有填充的近正方）→ 面板边界 + 点径 ----
    filled = [it for it in page.get_drawings() if it.get("fill")]
    dots = [it["rect"] for it in filled
            if 2.0 < it["rect"].width < max(W, H) * 0.12
            and abs(it["rect"].width - it["rect"].height) < 3.0]
    if dots:
        pl = min(r.x0 for r in dots)
        pb = max(r.y1 for r in dots)
        pr = max(r.x1 for r in dots)
        pt_ = min(r.y0 for r in dots)
        spec["panel_pt"] = [round(pl, 1), round(pt_, 1), round(pr, 1), round(pb, 1)]
        dmin = min(r.width for r in dots)
        dmax = max(r.width for r in dots)
        spec["dot_diameter_pt"] = {"min": round(dmin, 1), "max": round(dmax, 1),
                                  "dot_scale_hint_mm": round(dmax / 2.8346, 2)}
        spec["n_dots"] = len(dots)
    else:
        pl, pb = W * 0.10, H * a.x_band
        spec["panel_pt"] = None
        spec["dot_diameter_pt"] = None

    # ---- y 轴标签：面板左侧一列，按 y0 升序逐行聚类 ----
    yw = sorted([s for s in spans if s["x1"] <= pl + 2.0], key=lambda s: s["y0"])
    y_order, cur = [], []
    for s in yw:
        if cur and s["y0"] - cur[-1]["y0"] > a.row_gap:
            y_order.append(" ".join(x["t"] for x in sorted(cur, key=lambda z: z["x0"])))
            cur = []
        cur.append(s)
    if cur:
        y_order.append(" ".join(x["t"] for x in sorted(cur, key=lambda z: z["x0"])))
    spec["y_order_top2bottom"] = y_order

    # ---- x 轴标签：底部 band，按 x0 升序 ----
    xw = sorted([s for s in spans if s["y0"] >= min(pb - 4.0, H * a.x_band)],
                key=lambda s: s["x0"])
    # 剔除混进来的轴标题（通常字号更大且居中）——保留信息由调用方判断
    spec["x_order_left2right"] = [s["t"] for s in xw]
    if xw:
        s0 = xw[0]
        spec["label_rotation_deg"] = round(
            math.degrees(math.atan2(-s0["dir"][1], s0["dir"][0])), 1)
        spec["label_size_pt"] = s0["size"]
        spec["x_label_raw"] = [{"t": s["t"], "x0": round(s["x0"], 1),
                                "y0": round(s["y0"], 1), "size": s["size"]} for s in xw]

    # ---- 色条（内嵌位图优先）----
    pal = {"source": "none"}
    imgs = page.get_images()
    if imgs:
        try:
            from PIL import Image
            xref = imgs[0][0]
            raw = doc.extract_image(xref)
            im = Image.open(io.BytesIO(raw["image"])).convert("RGB")
            w, h = im.size
            col = w // 2
            pal = {"source": "embedded-image", "image_index": 1,
                   "size": [w, h], "top": _hex(im.getpixel((col, 1))),
                   "bottom": _hex(im.getpixel((col, h - 2))),
                   "note": "同页位图若多于一张，请人工确认哪张是色条（此处取第 1 张）"}
            if len(imgs) > 1:
                pal["n_images"] = len(imgs)
        except Exception as e:  # noqa: BLE001
            pal = {"source": "image-error", "error": "%s: %s" % (type(e).__name__, e)}
    elif filled:
        lums = sorted(((sum(it["fill"]) / 3.0, tuple(it["fill"])) for it in filled))
        pal = {"source": "drawings-fallback",
               "darkest": _hex(lums[0][1]), "lightest": _hex(lums[-1][1]),
               "note": "没找到内嵌位图；用图形填充色极值近似"}
    spec["palette"] = pal

    # ---- 图例区文字（右侧）----
    leg = sorted([s for s in spans if s["x0"] > W * 0.90], key=lambda s: s["y0"])
    spec["legend_text_top2bottom"] = [s["t"] for s in leg]

    doc.close()

    print(json.dumps(spec, ensure_ascii=False, indent=2))
    print("\n--- 复刻换算速记 ---", file=sys.stderr)
    print("画布      : %.2f x %.2f in" % tuple(spec["page_inches"]), file=sys.stderr)
    if spec["dot_diameter_pt"]:
        print("dot.scale : %.2f mm (由最大点 %.2f pt 换算)"
              % (spec["dot_diameter_pt"]["dot_scale_hint_mm"],
                 spec["dot_diameter_pt"]["max"]), file=sys.stderr)
    if "label_rotation_deg" in spec:
        print("x 标签    : %.1f° / %.1f pt" % (spec["label_rotation_deg"],
                                              spec["label_size_pt"]), file=sys.stderr)
    print("配色      : %s" % spec["palette"], file=sys.stderr)
    print("y 行数    : %d   x 标签数: %d" % (len(spec["y_order_top2bottom"]),
                                            len(spec["x_order_left2right"])), file=sys.stderr)

    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)
        print("\n已写: %s" % a.out, file=sys.stderr)


if __name__ == "__main__":
    main()