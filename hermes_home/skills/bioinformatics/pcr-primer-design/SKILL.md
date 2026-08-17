---
id: skill_62f7fe9a2d3e475983cadecafd0547e3
name: pcr-primer-design
when_to_use: "[pcr-primer-design] PCR引物设计：DNA模板序列→Primer3→引物对(正向/反向)→Tm/GC含量→特异性检查→PCR条件优化"
category: Mol Bio
short-description: Design and validate primers for PCR, qPCR, TaqMan, and sequencing applications.
detailed-description: >
  Design optimized primers for various PCR applications (standard PCR, qPCR,
  TaqMan, multiplex, sequencing, SNP genotyping) with comprehensive validation
  pipeline. Includes Tm calculation, dimer analysis, secondary structure prediction,
  and specificity checking. Generates MIQE-compliant reports and multi-format
  exports (CSV, Excel, IDT ordering format). Use when you need primers for molecular
  biology applications with rigorous quality validation. Best for qPCR assays
  requiring MIQE 2.0 compliance, or any PCR application needing publication-quality
  documentation.
starting-prompt: "Design qPCR primers for human GAPDH with MIQE compliance checking. Generate a PDF report with an intro, methods, results, conclusions and figures from all of the analyses you perform."
---
---

## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化生信分析平台。以下规则覆盖所有 Biomni 默认行为。

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



# PCR Primer Design

Comprehensive PCR and qPCR primer design following MIQE 2.0 guidelines with automated validation.

## When to Use This Skill

Use this skill when you need:
- ✅ **qPCR primers** with MIQE 2.0 compliance for publication
- ✅ **Standard PCR primers** for cloning, genotyping, or amplification (100-1000 bp)
- ✅ **TaqMan probes** for probe-based qPCR assays
- ✅ **Rigorous validation** (specificity, dimers, secondary structures)
- ✅ **Publication-quality documentation** with comprehensive reports

**Choose application based on:**
- qPCR: 70-140 bp amplicons, strict Tm matching (±2°C), MIQE compliance
- Standard PCR: 100-1000 bp amplicons, general amplification
- TaqMan: Probe-based detection, fluorescent assays
- Multiplex: Multiple targets, compatible Tm requirements
- Sequencing: Single-direction primers, Sanger sequencing

**Don't use for:**
- ❌ In-situ hybridization probes → use specialized oligo design tools
- ❌ NGS library prep primers → use adapter design workflows
- ❌ CRISPR guide RNAs → use CRISPR-specific design tools

## Quick Start (Example)

Test this skill with a sample qPCR design in ~2 minutes:

