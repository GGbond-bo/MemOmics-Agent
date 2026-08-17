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
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("memomics.skill_evolution")


# Holographic memory bridge (lazy import to avoid __init__ chain)
try:
    import importlib.util as _mb_importlib
    _mb_spec = _mb_importlib.spec_from_file_location(
        "memory_bridge",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory_bridge.py")
    )
    _mb = _mb_importlib.module_from_spec(_mb_spec)
    _mb_spec.loader.exec_module(_mb)
    _has_memory_bridge = True
except Exception:
    _has_memory_bridge = False
    _mb = None


def _archive_to_results_log(record: dict, action: str):
    """需求1c：将 record_run/record_error 记录归档到 results/.../log/run_record_*.json"""
    try:
        from memomics.bio_tools.debate_analysis import get_session_results_dir, get_session_sid
        results_dir = get_session_results_dir()
        if not results_dir:
            # 尝试从 session 字典恢复（回退方案）
            sid = get_session_sid()
            if sid:
                import importlib, sys
                # 尝试从 webui.server 的 _sessions 字典获取
                try:
                    server_mod = sys.modules.get("webui.server")
                    if server_mod and hasattr(server_mod, "_sessions"):
                        sess = server_mod._sessions.get(sid, {})
                        results_dir = sess.get("results_dir", "")
                except Exception:
                    pass
        if not results_dir:
            # 最后回退：打印警告，不静默跳过
            import sys as _sys
            print(f"[skill_evolution] WARNING: results_dir is empty, cannot archive {action} record", file=_sys.stderr)
            return
        log_dir = Path(results_dir) / "log"
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        action_tag = "verdict" if action == "record_verdict" else (
            "run" if action in ("record_success", "record_run") else "error")
        archive_path = log_dir / f"run_record_{ts}_{action_tag}.json"
        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # 归档失败不阻断主流程


def _get_skill_dir(skill_name: str) -> Optional[str]:
    """找到 skill 目录（先 skills/ 再 hermes_home/skills/bioinformatics/）"""
    # 动态获取 MemOmics 安装目录
    memomics_root = _get_memomics_root()
    candidates = [
        os.path.join(memomics_root, "skills", skill_name),
        os.path.join(memomics_root, "hermes_home", "skills", "bioinformatics", skill_name),
    ]
    for p in candidates:
        if os.path.isdir(p):
            return p
    return None


