---
name: input-data-integrity-audit
description: "分析输入定义文件的完整性审计（分析前必做）：比对原始 vs 「修复版/CLEAN/v2」派生文件、用官方 cardinality 指纹识别静默截断、区分来源分类与显示分组。触发：用户给一份基因集/通路/打分/元数据定义表要用它算分或做溯源、用户问「这个文件是不是我要的那份」、目录里同时存在原始与修复版文件；也覆盖压缩参考文件（GTF/FASTA .gz）「这个能不能用 / 解压后再用」的三步自证（gzip -t → -k 解压 → 字节+行数+头部元数据）与断流检出。"
when_to_use: "拿到任何分析输入定义文件（基因集定义、通路清单、打分矩阵、样本元数据表）准备用它做打分/富集/溯源前；或用户问「这个是不是？」「该用哪份文件」；或你发现某组条目数整齐得可疑时。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [data-quality, provenance, geneset, input-validation]
    difficulty: basic
    language: Python+R
    category: bioinformatics
---

# 输入数据完整性审计

> 在**用一份输入定义文件做分析之前**审计它。本 skill 来自一次真实事故：
> 一份"修复版"文件比原始文件少了 10/22 个基因集的基因，且**不报错**——若直接拿它算分或做溯源，结论全错。

## 何时触发

- 用户交来一份**定义文件**（基因集定义表、通路清单、打分矩阵、样本元数据表），要用它做打分 / 富集 / 溯源 / 图注
- 用户问 **"这个文件是不是我要的那份？"** —— 别只看结构对就答"是"，**审计内容**
- 目录里**同时存在** `原始` 与 `修复版 / CLEAN / v2 / backup / tabfix` 之类的兄弟文件 → 必须逐条比对
- 你发现某几组的条目数**整齐得可疑**（多行落在同一个数字上）

## 铁律

| # | 规则 | 理由 |
|---|---|---|
| 1 | **永远不要相信"修复版 / CLEAN 版 / v2 / 最终版"派生文件** | 派生文件可能比原始更差且静默无报错；原始文件才是权威 |
| 2 | 用**官方 cardinality 指纹**判完整性 | 官方集条目数是固定值（MSigDB/KEGG/Reactome），对不上就是信号 |
| 3 | **排序中途截断指纹** | 按符号 A→Z 排列却停在字**母表中途** = 截断，不是精选 |
| 4 | **"魔法数字"= 截断信号** | 多组计数落同一个数（10 行里 9 行 = 23）是上限/截断，不是生物学子集 |
| 5 | 分类列**前向填充**，并**主动标注语义错位** | 分类列常只标每组首行且**无合并单元格**；延续会产生错位归属 |
| 6 | **来源分类 ≠ 显示分组** | 出图脚本的重排分组只服务排版，**不能当"分类依据"作答** |
| 7 | 副作用边界要说准 | 集群算好的打分不受派生文件影响，但**绝不能用派生文件重算/溯源** |

## 三步审计（确定性判据，不靠猜）

1. **原始 vs 派生 逐条计数比对** —— 同条目名/同行号逐个 `len(items)` 对比，列出全部不等项。最快暴露问题（一行代码即可扫全表）。
2. **官方 cardinality 指纹对表** —— 把每集计数与官方值并排列出，标 ✔ / ⚠️。多数吻合 ⇒ 原表可信；个别对不上 ⇒ **作为开放问题交回用户**，不要替作者圆场。
3. **排序中途截断 + 列上限 + 集内重复** —— 字母序停在中途即截断；末列被占用提示可能卡列上限；顺手扫集内重复（影响 AUCell/ssGSEA 权重）。

三步必须**交叉验证**后才下结论：单看"不像字母序"会误判（按重要性排序的清单天然不像字母序），要与 ①② 一致才成立。

## 交付物

```
results/<sid>/<task>/results/
  ├── <名>_provenance.csv   # 列: name, cls, annotation, n_original, n_derived, status
  └── <名>_provenance.md    # 人读版: 逐条溯源 + 分类汇总 + 与脚本分组的差异对照
```
`status` 列**直接写判定**（`✅ 一致` / `❌截断 -177`），不要只给数字让用户自己算。

## 读不开的输入表

