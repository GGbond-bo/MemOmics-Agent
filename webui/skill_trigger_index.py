# -*- coding: utf-8 -*-
"""触发索引生成器：把 407 个 skill 的「触发词 → 技能」整理成可读、可核对的一页。

为什么需要它：
    SKILLS_INDEX.md 是注入 system prompt 的机器目录（每行都带触发词），但它是
    「按技能罗列」的；当用户说一句「帮我把基金本子排一下版」时，人（和模型）
    很难在 407 行里判断该用哪个。更麻烦的是 RED 层有 24 个关键词被两个以上
    技能共用（基金/标书、写论文、审稿、LaTeX、Illustrator、去 AI 腔、样本量），
    消息级匹配会一次命中多个，靠模型猜。

本模块只做三件事：
    1. 从 skill.json + SOUL.md 必触发表收集触发词（与 SKILLS_INDEX 同源同口径，
       直接复用 webui.skills_registry 的清洗与分节函数）；
    2. 生成 memomics_home/SKILLS_TRIGGERS.md：概览 / RED 总表 / YEL·GRN 清单 /
       歧义与首选 / 质量清单（名称派生、缺中文词、SOUL 未覆盖）；
    3. --check 校验索引与磁盘一致，并在 RED 覆盖不全时 exit 2（可挂 CI）。

用法：
    python -m webui.skill_trigger_index --report     # 只打印统计
    python -m webui.skill_trigger_index --build      # 生成 SKILLS_TRIGGERS.md
    python -m webui.skill_trigger_index --check      # 不一致 exit 2

真源优先级（与 contracts/skill_triggers.json 一致）：
    skill.json#trigger_keywords（人工） > SOUL 必触发表（合并前置） > 名称派生
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

try:
    from webui import skills_registry as R
except ImportError:  # 直接 python webui/skill_trigger_index.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from webui import skills_registry as R

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT_PATH = os.path.join(_ROOT, "contracts", "skill_trigger_index.json")
OUT_PATH = os.path.join(R.MEMOMICS_HOME, "SKILLS_TRIGGERS.md")

LEVEL_LABEL = {"RED": "🔴 必触发", "YEL": "🟡 讨论触发", "GRN": "🟢 按需触发", "WHT": "⚪ 系统级"}
LEVEL_RANK = {"RED": 0, "YEL": 1, "GRN": 2, "WHT": 3}


def _load_contract() -> dict:
    try:
        with open(CONTRACT_PATH, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _iter_skill_jsons():
    root = R.SKILLS_DIR
    if not os.path.isdir(root):
        return
    for top in sorted(os.listdir(root)):
        top_dir = os.path.join(root, top)
        if not os.path.isdir(top_dir):
            continue
        for name in sorted(os.listdir(top_dir)):
            p = os.path.join(top_dir, name, "skill.json")
            if os.path.isfile(p):
                yield name, p


def collect() -> list:
    """收集全部技能的触发信息（与 SKILLS_INDEX 同口径）。"""
    soul_map = R._read_soul_red()
    records = []
    for name, path in _iter_skill_jsons():
        try:
            with open(path, encoding="utf-8") as f:
                sj = json.load(f) or {}
        except Exception:
            continue
        kws = R._split_keywords(sj.get("trigger_keywords")) or []
        soul_kws = soul_map.get(name) or []
        merged = []
        for k in list(soul_kws) + list(kws):
            if k and k not in merged:
                merged.append(k)
        category = str(sj.get("category") or "").lower()
        section = R.CATEGORY_TO_SECTION.get(category, R.DEFAULT_SECTION)
        level = str(sj.get("trigger_level") or ("GRN" if section == "09_内置" else "YEL")).upper()
        if level not in LEVEL_RANK:
            level = "YEL"
        usage = R._clip(R._clean(sj.get("when_to_use") or sj.get("description") or ""), 60)
        records.append({
            "name": name,
            "section": section,
            "level": level,
            "keywords": merged,
            "usage": usage,
            "in_soul": bool(soul_kws),
            "from_soul": soul_kws,
        })
    records.sort(key=lambda r: (
        R.SECTION_ORDER.index(r["section"]) if r["section"] in R.SECTION_ORDER else 99,
        LEVEL_RANK.get(r["level"], 9),
        r["name"].lower(),
    ))
    return records


def find_conflicts(records: list) -> dict:
    """同一关键词被 ≥2 个技能共用 → {kw: [skills]}（大小写归一）。"""
    kw2 = defaultdict(list)
    for r in records:
        for kw in r["keywords"]:
            kw2[kw.strip().lower()].append(r["name"])
    return {k: v for k, v in kw2.items() if len(v) > 1}


def _md_escape(text: str) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def _fmt_kw(kws, limit=None) -> str:
    items = list(kws)
    if limit:
        items = items[:limit]
    return "、".join(_md_escape(k) for k in items) if items else "—"


def render(records: list, contract: dict) -> str:
    preferred = {str(k).lower(): v for k, v in (contract.get("preferred") or {}).items()}
    notes = contract.get("cluster_notes") or {}
    levels = defaultdict(int)
    for r in records:
        levels[r["level"]] += 1
    reds = [r for r in records if r["level"] == "RED"]
    yels = [r for r in records if r["level"] == "YEL"]
    grns = [r for r in records if r["level"] == "GRN"]

    L = []
    L.append("# MemOmics SKILLS_TRIGGERS — 触发索引")
    L.append("")
    L.append("> 自动生成，请勿手改：`python -m webui.skill_trigger_index --build`")
    L.append("> 真源：`skills/<cat>/<name>/skill.json#trigger_keywords/trigger_level` + `SOUL.md` 必触发表；")
    L.append("> 机器目录见 `SKILLS_INDEX.md`（注入 system prompt），本文件是给人看的『一句话 → 哪个 skill』总表。")
    L.append("")
    L.append("## 0. 怎么用这张表")
    L.append("")
    L.append("| 层级 | 谁会读 | 触发方式 |")
    L.append("|---|---|---|")
    L.append("| 🔴 RED | 用户消息 → `server._match_red_skill_hits()` 自动匹配 | 命中即 `skill_view`，不等确认 |")
    L.append("| 🟡 YEL | 模型读 `SKILLS_INDEX` + 本表 | 先讨论/确认方案，再 `skill_view` |")
    L.append("| 🟢 GRN | 用户点名或 `skill_search` | 只有明确提到才用 |")
    L.append("")
    L.append("**命中多个 RED 时**：先看 §4 的『首选』和簇口径；仍不确定 → 问用户一句，别同时 `skill_view` 两个互相冲突的技能。")
    L.append("")
    L.append("## 1. 概览")
    L.append("")
    L.append(f"- 技能总数 **{len(records)}**：🔴 {levels['RED']} / 🟡 {levels['YEL']} / 🟢 {levels['GRN']}"
             + (f" / ⚪ {levels['WHT']}" if levels['WHT'] else ""))
    by_section = defaultdict(int)
    for r in records:
        by_section[r["section"]] += 1
    L.append("- 分节：" + " · ".join(
        f"{R.SECTION_TITLES.get(s, s)} {by_section[s]}" for s in R.SECTION_ORDER if by_section.get(s)))
    L.append(f"- RED 已进 SOUL 必触发表：**{sum(1 for r in reds if r['in_soul'])}/{len(reds)}**")
    name_derived = [r for r in records if r["keywords"] and set(k.lower() for k in r["keywords"])
                    <= set(k.lower() for k in R._name_keywords(r["name"], {}))]
    L.append(f"- 触发词只靠技能名派生（中文说法可能唤不醒）：**{len(name_derived)}** 个，见 §5")
    L.append("")

    # ---- RED
    L.append(f"## 2. 🔴 RED 必触发（{len(reds)}）")
    L.append("")
    for sec in R.SECTION_ORDER:
        rows = [r for r in reds if r["section"] == sec]
        if not rows:
            continue
        L.append(f"### {R.SECTION_TITLES.get(sec, sec)}（{len(rows)}）")
        L.append("")
        L.append("| 触发词 | 技能 | 何时用 |")
        L.append("|---|---|---|")
        for r in rows:
            L.append(f"| {_fmt_kw(r['keywords'], 10)} | `{r['name']}` | {_md_escape(r['usage'])} |")
        L.append("")

    # ---- YEL
    L.append(f"## 3. 🟡 YEL 讨论触发（{len(yels)}）")
    L.append("")
    L.append("> 这些技能不参与消息级自动匹配：先在本节按主题找到候选，再用 `skill_search` / `skill_view`。")
    L.append("")
    for sec in R.SECTION_ORDER:
        rows = [r for r in yels if r["section"] == sec]
        if not rows:
            continue
        L.append(f"### {R.SECTION_TITLES.get(sec, sec)}（{len(rows)}）")
        L.append("")
        L.append("| 技能 | 触发词 |")
        L.append("|---|---|")
        for r in rows:
            L.append(f"| `{r['name']}` | {_fmt_kw(r['keywords'], 8)} |")
        L.append("")

    # ---- GRN
    L.append(f"## 4. 🟢 GRN 按需（{len(grns)}）")
    L.append("")
    if grns:
        L.append("| 技能 | 触发词 |")
        L.append("|---|---|")
        for r in grns:
            L.append(f"| `{r['name']}` | {_fmt_kw(r['keywords'], 8)} |")
    else:
        L.append("（无）")
    L.append("")

    # ---- 歧义
    conflicts = find_conflicts(records)
    red_names = {r["name"] for r in reds}
    red_conf = {k: [n for n in v if n in red_names] for k, v in conflicts.items()}
    red_conf = {k: v for k, v in red_conf.items() if len(v) > 1}
    L.append(f"## 5. ⚠️ RED 歧义与首选（{len(red_conf)} 个关键词）")
    L.append("")
    L.append("同一句话会同时命中多个 RED；下表给出首选（`contracts/skill_trigger_index.json` 维护）。")
    L.append("")
    L.append("| 触发词 | 首选 | 同时命中 |")
    L.append("|---|---|---|")
    for kw in sorted(red_conf):
        who = red_conf[kw]
        pick = preferred.get(kw, "")
        others = [n for n in who if n != pick]
        L.append(f"| {_md_escape(kw)} | {'`' + pick + '`' if pick else '（未指定）'} | "
                 f"{_fmt_kw(others, 6)} |")
    L.append("")
    if notes:
        L.append("### 簇口径（怎么判）")
        L.append("")
        for title, text in notes.items():
            L.append(f"- **{title}**：{_md_escape(text)}")
        L.append("")

    # ---- 质量
    L.append("## 6. 触发词质量清单")
    L.append("")
    no_cjk = [r for r in reds if not any(any('\u4e00' <= ch <= '\u9fff' for ch in k) for k in r["keywords"])]
    L.append(f"- RED 里没有任何中文触发词（中文说法唤不醒）：{_fmt_kw([r['name'] for r in no_cjk]) if no_cjk else '无'}")
    missing_soul = [r["name"] for r in reds if not r["in_soul"]]
    L.append(f"- RED 未写进 SOUL 必触发表：{_fmt_kw(missing_soul) if missing_soul else '无（已对齐）'}")
    weak = [r["name"] for r in reds if r in name_derived]
    L.append(f"- RED 触发词仅名称派生：{_fmt_kw(weak) if weak else '无'}")
    L.append(f"- 触发词全部来自技能名词元（没有人工中文同义词，中文说法容易唤不醒）：{len(name_derived)} 个")
    L.append("")
    L.append("> 补词规则：改 `skill.json#trigger_keywords`（不要只改 SKILL.md，`normalize_meta(existing=)` 会保留旧词），")
    L.append("> 然后 `python -m webui.skills_registry --build` + `python -m webui.skill_trigger_index --build`。")
    L.append("")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成/校验 MemOmics 触发索引")
    ap.add_argument("--build", action="store_true", help="写入 memomics_home/SKILLS_TRIGGERS.md")
    ap.add_argument("--check", action="store_true", help="与磁盘一致才 exit 0")
    ap.add_argument("--report", action="store_true", help="只打印统计")
    args = ap.parse_args(argv)

    records = collect()
    contract = _load_contract()
    text = render(records, contract)
    levels = defaultdict(int)
    for r in records:
        levels[r["level"]] += 1
    reds = [r for r in records if r["level"] == "RED"]
    red_conf = {k: v for k, v in find_conflicts(records).items()
                if len([n for n in v if any(r['name'] == n and r['level'] == 'RED' for r in records)]) > 1}

    if args.report or not (args.build or args.check):
        print(f"技能总数: {len(records)}")
        print(f"级别: {dict(levels)}")
        print(f"RED 进 SOUL: {sum(1 for r in reds if r['in_soul'])}/{len(reds)}")
        print(f"RED 歧义关键词: {len(red_conf)}")
        pref = (contract.get("preferred") or {})
        unresolved = sorted(k for k in red_conf if k.lower() not in {p.lower() for p in pref})
        print(f"未指定首选: {len(unresolved)} {unresolved[:10]}")
        return 0

    if args.build:
        with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"已写入 {OUT_PATH}（{len(text)} 字符）")
        return 0

    # --check
    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            old = f.read()
    except OSError:
        print("SKILLS_TRIGGERS.md 不存在，先跑 --build", file=sys.stderr)
        return 2
    if old != text:
        print("SKILLS_TRIGGERS.md 与磁盘不一致，请跑 --build", file=sys.stderr)
        return 2
    missing = [r["name"] for r in reds if not r["in_soul"]]
    if missing:
        print(f"RED 未覆盖 SOUL 必触发表（{len(missing)}）：{missing[:8]}", file=sys.stderr)
        return 2
    print("SKILLS_TRIGGERS.md 与磁盘一致；RED 全部覆盖 SOUL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())