def _get_memomics_root() -> str:
    """动态获取 MemOmics 安装根目录"""
    # 1. 从 .install_path 读取
    install_path_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "hermes_home", ".install_path")
    try:
        if os.path.isfile(install_path_file):
            with open(install_path_file, "r", encoding="utf-8") as f:
                root = f.read().strip()
                if os.path.isdir(root):
                    return root
    except Exception:
        pass
    # 2. 回退：从当前文件路径推导
    # memomics/bio_tools/skill_evolution.py → 上三级 → 安装根目录
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
        return {
            "success": True, "action": "query_logs", "skill": skill_name,
            "proven_runs": [], "known_errors": [], "references": [],
            "summary": f"无历史运行记录。skill '{skill_name}' 尚未注册或目录不存在 — 运行后将自动创建记录。",
        }

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

    # 检查是否是重复错误（仅当相同 row 已存在时标记 recurrence）
    err_short = error_message.replace("|", "/")[:80]
    is_duplicate = False
    # 只在表格行内匹配（不匹配 header 文字）
    for row in re.findall(r'^\|.*\|\s*$', existing_log, re.MULTILINE):
        if err_short[:40] in row:
            is_duplicate = True
            break
    if is_duplicate:
        # 更新 recurrence count
        new_row = f"| {timestamp} | {error_message[:60]}... | {error_type} | *(recurrence)* | {fix_applied[:40]} | {species} | {tissue} | {severity} |"
    else:
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

    
    # 3.5. Holographic memory: store error experience
    if _has_memory_bridge and _mb:
        try:
            _mb.store_skill_exp(
                skill_name=skill_name,
                content=f"ERROR [{error_type}] {error_message[:200]} | fix: {fix_applied[:200]}",
                tags=f"error,{error_type},{species},{tissue},{direction},severity-{severity}"
            )
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
        return {
            "success": True, "action": "query_logs", "skill": skill_name,
            "proven_runs": [], "known_errors": [], "references": [],
            "summary": f"无历史运行记录。skill '{skill_name}' 尚未注册或目录不存在 — 运行后将自动创建记录。",
        }

    result = {
        "success": True,
        "action": "query_logs",
        "skill": skill_name,
        "query": {"species": species, "tissue": tissue, "direction": direction, "script": script_name},
        "proven_runs": [],
        "known_errors": [],
        "references": [],
        "summary": "",
        "⚠️_session_warning": "这些日志来自所有历史session，不是当前session专属。仅供参数参考，禁止据此自动启动新任务（铁律-5）！",
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
            for row in re.findall(r'^\|.*\|\s*$', error_content, re.MULTILINE):
                if "---" in row or "| Date |" in row or row.strip().startswith("| Date"):
                    continue
                cols = [c.strip() for c in row.split("|")[1:-1]]
                if len(cols) < 6:
                    continue
                row_species = cols[5] if len(cols) > 5 else ""
                row_tissue = cols[6] if len(cols) > 6 else ""
                err_entry = {
                    "date": cols[0], "error_summary": cols[1], "error_type": cols[2],
                    "root_cause": cols[3], "fix": cols[4], "species": row_species, "tissue": row_tissue,
                }
                if species and row_species and species.lower() not in row_species.lower():
                    continue
                if tissue and row_tissue and tissue.lower() not in row_tissue.lower():
                    continue
                result["known_errors"].append(err_entry)
        except Exception:
            pass

    # 3. 读取 references/ 目录
    refs_dir = os.path.join(skill_dir, "references")
    if os.path.isdir(refs_dir):
        for ref_file in os.listdir(refs_dir):
            if ref_file.endswith(".md"):
                result["references"].append({"file": ref_file, "path": os.path.join(refs_dir, ref_file)})

    # 3.5. Holographic memory: recall experience
    if _has_memory_bridge and _mb:
        try:
            mem = _mb.recall_experience(
                skill_name=skill_name,
                species=species or "",
                tissue=tissue or "",
                direction=direction or "",
            )
            for s in mem.get("proven_scripts", []):
                result["proven_runs"].append({
                    "source": "holographic",
                    "fact_id": s["fact_id"],
                    "content": s["content"],
                    "trust_score": s["trust_score"],
                })
            for e in mem.get("known_errors", []):
                result["known_errors"].append({
                    "source": "holographic",
                    "fact_id": e["fact_id"],
                    "content": e["content"],
                    "trust_score": e["trust_score"],
                })
        except Exception:
            pass

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




# --- 1c. DELIVERY GATE ---

def _verify_delivery_gate(skill_name: str, portal_urls: str = "") -> dict:
    """Create-bio-skill Step 9 delivery gate: 6-item review checklist."""
    results = []
    blocked = []
    skill_dir = _get_skill_dir(skill_name)
    if not skill_dir:
        return {"passed": False, "error": f"Skill '{skill_name}' not found", "checks": [], "blocked": ["skill not found"]}
    skill_md_path = os.path.join(skill_dir, "SKILL.md")
    skill_md = _read_file(skill_md_path) or ""

    # 1. References have URLs?
    refs = skill_md.split("## References")[-1] if "## References" in skill_md else ""
    ok1 = bool(re.search(r'https?://', refs))
    results.append({"check": "official_docs", "passed": ok1, "detail": "Has URLs" if ok1 else "No official URL"})
    if not ok1: blocked.append("Missing official doc URLs in References")

    # 2. When to Use has scenarios?
    when = skill_md.split("## When to Use")[-1].split("## ")[0] if "## When to Use" in skill_md else ""
    ok2 = bool(re.search(r'(should|trigger|use|适用)', when, re.I))
    results.append({"check": "usage_scenarios", "passed": ok2, "detail": "Has scenarios" if ok2 else "No usage scenarios"})
    if not ok2: blocked.append("When to Use missing usage scenarios")

    # 3. Prerequisites have packages? (case-insensitive: "Prerequisites:" or "prerequisites:")
    p = re.search(r'prerequisites', skill_md, re.I)
    ok3 = bool(p and (re.search(r'[a-zA-Z]', skill_md[p.end():p.end()+300])))
    results.append({"check": "prerequisites", "passed": ok3, "detail": "Has packages" if ok3 else "Empty"})
    if not ok3: blocked.append("Prerequisites empty - must list packages")

    # 4. Scripts exist?
    sd = os.path.join(skill_dir, "scripts")
    ok4 = os.path.isdir(sd) and any(f.endswith(('.py','.R')) for f in os.listdir(sd))
    results.append({"check": "scripts_exist", "passed": ok4, "detail": "Has scripts" if ok4 else "No scripts"})
    if not ok4: blocked.append("No runnable scripts found")

    # 5. skill.json exists?
    ok5 = os.path.exists(os.path.join(skill_dir, "skill.json"))
    results.append({"check": "skill_json", "passed": ok5, "detail": "Exists" if ok5 else "Missing"})
    if not ok5: blocked.append("skill.json missing - record_run will silently fail")

    # 6. Proven Scripts table?
    ok6 = bool(re.search(r'##\s*Proven Scripts', skill_md))
    results.append({"check": "proven_table", "passed": ok6, "detail": "Has table" if ok6 else "Missing"})
    if not ok6: blocked.append("Proven Scripts table missing")

    passed = len(blocked) == 0
    return {"passed": passed, "skill": skill_name, "checks": results, "blocked": blocked,
            "message": "GATE PASSED" if passed else "GATE FAILED: %d blocked" % len(blocked)}

# ─── 2. RECORD SUCCESS ────────────────────────────

def _record_success(skill_name: str, script_name: str = "", params_used: str = "",
                    species: str = "", tissue: str = "", direction: str = "",
                    result_summary: str = "", score: float = 0.0,
                    auto_score: float = 0.0, approved: bool = False,
                    custom_script: bool = False) -> Dict[str, Any]:
    """记录成功脚本到 Proven Scripts + skill.json
    
    🆕 auto_score: rail_review 自动技术分 (0-10). 0 表示未评分.
    🆕 approved: 用户是否确认认可. False = 仅存 logs/ 供调试.
    🆕 custom_script: 是否为用户自定义脚本 (figure_scripts/ 或 user_scripts/).
    """
    skill_dir = _get_skill_dir(skill_name)
    if not skill_dir:
        return {
            "success": True, "action": "query_logs", "skill": skill_name,
            "proven_runs": [], "known_errors": [], "references": [],
            "summary": f"无历史运行记录。skill '{skill_name}' 尚未注册或目录不存在 — 运行后将自动创建记录。",
        }

    timestamp = datetime.now().strftime("%Y-%m-%d")
    skill_md_path = os.path.join(skill_dir, "SKILL.md")
    skill_md = _read_file(skill_md_path)

    # 1. 更新 Proven Scripts 表（追加到表尾，不覆盖已有行）
    proven_added = False
    if skill_md:
        # 找到 Proven Scripts section 的表尾位置
        header_match = re.search(r'##\s*Proven Scripts\s*\n', skill_md)
        if not header_match:
            # 🆕 自动创建 Proven Scripts 章节（追加到文件末尾）
            proven_section = """
## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
"""
            skill_md = skill_md.rstrip() + "\n" + proven_section
            _write_file(skill_md_path, skill_md)
            header_match = re.search(r'##\s*Proven Scripts\s*\n', skill_md)
            proven_auto_created = True
        else:
            proven_auto_created = False

        if header_match:
            after_header = skill_md[header_match.end():]
            # 找到 section 结束：下一个 ## heading 或 --- 分隔线或文件尾
            sec_end_marker = re.search(r'\n(?:##\s|---)', after_header)
            sec_end = header_match.end() + (sec_end_marker.start() + 1 if sec_end_marker else len(after_header))
            section = skill_md[header_match.start():sec_end]
            # 确认 section 中有表格行
            if re.search(r'^\|.*\|\s*$', section, re.MULTILINE):
                # 🆕 8-column format: 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔
                user_score_str = str(score) if approved and score > 0 else "-"
                auto_score_str = str(auto_score) if auto_score > 0 else "-"
                approved_str = "✅" if approved else ""
                script_short = os.path.basename(script_name) if script_name else "-"
                proven_row = f"| {species or '-'} | {tissue or '-'} | {direction or '-'} | {timestamp} | {script_short} | {auto_score_str} | {user_score_str} | {approved_str} |"
                # 在 section 末尾（下一个 ## 之前）追加新行
                skill_md = skill_md[:sec_end] + proven_row + "\n" + skill_md[sec_end:]
                _write_file(skill_md_path, skill_md)
                proven_added = True

    # 2. 更新 skill.json
    skill_json_path = os.path.join(skill_dir, "skill.json")
    json_updated = False
    if os.path.exists(skill_json_path):
        try:
            with open(skill_json_path, "r", encoding="utf-8") as f:
                sj = json.load(f)
            # 🔧 P2-3 修复(2026-08-01): 去重 — 同一天+同脚本+同物种/组织/方向不重复记录
            # 之前: deg-analysis 同一 MAST 错误被记录3次
            existing = sj.get("proven_params") or []
            dup = any(
                e.get("script") == script_name
                and e.get("date") == timestamp
                and e.get("species") == species
                and e.get("tissue") == tissue
                and e.get("direction") == direction
                for e in existing
            )
            if dup:
                logger.info(f"skill_evolution: duplicate run for {skill_name} {script_name} {timestamp}, skipped")
                return {
                    "success": True, "action": "record_run", "skill": skill_name,
                    "summary": f"重复运行记录已跳过 (同一天+同脚本+同参数): {script_name}",
                    "deduplicated": True,
                }
            # 🆕 记录 auto_score + approved + user_prefs
            sj["success_count"] = sj.get("success_count", 0) + 1
            sj["proven_script"] = script_name
            if sj.get("proven_params") is None:
                sj["proven_params"] = []
            entry = {
                "species": species,
                "tissue": tissue,
                "direction": direction,
                "script": script_name,
                "params": params_used,
                "date": timestamp,
                "score": score,
                "auto_score": auto_score,
                "approved": approved,
                "custom_script": custom_script,
                "result": result_summary[:200],
            }
            sj["proven_params"].append(entry)
            # 🆕 更新 user_prefs 的 last_used_script
            if "user_prefs" not in sj:
                sj["user_prefs"] = {}
            sj["user_prefs"]["last_used_script"] = script_name
            with open(skill_json_path, "w", encoding="utf-8") as f:
                json.dump(sj, f, indent=2, ensure_ascii=False)
            json_updated = True
        except Exception:
            pass

    
    # 3.5. Holographic memory: store script score
    if _has_memory_bridge and _mb and script_name:
        try:
            _mb.store_script_score(
                skill_name=skill_name,
                script_name=script_name,
                user_score=int(score) if score else 0,
                auto_score=int(auto_score) if auto_score else 0,
                species=species or "",
                tissue=tissue or "",
                direction=direction or "",
                approved=approved,
                notes=result_summary[:200] if result_summary else ""
            )
            if result_summary:
                _mb.store_skill_exp(
                    skill_name=skill_name,
                    content=f"{species}/{tissue}/{direction}: {result_summary[:200]}",
                    tags=f"{species},{tissue},{direction},success"
                )
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

def _record_verdict(skill_name: str = "", topic: str = "",
                    verdict: str = "", recommended_params: str = "",
                    confidence: float = 0.0, evidence: str = "") -> dict:
    """P1(2026-08-10): 辩论裁决回流 — verdict → skill.json debate_verdicts 沉淀。

    由 debate_analysis 成功返回后自动调用，也可由 agent 手动触发。
    - skill_name 非空时：写入 skill_dir/skill.json 的 debate_verdicts 数组（带 evidence）
    - 无论 skill_name 是否为空，都会归档到 results/.../log/run_record_*_verdict.json
    - 去重：同一 topic+verdict 摘要前 50 字不重复追加
    """
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "topic": topic,
        "verdict": (verdict or "")[:500],
        "recommended_params": recommended_params,
        "confidence": confidence,
        "evidence": (evidence or "")[:300],
        "date": timestamp,
    }
    skill_updated = False
    if skill_name:
        skill_dir = _get_skill_dir(skill_name)
        if skill_dir:
            skill_json_path = os.path.join(skill_dir, "skill.json")
            try:
                if os.path.exists(skill_json_path):
                    with open(skill_json_path, "r", encoding="utf-8") as f:
                        sj = json.load(f)
                else:
                    sj = {}
                verdicts = sj.get("debate_verdicts") or []
                dup = any(
                    e.get("topic") == topic
                    and e.get("verdict", "")[:50] == entry["verdict"][:50]
                    for e in verdicts
                )
                if not dup:
                    verdicts.append(entry)
                    sj["debate_verdicts"] = verdicts
                    with open(skill_json_path, "w", encoding="utf-8") as f:
                        json.dump(sj, f, indent=2, ensure_ascii=False)
                    skill_updated = True
            except Exception as e:
                logger.warning(f"record_verdict: skill.json update failed: {e}")
    return {
        "success": True,
        "action": "record_verdict",
        "skill": skill_name,
        "skill_json_updated": skill_updated,
        "verdict_archived": True,
        "entry": entry,
        "note": "裁决已归档（run_record_*_verdict.json）；skill_name 非空且 skill.json 存在时同步沉淀到 debate_verdicts。",
    }


