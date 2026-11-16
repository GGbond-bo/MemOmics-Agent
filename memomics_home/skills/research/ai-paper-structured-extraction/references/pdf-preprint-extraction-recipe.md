# PDF 长预印本提取配方（含 CellVoyager 全量数值）

> 场景：用户直接给一篇 PDF（非 `.txt`），要求「精读 + 总结 背景 / 思路 / 实验内容（步骤+结果）/ 结论」。
> 实测标本：**CellVoyager: AI CompBio Agent Generates New Insights by Autonomously Analyzing Biological Data**
> （Stanford，James Zou 组；bioRxiv preprint 2025-06-04；doi 10.1101/2025.06.03.657517；31 页；99,245 字符）

## 0. 先落地全文（不要硬读 PDF）

```bash
OUT="results/<sid>/data/<paper>"; mkdir -p "$OUT"
.venv/Scripts/python.exe memomics_home/skills/bioinformatics/paper-summary/scripts/run.py \
  extract --tier1 --pdf "<pdf路径>" --out "$OUT"
```

产出：`fulltext.txt`（1678 行）/ `metadata.json` / `figures/`（3 张：fig_04_01 1.06 MB、fig_08_01 1.81 MB、fig_26_01 35 KB）/ `figure_captions`（5 条）。
依赖 pymupdf（`.venv` 已装 1.28.2）；`import fitz` 有 deprecation warning，不影响。

## 1. 章节地图与误命中（本例实际行号）

| 内容 | 行号 | 定位方式 |
|------|------|---------|
| Abstract | 10–38 | 直接读 |
| Introduction | 40 | 直接读 |
| Related Work | 113 | — |
| CellVoyager Methodology | 166 | — |
| CellBench 评估 | 269 | 编号节头 `^4` |
| Case Studies（结果） | 393–693 | 编号节头；子节 `5.1` COVID / `5.2` Endometrium / `5.3` Aging |
| Discussion | 696–746 | 直接读 |
| References | 798+ | — |
| Extended Methods（附录） | 1033+（`A.1`、`A.1.1`–`A.1.4`、`A.2`） | `grep -n "^A\.[0-9]"` |
| Supplementary Table 1（数值表） | 1648 | `grep -n "Table 1"` 的**第二条**命中 |

**误命中警告（两条，都会让人读错地方）**
1. 用上面那条综合 grep 会报 `422:Methods` —— 422 行附近根本不是 Methods 章（真正结果节从 393 行起）。→ 落到该行 read_file 核对后才能定结构。
2. `grep "Table 1"` 的首条命中是**正文 625 行的叙述引用**，真正的数值表在文末 1648 行（Supplementary）。只看首条会找不到数字。

其他噪声：bioRxiv 页脚每页都插版权声明 + `doi:` + `bioRxiv preprint`（约 4–6 行/页），占掉大量行号，别当正文内容。

## 2. 分块读（read_file 单次 ~100K 字符截断）

本例 4 块覆盖全部有效内容：`1–450`、`451–850`、`1015–1239`、`1634–1678`。
顺序：摘要/引言 → 框架 → 结果 → Discussion → 附录方法学 → 文末表数值。

## 3. 数字双来源核对（本例两处，都要读）

**A. 文末 Supplementary Table 1（CellBench，3 次运行均值 ± SD）**

| 模型 | Micro-Avg | Macro-Avg |
|------|-----------|-----------|
| GPT-4o 基线 | 49.89 (2.73) | 49.41 (2.40) |
| o3-mini 基线 | 55.25 (0.80) | 55.46 (0.58) |
| **CellVoyager (GPT-4o)** | **65.89 (1.81)** | **68.74 (1.52)** |
| CellVoyager (o3-mini) | 64.90 (1.30) | 67.90 (1.47) |

**B. 正文叙述**：相对最好基线 +16% micro (p<0.01)、+19.33% macro (p<0.001)；摘要口径 "up to 20%"。

