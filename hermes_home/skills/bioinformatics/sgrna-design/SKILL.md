---
name: sgRNA Design
description: CRISPR sgRNA design with three-tiered scoring
category: Mol Bio
tags: [crispr, sgrna, design]
when_to_use: "sgRNA设计：基因序列→CRISPR靶点扫描→效率+脱靶评分→最优sgRNA推荐→文库设计"
---
# sgRNA Design: Three-Tiered Approach

Find or design sgRNAs by **prioritizing validated sequences before computational predictions**.
Always start at Option 1 and only descend to the next tier when the current one yields nothing
usable. Ported from the Biomni `sgRNA_design_guide.md` (snap-stanford/Biomni), with the data
parsing corrected and the literature step wired to this environment's search tools.

## When to use
- "Give me an sgRNA to knock out TP53 in human cells"
- "Design CRISPR guides to activate OCT4" / "CRISPRi guides for MYC"
- "What guide RNA should I use for <gene> with SpCas9 / SaCas9 / Cas12a?"
- Selecting guides for an arrayed or pooled CRISPR screen

## Inputs
- **Gene symbol** (required), e.g. TP53, BRCA1, AAVS1.
- **Organism** (default human), e.g. human/mouse/rat or NCBI TAXID.
- **Application** (default knockout): knockout / activation (CRISPRa) / inhibition (CRISPRi).
- **Cas enzyme** (default SpCas9): SpCas9, SaCas9, AsCas12a, enAsCas12a.

## Outputs
- `<GENE>_selected_sgRNAs.csv` — unified table of 3–4 recommended guides (sequence, source,
  rank/score, exon/position, PAM, citation/dataset, notes).
- `<GENE>_sgRNA_summary.md` — which tier was used and why, the picks, and caveats.

Save both to the user's results directory.

## Bundled resources (work offline; refresh via `references/refresh_resources.md`)
- `references/resource/addgene_grna_sequences.csv` — 321 validated sgRNAs, 197 genes (Addgene).
- `references/resource/CRISPick_download_links.txt` — 238 CRISPick dataset URLs, 13 organisms.

## Scripts
| Script | Purpose |
|when_to_use: "[sgrna-design] 需使用sgrna design功能，适用于相关生信分析场景"
------
---

## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化生信分析平台。以下规则覆盖所有默认行为。

### 规则1: 拿到数据 → 必须调 search_knowledge
- **每个分析步骤写代码前**，必须先调 `search_knowledge(species=..., tissue=..., direction=..., query="<步骤名> 参数")`
- 知识库有匹配 → 用知识库的参数和模板
- 知识库无匹配 → 用 web 搜索文献，提取方法和参数，存入知识库
- **绝对不能跳过直接写代码**

### 规则2: 7步循环（每步必须走完整循环）
```
1. search_knowledge 查本步骤的方法和参数
2. check_env 检查环境
3. rail_review(pre) 前置审查
4. source/import 预写脚本（禁止 inline 代码）
5. terminal 执行（分步执行，禁止 && 连接多步骤）
6. debate_analysis 多方辩论（正方/反方切断上下文独立生成 + LLM裁决）
7. rail_review(post) 后置审查
```

### 规则3: 代码分段执行 — 写一步跑一步
- ❌ **禁止**一次性写完全部代码用 && 连接执行
- ✅ **必须**分步：写一步 → 执行 → 检查结果 → 辩论 → 下一步

### 规则4: 关键参数多参数尝试 + 辩论
- 涉及数值参数时（如 resolution, n_pcs, min_features, FDR threshold等），**至少尝试 2-3 个值**
- 每次参数变更后调 `debate_analysis` 辩论"这个参数合理吗？结果有没有变好？"
- 辩论格式（多角色对抗 v3）：
  - 正方 3 位专业编辑（各自独立，互相不知道）：生物学编辑 / 统计学编辑 / 生信编辑
  - 反方 4 位专业编辑（各自独立，互相不知道，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
  - 裁判编辑：看到所有 7 方论点，给出裁决 + 置信度（高/中/低）
  - 上下文隔离：每个编辑独立 HTTP API 调用，messages 只有自己的 prompt
  - 分科知识库：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
  - 辩论结果自动归档到 results/.../log/debate_*.json
- **不确定的参数就辩论**，不要自己拍脑袋

### 规则5: 执行后审查

### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"

  - **图片检查**：
    - 图有没有生成？没生成 → **强制重新执行**
    - 图片是否空白（全白/全黑/全单一色）？空白 → **强制重新出图**
    - 图片是否有 NA/缺失值（>10% 像素是 NA）？有 NA → **强制重新出图**
    - 图片大小是否过小（<5KB）？过小 → **强制重新出图**
    - 图片数量是否足够？（每步至少 1 张图，关键步骤至少 2-3 张）
  - **代码质量检查**：
    - 代码行数是否合理？（过短可能偷懒，过长可能未分段）
    - 代码是否有注释？
    - 代码是否分段执行（禁止 && 连接多步骤）？
  - **结果合理性**：
    - 数值范围是否合理？
    - 跟知识库对应吗？
  - **参数和结论辩论**：
    - 有参数的选择 → **必须调 debate_analysis 辩论**
    - 有结论输出 → **必须调 debate_analysis 辩论**
    - 不通过 → 修复重跑
    - 通过 → **必须调 skill_evolution(action="record_run")** 记录成功经验（skill_name/script_name/species/tissue/direction/params_used/result_summary/quality_score/notes） → 创建目录存储(figures/results/scripts/data) → 下一步
    - **不通过 → 修复后重跑 → 成功后调 skill_evolution(action="record_run")**；如果是脚本报错 → **调 skill_evolution(action="record_error")** 记录根因+修复方案

### 规则6: 结果存储结构
```
results/<模块>/<方法>/
  ├── scripts/     # 分析脚本
  ├── figures/     # PNG + SVG 图表
  ├── data/        # RDS/H5AD 中间数据
  └── results/     # CSV/TSV 结果表
```


### 规则7: 脚本出错/成功 → 必须调 skill_evolution（自进化）

| 时机 | action | 调 | 不调 |
|------|--------|----|------|
| 脚本报错+你分析根因+修复后 | record_error | ✅ R/Python 脚本报错，你找到根因并修复 | ❌ trivial 错误（打字错误、路径不存在） |
| 脚本成功+结果通过 rail_review | record_success | ✅ 分析步骤完成，图生成，审查通过 | ❌ 闲聊/方法咨询/非分析任务 |
| 修复后脚本验证稳定有效 | update_script | ✅ 同一错误修复了，重跑成功 | ❌ 只改参数没改脚本；未验证就更新 |

---

--|---------|
| `scripts/search_addgene.py` | Tier 1 / Method 1 — search the Addgene database (handles the HTML-wrapped IDs and messy species values). |
| `scripts/find_crispick_dataset.py` | Tier 2 / Step 1 — resolve the correct CRISPick download URL for organism+enzyme+application. |
| `scripts/select_crispick_sgrnas.py` | Tier 2 / Step 3 — filter a downloaded CRISPick file to your gene, rank, pick 3–4. |
| `scripts/check_design_rules.py` | Tier 3 — sanity-check a candidate guide (length, GC, TTTT, PAM). |
| `scripts/export_results.py` | Write the unified CSV + markdown summary. |

---

## Option 1 — Validated sequences (ALWAYS try first)

> You MUST complete **both** Method 1 and Method 2 before considering Option 2. Do not skip
> Method 2 even if Method 1 finds nothing — many validated guides live only in the literature.

### Method 1 — Bundled Addgene database
```python
import sys; sys.path.insert(0, "scripts")
from search_addgene import search_addgene

hits = search_addgene("TP53", species="human", application="knockout")
print(len(hits))   # 0 for TP53 -> still do Method 2 before Option 2
```
Each hit carries a clean `Target Sequence`, `pubmed_id`/`pubmed_url`, `plasmid_id`/`plasmid_url`,
and `Depositor`. **Cite the PubMed ID** of the original publication in your methods.

`application` accepts intent words and maps them to Addgene's vocabulary:
knockout→`cut`, activation→`activate`, inhibition/CRISPRi→`interfere`/`RNA targeting`.

### Method 2 — Literature & web search (REQUIRED)
This environment does not expose `advanced_web_search_claude`; use the available tools instead.
Run **both** for coverage:
- `LiteratureSearch` — peer-reviewed papers (validated guides, supplements).
- `WebSearch` — vendor/database hits (GenScript, Horizon, lab protocols).

Query templates (substitute the gene):
```
"sgRNA" OR "guide RNA" "<GENE>" validated experimental
"CRISPR knockout" "<GENE>" sgRNA sequence validated
"<GENE>" sgRNA "cutting efficiency" OR "on-target"
```
Scan ≥10–15 results and check supplementary materials. For any validated guide, record the
sequence, citation (PMID/DOI), and validation details (cell line, cutting efficiency).

**Decision:** if either method yields usable validated guides, select 3–4 and export. Only if
**both** come up empty, go to Option 2.

---

## Option 2 — CRISPick precomputed designs