def _update_script(skill_name: str, script_name: str, fixed_script_path: str,
                   reason: str = "") -> Dict[str, Any]:
    """用修复后的脚本覆盖原脚本，备份旧版本"""
    skill_dir = _get_skill_dir(skill_name)
    if not skill_dir:
        return {
            "success": True, "action": "query_logs", "skill": skill_name,
            "proven_runs": [], "known_errors": [], "references": [],
            "summary": f"无历史运行记录。skill '{skill_name}' 尚未注册或目录不存在 — 运行后将自动创建记录。",
        }

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


# ─── 4. REGISTER SKILL ────────────────────────────

# Stop words: overly generic terms filtered from auto-expansion
_EN_GENERIC = {
    "scoring", "analysis", "data", "pipeline", "based", "tool",
    "method", "model", "result", "test", "sample", "run",
    "processing", "detection", "identification", "inference",
}
_CN_GENERIC = {
    "细胞", "分类", "分析", "数据", "工具", "方法", "结果",
    "样本", "处理", "检测", "模型",
    # 过于泛化的 bigram
    "深度",  # 深度学习/深度测序/深度分析
    "推断",  # 统计推断/轨迹推断/推断分析
    "学习",  # 深度学习/机器学习
    "时间",  # 伪时间/时间序列/时间点
}


