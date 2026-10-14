#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""幂等重打 ChineseResearchLaTeX 本机补丁（MiKTeX 便携版；2026-10-12 实测）

补丁 A：bensz-fonts.sty —— \theabsdir 为空时回退到绝对字体目录
补丁 B：cv 模板 main-*.tex —— tabu -> array + tabular（tabu 与本机内核不兼容）

用法:
  python crl_fix_local_patches.py --check              # 体检，不改任何文件
  python crl_fix_local_patches.py                      # 打全部（A + 所有 cv-* 项目）
  python crl_fix_local_patches.py --project cv-01      # 只处理指定 cv 项目
退出码: 0=已就绪/已修好; 1=有需要人工处理的问题
"""
from __future__ import annotations
import argparse
import os
import re
import sys

CRL_ROOT = os.environ.get("CRL_ROOT", r"E:/MemOmics-Agent/third_party/CRL")
MIKTEX_TEXMF = os.environ.get("MIKTEX_TEXMF", r"E:/MiKTeX/texmf-local")
BACKUP_SUFFIX = ".bak-memomics"

FONT_MARKS = ("% [MemOmics local patch", "% [MemOmics 本地修复")  # 已打补丁的标记（兼容两种措辞）


def _read(p: str) -> str:
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def _backup(p: str) -> None:
    b = p + BACKUP_SUFFIX
    if not os.path.exists(b):
        with open(p, "rb") as src, open(b, "wb") as dst:
            dst.write(src.read())


def fix_fonts_sty(path: str, apply: bool) -> str:
    """给一个 bensz-fonts.sty 打空值回退补丁。返回状态描述。"""
    if not os.path.exists(path):
        return "SKIP(不存在): %s" % path
    txt = _read(path)
    if any(mk in txt for mk in FONT_MARKS):
        return "OK(已打): %s" % path
    m = re.search(r"(\\getabspath\{bensz-fonts\.sty\}\r?\n\\edef\\BenszFontsPackageDir\{\\theabsdir\})", txt)
    if not m:
        return "WARN(找不到锚点，需人工看): %s" % path
    if not apply:
        return "TODO(待打): %s" % path
    d = os.path.dirname(path).replace("\\", "/")
    if not d.endswith("/"):
        d += "/"
    patch = (
        m.group(1)
        + "\r\n% [MemOmics 本地修复] MiKTeX 便携版下 \\theabsdir 可能为空 -> 回退绝对路径"
        + "\r\n\\ifx\\BenszFontsPackageDir\\empty"
        + "\r\n  \\edef\\BenszFontsPackageDir{" + d + "}"
        + "\r\n\\fi"
    )
    _backup(path)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(txt.replace(m.group(1), patch, 1))
    return "FIXED: %s" % path


def fix_cv_project(proj_dir: str, apply: bool, variant: str) -> str:
    """把 cv 模板里的 tabu 换成 array + tabular。"""
    path = os.path.join(proj_dir, variant)
    if not os.path.exists(path):
        return "SKIP(不存在): %s" % path
    txt = _read(path)
    if "\\begin{tabu}" not in txt and "\\usepackage{tabu}" not in txt:
        return "OK(无 tabu): %s" % path
    if not apply:
        return "TODO(待打): %s" % path
    _backup(path)
    txt = txt.replace("\\usepackage{tabu}",
                      "% [MemOmics 本地修复] tabu 与本机 LaTeX 内核不兼容 -> 改用 array+tabular\r\n\\usepackage{array}")
    txt = txt.replace("\\begin{tabu}", "\\begin{tabular}").replace("\\end{tabu}", "\\end{tabular}")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(txt)
    return "FIXED: %s" % path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只体检不改文件")
    ap.add_argument("--project", default=None, help="只处理该 cv 项目名（如 cv-01）")
    ap.add_argument("--variant", default=None, help="指定单个 .tex（默认 main-zh.tex + main-en.tex）")
    args = ap.parse_args()
    apply = not args.check
    out = []

    # --- 补丁 A ---
    for p in [os.path.join(MIKTEX_TEXMF, r"tex/latex/bensz-fonts/bensz-fonts.sty"),
              os.path.join(CRL_ROOT, r"packages/bensz-fonts/bensz-fonts.sty")]:
        out.append(fix_fonts_sty(p.replace("\\", "/"), apply))

    # --- 补丁 B ---
    proj_root = os.path.join(CRL_ROOT, "projects")
    projects = [args.project] if args.project else (
        sorted(d for d in os.listdir(proj_root) if os.path.isdir(os.path.join(proj_root, d)) and "cv" in d.lower())
        if os.path.isdir(proj_root) else [])
    variants = [args.variant] if args.variant else ["main-zh.tex", "main-en.tex"]
    for prj in projects:
        for v in variants:
            out.append(fix_cv_project(os.path.join(proj_root, prj), apply, v))

    print("\n".join(out))
    bad = [l for l in out if l.startswith(("WARN", "TODO"))]
    if args.check:
        print("\n[体检模式] 待打补丁 %d 项；执行时去掉 --check" % len(bad))
    return 1 if bad and args.check else 0


if __name__ == "__main__":
    sys.exit(main())