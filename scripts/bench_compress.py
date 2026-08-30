# -*- coding: utf-8 -*-
"""极端评测 F：压缩免疫 / 跨折叠关键事实保留率 + 注入预算。

合成 100 轮会话（早期 40 轮藏 10 条关键事实：路径/参数/结论/脚本），
REQUIREMENTS.md + conclusions.md 各放 5 条。跑 server 的真实折叠链
（c0 rollup → skip_rebuild → L1 注册表注入 → L2 digest），
检查关键事实在发给模型的最终上下文里的保留率。
"""
import sys, os, json, tempfile
sys.path.insert(0, r'E:\MemOmics-Agent\webui')
sys.path.insert(0, r'E:\MemOmics-Agent\hermes-agent')
os.environ.setdefault('HERMES_HOME', r'E:\MemOmics-Agent\hermes_home')
os.environ['MEMOMICS_ROLLUP_BUDGET'] = '30000'
os.environ['MEMOMICS_ROLLUP_TAIL'] = '8'

import server

tmp = tempfile.mkdtemp(prefix='bench_compress_')
rd = os.path.join(tmp, 'results')
os.makedirs(rd)
session = {"id": "bench-compress-1", "results_dir": rd,
           "model_config": {"model": "deepseek-v4-flash"}}

KEY_FACTS = [
    "E:\\data\\human_Hf_peaks.csv",          # 路径
    "resolution=0.8, dims=1:30",             # 参数
    "MS4A1 是 B 细胞 marker, log2FC=4.2",    # 结论
    "QC 过滤后剩余 82000 细胞",               # 结论
    "01_qc.R 用途=双胞过滤",                  # 脚本用途
    "决定改用 pheatmap 出热图",               # 决策
    "MACS2 装不上→TileMatrix(500bp) 替代",    # 修复
    "R 4.5.3 库在 E:/R-libs/R-4.5.3",         # 环境
    "human 40 样本 / monkey 63 文库",          # 数据规模
    "专利结论表 = 8大群×物种对照",             # 项目定义
]
# 前 40 轮藏关键事实（每条 2 轮）
history = []
for i in range(100):
    body = f"第{i}轮：请你帮我继续做海马单细胞分析，先看 QC，再看 UMAP 聚类，然后跑 marker，注意参数和文件路径。 " * 8
    if i < 20 and (i % 2 == 0):
        body += " 【关键事实】" + KEY_FACTS[i // 2 % 10]
    history.append({"role": "user", "content": body})
    history.append({"role": "assistant", "content": f"好的第{i}轮完成，UMAP 显示 30 群，继续下一步。 " * 8})

# REQUIREMENTS.md（跨折叠持久源 1）
with open(os.path.join(rd, "REQUIREMENTS.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(KEY_FACTS[:5]) + "\n")
# conclusions.md（跨折叠持久源 2）
from conclusion_store import append_conclusions
append_conclusions(session, [("结论", k) for k in KEY_FACTS[5:]])

# 模拟 server 全链
est_before = sum(server._est_message_tokens(m) for m in history)
pre = history
rolled = server._maybe_rollup_history(session, history)
folded = rolled is not pre
l1 = ""
try:
    from conclusion_store import build_memory_budget_context
    l1 = build_memory_budget_context(session, limit=20, max_chars=4000)
except Exception:
    pass
l2 = server._build_recent_turns_digest(session, max_turns=8)

final = rolled + ([{"role": "system", "content": l1}] if l1 else []) + \
        ([{"role": "system", "content": l2}] if l2 else [])
est_after = sum(server._est_message_tokens(m) for m in final)
text_all = "\n".join(str(m.get("content", "")) for m in final)

print(f"est tokens: before={est_before:,} after={est_after:,} ({est_after*100//max(1,est_before)}%)")
print(f"folded: {folded} | messages after: {len(final)} (was {len(history)})")

kept = [k for k in KEY_FACTS if k in text_all]
lost = [k for k in KEY_FACTS if k not in text_all]
print(f"\nkey-fact retention: {len(kept)}/10")
for k in kept:
    print("  KEEP ", k)
for k in lost:
    print("  LOST ", k)
# elision marker 存在性（捞回细节的指针）
print("\nelision marker present:", "折叠边界 message_id" in text_all)
print("\n--- injection blocks in final context (order) ---")
for m in final:
    c = str(m.get("content", ""))
    head = c.split("\n", 1)[0][:60]
    print(f"  [{m['role']:9s}] {len(c):6d} chars | {head}")
