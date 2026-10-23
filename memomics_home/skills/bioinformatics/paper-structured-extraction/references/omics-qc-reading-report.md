# 变体：组学论文精读报告（scRNA-seq / 空间转录组，QC 参数为重点）

适用触发：用户要求「精读 N 篇文献 / 逐篇产出中文结构化精读报告」且对象是**组学论文**（scRNA-seq、snRNA-seq、
空间转录组 Stereo-seq / Visium、多组学），并常附带硬要求：**含精确质控参数**、**务必带英文原文引用作为证据**。

与主模板（§二 10 节，偏 AI-agent/方法论文）的区别：本变体把重心放在 **样本与测序规模** 和 **QC 阈值**，
并要求**每条数字后面挂英文原文引用**（不是只给行号），未报告项写「原文未报告」。

---

## 一、7 节模板（每篇独立一级标题分节）

1. **研究问题与核心结论（含具体数字）** —— 引用原文说明 gap；结论逐条带数字（细胞数、cluster 数、关键基因/通路）。
2. **样本与数据规模** —— 建议表格。必填：胚胎/样本数、发育阶段（Carnegie stage / PCW / E）、细胞数、
   测序平台（10x Chromium 试剂盒版本、Illumina 机型、读长）、参考基因组（hg19/hg38/mm10）、
   空间平台（Stereo-seq / Visium）、**空间分辨率（bin 尺寸 / spot 直径；未报告就写「原文未报告」）**、
   切片厚度与数量、透化时间、公共参考数据。
3. **生信分析全流程（软件名 + 版本 + 关键参数，按执行顺序）** —— 编号 1..N，每一步给版本号与参数；
   顺序照原文方法学走（比对 → QC → 归一化 → 降维 → 批次校正 → 聚类 → 注释 → 下游）。
4. **质控参数（本任务重点）** —— 拆 scRNA 与空间两个子表，见 §三。
5. **细胞类型注释策略与 marker** —— 策略（无监督聚类 + marker + GO？空间约束聚类？标签转移？）+ 代表 marker 基因逐个列出。
6. **下游分析** —— 3D 重建 / 空间域 / 轨迹 / 基因调控 / 细胞通讯 / 跨物种，**逐个注明工具名+版本**。
7. **数据与代码可用性** —— GEO / GSA-Human / ArrayExpress 号、Zenodo 代码 DOI（**「无新代码」也要如实照抄原文**）、交互网站。

末尾追加两段：
- **两篇（多篇）对比表**（行=维度，列=各篇）；
- **「空间转录组 QC 与 scRNA QC 的差异」专节**——用户常显式点名要这一段，见 §四。

## 二、英文原文引用是证据，不是装饰

本变体要求「务必带英文原文引用作为证据」，落地方式：

- 每个关键数字/断言后跟 `「英文原句」`（或 `*"English quote"*`）。
- 引用**照抄**，不改写、不省略到失真、不拼接两处原文成一句。
- 「未报告」也要用原文**反证**：把方法学里实际写了什么引出来，再写「原文未报告」。
  例：空间 QC —— 引 Space Ranger 那句原文，然后写「spot 级 QC 阈值：原文未报告」。
- **用户常追加「标注出自 Methods 哪一段」** —— 此时引文必须挂**原文 Methods 的真实小节标题**，
  不要自己概括成「方法部分」。三段式最稳：

  ```
  - **线粒体基因比例上限：<0.02（<2%）**
    原文（Methods「Raw data processing and normalization」）：
    "we only retained cells with more than 2,000 detected genes, with overall mapping rate
     greater than 55% and with relatively low mapping rate to mitochondrial genes (<0.02)
     and to ERCC spike-ins (<0.2)."
  ```

  段名与行号可并存（行号给机器核，段名给人读）；若原文 Methods 无小节标题，写「Methods 第 N 段」。

## 三、QC 参数抽取清单（两个子表，逐条给数字 + 原文）

