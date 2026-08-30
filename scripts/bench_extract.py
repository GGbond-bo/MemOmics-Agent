# -*- coding: utf-8 -*-
"""极端评测 D+E：auto_extract 与 REQUIREMENTS 提取质量（真实干净消息）。

D: HolographicMemoryProvider.on_session_end 在 484 条干净 user 消息上的提取：
   条数 / 内容质量（含噪音/截断/代码）。
E: server._extract_and_store_requirements 在真实消息上的误报率（临时目录）。
"""
import sys, os, json, re, tempfile
sys.path.insert(0, r'E:\MemOmics-Agent\webui')
sys.path.insert(0, r'E:\MemOmics-Agent\hermes-agent')
os.environ.setdefault('HERMES_HOME', r'E:\MemOmics-Agent\hermes_home')

clean = json.load(open(r'E:\MemOmics-Agent\scripts\bench_clean_msgs.json', encoding='utf-8'))
msgs = [{"role": "user", "content": m["text"]} for m in clean]
print(f"clean msgs: {len(msgs)}")

# ---- D: auto_extract ----
from plugins.memory.holographic import HolographicMemoryProvider
tmp = tempfile.mkdtemp(prefix='bench_extract_')
p = HolographicMemoryProvider(config={'auto_extract': True, 'db_path': os.path.join(tmp, 'm.db')})
p.initialize(session_id='bench-1')
p.on_session_end(msgs)
facts = p._store.list_facts(limit=200)
p.shutdown()
print(f"\n[D] auto_extract facts: {len(facts)}")
n_noise = sum(1 for f in facts if len(f['content']) < 15)
n_code = sum(1 for f in facts if re.search(r'<-\s*[A-Za-z]|\b(getPeakSet|saveArchRProject|filterDoublets|library\()', f['content']))
n_long = sum(1 for f in facts if len(f['content']) > 250)
print(f"  short/noise-like: {n_noise} | code-like: {n_code} | long: {n_long}")
print("  samples:")
for f in facts[:14]:
    print("   *", f['category'], '|', f['content'][:110])

# ---- E: REQUIREMENTS 误报 ----
import server
tmp2 = tempfile.mkdtemp(prefix='bench_req_')
session = {"id": "bench-req-1", "results_dir": tmp2}
ingested = 0
for m in clean:
    before = ""
    rp = os.path.join(tmp2, "REQUIREMENTS.md")
    if os.path.isfile(rp):
        before = open(rp, encoding='utf-8').read()
    server._extract_and_store_requirements(session, m["text"])
    after = open(rp, encoding='utf-8').read() if os.path.isfile(rp) else ""
    if after != before:
        ingested += 1
print(f"\n[E] REQUIREMENTS: {ingested}/{len(clean)} messages triggered a write")
lines = [l for l in open(rp, encoding='utf-8').read().splitlines() if l.strip()] if os.path.isfile(rp) else []
print(f"  final lines: {len(lines)}")
print("  final content:")
for l in lines[:25]:
    print("   -", l[:110])
# 误报启发式：问句/元指令/无关闲聊不应在 REQUIREMENTS 里
false_pos = [l for l in lines if re.search(r'[吗呢么吧]$|看看|多少|为什么', l)]
print(f"  question/chat-like false positives: {len(false_pos)}")
