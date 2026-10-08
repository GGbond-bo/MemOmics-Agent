# -*- coding: utf-8 -*-
"""
把 HTML 幻灯片逐页渲染为 PNG 预览图（真渲染，非占位图）。

为什么需要
----------
1) 交付 .pptx 后，用户无法在对话里直接看版式 → 逐页 PNG 让他一眼扫完、指页号提意见。
2) rail_review(post) 会用「数据图」标准判 deck（figure_count=0 → 「未生成任何图片」）。
   正确修法是**真渲染预览图**，不是凑一张占位图。

路径选择
--------
本机无 LibreOffice、无 POWERPNT 时（用户办公套件是 WPS），PPTX 无法直接转图；
若 deck 同时出了 HTML 双版本 → 走 **HTML → Edge/Chrome 无头截图**（实测可行）。

依赖：Pillow。浏览器用 Edge/Chrome 无头模式（自动探测）。

用法
----
    python render_slide_previews.py <deck.html> <out_dir> [--width 1600] [--browser PATH]

示例
----
    python render_slide_previews.py \
        E:/MemOmics-Agent/results/<sid>/reports/deck.html \
        E:/MemOmics-Agent/results/<sid>/figures

约定
----
- HTML 里每个 <section>…</section> 作为一页；
- <div class="cover">…</div> 作为封面页（可选，自动识别为 slide_00.png）。
输出：<out_dir>/slide_00.png, slide_01.png, ...

验收（出图后必做）
------------------
用 vision_describe 对最复杂的一两页做 OCR 断言：表头/列是否齐全、关键数字是否都在、
有无裁切。只回「已生成」而不核验 = 把坏页交给用户。
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

CANDIDATES = [
    r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    r"C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    r"C:/Program Files/Google/Chrome/Application/chrome.exe",
    r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def find_browser(explicit=None):
    if explicit:
        return explicit
    for c in CANDIDATES:
        if os.path.exists(c):
            return c
    for n in ("msedge", "chrome", "chromium", "google-chrome"):
        p = shutil.which(n)
        if p:
            return p
    return None


def split_pages(html):
    """返回 (style_css, [(tag, fragment), ...])。"""
    m_style = re.search(r"<style>(.*?)</style>", html, re.S)
    m_body = re.search(r"<body>(.*?)</body>", html, re.S)
    if not m_body:
        raise SystemExit("HTML 里找不到 <body>")
    style = m_style.group(1) if m_style else ""
    body = m_body.group(1)

    pages = []
    cover = re.search(r'(<div class="cover">.*?</div>\s*</div>)', body, re.S)
    if cover:
        pages.append(("00", cover.group(1)))
    for i, sec in enumerate(re.findall(r"<section>(.*?)</section>", body, re.S), 1):
        pages.append(("%02d" % i, "<section>%s</section>" % sec))
    return style, pages


def trim(path, pad=26):
    """从右下角把画布空白裁掉，让每页高度贴合内容。"""
    from PIL import Image

    im = Image.open(path).convert("RGB")
    w, h = im.size
    px = im.load()
    bg = px[5, h - 5]          # 左下角 = body 背景色

    bottom, right = h, w
    for y in range(h - 1, -1, -1):
        if not all(px[x, y] == bg for x in range(0, w, 7)):
            bottom = min(h, y + pad)
            break
    for x in range(w - 1, -1, -1):
        if not all(px[x, y] == bg for y in range(0, bottom, 7)):
            right = min(w, x + pad + 4)
            break

    im.crop((0, 0, right, bottom)).save(path, "PNG")
    return im.size


def main():
    ap = argparse.ArgumentParser(description="HTML 幻灯片 → 逐页 PNG 预览图")
    ap.add_argument("html", help="deck 的 HTML 文件路径")
    ap.add_argument("out_dir", help="PNG 输出目录（通常 .../figures）")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=3000,
                    help="截图窗口高；给足余量，随后自动裁白边")
    ap.add_argument("--browser", default=None, help="显式指定 msedge/chrome 可执行文件")
    a = ap.parse_args()

    browser = find_browser(a.browser)
    if not browser:
        raise SystemExit("找不到 Edge/Chrome —— 用 --browser 显式指定可执行文件路径")

    os.makedirs(a.out_dir, exist_ok=True)
    style, pages = split_pages(open(a.html, encoding="utf-8").read())
    if not pages:
        raise SystemExit("没找到 <section>，无法拆页")

    # 注意：注入的 CSS 里不要出现裸 %（本模板已避免），否则 %-formatting 会炸
    tpl = ('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><style>%s\n'
           'html,body{background:#FBFCFD;} body{padding:26px 30px;}'
           '.wrap{padding:0;max-width:none;}'
           'section{box-shadow:none;margin:0;}</style></head>'
           '<body><div class="wrap">%s</div></body></html>')

    tmp = tempfile.mkdtemp(prefix="slidepng_")
    ok = 0
    for tag, frag in pages:
        hp = os.path.join(tmp, "s%s.html" % tag)
        with open(hp, "w", encoding="utf-8") as f:
            f.write(tpl % (style, frag))

        op = os.path.join(a.out_dir, "slide_%s.png" % tag)
        cmd = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
               "--no-first-run", "--no-default-browser-check",
               "--user-data-dir=" + os.path.join(tmp, "prof"),
               "--window-size=%d,%d" % (a.width, a.height),
               "--screenshot=" + op,
               "file:///" + hp.replace("\\", "/")]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

        if not os.path.exists(op):
            print("[FAIL] slide_%s: rc=%s %s"
                  % (tag, r.returncode, (r.stderr or r.stdout)[-200:]))
            continue
        size = trim(op)
        print("[OK] slide_%s.png  %s  %d B" % (tag, size, os.path.getsize(op)))
        ok += 1

    print("TOTAL: %d/%d" % (ok, len(pages)))
    if ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()