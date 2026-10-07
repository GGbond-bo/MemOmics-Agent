# 富集前的列表成分审计（gene-list composition audit）

> 来源：2026-09-25 会话（human / skeletal_muscle / aging+exercise+diabetes，pseudobulk DEG）
> 触发：用户定完富集口径后**单独**问「表里有没有 XX 开头的基因 / 这是什么基因」
> 定位：这是富集前的**列表成分审计**，属于门禁 6b；也适用于任何"某基因家族在不在我的结果里"的追问。

## 1. 为什么要做（它影响的是结论措辞）

富集口径定完后，报告里会写"某通路被逆转/被富集"。
如果那条通路的支撑基因只有 2 个、或者这 2 个基因的功能被讲错，
**整个通路级措辞就是错的**。审计这一步同时解决三件事：
① 家族在不在表里；② 基因究竟是什么（权威注释）；③ 数据方向能不能支撑叙事。

## 2. 四步配方

### 步骤 1 — 家族扫描（含 0 命中的假阴性防护）

```python
# ✅ 正确：纯大写字面前缀（HSP 天然覆盖 HSPA/HSPB/HSPD/HSPE/HSPH）
search_files(pattern="HSP", file_glob="table[34]*.csv",
             path="results/<sid>/task4/results")

# ✅ 家族扩检：大写字面量 alternation
search_files(pattern="HSPB|HSPE|DNAJ|CRYAB|BAG3|HSP90", ...)

# ❌ 错误：内联标志会被静默丢掉 → 返回 0 命中且不报错
search_files(pattern="(?i)\\bHSP|Hsp[0-9]|DNAJ|HSPB", ...)   # → total_count: 0（假阴性）
```

**0 命中必须配阳性对照**：先用一个已知必然命中的最小 pattern 在同批文件跑一次。
阳性对照也 0 → 是 glob/路径/工具问题，不是"数据里没有"。
（完整根因：`platform-execution-pitfalls` → `references/search-files-regex-quirk.md`）

⚠️ 同时确认 `file_glob` 的覆盖面。本会话用 `table[34]*.csv` 覆盖 4 张逆转向表 ——
glob 写窄会造成**静默漏检**，和正则标志是同一类风险。

### 步骤 2 — 权威功能注释

```
query_uniprot(query="<gene symbol> human", query_type="search")
```

取 `protein_name` / `function` / `keywords`。比凭记忆可靠，且满足多源验证要求。

### 步骤 3 — 方向解读（先数据，后生物学）

把每个基因的**数据事实**先摆全：各条件的 effect、显著亚群、FDR。
只有数据方向清楚后，才谈生物学含义。

### 步骤 4 — 反例必须如实列出

检索到**方向相反**的文献时，写进答复并说明为什么，⛔ 不要只挑顺手的引用。

## 3. 本次实例（可作模板）

### 扫描结果（4 张逆转向表）

| 表 | HSP 开头基因 |
|---|---|
| 逆转衰老 Aging↑→Ex↓（785） | **HSPA9、HSPD1** |
| 逆转衰老 Aging↓→Ex↑（27） | 0 |
| 逆转糖尿病（4a / 4b） | **0** |

同家族扩检（`HSPB\|HSPE\|DNAJ\|CRYAB\|BAG3\|HSP90`）= **0**
⇒ HSPA9 + HSPD1 是 4 张表里唯二的伴侣类基因。

命中位置：`table3a_reversal_aging_up_to_down.csv` 第 346 / 347 行。

### 数据事实

| 基因 | 衰老方向 | 衰老显著亚群 | Aging coef / FDR | 运动后 | 运动显著亚群 | Ex coef / FDR |
|---|---|---|---|---|---|---|
| HSPA9 | Up | 5 个（Pure I / Pure IIA / Pure IIX / Specialized MF / OTUD1+(II)） | 0.38 / 0 | Down | OTUD1+(II) | 0.29 / 2.9e-38 |
| HSPD1 | Up | 同上 5 个 | 0.32 / 0 | Down | OTUD1+(II) | 0.29 / 1.3e-18 |

（衰老侧 5 个亚群、运动侧仅 1 个亚群 —— 这个不对称本身要在措辞里体现。）

### 权威注释（UniProt）

| 基因 | accession | protein_name | 定位与功能要点 |
|---|---|---|---|
| **HSPD1** | **P10809** | 60 kDa heat shock protein, mitochondrial（Hsp60） | 线粒体基质伴侣蛋白（chaperonin）；与 Hsp10 协同折叠新导入蛋白；7 聚体双环；关键词含 Hereditary spastic paraplegia（突变）、Leukodystrophy |
| **HSPA9** | **P38646** | Stress-70 protein, mitochondrial（mortalin / mtHsp70 / GRP75） | 线粒体 Hsp70 家族；蛋白导入/折叠/质检；铁硫簇（ISC）组装；线粒体钙依赖凋亡（ITPR1–VDAC1–MCU）；参与细胞衰老调控 |

### 叙事（与数据方向对齐）

HSP = Heat Shock Protein（热休克蛋白）= 分子伴侣。
两者**都是线粒体伴侣**（一个 chaperonin 家族、一个 Hsp70 家族）。
⇒ 衰老时两个"线粒体维修工"同向上调 = 线粒体蛋白稳态压力升高；
老年运动后回落 = 应激缓解。与"运动改善线粒体质量"的文献一致。

### 文献（含反例）

| 用途 | 引用 |
|---|---|
| ISR + 线粒体 UPR 在骨骼肌稳态 | [PMID:42201142] Sanfrancesco et al. *Muscles* (2026) |
| 运动介导的线粒体质量控制重塑（衰老） | [PMID:41988385] Cai et al. *Front Cell Dev Biol* (2026) |
| 线粒体 hsp60 失衡 → 肌病/早死 | [PMID:41507123] Chen et al. *Cell Death Dis* (2026) |
| 伴侣蛋白在肌萎缩中的角色 | [PMID:39707668] Acquarone et al. *J Cachexia Sarcopenia Muscle* (2025) |
| **反例（方向相反）** | [PMID:16524679] Murlasits et al. *Exp Gerontol* (2006) —— 抗阻训练**提高**年轻/老年大鼠骨骼肌 HSP |
| mortalin 同源物过表达延长寿命 | [PMID:11959102] Yokoyama et al. *FEBS Lett* (2002) |

### 报告里必须写的两条限制

1. HSPA9/HSPD1 是**核编码**线粒体基因 → **不按 MT- 污染剔除**（与真正的 MT- 基因组基因区分）。
2. 它们贡献的 protein folding / mitochondrial protein import 类词条**只有 2 个基因顶着**
   → 标注 n，降级为描述性，⛔ 不写"显著富集"。

## 4. 交付形态

给合作方/他人看的解释 → **中文版 + English version 两段并列、可直接转发**。
用户说「不要太复杂 / 简单点」时压到 3 点核心（本例：靠什么区分 / 重叠范围多大 / 数据自证），
砍掉推导过程与备选方案列表。