def _expand_keywords(keywords: str) -> str:
    """Derive short keywords from compound ones to boost hit coverage.

    ZH: 4+ char words → 2-char bigram expansion ("衰老分类" → appends "衰老")
    EN: multi-word phrases → word splitting ("senescence scoring" → appends "senescence")
    Filters generic stop-words to prevent false positives ("scoring", "细胞", etc.)
    """
    raw_kws = [kw.strip().strip('"') for kw in keywords.split("/")]
    expanded = set(raw_kws)

    for kw in raw_kws:
        if re.search(r'[\u4e00-\u9fff]', kw):
            if len(kw) >= 4:
                for i in range(len(kw) - 1):
                    bigram = kw[i:i+2]
                    # 🆕 只有纯中文 bigram 才加入(过滤 VA/AE 等 ASCII 碎片)
                    if bigram not in expanded and len(bigram) == 2 \
                            and re.match(r'^[\u4e00-\u9fff]{2}$', bigram) \
                            and bigram not in _CN_GENERIC:
                        expanded.add(bigram)
        elif ' ' in kw:
            for w in kw.lower().split():
                w_stripped = w.strip('()[]{}')
                if len(w_stripped) >= 3 and w_stripped != kw \
                        and w_stripped not in _EN_GENERIC:
                    expanded.add(w_stripped)

    # 交叉词印证过滤：中文 bigram 必须被 >=2 个原始关键词包含才保留
    bigram_candidates = expanded - set(raw_kws)
    validated = set()
    for bg in bigram_candidates:
        if re.match(r'^[一-鿿]{2}$', bg):
            count = sum(1 for kw in raw_kws if bg in kw)
            if count >= 2:
                validated.add(bg)
        else:
            validated.add(bg)
    expanded = set(raw_kws) | validated

    ordered = raw_kws + sorted(expanded - set(raw_kws), key=len)
    return " / ".join(f'"{k}"' for k in ordered)


