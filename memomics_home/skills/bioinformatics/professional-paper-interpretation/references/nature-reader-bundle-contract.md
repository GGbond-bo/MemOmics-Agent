# nature-reader 联用契约：交付前必过的校验与提图口径

来源：2026-10-23 CellVoyager（bioRxiv 2025.06.03.657517，31 页）单篇精读会话。
场景：用户说「解读这篇文件」→ 走 nature-reader 全文中英对照，再用本 skill 的编辑视角解读。
本文件记录 **联用时真正会卡住的地方**（校验器 schema、提图双轨、标签口径），不是 nature-reader 的复述。

---

## 1. 推荐流水线（实测跑通顺序）

```
01 抽文本      PyMuPDF get_text("text")  → data/<name>_rawtext.txt + <name>_pages.json
               （有文本层的 PDF 不要 OCR；逐页打印 chars 与首行，确认无空页）
02 提图        双轨（见 §3）→ figures/assets/ + figures/assets/manifest.json
03 写双语分片  write_file 到 paper_part1..N.md，每片主题不同
                 ⛔ 不要在分片里手写 source_map；map 从合并后的 paper.md 反推
04 合并        脚本拼接 part 文件 → paper.md，随后删除 part 文件
                 同时脚本周内**从 paper.md 正则抽取锚点**生成 source_map.json
05 校验        跑 nature-reader 官方校验器（见 §2），FAIL 必须修到 Ready: yes
06 交付        对话里给完整解读 + 交付物清单表 + 校验结果一句
```

关键顺序：**paper.md 是唯一真相源，source_map.json 由它派生**。手写 map 再对 paper.md
（本次的错误做法）必然出现 `SOURCE_MAP_ORPHAN` / `MISSING_SOURCE_MAP_ENTRY` 来回冲突。

---

## 2. 校验器 schema（本次栽在这里，务必照抄）

```bash
python "<skills>/bioinformatics/nature-reader/scripts/validate_reader_math.py" \
       paper.md --source-map source_map.json
# 期望输出：No math validation findings. Ready: yes
```

`validate_reader_math.py` 对 source_map **逐字段硬校验**，不满足一律 FAIL：

| 字段 | 硬要求 | 常见错法 |
|---|---|---|
| `equations` | **必须是 list[dict]** | 写成 `{"E001": {...}}`（dict-of-dicts）→ 直接 `MISSING_SOURCE_MAP_ENTRY` |
| `id` | 正则 `^E\d{3,}$`（≥3 位数字） | `E1` / `eq1` → `INVALID_EQUATION_ID` |
| `page` | **int 且 ≥1** | 写成字符串 `"18"` → `MISSING_PAGE` |
| `confidence` | ∈ `{high, medium, low}` | 缺字段或写 `"high-ish"` → `MISSING_CONFIDENCE` |
| `latex` 或 `image_path` | 二者至少一个有非空值 | 都缺 → `MISSING_REPRESENTATION` |
| `image_path` | 文件存在 **且** 该路径在 paper.md 里被 `![](...)` 引用 | 只存不用 → `UNUSED_EQUATION_IMAGE` |

其他规则：
- `blocks[]` 里 `type == "equation"` 的条目**也算** equation entry；用 `kind` 字段名不算（本次踩过：blocks 写 `kind` → 校验器看不到）。
- paper.md 里有 `E...` 锚点但 map 无对应条目 → `MISSING_SOURCE_MAP_ENTRY`（本次的 FAIL）。
- 反向：map 有条目而 paper.md 无锚点 → `SOURCE_MAP_ORPHAN`。
- 展示公式（`$$`）≥3 处时必须有一节 `## 公式索引` / `## Equation Index`，否则 WARN。
- 交付可复用产物时加 `--strict`。

### 标签口径（校验器只认这几个）

| 用途 | 必须写成 | 不要写 |
|---|---|---|
| 英文原文 | `**Original:**` | `**Original caption:**`（图注）／`**Source caption:**` |
| 中文译文 | `**中文:**` | — |
| 中文图注 | `**中文图注:**` | — |
| 中文表注 | `**中文图注:**` 或 `**中文说明:**` | `**中文表注:**`（**不在** `中文|中文说明|中文图注` 白名单内） |

实践：图/表 caption 块也用 `**Original:**` 承载原文图注，中文侧用 `**中文图注:**`——
这样「每个块都有 Original + 中文 对」的交付自检能一次通过。本次把 7 个 caption 块
（6 图 + 1 表）从 `**Original caption:**` 改成 `**Original:**` 后，`no-original` 由 7 → 0。

---

## 3. 提图双轨（矢量图必须走整页渲染）

```python
# 轨道 A：嵌入位图（只对真位图有效）
for idx, info in enumerate(page.get_images(full=True)):
    pix = fitz.Pixmap(doc, info[0])
    if pix.n - pix.alpha >= 4: pix = fitz.Pixmap(fitz.csRGB, pix)   # CMYK → RGB
    pix.save(...)

# 轨道 B：整页渲染（矢量图唯一可靠路径）
pix = doc[pno-1].get_pixmap(matrix=fitz.Matrix(2.0, 2.0))           # ~144 dpi
```

