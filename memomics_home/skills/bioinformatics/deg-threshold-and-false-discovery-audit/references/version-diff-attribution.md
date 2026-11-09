# 两版 DEG 脚本结果差异的归因实录（铁律 1.8 全文）

2026-11-03 · Immune snRNA-seq（19,934 细胞 / 47 样本 / 24 个体 / 17 个 L3 亚群）
输入 `/cluster/share/user/Muscle_96_38/Umap/Immune_exercise_clean_umap.rds`
集群 node1，R 4.4.1（`/cluster/share/zhangxiao6/software/miniconda3/envs/R4.41/bin/Rscript`）

## 0. 起点：用户的问题

> 「immune_RUV_MAST.R 这是 v2 代码，v2 跟 v8 有什么区别吗？我之前就按照 v2 跑了，按照 v8，结果会不会变」
> 「v2 的跑过了，你现在跑个 v8 的，看看两者区别」

诉求关键：**要实测，不要代码 diff 式的推测**。回答「会不会变」的唯一可信方式是两版都真跑再比。

## 1. 两版的实质差异（只有 3 处会影响统计量）

| 项 | v2 | v8 |
|---|---|---|
| **k（RUV W 因子数）** | `k = min(nruv, df_resid - 1)`，实测 **2–10** | `k = min(nruv, max(2, floor(df_resid/3)))`，实测 **2–5**（39/50 为 k=2） |
| **batch 协变量** | 完全不入模 | 逐比较组判定能否入模（23/50 入模） |
| **残差守卫** | 无（df 再小也硬拟合，k=1） | `df_resid <= 2` → 跳过 |
| CDR | 两者都没有 | 两者都没有 |
| 检验 | Wald z（分量 C，退化用 D） | 同 |
| 输出 | 55 表 `_sDEG.csv` | 50 表 `_v8.csv` |
| 新增列 | — | `k_actual / k_pre_v3 / batch_used / batch_reason / df_resid / med_* / batch_*`（纯标注） |

> 教训：**先分清"会改数值的"和"只是多加列/多打标记的"**。用户前面已明确否决自造质控阈值
> （见 `self-invented-guardrail-audit.md`），那段改动对统计量应为零影响——这一点在本轮由
> 「k 未变子集结果逐位相同」实测证实。

## 2. 首次运行失败：`type 映射失败：NA`（四个分片同时崩）

```
[layers] RNA: counts | data
Error: type 映射失败：NA
Execution halted
[memomics] exit=1
```

根因对比：

```r
# v2 —— dplyr::recode，未登记的值【原样保留】，随后守卫通过
md$type <- dplyr::recode(as.character(md$type),
  "Young_normal" = "Y_Pre", "Young_normal_Post" = "Y_Post", ...)

# v8 —— 命名向量查表，未登记的值【直接变 NA】，随后守卫失败
md$type <- unname(type_map[as.character(md$type)])
```

修法（等价 recode 语义 + 可诊断）：

```r
raw_type <- as.character(md$type)
cat("[map.raw] type raw values:", paste(sort(unique(raw_type)), collapse = " | "), "\n")
md$type <- ifelse(raw_type %in% names(type_map), unname(type_map[raw_type]), raw_type)
```

**为什么 v2 能跑而 v8 崩**：同一对象、同一份数据，差别只在映射函数的 fallback 语义。
`recode` 保留原值 ⇒ 若原值已是短码则静默通过；查表则一律 NA。
**结论：向量查表式映射必须配 fallback，且必须先打印 raw 唯一值。**

## 3. 运行（集群 4 分片并行）

```bash
# 每片：MEMO_SHARD=i/4  MEMO_NCORES=16  MEMO_OUT=Immune_v8
/cluster/.../envs/R4.41/bin/Rscript /home/user/memomics_jobs/scripts/immune_RUV_MAST_v8.R
```
- 4 片全部 `exit=0`，`errors.log` 为空，耗时约 20 分钟（含读 794MB rds）。
- ⚠️ `remote_cluster action='submit'` 返回 `status=error / exit=124 (timed out after 20s)`
  **但进程实际已在跑**（setsid 启动器 ssh 挂住）。**投递后必须 `ps -ef | grep <script>` 核实，再决定是否重投**，
  否则会重复启动分片。本轮 4 片首投即成功，仅返回码吓人。

## 4. 覆盖率差：v8=50 vs v2=55

`comm` 对比两版文件名集合，v8 少 5 个，**全是 `df_resid ≤ 2` 守卫跳过**（日志 `跳过：残差 df=N 不足`）：

| 亚群 | 比较组 | 残差 df |
|---|---|---|
| CD14+ Mono | O_Pre_vs_OD_Pre | 2 |
| CD14+ Mono | O_Pre_vs_O_Post | 1 |
| CD16+ Mono | O_Pre_vs_OD_Pre | 2 |
| LYVE1+ C1Q_high Mac | O_Pre_vs_O_Post | 1 |
| moDC | O_Pre_vs_OD_Pre | 2 |

**定性**：小样本组合（每组 2–3 样本）加 W 后残差自由度耗尽。v8 拒绝拟合、v2 用 k=1 硬拟合。
**是设计取舍，不是 bug**——但必须在报告里点明，否则对比基数错。