def _register_skill(skill_name: str, keywords: str = "",
                    trigger_level: str = "RED 必触发",
                    category: str = "") -> Dict[str, Any]:
    """注册新 skill 到 SOUL.md 的 AUTO_SKILL_INSERT_MARKER 上方，使下次可自动触发。"""
    memomics_root = _get_memomics_root()
    soul_path = os.path.join(memomics_root, "hermes_home", "SOUL.md")
    if not os.path.exists(soul_path):
        return {"success": False, "error": f"SOUL.md not found at {soul_path}"}

    soul_md = _read_file(soul_path)
    if not soul_md:
        return {"success": False, "error": "Failed to read SOUL.md"}

    # 检查是否已注册
    if f'skill_view("{skill_name}")' in soul_md:
        return {
            "success": True,
            "action": "register_skill",
            "skill": skill_name,
            "already_registered": True,
            "message": f"Skill '{skill_name}' already registered in SOUL.md"
        }

    # 生成关键词（未提供则用 skill_name）
    if not keywords:
        keywords = f'"{skill_name}"'

    # 构建触发行（与 SOUL.md 必触发表格式一致）
    trigger_row = f'| {keywords} | `skill_view("{skill_name}")` |'

    # 插入到 AUTO_SKILL_INSERT_MARKER 上方
    marker = "<!-- AUTO_SKILL_INSERT_MARKER -->"
    if marker not in soul_md:
        return {"success": False, "error": "AUTO_SKILL_INSERT_MARKER not found in SOUL.md"}

    # 自动扩展关键词：从 "衰老分类" 派生 "衰老"，从 "senescence scoring" 派生 "senescence"
    keywords = _expand_keywords(keywords)

    # ===== Gate: minimum keyword check =====
    kw_parts = [k.strip().strip('"').strip() for k in keywords.split("/") if k.strip().strip('"').strip()]
    if len(kw_parts) < 4:
        return {
            "success": False,
            "action": "register_skill",
            "skill": skill_name,
            "error": f"KEYWORD_GATE_FAILED: only {len(kw_parts)} keywords ({keywords}). "
                     f"Need >=4 (Chinese + English mixed). "
                     f"Add more from SKILL.md When to Use / metadata.tags / package name / function description.",
            "hint": "Example minimum: '\"包名\" / \"功能中文\" / \"package_name\" / \"function_english\"'"
        }
    # Warning (non-blocking) for <5 keywords
    if len(kw_parts) < 5:
        logger.warning(f"register_skill: only {len(kw_parts)} keywords for '{skill_name}'. Recommend >=5.")

    # 重新构建触发行（使用扩展后的关键词）
    trigger_row = f'| {keywords} | `skill_view("{skill_name}")` |'

    # ===== 去重: 检查手写触发表中是否已存在相同的 skill_view =====
    existing_pattern = f'skill_view(\\"{skill_name}\\")'
    if re.search(existing_pattern, soul_md):
        return {
            "success": True,
            "action": "register_skill",
            "skill": skill_name,
            "already_registered": True,
            "message": f"Skill '{skill_name}' already in trigger table (not re-inserting)"
        }

    soul_md = soul_md.replace(marker, trigger_row + "\n" + marker)
    if not _write_file(soul_path, soul_md):
        return {"success": False, "error": "Failed to write SOUL.md"}

    return {
        "success": True,
        "action": "register_skill",
        "skill": skill_name,
        "keywords": keywords,
        "trigger_level": trigger_level,
        "soul_md_updated": True,
        "message": (
            f"Skill '{skill_name}' 已注册到 SOUL.md。"
            f"关键词: {keywords}。重启 server 后 SKILLS_INDEX.md 将自动重建。"
            f"验证: grep 'skill_view(\"{skill_name}\")' hermes_home/SOUL.md"
        )
    }


