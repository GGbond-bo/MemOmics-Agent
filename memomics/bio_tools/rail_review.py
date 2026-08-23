"""Rail review tool — pre/post analysis review (铁轨审查)."""
import json
import os
import logging

logger = logging.getLogger(__name__)

SCHEMA = {
    "name": "rail_review",
    "description": (
        "Rail review (铁轨审查) for analysis steps. "
        "PRE review: checks if environment/packages are ready before running "
        "analysis code. Returns should_proceed=False if packages missing. "
        "POST review: checks result quality after analysis — figure count, "
        "file outputs, code length, conclusion validity. Returns passed=False "
        "if quality insufficient. MUST be called before and after each "
        "analysis subtask."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "phase": {
                "type": "string",
                "enum": ["pre", "post"],
                "description": "Pre-review (before analysis) or post-review (after analysis)"
            },
            "module_id": {"type": "string", "description": "Module ID (e.g. qc, normalize, cellchat)"},
            "method_name": {"type": "string", "description": "Method name (e.g. Seurat_QC, CellChat_v2)"},
            "output_dir": {"type": "string", "description": "Output directory for post-review (results/module/method/)"},
            "code_executed": {"type": "string", "description": "The code that was executed (for post-review quality check and package detection)"},
            "required_packages": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Required packages. PRE: checked for installation. POST: compared against packages actually used in code_executed to detect unregistered packages."
            },
            "skill_name": {
                "type": "string",
                "description": "名称已在 skill_view() 中加载（如 'deg-analysis'）。必须传递此参数以确认正确使用 skill。"
            }
        },
        "required": ["phase", "module_id"]
    }
}


def _pre_review(module_id, required_packages=None, skill_name=""):
    """Pre-analysis review."""
    issues = []
    warnings = []
    missing_packages = []

    # P4: Check if skill_view was called (铁轨阻断)
    if not skill_name or not skill_name.strip():
        issues.append(
            "SKILL_NOT_LOADED: 未检测到 skill_view 调用。"
            "请先调用 skill_search() 找到合适的 skill，然后用 skill_view() 加载完整指令。"
            "所有分析必须在 skill 指导下进行，禁止未经 skill 确认直接写代码。"
        )

    # Check required packages
    if required_packages:
        # Quick check via check_env logic
        from . import env_check
        result = env_check.check_env(required_packages, auto_install=False)
        missing = list(result.get("missing", {}).keys())
        if missing:
            missing_packages = missing
            issues.append(f"Missing packages: {', '.join(missing)}")

    should_proceed = len(issues) == 0
    return {
        "phase": "pre",
        "module_id": module_id,
        "should_proceed": should_proceed,
        "issues": issues,
        "warnings": warnings,
        "missing_packages": missing_packages,
    }


def _extract_packages(code):
    """Extract package names from R/Python code that are actually used.

    R patterns: library(x), require(x), requireNamespace("x"), x::func
    Python patterns: import x, from x import y

    Excludes R/Python base packages. Returns a sorted set of unique package names.
    """
    import re
    if not code or not isinstance(code, str):
        return set()

    packages = set()

    # --- R patterns ---
    # library(CellChat), library("CellChat"), library('CellChat')
    for m in re.finditer(r'(?:library|require)\s*\(\s*["\']?(\w+(?:\.\w+)*)', code):
        packages.add(m.group(1))
    # requireNamespace("CellChat")
    for m in re.finditer(r'requireNamespace\s*\(\s*["\'](\w+(?:\.\w+)*)', code):
        packages.add(m.group(1))
    # pkg::func  (e.g. SCP::CellDimPlot, presto::wilcoxauc)
    for m in re.finditer(r'(\w+(?:\.\w+)*)::', code):
        packages.add(m.group(1))

    # --- Python patterns ---
    for m in re.finditer(r'^import\s+(\w+(?:\.\w+)*)', code, re.MULTILINE):
        packages.add(m.group(1))
    for m in re.finditer(r'^from\s+(\w+(?:\.\w+)*)\s+import', code, re.MULTILINE):
        packages.add(m.group(1))

    # Exclude R/Python base packages (false positives)
    r_base = {'base', 'stats', 'utils', 'graphics', 'grDevices', 'methods', 'datasets',
              'parallel', 'grid', 'splines', 'stats4', 'tcltk', 'tools', 'compiler'}
    py_base = {'os', 'sys', 're', 'json', 'math', 'time', 'datetime', 'collections',
               'itertools', 'pathlib', 'logging', 'warnings', 'argparse', 'copy',
               'glob', 'subprocess', 'tempfile', 'shutil', 'typing', 'functools'}

    packages = {p for p in packages if p.lower() not in r_base and p.lower() not in py_base}
    return packages


