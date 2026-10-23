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
        "analysis code. **按执行位置审查**：location 说清这次跑在哪（local=本机 / cluster=集群 / "
        "cloud=云平台 / auto=推断），只查对应位置的包清单——本地缺的包不会拦集群任务"
        "（实测踩过：本地缺 RUVSeq 拦了集群投递，而集群上其实有）。位置写成 "
        "location_source=explicit|inferred，inferred 的问题只报警告不拦。"
        "Returns should_proceed=False if packages missing（仅显式位置）。 "
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
            },
            "location": {
                "type": "string",
                "enum": ["auto", "local", "cluster", "cloud"],
                "default": "auto",
                "description": (
                    "这次分析**在哪跑**（2026-10-09 起必填概念，默认 auto 推断）："
                    "local=本机 execute_r/execute_python；cluster=远端集群（remote_cluster/session_*）；"
                    "cloud=云平台（DCS 等）；auto=按最近活跃的常驻会话/集群上下文推断。"
                    "审查只查**对应位置**的包清单：本地缺的包不再拦集群任务，反之亦然。"
                    "显式传 location 才有硬拦；auto 推断出来的问题只报警告，不拦执行。"
                )
            },
            "node": {"type": "string",
                     "description": "location=cluster：哪个节点（如 node4；只配一个节点时可省）"},
            "env": {"type": "string",
                    "description": "location=cluster：哪个环境（conda env 名，如 R4.41；默认 remote.session.env）"},
            "rscript": {"type": "string",
                        "description": "location=cluster：Rscript 绝对路径（覆盖自动探测）"},
        },
        "required": ["phase", "module_id"]
    }
}


