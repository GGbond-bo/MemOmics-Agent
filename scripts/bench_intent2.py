# -*- coding: utf-8 -*-
"""极端评测 B2：意图基准（全文 + 可接受意图集）。

每条真实消息标注"可接受意图集合"（理想意图 ∪ 语义可容错的意图），
同时报告精确命中率（理想意图==输出）与可接受率（输出∈集合）。
"""
import sys, sqlite3, re, time
sys.path.insert(0, r'E:\MemOmics-Agent\webui')
sys.path.insert(0, r'E:\MemOmics-Agent\hermes-agent')

# mid -> (理想意图, 可接受意图集合)
LABELS = {
    31611: ("literature", {"literature", "analysis"}),
    31650: ("knowledge_ask", {"knowledge_ask", "literature", "analysis"}),
    31673: ("direct_exec", {"direct_exec", "analysis"}),
    31690: ("knowledge_ask", {"knowledge_ask", "analysis"}),
    31692: ("knowledge_ask", {"knowledge_ask", "literature", "analysis"}),
    31700: ("knowledge_ask", {"knowledge_ask", "analysis"}),
    31702: ("knowledge_ask", {"knowledge_ask", "analysis"}),
    31736: ("analysis", {"analysis", "knowledge_ask", "chat"}),
    31784: ("analysis", {"analysis", "literature"}),
    31790: ("research_plan", {"research_plan", "analysis", "literature"}),
    31908: ("knowledge_ask", {"knowledge_ask", "analysis"}),
    31919: ("progress_check", {"progress_check", "analysis"}),
    31924: ("analysis", {"analysis", "chat"}),
    32073: ("knowledge_ask", {"knowledge_ask", "chat", "analysis"}),
    32075: ("chat", {"chat", "analysis"}),
    32100: ("knowledge_ask", {"knowledge_ask", "literature", "analysis"}),
    32126: ("knowledge_ask", {"knowledge_ask", "analysis"}),
    32130: ("direct_exec", {"direct_exec", "analysis"}),
    32196: ("progress_check", {"progress_check", "investigate", "analysis"}),
    32215: ("direct_exec", {"direct_exec", "analysis"}),
    32253: ("analysis", {"analysis", "research_plan", "knowledge_ask"}),
    32275: ("analysis", {"analysis", "progress_check", "research_plan"}),
    32280: ("direct_exec", {"direct_exec", "analysis"}),
    32294: ("direct_exec", {"direct_exec", "analysis"}),
    32299: ("knowledge_ask", {"knowledge_ask", "analysis", "literature"}),
    32301: ("direct_exec", {"direct_exec", "analysis"}),
    32320: ("direct_exec", {"direct_exec", "analysis", "research_plan"}),
    32373: ("knowledge_ask", {"knowledge_ask", "analysis"}),
    32399: ("chat", {"chat", "knowledge_ask"}),
    32421: ("direct_exec", {"direct_exec", "analysis"}),
    32552: ("progress_check", {"progress_check", "result_check", "analysis"}),
    32554: ("result_check", {"result_check", "analysis"}),
    32568: ("result_check", {"result_check", "analysis"}),
    32593: ("knowledge_ask", {"knowledge_ask", "analysis"}),
    32608: ("knowledge_ask", {"knowledge_ask", "analysis"}),
    32627: ("direct_exec", {"direct_exec", "analysis"}),
    32974: ("research_plan", {"research_plan", "analysis"}),
    33116: ("direct_exec", {"direct_exec", "analysis"}),
    33219: ("research_plan", {"research_plan", "analysis"}),
    33245: ("direct_exec", {"direct_exec", "analysis"}),
}

DB = r'E:\MemOmics-Agent\hermes_home\state.db'
c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
texts = {}
for mid in LABELS:
    row = c.execute("SELECT content FROM messages WHERE id=? AND role IN ('user','human')", (mid,)).fetchone()
    if row:
        t = re.sub(r'\s+', ' ', str(row[0] or '')).strip()
        texts[mid] = t  # 全文
c.close()

import server
import session_state as ss

exact = accept = 0
total = len(texts)
wrong = []
conf_mx = {}
for mid, (ideal, ok) in LABELS.items():
    t = texts.get(mid, '')
    got, confv, meta = server._classify_intent(t)
    if got == ideal:
        exact += 1
    if got in ok:
        accept += 1
    else:
        wrong.append((mid, ideal, got, t[:80]))
    conf_mx[got] = conf_mx.get(got, 0) + 1
print(f"n={total} | exact-accuracy={exact}/{total} = {exact/total:.0%} | acceptable={accept}/{total} = {accept/total:.0%}")
print("output distribution:", dict(sorted(conf_mx.items(), key=lambda x: -x[1])))
print("\n--- hard misses (outside acceptable set) ---")
for mid, ideal, got, t in wrong:
    print(f"  id={mid} ideal={ideal:14s} got={got:14s} | {t}")