# ─── SYNC ─────────────────────────────────────────

def _copy_with_retry(src, dst, max_retries=3, delay=0.5):
    """带重试的文件复制，处理 Windows 文件锁"""
    for attempt in range(max_retries):
        try:
            shutil.copy2(src, dst)
            return
        except (PermissionError, OSError):
            if attempt < max_retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                raise


def _sync_to_hermes_home(skill_name: str, skill_dir: str):
    """同步更新到 hermes_home/skills/bioinformatics/<skill_name>/ — 动态推导路径"""
    try:
        memomics_root = _get_memomics_root()
        target = os.path.join(memomics_root, "hermes_home", "skills", "bioinformatics", skill_name)
        # 如果 hermes_home 中不存在，自动创建并全量复制（修复 skill_manage 写到 ~/.hermes 的 bug）
        if not os.path.isdir(target) and os.path.isdir(skill_dir):
            shutil.copytree(skill_dir, target)
            return
        if os.path.isdir(target) and os.path.isdir(skill_dir):
            # 只同步 .md, .json, logs/ — 添加重试机制处理 Windows 文件锁
            for item in ["SKILL.md", "skill.json"]:
                src = os.path.join(skill_dir, item)
                if os.path.exists(src):
                    _copy_with_retry(src, os.path.join(target, item))
            # 同步 logs
            src_logs = os.path.join(skill_dir, "logs")
            dst_logs = os.path.join(target, "logs")
            if os.path.isdir(src_logs):
                if not os.path.isdir(dst_logs):
                    os.makedirs(dst_logs, exist_ok=True)
                for f in os.listdir(src_logs):
                    _copy_with_retry(os.path.join(src_logs, f), os.path.join(dst_logs, f))
            # 同步 scripts
            src_scripts = os.path.join(skill_dir, "scripts")
            dst_scripts = os.path.join(target, "scripts")
            if os.path.isdir(src_scripts):
                if not os.path.isdir(dst_scripts):
                    os.makedirs(dst_scripts)
                for f in os.listdir(src_scripts):
                    if not f.startswith("."):
                        shutil.copy2(os.path.join(src_scripts, f), os.path.join(dst_scripts, f))
    except Exception as e:
        import sys
        print(f"[skill_evolution] WARNING: sync to hermes_home failed for '{skill_name}': {e}", file=sys.stderr)


