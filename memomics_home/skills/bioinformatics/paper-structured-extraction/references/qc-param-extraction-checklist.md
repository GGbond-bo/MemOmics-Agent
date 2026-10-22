# QC / 方法学提取变体：7 节模板 + 参数清单 + 定位技法

来源：2026-10-20 session（精读 3 篇人类胚胎单细胞文献，逐篇 7 节 + 三篇对比表，要求「含精确质控参数」并「务必带英文原文引用作为证据，标注出自 Methods 哪一段」）。
样本：Xiang 2020 Nature（Smart-seq2）/ Tyser 2021 Nature（Smart-seq2）/ Ai 2023 Cell Research（10×）。

---

## 一、7 节模板（方法学/QC 向，与主模板 10 节并列的变体）

用户常说「精读 N 篇文献，逐篇产出中文结构化报告（含精确质控参数）」——此时用这套 7 节，而不是 10 节：

1. **研究问题与核心结论**：一句话 ≤60 字 + 3–5 条主要发现，**每条带具体数字**（细胞数/基因数/比例/胚胎数）
2. **样本与数据规模**：胚胎/样本数、分期（Carnegie stage 或 d.p.f./E 日龄，**二选一并写清原文用哪个**）、细胞数、测序平台+版本、样本来源、伦理（批号+机构+声明原文）
3. **生信分析全流程**：**按顺序**列 比对/定量 → 过滤 → 标准化 → 降维 → 聚类 → 注释 → 下游；每步写「软件名 + 版本 + 关键参数」。表格形式最易核对（列：步骤 / 工具·版本 / 关键参数原文）
4. **质控参数（本类任务的重点节）**：见下「二、参数清单」，逐条数字 + 原文英文句
5. **细胞类型注释策略与 marker**：注释策略一句话 + 列出全部鉴定出的主要细胞类型 + marker 基因
6. **下游分析**：轨迹/通讯/空间/GRN/DEG/甲基化等，逐项注明工具（有版本写版本；未写版本写「原文未报告版本」）
7. **数据与代码可用性**：GEO/ArrayExpress/GSA 等**登录号原文照抄**（注意 2023 后中国团队多用 GSA/NGDC BioProject，非 GEO）+ 参照数据集号 + 代码仓库（没有就写「未提供独立仓库」）

末尾追加 **N 篇对比表**：维度建议 = 研究阶段 / 物种·材料 / 样本量 / 测序平台 / QC 阈值（拆成「最低基因数」「MT% 上限」「doublet」「过滤保留率」多行更好读）/ 主要方法差异 / 数据登录号 / 代码。

---

## 二、质控参数清单（逐条问，缺就写「原文未报告」）

这是本变体的核心。**逐条**输出数字 + 原文英文句 + 该句所在 Methods 段名。**不要因为"这是常识应该有"就替作者补一个数**。

| # | 参数 | 备注 |
|---|---|---|
| 1 | 最低基因数（nFeature/nGene 下限） | Smart-seq2 常写成 "more than 2,000 detected genes" |
| 2 | 最高基因数上限（nFeature 上限） | 多数论文**不设**，写「原文未报告」 |
| 3 | UMI / counts 阈值（nCount 上下限） | **仅 UMI 体系（10×）适用**；Smart-seq2 无此概念，写「不适用（Smart-seq2 非 UMI）」 |
| 4 | 线粒体基因比例上限（MT%） | Smart-seq2 常写 "mapping rate to mitochondrial genes (<0.02)"；10× 常写 "below 20%" |
| 5 | 核糖体基因比例上限 | 多数不设 |
| 6 | doublet 检测方法与阈值 | 10× 常 DoubletFinder（写清 v 版本 + multiplet rate 取法）；Smart-seq2 多用 FACS 单细胞分选替代 → 写「未做 doublet 检测（FACS 分选替代）」 |
| 7 | 环境 RNA（ambient RNA）去除 | SoupX/DecontX/CellBender；多数不写 |
| 8 | 过滤后保留的细胞数 / 基因数 | 必答 |
| 9 | 过滤掉的细胞比例 | 必答（= 1 − 保留/初始），**用原始两数自己算要标注是自算** |
| 10 | 上游额外门槛 | reads/cell 下限、比对率下限、ERCC/外源 spike-in 比例上限等 |

同时记录：初始细胞数 → 过滤后细胞数（如 1719→1195、557→555）；若正文未给，注明数字在哪张补充图（如「见 Supplementary Fig. S1a」）**并明确说明该补充图不在所给源文本内**。

