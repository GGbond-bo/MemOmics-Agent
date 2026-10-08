#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""merge_subagent_cards.py — 把多个子代理回传的竞品卡/证据 JSON 合并进主清单。

用途（模式 C/D）：N 个子代理各读一批论文、回传 ```json {"cards":[...],"evidence":[...]} ```，
主代理需要把它们的产出合并进既有的 cards.json，并重建 evidence.csv。

为什么需要「抢救式解析」：子代理回执里的 JSON 有三类常见破损 ——
  ① 尾随逗号（LLM 手写 JSON 的通病）
  ② 输出长度上限截断（最后一两个对象只写了一半）
  ③ 重复键（同一 card 里 novelty 出现两次）
json.loads 对 ①② 直接抛错，本模块按 原样 → 去尾随逗号 → 逐字符截断补齐 → 栈式花括号抢救 四级回退。

⛔ 最重要的一条纪律：写回共享中间文件时**必须保持原容器形状**。
   实测事故：cards.json 原本是 list，被写成 {"cards":[...], "evidence":[...]} 的 dict 后，
   下游 `sorted(cards)` 的构建脚本当场崩（TypeError/形状不符），且报错点离事故点很远。

用法:
  python merge_subagent_cards.py \
      --summaries <a.txt> <b.txt> ...      # 子代理回执文件（含 ```json 围栏）
      --cards data/cards.json             # 主清单（list 或 {"cards":[...]}，脚本会按原形状写回）
      --evidence-csv review/evidence.csv   # 可选：合并并重建证据表
      --report-json data/merge_report.json # 可选：合并统计落盘

输出（stdout）: 一行 JSON —— parsed_new_cards / merged / final_cards / evidence_rows_total 等。
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import OrderedDict

SUFFIXES = ('"}]}', '"}]', ']}', '}', ']')
EVIDENCE_COLS = ["doi", "pmcid", "title", "claim", "method", "strength",
                 "species", "tissue", "direction", "source"]


# ─────────────────────────── 解析层 ───────────────────────────
def extract_json_blocks(txt):
    """抽取 ```json … ``` 代码块；末块未闭合（被截断）也算。"""
    return [m.group(1).strip()
            for m in re.finditer(r"```json\s*(.*?)(?:```|\Z)", txt, re.S)]


def strip_trailing_commas(s):
    return re.sub(r",\s*([}\]])", r"\1", s)


def try_parse(s):
    """四级回退：原样 → 去尾随逗号 → 截断补齐。返回 (obj, how)。"""
    for cand in (s, strip_trailing_commas(s)):
        try:
            return json.loads(cand), "ok"
        except Exception:
            pass
    t = strip_trailing_commas(s)
    for cut in range(1, min(len(t), 5000)):          # 从尾部逐字符裁，试闭合后缀
        frag = t[:-cut]
        for suffix in SUFFIXES:
            try:
                return json.loads(frag + suffix), "truncated_repair"
            except Exception:
                continue
    return None, "failed"


def salvage_objects(s):
    """末级抢救：栈式花括号配对，逐个抠出顶层 {...} 对象，能解几个算几个。
    注意字符串态内的花括号不参与配对（否则含 '{' 的文本会把对象切碎）。"""
    out, depth, start, in_str, esc = [], 0, None, False, False
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    out.append(json.loads(strip_trailing_commas(s[start:i + 1])))
                except Exception:
                    pass
                start = None
    return out


def harvest(summary_paths):
    """从多个子代理回执里收割 cards / evidence（dict 或裸对象两种形态都收）。"""
    cards, evidence, report = [], [], []
    for p in summary_paths:
        txt = open(p, encoding="utf-8", errors="replace").read()
        n_c = n_e = 0
        for blk in extract_json_blocks(txt):
            obj, how = try_parse(blk)
            if obj is None:
                objs = salvage_objects(blk)
                cs = [o for o in objs if "n" in o and "name" in o]
                es = [o for o in objs if "doi" in o and "claim" in o]
                n_c, n_e = n_c + len(cs), n_e + len(es)
                cards += cs
                evidence += es
                report.append({"file": os.path.basename(p), "how": "salvaged",
                               "cards": len(cs), "evidence": len(es)})
                continue
            if isinstance(obj, dict):
                cs = obj.get("cards") or []
                es = obj.get("evidence") or []
            elif isinstance(obj, list):          # 子代理偶尔只回一个裸数组
                cs, es = [o for o in obj if "name" in o], []
            else:
                cs, es = [], []
            n_c, n_e = n_c + len(cs), n_e + len(es)
            cards += cs
            evidence += es
            report.append({"file": os.path.basename(p), "how": how,
                           "cards": len(cs), "evidence": len(es)})
        if not report or report[-1]["file"] != os.path.basename(p):
            report.append({"file": os.path.basename(p), "how": "no_block",
                           "cards": n_c, "evidence": n_e})
    return cards, evidence, report


