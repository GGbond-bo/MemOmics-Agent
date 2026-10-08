# 事故复盘：22 个基因签名定义表的静默截断

> 2026-09，人骨骼肌项目。用户问"`pathway_score_CLEAN_v2.xlsx` 这个是不是呢？"（问它是不是我需要的那份基因集定义）。
> 结构上"是"，**内容上不是** —— 22 个签名里 10 个的基因列表被静默截断。以下是完整数字与判据。

## 1. 逐集对照（原始 → 派生）

| 签名 | 原始 | CLEAN_v2 | 缺失 |
|---|---|---|---|
| Inflammatory | 200 | 23 | **-177** |
| TNFA signaling via NFKB | 200 | 23 | **-177** |
| Insulin signaling | 137 | 23 | **-114** |
| SenMayo | 124 | 23 | **-101** |
| Stress index | 98 | 23 | -75 |
| Oxidative phosphorylation | 58 | 23 | -35 |
| Reactive Oxygen species | 49 | 23 | -26 |
| Atrophy | 44 | 23 | -21 |
| Sarcomeric | 38 | 23 | -15 |
| Denervation | 11 | 8 | -3 |
| Type I / Type II / Type IIA / Type IIX | 6 / 6 / 8 / 12 | 同 | ✅ 一致 |
| RegMyon | 15 | 15 | ✅ 一致 |
| Glycolysis | 200 | 200 | ✅ 一致 |
| Fatty acid metabolism | 158 | 158 | ✅ 一致 |
| AMPK-PGC1a | 16 | 16 | ✅ 一致 |
| Autophagy | 27 | 27 | ✅ 一致 |
| Adipogenesis | 200 | 200 | ✅ 一致 |
| mTORC1 | 200 | 200 | ✅ 一致 |
| Fibrosis | 95 | 95 | ✅ 一致 |

- 原始合计：**22 个签名 / 1902 条基因条目**
- 派生被截断：**10/22**
- 🔑 **魔法数字指纹**：10 个被截断的行里 **9 个都等于 23** —— 这种整齐是截断/上限，不是生物学子集。

## 2. 官方 cardinality 指纹表（判完整性的核心工具）

| 基因集 | 官方条目数 | 原表 |
|---|---|---|
| HALLMARK_OXIDATIVE_PHOSPHORYLATION | 200 | **58 ⚠️ 对不上** |
| HALLMARK_REACTIVE_OXYGEN_SPECIES_PATHWAY | 49 | 49 ✔ |
| HALLMARK_INFLAMMATORY_RESPONSE | 200 | 200 ✔ |
| HALLMARK_TNFA_SIGNALING_VIA_NFKB | 200 | 200 ✔ |
| HALLMARK_GLYCOLYSIS | 200 | 200 ✔ |
| HALLMARK_FATTY_ACID_METABOLISM | 158 | 158 ✔ |
| HALLMARK_ADIPOGENESIS | 200 | 200 ✔ |
| HALLMARK_MTORC1_SIGNALING | 200 | 200 ✔ |
| KEGG_INSULIN_SIGNALING_PATHWAY | 137 | 137 ✔ |
| SAUL_SEN_MAYO | 125 | 124（差 1，待核） |

**判读**：10 个里 9 个精确吻合 ⇒ **原表是官方完整下载，可信**；唯一对不上的 OxPhos（58 vs 200）
→ **如实作为开放问题交回用户**（"其余 7 个 Hallmark 基因数与官方精确吻合，只有这行对不上，建议核实"），
**不要替作者圆场说"这是精选子集"** —— 那也是猜。

## 3. 排序中途截断指纹（实测末位基因）

| 签名 | 末位基因 | 字母序覆盖 |
|---|---|---|
| Stress index | `CX3CR1` | 只到 C ⇒ 截断 |
| Oxidative phosphorylation | `LDHA` | 只到 L ⇒ 截断 |
| Reactive Oxygen species | `MBP` | 中途 ⇒ 截断 |
| SenMayo | `CD55` | 中途 ⇒ 截断 |
| Inflammatory | `CCL17` | 中途 ⇒ 截断 |
| TNFA via NFKB | `CCND1` | 中途 ⇒ 截断 |
| Glycolysis | `ZNF292` | 到 Z ⇒ 完整 |
| Fatty acid metabolism | `YWHAH` | 到 Y ⇒ 完整 |

