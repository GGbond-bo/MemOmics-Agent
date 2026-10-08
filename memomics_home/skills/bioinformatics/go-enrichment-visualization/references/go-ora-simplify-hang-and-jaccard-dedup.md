# GO ORA 全量结果卡死（simplify / GOSemSim）与 Jaccard 去冗余替代方案

会话来源：memomics-97bc1d82（人骨骼肌 MF，Y_Post vs O_Post，细胞级 Wilcoxon DEG → GO 富集）
日期：2026-09-24

## 1. 现象

`11_go_YPost_vs_OPost.R` 跑完 `enrichGO`（6 张结果表全部落盘）后进入 simplify 步骤：

```
PID 59900 | 281s 内 CPU/IO 零变化 | RSS 2335MB → 3873MB
```

进程**存活但不消耗 CPU**，仅内存缓慢上涨 → 判假死（不是 OOM、不是死锁在 I/O）。
杀进程后产出状态：

| 已落盘 | 缺失 |
|---|---|
| `results/go_BP_up.csv` (3584 行) / `go_BP_down.csv` (3165) | `go_BP_simplified_*.csv` |
| `go_CC_up.csv` (442) / `go_CC_down.csv` (364) | `go_BP_all_updown.csv` |
| `go_MF_up.csv` (642) / `go_MF_down.csv` (502) | `go_BP_top10_jaccard_up.csv` |
| `go_summary_counts.csv` | `figures/`（空） |

**教训**：ORA 表已经全部拿到，只有 downstream 的 simplify / 出图丢了 —— 但因为是单脚本，整个脚本得重跑。**必须拆脚本。**

规模参考（该数据 + 检出基因 universe 口径的实测产出）：

| Ontology | Direction | 名义 p<0.05 | FDR<0.05 |
|---|---|---|---|
| BP | Up | 489 | 182 |
| BP | Down | 625 | 178 |
| CC | Up | 43 | 21 |
| CC | Down | 100 | 70 |
| MF | Up | 105 | 26 |
| MF | Down | 80 | 21 |

## 2. 根因

`simplify()` 默认 `measure = "Wang"`，走 GOSemSim 计算词条两两的 GO 图语义相似度：
- 复杂度 O(n²) 次 GO 图遍历；
- n = 3584 / 3165（BP 全量词条数）时是千万级词条对；
- 结果：秒级操作变成几十分钟的"看似卡死"。

注意 `enrichGO(pvalueCutoff = 1, qvalueCutoff = 1)` **不是**卡死原因 —— 这是推荐做法（全量落盘、本地再过滤，便于同时出 raw P 版与 FDR 版）。卡死在 `simplify()`。

## 3. 分级方案（按代价从低到高）

| 方案 | 依赖 | 耗时 | 何时用 |
|---|---|---|---|
| **Jaccard 去冗余**（推荐默认） | 无（base R 集合运算） | 秒级 | 任何规模；只需"找出冗余簇、每簇留代表词条" |
| `simplify()` on 显著子集 | GOSemSim / org.Hs.eg.db | n≤200 时约 1–3 min | 想要 GO 层级语义合并（而非基因集重叠）时 |
| GSEA（fgsea + msigdbr） | fgsea / msigdbr | 秒级 | 想要排序信息、且可绕开 clusterProfiler 全家桶时 |

**硬阈值**：`simplify()` 只在 `nrow(sig) <= 200` 且已按 `p.adjust < 0.05` 过滤后调用；>200 直接跳过改用 Jaccard。写成守卫，不要靠人记。

## 4. Jaccard 去冗余算法（本会话已验证）

输入：显著子集的 `as.data.frame(enrichResult)`，含 `Description` / `geneID`（`/` 分隔）/ `Count` / `pvalue` / `p.adjust`。

1. `gl <- strsplit(top$geneID, "/")`，`names(gl) <- top$Description`；
2. 建 n×n 相似度矩阵 `m[i,j] = |A∩B| / |A∪B|`，`diag(m) <- 1`；
3. 按 `p.adjust` 升序遍历，未被归簇者列为**簇代表**，把 `m[i, ] > 0.7` 的全部标记为已归簇（贪心，一趟）；
4. 输出代表词条表（含 `Members` 列列出被合并词条，便于人工核对是否语义同类）+ 相似度矩阵 CSV。

阈值经验：Jaccard > 0.7 = 高度冗余（与 KEGG 会话里 Prion / Parkinson / Alzheimer 被重复注释、Jaccard 0.7–0.9 的观察一致）。`median(off-diagonal)` 可作整体冗余度指标，报告里值得写一句。

实现：`scripts/jaccard_term_dedup.R`（含 `safe_simplify()` 守门函数）。

## 5. 假死进程的处理规程

1. 读任务日志尾部 → 确认停在哪一步（本例：simplify）
2. `tasklist //FI "PID eq <pid>"`（Windows/MSYS 用双斜杠）→ 看进程是否存活
3. **判据**：存活 + 280s 零 CPU/IO 变化 = 假死 → 强杀
4. **不要原样重试**：改结构（拆脚本 / 换 Jaccard / 加 n≤200 守门）再跑
5. 产出清单先核对：**已落盘的表不要重算**，只补缺的那部分
6. ⚠️ 动手前查 CommandLine：`_kernel_worker.py` / `_kernel_worker.R` / `webui/server.py` = 平台基础设施，绝不杀

## 6. 环境要点

clusterProfiler / org.Hs.eg.db / enrichplot / DOSE 在用户库 `C:/Users/23136/R/R-4.5.3-library`，持久内核默认 `.libPaths()` 不含：

```r
.libPaths(c("E:/R-libs/R-4.5.3", "C:/Users/23136/R/R-4.5.3-library", .libPaths()))
```

不追加则 `library(clusterProfiler)` 报 "there is no package called 'clusterProfiler'"。

## 7. 出图口径

raw P 版（探索，保留边缘显著如 p=0.047）+ FDR 版（定稿）**两版都留**；dotplot（GeneRatio × 词条，size = Count，color = -log10 校正值）+ barplot（共同 FDR 轴便于两侧比较）+ ontology 产出计数图。R 的 `png()`/`pdf()` 出不了中文标签，中文图注走 matplotlib。