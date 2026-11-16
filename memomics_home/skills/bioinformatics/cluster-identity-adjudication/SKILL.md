---
name: cluster-identity-adjudication
description: "判定一个 cluster 是真实细胞类型还是污染/错注释/分辨率伪影，并裁决删、重新归类、还是保留；也判定整套亚型命名（L3/L4）是否站得住。触发：某亚群 marker 与注释不符、要不要删掉某亚群、这个群是不是污染、分辨率该用哪档、你的注释是否合理、找文章核对标注"
when_to_use: "[cluster-identity-adjudication] 判定 cluster 身份并裁决去留：某亚群 top marker 与注释不符 / 要不要删 / 是不是污染 / 分辨率 0.6 vs 0.8 更稳；以及**方案级审计**——用户问「你的注释是否合理 / 找找其他文章核对 / 这些亚型名有依据吗」、或你自己刚拼出一套 L3/L4 亚型准备交付前"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  memomics:
    tags: [annotation, clustering, contamination, QC]
    difficulty: basic
    language: Python
    category: scRNA
---

# Cluster Identity Adjudication

判定一个 cluster 到底是"真实细胞类型 / 污染 / 错注释 / 分辨率伪影"，并裁决删、重新归类、还是保留。

## When to Use

- 某亚群的 top marker 与它被分配的细胞类型不符（例：标"肌纤维"却冒出 NSG2/RYR2 这类神经元/心肌基因）
- 用户问"这个亚群要不要删" / "这是污染还是新细胞类型" / "分辨率 0.6 还是 0.8 更稳"
- 自动注释后出现未注释 / 注释不确定的新群，需要定身份

## 六步证据采集（每一步实查，不猜）

1. **细胞数**：<50 技术噪声小群，还是 >千 的真实群体？
2. **QC**：nFeature/nCount/percent.mt 是否正常？双细胞 nFeature/nCount 偏高、死细胞 percent.mt 偏高、环境 RNA 低 UMI。QC 正常 = 真实细胞，不是该"删"的对象。
4. **打分面板**：若有 AUCell/AddModuleScore（肌节/氧化磷酸化/应激/衰老等），看该群相对其他群的打分。被标"肌纤维"却 sarcomeric/OxPhos 全表最低 = 注释错配的硬证据。
5. **生物学信号**：该群在某条件（衰老/疾病/运动）下是否差异显著 / 比例变化？有信号 = 真实生物学群体，删掉丢信息 + 扭曲比例。
6. **分辨率伪影判定**：top marker 的 log2FC 若 >~4（几十倍差异），**不是**过度聚类的伪影（假群 marker 边界模糊、log2FC 低）。降分辨率解决不了它，反而把它藏进邻近群，掩盖真实异质性。

## 方案级审计：一套亚型命名是否站得住（L3/L4）

单群裁决管「这个群是真是假」，本节管「**这个亚型名字合不合法、粒度是否过切**」。
用户在拿到注释结果后会直接问「你的注释是否真的合理 / 找找其他文章核对」——这就是本节的触发点，
**不要用「我用了经典 marker」来答，那只是在重复自己的假设，必须做下面两道外部检验。**

### 检验 A：判别力（几秒钟，先在数据里自查）

命名一个亚型 = 宣称该基因能把它与兄弟群分开。用**检出率**（percent expressing，不是平均表达）直接验：

```
pct(命名基因, 本群)  vs  max pct(命名基因, 其他所有群)
```

| 结果 | 判定 |
|---|---|
| 本群高出兄弟群 ≥2 倍或 ≥30 个百分点 | ✅ 可作亚型 marker |
| 本群与兄弟群都在 90%+ | ❌ **泛身份基因冒充亚型基因 → 该亚型不可分** |
| 本群低于某个兄弟群 | ❌ **命名与数据相反，必须撤销** |
| 本群检出 <5% | ⚠️ 名字几乎必然误导，换基因或标注弱依据 |

> 实测教训：三个命名为 `CapEC_BTNL9 / CapEC_CD36 / CapEC_GPIHBP1` 的毛细血管亚型，
> BTNL9 检出率分别是 97.7% / 94.5% / 90.6% —— **在命名基因上完全不可分**；
> `Pericyte_NR2F2` 的 NR2F2（75.2%）反而低于兄弟群 `Pericyte_HIGD1B`（88.3%）。
> 这类错误靠「看一眼 DotPlot 觉得分得开」是发现不了的，必须取数字。

