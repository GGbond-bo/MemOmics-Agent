#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""merge_deep_cards.py — 深度卡回收合并器（competitor-agent-research 模式 C10）

把子代理回的「深度卡 JSON」落盘、合并进既有 cards.json、并追加证据表行。
解决五类必然破损：尾随逗号 / 输出截断 / 重复键 / 字符串内**裸 ASCII 引号** /
顶层键格式不统一（"4" vs "n=9" vs "34"）。

用法（两种输入任选）：
  A) 从 session DB 回收子代理结果（live transcript 只有截断片段，不可用）：
     python merge_deep_cards.py --delegation-phrase "MCP 原生层级化" \
         --cards data/cards.json --evidence review/evidence.csv \
         --raw-out data/deep_cards_raw.json
  B) 已落盘的 JSON：
     python merge_deep_cards.py --json data/deep_cards_raw.json \
         --cards data/cards.json --evidence review/evidence.csv

约定：
  - cards.json 的**容器形状不被改变**（list 保持 list；C8 红线）。
  - 升级前自动快照 <cards>.v1_snapshot.json。
  - 卡片 10 字段：architecture inputs outputs models benchmark validation
    key_claim novelty limitations evidence_quote
"""
import argparse, csv, datetime, json, os, re, shutil, sqlite3, sys

DEEP_FIELDS = ["architecture", "inputs", "outputs", "models", "benchmark",
               "validation", "key_claim", "novelty", "limitations", "evidence_quote"]


# ── 第五级解析：字符串内的裸引号修复 ────────────────────────────────
def fix_quotes(s):
    """字符串态内遇到 '"'：向后看下一个非空白字符，属 ,}]: 或 EOF 才是闭合，否则转义。"""
    out, in_str, i, n = [], False, 0, len(s)
    while i < n:
        ch = s[i]
        if not in_str:
            out.append(ch)
            if ch == '"':
                in_str = True
            i += 1
            continue
        if ch == "\\":                      # 已转义序列原样保留
            out.append(ch)
            if i + 1 < n:
                out.append(s[i + 1])
            i += 2
            continue
        if ch == '"':
            j = i + 1
            while j < n and s[j] in " \t\r\n":
                j += 1
            nxt = s[j] if j < n else ""
            if nxt in ",}]:;" or nxt == "":
                out.append('"'); in_str = False
            else:
                out.append('\\"')           # 裸引号 → 字面量
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def strip_trailing_commas(s):
    return re.sub(r",\s*([}\]])", r"\1", s)


def salvage_objects(s):
    """栈式花括号配对逐对象抢救（字符串态内的 {} 不参与配对）。"""
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


def parse_json_blocks(txt):
    """→ {int n: card}；逐块走五级回退。"""
    blocks = re.findall(r"```json\s*(.*?)(?:```|\Z)", txt, re.S)
    if not blocks:                                  # 没围栏也试直接解析整段
        blocks = [txt]
    cards, report = {}, []
    for bi, b in enumerate(blocks):
        obj, how = None, ""
        for cand, tag in ((b, "raw"),
                          (fix_quotes(b), "fixquote"),
                          (strip_trailing_commas(fix_quotes(b)), "fixquote+comma")):
            try:
                obj = json.loads(cand); how = tag; break
            except Exception as e:
                last = str(e)
        if obj is None:                             # 第四/五级：逐对象抢救
            salv = [o for o in salvage_objects(fix_quotes(b)) if isinstance(o, dict)]
            if salv and all(re.match(r"^\s*[A-Za-z= ]*\d+\s*$", str(k)) is None for o in salv[:1] for k in o):
                pass
            merged = {}
            for o in salv:
                merged.update(o)
            obj, how = (merged or None), "salvaged"
        if not obj:
            report.append((bi, "FAILED", last[:120]))
            continue
        got = 0
        for k, v in obj.items():
            m = re.search(r"\d+", str(k))
            if not m or not isinstance(v, dict):
                continue
            cards[int(m.group())] = v
            got += 1
        report.append((bi, how, f"{got} cards"))
    return cards, report


def from_state_db(phrase, db_path):
    """从 state.db 回收 delegation 合并消息（live transcript 不可用）。"""
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT id, session_id, role, length(content) FROM messages "
        "WHERE content LIKE ? ORDER BY length(content) DESC LIMIT 5",
        (f"%{phrase}%",)).fetchall()
    con.close()
    if not rows:
        sys.exit(f"[!] state.db 中找不到含『{phrase}』的消息；换一个更独特的短语")
    print("候选消息 (id, session, role, chars):")
    for r in rows:
        print("   ", r)
    con = sqlite3.connect(db_path)
    mid = rows[0][0]
    content = con.execute("SELECT content FROM messages WHERE id=?", (mid,)).fetchone()[0]
    con.close()
    print(f"[i] 采用 id={mid}（{len(content):,} chars）")
    return content


def merge_into_cards(cards_path, deep, batch="", dry=False):
    raw = json.load(open(cards_path, encoding="utf-8"))
    is_list = isinstance(raw, list)
    by_n = {c.get("n"): c for c in (raw if is_list else raw.get("cards", []))}
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    upgraded, grown = [], {}
    for n, d in sorted(deep.items()):
        c = by_n.get(n)
        if c is None:
            print(f"    n={n}: cards.json 里无此编号，跳过（未新建卡）")
            continue
        for f in DEEP_FIELDS:
            v = d.get(f)
            if not v:
                continue
            if f == "evidence_quote" and c.get(f):
                c["evidence_quote_v1"] = c[f]
            grown[f] = grown.get(f, 0) + (len(v) - len(c.get(f, "") or ""))
            c[f] = v
        c["deep_read"] = True
        if batch:
            c["deep_read_batch"] = batch
        c["deep_read_at"] = ts
        upgraded.append(n)
    print(f"[i] 升级 {len(upgraded)} 张: {upgraded}")
    print(f"[i] 各字段净增字符: {json.dumps(grown, ensure_ascii=False)}")
    if dry:
        return upgraded
    shutil.copy2(cards_path, cards_path.replace(".json", "") + ".v1_snapshot.json")
    json.dump(raw, open(cards_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[ok] 写回 {cards_path}（形状={'list' if is_list else 'dict'}，未改变）"
          f" {os.path.getsize(cards_path):,} B")
    return upgraded


def append_evidence(evidence_csv, deep, cards_path):
    if not evidence_csv or not os.path.exists(evidence_csv):
        return 0
    cards = json.load(open(cards_path, encoding="utf-8"))
    by_n = {c.get("n"): c for c in (cards if isinstance(cards, list) else cards.get("cards", []))}
    with open(evidence_csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    cols = list(rows[0].keys()) if rows else ["doi", "pmcid", "title", "claim", "method",
                                              "strength", "species", "tissue", "direction", "source"]
    have = {((r.get("doi") or "").lower(), (r.get("claim") or "")[:80]) for r in rows}
    added = 0
    for n in sorted(deep):
        c = by_n.get(n, {})
        q = (c.get("evidence_quote") or "").strip()
        doi = (c.get("doi") or "").strip()
        if not q or not doi or (doi.lower(), q[:80]) in have:
            continue
        rows.append({"doi": doi, "pmcid": c.get("pmcid", ""), "title": c.get("title", ""),
                     "claim": q, "method": "全文重读逐字佐证（v2 深读卡）", "strength": "strong",
                     "species": "", "tissue": "", "direction": "AI agent / method",
                     "source": f"card n={n} (deep-read v2)"})
        have.add((doi.lower(), q[:80])); added += 1
    with open(evidence_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    print(f"[ok] {evidence_csv}: {len(rows)} rows (+{added})")
    print("     ⚠️ 记得把 review/evidence.csv 同步到 deliverables/evidence.csv")
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="已落盘的深度卡 JSON（键任意格式都会归一化）")
    ap.add_argument("--delegation-phrase", help="从 state.db 检索用的唯一中文短语")
    ap.add_argument("--state-db", default=r"E:/MemOmics-Agent/hermes_home/state.db")
    ap.add_argument("--cards", default="data/cards.json")
    ap.add_argument("--evidence", default="review/evidence.csv")
    ap.add_argument("--raw-out", default="data/deep_cards_raw.json")
    ap.add_argument("--batch", default="")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    if a.json:
        cards = json.load(open(a.json, encoding="utf-8"))
        deep = {int(re.search(r"\d+", str(k)).group()): v for k, v in cards.items()
                if isinstance(v, dict) and re.search(r"\d+", str(k))}
        print(f"[i] 读取 {a.json}: {len(deep)} 张")
    elif a.delegation_phrase:
        content = from_state_db(a.delegation_phrase, a.state_db)
        deep, report = parse_json_blocks(content)
        for bi, how, msg in report:
            print(f"    block{bi}: {how} — {msg}")
        print(f"[i] 解析出 {len(deep)} 张: {sorted(deep)}")
        json.dump({str(k): v for k, v in deep.items()},
                  open(a.raw_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"[ok] 原始卡落盘 {a.raw_out}")
    else:
        sys.exit("[!] 需要 --json 或 --delegation-phrase")

    merge_into_cards(a.cards, deep, batch=a.batch, dry=a.dry)
    if not a.dry:
        append_evidence(a.evidence, deep, a.cards)


if __name__ == "__main__":
    main()