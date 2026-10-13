#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_figure_layers.py — base-R / matplotlib 出图的三层核验（一次跑完，别反复像素扫描）

为什么需要它：base graphics 图的失效是**静默**的 —— 文件非空、exit 0、无 warning，
但某个元素（分组色块条 / 标签 / 轴名）可能压根没渲染，或被裁到画布外。
本脚本把「SVG 元素层 + PNG 栅格层」一次测完并给 PASS/FAIL，避免靠肉眼/反复 vision 猜。

用法
----
  # 最小：只验 SVG 里有没有出现这些颜色
  python3 verify_figure_layers.py --svg fig.svg --expect 2C7FB8 1B9E77 7BA05B

  # 完整：同时验栅格层（沿色块条所在列采样，检查「每成员采样点数」是否成比例）
  python3 verify_figure_layers.py --svg fig.svg --png fig.png \
      --column 880 --expect 2C7FB8:4 1B9E77:4 7BA05B:3 D64550:4 8C5FA8:2

参数
----
  --expect C1[:n1] C2[:n2] ...   预期颜色(hex) 及其**成员数**（分组有几个成员就写几）
  --column X                     PNG 采样列（色块条所在的 x 像素）；可给多个
  --tol T                        栅格层像素比对的单通道容差（默认 0 = 精确匹配，边缘抗锯齿像素会被忽略）

  ① SVG 层：每个预期色命中数应 > 0；若某色 0 命中 → **先确认不是方法假阴性**（本层只认 rgb(%) 形式，
     `grep '#RRGGBB'` 必然 0）——做法是拿一张**已知含该色**的图跑同一命令做阳性对照；阳性对照正常
     且该色仍 0 → **元素没渲染**（多半是绘制顺序/被裁），不是配色问题。注意 R 的 svg() 把文字转成
     glyph，`<text>` 数天然为 0，别误判。
  ② PNG 层：每个色「采样计数 ÷ 成员数」应近似为常数（= 一个格子的高度 / 采样步长）。
     成比例 = 色块高度正确、无重叠错位；某色 0 命中或比例失衡 = 行位置算错。