Use when no validated guides exist, you need genome-wide coverage, or you want ranked options.

### Step 1 — Resolve the dataset URL
```python
from find_crispick_dataset import find_crispick_dataset
info = find_crispick_dataset("human", cas="SpCas9", application="knockout")
print(info["matches"])   # GRCh38 + GRCh37 dataset URLs
print(info["warning"])   # Cas12a variant warning, if applicable
```
> **AsCas12a vs enAsCas12a are different enzymes.** Guides for one may not work with the other.
> The finder matches the exact enzyme token so datasets never cross-contaminate.

### Step 2 — Download & extract (files are 50–700 MB; not bundled)
```bash
wget '<URL from Step 1>'
gunzip sgRNA_design_*.txt.gz
```

### Step 3 — Filter, rank, select
```python
from select_crispick_sgrnas import select_crispick_sgrnas
picks = select_crispick_sgrnas("sgRNA_design_..._CRISPRko_....txt", "TP53", n=4)
```
Ranks by **Combined Rank** (lower = better) by default; `rank_by="on_target"` or
`"off_target"` to prioritize efficiency or specificity. Spreads picks across distinct exons for
redundancy. Optional filters: `exon=`, `cut_position_range=`, `max_target_cut_pct=` (knockout).
Column names are resolved defensively (handles both real CRISPick and abbreviated layouts);
see `references/crispick_file_format.md`. If the gene is absent → Option 3.

---

## Option 3 — De-novo design (last resort)

For genes/organisms not covered above. Follow `references/design_rules.md`:
- Length: 20 bp (SpCas9/SaCas9), 23–25 bp (Cas12a). PAM: SpCas9 NGG, SaCas9 NNGRRT, Cas12a TTTV (5').
- GC 40–60%; avoid TTTT and homopolymer runs >4 nt.
- KO → early exons (first ~50%); CRISPRa → −200 to +1 of TSS; CRISPRi → −50 to +300 of TSS.
```python
from check_design_rules import check_design_rules, format_report
print(format_report(check_design_rules("GAGGTTGTGAGGCGCTGCCC", "SpCas9", pam="AGG")))
```
This checks rules only — for real off-target assessment use Cas-OFFinder/CRISPOR or CRISPick ranks.

---

## Export (all tiers)
```python
from export_results import from_addgene, from_crispick, export
unified = from_addgene(hits, application="knockout", enzyme="SpCas9")  # or from_crispick(...)
export(unified, gene="TP53", tier="Option 1 (validated Addgene)",
       outdir="/path/to/results", rationale="Validated guides found via Method 1.")
```

## Universal best practice
**Test 3–4 sgRNAs per gene experimentally regardless of predicted scores**, and validate edits
(Sanger sequencing; TIDE/T7E1 for indels). Prediction scores guide selection but do not replace
empirical validation.

## Citations & acknowledgments (preserve in user methods)
- **Validated guides (Option 1):** Addgene (https://www.addgene.org). Cite the PubMed ID of each
  guide's original publication. Acknowledge: "Validated sgRNA sequences obtained from Addgene."
- **CRISPick (Option 2):** "Guide designs provided by the CRISPick web tool of the GPP at the
  Broad Institute."
  - Cas9 (SpCas9, SaCas9): Sanson KR, et al. *Nat Commun.* 2018;9(1):5416. PMID: 30575746.
  - Cas12a (AsCas12a, enAsCas12a): DeWeirdt PC, et al. *Nat Biotechnol.* 2021;39(1):94–104.
    PMID: 32661438. (Specify which Cas12a variant you used.)

## Scientific caveats
- Bundled Addgene/CRISPick files are a fixed snapshot (197 genes / 238 datasets); literature
  search (Method 2) is mandatory precisely because the snapshot is incomplete.
- Genome build matters: human defaults GRCh38 (GRCh37 also available), mouse GRCm38 — match
  coordinates to your reference.
- The skill does not perform genome-wide off-target alignment beyond CRISPick's precomputed ranks.


---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="{当前分析} 参数与结果 —— {样本}",
     context="参数: {实际参数} | 结果: {输出摘要}",
     knowledge_base_info=<预查的 KB 内容>,
   )
   辩论维度：参数合理性、方法选择正确性、与KB生物学知识一致性、统计方法正确性
3. save_conclusions(module="{模块}", topic="{分析名}", debate_json=<debate返回JSON>, output_dir=<session results_dir>)
   → 写入 {module}/conclusions.md + conclusions.json
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```

⛔ 未完成以上 5 步 = 禁止启动下一个分析步骤。
⛔ debate confidence=low → 调整参数重跑。