**C. 其他逐字引用项**：CellBench = 50 篇论文 / 483 条分析；LLM judge 与两名 PhD 一致率 89% / 85%（n=47）；子宫内膜 73,180 细胞 / 29 名供卵者；COVID n=7 重症 + 6 健康对照；每篇论文跑 8 条轨迹、取前 5 条评分（共 15 条）；案例创造力 2.8（COVID）/ 3.4（Endometrium）/ 2.4（Aging），均值 2.8/4；12/15 = **80%** 假设被认为值得深入；CD8+ T 焦亡 **p = 0.001**；脑 SVZ 转录噪声 **r = 0.047, p = 0.0135**，寡树突/小胶质/mural **p < 0.001**。

## 4. 参数在附录 Extended Methods（正文不写）

- 反思轮数 **1 轮**（更多轮无显著收益，为省时间砍掉）
- 代码修错上限 **3 次**；修不好就记一笔「失败、换思路」并重规划
- 每条分析最多 **8 步**，封装独立 notebook（通常 5–8 步）
- 每条分析约 **30 min**；**顺序执行**，未并行
- 环境白名单：Python 3.9.22 + scanpy 1.10.3 / scvi-tools 1.1.6 / celltypist 1.6.3 / anndata 0.10.8 / matplotlib 3.9.4 / numpy 1.26.4 / seaborn 0.13.2 / pandas 2.2.3 / scipy 1.13.1
- 算法主循环原文给了 **Algorithm 1**，Mermaid 节点名照抄它：`PLAN → REFLECT → CODE → EXECUTE（报错→FIXCODE ≤F）→ VLM 解读 → REPLAN → REPORT`
- 评分 rubric 每级定义也在附录（Creativity 1–4 / Biological Relevance Y-N / Soundness Y-Mostly-N / Further Exploration Y-N）

## 5. 该论文可直接复用的分析模板（对做 agent 类系统的借鉴）

1. **Blueprint 显式化**：先产出「假设 + 分步计划」，自批评一轮后再执行 —— 把「想法质量」与「代码质量」分开治理。
2. **视觉闭环**：代码的文字 + 图像输出交给 VLM 解读，解读结果驱动下一步重规划（agent 能"看懂"自己画的图）。
3. **条件化于既往工作**：把 `past_analyses` 作为输入条件，避免重复、实现补位而非另起炉灶。
4. **以执行成功率筛轨迹**：按「代码单元成功执行比例」取前 5 条送人工评分 —— 可用于任何 agent 产出筛选。
5. **通用 agent 的对照价值**：同数据喂 Google Colab Data Science Agent → 失败（分析肤浅、用不好领域包、陷重复报错循环），说明领域专用 agent 的存在必要性。

## 6. 输出骨架（用户点名四块时直接照此答）

1. 一句话结论（是什么 + 最硬的数字，可含出处/DOI）
2. **背景**：痛点逐条（数据丰富度 vs 分析覆盖率、现有 agent 只执行用户命令、不考虑既往分析）
3. **思路**：设计支点表 + ```mermaid flowchart TD（算法主循环，节点内嵌参数）→ 每个支点解决什么问题
4. **实验内容**：分实验列出「步骤表 → 结果表（含 p 值）」；案例研究用「案例 × 指标」表；新发现分条写清步骤链
5. **结论**：量化结论 + 作者自陈局限（照录不美化）+ 更大的意义
6. 产出清单（交付 md 路径 + 原始提取物路径）+ 可选的下一步（如 Tier 2 HTML / 多篇横向对比表）

## 7. 交付目录分工

- 交付物（精读 md）：`results/<sid>/results/<论文>_精读总结.md`
- 原始提取物（fulltext.txt / metadata.json / figures/）：`results/<sid>/data/<paper>/`
- 回复里两条路径都如实列出；对话正文必须自成一体的完整解读，不能只给路径。