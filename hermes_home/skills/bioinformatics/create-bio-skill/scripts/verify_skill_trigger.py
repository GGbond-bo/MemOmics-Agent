#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""verify_skill_trigger.py — 规则 4e 意图测试门禁（2026-08-10 新增）

创建 skill 后必须运行：验证「用户意图 → SOUL.md 触发表 → skill_view 可加载」全链路。

用法:
    python verify_skill_trigger.py <skill_name> [--intents "意图1|意图2|..."]
    不传 --intents 时从 SOUL.md 注册行自动提取触发关键词作测试意图。

通过标准（全部 PASS 才可交付）:
    1. SOUL.md 触发表包含该 skill（已注册）
    2. 每个测试意图至少命中一个触发关键词
    3. skill_view(name) 可加载（frontmatter 与目录名一致）
"""
import re
import sys
import json
import os

SOUL_PATH = os.environ.get("SOUL_MD_PATH", "hermes_home/SOUL.md")
SKILLS_BASE = os.environ.get("SKILLS_BASE", "hermes_home/skills/bioinformatics")


def extract_trigger_line(soul: str, skill_name: str) -> str | None:
    """从 SOUL.md 触发表找含 skill_name 的行。"""
    for line in soul.split("\n"):
        if skill_name in line and "skill_view" in line:
            return line.strip()
    return None


def extract_keywords(trigger_line: str) -> list:
    """从触发行提取关键词（| "kw1" / "kw2" / ... | `skill_view("name")` | 格式）。

    取行内所有 "..." 片段，排除 skill_view("name") 里的 skill 名。
    """
    kws = re.findall(r'"([^"]+)"', trigger_line)
    # 最后一个引号片段通常是 skill_view("skill-name") 里的名字
    m = re.search(r'skill_view\("([^"]+)"\)', trigger_line)
    if m:
        kws = [k for k in kws if k != m.group(1)]
    return [k.strip() for k in kws if k.strip()]


def check_intent_hit(intent: str, keywords: list) -> tuple:
    """意图是否命中关键词（子串匹配，中英文都算）。"""
    il = intent.lower()
    for kw in keywords:
        if kw.lower() in il:
            return True, kw
    return False, None


def verify_skill(skill_name: str, intents: list | None = None) -> dict:
    results = {"skill": skill_name, "checks": [], "passed": True}
    soul = open(SOUL_PATH, encoding="utf-8").read()

    # ── 检查 1: SOUL.md 注册 ──
    line = extract_trigger_line(soul, skill_name)
    results["checks"].append({
        "name": "SOUL.md 注册", "passed": bool(line),
        "detail": line or "未在触发表中找到",
    })
    if not line:
        results["passed"] = False
        return results

    keywords = extract_keywords(line)
    results["checks"].append({
        "name": "触发关键词提取", "passed": len(keywords) >= 4,
        "detail": f"{len(keywords)} 个: {keywords[:8]}{'...' if len(keywords) > 8 else ''}",
    })
    if len(keywords) < 4:
        results["passed"] = False

    # ── 检查 2: 意图命中（自动从关键词取样 + 用户提供）──
    if not intents:
        intents = [kw for kw in keywords[:5]]
    hits, misses = [], []
    for it in intents:
        ok, kw = check_intent_hit(it, keywords)
        (hits if ok else misses).append((it, kw))
    results["checks"].append({
        "name": "意图命中", "passed": not misses,
        "detail": f"命中 {len(hits)}/{len(intents)} | 未命中: {[m[0] for m in misses][:3]}",
    })
    if misses:
        results["passed"] = False

    # ── 检查 3: skill_view 可加载（frontmatter 一致）──
    md_path = os.path.join(SKILLS_BASE, skill_name, "SKILL.md")
    if os.path.exists(md_path):
        src = open(md_path, encoding="utf-8").read()
        fm_name = re.search(r"^name:\s*(.+)$", src, re.M)
        name_ok = fm_name and fm_name.group(1).strip().strip('"') == skill_name
        desc_ok = bool(re.search(r"^description:\s*.{20,}", src, re.M))
        results["checks"].append({
            "name": "SKILL.md 可加载", "passed": name_ok and desc_ok,
            "detail": f"name匹配={name_ok} description≥20字={desc_ok}",
        })
        if not (name_ok and desc_ok):
            results["passed"] = False
    else:
        results["checks"].append({"name": "SKILL.md 可加载", "passed": False,
                                  "detail": f"{md_path} 不存在"})
        results["passed"] = False

    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python verify_skill_trigger.py <skill_name> [--intents 'a|b|c']")
        sys.exit(2)
    name = sys.argv[1]
    intents = None
    if "--intents" in sys.argv:
        i = sys.argv.index("--intents")
        intents = [x.strip() for x in sys.argv[i + 1].split("|") if x.strip()]
    r = verify_skill(name, intents)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    sys.exit(0 if r["passed"] else 1)