⚠️ **反例（别误判）**：Atrophy 从 `UBB` 到 `NEDD4`（U→N）、Sarcomeric 从 `ACTA1` 到 `TNNC1` ——
这些按重要性/通路序排，**天然不像字母序**。单凭"不像字母序"判截断会冤枉完整集，
必须与"逐集计数比对 + 官方 cardinality"两条一致才能定论。

## 4. 其它顺手检查

- **列上限截断**：逐行检查最后一列是否被占用。本次 200 列的集（Glycolysis 末列 `ZNF292`、Adipogenesis `YWHAG`、mTORC1 `YKT6`）被占用但恰好 = 官方数，确认完整。⚠️ 检查 `max_column` 时要意识到：**列数上限会造成"看起来刚好装满"的假象**，要与官方数对照才能排除。
- **集内重复基因**：Atrophy 内 `FBXO30`；Fibrosis 内 `CTSB`、`COL11A2`。重复会影响 AUCell/ssGSEA 权重，报告应列出。
- **空行占位**：该 workbook `max_row=126`，但**有数据的行只有 1–24**（25–68 空、69–126 空行占位）。⇒ 判断"有没有残留数据"必须**逐个打印有数据的行号**，不能只看 `max_row`。

## 5. 分类语义：Class 列 + 两套分组

`Class` 列（Muscle / Metabolism / Diabete / Aging / Inflammation）**只在每组首行有值，其余为空，且无合并单元格**
（`ws.merged_cells.ranges` 为空 —— 若误当合并单元格读会拿不到值）。前向填充后：

| Class | n | 成员 |
|---|---|---|
| Muscle | 10 | Stress, Type I, Type II, Type IIA, Type IIX, Sarcomeric, Atrophy, RegMyon, Denervation, mTORC1 |
| Metabolism | 5 | OxPhos, Glycolysis, FattyAcid, AMPK-PGC1a, Autophagy |
| Diabete | 3 | Insulin, Adipogenesis, **ROS（前向填充产生，见下）** |
| Aging | 2 | SenMayo, Fibrosis |
| Inflammation | 2 | Inflammatory, TNFA-via-NFKB |

⚠️ **前向填充错位**：`ROS`（Hallmark 氧化应激）紧跟在 `Insulin`（Diabete）之后，被填成 `Diabete`。
从内容是代谢/应激轴 → 必须标注"按前向填充规则归 Diabete，表内未单独标注，建议确认"。

🔴 **来源分类 vs 出图脚本分组（不可混用）**：

| 签名 | 表 Class | 脚本 `PROG_GROUPS` |
|---|---|---|
| mTORC1 | Muscle | Metabolic |
| Insulin / Adipogenesis | Diabete | Metabolic |
| ROS | Diabete（前向填充） | Stress-Inflam |
| SenMayo / Fibrosis | Aging | Stress-Inflam / Atrophy-Fibrosis |

**教训**：用户先问"每个基因集的分类是什么依据"，我按**脚本分组**回答了（Metabolic 7 / Structural 1 / …），
用户随即把**原始定义表**发来纠正。⇒ 用户问"分类依据"时，指的是**定义表里的来源分类**；
脚本分组只能解释热图排版，**不能当作分类依据作答**。

## 6. 副作用边界（表述要准）

- 打分行（`*_AUC`）是在**集群上用完整基因集**算出的 ⇒ **已有打分不受派生文件影响**，CLEAN_v2 只是本地查看副本。
- 但**绝不能用派生文件重算打分或做溯源**（200→23 会让分数完全变样）。
- 正确表述：**"打分本身需确认集群用的是哪一份；派生文件不可用于重算/溯源"** ——
  不要笼统说"之前结果全错"（吓人且不实），也不要轻描淡写说"没影响"（重算/溯源就错了）。

## 7. 产出

`results/<sid>/task2/results/gene_signature_provenance.csv`（22 行，含 `n_original` / `n_clean` / `status`）
与 `gene_signature_provenance.md`（逐集溯源 + Class 汇总 + 与脚本分组差异对照表），
可直接当图注或补充材料。
