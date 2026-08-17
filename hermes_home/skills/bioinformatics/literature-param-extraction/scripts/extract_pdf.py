#!/usr/bin/env python3
# ============================================================
# 🔒 MemOmics 审查与辩论机制 + 自进化日志
# ============================================================
# 此脚本由 MemOmics Agent 执行。原脚本永远不被修改。
#
# 执行前必须:
#   1. rail_review(action="pre")  — 检查环境/参数/数据
#   2. skill_evolution(action="query_logs", script_name="本脚本名",
#      species="物种", tissue="组织", direction="方向")
#      → 查同类运行日志，有则参考已有参数和经验，无则按原脚本执行
#   3. debate_analysis(topic, context) — 参数不确定时多角色辩论
#
# 执行后必须:
#   1. rail_review(action="post") — 检查输出/质量/图表
#      ★ 强制审查项（任一不通过则重新执行）:
#        a. 图片是否生成？无图 → 重新执行
#        b. 图片是否空白（全白/全黑/全单一色）？空白 → 强制重新出图
#        c. 图片是否有 NA/缺失值（>10%像素是NA）？有NA → 强制重新出图
#        d. 图片大小是否过小（<5KB）？过小 → 强制重新出图
#        e. 图片数量是否足够？（每步至少1张图，关键步骤至少2-3张）
#        f. 代码行数是否合理？是否分段执行（禁止&&连接）？
#        g. 数值范围是否合理？跟知识库对应吗？
#   2. 如果通过 → skill_evolution(action="record_run",
#      script_name="本脚本名", species="物种", tissue="组织",
#      direction="方向", params_used="参数JSON", result_summary="结果",
#      quality_score=8, notes="经验总结")
#      → 记录成功运行日志，供后续同类型分析参考
#   3. 如果失败 → skill_evolution(action="record_error",
#      script_name="本脚本名", species="物种", tissue="组织",
#      direction="方向", error_message="报错", root_cause="根因",
#      fix_applied="修复方案")
#      → 记录错误日志，修正后重跑
#
# ★ 参数和结论辩论铁律:
#   - 有参数选择 → 必须调 debate_analysis 辩论
#   - 有结论输出 → 必须调 debate_analysis 辩论
#   - 辩论格式：正方(支持) vs 反方(质疑+替代) → 裁判决断
#   - 最多3轮，3轮后选最优结果
#
# 日志存储: skill 目录下 .run_logs/ 目录，按 物种_组织_方向_日期 命名
# ============================================================

# ============================================================
# 🔒 MemOmics 审查铁律 — 执行本脚本前后的强制步骤
# ============================================================
# 执行前必须: rail_review(action="pre")  — 环境检查 + 参数校验 + 代码审查
# 执行后必须: rail_review(action="post") — 结果质量评估 + 图表检查 + 数值检查
#   ★ 强制: 图片空白/NA/过小 → 重新出图 | 图片不够 → 补图 | 代码未分段 → 重写
#   ★ 强制: 有参数有结论 → debate_analysis 辩论
# 参数有争议: debate_analysis(topic=..., context=...) — 多角色辩论
# 执行失败:   skill_evolution(action="record_error") — 记录错误
# 修复成功:   skill_evolution(action="update_script") — 替换脚本
# ============================================================


"""PDF 文献参数提取 — 第一层 pymupdf, 第二层 markitdown fallback.

用法:
    python extract_pdf.py <pdf_path> [--method auto|pymupdf|markitdown]

输出: Markdown 格式文本到 stdout
"""

import sys
import argparse
import subprocess
import json
import re


def extract_with_pymupdf(pdf_path: str) -> str:
    """第一层: pymupdf 快速提取."""
    try:
        import pymupdf as fitz  # 新包名（1.28 用 fitz 会向 stdout 打弃用警告污染 JSON 输出）
    except ImportError:
        try:
            import fitz  # noqa: F401 — 旧版兼容
        except ImportError:
            return ""

    doc = fitz.open(pdf_path)
    sections = []
    for page_num, page in enumerate(doc, 1):
        text = page.get_text("text")
        if text.strip():
            sections.append(f"## Page {page_num}\n\n{text}")
        # 提取表格
        tables = page.find_tables()
        for i, table in enumerate(tables):
            table_data = table.extract()
            if table_data:
                sections.append(f"\n### Table (Page {page_num}, #{i+1})\n")
                # 转 Markdown 表格
                for row in table_data:
                    cells = [str(c or "").replace("\n", " ") for c in row]
                    sections.append("| " + " | ".join(cells) + " |")
                # 分隔行
                if table_data:
                    sections.append("| " + " | ".join(["---"] * len(table_data[0])) + " |")
    doc.close()
    return "\n\n".join(sections)


