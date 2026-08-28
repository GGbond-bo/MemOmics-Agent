---
name: dnbc4tools-index-building
description: "华大BGI DNBelab C系列高通量单细胞数据分析软件 dnbc4tools 的参考基因组索引构建流程（rna mkref=STAR 2.7.2b genomeGenerate + atac mkref=chromap + tools mkgtf GTF过滤校正）。⚠️触发门禁（用户特别指定，最高优先级）：命中触发词时禁止直接执行——必须先向用户澄清 ①是否华大BGI/DNBelab平台 ②要建的是RNA索引还是ATAC索引 ③是否已有ref.json库，确认后才加载执行；未确认华大平台（10X/标准STAR/hisat2等其他平台）或非索引需求 → 不触发本skill，redirect到正确流程。"
version: 1.1.0
author: MemOmics (auto-created)
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [dnbc4tools, DNBelab, 华大单细胞, 基因组索引, mkref, STAR, chromap, mkgtf, BGI, 参考数据库, 触发门禁]
    difficulty: intermediate
    language: Shell
    category: Transcriptomics
prerequisites:
  r_packages: []
  python_packages: []
related_skills: [scrna-qc, scrnaseq-seurat-core-analysis, atac-seq-memomics, create-bio-skill]
---

## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化生信分析平台。使用本 skill 前，必须先通过 skill_view 加载本文件。以下规则覆盖所有默认行为。

### 规则0: 触发门禁（🔴 用户特别指定 · 先问清楚再触发 · 优先级最高）

> **2026-08-28 用户明确要求："触发这个skill之前，一定要问清楚是BGI,华大基因，华大的ATAC或者RNA索引，记得写到触发场景和skill里，什么触发什么时候不触发"**

**命中触发词（DNBelab/dnbc4tools/华大单细胞/BGI索引/mkref/华大/索引等）时，禁止直接执行建库命令，必须先依次确认：**

| # | 必问问题 | 用户回答「是/确认」→ | 用户回答「否/无关」→ |
|---|---------|---------------------|---------------------|
| ① | **厂家确认**：你的数据/需求是华大 BGI / DNBelab C 系列平台吗？（不是 10X Genomics，不是 Illumina 常规流程） | 继续问 ② | ❌ **不触发本 skill** → redirect：10X → Cell Ranger/STARsolo；常规 RNA-seq → 标准 STAR/hisat2；问用户具体平台 |
| ② | **类型确认**：要建的是 **RNA 索引**（`rna mkref`，STAR 2.7.2b，服务 scRNA 比对+量化）还是 **ATAC 索引**（`atac mkref`，chromap，服务 scATAC 可及性）？ | 按对应分支执行（Step 3a / 3b） | 用户要的是 scVDJ → 不建库，直接 `vdj run --ref Human/Mouse`；要标准 STAR 索引 → 不触发 |
| ③ | **状态确认**：已存在含 `ref.json` 的库目录了吗？ | 已有 → ❌ **不建库**，直接 `rna run --genomeDir` / `atac run --genomeDir` 复用 | 没有 → 开始建库流程 |

**确认完成 → 才允许 skill_view 加载 + 执行建库。**

⛔ **禁止**在未澄清厂家的情况下把任何"建索引"需求都路由到本 skill。

### 规则1: 写代码前 → 必须先 search_knowledge + skill_view
- **每个分析步骤写代码前**，必须先调 `search_knowledge(species=..., tissue=..., direction=..., query="<步骤名> 参数")`
- 知识库有匹配 → 用知识库的参数和模板
- 知识库无匹配 → 用 search_papers_by_context 搜文献，提取方法和参数，存入知识库
- **绝对不能跳过直接写代码**

