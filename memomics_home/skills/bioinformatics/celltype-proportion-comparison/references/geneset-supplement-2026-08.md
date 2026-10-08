# 基因集补充与 R 代码交付（骨骼肌衰老+糖尿病运动，2026-08-14 实测）

场景：用户 `pathway_score.xlsx`（Supplementary Table 3，宽表格式）已有 14 个 AUCell 打分，
要求按研究问题补缺失基因集，并交付可直接粘贴跑 AUCell 的 R 代码。

## 1. 补充的 8 个基因集（最终交付清单）

| # | Signature | 基因数 | 来源（真实可追溯） |
|---|---|---|---|
| 1 | Glycolysis score | 200 | MSigDB HALLMARK_GLYCOLYSIS (M5937)，下载 gmt（或 grp）格式 |
| 2 | Fatty acid metabolism score | 158 | MSigDB HALLMARK_FATTY_ACID_METABOLISM |
| 3 | Denervation score | 11（修正版） | 文献：Covault & Sanes 1985 PNAS PMID 3892537；Tang 2009 MBC PMID 19109424；Lai 2024 Nature PMID 38649488 |
| 4 | AMPK-PGC1a signaling score | 16 | Gundersen 2011 Biol Rev PMID 21040371（excitation-transcription coupling） |
| 5 | Autophagy score | 27 | Chen 2022 JCSM PMID 35434959 |
| 6 | Adipogenesis score | 200 | MSigDB HALLMARK_ADIPOGENESIS |
| 7 | mTORC1 signaling score | 200 | MSigDB HALLMARK_MTORC1_SIGNALING |
| 8 | Fibrosis score | 95 条目 → 90 唯一 | Reactome R-HSA-1650814 Collagen formation |

## 2. Denervation 修正版（11 基因，用户原 16 基因的修正）

```r
Denervation <- c("CHRNA1","CHRNG","CHRND","MYOG","RUNX1","SCN5A","KCNMB1",
                 "NCAM1","MYH8","NGFR","GAP43")
```
修正依据（辩论共识 + 文献）：
- 删 SCN4A（成人型钠通道，去神经时**下调**，与 SCN5A 上调互相抵消）
- 删 FBXO32/TRIM63/CTSL/GABARAPL1/BAG3（与 Atrophy score 重叠 → 打分共线性）
- 删 DCLK1/VIM/DES（与 RegMyon 重叠/非特异）
- 加 NCAM1（最经典去神经 marker，Covault & Sanes 1985）、MYH8/NGFR/GAP43（去神经诱导）

## 3. msigdbr 26.1.0 API 变更（2026-08-14 实测踩坑）

- 旧版参数 `category=` / `subcategory=` → 新版 **`collection=` / `subcollection=`**
- 可用集合名（26.1.0）：`H`（hallmark，50 集）、`CP:KEGG_LEGACY`（186 集，**旧 KEGG 通路名**，
  与用户已有 Insulin score 的 KEGG 旧名一致）、`CP:REACTOME`（1839 集）
- **KEGG_MEDICUS（新版 658 通路）不要用于打分基因集**：通路名全变、碎片化，不适合 AUCell 打分；
  AMPK/Autophagy 等 KEGG 拿不到 → 改用文献核心基因（教科书级真实基因 + 真实 PMID）
- Fibrosis 用 Reactome COLLAGEN_FORMATION（R-HSA-1650814，95 条目含 5 个重复基因如 CTSB/COL11A2 → 去重 90 唯一）

## 4. 交付 R 代码的格式铁律（用户两次纠正后）

1. **基因向量必须完整，一个不漏**——用户会数基因数（"那些基因，你怎么省略了？给我完整的啊"）。
   **R 代码要从 CSV/数据文件程序化生成**（读 `new_genesets_final.csv` → 按 10 个/行分组 → 拼
   `Name <- c("A","B",...)`），**不要手抄**（手抄 = 截断风险）。生成后必须验证每集基因数
   （200/158/11/16/27/200/200/90）与 CSV 一致。
2. **每个基因集内部去重**（Reactome 原始数据自带重复）：`unique()` 保序去重后交付，
   AUCell 对重复基因会自动处理但干净代码更好。
3. **用户粘贴的代码要自包含**：gene_sets <- list(...) + AUCell_buildRankings /
   AUCell_calcAUC / getAUC / t() / AddMetaData 注释完整，附 `%in% rownames(seu)` 过滤提醒
   （骨骼肌 scRNA 约 70-80% 基因可检出）。
4. **交付到对话里**（用户偏好：脚本直接贴对话，不只存文件）；同时存 `scripts/new_genesets_full.R`
   留档，交付时说明"完整文件也保存在 scripts/xxx.R"。
5. **来源列必须真实可追溯**：MSigDB 给 gmt/grp 链接、Reactome 给 R-HSA-xxxxx、文献给 PMID——
   用户明确要求"我要真实文献和数据库的，我都提供了来源"。

## 5. PDF 下载被 Cloudflare 反爬拦截的兜底

download_pdf 对 PMC/EuropePMC 被 Cloudflare 反爬拦截（返回反爬页）；curl 直连也只有搜索页 200。
兜底：**PMC 页面本身可达**（HTTP 200）→ 把 PMC/EuropePMC 链接列表给用户手动下载，不硬试。
PMC 开放获取链接格式：`https://pmc.ncbi.nlm.nih.gov/articles/PMCxxxx/` 或
`https://europepmc.org/articles/PMCxxxx?pdf=render`。