def extract_with_markitdown(pdf_path: str) -> str:
    """第二层: markitdown fallback (保留格式更好)."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "markitdown", pdf_path],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout
    except Exception as e:
        print(f"markitdown error: {e}", file=sys.stderr)
    return ""


def extract_pdf(pdf_path: str, method: str = "auto") -> str:
    """主提取函数 — auto 模式先 pymupdf, 不够再 markitdown."""
    if method == "pymupdf":
        return extract_with_pymupdf(pdf_path)
    elif method == "markitdown":
        return extract_with_markitdown(pdf_path)
    else:  # auto
        text = extract_with_pymupdf(pdf_path)
        # 如果 pymupdf 提取太少 (< 500 字), 用 markitdown
        if len(text.strip()) < 500:
            md_text = extract_with_markitdown(pdf_path)
            if len(md_text.strip()) > len(text.strip()):
                return md_text
        return text


# ============ 2026-08-14 升级: 章节拆分 + 参数对提取 ============
# 修复: 旧版只回传 text_preview[:3000]，Methods 参数基本丢失。
# 现在: 章节级拆分（Abstract/Introduction/Methods→小节/Results/...）
#       + 确定性参数对提示（参数→值→出处句），供 LLM 结构化时对齐。

_SECTION_RE = re.compile(
    r"^\s*(?:(\d+(?:\.\d+)*)[\.\s]+)?(abstract|introduction|methods|materials and methods"
    r"|results|discussion|conclusion|references|supplementary|background|summary)\b",
    re.IGNORECASE,
)
_METHODS_SUB_RE = re.compile(
    r"^\s*(?:(\d+(?:\.\d+)*)[\.\s]+)?(quality control|qc and|data quality|filtering|cell filtering"
    r"|doublet|normalization|clustering|dimension|dimensionality|differential expression|deg|"
    r"marker|trajectory|pseudotime|velocity|cell.?cell communication|integration|batch|"
    r"annotation|cell type annotation|enrichment|gsea|go analysis|kegg|regulon|tf activity"
    r"|rna velocity|sample preparation|library preparation|sequencing|alignment|mapping|quantification)\b",
    re.IGNORECASE,
)

# 参数对提取模式: (参数名, 正则)
_PARAM_PATTERNS = [
    ("resolution", re.compile(r"resolution[\s=:：]*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)),
    ("min.cells/min_cells", re.compile(r"min[._]?cells[\s=:：><]*([0-9]+)", re.IGNORECASE)),
    ("nFeature_RNA", re.compile(r"nFeature_RNA[\s><=:：-]*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)),
    ("nCount_RNA", re.compile(r"nCount_RNA[\s><=:：-]*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)),
    ("percent.mt / MT%", re.compile(r"(?:percent[._]?mt|mitochondrial (?:content|percentage)|MT\s*%?)[\s><=:：-]*([0-9]+(?:\.[0-9]+)?)\s*%?", re.IGNORECASE)),
    ("dims", re.compile(r"dims[\s=:：]*1[:\-](\d+)", re.IGNORECASE)),
    ("HVG nfeatures", re.compile(r"(?:variable features|HVGs?|hvf)[^.]{0,60}?([0-9]{3,5})", re.IGNORECASE)),
    ("logfc.threshold", re.compile(r"logfc[._]?threshold[\s=:：]*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)),
    ("min.pct", re.compile(r"min[._]?pct[\s=:：]*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)),
    ("k.param", re.compile(r"k[._]?param[\s=:：]*([0-9]+)", re.IGNORECASE)),
    ("p_val_adj", re.compile(r"(?:p_val_adj|padj|adjusted p)[\s=:：<]*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)),
    ("doublet_rate", re.compile(r"doublet[^.]{0,40}?([0-9]+(?:\.[0-9]+)?)\s*%", re.IGNORECASE)),
    ("harmony", re.compile(r"harmony", re.IGNORECASE)),
    ("SCTransform", re.compile(r"sctransform|SCTransform", re.IGNORECASE)),
    ("batch_vars", re.compile(r"(?:vars[._]to[._]regress|regress(?:ed)? out)[^\n]{0,80}", re.IGNORECASE)),
]


def _split_sections(full_text: str) -> list:
    """把整篇文本拆成 摘要/引言/方法/结果/讨论/参考文献 等章节；无标题则整体一段。"""
    lines = full_text.splitlines()
    sections = []
    cur_title = "Front matter"
    cur_lines = []
    in_methods = False
    for line in lines:
        m = _SECTION_RE.match(line)
        if m and len(line.strip()) < 80:
            if cur_lines:
                sections.append({"title": cur_title, "text": "\n".join(cur_lines).strip()})
            cur_title = (m.group(2) or "").strip() or "Section"
            in_methods = cur_title.lower() in ("methods", "materials and methods")
            cur_lines = []
            continue
        if in_methods:
            ms = _METHODS_SUB_RE.match(line)
            if ms and len(line.strip()) < 80:
                if cur_lines:
                    sections.append({"title": cur_title, "text": "\n".join(cur_lines).strip()})
                cur_title = "Methods: " + (ms.group(2) or ms.group(1) or "subsection")
                cur_lines = []
                continue
        cur_lines.append(line)
    if cur_lines:
        sections.append({"title": cur_title, "text": "\n".join(cur_lines).strip()})
    return [s for s in sections if s["text"]]


def _extract_param_hints(full_text: str, max_hints: int = 60) -> list:
    """从全文确定性抓取 参数→值→出处句 提示（供 LLM 结构化提取时对齐）。"""
    hints = []
    seen = set()
    for name, pat in _PARAM_PATTERNS:
        for m in pat.finditer(full_text):
            val = m.group(1) if m.lastindex else None
            key = f"{name}={val}" if val is not None else f"{name}={m.group(0)[:24]}"
            if key in seen:
                continue
            seen.add(key)
            start = max(0, m.start() - 120)
            end = min(len(full_text), m.end() + 120)
            ctx = full_text[start:end].replace("\n", " ").strip()
            hints.append({"param": name, "value": val, "context": ctx[:260]})
            if len(hints) >= max_hints:
                return hints
    return hints


def _local_vision_describe(image_path: str) -> str:
    """调用 MemOmics 本地读图管道（OCR+结构+ASCII），失败返回空串。

    借鉴 pdf-inspector 的"图表页→视觉"路由思想，但用纯本地管道实现，零新依赖。
    """
    try:
        import os as _os
        _repo = _os.environ.get("MEMOMICS_REPO_ROOT", "")
        if not _repo and _os.environ.get("HERMES_HOME"):
            _repo = _os.path.dirname(_os.environ["HERMES_HOME"])
        if not _repo:
            _repo = _os.path.abspath(_os.path.join(
                _os.path.dirname(_os.path.abspath(__file__)), "..", "..", "..", "..", ".."))
        import sys as _sys
        for _p in (_repo, _os.path.join(_repo, "hermes-agent")):
            if _p not in _sys.path:
                _sys.path.insert(0, _p)
        from memomics.bio_tools.vision_tool import _local_describe, _format_describe
        return _format_describe(_local_describe(image_path))
    except Exception:
        return ""


def _chart_pages(pdf_path: str, max_pages: int = 8) -> list:
    """识别图表页（图多字少）→ 渲染 PNG → 本地视觉分析。

    返回 [(page_no, describe_text)]。任何一步失败都静默跳过（图表分析是增强项）。
    """
    try:
        import fitz as _fitz
    except ImportError:
        try:
            import pymupdf as _fitz
        except ImportError:
            return []
    try:
        doc = _fitz.open(pdf_path)
    except Exception:
        return []
    out = []
    try:
        for page_no, page in enumerate(doc, 1):
            if len(out) >= max_pages:
                break
            text_len = len(page.get_text("text").strip())
            images = page.get_images(full=True)
            is_chart = bool(images) and (text_len < 250 or len(images) >= 3)
            if not is_chart:
                continue
            try:
                pix = page.get_pixmap(matrix=_fitz.Matrix(1.6, 1.6))
                import tempfile
                import os as _os
                fd, tmp = tempfile.mkstemp(suffix=".png")
                _os.close(fd)
                pix.save(tmp)
                _desc = _local_vision_describe(tmp)
                _os.remove(tmp)
                if _desc:
                    out.append((page_no, _desc))
            except Exception:
                continue
    finally:
        doc.close()
    return out


def extract_pdf_structured(pdf_path: str, method: str = "auto") -> dict:
    """结构化提取: 章节 + 参数对提示 + 图表页本地视觉分析（供入库管线使用）。"""
    text = extract_pdf(pdf_path, method)
    structured = {
        "full_text_length": len(text),
        "sections": _split_sections(text),
        "param_hints": _extract_param_hints(text),
    }
    # 2026-08-14: 图表页路由（借鉴 pdf-inspector，纯本地视觉管道）
    if method in ("auto", "pymupdf"):
        _charts = _chart_pages(pdf_path)
        if _charts:
            structured["chart_pages"] = [{"page": p, "analysis": d} for p, d in _charts]
    return structured


def main():
    parser = argparse.ArgumentParser(description="PDF 文献参数提取")
    parser.add_argument("pdf_path", help="PDF 文件路径")
    parser.add_argument("--method", choices=["auto", "pymupdf", "markitdown"], default="auto")
    parser.add_argument("--sections", action="store_true",
                        help="输出 JSON 结构化章节 + 参数对提示（供入库管线使用）")
    args = parser.parse_args()

    if args.sections:
        out = extract_pdf_structured(args.pdf_path, args.method)
        print(json.dumps(out, ensure_ascii=False))
    else:
        text = extract_pdf(args.pdf_path, args.method)
        print(text)


if __name__ == "__main__":
    main()