def _is_report_step(module_id, method_name=""):
    """报告/加载类步骤判定（2026-08-14 死锁修复）。

    纯"加载并报告结构"的步骤（如 scrna-load / Seurat_load_report）本身不产图、
    代码天然短，不应被"必须 >=1 张图"和"代码 >=10 行"硬性阻断——否则会死锁：
    过审要图 -> 产图要 execute_r -> execute_r 被未通过的审查全局阻断。
    """
    mid = (module_id or "").lower()
    mname = (method_name or "").lower()
    if mid.endswith("-load") or mid in ("load", "report", "data-load"):
        return True
    if "load_report" in mname or "overview" in mname or mname.endswith("_load") or "report" in mname:
        return True
    return False


def _post_review(module_id, method_name, output_dir, code_executed, required_packages=None):
    """Post-analysis review."""
    issues = []
    warnings = []
    figure_count = 0
    result_files = []

    # Check output directory
    if output_dir and os.path.exists(output_dir):
        # 问题7: 图片健康度检测（强化版）
        import os as _os
        figure_issues = []
        figure_warnings = []
        for root, dirs, files in os.walk(output_dir):
            for f in files:
                fpath = _os.path.join(root, f)
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.svg', '.tiff')):
                    figure_count += 1
                    # 问题7: 检测图片大小（<5KB → 强制重新生成）
                    try:
                        fsize = _os.path.getsize(fpath)
                        if fsize < 5 * 1024:  # < 5KB
                            figure_issues.append(f"图片太小 ({fsize}B): {f} — 可能是空白图或错误图，必须重新生成")
                    except Exception:
                        figure_issues.append(f"无法读取图片大小: {f}")
                    # 用 PIL 检测空白/NA (只查 PNG/JPG)
                    if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                        try:
                            from PIL import Image
                            import numpy as _np
                            img = Image.open(fpath)
                            arr = _np.array(img)
                            # 检测全白/全黑/全单一色
                            if arr.size > 0:
                                if arr.ndim == 3:
                                    flat = arr.reshape(-1, arr.shape[-1])
                                else:
                                    flat = arr.flatten()
                                unique_count = len(_np.unique(flat, axis=0)) if arr.ndim == 3 else len(_np.unique(flat))
                                if unique_count <= 2:
                                    figure_issues.append(f"图片几乎全为单一颜色 ({unique_count} 种值): {f} — 可能是空白图，必须重新生成")
                                # 检测 NA 比例
                                if _np.any(_np.isnan(arr.astype(float)) if arr.dtype.kind == 'f' else False):
                                    na_ratio = _np.isnan(arr.astype(float)).sum() / arr.size
                                    if na_ratio > 0.1:
                                        figure_issues.append(f"图片含 {na_ratio*100:.1f}% NA 值: {f} — 画图不全，必须重新生成")
                        except ImportError:
                            pass  # PIL 未安装则跳过深度检测
                        except Exception:
                            figure_issues.append(f"图片可能损坏无法打开: {f} — 必须重新生成")
                elif f.lower().endswith(('.csv', '.tsv', '.rds', '.h5ad', '.txt', '.json')):
                    result_files.append(f)
        # 图片数量检查（强制；报告/加载类步骤豁免——本身不产图，否则死锁）
        if figure_count == 0 and not _is_report_step(module_id, method_name):
            figure_issues.append("未生成任何图片 — 每步至少 1 张图，必须重新执行")
        elif figure_count < 2 and module_id in ('clustering', 'deg', 'cellchat', 'trajectory', 'annotation', 'spatial', 'atac'):
            figure_issues.append(f"图片数量不足 ({figure_count} 张) — 关键步骤({module_id})至少需要 2-3 张图，必须补充")
        if not result_files:
            warnings.append("No result files found in output directory")
        # 问题7: 图片健康度问题作为 issues（阻断，不是 warnings）
        issues.extend(figure_issues)
        warnings.extend(figure_warnings)
    elif output_dir:
        issues.append(f"Output directory not found: {output_dir}")

    # Check code quality (强化版)
    if code_executed:
        code_lines = code_executed.strip().split('\n')
        # 代码行数检查（报告/加载类步骤豁免——天然短，否则死锁）
        if len(code_lines) < 10 and not _is_report_step(module_id, method_name):
            issues.append(f"代码过短 ({len(code_lines)} 行) — 可能偷懒，必须写完整分析代码")
        if len(code_lines) > 500:
            warnings.append(f"代码过长 ({len(code_lines)} 行) — 建议拆分")
        # 代码分段执行检查（禁止 && 连接多步骤）
        if '&&' in code_executed:
            issues.append("代码使用 && 连接多步骤 — 必须分步执行：写一步→执行→检查→下一步")
        # 注释检查
        comment_lines = [l for l in code_lines if l.strip().startswith('#') or l.strip().startswith('//')]
        if len(comment_lines) < 2:
            warnings.append(f"代码注释过少 ({len(comment_lines)} 行) — 建议添加关键步骤注释")
        # 错误处理检查
        if 'tryCatch' not in code_executed and 'try:' not in code_executed and 'stopifnot' not in code_executed:
            warnings.append("No error handling in code (tryCatch/try)")
        # 2026-08-14: 持久 kernel 复用提醒——非加载类步骤重复 readRDS 是浪费
        # （同会话 kernel 保留 obj，900MB 级对象每步重读极慢）
        if 'readRDS(' in code_executed and not _is_report_step(module_id, method_name):
            warnings.append(
                "检测到代码中 readRDS 重新加载数据。execute_r 持久 kernel 在同会话内保留变量（obj）"
                "和已加载的包，后续步骤应直接复用 obj，无需每步 readRDS（大对象重读极慢）。"
                "仅当报 object not found（kernel 超时/重启）时才重新加载。"
            )

        # === 包检测：扫描代码中实际使用的包 vs skill 声明的 required_packages ===
        code_packages = _extract_packages(code_executed)
        unregistered = []
        if code_packages and required_packages is not None:
            declared_lower = {p.lower() for p in required_packages if p}
            for pkg in code_packages:
                if pkg.lower() not in declared_lower:
                    unregistered.append(pkg)
            if unregistered:
                warnings.append(
                    f"UNREGISTERED_PACKAGES: 代码使用了 {len(unregistered)} 个 skill 未声明的包: "
                    f"{', '.join(unregistered)}。"
                    f"这些包未在 skill_view() 的 r_packages/python_packages 中声明。"
                    f"请选择其一: (1) 用原生包替代 (2) 补充到 SKILL.md 的 r_packages/python_packages 列表 (3) 记录到 Common Issues 作为可选加速包。"
                    f"否则下次分析可能因环境不同而失败。"
                )

    passed = len(issues) == 0
    # 强化提醒：有参数或结论时必须辩论
    debate_reminder = ""
    if passed and code_executed:
        # 检测代码中是否有参数选择或结论输出
        has_params = any(kw in code_executed.lower() for kw in ['resolution', 'min_', 'max_', 'threshold', 'dims', 'pcs', 'alpha', 'lambda', 'penalty', 'n_neighbors', 'perplexity'])
        has_conclusions = any(kw in code_executed.lower() for kw in ['conclusion', 'finding', 'result', 'significant', 'pvalue', 'p.value', 'enriched', 'marker'])
        if has_params or has_conclusions:
            debate_reminder = "⚠️ 代码包含参数选择或结论输出 — 必须调 debate_analysis 进行辩论（正方 vs 反方 → 裁决）"

    # 自进化提醒：审查通过/失败时必须调 skill_evolution
    evolution_reminder = ""
    if passed:
        evolution_reminder = (
            "✅ 审查通过 — 必须调 skill_evolution(action=\"record_run\") 记录本次成功经验：\n"
            "   skill_name=<本步骤skill>, script_name=<脚本名>, species=<物种>, tissue=<组织>,\n"
            "   direction=<方向>, params_used=<参数JSON>, result_summary=<结果摘要>,\n"
            "   quality_score=<0-10>, notes=<经验总结>\n"
            "   → 记录后下次同类分析可直接复用参数，越用越稳"
        )
    else:
        evolution_reminder = (
            "❌ 审查未通过 — 修复问题后重跑，成功后调 skill_evolution(action=\"record_run\") 记录。\n"
            "   如果脚本报错，修复后调 skill_evolution(action=\"record_error\") 记录根因和修复方案：\n"
            "   skill_name=<本步骤skill>, script_name=<脚本名>, species=<物种>, tissue=<组织>,\n"
            "   direction=<方向>, error_message=<报错>, root_cause=<根因>, fix_applied=<修复方案>\n"
            "   → 记录后下次遇到同类错误可自动避坑"
        )

    return {
        "phase": "post",
        "module_id": module_id,
        "method_name": method_name or "unknown",
        "passed": passed,
        "issues": issues,
        "warnings": warnings,
        "figure_count": figure_count,
        "result_files": result_files,
        "debate_reminder": debate_reminder,
        "evolution_reminder": evolution_reminder,
        "code_packages": list(code_packages) if 'code_packages' in dir() and code_packages else [],
        "unregistered_packages": unregistered,
    }


def rail_review(phase, module_id, method_name="", output_dir="", code_executed="", required_packages=None, skill_name=""):
    """Rail review handler."""
    if phase == "pre":
        result = _pre_review(module_id, required_packages, skill_name)
    else:
        result = _post_review(module_id, method_name, output_dir, code_executed, required_packages)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _register():
    from tools.registry import registry
    registry.register(
        name="rail_review",
        toolset="memomics",
        schema=SCHEMA,
        handler=lambda args, **kw: rail_review(
            args.get("phase", "pre"),
            args.get("module_id", ""),
            args.get("method_name", ""),
            args.get("output_dir", ""),
            args.get("code_executed", ""),
            args.get("required_packages"),
            args.get("skill_name", "")
        ),
        emoji="🛡️",
        max_result_size_chars=20_000,
    )

_register()