```python
# Example: Design qPCR primers for a 700bp target sequence
from scripts.design_qpcr_primers import design_qpcr_primers

# Sample GAPDH sequence (700 bp, exon 3-4 region)
sequence = "ATGGGGAAGGTGAAGGTCGGAGTCAACGGATTTGGTCGTATTGGGCGCCTGGTCACCAGGGCTGCTTTTAACTCTGGTAAAGTGGATATTGTTGCCATCAATGACCCCTTCATTGACCTCAACTACATGGTTTACATGTTCCAATATGATTCCACCCATGGCAAATTCCATGGCACCGTCAAGGCTGAGAACGGGAAGCTTGTCATCAATGGAAATCCCATCACCATCTTCCAGGAGCGAGATCCCTCCAAAATCAAGTGGGGCGATGCTGGCGCTGAGTACGTCGTGGAGTCCACTGGCGTCTTCACCACCATGGAGAAGGCTGGGGCTCATTTGCAGGGGGGAGCCAAAAGGGTCATCATCTCTGCCCCCTCTGCTGATGCCCCCATGTTCGTCATGGGTGTGAACCATGAGAAGTATGACAACAGCCTCAAGATCATCAGCAATGCCTCCTGCACCACCAACTGCTTAGCACCCCTGGCCAAGGTCATCCATGACAACTTTGGTATCGTGGAAGGACTCATGACCACAGTCCATGCCATCACTGCCACCCAGAAGACTGTGGATGGCCCCTCCGGGAAACTGTGGCGTGATGGCCGCGGGGCTCTCCAGAACATCATCCCTGCCTCTACTGGCGCTGCCAAGGCTGTGGGCAAGGTCATCCCTGAGCTGAACGGGAAGCTCACTGGCATGGCCTTCCGTGTCCCCACTGCCAACGTGTCAGTGGTGGACCTGACCTGCCGTCTAGAAAAACCTGCCAAATATGATGACATCAAGAAGGTGGTGAAGCAGGCGTCGGAGGGCCCCCTCAAGGGCATCCTGGGCTACACTGAGCACCAGGTGGTCTCCTCTGACTTCAACAGCGACACCCACTCCTCCACCTTTGACGCTGGGGCTGGCATTGCCCTCAACGACCACTTTGTCAAGCTCATTTCCTGGTATGACAACGAATTTGGCTACAGCAACAGGGTGGTGGACCTCATGGCCCACATGGCCTCCAAGGAGTAAGACCCCTGGACCACCAGCCCCAGCAAGAGCACAAGAGGAAGAGAGAGACCCTCACTGCTGGGGAGTCCCTGCCACACTCAGTCCCCCACCACACTGAATCTCCCCTCCTCACAGTTGCCATGTAGACCCCTTGAAGAGGGGAGGGCTCTCTCTTCCTCTTGTGCTCTTGCTGGGGCTGGCATTGCCCTCAACGACCACTTTGTCAAGCTCATTTCCTGGTATGACAACG"

primers = design_qpcr_primers(
    sequence=sequence,
    amplicon_size_range=(80, 120),
    num_return=5
)

print(f"Found {len(primers['primers'])} primer pairs")
print(f"MIQE-compliant: {sum(p.get('miqe_compliant', False) for p in primers['primers'])}")
```

**What you get:** 3-5 MIQE-compliant primer pairs, amplicons 80-120 bp, Tm matched within 2°C

**For your own data:** Follow Clarification Questions below to provide your sequence.

## Installation

**Core packages:**
```bash
pip install primer3-py biopython plotnine plotnine-prism pandas requests openpyxl
```

**Recommended:** Use virtual environment:
```bash
python -m venv pcr_env
source pcr_env/bin/activate  # Windows: pcr_env\Scripts\activate
pip install -r requirements.txt
```

### Software Requirements

| Software | Version | License | Commercial Use | Installation |
|----------|---------|---------|----------------|--------------|
| primer3-py | ≥2.0.0 | GPL v2 | ✅ Permitted* | `pip install primer3-py` |
| Biopython | ≥1.80 | BSD | ✅ Permitted | `pip install biopython` |
| plotnine | ≥0.12.0 | MIT | ✅ Permitted | `pip install plotnine` |
| plotnine-prism | latest | MIT | ✅ Permitted | `pip install plotnine-prism` |
| pandas | ≥1.5.0 | BSD | ✅ Permitted | `pip install pandas` |

*GPL v2 permits use in AI agent applications (execution, not distribution).