### 检验 B：文献反查（把我用的命名基因丢进同类组织图谱全文数命中）

不是查「有没有人研究这个细胞」，而是**查我实际用作分组名的基因在本领域图谱里有没有先例**：

- 命名基因被原文明确列为该类 marker → 强支持
- 基因出现但语境是**另一种细胞** → 冲突信号，先做排除性 marker（PTPRC/CD68/CD163/ADGRE1）
- **全文 0 命中 → 自创命名**，可保留但必须标「文献无先例，探索性命名」

⚠️ 反向陷阱：**「文献里这个基因指另一种细胞」不等于我标错了**。
实测 `Pericyte_LYVE1`：两篇示例组织图谱的 LYVE1 都用于 LYVE1⁺ M2 巨噬细胞，
但该群 CD68/CD163/ADGRE1 全 ≤0.7%、PTPRC 仅 0.5% ⇒ 它是 CD45 阴性真周细胞。
**先排除，再下结论。**

### 检验 C：这个「亚型」是不是技术簇（2026-11-05 实测补，最容易被漏掉的一道）

检验 A 只问「能不能分开」，**不问「分开的是不是生物学」**。一个簇完全可以在数值上分得很开，
但分它的原因不是细胞类型，而是**测序复杂度**。判决两条硬指标，同时命中即判技术簇：

```r
top <- FindMarkers(obj, ident.1=cl, only.pos=TRUE)      # 或 FindAllMarkers 的该簇段
head(rownames(top), 20)                                  # ① top DE 基因名单
median(obj$nCount_RNA[obj$seurat_clusters == cl])        # ② 该簇 nCount 中位数 vs 其余簇
```

| 指纹 | 判定 |
|---|---|
| top DE 全是 **RPS\*/RPL\*/TMSB10/TMSB4X/EIF\*** 一类核糖体/翻译基因 | ⚠️ 翻译活性或**测序深度**假象，不是亚型 |
| 该簇 **nCount 中位数明显低于**兄弟簇（实测 1588 vs 其余 3000+） | 与上一行叠加 ⇒ **技术簇，不许给生物学命名** |
| top DE 是**功能基因**（UNC5B/CPAMD8/RGS6/SLIT3/EGFLAM/COL5A3…）且与兄弟簇 log2FC≥2 | ✅ 生物学亚型，可用该基因命名 |

处理：技术簇**并回父类**（如毛细血管 → 单一 `Capillary_EC`），但把内部亚簇编号留在
`<Parent>_subcluster` 列里备查 —— 既不丢结构，也不给它一个骗人的生物学名字。

> 实测：`CapEC_GPIHBP1` 951 细胞的 top DE 是 RPS12/RPL34/TMSB10/TMSB4X、nCount 中位数全场最低
> ⇒ 它是低复杂度技术分层，不是「一种毛细血管」。四个毛细血管簇最终只有 3 个有真实转录差异，
> 而它们的差异基因是 RGS6/UNC5B/CPAMD8，**不是** CA4/BTNL9/GPIHBP1 这些泛身份基因。

### 检验 D：命名与数据方向一致性（撤销级）

命名基因在本群低于兄弟群 = 名字直接说反了，**没有讨论余地**，必须撤销重命名。

> 实测：`Pericyte_PDGFRB` 的 PDGFRB 94%（四群中**最低**、兄弟群 98.5%）；
> `Pericyte_NR2F2` 的 NR2F2 75.2% 低于 `Pericyte_HIGD1B` 的 88.3%。
> 两者都被撤回，改用各自 FindMarkers 的真差异基因（SLIT3 4.95×、EGFLAM 99.1%、COL5A3/IL34/ANO1）。

### 同时要判「文献有、我没分出来」≠「我漏了」

| 情况 | 判定 |
|---|---|
| 该亚型定义基因在本数据检出 <1% | 数据不支持，照实写「本数据 IL6 检出 <1%，未分 IL6⁺venEC」 |
| 定义 marker 在本数据弥散在所有亚群（如 CD44 在各周细胞群 32–49%） | 无独立群，不是漏 |
| 确实存在但被并进邻近标签 | 真遗漏，补分群 |

### 交付形状（用户要结论，不要检索日志）