### scRNA-seq

| 必抽项 | 说明 |
|---|---|
| QC 前矩阵规模 | cells × genes（原文常写 "the merged matrix contains ..."） |
| 细胞过滤准则 | 每条独立列出：检出基因数下限、**是否有上限**、MT% 上限 |
| 基因过滤 | 基因至少在多少个细胞中表达才保留（min_cells 的 scRNA 版） |
| doublet 检测 | 工具 + 版本 + **全部参数逐个**（如 `n_prin_comps`、`expected_doublet_rate`、`sim_doublet_rate`）+ 剔除数量 |
| QC 后保留 | cells × genes |
| **过滤比例** | 只有原文写了才直接引用；**通常需自己算** → 必须标注「据原文数字计算，原文未直接给出百分比」 |

### 空间转录组（Visium / Stereo-seq）

| 必抽项 | 说明 |
|---|---|
| 过滤单元 | spot（Visium）/ bin（Stereo-seq，如 bin50 = 50×50 DNBs） |
| 有效分辨率 | bin 边长或 spot 直径；Stereo-seq 给 DNB 间距（如 500–750 nm）+「每 bin ≈ 1–3 个细胞」的原话 |
| spot/bin 最低计数 | UMI 下限（常**不报告**） |
| **spot/bin 最低基因数** | 如 `min_gene = 100` |
| **MT% 阈值** | 空间常比 scRNA 严得多（如 percent.mt < 5） |
| 面积过滤 | **空间特有维度**；Stereo-seq 固定网格一般不设，Visium 论文常不报告 → 写「原文未报告」 |
| 基因级 min_cells | 如 `min_cells = 10`（bin 总数远少于细胞数，阈值相应低） |
| doublet 检测 | 空间**通常不做** → 写「未做（原文未报告）」 |
| 过滤后 spot 数 + 过滤比例 | 常见只给过滤后、**不给过滤前** → 比例写「原文未报告」 |
| 污染/非目标组织剔除 | 空间特有，如剔除共表达滋养层 marker（KRT7/LEP/PSG8）的 spot |
| 上游 reads 级 QC | Stereo-seq：CID 错配上限、MID 质量过滤、MAPQ 阈值；Visium：Space Ranger 参数 |
| QC 可视化 | 图号（如「Figure S1B 小提琴图：read counts / gene numbers / MT%，红虚线为阈值」） |

### 机械核验（把「禁止编造」变成可验证事实）

txt dump 读完后，**用 `search_files(target=content)` 或 grep 扫一遍 QC 关键词**，确认没漏、也确认「未报告」判断成立：

```
spot|filter|quality control|permeabil|percent.mt|min_gene|min_cells|MAPQ|bin50|Bin 50|
doublet|mitochondrial|UMI|retained|excluded|resolution
```

- **grep 有命中** → 回读该行区域取证。
- **grep 只返回无关命中（如 "single-cell resolution" 这类词组）→ 才可以下「原文未报告」的结论**，
  并在交付里说明「grep 后确认原文未报告」，让「未报告」也是可核查的。
- 注意 §一 Pitfall：含特殊字符的查询串可能漏匹配，grep 意外为 0 时回读原文区域复核，别据此判定未报告。

## 四、知识库：空间转录组 QC vs scRNA QC 的差异（复用结论）

1. **过滤单元不同**：scRNA 是 cell；空间是 spot/bin。
2. **MT% 口径相反**：scRNA 常规宽松（实测 **MT% < 20**）；空间通常更严（实测 **percent.mt < 5**）。
   原因：空间 spot 常含多个细胞叠加 + 切片/透化致 RNA 降解推高 MT%，沿用 scRNA 宽松阈值会留大量降解 spot。
3. **基因数上下限不同**：scRNA 常见**有上限**（如 800–6000，用来排双细胞/多细胞）；
   空间一般**只设下限且更松**（如 min_gene = 100、不设上限），因为 bin 本身含 1–3 个细胞，设上限会误杀。
