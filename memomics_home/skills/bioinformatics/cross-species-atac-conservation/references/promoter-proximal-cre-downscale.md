# 启动子近端 CRE 级下钻（基因级 S 评分 → CRE 级）

把「基因本体区域级」可替代性评分下钻到「启动子近端 CRE（TSS±2kb）」级，用 **ortholog 基因锚定绕开跨物种 liftover**。

## 何时用
- 专利权利要求要从「基因级」落位到「CRE 坐标级」（扩大/收窄实质保护范围）
- 跨物种组装之间 **无 liftover chain**（食蟹猴 T2T-MFA8v1.1 → hg38 无官方 chain）
- 用户说「CRE 级下钻」「启动子近端」「逐 CRE 算效应」

## 核心方法（v6_promoter_cre_score.py）
1. 猴 tile → 锚定猴基因启动子窗（TSS±2kb）
   - 猴 TSS 精确定位：feature_table 有 **strand 列**（+/− 分别取 start/end）
   - 人 TSS：人侧坐标表无 strand，用 start 近似
2. 猴基因 → 人 ortholog 基因（orthologs_full.csv 桥接）
3. 人同源基因启动子窗内 tile 取效应量
4. Stouffer 聚合（tile 级 r/p → 基因级 Z），S = min(|Z_m|,|Z_h|)×sign
5. 置换检验 + 四分类 A/B/C/D

## 关键坑
- **食蟹猴 T2T-MFA8v1.1（GCF_037993045.1，2024 发布）无官方 hg38 chain**。UCSC 只收录 macFas5/6，Ensembl 用 Macaca_fascicularis_6.0，都不是 T2T-MFA8v1.1。别浪费时间找 chain，直接 ortholog 基因锚定绕开（本方法全程不碰坐标 liftover）。
- **Stouffer 窗口收窄 → Z 幅度暴跌**：全基因 body 几百 tile → TSS±2kb 约 8 tile，Z 从 ~30 暴跌到 ~3.8（Z=sum(Z_i)/sqrt(n)，tile 少 → Z 幅度小）。不是 bug，是窗口收窄的必然。报告时别拿 CRE 级 Z 和基因级 Z 直接比幅度。
- **相邻 tile 自相关违反 Stouffer 独立假设**：同一启动子内 8 个相邻 tile 空间自相关，Stouffer 把 n 当独立样本会高估。统计背景审查员会抓。备选：tile 级 Z 直接取中位，或说明书交代相关性处理。
- **猴 feature_table.txt.gz 列位置**：基因行 p[0]=='gene'，chrom/start/end=p[6/7/8]，strand=p[9]，symbol=p[14]，geneid=p[15]（`str(int(p[15]))`）。

## 关键结果（2026-09，人 40 + 食蟹猴 20，海马 ATAC）
| 层级 | 配对 | A 类 | 占比 | 置换 p | top 身份 |
|---|---|---|---|---|---|
| 基因级(v5) | 16031 | 1904 | 11.88% | 0.0008 | 突触基因 SLC1A2/NRXN1/GRIA1 |
| 启动子近端 CRE(v6) | 15178 | 402 | 2.65% | ≈0(<1e-4) | 转录因子 RFX4/FEZF2/EMX2/HES5 |

**分层递进鉴别证据**（可作专利技术效果）：CRE 级把「可替代元件」从 11.88% 收窄到 2.65%，置换 p 更显著，捕获信号从「突触结构层」下沉到「转录调控层」——证明方法「越细分越精确」的递进鉴别力。注意：启动子近端 CRE 的 top 是转录因子/发育基因（RFX4/EDNRB/HES5/FEZF2/EMX2/POU3F4），与基因级 top（突触基因）完全不同，因为衰老的转录调控改变集中在启动子近端，而突触基因信号多分布在基因 body 内内含子/远端增强子。

## 文件
- 脚本：`results/<sid>/scripts/v6_promoter_cre_score.py`（启动子近端 CRE 级）
- 输出：`E:/专利/P3_L1_data/v6_promoter_cre_all.csv` / `_A_list.csv`(402) / `_stats.json`
- 基因级：`v5_substitutability_score.py` → `v5_substitutability_*.csv`(16031 全量 / 1904 A 类)