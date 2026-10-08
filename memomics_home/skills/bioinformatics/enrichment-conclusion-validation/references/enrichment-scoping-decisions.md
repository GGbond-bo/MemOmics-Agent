# 富集口径 / 输入选择 —— 实例与依据（门禁 6 详版）

来源会话：`memomics-afd2d418`（人骨骼肌 48 样本 / 6 组 Y·O·OD × Pre·Post / 10 亚群 / universe 7,743）
用户原话（两次）：「**先别跑，我只是想先把口径和思路理清楚。**」「**不要太复杂，简单点。**」

---

## 一、两类被问到的口径问题（都是真问题）

### 情形 A：三组共同 DEG 交集只有 7 up / 2 down —— 要不要直接富集？

**答：不做 ORA 主分析，改 GSEA pre-ranked + 小列表描述性表。**

功效上限实算（universe 7,743；GO+KEGG ≈ 1 万条；BH 需 p<5e-6）：

| 列表 | 需要几个基因同属一条通路才能过校正 |
|---|---|
| 7 个（UP） | 小通路 **3/7**｜中型 **4/7**｜大通路 **5–6/7** |
| 2 个（DOWN） | **基本无解**（只有最小通路全中才勉强过） |

⇒ 只能看见「大多数基因挤在同一条通路」这种极端情形，**假阴性极高**；跑出非空结果也多半被 2–3 个基因撑着。

**同时必须说清：这 7/2 本身已是强结果**，不需靠富集立论。实测（`table6_overlap_significance.csv`）：

| 交集 | 观测 | 随机期望 | fold vs 随机 | P |
|---|---|---|---|---|
| 三组共同 UP | 7 | 0.002 | **3674×** | 2.0e-04 |
| 三组共同 DOWN | 2 | 0.017 | **115×** | 2.0e-04 |

⇒ 7/2 当「核心基因」讲：基因→通路/复合物描述性表（不写 P 值）。

**另一个被问到的方案「按每个亚群把交集基因挑出来」也不对**：交集本身就是跨亚群求交的产物，
按亚群拆只会得到近乎重复的更小列表（每群 0–2 个），**是把功效往反方向切**。

### 情形 B：785 个「衰老上升→运动下降」逆转基因 —— 按亚群分，还是拿全量？

**答：不是二选一，两个都做，但输入必须分开取。**

- 两者回答**不同问题**：
  - **全量 785** → 整体逆转程序（headline）
  - **逐亚群** → 「运动对每个亚群的影响涉及哪些词条」（用户真正想看的那层）
- 只做全量 = 异质亚群信号混在一起得到平均，**恰好看不出亚群差异**。

**关键操作约束**：逆转表（如 `table3a_reversal_aging_up_to_down.csv`，786 行含表头 = 785 基因）
自带 `Aging_subclusters` / `Ex_Old_subclusters` 列 —— **不能用这两列把 785 拆开**：

```text
AAK1   Aging_subclusters = LRP1B+(I);Pure Type I;Pure Type IIA;OTUD1+(I);Specialized MF;Pure Type IIX;RSS   ← 7 个亚群
AAMDC  Aging_subclusters = Pure Type IIA;Pure Type I;OTUD1+(II);Pure Type IIX                              ← 4 个
```

一个基因同时属于多个亚群 → 按列拆开**重复计数**，各亚群基因数之和 ≫ 785。
**正确做法：每个亚群回到自己的完整 DEG 表，取「该亚群 Aging↑ ∩ Ex↓」的基因。**

**其余约束**：
1. **universe 跟层走**：各亚群用自己的检测基因集（本项目约 6–7 千），⛔ 不要统一套全局 7,743。
2. **先出「每亚群反转基因数」一张表**：数量太少（<15）的亚群不单独下结论（功效不足）。
3. **汇总成「通路 × 亚群」矩阵**，比 10 张独立表清楚；表述用「某通路在 8/10 亚群出现」。
4. ⛔ **别把 3a（Up→Down）和 3b（Down→Up）混进同一个列表跑** —— 方向口径不同。

---

## 二、为什么「已筛列表再取 top100」不行

- 785 已经过一轮阈值筛选（FDR + |coef|）；**再取 top-N = 二次阈值**，
  且「top」取决于按什么排（coef？p？），按 p 排会系统性偏好高表达/低方差基因。
- **N 变成隐藏参数**：换 N 就换结论 → 方法学上站不住。
- 要控长度，正确工具是 **GSEA pre-ranked（阈值无关设计）**——GSEA 当初正是为绕开「阈值怎么切」而提出。
- ⚠️ 与门禁 5 的关系：门禁 5 讨论「θ 取多少」（一次阈值），本条讨论的是**不许做二次截断**。

---

## 三、文献依据（均逐字核实标题/作者/期刊/年份/DOI）

| PMID | 文献 | 用在哪 |
|---|---|---|
| 42018548 | Bora A, McKenzie M, Ziemann M. *Ten common mistakes that could ruin your enrichment analysis.* PLoS Comput Biol (2026). DOI 10.1371/journal.pcbi.1014122 | 口径错误清单（阈值/背景/多重检验家族） |
| 16199517 | Subramanian A, et al. *Gene set enrichment analysis: a knowledge-based approach for interpreting genome-wide expression profiles.* PNAS (2005) | GSEA 阈值无关设计的原始出处 |
| 32026945 | Geistlinger L, et al. *Toward a gold standard for benchmarking gene set enrichment analysis.* Brief Bioinform (2021) | ORA vs GSEA 方法学基准 |

内部依据：
- `functional-enrichment` 坑表「小基因集（n<15）在小家族内 BH 后假显著」（GOBP_MUSCLE_ATROPHY n=9 padj 0.006 → 全家族 3970 集合校正后 0.119）；
- KB `Homo_sapiens/skeletal_muscle/aging/03_测序方法/RNA/functional-enrichment_empirical.yaml`（本项目既往 universe/阈值口径）。

---

## 四、回答这类问题的格式（用户偏好）

- 先给**判定表**（方案 → ✅/❌ → 一句话原因），再给做法，最后给坑；不要长方案、长文献清单、十来条编号列表。
- 用 `dsh-ui` 结构化呈现（table / callout / steps）+ 一个 mermaid 决策图 —— 用户偏好这种「不复杂」的表达。
- 纯口径讨论时，末尾说明「**本轮没有新增或修改文件**」（用户会关心有没有动数据）。