### 规则2: 8步循环（每步必须走完整循环）
```
1. search_knowledge 查本步骤的方法和参数
2. skill_view 加载本 SKILL.md（获取脚本模板+审查规则+参数范围）
3. check_env 检查环境（缺包自动安装）
4. rail_review(pre) 前置审查（参数合理吗？包齐了吗？数据准备好了吗？）
5. 写这一步的代码（基于 skill 模板，只写这一步，不写后续步骤）
6. terminal 执行（分步执行，禁止 && 连接多步骤）
7. debate_analysis 多方辩论（正方/反方切断上下文独立生成 + LLM裁决）
8. rail_review(post) 后置审查（结果合理吗？索引文件存在且非空？跟知识库对应吗？）
```

### 规则3: 代码分段执行 — 写一步跑一步
- ❌ **禁止**一次性写完全部代码用 && 连接执行
- ✅ **必须**分步：写一步 → 执行 → 检查结果 → 辩论 → 下一步

### 规则4: 关键参数多参数尝试 + 辩论
- 涉及数值参数时，**至少尝试 2-3 个值**
- 每次参数变更后调 `debate_analysis` 辩论"这个参数合理吗？结果有没有变好？"
- 辩论格式（多角色对抗 v3）：正方 3 位专业编辑 / 反方 4 位专业编辑 / 裁判编辑
- **不确定的参数就辩论**，不要自己拍脑袋
- **辩论最多 3 轮**：3 轮后选最优参数结果

### 规则5: 执行后审查（强化版）
- 每步执行完调 `rail_review(post)` 审查，审查内容**全部强制**：
  - **结果合理性**：索引文件存在且非空？ref.json 生成？字段与 skill 预期吻合？
  - **参数和结论辩论**：有参数的选择 → 必须调 debate_analysis
  - 通过 → **必须调 skill_evolution(action="record_run")** 记录成功经验
  - 不通过 → 修复重跑；脚本报错 → skill_evolution(action="record_error")

### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 运行日志是"参考"不是"免审凭证"

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
| 脚本报错+找到根因并修复 | record_error | ✅ | ❌ trivial 错误 |
| 脚本成功+通过 rail_review | record_success | ✅ | ❌ 闲聊/非分析 |
| 修复后脚本验证稳定 | update_script | ✅ | ❌ 只改参数 |

---

# dnbc4tools 参考基因组索引构建（DNBelab C 系列）

> # 🔴 触发门禁（用户特别指定 · 2026-08-28）
> **触发本 skill 前必须先问清楚 3 件事**（详见上方"规则0: 触发门禁"表格）：
> ① 是华大 BGI / DNBelab 平台吗？ ② RNA 索引还是 ATAC 索引？ ③ 已有 ref.json 库了吗？
> **未确认 → 不触发；确认后 → 才按下面 Pipeline 执行对应分支（Step 3a RNA / Step 3b ATAC）。**

华大智造（MGI/BGI）官方开源的单细胞分析软件 **dnbc4tools**（v2.1.3，仓库 version2.0 分支）的**参考数据库（基因组索引）构建流程**。该步骤是运行 `dnbc4tools rna run` / `dnbc4tools atac run` 分析前**必须完成**的前置步骤。

三个建库相关子命令：

| 子命令 | 底层工具 | 用途 |
|--------|---------|------|
| `dnbc4tools tools mkgtf` | 自研 | GTF 注释文件统计/校正/基因类型过滤（可选但强烈推荐） |
| `dnbc4tools rna mkref` | **STAR 2.7.2b** `runMode=genomeGenerate` | 构建 scRNA 比对索引（Genome/SA/SAindex + 注释 info 表） |
| `dnbc4tools atac mkref` | **chromap 0.2.6-r490** | 构建 scATAC 比对索引（genome.index + TSS/promoter/blacklist） |

scVDJ 分析使用**预构建数据库**（Human/Mouse），**无需** mkref。

## When to Use（触发判定 · 用户特别指定）

### ✅ 触发条件（必须全部满足）
1. **厂家已确认 = 华大 BGI / DNBelab C 系列**（用户明确说是华大/DNBelab/MGI 单细胞数据，或已通过 Step 0 确认）——🔴 **没有确认厂家 = 不触发**
2. **类型已确认 = 需要构建 RNA 索引或 ATAC 索引**（用户说"建索引/mkref"，或拿到 DNBelab FASTQ 准备跑 `rna run`/`atac run` 但缺 `ref.json` 库）
3. **状态已确认 = 没有现成可用库**（官方预建库不存在 / 自定义物种 / 非人鼠物种）

