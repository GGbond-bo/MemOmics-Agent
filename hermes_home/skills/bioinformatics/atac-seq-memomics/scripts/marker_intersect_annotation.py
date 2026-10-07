# -*- coding: utf-8 -*-
"""跨物种 marker 交集注释：参考物种亚群 marker × 目标物种 getMarkerFeatures CSV
2026-08-26 验证：张潇猴脑16亚群 × 40人海马ATAC 28 cluster
用法：改 zx dict 为你的参考 marker、df 路径为你的 getMarkerFeatures CSV。
强注释=全marker命中(比例1.0)且基因特异；弱注释(0.5-0.67)只给大类提示；单基因命中(尤其GPNMB)不注释。
"""
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# 1. 参考物种亚群 marker（张潇原稿提取，可换成任何参考列表）
zx = {
    "MGE-Inh": ["GAD2","LHX6"], "CGE-Inh": ["GAD2","ADARB2"], "LGE-Inh": ["GAD2","FOXP1"], "MB-Inh": ["GAD2","OTX2"],
    "Mic1": ["CSF1R","CX3CR1"], "Mic2": ["CD83","GPNMB"], "Mic3": ["CD83","CXCL10"], "Macrophage": ["LYVE1","F13A1"],
    "ODC1": ["MBP","OPALIN"], "ODC2": ["MBP","GSN"], "Ast1": ["SLC1A2","WIF1","GFAP"],
    "Ast2": ["SLC1A2","CRYAB","GFAP"], "Ast3": ["SLC1A2","GRIA4","PAX3"],
    "OPC1": ["TSHZ2","GPC5"], "OPC2": ["ACTG1","SEMA3D"], "COP": ["ENPP6"],
}

# 2. 目标物种 getMarkerFeatures CSV（ArchR 导出，列含 group/group_name/name/Log2FC/FDR）
df = pd.read_csv(r"E:\专利\human_40_markerList.csv")
out_dir = r"E:\MemOmics-Agent\results\memomics-cd677556\task4"

# 3. 每 cluster 基因集 + Log2FC
clusters = sorted([(g, df[df['group']==g]['group_name'].iloc[0]) for g in df['group'].unique()])
clu_maps = {}; clu_lfc = {}
for g, gn in clusters:
    grp = df[df['group']==g]
    clu_maps[gn] = set(grp['name'])
    clu_lfc[gn] = dict(zip(grp['name'], grp['Log2FC']))

# 4. 特异性：每个基因出现在多少 cluster（越大越广谱/越不可靠）
gene_nclu = df.groupby('name')['group'].nunique()

# 5. 命中矩阵
cts = list(zx.keys())
mat = np.zeros((len(cts), len(clusters))); annot = [[""]*len(clusters) for _ in range(len(cts))]
for i, ct in enumerate(cts):
    for j, (g, gn) in enumerate(clusters):
        hits = [x for x in zx[ct] if x in clu_maps[gn]]
        mat[i, j] = len(hits)/len(zx[ct])
        if hits: annot[i][j] = ",".join(hits)

# 6. 热图
fig, ax = plt.subplots(figsize=(14,6.5))
im = ax.imshow(mat, cmap="Reds", aspect="auto", vmin=0, vmax=1)
ax.set_xticks(range(len(clusters))); ax.set_xticklabels([gn for _,gn in clusters], rotation=45, ha="right", fontsize=9)
ax.set_yticks(range(len(cts))); ax.set_yticklabels(cts, fontsize=9)
for i in range(len(cts)):
    for j in range(len(clusters)):
        if mat[i,j]>0:
            ax.text(j, i, f"{mat[i,j]:.0%}"+(f"\n{annot[i][j]}" if len(annot[i][j])<18 else ""),
                    ha="center", va="center", fontsize=6.5, color="white" if mat[i,j]>0.6 else "black")
cbar = fig.colorbar(im, ax=ax, shrink=0.6); cbar.set_label("marker hit ratio")
ax.set_title("Reference markers x target clusters", fontsize=12)
plt.tight_layout()
fig.savefig(f"{out_dir}/marker_intersect_annotation_heatmap.png", dpi=200)
fig.savefig(f"{out_dir}/marker_intersect_annotation_heatmap.svg")

# 7. 汇总表（每 cluster best annotation）
rows = []
for gn in [g2 for _,g2 in clusters]:
    gset = clu_maps[gn]; best=[]
    for ct, genes in zx.items():
        hit=[x for x in genes if x in gset]
        if hit: best.append((len(hit)/len(genes), ct, ",".join(hit)))
    if best:
        best.sort(key=lambda t:-t[0]); rows.append({"cluster":gn,"annotation":best[0][1],"hit_genes":best[0][2],"ratio":round(best[0][0],2)})
    else: rows.append({"cluster":gn,"annotation":"未命中/需独立注释","hit_genes":"","ratio":0})
res = pd.DataFrame(rows); res.to_csv(f"{out_dir}/marker_intersect_summary.csv", index=False)
print(res.to_string())

# 8. 🔴 坑提醒（读结果时核对）：
#    - 单基因命中(尤其 GPNMB 出现在 8/28 cluster=背景噪声) → 不注释，看该 cluster 自己的 top marker
#    - 星形 SLC1A2/GFAP/WIF1 广谱 → 6 群全命中但分不出 Ast1/2/3（ATAC 分辨率天花板，与张潇原文结论一致）
#    - 无命中 cluster ≈ 兴奋性神经元亚群/血管细胞，需独立 top marker 注释