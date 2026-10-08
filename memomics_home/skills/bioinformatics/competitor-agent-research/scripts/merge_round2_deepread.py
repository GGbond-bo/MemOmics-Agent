# -*- coding: utf-8 -*-
"""多批次深读卡归并器（模式 C12）——把散落在多个 `data/<prefix>_t*.json` 的深读卡，
经**逐字引文硬门**后字段级并入 store（`data/cards.json`），并落盘审计与合并报告。

与 `merge_deep_cards.py`（C10）的分工：
  - merge_deep_cards.py：从 state.db/回执回收**一批**深度卡 → 解析 → 合并（含裸引号修复）
  - 本脚本：批已被反复重派、碎成**多个文件**时，**以引文硬门 + 代次归一化 + 字段长度 diff** 归并
    （门开在写入路径上：引文不通过就拒写该字段）

用法（改下面 PATHS 段即可，无 CLI）：
    python merge_round2_deepread.py

输出：
  data/cards.json                 就地更新（list[dict] 形状保持不变）
  data/cards_v<k>_snapshot.json   首次运行自动建备份（不覆盖已有）
  log/<slug>_quote_audit.json     逐卡引文审计（n / pmcid / quote_len / exact_substring）
  log/<slug>_merge_report.json    逐卡 filled / skipped / grew（字段长度 before->after）+ 总量口径
"""
import os, re, json, glob, shutil, datetime

# ─────────────── PATHS（按项目改这一段）───────────────
BASE = r"E:/MemOmics-Agent/results/<sid>"
STORE = os.path.join(BASE, "data/cards.json")
SRC = ["deep_cards_round2_t0a.json", "deep_cards_round2_t0b.json",
       "deep_cards_round2_t1.json", "deep_cards_round2_t2.json"]
TEXT_GLOB = os.path.join(BASE, "data/text/PMC*.txt")     # 本地全文（引文硬门回源用）
SNAPSHOT = os.path.join(BASE, "data/cards_v3_snapshot.json")
SLUG = "round2"
ROUND_DATE = "2026-10-08"      # 代次日期（纯日期，渲染徽标要干净）
ROUND_PASS = "round2"          # 批次语义（round2 / round1-deep / ...）
# ─────────────────────────────────────────────────────

FIELDS = ["architecture", "inputs", "outputs", "models", "benchmark",
          "validation", "key_claim", "novelty", "limitations", "evidence_quote"]
TS = datetime.datetime.now().strftime("%Y-%m-%d")
logdir = os.path.join(BASE, "log")
os.makedirs(logdir, exist_ok=True)

# ---- 1. 归并全部散件（别只认最后一批！）----
merged = {}
for f in SRC:
    p = os.path.join(BASE, "data", f)
    if not os.path.exists(p):
        print("!! 缺件（检查是否漏了某一轮派发的产出）:", f); continue
    for k, v in json.load(open(p, encoding="utf-8"))["cards"].items():
        if str(k) in merged:
            print("!! 重复键，注意两轮是否都在写同一编号:", k)
        merged[str(k)] = v
print(f"散件归并: {len(SRC)} 文件 -> {len(merged)} 卡 {sorted(merged, key=int)}")

# ---- 2. store：先看形状再写逻辑（cards.json 常是 list[dict]，键在元素里）----
raw = json.load(open(STORE, encoding="utf-8"))
cards = raw["cards"] if isinstance(raw, dict) else raw
print("store 形状:", type(raw).__name__, "| cards:", len(cards), "| 首元素 keys:", sorted(cards[0].keys())[:8])
by_n = {str(c["n"]): c for c in cards}

# ---- 3. 逐字引文硬门（空白归一化子串；不做这步坏引文会写进 store）----
norm = lambda s: re.sub(r"\s+", " ", str(s)).strip()
corpus = {os.path.basename(p)[:-4]: open(p, encoding="utf-8", errors="ignore").read()
          for p in glob.glob(TEXT_GLOB)}
audit, rejected = [], []
for n, c in sorted(merged.items(), key=lambda kv: int(kv[0])):
    pmcid = str(c.get("pmcid") or by_n.get(n, {}).get("pmcid") or "")
    q, t = norm(c.get("evidence_quote", "")), norm(corpus.get(pmcid, ""))
    ok = bool(q) and bool(t) and q in t
    audit.append({"n": int(n), "pmcid": pmcid, "quote_len": len(q), "exact_substring": ok})
    if not ok:
        rejected.append(n)
print(f"引文硬门: {sum(a['exact_substring'] for a in audit)}/{len(audit)} exact | rejected={rejected}")
json.dump(audit, open(os.path.join(logdir, f"{SLUG}_quote_audit.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

# ---- 4. 备份 + 字段级覆盖（拒写被硬门拦下的 evidence_quote）----
if not os.path.exists(SNAPSHOT):
    shutil.copy2(STORE, SNAPSHOT); print("snapshot:", SNAPSHOT)
else:
    print("snapshot 已存在，不覆盖:", SNAPSHOT)

tot_before = tot_after = 0
report = []
for n, nc in sorted(merged.items(), key=lambda kv: int(kv[0])):
    if n not in by_n:
        nc.update(deep_read=True, deep_read_round=ROUND_DATE, deep_read_pass=ROUND_PASS,
                  deep_read_date=TS)
        by_n[n] = nc
        report.append({"n": int(n), "action": "NEW_CARD_ADDED"})
        continue
    base = by_n[n]
    before = {k: len(str(base.get(k, ""))) for k in FIELDS}
    filled, skipped = [], []
    for k in FIELDS:
        v = nc.get(k)
        if k == "evidence_quote" and n in rejected:
            skipped.append(k); continue
        if v in (None, "", "原文未报告", "本次未读取全文"):
            skipped.append(k); continue
        if k == "evidence_quote" and base.get("evidence_quote") and base["evidence_quote"] != v:
            base.setdefault("evidence_quote_v1", base["evidence_quote"])   # 审计要留旧引文
        base[k] = v; filled.append(k)
    base.update(deep_read=True, deep_read_round=ROUND_DATE,
                deep_read_pass=ROUND_PASS, deep_read_date=TS)
    after = {k: len(str(base.get(k, ""))) for k in FIELDS}
    tot_before += sum(before.values()); tot_after += sum(after.values())
    report.append({"n": int(n), "name": base.get("name"), "filled": len(filled), "skipped": skipped,
                   "grew": {k: f"{before[k]}->{after[k]}" for k in FIELDS if after[k] != before[k]}})

# ---- 5. 写回：保持原容器形状（list 进去 list 出来）----
final = [by_n[k] for k in sorted(by_n, key=int)]
if isinstance(raw, dict):
    raw["cards"] = final
else:
    raw = final
json.dump(raw, open(STORE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

thin = [c["n"] for c in final if not c.get("deep_read")]
out = {"total_cards": len(final), "deep_read_count": len(final) - len(thin),
       "still_thin_n": thin, "quote_audit_pass": f"{len(audit)-len(rejected)}/{len(audit)}",
       "rejected": rejected, "chars_before": tot_before, "chars_after": tot_after,
       "delta_pct": round(100 * (tot_after - tot_before) / max(tot_before, 1), 1),
       "this_round": report}
json.dump(out, open(os.path.join(logdir, f"{SLUG}_merge_report.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "this_round"}, ensure_ascii=False, indent=1))
print("→ 下一步：重渲染 md 附录（升级过的卡从 cards.json 整节重渲染）→ md2docx / build_report_html → 跑终态断言（C12-b）")