一句话判定（允许直说「X 个标签站不住」）→ 文献基准表（论文 + 证据层级）→ **逐标签裁决表**
（标签 / 细胞数 / 命名基因本群% / 其他群最高% / 判定）→ 单列「必须承认的错误」并配真实数字 →
修正清单 + 询问是否重跑；证据表落 `results/<sid>/results/<name>_literature_audit.csv`。

完整流程、三个定量的实测数字、人示例组织血管参考面板（Lai 2024 Nature / Kedlian 2024 Nat Aging
的 EC 与壁细胞亚型 marker 表）、以及全文获取链见

## 兄弟群对比裁决：两个亚群是否同类、谁更典型（2026-11-05 实测）

触发语：用户把**两个亚群各自的 top 基因清单**贴过来问「这两个都是 X 吗？还是谁更像 X」。
这是与上面「单群真假」「整套命名」都不同的一类问题——**两个都可能是真的，要判的是同类性与典型度**。
⛔ 不要靠读基因名回答，同一批基因常常被两群共有（实测 SEMA3G 在两群 49.5% vs 49.6%，完全无法区分）；
必须取检出率与评分。五步全做，缺一步就可能把「状态」误判成「身份」。

### 步骤 1：分层评分——严口径与宽口径**必须同时报**

同一类细胞可以有「严格核心」与「泛化程序」两套基因，**两套评分会给出相反的排序**，只报一套就是误导：

| 评分 | 典型基因 | 回答什么 |
|---|---|---|
| 严口径（strict） | GJA5 / BMX / HEY2 / FBLN5 / GJA4 / SOX17 | 是不是**经典/终末**那一型（如大动脉/弹性动脉） |
| 宽口径（broad） | SEMA3G / EFNB2 / DLL4 / HEY1 / CXCL12 / GATA2 / NOTCH1 | 是不是**这个谱系**（含过渡态、Notch 高的分支） |

实测：亚群1 宽口径 0.436 > 亚群2 0.276（1.6 倍），但严口径 0.087 < 0.196（只有 0.44 倍）。
**结论必须写成「两群都属该谱系，X 群更经典」**，而不是「X 群是、Y 群不是」。

### 步骤 2：排除性评分——证明它们不是**别的**类型

只是「像目标类型」不够，还要给出「不像其他类型」的倍数：

```
本群 score / 该类型参考群 score   静脉实测 0.013、0.024 vs 真静脉 0.314 → 差 13–24 倍，干净排除
```

毛细血管污染评分还能顺手当**纯度指标**：实测亚群2 = 0.018（全场最低）< 亚群1 = 0.138，
「谁更纯」据此定，别凭感觉。

### 步骤 3：ambient 方向检验——marker 是自身表达还是旁边漏来的

某个基质/分泌基因在目标群很高时，先问「它的**源细胞类型**是不是更高」：

| 观测 | 判定 |
|---|---|
| 源细胞类型（如 SMC / 周细胞）检出率 **高于**目标群 | ⚠️ 疑似 ambient / doublet，不能当身份证据 |
| 源细胞类型 **明显低于**目标群 | ✅ 目标群自身表达（反向不可能由污染产生） |

实测：ELN 在亚群2 81.9%，而 ELN 的源细胞 SMC 只有 28.9%、SULF1 14.2% ⇒ **排除 SMC ambient**，
是内皮自身表达。这条比"看 nCount 高不高"硬得多。

### 步骤 4：身份 vs 状态——最容易翻车的一步

签名基因若恰好也是**衰老 / 疾病 / 干预**相关基因，且该群**组别分布偏斜**，那它可能是「状态」不是「身份」：

```
① 查组别构成：table(obj$condition, obj$subgroup) → 某群年轻组占比 14.7% vs 另一群 44.3%（偏斜明显）
② 簇内分层：在该群**内部**按条件重算 marker 均值
③ donor 级检验：每样本先取均值再 Wilcoxon（避免细胞数当重复的伪重复）
```

实测两种结局都出现过，必须真的跑：
- ELN/SULF1（血管僵硬 ECM 基因）在亚群2 **年轻组已 1.37/1.62**，Old 1.60/1.76，donor 级 p=0.118
  ⇒ **不显著**，是固有身份，衰老混淆被排除。
- 若反过来 p<0.05 且年轻组很低，则必须改述为「XX 条件下的高基质状态」，不能叫大动脉。

### 步骤 5：命名基因的条件稳定性（检验 A 之外的新门槛）

检验 A 只问「群间可分」，**不问「跨条件稳不稳」**。命名基因若随年龄/干预显著变化，标签自带偏倚：