# ─────────────────────────── 合并层 ───────────────────────────
def dedupe_cards(cards):
    """同 n 保留字段最全者（JSON 长度当代理，实测够用）。"""
    best = {}
    for c in cards:
        n = c.get("n")
        if n is None:
            continue
        cur = best.get(n)
        if cur is None or len(json.dumps(c, ensure_ascii=False)) > \
                len(json.dumps(cur, ensure_ascii=False)):
            best[n] = c
    return best


def merge_into_existing(cards_path, by_n):
    """字段级合并并**按原容器形状**写回。返回 (final_list, shape, merged_count)。"""
    raw = json.load(open(cards_path, encoding="utf-8"))
    shape = "dict" if isinstance(raw, dict) else "list"
    existing = raw["cards"] if shape == "dict" else raw
    ex = {c.get("n"): c for c in existing}

    merged = 0
    for n, c in by_n.items():
        if n in ex:
            base = dict(ex[n])
            base.update({k: v for k, v in c.items() if v})   # 新卡覆盖空字段，旧卡独有字段保留
            ex[n] = base
            merged += 1
        else:
            ex[n] = c

    final = [ex[k] for k in sorted(ex, key=lambda x: (x is None, x))]
    out = {"cards": final} if shape == "list" else {"cards": final}
    payload = final if shape == "list" else dict(raw, cards=final)
    json.dump(payload, open(cards_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return final, shape, merged


def card_quotes_as_evidence(cards, evidence):
    """卡片里的 evidence_quote 补进证据表（每篇至少一条原文佐证）。"""
    have = {(e.get("doi") or "").lower() for e in evidence}
    for c in cards:
        doi = (c.get("doi") or "").lower()
        q = c.get("evidence_quote")
        if q and doi and doi not in have:
            evidence.append({
                "doi": c.get("doi"), "pmcid": c.get("pmcid"), "claim": q,
                "method": "原文佐证引文（subagent full-text extraction）",
                "strength": "moderate", "direction": "AI agent / method",
                "title": c.get("title", ""), "source": "card n=%s" % c.get("n"),
            })
    return evidence


def rebuild_evidence_csv(csv_path, evidence):
    """合并旧表 + 新条目，去重键 =(doi, claim[:80])。"""
    old = []
    if csv_path and os.path.exists(csv_path):
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            old = list(csv.DictReader(f))
    seen, rows = set(), []
    for r in old + evidence:
        doi = (r.get("doi") or "").strip()
        if not doi:
            continue
        key = (doi.lower(), (r.get("claim") or "")[:80])
        if key in seen:
            continue
        seen.add(key)
        rows.append({k: (r.get(k) or "") for k in EVIDENCE_COLS})
    if csv_path:
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=EVIDENCE_COLS)
            w.writeheader()
            w.writerows(rows)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summaries", nargs="+", required=True)
    ap.add_argument("--cards", required=True, help="主卡片清单（list 或 dict），按原形状写回")
    ap.add_argument("--evidence-csv", default="")
    ap.add_argument("--report-json", default="")
    a = ap.parse_args()

    cards, evidence, report = harvest(a.summaries)
    by_n = dedupe_cards(cards)
    final, shape, merged = merge_into_existing(a.cards, by_n)
    evidence = card_quotes_as_evidence(final, evidence)
    rows = rebuild_evidence_csv(a.evidence_csv or None, evidence)

    out = {
        "parsed_new_cards": len(by_n),
        "merged_into_existing": merged,
        "final_cards": len(final),
        "cards_json_shape_kept": shape,
        "evidence_rows_total": len(rows),
        "n_coverage": [c.get("n") for c in final],
        "has_evidence_quote": sum(1 for c in final if c.get("evidence_quote")),
        "has_memomics_implication": sum(1 for c in final if c.get("memomics_implication")),
        "per_summary": report,
    }
    if a.report_json:
        json.dump(out, open(a.report_json, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())