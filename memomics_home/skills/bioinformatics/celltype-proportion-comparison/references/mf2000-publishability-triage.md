# MF_2000.rds 发表可行性评估（publishability triage）实测记录

**数据**：`E:\release\_memtest\data\MF_2000.rds`（101.6 MB，sha256 `c0a96825…`）
**评估日期**：2026-09-24 · **会话**：memomics-44540a28
**用户原话**：「这份数据能发文章吗？帮我看看有没有什么亮点」（只给路径，无方向、无出图要求）

---

## 0. 一句话结论

**这份 2132 细胞抽样版不能单独支撑一篇文章**；但它代表的数据集有 2 个够得上发表的亮点，
需要用**全量数据 + donor 级检验 + MDE 校准**重新定稿。

---

## 1. 数据结构（一趟 `source()` 扫全）

| 项 | 值 |
|---|---|
| 类 | Seurat v5，`RNA`(counts+data) + `SCT` 双 assay，4,081 SCT features / 51,227 RNA features |
| 维度 | **51,227 genes × 2,132 cells**（`dim()` = genes × cells，汇报时勿读反） |
| 降维 | `pca` / `harmony` / `umap`（**已处理对象**） |
| 分组 | `type` 6 组：Y_Pre 450 / Y_Post 450 / O_Pre 315 / O_Post 287 / OD_Pre 315 / OD_Post 315 |
| 层级 | `celltype`(3: TypeI/TypeII/RSS) → `annotation_L2`(4) → `annotation`(5) → `annotation_L3`(**10 亚群**) |
| 打分列 | `score*_AUC` **18 个**（I/II/IIa/IIx/Sarcomeric/OxPhos/Stress/Atrophy/RegMyon/SenMayo/Inflammatory/Insulin/ROS/TNFA/…） |
| 样本 | `library` 96 个 → `samplename` **48 个**（Young_1…Young_16 / Old_1…Old_23 / Old_*C 三组各 Pre+Post） |
| ⚠️ 抽样特征 | **每样本细胞数 min 17 / q1 45 / median 45 / mean 44.4 / max 45** ⇒ 明确是「每样本取 45 细胞」的抽样版 |
| ⚠️ 性别 | **全部 Female**（sex 列单一值） |
| 年龄 | Y 18/19/21；O 61/62/66/77/83；OD 68–78 |

**QC（极干净，样本已质控过）**：

| 指标 | min | q25 | median | q75 | max |
|---|---|---|---|---|---|
| nCount_RNA | 1,001 | 2,997 | 5,297 | 7,929 | 24,313 |
| nFeature_RNA | 508 | 1,715 | 2,533 | 3,324 | 7,807 |
| percent.mt | 0.00 | 0.15 | **0.40** | 0.91 | **4.98** |
| pct_counts_ribo | 0.00 | 0.21 | 0.35 | 0.62 | 5.51 |

`percent.mt > 10` 的细胞 = **0 / 2132**。

---

## 2. 亚群比例矩阵（%，`prop.table(table(annotation_L3, type), 2)*100`）

| 亚群 | Y_Pre | Y_Post | O_Pre | O_Post | OD_Pre | OD_Post |
|---|---|---|---|---|---|---|
| RSS | **2.7** | 2.0 | **12.7** | 16.4 | 14.0 | 14.6 |
| Specialized MF | 4.2 | 3.3 | 6.0 | **12.2** | 11.1 | **17.8** |
| Pure Type IIA | 14.9 | 17.3 | 4.8 | 4.9 | 7.3 | 7.0 |
| Pure Type IIX | 9.3 | 8.4 | 13.7 | 4.2 | 18.7 | 11.4 |
| Pure Type I | 13.6 | 15.3 | 12.1 | 8.4 | 7.3 | 7.0 |
| LRP1B+(I) | 10.4 | 10.2 | 14.6 | 8.7 | 8.3 | 7.3 |
| OTUD1+(I) | 10.4 | 8.4 | 8.3 | 10.8 | 8.6 | 7.3 |
| OTUD1+(II) | 7.3 | 12.7 | 7.9 | 13.6 | 10.8 | 13.7 |
| RP_high(I) | 12.4 | 10.7 | 11.4 | 15.7 | 6.3 | 5.4 |
| RP_high(II) | 14.7 | 11.6 | 8.6 | 5.2 | 7.6 | 8.6 |

**对 MDE 的逐条判定**（阶梯 2.22pp；低丰度基线 n=10 → MDE ≈10pp，n=5 → 15pp）：

| 信号 | 观测差 | MDE | 判定 |
|---|---|---|---|
| RSS Y_Pre→O_Pre | **+10.0pp** | ~10pp | 🟡 **正好在边界**（唯一强信号） |
| RSS Y_Pre→OD_Pre | +11.3pp | ~10pp | 🟡 达边界 |
| Specialized MF Y→OD_Pre | +6.9pp | ~10pp | ⚪ 提示性 |
| Specialized MF OD 运动 | +6.7pp | ~15pp | ⚪ 提示性 |
| Pure Type IIA Y→O | −10.1pp | ~20pp（中丰度） | ⚪ 提示性 |

---

## 3. AUCell 打分 × 6 组（细胞级中位数）