4. **基因级 min_cells**：空间阈值更低（如 10）vs scRNA 常用「< 20 个细胞表达即剔除」，因 bin 总数远少于细胞数。
5. **面积过滤是空间特有维度**；但两篇实测论文均未报告，属领域共性短板。
6. **doublet 检测不适用空间**：scRNA 必做（Scrublet/DoubletFinder），空间论文**普遍不做**——
   spot 本身即多细胞混合，"doublet" 概念不成立；代之以空间域解卷积（Tangram / Seurat TransferData）或接受 bin 级混合信号。
7. **空间另有组织边界污染过滤**（剔除滋养层/非目标 marker 阳性 spot），scRNA 无此维度。
8. **上游 reads 级 QC 更复杂**：Stereo-seq 需 CID 定位 + MID 质量过滤 + MAPQ 阈值；Visium 由 Space Ranger 默认流程吞掉。
9. **透明度共性短板**：scRNA QC 通常完整（阈值 + doublet 参数 + 前后计数）；
   空间 QC 常**完全缺失**（实测一篇 Visium 论文零 spot 级阈值），或只给过滤后 spot 数、不给过滤前与比例。

### 典型平台 QC 指纹（实测样本，可作参照基线）

| 平台 | 指纹 |
|---|---|
| **Stereo-seq** | bin50 = 50×50 DNBs；DNB 间距 500–750 nm；上游 SAW pipeline（CID ≤1 错配、MID 含 N 或 >2 碱基 Q<10 剔除、MAPQ > 10）；bin 级 QC `percent.mt < 5, min_gene = 100, min_cells = 10`；每 bin 平均 ~3,283 UMI / 1,233 genes |
| **10x Visium** | Space Ranger（参考基因组常为 hg38，与 scRNA 用的 hg19 不同——注意分别记录）；切片 16 µm；透化 10 min；**实测论文未报告 spot 级阈值** |

> 平台默认参数（如 Visium 55 µm spot）**不要**当成原文报告值填进去——原文没写就写「原文未报告」。

## 五、执行流程

1. `search_files(target=files)` / `wc -c` 定位源文本与体量；txt dump 常带 `===== PAGE N =====` 页标记。
2. **分块精读**：`read_file` 带 `offset`/`limit`（每次 400–500 行）。**必须读到文件末尾**——
   STAR Methods 在参考文献**之后**，QC 阈值几乎都在那里；Visium/Stereo-seq 的 QC 更是只在 STAR Methods。
3. 用 §三 的两张清单逐条抽取，每条挂原文引用。
4. §三 的机械核验 grep 扫一遍，坐实「未报告」项。
5. 落盘成 markdown（路径如 `results/<sid>/data/<数据集>/reports/<主题>_N篇_结构化精读报告.md`），
   **同时**在回复里给出报告本体（交付物=报告本身）。
6. 回复里另附「核心质控发现」浓缩段 + 文件路径，避免让用户只能读文件。

## 六、Pitfalls

- **空间 QC 「原文未报告」是常态，不是你没找到**：先按 §三 grep 核验，再下结论；不要用平台默认值填空。
- **过滤比例多为自算**：原文只给前后数量时，比例要标明「据原文数字计算」；能不给就不给，避免引入未报告数字。
- **scRNA 与空间可能用不同参考基因组**（实测：scRNA hg19、Visium 空间 hg38）——分开记录，别合并成一个。
- **方法学在文末**：漏读 STAR Methods / Appendix = 漏掉全部 QC 阈值。这是本类任务最常见的失败模式。
- **「无新代码」也要如实照抄**（原文 "There is no new code generated in this study."），不要因为空就省略该节。
- **多篇必须各自独立分节**，对比表放在全部之后，不能替代分节。
- **n=1 的胚胎研究要照抄其统计免责声明**（原文常写明只做一个胚胎、未做生物学重复假设检验）——这是重要局限。