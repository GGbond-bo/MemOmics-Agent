---
name: input-data-integrity-audit
description: "分析输入定义文件的完整性审计（分析前必做）：比对原始 vs 「修复版/CLEAN/v2」派生文件、用官方 cardinality 指纹识别静默截断、区分来源分类与显示分组。触发：用户给一份基因集/通路/打分/元数据定义表要用它算分或做溯源、用户问「这个文件是不是我要的那份」、目录里同时存在原始与修复版文件。"
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

## 参考

- `references/input-file-integrity-audit.md` — 完整事故复盘：19 个基因集的逐集对照数字、官方 cardinality 指纹表、前向填充错位实例、来源分类 vs 脚本分组错位对照