---

## 三、★ 平台决定 QC 可比性（最重要的判读纪律）

**Smart-seq2 与 10× 的 QC 参数不是同一套，不能横向拉齐比较，也不要用一套去要求另一套。**

| | Smart-seq2（全长、非 UMI） | 10× Chromium（UMI） |
|---|---|---|
| 主要门槛 | 检出基因数、比对率、MT reads 比例、ERCC spike-in 比例 | nFeature/nCount 上下限、MT% 上限、doublet rate |
| UMI 阈值 | 不适用 | 适用 |
| doublet | 通常不做（FACS 分选 + live/dead 染料） | DoubletFinder/Scrublet |
| MT% 形态 | 常写成 mapping rate（如 <0.02） | 常写成百分比（如 <20%） |
| 过滤淘汰率 | 常极低（本 session 一篇仅 2/557=0.36%） | 常较高（10–30%） |

对比表里必须把这一差异点出来，否则读者会误以为「阈值宽松=质量差」。

---

## 四、定位技法：keyword-grep 先行，再定点读（省 token 的关键）

源文本动辄 3 万 token/篇（本 session 三篇分别 8.5 万/10 万/11.6 万字符）。**不要一上来就从头读到尾**：

1. `search_files(target=files)` 或 `wc -c` 确认体量与页码范围（`grep -n "===== PAGE"` 看分页锚点）
2. **一次 grep 扫全部 QC 关键词拿行号**：
   ```
   grep -n -iE "mitochondrial|MT-|nFeature|nGene|gene count|UMI|doublet|Cell ?Ranger|Seurat|Harmony|ambient|quality control|filter|threshold|[0-9]{3,} cells" <file>
   ```
   再加一轮结果/样本关键词：`grep -n -iE "ethic|consent|Carnegie|approv|GEO|accession|GSE|PRJCA|Carnegie|d\.p\.f|^E1[0-4]|[0-9,]{3,} (single )?cells"`
3. 由行号**定点读** 3–5 个区段即可写完 7 节：① 摘要+结果开头（样本量与主要数字）② Methods 的 QC/比对段 ③ 数据可用性 + 伦理段 ④ Extended Data figure legends（QC 图注常补充阈值）⑤ Reporting Summary（软件版本与 ethics 在这里最全）
4. **grep 命中 0 必须用 read_file 复核该区域再写「原文未报告」**——带 `.`/`-` 的版本号或 `|` 多模式可能漏匹配（与主 SKILL §四 同一条坑）

---

## 五、证据锚定格式（用户显式要求，照此执行）

用户原话：「务必带**英文原文引用**作为证据，标注出自 **Methods 哪一段**」。

每条 QC 参数写成：

```
- **线粒体基因比例上限：<0.02（<2%）**
  原文（Methods「Raw data processing and normalization」）：
  "we only retained cells with more than 2,000 detected genes, with overall mapping rate
   greater than 55% and with relatively low mapping rate to mitochondrial genes (<0.02)
   and to ERCC spike-ins (<0.2)."
```

要点：
- 引号内**逐字照抄英文**，不改写、不缩写、不加省略号吞掉关键数字
- 段名用**原文 Methods 的真实小节标题**（如「Quality control, alignment of the scRNA-seq profiles and stringent filtering」「Single cell dissociation, RNA-seq and data processing」），不要自己概括成「方法部分」
- 一次可引同一段多句，但**每条参数都要能看到对应数字落在引文里**
- 行号（本仓库源文本为 txt dump 时）与段名可并存，段名对用户更可读

---

## 六、典型「原文未报告」清单（本 session 实测，供预判）

- 2020 Nature Xiang：MT%、UMI/counts、最高基因数、核糖体、doublet、ambient RNA **全未报告**（仅设「FPKM>1 的基因数 >2,000」一条硬阈值）
- 2021 Nature Tyser：**无**最高基因数 / 核糖体 / doublet 阈值（MT 与 ERCC 有，最完整的一篇）
- 2023 Cell Research Ai：最低基因数只写 "based on number of expressed genes" **未给数字**；doublet 用 DoubletFinder 但**未给比例阈值**；**过滤后细胞数/基因数与胚胎数在 Supplementary Fig. S1a（不在所给源文本内）**

→ 遇到这种「数字在正文外」的情况，**不要留空、不要猜、不要从图里目测一个数**：写「正文未报告，见 Supplementary Fig. S1a（该补充材料未包含在本次源文本中）」。