# ─── MAIN ENTRY ───────────────────────────────────

def _flow_run_params_to_kb(species: str = "", tissue: str = "", direction: str = "",
                          skill_name: str = "", params_used: str = "",
                          result_summary: str = "", quality_score: float = 0) -> str:
    """record_run 成功后把高分实测参数回流知识库（2026-08-14，非阻塞）。

    条件: 物种/组织/方向/参数齐全 + quality_score >= 8。
    落点: knowledge_base/<Species>/<tissue>/<direction>/03_测序方法/RNA/<skill>_empirical.yaml
    铁轨: source=data_driven + evidence=run log（save_knowledge 内部强制）。
    """
    try:
        _score = 0.0
        try:
            _score = float(quality_score or 0)
        except Exception:
            pass
        if _score < 8:
            return "skipped: score<8"
        if not (species and tissue and direction and skill_name and params_used):
            return "skipped: missing context"
        from memomics.bio_tools.save_knowledge import save_knowledge
        _content = (
            f"skill: {skill_name}\nquality_score: {_score}\n\n"
            f"params_used:\n{params_used}\n\nresult_summary:\n{result_summary}"
        )
        _r = save_knowledge(
            name=f"{skill_name}_empirical", content=_content,
            source="data_driven", evidence=f"record_run({skill_name}): {str(result_summary)[:200]}",
            verified="partially_verified",
            species=species, tissue=tissue, direction=direction,
            kb_category="03_测序方法", assay_type="RNA",
        )
        logger.info("[KB-FLOW] record_run 参数回流: %s", str(_r)[:200])
        return _r
    except Exception as e:
        logger.warning(f"[KB-FLOW] 回流失败(非阻塞): {e}")
        return "error"


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
                    auto_score: float = 0.0,
                    approved: bool = False,
                    severity: str = "medium",
                    reason: str = "",
                    keywords: str = "",
                    trigger_level: str = "RED 必触发",
                    category: str = "",
                    topic: str = "") -> str:
    """
    MemOmics Skill 自进化引擎

    Args:
        action: "record_error" | "record_success" | "update_script" | "register_skill"
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
        score: 质量评分 0-10 (record_success) — user score，只有 approved=True 才入表
        auto_score: rail_review 自动技术分 0-10 (record_success)，0=未评分
        approved: 用户是否确认认可
        severity: 严重程度 critical/high/medium/low
        reason: 更新原因 (update_script)
        keywords: SOUL.md 命中关键词 (register_skill), 如 '"scTour" / "深度伪时间"'
        trigger_level: 触发级别 RED必触发/YEL讨论触发/GRN按需触发/WHT系统级
        category: skill 分类 (register_skill)

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
            auto_score=auto_score,
            approved=approved,
        )
        # 2026-08-14: 高分实测参数自动回流知识库（非阻塞，失败不影响 record）
        try:
            _flow_run_params_to_kb(
                species=species, tissue=tissue, direction=direction,
                skill_name=skill_name, params_used=params_used,
                result_summary=result_summary, quality_score=score or auto_score)
        except Exception:
            pass
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
    elif action == "record_verdict":
        # P1(2026-08-10): 辩论裁决回流 — verdict → skill.json debate_verdicts 沉淀
        # 由 debate_analysis 成功返回后自动调用（带 evidence），也可由 agent 手动触发
        result = _record_verdict(
            skill_name=skill_name,
            topic=topic,
            verdict=result_summary,
            recommended_params=params_used,
            confidence=score,
            evidence=reason,
        )
    elif action == "verify_delivery_gate":
        result = _verify_delivery_gate(
            skill_name=args.get("skill_name", args.get("skill", "")),
            portal_urls=args.get("portal_urls", "")
        )
    elif action == "register_skill":
        result = _register_skill(
            skill_name=skill_name,
            keywords=keywords,
            trigger_level=trigger_level,
            category=category,
        )
    else:
        result = {"success": False, "error": f"Unknown action: {action}. Use: record_error, record_success, record_run, query_logs, update_script"}

    # 需求1c：record_run/record_error 归档到 results/.../log/
    if action in ("record_error", "record_success", "record_run") and isinstance(result, dict):
        _archive_to_results_log(result, action)

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
        "Actions: record_error, record_success/record_run, query_logs, update_script, record_verdict。"
        "record_verdict 由辩论引擎自动触发（裁决回流），也可手动调用：把辩论裁判的裁决/推荐参数/置信度沉淀到 skill.json 的 debate_verdicts 数组（带 evidence）。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["record_error", "record_success", "record_run", "query_logs", "update_script", "register_skill", "record_verdict"],
                "description": "record_error: 记录错误+根因+修复方案到skill; record_success/record_run: 记录成功脚本+参数到proven scripts; query_logs: 查同类运行日志拿历史经验; update_script: 用修复后的脚本覆盖原脚本并备份; register_skill: 注册新skill到SOUL.md使下次可自动触发; record_verdict: 辩论裁决回流（topic+verdict+推荐参数+置信度+evidence 沉淀到 skill.json debate_verdicts）",
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
            "score": {"type": "number", "description": "质量评分 0-10 (record_success/record_run)；record_verdict 时=裁判置信度 0-1"},
            "severity": {
                "type": "string",
                "enum": ["critical", "high", "medium", "low"],
                "description": "严重程度",
            },
            "reason": {"type": "string", "description": "更新原因 (update_script)；record_verdict 时=evidence（文献/知识库证据）"},
            "topic": {"type": "string", "description": "辩论主题 (record_verdict)，如 'hdWGCNA 软阈值选择'"},
            "keywords": {"type": "string", "description": "SOUL.md 命中关键词 (register_skill), 如 '\"scTour\" / \"深度伪时间\"'"},
            "trigger_level": {
                "type": "string",
                "enum": ["RED 必触发", "YEL 讨论触发", "GRN 按需触发", "WHT 系统级"],
                "description": "触发级别 (register_skill)",
            },
            "category": {"type": "string", "description": "Skill 分类 (register_skill)"},
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
            keywords=args.get("keywords", ""),
            trigger_level=args.get("trigger_level", "RED 必触发"),
            category=args.get("category", ""),
        ),
        emoji="🧬",
        max_result_size_chars=40_000,
        description=(
            "MemOmics Skill 自进化引擎: 脚本出错→记录错误+根因+修复方案到skill的error_log.md和Common Issues; "
            "成功→记录proven脚本+参数; 跑前→query_logs查同类经验; 创建skill后→register_skill注册到SOUL.md使下次可自动触发。 "
            "Actions: record_error(出错), record_success/record_run(成功), query_logs(查经验), update_script(修脚本), register_skill(注册触发)。"
        ),
    )
except Exception:
    pass
