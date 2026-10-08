# M2→M3：tile(r/p/q) → 基因锚定 → Stouffer 聚合（人猴 age-DA 跨物种对账）

> 2026-09-11 会话实测。属于专利管线「可替代性 S 评分」的上游数据准备段。M2 产物由用户在自己环境（ArchR getGroupSE + 个体级 age 相关）跑出，回传本地。

## M2 输入形态（已用户确认 + 本地复核）

| 文件 | 行数 | 列 | 说明 |
|------|------|-----|------|
| `E:/专利/M2/human_ageDA_all.csv` | 5,555,248 | chr,start,end,r,p,q | hg38 坐标 |
| `E:/专利/M2/human_ageDA_up.csv` | 22 | 同上 | q<0.1 & r>0 |
| `E:/专利/M2/human_ageDA_down.csv` | 28 | 同上 | q<0.1 & r<0 |
| `E:/专利/M2/monkey_ageDA_all.csv` | 5,296,657 | chr,start,end,r,p,q | **T2T-MFA8v1.1 NC_XXXXX.1 坐标** |
| monkey up/down | 0 / 0 | — | 猴无显著 tile（无对应文件） |

- tile 步长 500bp（用户原始 rowData 列 seqnames/idx/start，start=0,500,1000…）。
- r = 年龄 Spearman 相关，p/q 为该 tile 的原始/FDR p 值。
- 关键事实：**猴侧坐标体系是 T2T-MFA8v1.1（NC_XXXXX.1），与 hg38 完全不同坐标系**，直接拿人侧 hg38 坐标 overlap 猴 tile 是错的。

## 跨坐标系锚定正解（D 项，辩论双方一致认可）

猴侧必须走完整链条，才能落到「共同 human GeneID」上与人侧对账：
1. 猴 tile (NC_XXXXX.1) → overlap `GCF_037993035.2_T2T-MFA8v1.1_feature_table.txt.gz` 基因体（±2kb 扩窗）→ 猴 GeneID + symbol
2. 猴 GeneID → NCBI efetch (Orthologs from Annotation Pipeline) → human GeneID（`monkey_human_orthologs_full.csv` 已含此映射）
3. human GeneID → hg38 坐标（`human_ortholog_hg38_full.csv`）
4. 人侧 tile (hg38) → 直接 overlap 人基因体 ±2kb（同坐标系，无转换）
5. 两物种 tile 各自聚到「共同 human GeneID」→ 每基因收集覆盖 tile 的 r/p → Stouffer 合并 → Z_human / Z_monkey

相关脚本：`E:/专利/P3_L1_data/gene_anchor_ortholog_full.py`（猴 peak→hg38 映射参考，53.8 万 peaks 版，方法节可复用；M3 的输入是 tile 不是 peak，逻辑同构）。

## M3 设计辩论裁决（L1，2026-09-11）

topic: tile→基因锚定→Stouffer 聚合脚本设计。裁决 **need_more_info / confidence=low**，正方关键论点：±2kb 窗口合理但覆盖不到远端调控；多基因 tile 全部计入（500bp 分辨率有限，基因密度高）防信号丢失；Stouffer 用 Fisher z=atanh(r) 加权 sqrt(n-3)；共享 tile 重复计入违反 Stouffer 独立性。**裁判列出的 missing（执行前必须补）**：
1. 锚定窗口敏感性分析（±0kb / ±2kb / ±5kb）对最终基因列表与 S 排序的影响
2. 多基因 tile 共享信号对 Stouffer 独立性的影响（连锁/聚类校正）
3. Fisher z 应用于 Spearman r 在 scATAC/pseudobulk 场景的文献支持
4. ortholog 一对一/多对多分布与错误率估计
5. 两物种 Z 方向一致性定义 + r 正负混入时 Stouffer 的实际数据分布
6. Stouffer 权重（等权 vs sqrt(n-3) vs 有效独立 tile 数）稳健性比较

**执行建议**：先跑 1 的敏感性分析（数据量小，555 万行 join 后每基因 tile 数少），把缺项补成一张对账表再定稿 M3，避免 16,031 基因 S 排序因参数选择被质疑。

## 对账目标（M3 输出要复现/对齐的基准）

`E:/专利/P3_L1_data/v5_substitutability_all.csv` — 16,031 基因，列含 Z_human / Z_monkey / S=min(|Z_h|,|Z_m|) / same_direction（历史 L1 流程完整版）。

## Windows 坑（实测）

`wc -l < "E:/专利/xxx.csv"`（中文路径经 subprocess → git-bash）返回非零退出码。数大文件行数用 Python 原生 `open() + for 迭代计数`，不要 shell wc；读列名前几行用 `pd.read_csv(nrows=5)`。