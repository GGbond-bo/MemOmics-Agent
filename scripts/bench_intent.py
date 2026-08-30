# -*- coding: utf-8 -*-
"""极端评测 B：意图识别基准。

人工标注 40 条真实用户消息（来自 memomics-cd677556，过滤脚手架后）的
理想意图，跑 server._classify_intent / _detect_domain_from_text /
session_state.extract_entity / capture_user_request，计算混淆矩阵与 F1。

理想意图体系（对齐 _classify_intent 五级+扩展）：
chat / knowledge_ask / analysis / direct_exec / research_plan /
progress_check / result_check / cancel_task / self_intro
"""
import sys, json, os, time
sys.path.insert(0, r'E:\MemOmics-Agent\webui')
sys.path.insert(0, r'E:\MemOmics-Agent\hermes-agent')

# 标注集：message_id -> (期望意图, 期望实体或'')
LABELS = {
    31611: ("analysis", ""),
    31650: ("knowledge_ask", ""),
    31673: ("direct_exec", "marker"),
    31690: ("knowledge_ask", ""),
    31692: ("knowledge_ask", "聚类"),
    31700: ("knowledge_ask", ""),
    31702: ("knowledge_ask", ""),
    31736: ("analysis", ""),
    31784: ("analysis", ""),
    31790: ("research_plan", ""),
    31908: ("knowledge_ask", ""),
    31919: ("progress_check", ""),
    31924: ("analysis", ""),
    32073: ("knowledge_ask", ""),
    32075: ("chat", ""),
    32100: ("knowledge_ask", "marker"),
    32126: ("knowledge_ask", ""),
    32130: ("direct_exec", "marker"),
    32196: ("progress_check", ""),
    32215: ("direct_exec", ""),
    32253: ("analysis", ""),
    32275: ("analysis", ""),
    32280: ("direct_exec", ""),
    32294: ("direct_exec", ""),
    32299: ("knowledge_ask", ""),
    32301: ("direct_exec", ""),
    32320: ("direct_exec", ""),
    32373: ("knowledge_ask", ""),
    32399: ("chat", ""),
    32421: ("direct_exec", ""),
    32552: ("progress_check", ""),
    32554: ("result_check", ""),
    32568: ("result_check", ""),
    32593: ("knowledge_ask", "umap"),
    32608: ("knowledge_ask", ""),
    32627: ("direct_exec", "注释"),
    32974: ("research_plan", ""),
    33116: ("direct_exec", "注释"),
    33219: ("research_plan", ""),
    33245: ("direct_exec", "marker"),
}

import sqlite3, re
DB = r'E:\MemOmics-Agent\hermes_home\state.db'
c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
texts = {}
for mid in LABELS:
    row = c.execute("SELECT content FROM messages WHERE id=? AND role IN ('user','human')", (mid,)).fetchone()
    if row:
        t = re.sub(r'\s+', ' ', str(row[0] or '')).strip()
        # 剥离脚手架构前缀
        PREFIXES = ("[会话要求", "[相关历史记忆", "[会话锚点", "[系统唤醒", "[System:", "[数据读取配方")
        while t.startswith(PREFIXES):
            idx = t.rfind('\n\n')
            t = t[idx+2:].strip() if idx > -1 else ''
        texts[mid] = t
c.close()

import server  # 重量级：加载 FastAPI app（不启动）
import session_state as ss

conf = {}  # intent -> {correct, total}
pair_wrong = []
domain_hits = 0
entity_ok = 0
t0 = time.time()
for mid, (exp_intent, exp_ent) in LABELS.items():
    t = texts.get(mid, '')
    got, confv, meta = server._classify_intent(t)
    dom = server._detect_domain_from_text(t)
    ent = ss.extract_entity(t)
    # 归一：cancel/self_intro 等扩展意图在本标注集未出现，视为命中自身
    key = got
    conf.setdefault(key, {"correct": 0, "total": 0})
    conf[key]["total"] += 1
    if got == exp_intent:
        conf[key]["correct"] += 1
    else:
        pair_wrong.append((mid, exp_intent, got, t[:60]))
    if exp_ent and ent.lower() == exp_ent.lower():
        entity_ok += 1
    if dom:
        domain_hits += 1
print(f"ran in {time.time()-t0:.2f}s")
total = len(LABELS)
correct = sum(v["correct"] for v in conf.values())
print(f"intent accuracy: {correct}/{total} = {correct/total:.1%}")
print(f"domain detected: {domain_hits}/{total}")
print(f"entity exact: {entity_ok}/{sum(1 for e,_ in LABELS.values() if e)}")
print("\n--- confusion (got -> correct/total) ---")
for k in sorted(conf):
    v = conf[k]
    print(f"  {k:16s} {v['correct']:2d}/{v['total']:2d}")
print("\n--- misclassified ---")
for mid, exp, got, t in pair_wrong:
    print(f"  id={mid} expect={exp:14s} got={got:14s} | {t}")
