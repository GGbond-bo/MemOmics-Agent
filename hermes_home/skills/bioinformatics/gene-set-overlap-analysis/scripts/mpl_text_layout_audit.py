# -*- coding: utf-8 -*-
"""
mpl_text_layout_audit.py — matplotlib 版式确定性自检 + 一步导出
================================================================
不靠肉眼、不靠 OCR 猜：用文字**包围盒**判定
  ① 越出画布（溢出到隔壁面板 / 被裁掉）
  ② 文字两两重叠（标签粘连 —— 如 "Aging UP (Old vs Youngx_Old DOWN"）

为什么必须用它：出图 → 读图 → 改标签 → 重跑 的迭代会连吃平台循环检测干预
（实测本类任务重跑 3 轮、两度收到"判定为循环失控"）。把自检焊进 save()
⇒ **一次运行就拿到越界/重叠数字**，不必再多轮往返。

用法 A（推荐，替换你自己的 save）
    from mpl_text_layout_audit import save_figure
    save_figure(fig, "fig_venn_exercise", outdir="results/task4/figures")

用法 B（只查，不出图）
    from mpl_text_layout_audit import audit_figure_layout
    rep = audit_figure_layout(fig)      # dict: overflow / collisions / n_texts / canvas
    assert not rep["overflow"] and not rep["collisions"]

用法 C（本文件自测：python mpl_text_layout_audit.py）
    故意摆两个重叠文本 + 一个越界文本，验证检测器真的能抓到。
"""
from __future__ import annotations

import os

__all__ = ["audit_figure_layout", "save_figure", "format_report"]


def _texts_with_bbox(fig, renderer):
    """收集画布上全部非空 Text 及其显示坐标包围盒。"""
    items = []
    for ax in fig.axes:
        cand = list(ax.texts)
        for extra in ("title", "xaxis", "yaxis"):
            obj = getattr(ax, extra, None)
            if obj is not None and getattr(obj, "label", None) is not None:
                cand.append(obj.label)
        for t in cand:
            try:
                if not t.get_text():
                    continue
                items.append((t, t.get_window_extent(renderer)))
            except Exception:
                continue
    return items


def audit_figure_layout(fig, pad: float = 1.0) -> dict:
    """确定性版式自检。

    pad: 容差（像素）。默认 1 px —— 亚像素贴合不算越界/重叠。
    返回 dict(canvas, n_texts, overflow=[str], collisions=[str])
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    W, H = float(fig.bbox.width), float(fig.bbox.height)
    items = _texts_with_bbox(fig, renderer)

    overflow = []
    for t, b in items:
        if b.x0 < -pad or b.x1 > W + pad or b.y0 < -pad or b.y1 > H + pad:
            overflow.append(
                f"{t.get_text()[:26]!r} bbox x[{b.x0:.0f},{b.x1:.0f}] y[{b.y0:.0f},{b.y1:.0f}]"
                f" out of canvas {W:.0f}x{H:.0f}"
            )

    collisions = []
    for i, (a, A) in enumerate(items):
        for b, B in items[i + 1:]:
            # 双向包含判定：多行文本是单个 Text 对象，不会自我重叠；故只做跨对象比较
            if (A.x1 > B.x0 + pad and B.x1 > A.x0 + pad
                    and A.y1 > B.y0 + pad and B.y1 > A.y0 + pad):
                collisions.append(f"{a.get_text()[:18]!r} ⋂ {b.get_text()[:18]!r}")

    return {"canvas": (round(W), round(H)), "n_texts": len(items),
            "overflow": overflow, "collisions": collisions}


def format_report(stem: str, rep: dict) -> str:
    ok = (not rep["overflow"]) and (not rep["collisions"])
    head = (f"  版式自检 {stem}: 画布 {rep['canvas'][0]}x{rep['canvas'][1]} | "
            f"文字 {rep['n_texts']} 个 | 越界 {len(rep['overflow'])} | "
            f"重叠 {len(rep['collisions'])}")
    return head + (" ✓" if ok else "  ⚠ " + "; ".join(rep["overflow"] + rep["collisions"]))


def save_figure(fig, stem: str, outdir: str = ".", exts=("png", "pdf", "svg"),
                dpi: int = 300, audit: bool = True, close: bool = True) -> dict:
    """自检 + 一步导出（PNG 300dpi / 矢量 PDF 字体内嵌 / 可编辑 SVG）。

    ⚠️ 出图前务必先设：plt.rcParams["pdf.fonttype"]=42, ps.fonttype=42,
       svg.fonttype="none" —— 否则 PDF 不嵌字体，投稿会被拒。
    返回 audit 报告 dict（含 ok 字段）；outdir 不存在会自动建。
    """
    os.makedirs(outdir, exist_ok=True)
    rep = audit_figure_layout(fig) if audit else {"overflow": [], "collisions": [],
                                                 "n_texts": -1, "canvas": (0, 0)}
    rep["ok"] = (not rep["overflow"]) and (not rep["collisions"])
    if audit:
        print(format_report(stem, rep))
        if not rep["ok"]:
            print("  ⛔ 版式未通过：修标签位置/ylim 余量后重跑（不要靠肉眼确认）")
    for ext in exts:
        fig.savefig(os.path.join(outdir, f"{stem}.{ext}"), dpi=dpi,
                    bbox_inches="tight", facecolor="white")
    if close:
        import matplotlib.pyplot as plt
        plt.close(fig)
    print(f"  saved {stem}.{'/.'.join(exts)} -> {outdir}")
    return rep


if __name__ == "__main__":
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    fig, ax = plt.subplots(figsize=(4, 4))
    ax.axis("off")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_aspect("equal")
    ax.add_patch(Circle((0.35, 0.5), 0.3, alpha=.4, facecolor="#c0392b"))
    ax.add_patch(Circle((0.65, 0.5), 0.3, alpha=.4, facecolor="#2c6fbb"))
    # 故意重叠（外侧角对齐才是正解）
    ax.text(0.30, 0.92, "Aging UP (Old vs Young)", ha="center", va="bottom")
    ax.text(0.32, 0.92, "Ex_Old DOWN (Post vs Pre)", ha="center", va="bottom")
    # 故意越界
    ax.text(1.60, 0.05, "OFFCANVAS", ha="right", va="top")

    rep = audit_figure_layout(fig)
    print(format_report("self_test", rep))
    assert rep["collisions"], "自测失败：重叠检测没抓到"
    assert rep["overflow"], "自测失败：越界检测没抓到"
    print("✅ 自测通过：重叠与越界均被确定性捕获（无需肉眼/OCR）")