### ❌ 不触发条件（命中任一即 redirect，不走本 skill）
| 场景 | redirect 到 |
|------|------------|
| 用户没确认是华大平台 / 只是说"建索引"但厂家未知 | **先问**（Step 0 ①），不猜 |
| 10X Genomics（Cell Ranger）/其他平台数据 | Cell Ranger 或标准 STAR/STARsolo 流程 |
| 常规 bulk RNA-seq 建索引 | 标准 STAR / hisat2 流程 |
| scVDJ 分析 | 直接 `vdj run --ref Human/Mouse`，无需建库 |
| 已存在可用参考数据库目录（含 `ref.json`） | 直接 `rna run --genomeDir` / `atac run --genomeDir`，不重复建库 |
| 仅需 FASTA 建 general STAR 索引（无 GTF/无 DNBelab 结构） | 标准 STAR |
| 用户只是问参数/讨论流程（analysis_plan/knowledge_ask） | 只回答，不执行建库；不触发本 skill 的 Pipeline |
| 用户要跑的是分析（rna run/atac run）而非建索引 | 已建库→直接跑；未建库→本 skill 先建库（确认厂家后） |

### 环境门槛（官方要求）
- **Linux x86-64**；**CentOS 7.x+**（kernel 3.10.0+）；**≥50GB RAM；≥4 CPU**
- dnbc4tools 以 **tar.gz 闭源二进制**发布（v2.1.3 = 494M，MD5 `dac23475b79cb07cc5b7d4f092aa67fa`），解压即用，无需编译
- 下载：BGI CloudDrive `https://bgipan.genomics.cn/#/link/eCSNwpwnrlc2Mdqtjy6A`（访问码 `CABq`）

## Pipeline

> 所有命令中 `$dnbc4tools` 为可执行程序实际路径（如 `/opt/software/dnbc4tools2.1.3/dnbc4tools`）。

### Step 0: 安装与验证
```shell
Tool: terminal
tar -xzvf dnbc4tools2.1.3.tar.gz
$dnbc4tools -v            # 验证可执行
# 目录应含: dnbc4tools / external / lib / misc / sourceC4.bash
```

### Step 1: 准备 FASTA + GTF
- **FASTA**：`primary` 组装版本基因组（推荐 Ensembl/Gencode）
- **GTF**：必需，**不支持 GFF**。至少包含 `gene`/`transcript` 类型 + `exon` 类型；属性含 `gene_id`/`gene_name` + `transcript_id`/`transcript_name`
- 人：Gencode release_32（GRCh38 primary）；鼠：Gencode M23（GRCm38 primary）

### Step 2: GTF 处理（`dnbc4tools tools mkgtf`，可选但强烈推荐）
```shell
Tool: terminal
# 2a. 基因类型统计（看 tag type 选项）
$dnbc4tools tools mkgtf --action stat --ingtf genes.gtf --output gtfstat.txt --type gene_biotype
# 2b. 校正缺失行（填补 gene/transcript 行，多基因重叠位置会警告）
$dnbc4tools tools mkgtf --action check --ingtf genes.gtf --output corrected.gtf
# 2c. 基因类型过滤（默认保留 protein_coding/lncRNA/IG_*/TR_* 等，可用 --include 自定义）
$dnbc4tools tools mkgtf --ingtf genes.gtf --output genes.filter.gtf --type gene_type
```

### Step 3a: scRNA 索引构建（`dnbc4tools rna mkref`）—— ⚠️ 仅当 Step 0 确认是 **RNA 索引**
```shell
Tool: terminal
$dnbc4tools rna mkref --fasta genome.fa --ingtf genes.filter.gtf --species Homo_sapiens --threads 10
# 人鼠官方示例：
# wget http://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_32/GRCh38.primary_assembly.genome.fa.gz
# wget http://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_32/gencode.v32.primary_assembly.annotation.gtf.gz
```