Excel 输入常损坏：openpyxl 报 `KeyError: "There is no item named 'xl/drawings/drawing1.xml'"`，
而 `read_only=True` 会**静默返回空表**（假空表最危险，会让人以为"文件本来就是空的"）。
⇒ 兜底：把 xlsx 当 zip 解析 `sharedStrings.xml` + `worksheets/sheet*.xml`，
见 `platform-execution-pitfalls` 的 `references/corrupt-xlsx-zip-xml-fallback.md` 与其 `scripts/read_xlsx_manual.py`。
R 侧 `openxlsx::read.xlsx()` 对这类文件往往能读，可作交叉验证的第二条路。

## 参考文件（GTF / FASTA 等 `.gz`）「能不能用」：三步自证

用户拿一个**压缩参考文件**问「这个文件不能用吗？解压后再使用」时 —— 不要因为文件在场就答"能用"，
也**不要直接解压**（半截文件会被解压成"看起来正常、实际少了大半"的废文件）。顺序永远是：**先验完整性，再解压。**

| 步 | 命令 | 判据 |
|---|---|---|
| 1 | `gzip -t <file>.gz` | 通过 = CRC 完整；报 `unexpected end of file` = **下载断流**，必须重下 |
| 2 | `gunzip -k <file>.gz` | **`-k` 保留原包** —— 别删 `.gz`，它是校验过的原件 |
| 3 | 三重自证：**字节数 + 行数 + 头部元数据** | 例：GENCODE v32 GTF = **1,332,008,985 B / 2,900,496 行 / 头部 `GRCh38, version 32 (Ensembl 98), 2019-09-05`**（解压 ~1.1 s） |

**断流文件的典型特征**（实测目录里那份 v50 GTF）：`gzip -t` 报 `unexpected end of file`，
解压只有 **80,860 行 / ~65 KB**，而完整版应有 ~370 万行 / 55 MB 级别 —— 只剩文件头 + chr1 开头一小段。
⇒ 对它做任何分析都会**静默产出残缺结果**，属于必须拦截的一类；发现后**主动报给用户**，别默默跳过。

### 🔑 自证原则：基因身份 / 坐标类问题，以**原始注释文件**作答，不用 API 转述

实测用户原话：**「你下载下来，真实查看一下，它到底代表什么」**。数据库 API、网页摘要都是**二手转述**，
用户会要求回到**文件本身**：

```bash
grep -P 'gene_name "MEF2C(-AS1)?;"' gencode.v32.primary_assembly.annotation.gtf | head -4
# chr5 HAVANA gene 88717117 88904257 . - . gene_id "ENSG00000081189.15"; gene_type "protein_coding"; gene_name "MEF2C";
# chr5 HAVANA gene 88883328 89466398 . + . gene_id "ENSG00000248309.7";  gene_type "lncRNA";        gene_name "MEF2C-AS1";
```

- **第 9 列（attributes）就是答案本体**：`gene_type` = 官方 biotype（判"是不是编码基因"的权威口径）、
  `gene_name` / `gene_id` / `hgnc_id` / `level`
- 回答时**先把 `grep` 出的真实行贴给用户**，再补 API / 文献作交叉印证 —— **顺序反了会被质疑「你看过原文件吗？」**
- 顺带能数出"这份文件代表什么"的实证口径：三类行数
  （v32：`gene` 60,668 / `transcript` 227,529 / `exon` 1,372,563 / `CDS` 761,712 / `UTR` 310,268）

**GTF vs FASTA 选择判据**（用户问「我需要哪个」时）：

| 你要做什么 | 需要 |
|---|---|
| 已有 UMI/counts 矩阵，只做 DEG / 注释 / ID↔symbol 映射 | **只要 GTF** |
| 从 FASTQ 起比对定量、建参考索引（STAR / HISAT2 / cellranger mkref / dnbc4tools mkref） | **两个都要，且必须同 release** |
| 取某 lncRNA 的实际碱基序列（ORF 扫描 / 引物 / motif / 编码潜力验证） | 这时才要 FASTA |
| 判「某基因是不是非编码」 | **只要 GTF** —— `gene_type` 一行即官方结论，不必扫序列 |

⚠️ **GTF 与 FASTA 必须同 release、同 assembly**（如都是 release_32 + primary_assembly）——
混版本 → 坐标错位 → 定量结果直接废；染色体命名也要一致（`chr1` vs `1`）。
`primary_assembly` 版只含 40 条主序列（无 alt/patch 单倍型），查不到 alt 上的基因属正常，不是文件缺失。

## 参考

- `references/input-file-integrity-audit.md` — 完整事故复盘：19 个基因集的逐集对照数字、官方 cardinality 指纹表、前向填充错位实例、来源分类 vs 脚本分组错位对照
