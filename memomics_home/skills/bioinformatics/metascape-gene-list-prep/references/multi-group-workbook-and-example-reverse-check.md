# 多比较组工作簿 → Metascape 表 + 「用户样板反查」实战（2026-09-30）

## 任务

用户：把 `DEG_fdr05_coef025_5contrasts_formatted.xlsx`（5 个 sheet：`Aging / DM / Y_EX / O_EX / DM_EX`，
25,696 行 × 16 列）拆成 **5 个比较组**的 Metascape 输入表，放到 `D:/肌肉锻炼/DEG_metascape/`。

用户原话规则："各亚群上调和下调各自100个基因，按照|coef|最高往下排，选变化最大的100个基因，不足就全取出来"。

数据前提（先查清再动手，不要重算统计量）：
- 该表上游已按 `FDR<0.05 且 |coef|≥0.25` 过滤
- `method` 列全为 `bayesglm`（细胞级 glmer + RUV 的"新方法"）
- `comparison` 列给出每组对应关系：Aging=Y_Pre_vs_O_Pre、O_EX=O_Pre_vs_O_Post、DM=O_Pre_vs_OD_Pre、
  DM_EX=OD_Pre_vs_OD_Post、Y_EX=Y_Pre_vs_Y_Post

## 结果（可用于对照）

| 组 | comparison | 列数 | 每列基因数范围 | 取满 100 的列 |
|---|---|---|---|---|
| Aging | Y_Pre_vs_O_Pre | 20 | 30–100 | 9 |
| O_EX | O_Pre_vs_O_Post | 20 | 14–100 | 4 |
| DM | O_Pre_vs_OD_Pre | 20 | 5–39 | 0 |
| DM_EX | OD_Pre_vs_OD_Post | **19** | 2–42 | 0 |
| Y_EX | Y_Pre_vs_Y_Post | 20 | 1–15 | 0 |

合计 **99 列**（DM_EX 的 `up_RSS` 在该对比无显著基因 → 空列，已跳过）。
亚群 10 个，字母序：`LRP1B+(I) / OTUD1+(I) / OTUD1+(II) / Pure Type I / Pure Type IIA / Pure Type IIX / RP_high(I) / RP_high(II) / RSS / Specialized MF`
（注意 sheet 内文件顺序 ≠ 字母序，DM/Y_EX/O_EX/DM_EX 的 celltype 出现顺序都不一样 → 必须自己 `sorted()`）。

## 用户样板反查（三步法，全程用真实文件跑）

用户贴了 7 列样板：`up/down_LRP1B+(I)`、`up/down_OTUD1+(I)`、`up/down_OTUD1+(II)`、`up_Pure Type I`。

**第 1 步 — 列位置对齐**：样板某列第 2 行是单字符 `c` → 提示这是手工拼接的样板（不阻塞，但提高警惕）。

**第 2 步 — 穷举候选规则，逐位比对**（每列取 13 个基因）：

| 候选规则 | 合计逐位一致 | 备注 |
|---|---:|---|
| A = `|coef|` 降序（全量行） | 36/91 | `up_LRP1B+(I)` 仅 2/13 |
| B = **文件自身行序**（= fdr 升序） | **65/91** | 其中 5 列 **13/13** 完全一致 |
| C = 仅 `fdr==0` 再 `|coef|` 排序 | 55/91 | — |

**第 3 步 — 存在性检查**：B/C 都对不上的 2 列（`up_OTUD1+(I)`、`down_OTUD1+(II)`），
其基因序列在 `5 sheet × 10 亚群 × 2 方向` 里**全部不存在** → 样板有部分是手拼的。

**A 规则的差异明细**（关键洞察）：样板"漏掉"的基因，恰是该段里**唯一 fdr 不为精确 0** 的 ——
`IL1RAPL1`(fdr 2.6e-191)、`LRP1B`(1.7e-235)、`MYL1`(3.1e-156)、`ABLIM1`(1.3e-169)；
而所有 `fdr == 0` 的基因一个不差。即样板的排序是 **fdr 优先**，不是效应量优先。

**判定**：样板 = **格式示意（版式可信、内容不可信）** → 按用户文字规则（A）执行，把三步证据写进回复。

## 同时否决的候选口径 C（"只留 fdr 精确为 0"）

先量化再决定要不要问用户：

| 指标 | 值 |
|---|---|
| 列数 | 99 |
| 每列 `fdr==0` 基因数：中位数 | **0** |
| 极端例：Aging `up_RSS` | 2157 个候选 / **0** 个 fdr==0 → 整列变空 |

→ 明显不可行（会掏空表格），**直接否决并说明**，不拿它去弹窗问用户。

## 假基因符号

`Aging/up_OTUD1+(I)` 第 2 名是单字符 **`c`**（全表 1 行，|coef|=0.837）→ 上游注释解析残渣，**报告用户但未擅自删**。
长度 ≤2 的符号里 `MB / CS / GK / FH / PC / AR / KY` 均为真基因，原样保留。

## 实现要点（本次踩过的）

- 列名含 `+`、空格、`(`（如 `up_LRP1B+(I)`）：`csv.writer(delimiter="\t")` 原样写出即可，Metascape 能认，**不要做 sanitize**。
- 各列长度不等（不同亚群基因数不同）→ 手工补空：
  `matrix = [[g[i] if i < len(g) else "" for _, g in cols] for i in range(nrow)]`，别指望 `pd.DataFrame(dict)` 自己对齐再写 txt。
- 写 xlsx 用 `pd.DataFrame({c: pd.Series(g) for c, g in cols})`（自动 padding）。
- 空列**先判断再 append**，并把 `note="empty_skipped"` 记进汇总表 → 事后能解释"为什么这组少一列"。
- 交付前读回 5 个 txt 做终检（空列 / 列内重复 / 表头规范 / 基因数范围），回复里给"组 × 列数 × 基因数范围"表。
- 排序并列时用 fdr 升序做次键，保证结果可复现（同 |coef| 的基因顺序不会因读表顺序漂移）。
- `rail_review(post)` 对纯表格任务会报 `passed=false("未生成任何图片")` —— 预期误判，不拦执行，如实说明即可。