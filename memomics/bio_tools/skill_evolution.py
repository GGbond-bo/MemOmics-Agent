#!/usr/bin/env python3
"""
MemOmics Skill Evolution Engine
================================
自进化工具：脚本出错→记录→修复→更新skill；成功→记录proven脚本+参数。

五 actions:
  1. record_error   — 记录错误+根因+修复，更新 error_log.md + Common Issues
  2. record_success — 记录成功脚本+参数，更新 Proven Scripts + skill.json
  3. update_script  — 用修复后的脚本覆盖原脚本，备份旧版本
  4. query_logs     — 查同类运行日志（proven_params + error_log），返回历史经验
  5. record_run     — record_success 的别名，SOUL.md 铁律使用此名称
"""
import os
import json
import re
import shutil
from datetime import datetime
from typing import Dict, Any, Optional


def _get_skill_dir(skill_name: str) -> Optional[str]:
    """找到 skill 目录（先 skills/ 再 hermes_home/skills/bioinformatics/）"""
    candidates = [
        f"E:/MemOmics-Agent/skills/{skill_name}",
        f"E:/MemOmics-Agent/hermes_home/skills/bioinformatics/{skill_name}",
    ]
    for p in candidates:
        if os.path.isdir(p):
            return p
    return None


def _ensure_logs_dir(skill_dir: str) -> str:
    """确保 logs/ 目录存在"""
    logs_dir = os.path.join(skill_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    return logs_dir


def _read_file(path: str) -> str:
    """安全读文件"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _write_file(path: str, content: str) -> bool:
    """安全写文件"""
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        return False


# ─── 1. RECORD ERROR ───────────────────────────────

def _record_error(skill_name: str, error_message: str, error_type: str = "",
                  root_cause: str = "", fix_applied: str = "", fix_code: str = "",
                  species: str = "", tissue: str = "", direction: str = "",
                  script_name: str = "", severity: str = "medium") -> Dict[str, Any]:
    """记录错误到 error_log.md + 更新 SKILL.md Common Issues"""
    skill_dir = _get_skill_dir(skill_name)
    if not skill_dir:
        return {"success": False, "error": f"Skill '{skill_name}' not found"}

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    logs_dir = _ensure_logs_dir(skill_dir)
    log_path = os.path.join(logs_dir, "error_log.md")

    # 1. 追加到 error_log.md
    existing_log = _read_file(log_path)
    if not existing_log:
        existing_log = """# Error Log

> Errors and fixes accumulated from actual analysis runs.
> Each entry helps future runs avoid the same issues.

| Date | Error | Type | Cause | Fix | Species | Tissue | Severity |
|------|-------|------|-------|-----|---------|--------|----------|
"""

    # 检查是否是重复错误（相似错误信息）
    is_duplicate = error_message[:80] in existing_log
    if is_duplicate:
        # 更新 recurrence count
        new_row = f"| {timestamp} | {error_message[:60]}... | {error_type} | *(recurrence)* | {fix_applied[:40]} | {species} | {tissue} | {severity} |"
    else:
        # 截断长文本
        err_short = error_message.replace("|", "/")[:80]
        cause_short = root_cause.replace("|", "/")[:60] if root_cause else "-"
        fix_short = fix_applied.replace("|", "/")[:60] if fix_applied else "-"

        new_row = f"| {timestamp} | {err_short} | {error_type} | {cause_short} | {fix_short} | {species} | {tissue} | {severity} |"

    # 追加行
    updated_log = existing_log.rstrip() + "\n" + new_row + "\n"
    _write_file(log_path, updated_log)

    # 2. 如果是新错误模式，追加到 SKILL.md 的 Common Issues 表
    skill_md_path = os.path.join(skill_dir, "SKILL.md")
    skill_md = _read_file(skill_md_path)
    common_issues_added = False

    if skill_md and not is_duplicate:
        # 找 Common Issues 表
        issues_pattern = r'(##\s*Common Issues\s*\n\s*\|.*?\n.*?\n)'
        if re.search(issues_pattern, skill_md):
            # 追加行到表
            issue_row = f"| {err_short[:50]} | {cause_short[:40]} | {fix_short[:50]} |"
            skill_md = re.sub(
                issues_pattern,
                lambda m: m.group(0).rstrip() + "\n" + issue_row + "\n",
                skill_md
            )
            _write_file(skill_md_path, skill_md)
            common_issues_added = True
        else:
            # 没有 Common Issues 表，在 References 前插入
            issue_section = f"""
## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| {err_short[:50]} | {cause_short[:40]} | {fix_short[:50]} |

"""
            if "## References" in skill_md:
                skill_md = skill_md.replace("## References", issue_section + "\n## References")
            else:
                skill_md += "\n" + issue_section
            _write_file(skill_md_path, skill_md)
            common_issues_added = True

    # 3. 更新 skill.json
    skill_json_path = os.path.join(skill_dir, "skill.json")
    if os.path.exists(skill_json_path):
        try:
            with open(skill_json_path, "r", encoding="utf-8") as f:
                sj = json.load(f)
            sj["error_count"] = sj.get("error_count", 0) + 1
            # 追加到 errors 列表
            if "errors" not in sj:
                sj["errors"] = []
            sj["errors"].append({
                "timestamp": timestamp,
                "error_type": error_type,
                "message": error_message[:200],
                "root_cause": root_cause[:200],
                "fix_applied": fix_applied[:200],
                "species": species,
                "tissue": tissue,
                "script": script_name,
                "severity": severity,
            })
            with open(skill_json_path, "w", encoding="utf-8") as f:
                json.dump(sj, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # 4. 同步到 hermes_home
    _sync_to_hermes_home(skill_name, skill_dir)

    return {
        "success": True,
        "action": "record_error",
        "skill": skill_name,
        "is_duplicate": is_duplicate,
        "error_log_updated": True,
        "common_issues_updated": common_issues_added,
        "skill_json_updated": True,
        "message": f"Error recorded in {skill_name}/logs/error_log.md" +
                   (" (duplicate — recurrence noted)" if is_duplicate else " (new pattern — added to Common Issues)")
    }


# ─── 1b. QUERY LOGS ───────────────────────────────

def _query_logs(skill_name: str, species: str = "", tissue: str = "",
                direction: str = "", script_name: str = "") -> Dict[str, Any]:
    """查同类运行日志：skill.json 的 proven_params + logs/error_log.md + references/"""
    skill_dir = _get_skill_dir(skill_name)
    if not skill_dir:
        return {"success": False, "error": f"Skill '{skill_name}' not found"}

    result = {
        "success": True,
        "action": "query_logs",
        "skill": skill_name,
        "query": {"species": species, "tissue": tissue, "direction": direction, "script": script_name},
        "proven_runs": [],
        "known_errors": [],
        "references": [],
        "summary": "",
    }

    # 1. 读取 skill.json 的 proven_params
    skill_json_path = os.path.join(skill_dir, "skill.json")
    if os.path.exists(skill_json_path):
        try:
            with open(skill_json_path, "r", encoding="utf-8") as f:
                sj = json.load(f)
            proven = sj.get("proven_params", [])
            for p in proven:
                if species and p.get("species") and species.lower() not in p["species"].lower():
                    continue
                if tissue and p.get("tissue") and tissue.lower() not in p["tissue"].lower():
                    continue
                if direction and p.get("direction") and direction.lower() not in p["direction"].lower():
                    continue
                result["proven_runs"].append(p)
        except Exception:
            pass

    # 2. 读取 error_log.md
    error_log_path = os.path.join(skill_dir, "logs", "error_log.md")
    if os.path.exists(error_log_path):
        try:
            with open(error_log_path, "r", encoding="utf-8") as f:
                error_content = f.read()
            entries = re.split(r'##\s+ERROR\s+#', error_content)
            for entry in entries[1:]:
                lines = entry.strip().split(chr(10))
                err = {"raw": "## ERROR #" + entry.strip()[:500]}
                for line in lines:
                    line = line.strip()
                    if line.startswith("- **Error Type**:"):
                        err["error_type"] = line.replace("- **Error Type**:", "").strip()
                    elif line.startswith("- **Species**:"):
                        err["species"] = line.replace("- **Species**:", "").strip()
                    elif line.startswith("- **Root Cause**:"):
                        err["root_cause"] = line.replace("- **Root Cause**:", "").strip()
                    elif line.startswith("- **Fix**:"):
                        err["fix"] = line.replace("- **Fix**:", "").strip()
                result["known_errors"].append(err)
        except Exception:
            pass

    # 3. 读取 references/ 目录
    refs_dir = os.path.join(skill_dir, "references")
    if os.path.isdir(refs_dir):
        for ref_file in os.listdir(refs_dir):
            if ref_file.endswith(".md"):
                result["references"].append({"file": ref_file, "path": os.path.join(refs_dir, ref_file)})

    # 4. 生成摘要
    n_proven = len(result["proven_runs"])
    n_errors = len(result["known_errors"])
    n_refs = len(result["references"])
    parts = []
    if n_proven:
        parts.append(f"{n_proven} 个成功运行记录")
    if n_errors:
        parts.append(f"{n_errors} 个已知错误")
    if n_refs:
        parts.append(f"{n_refs} 个参考文档")
    if parts:
        result["summary"] = f"找到 {', '.join(parts)}。参考 proven_runs 中的参数和 known_errors 中的修复方案。"
    else:
        result["summary"] = "无历史运行记录，按 skill 的原始脚本和参数执行。"

    return result


# ─── 2. RECORD SUCCESS ────────────────────────────

def _record_success(skill_name: str, script_name: str = "", params_used: str = "",
                    species: str = "", tissue: str = "", direction: str = "",
                    result_summary: str = "", score: float = 0.0) -> Dict[str, Any]:
    """记录成功脚本到 Proven Scripts + skill.json"""
    skill_dir = _get_skill_dir(skill_name)
    if not skill_dir:
        return {"success": False, "error": f"Skill '{skill_name}' not found"}

    timestamp = datetime.now().strftime("%Y-%m-%d")
    skill_md_path = os.path.join(skill_dir, "SKILL.md")
    skill_md = _read_file(skill_md_path)

    # 1. 更新 Proven Scripts 表
    proven_added = False
    if skill_md:
        proven_pattern = r'(##\s*Proven Scripts\s*\n\s*\|.*?\n.*?\n)'
        if re.search(proven_pattern, skill_md):
            proven_row = f"| {species or '-'} | {tissue or '-'} | {direction or '-'} | {timestamp} | {score} |"
            skill_md = re.sub(
                proven_pattern,
                lambda m: m.group(0).rstrip() + "\n" + proven_row + "\n",
                skill_md
            )
            _write_file(skill_md_path, skill_md)
            proven_added = True

    # 2. 更新 skill.json
    skill_json_path = os.path.join(skill_dir, "skill.json")
    json_updated = False
    if os.path.exists(skill_json_path):
        try:
            with open(skill_json_path, "r", encoding="utf-8") as f:
                sj = json.load(f)
            sj["success_count"] = sj.get("success_count", 0) + 1
            sj["proven_script"] = script_name
            if sj.get("proven_params") is None:
                sj["proven_params"] = []
            sj["proven_params"].append({
                "species": species,
                "tissue": tissue,
                "direction": direction,
                "script": script_name,
                "params": params_used,
                "date": timestamp,
                "score": score,
                "result": result_summary[:200],
            })
            with open(skill_json_path, "w", encoding="utf-8") as f:
                json.dump(sj, f, indent=2, ensure_ascii=False)
            json_updated = True
        except Exception:
            pass

    # 3. 同步到 hermes_home
    _sync_to_hermes_home(skill_name, skill_dir)

    return {
        "success": True,
        "action": "record_success",
        "skill": skill_name,
        "proven_scripts_updated": proven_added,
        "skill_json_updated": json_updated,
        "message": f"Success recorded: {script_name} for {species}/{tissue}/{direction}"
    }


# ─── 3. UPDATE SCRIPT ─────────────────────────────

def _update_script(skill_name: str, script_name: str, fixed_script_path: str,
                   reason: str = "") -> Dict[str, Any]:
    """用修复后的脚本覆盖原脚本，备份旧版本"""
    skill_dir = _get_skill_dir(skill_name)
    if not skill_dir:
        return {"success": False, "error": f"Skill '{skill_name}' not found"}

    target_script = os.path.join(skill_dir, "scripts", script_name)
    if not os.path.exists(target_script):
        return {"success": False, "error": f"Script '{script_name}' not found in {skill_dir}/scripts/"}

    if not os.path.exists(fixed_script_path):
        return {"success": False, "error": f"Fixed script not found: {fixed_script_path}"}

    # 1. 备份旧版本
    backup_dir = os.path.join(skill_dir, "scripts", ".backups")
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{script_name}.{timestamp}.bak"
    backup_path = os.path.join(backup_dir, backup_name)
    shutil.copy2(target_script, backup_path)

    # 2. 用修复后的脚本覆盖
    shutil.copy2(fixed_script_path, target_script)

    # 3. 记录更新
    logs_dir = _ensure_logs_dir(skill_dir)
    update_log_path = os.path.join(logs_dir, "script_updates.md")
    existing = _read_file(update_log_path)
    if not existing:
        existing = "# Script Update Log\n\n> Record of script fixes applied during analysis.\n\n"
    new_entry = f"- **{timestamp}** `{script_name}` — Reason: {reason or 'bug fix'} — Backup: `{backup_name}`\n"
    _write_file(update_log_path, existing.rstrip() + "\n" + new_entry + "\n")

    # 4. 同步到 hermes_home
    _sync_to_hermes_home(skill_name, skill_dir)

    return {
        "success": True,
        "action": "update_script",
        "skill": skill_name,
        "script": script_name,
        "backup": backup_name,
        "message": f"Script '{script_name}' updated. Old version backed up as '{backup_name}'."
    }


# ─── SYNC ─────────────────────────────────────────

def _sync_to_hermes_home(skill_name: str, skill_dir: str):
    """同步更新到 hermes_home/skills/bioinformatics/<skill_name>/"""
    target = f"E:/MemOmics-Agent/hermes_home/skills/bioinformatics/{skill_name}"
    if os.path.isdir(target) and os.path.isdir(skill_dir):
        try:
            # 只同步 .md, .json, logs/
            for item in ["SKILL.md", "skill.json"]:
                src = os.path.join(skill_dir, item)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(target, item))
            # 同步 logs
            src_logs = os.path.join(skill_dir, "logs")
            dst_logs = os.path.join(target, "logs")
            if os.path.isdir(src_logs):
                if not os.path.isdir(dst_logs):
                    os.makedirs(dst_logs)
                for f in os.listdir(src_logs):
                    shutil.copy2(os.path.join(src_logs, f), os.path.join(dst_logs, f))
            # 同步 scripts
            src_scripts = os.path.join(skill_dir, "scripts")
            dst_scripts = os.path.join(target, "scripts")
            if os.path.isdir(src_scripts):
                if not os.path.isdir(dst_scripts):
                    os.makedirs(dst_scripts)
                for f in os.listdir(src_scripts):
                    if not f.startswith("."):
                        shutil.copy2(os.path.join(src_scripts, f), os.path.join(dst_scripts, f))
        except Exception:
            pass


# ─── MAIN ENTRY ───────────────────────────────────

def skill_evolution(action: str = "record_error",
                    skill_name: str = "",
                    error_message: str = "",
                    error_type: str = "",
                    root_cause: str = "",
                    fix_applied: str = "",
                    fix_code: str = "",
                    script_name: str = "",
                    fixed_script_path: str = "",
                    params_used: str = "",
                    species: str = "",
                    tissue: str = "",
                    direction: str = "",
                    result_summary: str = "",
                    score: float = 0.0,
                    severity: str = "medium",
                    reason: str = "") -> str:
    """
    MemOmics Skill 自进化引擎

    Args:
        action: "record_error" | "record_success" | "update_script"
        skill_name: Skill 名称 (如 "atac-seq", "scrnaseq-seurat-core-analysis")
        error_message: 错误信息 (record_error)
        error_type: 错误类型 (missing_package, memory, syntax, logic, ...)
        root_cause: 根因分析
        fix_applied: 修复方案描述
        fix_code: 修复代码
        script_name: 出错/成功的脚本名
        fixed_script_path: 修复后脚本路径 (update_script)
        params_used: 使用的参数 (record_success)
        species: 物种
        tissue: 组织
        direction: 研究方向
        result_summary: 结果摘要 (record_success)
        score: 质量评分 0-10 (record_success)
        severity: 严重程度 critical/high/medium/low
        reason: 更新原因 (update_script)

    Returns:
        JSON string with result
    """
    if action == "record_error":
        result = _record_error(
            skill_name=skill_name,
            error_message=error_message,
            error_type=error_type,
            root_cause=root_cause,
            fix_applied=fix_applied,
            fix_code=fix_code,
            species=species,
            tissue=tissue,
            direction=direction,
            script_name=script_name,
            severity=severity,
        )
    elif action == "record_success" or action == "record_run":
        # record_run 是 record_success 的别名（SOUL.md 铁律使用 record_run）
        result = _record_success(
            skill_name=skill_name,
            script_name=script_name,
            params_used=params_used,
            species=species,
            tissue=tissue,
            direction=direction,
            result_summary=result_summary,
            score=score,
        )
    elif action == "query_logs":
        result = _query_logs(
            skill_name=skill_name,
            species=species,
            tissue=tissue,
            direction=direction,
            script_name=script_name,
        )
    elif action == "update_script":
        result = _update_script(
            skill_name=skill_name,
            script_name=script_name,
            fixed_script_path=fixed_script_path,
            reason=reason,
        )
    else:
        result = {"success": False, "error": f"Unknown action: {action}. Use: record_error, record_success, record_run, query_logs, update_script"}

    return json.dumps(result, ensure_ascii=False, indent=2)


# ─── HERMES TOOL REGISTRATION ──────────────────────
# 注意：必须用 OpenAI function-calling 格式 (name + description + parameters 嵌套)，
# 不能把 properties 直接放顶层，否则 registry.get_definitions() 传给 LLM 的
# function.parameters.properties 会是空的，LLM 看不到任何参数。
SCHEMA = {
    "name": "skill_evolution",
    "description": (
        "MemOmics 自进化核心工具。原脚本永远不被修改，所有经验以运行日志形式累积。\n"
        "必须调用的时机：\n"
        "1. 跑脚本前 → query_logs（查同类运行日志，参考已有经验，避免重复踩坑）\n"
        "2. rail_review(post) 通过 → record_run（记录成功运行日志：参数/结果/质量）\n"
        "3. rail_review(post) 失败 → record_error（记录错误日志：报错/根因/修复方案）\n"
        "Actions: record_error, record_success/record_run, query_logs, update_script。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["record_error", "record_success", "record_run", "query_logs", "update_script"],
                "description": "record_error: 记录错误+根因+修复方案到skill; record_success/record_run: 记录成功脚本+参数到proven scripts; query_logs: 查同类运行日志拿历史经验; update_script: 用修复后的脚本覆盖原脚本并备份",
            },
            "skill_name": {
                "type": "string",
                "description": "Skill 名称, 如 atac-seq, scrnaseq-seurat-core-analysis",
            },
            "error_message": {"type": "string", "description": "原始错误信息"},
            "error_type": {
                "type": "string",
                "description": "错误类型: missing_package, memory, syntax_error, logic_error, runtime_error, timeout",
            },
            "root_cause": {"type": "string", "description": "根因分析 (LLM生成)"},
            "fix_applied": {"type": "string", "description": "修复方案描述"},
            "fix_code": {"type": "string", "description": "修复代码片段"},
            "script_name": {"type": "string", "description": "出错/成功的脚本名, 如 qc_metrics.R"},
            "fixed_script_path": {"type": "string", "description": "修复后脚本路径 (update_script)"},
            "params_used": {"type": "string", "description": "使用的参数 (record_success/record_run)"},
            "species": {"type": "string", "description": "物种, 如 human"},
            "tissue": {"type": "string", "description": "组织, 如 skeletal_muscle"},
            "direction": {"type": "string", "description": "研究方向, 如 aging"},
            "result_summary": {"type": "string", "description": "结果摘要 (record_success/record_run)"},
            "score": {"type": "number", "description": "质量评分 0-10 (record_success/record_run)"},
            "severity": {
                "type": "string",
                "enum": ["critical", "high", "medium", "low"],
                "description": "严重程度",
            },
            "reason": {"type": "string", "description": "更新原因 (update_script)"},
        },
        "required": ["action", "skill_name"],
    },
}

try:
    from tools.registry import registry

    registry.register(
        name="skill_evolution",
        toolset="memomics",
        schema=SCHEMA,
        handler=lambda args, **kw: skill_evolution(
            action=args.get("action", "record_error"),
            skill_name=args.get("skill_name", ""),
            error_message=args.get("error_message", ""),
            error_type=args.get("error_type", ""),
            root_cause=args.get("root_cause", ""),
            fix_applied=args.get("fix_applied", ""),
            fix_code=args.get("fix_code", ""),
            script_name=args.get("script_name", ""),
            fixed_script_path=args.get("fixed_script_path", ""),
            params_used=args.get("params_used", ""),
            species=args.get("species", ""),
            tissue=args.get("tissue", ""),
            direction=args.get("direction", ""),
            result_summary=args.get("result_summary", ""),
            score=args.get("score", 0.0),
            severity=args.get("severity", "medium"),
            reason=args.get("reason", ""),
        ),
        emoji="🧬",
        max_result_size_chars=40_000,
        description=(
            "MemOmics Skill 自进化引擎: 脚本出错→记录错误+根因+修复方案到skill的error_log.md和Common Issues; "
            "成功→记录proven脚本+参数; 跑前→query_logs查同类经验。 "
            "Actions: record_error(出错), record_success/record_run(成功), query_logs(查经验), update_script(修脚本)。"
            "脚本成功→记录proven script+参数; 修复有效→更新脚本到skill并备份旧版本. "
            "3个action: record_error, record_success, update_script."
        ),
    )
except Exception:
    pass
