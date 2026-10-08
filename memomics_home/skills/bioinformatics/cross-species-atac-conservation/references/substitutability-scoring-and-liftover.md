# 跨物种衰老可替代性评分（独权重心）+ 坐标 liftover 现状

## 1. 专利独权公式（已定稿，替代旧"方向预测器"重心）

独权重心从"方向预测器"（纯算法，易被 A25 客体适格打回）换成"跨物种衰老可替代性评估方法"：

```
S(g) = min(|Z_m|, |Z_h|) × sign(Z_m · Z_h)
```

- |S| = 较弱一侧的标准效应量（双侧都强才可信，天然防单侧假阳性）
- 符号 = 方向一致性（同向 + / 反向 −）
- τ = 1.96（双侧 p<0.05）

四分类（真实数据，16031 ortholog 基因对）：

| 分类 | 定义 | 数量 | 占比 |
|---|---|---|---|
| A 同向保守可替代 | 双侧 \|Z\|>τ 且同向 | 1904 | 11.88% |
| B 反向伪替代 | 双侧显著但反向 | 3487 | 21.75% |
| C 单侧分歧 | 单侧显著 | 7562 | 47.17% |
| D 双侧不显著 | — | 3078 | 19.20% |

置换检验（10000 次打乱 ortholog 配对）：A 真实 1904 vs 随机期望 2012.7 → 双侧 p=0.0008。

**关键含义**：同向保守的衰老脆弱基因是稀缺子集（11.88%），方法能精确筛出——有鉴别力 + 反直觉 + 可复现，避 A22.3 创造性硬伤。效果表述为"稀缺子集 + 置换检验鉴别力"，而非"方向预测"。

A 级 top（双侧同向下调，海马谷氨酸能突触/神经元结构核心）：SLC1A2(EAAT2)、NRXN1、GPM6A、SYT1、EPHA5/EPHA6、GRIA1/GRIA2。

脚本：`scripts/v5_substitutability_score.py`，产出 `E:/专利/P3_L1_data/v5_substitutability_{all,A_list,stats}.{csv,csv,json}`。

## 2. 坐标 liftover 现状（CRE 级下钻的硬障碍）

T2T-MFA8v1.1 = **食蟹猴 Macaca fascicularis** isolate 582-1：
- accession GCF_037993045.1，2024/06/04 发布，taxid 9541（NCBI nuccore `NC_088375.1` 考证）

**基本无官方 → hg38 liftOver chain**（2024 年新组装，UCSC/Ensembl 未建）：
- UCSC 收录食蟹猴为 macFas5 / macFas6（旧版 2013），非 T2T-MFA8v1.1
- Ensembl 用 Macaca_fascicularis_6.0，非 T2T-MFA8v1.1
- NCBI assembly FTP 从不提供跨物种 chain
- 本地唯一 chain = `rheMac3ToHg38.over.chain.gz`（恒河猴 rheMac3，不同物种/版本，不能配食蟹猴 T2T）

## 3. 三条绕过路径（CRE 级下钻，按推荐排序）

1. **ortholog 基因锚定（首选，零 liftover）**：A 级 1904 基因落回各自 CRE，用「同源基因 body ± 上游」锚定 tile 配对。基因级 S 评分已用 ortholog 基因名配好 16031 对；CRE 级只需把效应量从基因聚合层下钻到 tile 层。p4 阶段 `p4_crecs_AB_genes_tile.csv` 是锚点配对雏形（注意 Pitfall 10 网格不对齐坑，需改用 S 公式重算而非旧的 r 相关）。
2. **自建 chain**：minimap2/lastz 把 T2T-MFA8v1.1 比对到 hg38 生成 chain（可行但需算力 + 先备齐两组装 fa）。
3. **方法示范版**：用本地 rheMac3ToHg38 做 GSE67978 尾状核 H3K27ac 峰的 CRE 级 S 评分跑通流程（证明方法可落地），海马结论仍以基因级为准。

## 4. 查证教训

"食蟹猴 T2T-MFA8v1.1 有没有 chain"这类「外部资源是否存在」的问题，查一条权威源（NCBI nuccore 确认物种/assembly + 判断 NCBI 不提供跨物种 chain + UCSC/Ensembl 现有条目是旧版本）即可下结论。不要再 curl 循环探测被墙的 UCSC/Ensembl 服务器——一次点状确认后给结论 + 替代路径。