## 5. 对比指标定义

对每一对同名 `(亚群 × 比较组)`：

| 指标 | 定义 |
|---|---|
| 显著数 | `fdr < 0.05` 的基因数（各版本独立算） |
| **Jaccard** | `|S_v2 ∩ S_v8| / |S_v2 ∪ S_v8|`，S = 显著基因集 |
| **方向一致率** | 共有显著基因中 `sign(coef_v2) == sign(coef_v8)` 的比例 |
| coef Spearman | 全基因（交集）上 `coef` 的 Spearman |
| −log10(p) Spearman | 全基因排序稳定性 |

## 6. 结果

### 总体（50 对可比）

| 指标 | 值 |
|---|---|
| 显著基因合计 | v2 = 17,051；v8 = 18,387 |
| 共有 / v8 独有 / v2 独有 | 14,934 / 3,453 / 2,117 |
| Jaccard 中位（范围） | **0.4216**（0 ~ 1.0） |
| 方向一致率中位（最低） | **1.0000**（0.9817） |
| coef Spearman 中位 | 0.6402 |
| −log10(p) Spearman 中位 | 0.6683 |

### 归因（决定性）

| 分组 | n | Jaccard 中位 | coef Spearman |
|---|---|---|---|
| **k 未变** | 5 | **1.000（逐位相同）** | **1.000** |
| k 变 + batch 未入模 | 22 | 0.5168 | 0.8656 |
| k 变 + batch 入模 | 23 | 0.2357 | 0.5238 |

- **k 未变的 5 个组合结果完全一致**（且这 5 个 batch 均未入模）⇒ 证明 v8 新增的混杂标记列/元数据列
  对统计量**零影响**，差异全部来自 k。
- 压缩幅度与差异单调相关：

| v8 k / v2 k | n | Jaccard 中位 |
|---|---|---|
| ≤ 0.3 | 12 | 0.3446 |
| 0.3–0.5 | 27 | 0.4216 |
| 0.5–0.8 | 6 | 0.7368 |

### k 的实际取值（关键）

| v2 k | v8 k=2 | k=3 | k=4 | k=5 |
|---|---|---|---|---|
| 2 | 5 | | | |
| 3 | 6 | | | |
| 4 | 5 | | | |
| 5 | 6 | | | |
| 6 | 8 | | | |
| 7 | 5 | | | |
| 8 | 4 | 1 | | |
| 9 | | 2 | | |
| 10 | | 3 | 4 | 1 |

**v2 的 k=10 和 v8 的 k=2 都不是文献口径**（猴脑 `Figure7` 固定 `nruv=10` 估、`uruv=5` 入模）。

### 分比较组

| 比较组 | n | 显著 v2 | 显著 v8 | 共有 | Jaccard 中位 |
|---|---|---|---|---|---|
| Y_Pre_vs_Y_Post | 12 | 241 | 245 | 133 | 0.3095 |
| O_Pre_vs_O_Post | 9 | 2,492 | 2,373 | 2,212 | 0.7904 |
| OD_Pre_vs_OD_Post | 10 | 383 | 481 | 306 | 0.4594 |
| Y_Pre_vs_O_Pre | 11 | 8,217 | 9,544 | 7,557 | 0.5384 |
| O_Pre_vs_OD_Pre | 8 | 5,718 | 5,744 | 4,726 | 0.2631 |

组间比较（Y vs O、O vs OD）比运动前后（Pre/Post）稳定。

### 变动最大的组合（需重点复核）

| 亚群 | 比较组 | v2 | v8 | 共有 | Jaccard | k |
|---|---|---|---|---|---|---|
| NK | Y_Pre_vs_O_Pre | 690 | 1,076 | 544 | 0.445 | 10→4 |
| NKT | O_Pre_vs_OD_Pre | 147 | 317 | 109 | 0.307 | 4→2 |
| CD8+ activated T | O_Pre_vs_OD_Pre | 574 | 741 | 333 | 0.339 | 10→3 |
| Mast cell | O_Pre_vs_OD_Pre | 210 | 115 | 63 | 0.241 | 8→2 |
| LYVE1+ Mac | Y_Pre_vs_O_Pre | 4,960 | 5,334 | 4,925 | 0.917 | 10→5 |

## 7. 交付措辞

- ✅ 「**方向几乎没变（一致率中位 1.000），名单换了一半（Jaccard 0.42）**」
- ✅ 「差异几乎全部来自 W 因子个数 k 被压缩；batch 入模再放大一倍」
- ✅ 「两版都不是文献口径；以 v2 结果写的结论不能直接沿用」
- ⛔ 不说「两版基本一致」——名单换一半不能叫一致
- ⛔ 不说「v8 更严谨」——k=2 是欠校正，不是更严谨

## 8. 复核清单

- [ ] 两版输出目录与后缀不同，确认没有断点续跑读旧表
- [ ] 两版表格数量核对，差额逐个给跳过原因
- [ ] k 是否变化的组合单独分组，验证该子集是否逐位相同
- [ ] 第二个因素（batch/协变量）单独分层量化
- [ ] 报告里写明两版 k 的公式与实测范围，以及与文献口径的关系