**NCBI API:** Primer-BLAST access is free. Rate limit: 3 requests/second (no API key) or 10/second (with free API key). See [references/primer_design_best_practices.md#ncbi-api-setup](references/primer_design_best_practices.md) for API key setup.

## Inputs

**Required:**
- **Target DNA sequence** in one of these formats:
  - FASTA file (local or uploaded)
  - GenBank/RefSeq accession (e.g., NM_002046)
  - Raw sequence (paste directly)
  - Gene name + organism (fetches from NCBI)

**Sequence requirements:**
- Minimum length: 150 bp (qPCR), 300 bp (standard PCR)
- Format: ATCG nucleotides (U converted to T)
- Quality: Avoid ambiguous bases (N) in primer regions

**Optional:**
- Regions to avoid (SNPs, repeats, splice sites)
- Custom parameter ranges (Tm, GC%, amplicon size)
- Organism/genome for specificity checking

**See [references/primer_design_best_practices.md#input-preparation](references/primer_design_best_practices.md) for sequence preparation guidelines.**

## Outputs

**Primary results:**
- **Primer sequences** with properties (Tm, GC%, length, position)
- **Validation report** (dimers, secondary structures, specificity)
- **Quality scores** and QC flags
- **`specificity_status`** — an explicit record of what specificity check ran
  (`in_silico_on_target_only`, `flagged_high_risk_unverified`, `local_blast_passed`,
  `local_blast_failed`, `primer_blast_passed`, or `not_run`). Carried in the CSV
  (`Specificity_Status`/`Pseudogene_Risk` columns), JSON (`metadata.specificity_status`),
  and MIQE checklist. See [Specificity: what was actually checked](#specificity-what-was-actually-checked).

**Export formats** (user-selectable):
- `primers.csv` - Spreadsheet-compatible table
- `primers.xlsx` - Excel with multiple sheets (design, validation, parameters)
- `primers.json` - Structured data for programmatic use
- `idt_order.txt` - IDT ordering format (copy-paste ready)
- `miqe_checklist.xlsx` - MIQE 2.0 compliance documentation (qPCR only)

**Visualizations** (optional):
- Primer binding site alignment (SVG, 300 DPI)
- Tm distribution plots
- Secondary structure diagrams

**See [references/code_examples.md#export-examples](references/code_examples.md#export-examples) for format details.**

- `analysis_report.pdf` — Comprehensive PDF report with Introduction, Methods, Results, Conclusions, and embedded figures

**⚠️ PDF style rules:**
- **US Letter page size (8.5 × 11 in)** — always set page dimensions explicitly; do not rely on library defaults
- **No Unicode superscripts** — use `3.36e-06` or `3.36 × 10^(-6)`, not Unicode superscript chars (they render as ■ in PDF fonts)
- **No half-empty pages** — group headings with their content; only page-break before major sections (Results, Conclusions)
- **Figures ≥80% page width** — multi-panel figures must be large enough to read; never embed below 50% width

## Clarification Questions

### 1. Input Sequence (ASK THIS FIRST)

Do you have a specific DNA sequence to design primers for?

- **Option A:** Upload FASTA file or provide file path
- **Option B:** Provide GenBank/RefSeq accession (e.g., NM_001256799)
- **Option C:** Provide gene name + organism (will fetch from NCBI)
- **Option D:** Paste sequence directly

**If uploaded:** Is this the complete target sequence or a specific region?

**Expected:** 150+ bp for qPCR, 300+ bp for standard PCR

### 2. PCR Application

What is your intended use for these primers?

- **qPCR (Quantitative PCR)** - Gene expression, 70-140 bp amplicons, MIQE-compliant
- **Standard PCR** - General amplification, cloning, genotyping, 100-1000 bp amplicons
- **TaqMan Assay** - Probe-based qPCR with fluorescent detection
- **Multiplex PCR** - Multiple targets simultaneously, compatible Tm required
- **Sequencing** - Sanger sequencing, single-direction primer
- **SNP Genotyping** - Allele-specific amplification

**Default:** qPCR (most common for gene expression studies)

### 3. Design Parameters

Do you want to use application-specific default parameters or customize?

- **Standard parameters** (recommended) - Optimized for selected application
- **Custom Tm range** - Specify melting temperature range (default: 58-62°C for qPCR)
- **Custom amplicon size** - Specify product size range
- **Custom GC range** - Adjust GC% (default: 40-60%)
- **Avoid regions** - Exclude specific sequences (SNPs, repeats, etc.)

**For qPCR:** Target exon-exon junction or ensure intron >1kb (MIQE guideline)?

**To understand design parameters:** See [references/parameter_ranges.md](references/parameter_ranges.md)

### 4. Validation Level

How thoroughly should primers be validated?

- **Basic** - Tm, GC%, dimer check (~1 min, sufficient for most uses)
- **Standard** - Basic + in-silico PCR on the supplied transcript (~2-3 min, recommended). **On-target only** — does not check the genome.
- **Complete** - Standard + genome-wide check via local BLAST (requires `blastn` + a database) or NCBI Primer-BLAST. Publication-quality.
- **MIQE-compliant** - Complete + full documentation (qPCR only, ~10 min)

**Note:** In-silico PCR is fast and offline but checks only the one transcript you
provide. For genome-wide specificity (and to clear a `flagged_high_risk_unverified`
status on genes like ACTB/GAPDH) you must run local BLAST or NCBI Primer-BLAST.
NCBI Primer-BLAST requires internet and respects rate limits; the bundled
`check_primer_specificity()` returns `not_run` (it does not auto-submit to NCBI).

### 5. Output Requirements

What outputs do you need?

- **Export format:** CSV (default), Excel, JSON, IDT order format, or MIQE checklist
- **Report format:** Markdown (default), HTML, or text
- **Visualizations:** Generate primer alignment plots? (yes/no)
- **Number of primers:** How many primer pairs to return? (default: 5)

**For qPCR:** MIQE checklist is automatically generated.

## Standard Workflow

🚨 **EXECUTE EXACTLY AS SHOWN - Do not modify these commands.**

**CRITICAL: Use relative paths (scripts/, references/). DO NOT construct absolute paths.**

### Step 1: Load Target Sequence

**Option A: Load from FASTA file**

```python
from Bio import SeqIO
record = SeqIO.read("your_sequence.fasta", "fasta")
sequence = str(record.seq)
```

**Option B: Load from GenBank accession**

See [references/code_examples.md#loading-sequences](references/code_examples.md#loading-sequences) for NCBI fetching code.

**Option C: Paste sequence directly**

```python
# For quick testing, paste your target sequence
sequence = "ATGGGGAAGGTGAAGGTCGGAGTCAACGGATTTGGTCGTATTGGG..."  # Your sequence here
```

### Step 2: Design Primers

**Choose based on application (from Clarification Question #2):**

**For qPCR (most common):**

```python
from scripts.design_qpcr_primers import design_qpcr_primers

primers = design_qpcr_primers(
    sequence=sequence,
    amplicon_size_range=(70, 140),  # MIQE guideline
    tm_match_threshold=2.0,
    num_return=5
)
```

**For Standard PCR:**

```python
from scripts.design_standard_primers import design_pcr_primers

primers = design_pcr_primers(
    sequence=sequence,
    amplicon_size_range=(100, 1000),
    tm_range=(55, 65),
    num_return=5
)
```

**For TaqMan Assay:**

```python
from scripts.design_taqman_probes import design_taqman_assay

assay = design_taqman_assay(
    sequence=sequence,
    probe_tm_offset=8.0,  # Probe Tm = primer Tm + 8°C
    num_return=5
)
```

**For custom parameters:** Read [references/parameter_ranges.md](references/parameter_ranges.md) and adapt ranges to your requirements.

### Step 3: Validate Primers

**Basic validation (recommended for all):**

```python
from scripts.check_dimers import analyze_dimers
from scripts.check_secondary_structures import analyze_secondary_structures

top_primer = primers['primers'][0]

# Check dimers
dimer_result = analyze_dimers(
    [top_primer['forward_seq'], top_primer['reverse_seq']],
    temperature=60.0
)

# Check secondary structures
fwd_structure = analyze_secondary_structures(top_primer['forward_seq'], 60.0)
rev_structure = analyze_secondary_structures(top_primer['reverse_seq'], 60.0)
```

**Complete validation (for publication):**

```python
from scripts.validate_specificity import in_silico_pcr_report

# In-silico PCR (fast, OFFLINE) — checks ONLY the supplied transcript.
# Pass gene_symbol so pseudogene/paralog-prone targets (ACTB, GAPDH, ...) are flagged.
spec = in_silico_pcr_report(
    forward_primer=top_primer['forward_seq'],
    reverse_primer=top_primer['reverse_seq'],
    sequence=sequence,
    gene_symbol="ACTB"          # used for the pseudogene/paralog risk flag
)
print(spec['specificity_status'])   # e.g. 'in_silico_on_target_only' or 'flagged_high_risk_unverified'
if spec.get('warning'):
    print(spec['warning'])          # prominent caveat for high-risk genes
```

⚠️ **In-silico PCR only checks the ONE sequence you pass in.** It cannot see
pseudogenes, paralogs, or other transcripts elsewhere in the genome. A clean
result means "specific to this transcript", NOT "genome-wide specific". See
**[Specificity: what was actually checked](#specificity-what-was-actually-checked)** below.

**Genome-wide check (recommended for publication, especially for high-risk genes):**

```python
from scripts.validate_specificity import check_specificity_local_blast

# Requires BLAST+ (`blastn`) and a local genomic/transcriptomic database.
# If blastn or the db is unavailable, returns specificity_status == 'not_run'
# (an honest "not checked"), NOT a misleading pass.
spec = check_specificity_local_blast(
    forward_primer=top_primer['forward_seq'],
    reverse_primer=top_primer['reverse_seq'],
    blast_db_path="/path/to/blastdb/human_genome",
    max_mismatches=3,
    gene_symbol="ACTB"
)
print(spec['specificity_status'])   # 'local_blast_passed' | 'local_blast_failed' | 'not_run'

# NCBI Primer-BLAST: check_primer_specificity() builds a submit URL and returns
# 'not_run' (this offline build does NOT submit jobs to NCBI). See
# [references/code_examples.md#validation-examples](references/code_examples.md#validation-examples).
```

#### Specificity: what was actually checked

Every specificity function returns a **`specificity_status`** field so reports and
exports state exactly what was — and was not — verified. **The honest default is
in-silico-on-target only** (the genome is *not* checked unless you run local BLAST
or Primer-BLAST).

| `specificity_status` | Meaning |
|----------------------|---------|
| `in_silico_on_target_only` | In-silico PCR matched only the single supplied transcript. Genome-wide off-targets (pseudogenes, paralogs, other transcripts) **were NOT checked**. |
| `flagged_high_risk_unverified` | Target is a known pseudogene/paralog-prone gene (e.g. **ACTB, GAPDH**) **and** only in-silico-on-target ran. Off-targets are plausible but unverified — `is_specific` is `None` and a prominent `warning` is emitted. Run a genome-wide check. |
| `local_blast_passed` | Local `blastn` ran genome-wide and found no off-target hits above threshold. |
| `local_blast_failed` | Local `blastn` ran and found off-target hits — redesign. |
| `primer_blast_passed` | NCBI Primer-BLAST ran genome-wide and judged the primers specific. |
| `not_run` | No specificity check was actually performed (e.g. `blastn`/db unavailable, or Primer-BLAST not submitted). **Not** a pass. |

🚩 **Pseudogene / paralog caveat (ACTB, GAPDH, and friends).** Common reference
genes have processed pseudogenes (often retained in genomic DNA) and large paralog
families. In-silico PCR against a single transcript **cannot** detect these
off-targets. `flag_pseudogene_risk(gene_symbol)` flags such genes (curated set
includes ACTB, GAPDH, B2M, HPRT1, YWHAZ, RPL13A, PPIA, plus ribosomal `RPL*`/`RPS*`,
tubulin `TUBB*`/`TUBA*`, and actin `ACTG*` families). When a high-risk gene is only
checked in-silico-on-target, the status is escalated to `flagged_high_risk_unverified`
with a WARNING, and the MIQE checklist / CSV / JSON all carry the qualified status.
**Always pass `gene_symbol`** to the specificity functions so this flag fires.

**`in_silico_pcr()` mismatch tolerance:** the default is **exact match
(`max_mismatches=0`)**. Set `max_mismatches=N` to allow up to N substitutions
(Hamming, no indels) at each binding site to model tolerant priming.

⚠️ **CRITICAL - DO NOT:**
- ❌ Use absolute paths like `/mnt/knowhow/` → use relative paths `scripts/`
- ❌ Write inline primer design code → use provided scripts
- ❌ Skip dimer/structure checks → these catch common failures

### Step 4: Generate Reports and Export

```python
from scripts.generate_reports import generate_primer_report
from scripts.export_results import export_primers

# Generate report
report = generate_primer_report(
    primers=primers,
    validation_results={
        'dimers': dimer_result,
        'secondary_structures': {'forward': fwd_structure, 'reverse': rev_structure}
    },
    output_format="markdown",
    include_miqe_checklist=(application == 'qpcr')  # From Clarification Question #2
)

# Export in requested format(s). Pass validation_results so the
# specificity_status (and pseudogene flag) appear in the CSV/JSON/MIQE outputs.
export_primers(primers, format="csv", output_file="primers.csv",
               validation_results=validation_results)
export_primers(primers, format="excel", output_file="primers.xlsx",
               validation_results=validation_results)

# For qPCR: MIQE checklist (now carries the honest specificity_status)
if application == 'qpcr':
    export_primers(primers, format="miqe_checklist", output_file="miqe_checklist.xlsx",
                   validation_results=validation_results)
```

**Excel export is verified.** Every `.xlsx` write is wrapped in error handling and
checked for a non-trivial file size (>1000 bytes) afterward. If the write fails or
produces a suspiciously small/0-byte file, `export_primers` prints a warning and
**falls back to CSV** (same base filename, extra sheets as `<base>__<sheet>.csv`) —
it never silently leaves a corrupt `.xlsx`. The returned path tells you what was
actually written (`.xlsx` on success, `.csv` on fallback).

**For visualization plots:** See [references/code_examples.md#visualization](references/code_examples.md#visualization)

**That's it! The scripts handle all design and validation automatically.**

## Common Issues

| Issue | Likely Cause | Solution |
|-------|--------------|----------|
| **No primers found** | Target too short or constraints too strict | Relax Tm range (±5°C), widen GC range (35-65%), provide longer sequence (≥300 bp) |
| **High primer-dimer formation** | Complementary sequences, low Tm | Increase Tm to 60-62°C, redesign avoiding complementary regions |
| **Multiple off-target amplicons** | Low specificity, repetitive sequences | Move to unique region, increase primer length (22-25 nt), check specificity with BLAST |
| **Tm mismatch between primers** | Different GC content | Adjust primer lengths to balance Tm, use Primer3 penalty weights (see [references/parameter_ranges.md](references/parameter_ranges.md)) |
| **Poor qPCR efficiency** | Dimers, secondary structures, amplicon >150 bp | Redesign with shorter amplicon (70-120 bp), check for hairpins, verify no dimers |
| **NCBI API rate limit errors** | Too many requests too quickly | Wait 0.33 sec between requests, get free API key (10 req/sec), or use in-silico PCR first |
| **ImportError for scripts** | Missing `__init__.py` in scripts/ | Create empty `scripts/__init__.py` file to make it a Python package |

**For detailed troubleshooting:** See [references/troubleshooting_guide.md](references/troubleshooting_guide.md)

## Suggested Next Steps

After successful primer design:

1. **Order primers** - Use IDT order format export for direct ordering
2. **Optimize PCR conditions** - Test annealing temperature gradient (Tm ± 3°C)
3. **Validate experimentally**:
   - Test specificity (gel electrophoresis, melt curve for qPCR)
   - Optimize primer concentration (50-900 nM range)
   - Verify amplicon size (gel or bioanalyzer)
4. **For qPCR** - Perform standard curve, efficiency calculation, melt curve analysis
5. **Document** - Save MIQE checklist and validation reports for publication

**Related protocols:** See [references/primer_design_best_practices.md#experimental-validation](references/primer_design_best_practices.md#experimental-validation)

## Related Skills

- **qPCR Data Analysis** - Analyze qPCR Cq values after experimental validation
- **Sanger Sequencing Analysis** - Analyze results from sequencing primers
- **Gene Expression Normalization** - Choose reference genes for qPCR

## References

### Documentation
- [Primer Design Best Practices](references/primer_design_best_practices.md) - Comprehensive design guidelines
- [MIQE 2.0 Guidelines](references/miqe_guidelines.md) - qPCR standards and compliance
- [Parameter Ranges](references/parameter_ranges.md) - Recommended parameter values
- [Troubleshooting Guide](references/troubleshooting_guide.md) - Common issues and solutions
- [Code Examples](references/code_examples.md) - Complete code examples for all applications

### Key Publications
- **MIQE 2.0**: Bustin SA, et al. (2025) Clinical Chemistry 71(6):634-660
- **Primer3**: Untergasser A, et al. (2012) Nucleic Acids Research 40(15):e115
- **Primer-BLAST**: Ye J, et al. (2012) BMC Bioinformatics 13:134

### Online Resources
- NCBI Primer-BLAST: https://www.ncbi.nlm.nih.gov/tools/primer-blast/
- Primer3 Web: https://primer3.ut.ee/
- MIQE Guidelines: https://rdml.org/miqe.html
