# -*- coding: utf-8 -*-
"""极端评测 C：检索召回基准。

12 个真实/合成 query（含口语、英文、错别字、路径、追问式），
跑 holographic prefetch（真实库四源）输出各源 Top 结果，供人工相关性评分。
"""
import sys, os, json
sys.path.insert(0, r'E:\MemOmics-Agent\webui')
sys.path.insert(0, r'E:\MemOmics-Agent\hermes-agent')
os.environ.setdefault('HERMES_HOME', r'E:\MemOmics-Agent\hermes_home')

from plugins.memory.holographic import HolographicMemoryProvider, _enhance_query

QUERIES = [
    ("q1", "继续跑热图", "memomics-cd677556"),
    ("q2", "peak 怎么保存", "memomics-cd677556"),
    ("q3", "专利结论表", "memomics-cd677556"),
    ("q4", "human_40_markerList", "memomics-cd677556"),
    ("q5", "filterDoublets 这个2是怎么来的", "memomics-cd677556"),
    ("q6", "C25 C26 这几个亚群是噪声吗", "memomics-cd677556"),
    ("q7", "猴脑海马8大群的注释", "memomics-cd677556"),
    ("q8", "human_hf_peaks.csv 在哪", "memomics-cd677556"),
    ("q9", "帮我下载张潇那篇猴脑文章", "memomics-cd677556"),
    ("q10", "细胞注释的marker基因", "memomics-cd677556"),
    ("q11", "marker gene annotation cross-species", "memomics-cd677556"),
    ("q12", "猴孬海马怎么注释", "memomics-cd677556"),  # 错别字鲁棒性
]

p = HolographicMemoryProvider(config={'db_path': r'E:\MemOmics-Agent\hermes_home\memory_store.db'})
p.initialize(session_id='memomics-cd677556')

report = {}
for qid, q, sid in QUERIES:
    out = p.prefetch(q, session_id=sid)
    blocks = out.split("\n\n") if out else []
    summary = {}
    for b in blocks:
        head = b.split("\n", 1)[0][:30]
        lines = [l for l in b.split("\n")[1:8] if l.strip().startswith("- ")]
        summary[head] = lines
    report[qid] = {"query": q, "sources": summary}
    print(f"\n===== {qid}: {q} =====")
    if not out:
        print("  (no prefetch output)")
    for head, lines in summary.items():
        print(f"  [{head}]")
        for l in lines[:5]:
            print("    ", l[:130])

with open(r'E:\MemOmics-Agent\scripts\bench_retrieval_raw.json', 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=1)
p.shutdown()
print("\nsaved scripts/bench_retrieval_raw.json")