判据与实测（CellVoyager，31 页）：
- `get_images()` **拿不到矢量图**。本次 Figure 1（p4）3164×3402、Figure 4（p8）3754×3032 是位图，
  轨道 A 可用；而 Figure 2/3/5/6 是矢量绘制，轨道 A 只捞到图标级碎片：
  p6 两个 **160×160**（面板分隔图标）、p10 两个 **23×688 / 33×989**、p12 一个 **15×462**。
- 判据：**长边 ≥ ~1000 px 才当图用**，否则该页改走轨道 B。
- 因此对"含图页面清单"固定双出：位图（若够大）+ `pageNN_full.png` 整页渲染，并在
  `translation_notes.md` 写明"某图为矢量图，此处给出整页渲染以便核对版面"。
- 整页渲染在 paper.md 里正常 `![Figure N](assets/pageNN_full.png)` 引用即可，校验器只查引用存在性。
- 若页面 caption 在**下一页**（Nature/Cell 补充图常见），裁图请优先用本 skill 的
  `scripts/crop_figures_by_caption.py`，别手算矩形（见 SKILL.md Pitfalls）。

---

## 4. 交付自检（收尾前跑一遍）

- `paper.md` 中锚点块总数 = Open + 中文 对数；`no-original` 与 `no-translation` 应为空列表。
- paper.md 里每个 `![](assets/...)` 在 `figures/assets/` 真实存在（用正则收集引用后做差集）。
- 校验器 `Ready: yes`；FAIL 未清不得交付。
- `translation_notes.md` 必须记：抽取方式（是否 OCR）、覆盖范围（哪些附录/参考文献未逐条翻译及原因）、
  原文笔误与口径差异（本次记了 4 处：`are might be more poised` 语法笔误、`endrometrium` 拼写、
  Fig5D `PDGFBR` vs 正文 `PDGFRB` 不一致、摘要 "up to 20%" vs 表 1 实测 19.33 的约数差异）。
- ⛔ 编者自己算出来的数字（如由表 1 算出的百分点差 +16.00 / +19.33）必须在正文标注
  "由表中数值计算"，不得与原文数字混排而不加区分。

---

## 5. AI / agent 方法学论文的批判性阅读清单

本 skill 原有的批判性检查（体系/状态/物种/骨架族、直接观测 vs 间接推断、相关 vs 因果）是为
**实验/化学/生物**论文写的。AI/agent 方法论文（benchmark + 案例研究 + 人类评分）要换一套，
固定查这 9 点——本次逐条命中：

1. **真值怎么来的**：ground truth 若由 LLM 抽取（本次用 gemini-2.5-pro-preview 抽"论文做过哪些分析"），
   抽取**粒度未定义**（什么算一项"分析"？）→ 指标本身有噪声。
2. **判定器的人工校验样本量**：LLM-as-a-judge 只在多少条上校验过？（本次仅 47 条，一致率 89%/85%）
   对全量（483 项）的通胀风险有没有量化？→ 没量化就是折扣点。
3. **基线与 agent 的提示词是否同构**：本次是把 agent 的提示词专门改成"提出最可能的 held-out 分析"
   后才比的（基线用通用提示词）→ 增益里含**提示词工程**成分，读"提升 X%"必须连附录提示词一起看。
4. **案例/样本是否择优**：本次每篇 8 条轨迹按"代码单元成功执行率最高"取 5 条评估 → 系统性高估；
   被淘汰的 3 条发生了什么、有没有定量统计？
5. **评分者的盲法与一致性**：单一评分者？非盲（知道是 agent 生成的）？有没有 inter-rater 一致性？
6. **核心卖点有没有独立消融**：本次核心主张是"条件化于既往分析以防重复"，但基准输入只有背景章节，
   **没有把"既往分析清单"作为变量的控制实验** → 主张缺消融支撑，只能算定性观察。
7. **agent 自主性 vs 人机协作的归属**：最亮的结果是不是**人类提示后才产生的**？本次脑衰老的
   p<0.001 结论正是原作者要求"扩展到所有细胞类型 + 按中位数拆年轻/年老"后才出现 →
   交付时要写"人机协作的发现"，不能记作纯自主发现。
8. **统计口径是否踩伪重复**：单细胞分析里直接对**细胞**做组间检验（如 Mann–Whitney U）是典型
   pseudoreplication，须先按供体 pseudobulk。本次论文初版就踩了，是被原作者纠正后才补的 →
   这类"作者自我披露的统计缺陷"是最有价值的批判点，务必单独点出（说明 agent 的统计直觉需人类把关）。
9. **成本/失败率是否披露**：每项分析耗时（本次约 30 min）、LLM 调用与 token 消耗、失败轨迹比例。
   未披露即列为折扣点。

写法：做成 **"论文呈现 → 阅读时应注意"** 两列的证据强度审计表（表格抗截断），
比散文式吐槽可读得多；末尾给"三个案例的新发现分级"（强/中/中低 + 理由），
让用户一眼看到哪个结论能引用、哪个只能用来说明趋势。