实测 SEMA3G 在两群都随年龄显著下降（donor 级 p=1.3×10⁻⁵ / 8.4×10⁻⁴，0.58→0.33、0.79→0.33），
而 BTNL9 在 47/47 样本稳定（1.73 vs 1.75，p=0.815）。
⇒ **命名应选「群间可分 且 跨条件稳定」的基因**，`Arterial_EC_SEMA3G` 应改成 `Arterial_EC_BTNL9`。

### 步骤 6：样本覆盖（排除「亚型」其实是单样本/批次伪影）

```
细胞数来自几个样本？最大单样本占比？per-sample mean 的 max_frac？
```

实测 47 / 45 个样本、最大样本仅占 10.8% / 15.1%、关键基因 per-sample `max_frac` 0.04–0.06
⇒ 广泛分布，不是少数样本的 ambient 或个体效应。
反之若只来自 1–2 个样本、或 `max_frac > 0.4`，该「亚型」先按批次伪影处理。

### 交付形状

**一句话判定**（「两个都是 X；Y 更像 X」）→ 模块评分矩阵（严/宽 + 排除性合计 5–6 行）→
关键基因检出率对照表（含否定性对照：毛细血管/静脉标记必须同时列出）→
把用户给的 top 基因**按功能归组**解释（不是逐个基因翻译）→ 单列「保留意见」并配数字 →
可选：命名修订建议表。

完整实测案例（全部数字、模块评分矩阵、组别分层、donor 级检验代码）见

## 修正版落盘：用户说「保存到原路径」时的固定动作（2026-11-05 实测）

审计出 v1 站不住、改出 v2 之后，用户通常直接说「**你先保存到原路径吧**」。这不是一条 `saveRDS` 的事，
三个坑会让人把**错的那版**持久化下去：

1. 🔴 **先查清哪一列是当前版本**。修正版很可能存在**另一个列名**里（实测：`annotation_L3` 仍是 v1 的
   14 标签，v2 在 `annotation_L3_v2`），此时直接覆盖原文件 = 主列还是被推翻的旧结果，后续所有人读到错版本。
   ```r
   md <- obj@meta.data
   print(sapply(md[grep("annotation|cluster|celltype", names(md))], function(x) length(unique(x))))
   # 或分别 table(md$annotation_L3)、table(md$annotation_L3_v2) 对照标签数
   ```
   正确写法：**修正版提升为主列，旧版降级留痕**，不删——
   ```r
   obj$annotation_L3_v1 <- obj$annotation_L3      # 留痕：被推翻的版本
   obj$annotation_L3    <- obj$annotation_L3_v2   # 主列 = 修正版
   stopifnot(sum(is.na(obj$annotation_L3)) == 0)  # 落盘前 NA 必须为 0
   ```
2. 🔴 **`obj$col <- named_vector` 会被当成 barcode 对齐**，名字是簇号时报
   `No cell overlap between new meta data and Seurat object`。修法一行：`unname(vec)`。
   （`map[as.character(x)]` 这类命名向量映射，赋值给 meta 列前一律 `unname()`。）
3. 🔴 **原子覆盖，别直接写回原文件名**：中途失败会留下半截文件 → 原文件报废。
   ```r
   tmp <- file.path(dirname(dst), ".tmp_annot.rds")
   saveRDS(obj, tmp); ok <- file.rename(tmp, dst)   # 同文件系统内 rename 是原子的
   ```
   集群上还要先 `cp -p <原文件> <原文件>_L2orig_backup.rds`，写完用 `md5sum` 对照新旧两份，
   `file.size()` + 时间戳复核（实测 861,178,653 → 861,237,269 字节，165.9 秒，`readrds_calls` 仍为 1）。

## 裁决框架

| 情况 | 裁决 |
|---|---|
| 噪声小群 + QC 差 + 无信号 | 删 |
| 真实细胞 + QC 正常 + 有信号但注释错 | **移出错误注释 + 重新归类，不删** |
| 真实细胞 + QC 正常 + 无信号 + 身份模糊 | 重新归类，或标 "unresolved" 待查 |

**核心原则**："删 vs 留" 是伪二选一，正确的第三选项是"移出错误注释 + 重新归类"。删一个真实且有信号的群体是最差选项（丢信号 + 比例失真）；留在错误注释里会污染下游所有该细胞类型的结论（比例、DEG、富集、跨组比较）。

