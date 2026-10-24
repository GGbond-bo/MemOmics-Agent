# 分层亚群注释打回主对象（L2 → L1）—— 打回前核查协议

来源：2026-10-18 人示例组织 snRNA（主对象 604,244 细胞 + 6 个亚群对象），集群 node1 / R4.4.1_zb。
本地产物：`results/<sid>/task2/L2_annotation_check_report.md`、`scripts/check_annotation_levels_v2.R`。

## 场景

主对象已带 L1 大群列（如 `Celltype`，5–6 类）；按大群拆成若干亚群对象各自精注释出 L2 亚群列；
现在要把各亚群对象的 L2 标签**打回主对象**，得到一张同时带 L1 + L2 的主表。

这是"输入审计"的同一套精神用在**派生对象**上：细胞数一样、结构看着对，**不代表是同一批细胞、同一套标签**。

## ⛔ 打回前必查 4 项（缺一项就可能静默错配）

### 1. barcode 级精确比对 —— 细胞数相等 ≠ 同一批细胞

```r
ct <- "Muscle fibers"
main_bc <- colnames(main)[main$Celltype == ct]
sub_bc  <- colnames(sub)
stopifnot(length(intersect(main_bc, sub_bc)) == nrow(sub))
```

本次 6/6 对象 barcode 交集 100%、细胞数精确相等 —— 但这一步必须**实跑**，不能由"细胞数一样"推断。

### 2. 群名层级对应（L1 ↔ 亚群对象中间层）

亚群对象内部中间层 `celltype` 各类计数与主对象 `celltype` **逐一相等** → 两个文件用的是同一套中间层标签，
打回时可按中间层直接建立对应。本次全部相等 ✅：

TypeII 268,383 / TypeI 227,811 / RSS 12,467 / FAP 39,727 / MuSC 15,810 /
Myeloid 11,976 / EC 11,472 / Pericyte 8,213 / Lym 6,763 / MastCell 1,195 / Adipocyte 427

⚠️ 归属约定（中间层 → L1 大群）必须在报告里写明，否则打回后对不上：
RSS → Muscle fibers；Pericyte → Vascular cells；Myeloid + Lym + MastCell → Immune cells。

### 3. L2 列名 —— 不同对象列名不统一，**不能统一取列**

| 亚群 | L2 实际列名 | 类数 |
|---|---|---|
| MF | `annotation_L2` | 3 |
| MuSC | `annotation_L2` | 2 |
| Immune | `annotation_L2` | 8 |
| EC | `annotation` | 5 |
| FAP | `Annotation` / `Annotation_Level2` | 6 / 4 |

**按统一列名取值 → EC / FAP 整列取空，静默变 NA，不报错**。打回脚本必须按对象逐一映射：

```r
l2_col <- list(MF="annotation_L2", MuSC="annotation_L2", EC="annotation",
               FAP="Annotation_Level2", Immune="annotation_L2")
# 赋值后 assert：sum(is.na(main$annotation_L2)) == 0
```

同一对象常并存多个层级列（`annotation` / `annotation_L2` / `annotation_L3`），粒度不同 ——
取哪一层是科学口径，不是默认值。报告里把各层类数与清单都列出给用户看
（本次 MF 有 L2 3 类 / L3 10 类，Immune 有 L2 8 类 / L3 17 类）。

### 4. 加和闭合校验

`Σ 各亚群细胞数 == 主对象总数 − 无 L2 来源的群`

本次 603,817 = 604,244 − 427（Adipocyte）✅ 闭合。不闭合 → 有对象漏算，或用了不同版本子集。

## 关键坑

1. **同一批细胞两套注释 → 必须让用户择一，禁止自己挑。**
   本次 FAP 有两个文件（user 版 6 类 / liuyuxuan3 版 4 类），细胞数完全相同（39,727）、标签不同。
   用 `ask_user(kind="intent")` 勾选弹窗定；把两套清单（各自类数 + 各类细胞数）并列摆出来再问。
   口径选择是科学决定，不是技术细节。
2. **无 L2 来源的小群**处理方式同样问用户：填自身群名（不丢细胞、不污染其他亚群 = 推荐默认）
   还是留 NA。本次 Adipocyte 427 细胞（0.07%）。
3. **核查脚本必须分步落盘**：一次读 7 个大对象的长脚本中途被打断会全丢结果
   （本次 v1 只写出部分 `meta_*.csv` 即中断）。改为**每读完一个对象立刻
   `write.csv(meta, sprintf("meta_%s.csv", nm))`**，事后从落盘 csv 汇总 —— v2 一次跑通（exit=0）。
4. **报告形态**（用户接受的版本）：核对速览表（4 项 pass/fail）→ 逐项明细（barcode 比对表、
   层级对应表、各对象 L2/L3 清单）→ ⚠️ 注意事项（列名映射表 + 待用户决策项）→ 产物路径
   （集群 + 本地 + 脚本）。

## 输出口径（本次）

主对象新增 `annotation_L2` 一列，共 22 个 L2 亚群（MF 3 / MuSC 2 / EC 5 / FAP 4 / Immune 8）+ Adipocyte；
打回脚本另出 L1×L2 对照 UMAP + L2 计数表。