def _cluster_context(max_age_hours=6.0):
    """本机有没有「正在用/刚用过」的集群会话 → dict(node, env, session_id, status, last_active)。"""
    try:
        from . import cluster_session as _cs
    except Exception:
        return None
    try:
        rec = _cs.latest_session()
    except Exception:
        return None
    if not isinstance(rec, dict) or not rec.get("id"):
        return None
    state = str(rec.get("status") or "")
    last = str(rec.get("last_active") or rec.get("created") or "")
    age_h = None
    try:
        from datetime import datetime as _dt
        age_h = (_dt.now() - _dt.strptime(last, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600.0
    except Exception:
        age_h = None
    if state == "stopped" and (age_h is None or age_h > max_age_hours):
        return None
    return {"node": str(rec.get("node") or ""), "env": str(rec.get("env") or ""),
            "session_id": str(rec.get("id") or ""), "status": state,
            "last_active": last, "age_hours": age_h}


def _resolve_location(location, node="", env=""):
    """把 location 参数落成 (位置, 依据)：local / cluster / cloud。

    auto 的推断口径（2026-10-09）：本机账本里有常驻集群会话（未停止，或 6 小时内用过）
    → 认定这次跑在集群（node/env 跟着那个会话走）；否则按本地。
    推断结果只用于「报告里写清在哪审的」+ 软提醒；**硬拦只认显式传的 location**，
    免得推断错了又拿错位置的包清单去挡人（这正是这次要修的坑）。
    """
    loc = str(location or "auto").strip().lower()
    if loc in ("cluster", "remote", "集群", "远端"):
        ctx = _cluster_context() or {}
        return {"location": "cluster", "source": "explicit",
                "node": str(node or ctx.get("node") or ""),
                "env": str(env or ctx.get("env") or ""),
                "basis": "调用方显式指定 location=cluster" + ("（node/env 取常驻会话上下文）" if not node and ctx else "")}
    if loc in ("local", "本机", "localhost"):
        return {"location": "local", "source": "explicit", "node": "", "env": "",
                "basis": "调用方显式指定 location=local"}
    if loc in ("cloud", "云", "云平台", "dcs"):
        return {"location": "cloud", "source": "explicit", "node": str(node or ""),
                "env": str(env or ""), "basis": "调用方显式指定 location=cloud"}
    ctx = _cluster_context()
    if ctx:
        return {"location": "cluster", "source": "inferred",
                "node": str(node or ctx.get("node") or ""), "env": str(env or ctx.get("env") or ""),
                "basis": ("自动推断：本机有常驻集群会话 %s @%s（env=%s, 状态=%s, 最近活跃=%s）"
                          % (ctx.get("session_id"), ctx.get("node"), ctx.get("env") or "-",
                             ctx.get("status") or "-", ctx.get("last_active") or "-"))}
    return {"location": "local", "source": "inferred", "node": str(node or ""), "env": str(env or ""),
            "basis": "自动推断：本机没有活跃的集群会话上下文 → 按本地执行判"}


def _location_line(loc, res=None):
    """一句人话说明「这次审查查的是哪里的包」，给报告和用户看。"""
    where = {"local": "本机", "cluster": "集群", "cloud": "云平台"}.get(loc.get("location"), loc.get("location"))
    if loc.get("location") == "cluster":
        where = "集群 %s%s" % (loc.get("node") or "?", ("/" + loc["env"]) if loc.get("env") else "")
    src = "显式指定" if loc.get("source") == "explicit" else "自动推断"
    tail = ""
    if loc.get("location") == "local":
        tail = "（本机 R/Python 包清单）"
    elif loc.get("location") == "cluster" and res is not None:
        if res.get("reachable"):
            tail = "（节点上的 R 包清单，%s 个包，取于 %s%s）" % (
                res.get("count"), res.get("checked_at") or "?",
                "，缓存命中" if res.get("cached") else "")
        else:
            tail = "（**没法核实**：%s）" % (res.get("error") or "ssh 不通")
    elif loc.get("location") == "cloud":
        tail = "（云平台环境本机核不了 → 按未核实处理）"
    return "📍 审查位置：%s —— %s%s；依据：%s" % (where, src, tail, loc.get("basis") or "-")


def _pre_review(module_id, required_packages=None, skill_name="", location="auto",
                node="", env="", rscript=""):
    """Pre-analysis review（按执行位置审查：本地查本地、集群查集群、云平台标未核实）。"""
    issues = []
    warnings = []
    missing_packages = []
    unverified = []
    loc = _resolve_location(location, node, env)
    res = None

    # P4: Check if skill_view was called (铁轨阻断)
    if not skill_name or not skill_name.strip():
        issues.append(
            "SKILL_NOT_LOADED: 未检测到 skill_view 调用。"
            "请先调用 skill_search() 找到合适的 skill，然后用 skill_view() 加载完整指令。"
            "所有分析必须在 skill 指导下进行，禁止未经 skill 确认直接写代码。"
        )

    if required_packages:
        from . import env_check
        if loc["location"] == "cloud":
            res = {"missing": {}, "installed": {}, "unverified": list(required_packages),
                   "source": "cloud", "reachable": False, "count": None, "checked_at": "",
                   "error": "", "cached": None}
            warnings.append(
                "云平台(%s)的环境无法在本机核实：%s —— 按**未核实**处理，不拦执行；"
                "请在目标任务里加一步环境自检（或先跑一次会话内的 requireNamespace 检查）。"
                % (loc.get("node") or "cloud", "、".join(required_packages)))
        else:
            res = env_check.check_env(
                required_packages,
                language="R" if loc["location"] == "cluster" else "both",
                auto_install=False, scope=loc["location"],
                node=loc["node"], env=loc["env"], rscript=rscript)
        missing = list((res.get("missing") or {}).keys())
        unverified = [p for p in (res.get("unverified") or []) if p not in missing]
        where = ("集群 %s%s" % (loc.get("node") or "?", ("/" + loc["env"]) if loc.get("env") else "")
                 if loc["location"] == "cluster" else ("本机" if loc["location"] == "local" else "云平台"))
        # 位置上的清单压根没读到（ssh 不通/环境名错）→ 明确说「没法核实」，绝不当缺包
        if loc["location"] == "cluster" and not (res or {}).get("reachable", True):
            warnings.append(
                "⚠️ %s 的包清单**没法核实**（%s）—— %s 按未核实处理，**不拦执行**；"
                "先确认节点连通/环境名（可 remote_cluster action='nodes' 或 action='r_packages' 手查）。%s"
                % (where, (res or {}).get("error") or "未知原因",
                   "、".join(required_packages), (res or {}).get("hint") or ""))
        if missing:
            missing_packages = missing
            msg = "Missing packages (%s): %s" % (where, ", ".join(missing))
            if loc["location"] == "cluster" and not res.get("reachable"):
                # 连不上集群 ≠ 缺包：只提醒，不算问题（别拿不可用的事实拦人）
                warnings.append(msg + " —— ⚠️ 但集群清单没读到（%s），这是**没法核实**，不是确证缺包；"
                                       "先确认节点连通/包名拼写，别据此拒跑。" % (res.get("error") or ""))
                missing_packages, issues_missing = [], False
            else:
                issues_missing = True
            if loc["source"] != "explicit":
                # 位置是推断的：只报警告（推断错了不该拦人）
                warnings.append(msg + " —— 位置是%s，先确认这次到底在哪儿跑；"
                                       "确认后显式调 rail_review(phase='pre', location='%s'%s) 才会拦。"
                                % (loc.get("basis") or "推断",
                                   "cluster" if loc["location"] == "cluster" else loc["location"],
                                   (", node='%s'" % loc["node"]) if loc.get("node") else ""))
            elif issues_missing:
                issues.append(msg)
        if unverified:
            warnings.append(
                "未核实（%s判不了/本机看不到）：%s —— 不算缺包；"
                "要确证请在目标环境里跑一次 requireNamespace/import 自检。" % (where, ", ".join(unverified)))
        if not missing and not unverified and required_packages:
            warnings.append("✅ 包齐（%s）：%s" % (where, ", ".join(required_packages)))

    should_proceed = len(issues) == 0
    return {
        "phase": "pre",
        "module_id": module_id,
        # 位置信息（2026-10-09 用户要求）：审查必须说清「在哪审的」，本地/集群/云要分开
        "location": loc["location"],
        "location_source": loc["source"],
        "location_line": _location_line(loc, res),
        "location_basis": loc["basis"],
        "node": loc.get("node") or "",
        "env": loc.get("env") or "",
        "env_source": (res or {}).get("source") or loc["location"],
        "checked_at": (res or {}).get("checked_at") or "",
        "packages_checked": list(required_packages or []),
        "should_proceed": should_proceed,
        "issues": issues,
        "warnings": warnings,
        "missing_packages": missing_packages,
        "unverified": unverified,
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


def _post_review(module_id, method_name, output_dir, code_executed, required_packages=None,
                 location="auto", node="", env=""):
    """Post-analysis review（结果里标明这次分析在哪儿跑的：本机/集群/云）。"""
    _ploc = _resolve_location(location, node, env)
    # 2026-10-09：这两个变量原来只在 code_executed 非空时才赋值，导致「不带代码调 post」
    # （如只看产物目录/只盖章位置）会 UnboundLocalError 崩掉 —— 先给默认值。
    code_packages = set()
    unregistered = []
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
                    # 问题7: 检测图片大小（<5KB；2026-10-04 修误报：小图先看像素证据再判定）
                    fsize = None
                    try:
                        fsize = _os.path.getsize(fpath)
                    except Exception:
                        figure_issues.append(f"无法读取图片大小: {f}")
                    small = fsize is not None and fsize < 5 * 1024
                    small_handled = False  # 像素检测已确认的小图（有内容→放行/空白→已有 issue）
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
                                small_handled = True
                                if unique_count <= 2:
                                    figure_issues.append(f"图片几乎全为单一颜色 ({unique_count} 种值): {f} — 可能是空白图，必须重新生成")
                                elif small:
                                    figure_warnings.append(
                                        f"图片较小 ({fsize}B): {f} — 像素检测到 {unique_count} 种颜色，判定为有效内容（非空白/非错误图），已放行；"
                                        f"如为交付图请人工确认分辨率是否足够"
                                    )
                                # 检测 NA 比例
                                if _np.any(_np.isnan(arr.astype(float)) if arr.dtype.kind == 'f' else False):
                                    na_ratio = _np.isnan(arr.astype(float)).sum() / arr.size
                                    if na_ratio > 0.1:
                                        figure_issues.append(f"图片含 {na_ratio*100:.1f}% NA 值: {f} — 画图不全，必须重新生成")
                        except ImportError:
                            pass  # PIL 未安装则跳过深度检测
                        except Exception:
                            figure_issues.append(f"图片可能损坏无法打开: {f} — 必须重新生成")
                    # 小图且无法用像素检测确认（SVG/TIFF/无 PIL）→ 维持原严格判定
                    if small and not small_handled:
                        figure_issues.append(f"图片太小 ({fsize}B): {f} — 可能是空白图或错误图，必须重新生成")
                elif f.lower().endswith(('.csv', '.tsv', '.rds', '.h5ad', '.txt', '.json')):
                    result_files.append(f)
        # 图片数量检查（强制；报告/加载类步骤豁免——本身不产图，否则死锁）
        if figure_count == 0 and not _is_report_step(module_id, method_name):
            if _ploc["location"] == "cluster":
                figure_issues.append(
                    "未生成任何图片 — 每步至少 1 张图，必须重新执行。"
                    "⚠️ 本次按**集群执行**审的：如果图是在集群上出的，先把产物 pull 回本机"
                    "（remote_cluster action='pull'），或把 output_dir 指到本机拉回的目录再复审；"
                    "别把「产物还在远端」误当成「没出图」。")
            elif _ploc["location"] == "cloud":
                figure_issues.append(
                    "未生成任何图片 — 每步至少 1 张图，必须重新执行。"
                    "⚠️ 云平台任务：图可能还在云端产物目录里，先下载/挂载到本机（或指给 output_dir）再复审。")
            else: 
                figure_issues.append("未生成任何图片 — 每步至少 1 张图，必须重新执行")
        elif figure_count < 2 and module_id in ('clustering', 'deg', 'cellchat', 'trajectory', 'annotation', 'spatial', 'atac'):
            figure_issues.append(f"图片数量不足 ({figure_count} 张) — 关键步骤({module_id})至少需要 2-3 张图，必须补充")
        if not result_files:
            warnings.append("No result files found in output directory")
        # 问题7: 图片健康度问题作为 issues（阻断）；小图有像素证据时降级为 warning（2026-10-04）
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
        # 位置信息：后审查也要说清「这次分析是在哪儿跑的」（本机 vs 集群 vs 云）
        "location": _ploc["location"],
        "location_source": _ploc["source"],
        "location_line": _location_line(_ploc),
        "location_basis": _ploc["basis"],
        "node": _ploc.get("node") or "",
        "env": _ploc.get("env") or "",
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


def rail_review(phase, module_id, method_name="", output_dir="", code_executed="",
                required_packages=None, skill_name="", location="auto", node="", env="",
                rscript=""):
    """Rail review handler（location=这次分析在哪跑：auto/local/cluster/cloud）。"""
    if phase == "pre":
        result = _pre_review(module_id, required_packages, skill_name,
                             location=location, node=node, env=env, rscript=rscript)
    else:
        result = _post_review(module_id, method_name, output_dir, code_executed, required_packages,
                              location=location, node=node, env=env)
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
            args.get("skill_name", ""),
            args.get("location", "auto"),
            args.get("node", ""),
            args.get("env", ""),
            args.get("rscript", "")
        ),
        emoji="🛡️",
        max_result_size_chars=20_000,
    )

_register()