**输出目录**（含 `ref.json` 即成功）：
```
genomeDir/
├── chrLength.txt / chrNameLength.txt / chrName.txt / chrStart.txt
├── exonGeTrInfo.tab / exonInfo.tab / geneInfo.tab / transcriptInfo.tab
├── Genome / SA / SAindex
├── sjdbList.out.tab / sjdbList.fromGTF.out.tab / sjdbInfo.txt
├── genomeParameters.txt / Log.out / mtgene.list / ref.json
├── genes.filter.gtf + 原始 fasta/gtf
```

### Step 3b: scATAC 索引构建（`dnbc4tools atac mkref`）—— ⚠️ 仅当 Step 0 确认是 **ATAC 索引**
```shell
Tool: terminal
$dnbc4tools atac mkref --fasta genome.fa --ingtf genes.filter.gtf --species Homo_sapiens --prefix chr --threads 10
```
**输出目录**：
```
genomeDir/
├── chrom.sizes / genome.index / genome.fa.fai
├── tss.bed / promoter.bed
├── blacklist（自动匹配 hg19/hg38/mm10.full.blacklist.bed）
├── ref.json
```

### Step 4: 验证 ref.json + 下游使用
```shell
Tool: terminal
cat genomeDir/ref.json   # 记录 species/genome/gtf/genomeDir/chrmt/mtgenes + atac 另有 index/chromeSize/tss/promoter/blacklist/genomesize
# 下游：
$dnbc4tools rna run --name sample --cDNAfastq1 ... --oligofastq1 ... --genomeDir genomeDir --threads 10
$dnbc4tools atac run --name sample --fastq1 ... --fastq2 ... --genomeDir genomeDir --threads 10
```

## Parameters

### `dnbc4tools rna mkref`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--fasta` | 必需 | — | 参考基因组 FASTA（path） |
| `--ingtf` | 必需 | — | 注释 GTF（path；必需，不支持 GFF） |
| `--species` | 可选 | undefined | 物种名；细胞注释仅 `Homo_sapiens/Human/Mus_musculus/Mouse` 有效 |
| `--chrM` | 可选 | auto | 线粒体染色体名，auto 识别 chrM/MT/chrMT/mt/Mt → 生成 mtgene.list |
| `--genomeDir` | 可选 | 当前目录 | 数据库存放目录 |
| `--limitram` | 可选 | — | 索引生成最大可用 RAM（bytes） |
| `--threads` | 可选 | 4 | 线程数 |
| `--noindex` | 标志 | false | 已用 STAR 建过索引则只生成 ref.json 跳过索引 |

> 对不同大小染色体的基因组，**自动确定** `genomeSAindexNbases` 与 `genomeChrBinNbits`（STAR 2.7.2b 打印 `genomeSAindexNbases: 14 / genomeChrBinNbits: 18` 类日志）。

### `dnbc4tools atac mkref`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--fasta` / `--ingtf` | 必需 | — | 同上（GTF 至少含 gene/transcript 类型） |
| `--species` | 可选 | undefined | 同上 |
| `--prefix` | 可选 | chr | 染色体名前缀（chr 或空） |
| `--threads` | 可选 | 4 | 线程数 |
| `--genomeDir` | 可选 | 当前目录 | 输出目录 |

### `dnbc4tools tools mkgtf`

| 参数 | 类型 | 说明 |
|------|------|------|
| `--action` | 可选 | stat（统计）/ check（校正缺行） |
| `--ingtf` / `--output` | 必需 | 输入/输出 GTF |
| `--type` | 可选 | gene_biotype / gene_type（视图 tag 决定） |
| `--include` | 可选 | 逗号分隔保留的 gene 类型（默认 protein_coding,lncRNA/lincRNA,antisense,IG_*,TR_*） |

## Proven Scripts