"""

import argparse
import re
import sys
from pathlib import Path


# ---------- 工具 ----------
def hex_to_rgb(h):
    h = h.strip().lstrip("#")
    if len(h) != 6:
        raise ValueError("hex 颜色需为 6 位，如 2C7FB8")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def pct_triple(rgb):
    """R cairo svg 的写法：rgb(17.254902%, 49.803922%, 72.156863%)"""
    return "%.6f%%" % (rgb[0] / 255.0 * 100), "%.6f%%" % (rgb[1] / 255.0 * 100), "%.6f%%" % (rgb[2] / 255.0 * 100)


def parse_expect(items):
    """['2C7FB8:4', '1B9E77'] -> [(hex, n_or_None), ...]"""
    out = []
    for it in items:
        if ":" in it:
            c, n = it.split(":", 1)
            out.append((c.strip(), int(n)))
        else:
            out.append((it.strip(), None))
    return out


# ---------- 第①层：SVG 元素层 ----------
RGB_RE = re.compile(r"rgb\(\s*([\d.]+)%\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%\s*\)")


def layer_svg(svg_path, expect, tol=0.01):
    """把 svg 里所有 rgb(%) 解析回 0-255，再和预期色比对（数值容差，规避 R 的取整差异）"""
    txt = Path(svg_path).read_text(encoding="utf-8", errors="ignore")
    triples = []
    for m in RGB_RE.finditer(txt):
        triples.append(tuple(float(v) / 100.0 * 255.0 for v in m.groups()))

    print(f"[① SVG 元素层] {svg_path}  解析到 rgb() 元素 {len(triples)} 个")

    # 文字是 glyph 轮廓 → <text> 天然为 0，这里只做提示，不作为失败判据
    n_text = len(re.findall(r"<text\b", txt))
    n_use = len(re.findall(r"xlink:href", txt))
    print(f"    <text> 节点 = {n_text}（R svg() 转曲，天然 0，非失败判据）; xlink:href glyph 引用 = {n_use}")

    ok = True
    for hexc, n in expect:
        want = hex_to_rgb(hexc)
        cnt = sum(1 for t in triples
                  if all(abs(t[i] - want[i]) <= tol for i in range(3)))
        flag = "OK " if cnt > 0 else "❌ "
        extra = ""
        if n is not None:
            extra = f"   (成员数 {n} → 预期 ≥{n}，轴名若同样着色则 = {n + 1})"
        print(f"    {flag}#{hexc} 命中 {cnt}{extra}")
        if cnt == 0:
            ok = False
            print(f"         ⚠️ 先排除方法假阴性：本层只认 rgb(%) 形式，`grep '#RRGGBB'` 必然 0 命中；"
                  f"请先拿一张**已知含该色**的图跑同一命令做阳性对照 —— 阳性对照也 0 ⇒ 是取样方法问题，"
                  f"改用 --png 栅格层，别断言「元素没渲染」")
            print(f"         确认真 0 命中 = 该元素**没渲染**（查绘制顺序：凡在 par(fig=..,new=TRUE) "
                  f"+ plot.window() 之后用数据坐标画的都会被静默裁掉），不要从配色找原因")
    return ok


# ---------- 第②层：PNG 栅格层 ----------
def layer_png(png_path, columns, expect, tol=0):
    try:
        from PIL import Image
    except ImportError:
        print("[② PNG 栅格层] 跳过：未安装 Pillow（pip install pillow）")
        return True

    im = Image.open(png_path).convert("RGB")   # ⚠️ 必须 convert("RGB")：调色板模式会算错
    W, H = im.size
    print(f"[② PNG 栅格层] {png_path}  {W}x{H}")

    named = [(h, n) for h, n in expect if n]
    ok = True
    for x in columns:
        if not (0 <= x < W):
            print(f"    x={x} 越界，跳过")
            continue
        col = [im.getpixel((x, y)) for y in range(H)]
        counts = {}
        for hexc, _ in named:
            want = hex_to_rgb(hexc)
            counts[hexc] = sum(1 for p in col
                               if all(abs(p[i] - want[i]) <= tol for i in range(3)))
        total = sum(counts.values())
        if total == 0:
            print(f"    x={x} → ❌ 该列没有任何预期颜色（采样列打偏了？或色块条没渲染）")
            ok = False
            continue
        print(f"    x={x} → 命中 {total} 像素")
        per_member = []
        for hexc, n in named:
            c = counts[hexc]
            pm = c / n if n else float("nan")
            per_member.append(pm)
            print(f"        #{hexc}: {c:5d}  成员数 {n}  每成员 {pm:6.1f}")
        vals = [v for v in per_member if v > 0]
        if len(vals) >= 2:
            spread = (max(vals) - min(vals)) / max(vals)
            verdict = "✅ 成比例（色块高度 = 1 格、无重叠错位）" if spread < 0.15 \
                else "❌ 比例失衡（行位置/成员数算错了）"
            print(f"        每成员波动 {spread * 100:.1f}% → {verdict}")
            if spread >= 0.15:
                ok = False
        if any(counts[h] == 0 for h, _ in named):
            missing = [h for h, _ in named if counts[h] == 0]
            print(f"        ❌ 该列未出现: {', '.join('#' + m for m in missing)}")
            ok = False
    return ok


def main():
    ap = argparse.ArgumentParser(description="base-R/matplotlib 出图三层核验")
    ap.add_argument("--svg", help="SVG 文件（元素层）")
    ap.add_argument("--png", help="PNG 文件（栅格层）")
    ap.add_argument("--column", type=int, nargs="*", default=[],
                    help="PNG 采样列（色块条所在 x），可多个")
    ap.add_argument("--expect", nargs="+", required=True,
                    help="预期色 hex，可带成员数：2C7FB8:4 1B9E77:4 ...")
    ap.add_argument("--tol", type=float, default=0, help="栅格层单通道容差（默认 0）")
    a = ap.parse_args()

    expect = parse_expect(a.expect)
    ok = True

    if a.svg:
        ok = layer_svg(a.svg, expect) and ok
    else:
        print("[① SVG 元素层] 跳过（未给 --svg）")

    if a.png:
        if not a.column:
            print("[② PNG 栅格层] 跳过：未给 --column")
        else:
            ok = layer_png(a.png, a.column, expect, tol=a.tol) and ok
    else:
        print("[② PNG 栅格层] 跳过（未给 --png）")

    print("[③ OCR 文字层] 请另跑 vision_describe(png)：文本条数 ≥ 预期标签总数（含分组名）")
    print("\n=== 总判：%s ===" % ("✅ PASS" if ok else "❌ FAIL（按上面 ❌ 行逐条查）"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
