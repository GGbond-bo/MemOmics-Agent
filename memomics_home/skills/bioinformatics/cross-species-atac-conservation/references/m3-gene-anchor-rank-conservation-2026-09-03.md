# M3 跨物种秩保守比较 — 基因锚定方案（2026-09-03 实测）

## 背景与决策

用户拿到人/猴 ageDA 全表（`*_ageDA_all.csv`，5.5M/5.3M tile 行）后要求"跨物种比较年龄相关秩"。
liftover/chains 路线被否决：猴侧是 **T2T-MFA8v1.1**（染色体 `NC_088375.1` 格式），UCSC 只有旧组装
macFas5 的 chain，版本错配会系统性错位；UCSC 本机直连还超时。用户拍板 **基因锚定方案**
（tile → 基因±2kb → ortholog 桥 → 基因级 r 比较），与 L1 已实证跑通的
`macaque_da_gene_map.csv` / `gene_anchor_ortholog_full.py` 同一逻辑。

## 输入资产（全部已存在，无需重跑/下载）

| 资产 | 路径 | 说明 |
|------|------|------|
| 猴 T2T 基因坐标 | `E:/专利/P3_L1_data/GCF_037993035.2_T2T-MFA8v1.1_feature_table.txt.gz` | gene 行：parts[6]=NC accession, [7]/[8]=start/end, [14]=symbol, [15]=GeneID |
| 猴→人 ortholog 全表 | `E:/专利/P3_L1_data/monkey_human_orthologs_full.csv` | 列: macaque_gene_id, human_gene_id, human_symbol（26,502 行） |
| 人 ortholog/hg38 坐标 | `E:/专利/P3_L1_data/human_ortholog_hg38_full.csv` | 列: human_gene_id, chr(裸数字!), start, end（16,161 行） |
| 猴 ageDA 全表 | `E:/专利/monkey_ageDA_all.csv` | chr(CN_xxx),start,end,r,p,q（529.7 万行） |
| 人 ageDA 全表 | `E:/专利/human_ageDA_all.csv` | chr(chrN),start,end,r,p,q（555.5 万行） |

## 三步管线

### Step A — 猴侧锚定 → `m3_monkey_gene_r.csv`
- tile 中点 ±2kb（WINDOW=2000，与 L1 协议一致）二分 overlap feature_table gene 行
- 每基因聚合 r_mean + n_tiles（只存均值即可，秩比较用）
- 实测：42.1% tile 命中基因 → **38,990 基因**

### Step B — 人侧锚定 → `m3_human_gene_r.csv`
- 同一二分逻辑，基因源 = `human_ortholog_hg38_full.csv`
- ⚠️ chr 列是裸数字 `"19"` → 必须 `'chr' + row['chr']` 前缀对齐人 tile 的 chrN
- 实测：43.9% 命中 → **16,104 基因**

### Step C — ortholog 桥 + 秩保守 → `m3_conservation_gene.csv` + `m3_conservation_stats.txt`
- bridge `macaque_gene_id -> [(human_gene_id, symbol)]`；每猴基因取第一个映射，human 侧有 r 才配对
- Spearman 秩相关（自己实现，注意 rank 用排序索引等价）
- **bootstrap 500 次** 95% 百分位 CI（seed=42）
- 方向一致性：人 r>0 子集猴同号率、人 r<0 子集猴同号率，各做二项检验

## 实测结果（16,029 同源基因对）

```
Spearman rho = -0.0627  [95% CI: -0.0772, -0.0473]  → 弱负相关（|ρ|<0.1）
人上调 n=8184: 猴同号 4556 (55.7%)  binom_p<0.0001
人下调 n=7845: 猴同号 2869 (36.6%)  binom_p<0.0001
```

**解读铁律**：
- |ρ|<0.1 = "秩不保守"，**禁止**声称"显著负相关/反向进化"——专利/论文写成
  "跨物种年龄效应保守性弱（秩相关接近 0，方向不对称）"
- 方向不对称（上调同号 55.7%、下调反号 36.6%）与 L2⑤ 的"上调保守、下调分歧"模式一致 → 是支撑证据不是矛盾
- 猴侧 q<0.1 显著 = 0（20 样本 + 530 万次检验 FDR），秩保守法吃不显著全表即可，不受影响

## 踩坑记录（都在 Common Issues 表）

1. **ageDA CSV 坐标列是 tile 编号**（`.addTileMat` 的 featureDF `start=(idx-1)*500`，idx 每染色体独立重置）
   → 本地换算 `真实start=(idx-1)*500+1; 真实end=idx*500`，不用重跑；验证全文件 `end-start==499` 100%
2. **R write.csv 大数科学计数法**（`1e+05`）→ `int(float(val))` 中转
3. **二项检验 comb 溢出**大 n → `scipy.stats.binomtest` 数值稳定

## 脚本位置
`results/memomics-cd677556/scripts/m3_stepA_monkey_anchor.py`
`results/memomics-cd677556/scripts/m3_stepB_human_anchor.py`
`results/memomics-cd677556/scripts/m3_stepC_conservation.py`