## 分辨率裁决要点

- **先澄清**：查 meta 表实际存了哪几档分辨率（`SCT_snn_res.*` 列），用户记忆中的档位（如 0.6）可能根本不存在。
- 强特异性群体（log2FC >~4）不是分辨率伪影，降分辨率（0.8→0.6）不解决身份问题，反而掩盖异质性——高分辨率至少把它单独暴露出来。
- 主分析层用粗层（L2 / celltype 大群）最稳；细层（L3 program 命名亚群，如 LRP1B+(I)/OTUD1+(I)/RP_high）需逐一 marker 核验是否有生物学意义。

## 交付物：必须出证据图（rail_review(post) 强制 ≥1 图）

裁决类任务跑完证据采集后，rail_review(phase="post") 会硬查 output_dir 是否有图（figure_count≥1），否则判「未生成任何图片」拦下。标准三张证据图：
1. 条件/衰老占比柱状图（证明「有生物学信号」）
2. 七类 marker 交叉命中条形图（证明「身份锁定」）
3. AUCell 打分对比图（证明「非某细胞类型」）

中文标签用 Microsoft YaHei（`rcParams['font.sans-serif'] = ["Microsoft YaHei","SimHei"]` + `axes.unicode_minus=False`）。裁决结论落盘报告（Markdown + HTML 双份），并调 `skill_evolution(action="record_verdict")` 沉淀到 debate_verdicts。

## 参考


## Common Issues

| Error | Cause | Solution |
|---|---|---|
| read_file 读几百 MB 的 meta CSV 被"未登记大文件"门禁拦（>=100MB） | 大文件 | 用 pandas `usecols` + `chunksize` 流式只读需要的列，不整表进内存，既不触发门禁也不占内存 |
| `No cell overlap between new meta data and Seurat object`（给 `obj$newcol` 赋值时） | 传入的是**带 names 的命名向量**（名字是簇号 "0"/"1"…），Seurat 把名字当 barcode 去对齐 | `obj$newcol <- unname(vec)`；另查是不是把簇号当 barcode 传了 |
| **所有亚群指标静默变成 NaN**（不报错、不告警，矩阵打印出来整片 NaN） | 同一族的名字属性坑，但症状是静默的：`grp <- as.character(obj$annotation_L3)` **会丢掉向量名**，于是 `names(grp)` 是 `NULL`，`cells <- names(grp)[grp=="X"]` 取到 0 个细胞 → `rowMeans(m[g, cells])` 得 NaN | 取名时**显式重建**：`grp <- setNames(as.character(obj$col), colnames(obj))`；或干脆 `cells <- colnames(obj)[grp=="X"]`。跑完先 `cat(length(cells))` 抽查非 0，再信结果 |
| `presto::wilcoxauc` / `FindMarkers` 报 `number of columns of X does not match length of y`，伴随 warning `Layer 'RNA' is empty` | 对象某 assay 的层是空的（SCTransform/合并后常见：`RNA` 的 counts/data 空，真实数据在 `SCT`） | 先探层：`Layers(obj[["RNA"]])` 与 `Layers(obj[["SCT"]])`，然后 `GetAssayData(obj, assay="SCT", layer="data")`。**别把「assay 存在」当成「层有数据」** |
| 覆盖原 rds 后发现主列仍是旧版结果 | 修正版存在另一个列名里（如 `annotation_L3_v2`），`annotation_L3` 还是被推翻的 v1 | 保存前先 `table()` 对照两列标签数；修正版提升为主列、旧版降级为 `<col>_v1` 留痕，见「修正版落盘」节 |
| rail_review(post) 判「代码过短 (1 行)」不通过 | code_executed 传了单行摘要而非完整脚本 | code_executed 必须传**完整脚本代码**（用 read_file 读实际脚本文件内容再传入），传摘要会被判「偷懒」拦截，重传完整代码即通过 |

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| human | example_tissue | aging | 2026-11-02 | rss_adjudication_evidence.py | - | - |  |
| human | example_tissue | aging | 2026-11-02 | - | - | - |  |
| human | example_tissue | aging | 2026-11-03 | rss_adjudication_report.py | - | - |  |
| human | example_tissue | aging | 2026-11-03 | rss_adjudication_report.py | - | - |  |
| human | example_tissue | aging | 2026-11-03 | rss_adjudication_evidence.py | - | - |  |
