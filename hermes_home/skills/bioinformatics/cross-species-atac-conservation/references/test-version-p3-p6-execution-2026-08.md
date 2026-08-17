# 测试版 P3-P6 执行记录（2026-08-09，唤醒 #1）

测试版（猴 3 Arrow + 人 4 样本）跨物种 CRE 专利全流程 P3→P6 完成记录。
恢复入口：`results/memomics-1c1890da/task_plan.md` + `PATENT_TEST_PLAN.md` + `donor_age_map.json`。
数据目录：`E:/专利/P3_L1_data/`；专利文档：`results/memomics-1c1890da/patent/`。

## P3-L1 序列保守（phyloP）

脚本链（均在 `E:/专利/P3_L1_data/`）：
- `gene_anchor_ortholog.py` → `macaque_da_gene_map.csv`（119 tiles → 71 锚定 → 21 unique 基因）
- `macaque_human_orthologs.csv`（21 基因 → 8 human ortholog；13 个无映射 = 食蟹猴注释不全，非 bug）
- `fetch_hg38_coords_v3.py` → `human_ortholog_hg38.csv`（esummary hg19 + pyliftover → hg38）
- `l1_seq_scores.py` → `l1_seq_scores.csv`（40 可评估 tiles）
- `l1_phylop_fill_v3.py` → `l1_phylop_results.csv`（40 tiles 全查询成功，26/40 保守）

结果：Old 18 tiles → 9 保守 (50.0%)；Young 22 tiles → 17 保守 (77.3%)。
方向信号：Young DA 序列更保守，Old DA 更多非保守序列（仅方法验证，正式版需全量）。

**v1→v2→v3 失败链（复现参考）**：
1. v1：`data.get('bedGraph', [])` → UCSC 返回键是 `phyloP100way` → 全 NA
2. v1/v2：负链基因 hg38_start > hg38_end（fetch 只 liftOver start，end 残留 hg19 stop）→ HTTP 400
3. v2：全基因窗口查询（SNED1 1MB）→ 单区域 30-60s → 40 区域前台 300s 超时
4. v3 终版：相对位置映射 5kb 窗口 + min/max 归一化 + phyloP100way 键 + 断点续传

## P3-L2 可及性保守

- `l2_accessibility.py` → `l2_accessibility_scores.csv`
- 陷阱：gene_map key=macaque_gene_id、human_coords key=human_gene_id → 必须 `m2h` 桥接（macaque_human_orthologs.csv），否则 results 空
- 结果：8 基因 DA 密度矩阵；Spearman 猴Young vs 人Young = -0.668；猴(Young-Old) vs 人(Young-Old) = **+0.664**（年龄动态方向跨物种一致）
- 局限：人侧 DA 稀疏（仅 GSTM5/SNED1 命中），4 样本 power 限制

## P3-L3 TF 结合保守

- `l3_human_motif.R` → `human_motif_enrichment.rds` + `human_motif_rank_{old,young}.csv`
  - JASPAR2020 CORE 633 motifs + matchMotifs(out="scores") + GC-matched 背景（2000 bins）
  - 陷阱：BSgenome seqnames 带 chr 前缀，bed 转换必须保留（去掉报 `sequence 8 not found`）
  - 人Old Top：ELF1/SPIB/KLF15/E2F1/SP家族/ZFP57；人Young Top：ELF1/MLX/ZFP57/FOSL2::JUND
- `l3_motif_compare.R` → `l3_motif_topTF.csv`（JASPAR MA ID → TF 名映射 + Top30 Jaccard）
  - 猴侧 CSV 有 `tf` 列，取列时必须优先 tf 列（否则拿到 MA ID 算 Jaccard 全 0）
  - 结果：人Old vs 猴Old = 0.020，人Young vs 猴Young = 0.070，人Young vs 猴Old = 0.089（反向交叉最高）
  - 共享 TF：ZFP57/MLX（跨物种跨组）

## P4 CRECS 分类

- `p4_crecs_scores.py` → `p4_crecs_scores.csv`
- 测试版规则：L1=phyloP>0；L2=猴/人 DA 密度(各0.5)；L3=group 级 Jaccard 映射；CRECS=0.4L1+0.3L2+0.3L3
- 分类：A=CRECS≥0.8，B=L1=1 & L3<0.5（序列保守+TF 结合分歧=专利核心），D=L1=0
- 结果：26 tiles → **B=17**（DLD/TTC29/ULK4 Young tiles ★）+ D=9
- ⚠️ 正式版需 tile 级 L3（motif 实际命中该 tile）+ 逻辑回归校准权重（当前 group Jaccard 代理）

## P5 BNIP3 一正一反

- 正向：BNIP3 TSS±1kb phyloP=+0.185（保守 51.3%）→ 但基因全长 -0.126（被内含子稀释）→ **TSS±2kb 窗口铁律**
- 反向：GSTM5/SNED1 区域 phyloP<0 → D 类正确
- BNIP3 1:1 ortholog 验证（猴 102116967 → human 664）✅

## P6 专利文档（results/memomics-1c1890da/patent/）

- `技术交底书_v1.md`（背景含 Phan 2025 引用 + 三层方案 + 测试版数据 + A25 五锚点）
- `独权草案_v1.md`（独权 = S200 基因锚定映射 + S300 三层 + S400 混合效应模型 + S500 CRECS/进化锚点校准 + S600 SDI/IRS 决策；从权 2-10，9-10 RNA/Hi-C 占位）
- `实施例数据_测试版.md`（L1/L2/L3/CRECS/BNIP3 全部结果 + 正式版补全清单）

## 输出文件清单（E:/专利/P3_L1_data/）

| 文件 | 内容 |
|------|------|
| l1_phylop_results.csv | 40 tiles phyloP + conserved 标记 |
| l2_accessibility_scores.csv | 8 基因 DA 密度矩阵 |
| human_motif_rank_{old,young}.csv | 人侧 motif 富集（633 motifs × fc）|
| l3_motif_topTF.csv | 四组 Top30 TF 名清单 |
| p4_crecs_scores.csv | CRECS 评分 + A/B/C/D 分类 |

## 正式版补全清单

- [ ] 猴侧 ≥6 个体 × ≥3 年龄组（含连续年龄梯度）——测试版 3 个体不可作实施例
- [ ] 人侧 GSE278576 全量 40 样本 × 4 年龄组
- [ ] L3 补 HINT-ATAC/TOBIAS footprinting 实测（测试版用 motif 富集代理）
- [ ] 进化锚点校准权重（逻辑回归，≥3 物种对）
- [ ] 细胞类型特异性评估（跨物种细胞类型锚定）
