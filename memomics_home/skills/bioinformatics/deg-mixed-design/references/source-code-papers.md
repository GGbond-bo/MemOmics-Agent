# 混合设计 DEG：同结构文章目录 + 源码检索配方

> 来源：2026-08-28 用户研究（24 个体 3 组 Young/Old/Old+T2D × 运动前后，48 样本）方法学咨询时检索。用户特别要求：找同结构文章 + 看源码、来源专业、不局限于肌肉。

## 已验证的同结构/高相关文章（含源码线索）

| 文章 | 期刊·年 | 结构 | 源码状态 |
|---|---|---|---|
| Lovric et al. "Single-cell sequencing deconvolutes cellular responses to exercise in human skeletal muscle" | 2023 (GEO **GSE214544**) | 单细胞 + 骨骼肌 + 运动前后 | 第三方复现仓库（GitHub API 实查确认）：`evanpeikon/GSM_6611295`、`aspiroo/GSE214544-SC-RNA-RStudio` |
| Kedlian et al. "Human skeletal muscle aging atlas" | Nat Aging 2024, DOI 10.1038/s43587-024-00613-3, PMID 38622407 | 人类骨骼肌衰老图谱，跨组比较 | Teichlab GitHub org 下，仓库名需现场再确认（`Teichlab/SkeletalMuscleAgingAtlas` 404） |
| Edman et al. "The 24-hour molecular landscape after exercise…MYC" | EMBO Rep 2024, DOI 10.1038/s44319-024-00299-z, PMID 39482487 | 运动前后配对时间序列 | 方法公开；代码需确认 |
| Pillon et al. "Molecular choreography of acute exercise" | Cell Metab 2020 | bulk 运动时间序列（配对/重复测量方法可参考） | PillonLab 分析代码公开（仓库名需现场确认） |

## MoTrPAC 人类公共数据 meta 分析仓库核实（2026-08-28 实查 GitHub）

**用户问题："MoTrPAC 人类公共数据 meta 分析这篇是文章吗？" → 答案：不是单篇文章，是 MoTrPAC 官方代码仓库。**

- 仓库：`MoTrPAC/motrpac_public_data_analysis`，README 标题 "MoTrPAC: Analysis of publicly available exercise datasets"
- 结构：`data_collection/`（预处理）+ `metaanalysis/`（meta 分析）+ `metaanalysis_archive/`
- 数据：40+ 公开人类运动转录组研究（每研究多有运动前后配对），人工校对 metadata（Google Sheets 外链）
- **核心模型（README 原文）**：`g_fc ~ b0 + b1*x_tr + 1|dataset` —— metafor 混合效应 per-gene meta 分析，**dataset 作随机效应**
- 关键脚本：`run_meta_analysis_on_sherlock.R`、`simplified_moderators_metaanalysis.R`、`helper_functions_meta_analaysis.R`
- 对应正式文章（带 PMID）：Nature 2024 大鼠主文 38693412（另一仓库 `MotrpacRatTraining6mo`）；Cell 2020 设计 32589957；人类急性运动 bioRxiv 2026 预印本 42164870 / 41867848
- **教训**：引用"某文章用了 X 方法"前必须先核实该"文章"是否真的存在、代码是否真的在那；官方仓库≠单篇论文，正向反向都要查（README + contents API 实拉，别猜）

## 方法学引用（处理本设计的标准工具/金标准）

| 文献 | 用途 |
|---|---|
| Squair et al. 2022 *Nat Commun* "Confronting false discoveries in single-cell differential expression" | 伪重复金标准：个体数 ≥5/组 → pseudobulk |
| Crowell et al. 2020 *Mol Syst Biol*（muscat） | 多样本多条件单细胞 DE 标准流程（pbDS + dream/limma） |
| Hoffman & Schadt（variancePartition / dream） | 混合模型 `(1|subject)`，支持小样本 + 随机效应 |
| Finak et al. 2015 *Genome Biol*（MAST） | 逐细胞 Hurdle 模型；随机效应支持弱，作敏感性验证 |

> ⚠️ 上述 DOI/PMID 中，Kedlian/Edman 由本会话 search_papers 实测返回；Squair/Crowell/Finak/MAST 为方法学常识引用，**使用前用 search_papers 复核 PMID/DOI**，禁止直接写进论文草稿。

## GitHub 找文章源码的快速配方（比浏览器快）

```bash
# GitHub 仓库搜索 API —— 用论文标题核心词 / 方法词 / GEO 号
curl -s "https://api.github.com/search/repositories?q=<关键词>&per_page=10" \
  | python -c "import json,sys; d=json.load(sys.stdin); [print(r['full_name'],'|',r.get('description','')[:120],'|',r.get('html_url','')) for r in d.get('items',[])]"
```

经验：
- 搜 `论文核心词 + 方法词`（如 exercise + single cell + skeletal muscle）命中率最高
- **搜 GEO 号**（如 GSE214544）常能直接命中官方/第三方复现代码
- 描述里写明 "Replicating analyses from <paper>" = 第三方复现仓库，仍然可读
- API 免鉴权有速率限制（~10 req/min），间隔加 `sleep 1`

## 交付口径（用户特别要求）

- 用户要"看他们的源码"：先给可点 GitHub 链接，再问是否要拉下来逐行解读 DEG 代码（配对/随机效应怎么处理）
- 用户强调"一定要专业"：答复必须带期刊名+年份+DOI/PMID，方法建议要引用方法学金标准文献
- 编辑口径：先结论（统一模型 > 碎片 t 检验；pseudobulk > 逐细胞）后证据