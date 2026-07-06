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


def extract_with_pymupdf(pdf_path: str) -> str:
    """第一层: pymupdf 快速提取."""
    try:
        import fitz  # pymupdf
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


def main():
    parser = argparse.ArgumentParser(description="PDF 文献参数提取")
    parser.add_argument("pdf_path", help="PDF 文件路径")
    parser.add_argument("--method", choices=["auto", "pymupdf", "markitdown"], default="auto")
    args = parser.parse_args()

    text = extract_pdf(args.pdf_path, args.method)
    print(text)


if __name__ == "__main__":
    main()
