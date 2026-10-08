# 分组热图的「分组依据」来源分级（交付必附依据）

> 触发：热图/矩阵图上出现**分组色条 / 类别标签 / 基因集分块 / 通路分组**时；或用户、审稿人问「**这个分类是什么依据？**」。
> 实测标本：18 个 AUCell 程序打分分成 5 组 + Identity 4（`fig_split_v10.py` / `fig_split_v10.R`），用户追问「每个基因集的分类是什么依据？」

## 1. 分组只有三种来源 —— 交付时必须写明是哪一级

| 级别 | 含义 | 依据从哪来 | 图上/图注/说明里怎么写 |
|------|------|-----------|----------------------|
| **L1 外部标准** | MSigDB Hallmark / GO / Reactome 官方集或官方层级 | 数据库官方定义 | 写集名 + 数据库 + 来源文献 |
| **L2 数据驱动** | 聚类、相关矩阵、共表达模块自动生成 | 分析产物（必须能指到脚本 + 中间文件） | 写清算法与阈值 |
| **L3 展示分组** | 作者为可读性按功能轴**人工归组** | 出图脚本里的常量（如 `PROG_GROUPS`） | **必须声明「功能性展示分组，非数据库官方分类」** |

⛔ 最常见失分点：**把 L3 当 L1 呈现**。读者看到色条会默认「这是某个数据库/算法的分类」，第一个问题就是「依据是什么」——若答案其实是「按功能轴人工归的」，要自己先说，别等被问。

## 2. 分组图的交付清单（四件，缺一不可）

1. **成员清单**：每组含哪些集/词条，逐条列名（不要只写「7 个」）。
2. **分组判据**：一句话说明按什么轴归的（能量代谢 / 结构 / 再生 / 衰老-炎症 / 终末失代偿）。
3. **每个成员的来源**：数据库 + 来源文献（PMID/DOI），或标注「自建 / 项目内定义」。
4. **来源缺失时明写**：定义文件不在本工程内 → 直接说明并给回填路径，不含糊过去。

## 3. 来源不在盘上时的诚实处理（禁止凭记忆重建）

- 打分/富集矩阵 CSV **只带 `<集名>_AUC` 这类数值列，不含基因成员**；仅凭列名**无法反推**基因列表。
- 正确动作：① 报告「未在会话产物/数据目录找到基因集定义文件」；② 给可执行回填方案（从 MSigDB / 原文重取，落盘 `gene_sets/*.gmt`，与打分列名一一对应）；③ 需要基因数这类数字时**重新从原始来源查证**（`search_papers` 取 PMID/DOI），不许用记忆补。
- ⛔ 与本项目长期要求一致：**数字必须可溯源**（禁止出现追不到输入文件的数字）。

## 4. 实例：18 程序打分 → 5 组 + Identity（可直接复用）

| 组（色条） | 成员 | 分组判据（L3） | 可锚定的 L1 来源 |
|-----------|------|--------------|----------------|
| Metabolic (7) | OxPhos, Glycolysis, FattyAcidMetabolism, AMPK_PGC1a, Adipogenesis, Insulin, mTORC1 | 能量感受 / 底物利用轴 | 其中 OxPhos、Glycolysis、FattyAcidMetabolism、Adipogenesis、mTORC1 为 **MSigDB Hallmark 官方集**（Liberzon 2015, *Cell Syst*, PMID 26771021） |
| Structural (1) | Sarcomeric | 收缩装置本身，与代谢/应激轴正交，故单独成组 | — |
| Regeneration (3) | RegMyon, Denervation, Autophagy | 神经-肌接头 / 再生-降解轴 | — |
| Stress-Inflam (5) | SenMayo, Stress, TNFA, Inflammatory, ROS | 衰老-炎症-氧化应激轴（SASP 方向） | **SenMayo** = Saul 2022 *Nat Commun*（PMID 35974106）；TNFA、Inflammatory 为 Hallmark 官方集 |
| Atrophy-Fibrosis (2) | Atrophy, Fibrosis | 终末失代偿轴（肌萎缩 + ECM 沉积） | — |
| Identity (4，另图) | scoreI / scoreII / scoreIIa / scoreIIx | 肌纤维**类型身份**（非「程序」）→ 单独出图，不与程序分块混排 | — |

**引用这张表时必须保留「判据列」的位置说明**——它是 L3，写明后才不会被误读成数据库分类。

## 5. 落到图上的具体做法

- 组色条放在**行标签外侧**，与成员列表顺序一致（同组成员必须连续成块，否则色条失去意义）。
- 图注一句话承载依据：`Groups are editorial functional axes (not database categories); set provenance in Supplementary Table X.`
- 组色用**彼此可辨的定性色板**（每组一色），与热图本身的连续发散色标（如 `RdBu_r` / `YlOrRd`）明确区分——色条是分类、色块是数值，两套色彩语言不能混。
- 交付时把「成员清单 + 判据 + 来源」写进随图说明文件（与 `QA_verification.txt` / `figures_manifest_QA.csv` 同目录），别只留在对话里。