> 经实际运行验证成功的脚本记录。`skill_evolution(action="record_run")` 自动追加至此表。
>
> 🆕 评分规则：`auto` 来自 rail_review 技术审查，`user` 来自用户认可。`query_logs` 按 approved → recency → score 排序推荐。

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|:----|:----|:----|:----:|:-----|:----:|:----:|:-:|
| <!-- 首次运行后自动填充 --> | | | | | | | |

| - | - | - | 2026-08-28 | - | - | - |  |
## Common Issues

1. **GTF 缺 gene/transcript 行** → 主流程注释报错。用 `mkgtf --action check --output corrected.gtf` 校正，并检查 Warning 中的多基因重叠位置（该区 reads 会被过滤）。
2. **GFF 当 GTF 传入** → 报错。dnbc4tools 只支持 GTF，转格式后重试。
3. **`rna run` 找不到索引** → `--genomeDir` 必须指向含 `ref.json` + STAR 索引文件的目录，两处路径一致。
4. **细胞注释物种无效** → `--species` 用官方允许值（Homo_sapiens/Human/Mus_musculus/Mouse），否则跳过注释。
5. **Windows 无法运行** → dnbc4tools 是 Linux x86-64 闭源二进制，Windows 下用 WSL/集群/容器。
6. **内存不足** → mkref 是 RAM 密集任务（建议 ≥50GB），可用 `--limitram` 限制并加 `--threads` 提速；OOM 时减小线程数重试。
7. **下载链接慢/失效** → 官方 BGI CloudDrive（访问码 CABq）或 GitHub Releases；注意 2026-01-15 有修复 HTML 报告的重新上传版。
8. **STAR 版本差异** → 官方固定 2.7.2b genomeGenerate（日志首行 `STAR verison: 2.7.2b`），不要手动覆盖 genomeParameters.txt。
9. **被误触发** → 用户只是说"建索引"但厂家未知（可能是 10X/常规流程）→ 按触发门禁 Step 0 先澄清，不要默认路由到本 skill。

## References

- 官方 GitHub（version2.0 分支，dnbc4tools v2.1.3）：https://github.com/MGI-tech-bioinformatics/DNBelab_C_Series_HT_scRNA-analysis-software/tree/version2.0
- 安装说明：https://github.com/MGI-tech-bioinformatics/DNBelab_C_Series_HT_scRNA-analysis-software/blob/version2.0/doc/installation.md
- 流程总览：https://github.com/MGI-tech-bioinformatics/DNBelab_C_Series_HT_scRNA-analysis-software/blob/version2.0/doc/pipeline.md
- scRNA pipeline（中文）：https://github.com/MGI-tech-bioinformatics/DNBelab_C_Series_HT_scRNA-analysis-software/blob/version2.0/doc/pipeline/scRNA.md
- scATAC pipeline（中文）：https://github.com/MGI-tech-bioinformatics/DNBelab_C_Series_HT_scRNA-analysis-software/blob/version2.0/doc/pipeline/scATAC.md
- 参数文档（中文）：https://github.com/MGI-tech-bioinformatics/DNBelab_C_Series_HT_scRNA-analysis-software/blob/version2.0/doc/parameter/scRNA.md
- Quick Start（建库+分析示例）：https://github.com/MGI-tech-bioinformatics/DNBelab_C_Series_HT_scRNA-analysis-software/blob/version2.0/doc/quickstart.md
- 输出 io 说明（Seurat/scanpy 读取）：https://github.com/MGI-tech-bioinformatics/DNBelab_C_Series_HT_scRNA-analysis-software/blob/version2.0/doc/io.md

---

## ⛔ Terminal 完成后强制协议（铁律 26 · 新 skill 模板自带）

```
1. rail_review(phase='post')
2. debate_analysis(topic="{分析描述}", context="参数+结果", knowledge_base_info=<KB>)
3. save_conclusions(module="{模块}", topic="{分析名}", ...)
   → 写入 {module}/conclusions.md + conclusions.json
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```

⛔ 创建新 skill 时，此协议块自动包含在 SKILL.md 末尾。