| 打分 | Y_Pre | Y_Post | O_Pre | O_Post | OD_Pre | OD_Post |
|---|---|---|---|---|---|---|
| scoreI | **0.778** | 0.754 | 0.669 | 0.647 | **0.477** | 0.451 |
| scoreII | 0.742 | 0.770 | **0.512** | 0.533 | **0.726** | 0.634 |
| scoreSarcomeric | 0.503 | 0.488 | 0.418 | 0.427 | 0.415 | 0.414 |
| scoreOxPhos | 0.239 | 0.233 | 0.193 | 0.195 | 0.180 | 0.192 |
| scoreRegMyon | 0.085 | 0.083 | 0.075 | **0.109** | 0.091 | **0.095** |
| scoreAtrophy | 0.176 | 0.177 | 0.164 | 0.160 | 0.176 | 0.161 |
| scoreSenMayo | 0.033 | 0.031 | 0.028 | 0.028 | 0.032 | 0.029 |

**读法**：
- **scoreI 单调塌陷**（0.778→0.669→0.477）+ Sarcomeric/OxPhos 同向↓ = 慢肌身份程序随衰老丢失；
- **scoreII 在 OD 反弹**（O 0.512 → OD 0.726）= 糖尿病向糖酵解偏移，与 scoreI 构成镜像；
- **④ 老年专属再生响应**：RegMyon 青年运动 **无变化**（0.085→0.083），老年 0.075→**0.109**、糖尿病 0.091→**0.095**
  ⇒ 「运动只在老年激活再生程序」——设计上很漂亮、但幅度小（须过 MDE 才敢写）；
- **SenMayo 几乎零变化**（0.033→0.029）⇒ 衰老细胞标志在肌纤维里检测不到，与「衰老」主题缺正向锚点（主动披露）。

**亚群签名（行内 z 最高的打分）**：LRP1B+(I)/OTUD1+(I)/Pure Type I/RP_high(I) → **scoreI**（z 2.6–3.05）；
OTUD1+(II)/Pure Type IIA/Pure Type IIX/RP_high(II)/RSS/Specialized MF → **scoreII**（z 2.2–2.9）。
⇒ 好信号：10 亚群被两类身份打分干净二分，说明注释自洽；坏信号：**18 个程序打分在亚群间的 z 全为负**
（SenMayo/Inflammatory/ROS/TNFA/Insulin 全 −0.6~−0.9）⇒ 程序打分在本抽样里区分度弱。

---

## 4. 亚群特异 marker（`FindAllMarkers(SCT, only.pos, min.pct=0.25, logfc=0.5)`，每群 top5）

| 亚群 | markers |
|---|---|
| Pure Type IIA | DAAM2, IGFN1, GLUL, SLC16A3, NAV3 |
| OTUD1+(I) | AC099066.2, AC013652.1, MYL6B, MYH9, AC099066.1 |
| Specialized MF | **GALNTL6, ANKRD1, RUNX1**, AC068413.1, COL19A1 |
| RP_high(II) | TNNC2, RPS15, MTATP6P1, MYLPF, MT-ATP8 |
| RP_high(I) | RPL18A, MT-ND3, MT-ND2, TNNC1, MYL2 |
| Pure Type I | TECRL, **LGR5**, ATP2A2, ENPP5, AC090403.1 |
| LRP1B+(I) | **SLC16A7**, AC096589.2, B4GALNT3, LGI1, **LRP1B** |
| Pure Type IIX | **MYH1**, LINC02119, **ACTN3**, ENOX1, AC079467.1 |
| RSS | AC108067.1, **NSG2**, SLC14A2, **KCTD16**, AC044893.1 |
| OTUD1+(II) | **MYBPH**, ARID5A, **XIRP2**, TNFRSF12A, **ABRA** |

marker 数（每群 vs 其余）：OTUD1+(I) 249 / RP_high(I) 231 / RP_high(II) 224 / Pure Type IIA 151 /
Specialized MF 66 / …（SMF 最少 = 该群与其它 II 型样亚群最接近，注释独立性最弱）。

---

## 5. 可复跑脚本

`results/memomics-44540a28/scripts/MF2000_publishability_scan.R`（本 skill 的 Proven Scripts 未自动登记，
路径以会话目录为准）。跑法（**R 用 `source()`，不是 Python 的 `exec(open(...).read())`**）：

```r
source('E:/MemOmics-Agent/results/<sid>/scripts/MF2000_publishability_scan.R', encoding = 'UTF-8')
```

脚本内 `if (!exists("obj")) obj <- readRDS(...)` ⇒ 持久内核已有 `obj` 时不重复读 101 MB。
产出：`results/MF2000_subcluster_prop_by_type.csv`、`results/MF2000_AUCell_by_type.csv`、
`results/MF2000_subcluster_markers.csv`、`results/MF2000_eda_bundle.rds`。

---

## 6. 下次遇到同类请求的检查单

- [ ] 确认是**只读评估**（不给方向、不要图）⇒ 不开 task_plan、不跑 QC 管线、**不连查多轮文件**
- [ ] 一个 `source()` 的 R 脚本一次跑完 6 件事，落盘 3 CSV
- [ ] **MDE 必须写进交付**，观测差 < MDE 一律「提示性」
- [ ] 硬伤四面：每样本细胞数 / 性别单一 / 已处理对象 / 主题正向锚点
- [ ] 亮点每条带实测数字；判定「不能」时给出「在哪个数据上跑什么才能定稿」