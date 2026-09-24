---
name: analysis-output-validity-gates
description: 生信流程「跑完 ≠ 结果有效」的产出有效性自证门 + 失败归因（内存 vs 代码）。覆盖静默无效产出（exit 0、日志全 ✓、文件齐全但数值全是垃圾，如 AUCell 矩阵全 0、regulon 基因变单字符）与归因错层（把 dask worker OOM 当代码 bug 反复改）。触发：跑完了/为什么全是0/结果可疑/AUCell全0/产出无效/exit 0 但没结果/FutureCancelledError/MemoryError worker/静默失败/结果表全 NA。
when_to_use: "[analysis-output-validity-gates] 分析脚本跑完、退出码 0、产出文件齐全，但结果可疑（全 0 / 全 NA / 形状对不上 / 命中率低）时；或分布式任务崩了要判断是内存问题还是代码问题时"
display-name: "Analysis Output Validity Gates (静默无效产出自证)"
category: bioinformatics
short-description: "生信流程「跑完 ≠ 结果有效」的产出有效性自证门 + 失败归因（内存 vs 代码）"
starting-prompt: "我的分析跑完了但结果看起来不对（全 0 / 全 NA / 形状不对），帮我先验证产出到底有效没效。"
---

# 分析产出有效性门（Analysis Output Validity Gates）

## 核心原则

> **退出码 0 ≠ 结果有效；文件非空 ≠ 内容有意义；日志有 ✓ ≠ 分析成立。**

生信工具（尤其 pySCENIC / 分布式 / 多步骤管线）会在**参数或数据口径错位**时**静默降级**：
照样打印 `✓ completed`、照样写盘、行数形状都正常，但数值已经是垃圾。
**唯一可靠的防线是「可量化的不变量断言」**——每条断言都必须能自己算出一个数字（命中率、非零占比、
交集数、维度匹配），断言失败就报错、拒绝产出、拒绝汇报"分析完成"。

**禁止**：产出异常时先说"分析完成"，等用户质疑才发现无效。
**必须**：先自证（算出数字）→ 通过才汇报。

## 一、产出有效性硬校验清单（通用四问）

对**任何**交给下游/写进结论的结果表，依次回答：

| # | 问题 | 怎么答（要算出数字，不是眼看） | 不合格的信号 |
|---|------|------------------------------|-------------|
| 1 | **标识符对得上吗？** 结果 ID 命名体系和输入是同一套吗（HGNC vs ENSEMBL、带不带版本号、大小写） | `len(set(结果ID) & set(输入ID)) / len(结果ID)` | 命中率 < 0.9 → 口径错位 |
| 2 | **数值分布合理吗？** 是不是全 0 / 全 NA / 全同一个值 | `(arr > 0).mean()`、`np.nanmean`、`pd.Series.nunique()` | 非零占比 < 0.5、唯一值 = 1 |
| 3 | **形状/维度对得上吗？** 行列、ID 顺序、分组水平数 | `shape`、`index.is_unique`、`value_counts()` 与预期水平数比对 | 维度对不上、ID 重复 |
| 4 | **生物学/统计方向说得通吗？** 效应量符号、量级、组间关系 | 与知识库/文献已知方向比对；关键 marker 是否出现在该出现的位置 | 方向相反、量级离谱 |

把四问写成脚本（**每步分析都做**，不是最后统一做），断言失败直接 `raise`，不要 try/except 吞掉。

## 二、静默失败的「症状特征」速查（一眼认出）

| 症状 | 典型根因 | 深入 |
|------|---------|------|
| 结果表里出现**单字符**条目（`[`、`(`、`'`、单个字母） | 一个 str 被当成「列表/集合」逐字符迭代 | [references/prune2df-targetgenes-stringification.md](references/prune2df-targetgenes-stringification.md) |
| 整张活性/打分矩阵**全 0**，summary 也全 0（不是"算得低"） | 输入基因集与表达矩阵零交集（上游 ID/类型错位） | 同上 |
| 行数正常但**每条都是同一个值/权重 1.0** | 解析失败走了 fallback 默认值 | 同上 |
| 工具刷屏打印 `Less than N% of the genes ... are present` | **不是无害 warning**，是 ID 错位告警，命中率接近 0 | 同上 |
| 中间表列名对不上（`KeyError`），且发生在**最贵的步骤之后** | 自写代码猜了上游 DataFrame 的列结构（MultiIndex / 列名被截断） | 同上「列结构先看清再写」 |
| `MemoryError: Unable to allocate 1.93 MiB` + `FutureCancelledError: finalize-... cancelled for reason: unknown` | **不是代码 bug**：worker 被 OOM 杀掉 → scattered 数据丢失 | [references/distributed-worker-oom-vs-code-bug.md](references/distributed-worker-oom-vs-code-bug.md) |

## 三、失败归因决策树（先归因，再动手）

```
跑失败 / 产出可疑
  ├─ 进程崩了、有 traceback
  │    ├─ traceback 里有 MemoryError / ArrayMemoryError / "Unable to allocate" / worker removed
  │    │    → 归因【内存】。先量资源余量（Windows 看 commit 上限！），再定并发。禁止反复改代码重试。
  │    │    → 见 references/distributed-worker-oom-vs-code-bug.md
  │    └─ KeyError / TypeError / AttributeError 发生在"导出/汇总"步
  │         → 归因【自写代码猜了上游结构】。先 print 上游真实列/类型，再改代码。
  └─ 进程正常退出、产出可疑
       → 归因【口径/解析错位】。跑第一节四问；从最上游产出开始逐层验证（见第四节）
```

**⚠️ 铁律**：同一失败**换并发/换路径重试前**，先确认根因判对了。
本类事故的典型浪费模式是"崩了 → 直接重跑 → 又崩"，每次烧十几分钟。

## 四、最小重跑路径（别从最贵的一步重来）

1. 先列盘上已有中间产物（`adjacencies.csv` / `modules.pkl` / 导出矩阵…），**最贵的一步（GRN 推断、
   比对、训练）几乎总能复用**；
2. 只重跑被修的那一步，并**立刻把该步原始输出落盘**（`*_raw.csv`）——本类事故最亏的是
   "跑完 10 分钟才发现中间表没存，只能整步重来"；
3. 旧（无效）产出**移到 `_old_*/` 子目录留痕**，不要就地覆盖到无法追溯；
4. 重跑后用第一节四问自证，把断言输出的数字写进汇报。

## 五、与平台上其它门的关系

- `rail_review(pre/post)`：平台级质量门（图数量、文件存在性）→ 本 skill 补的是**内容有效性**（数值可信否）。
- `enrichment-conclusion-validation`：DEG→富集**结论**的定稿前验证 → 本 skill 面向**任意产出物**的中间自证。
- 汇报纪律：断言数字必须如实报（"非零占比 100%、基因命中率 0.998"），**不许**只报"分析完成"。

## 参考与脚本

- [references/prune2df-targetgenes-stringification.md](references/prune2df-targetgenes-stringification.md)
  —— 完整案例：pySCENIC `prune2df` 的 `TargetGenes` 是字符串 → ctxcore 逐字符 → 264 个 regulon 全是
  单字符 → AUCell 562,848 个值全 0；含源码级根因链、A/B 定位实验、修复代码、列结构陷阱。
- [references/distributed-worker-oom-vs-code-bug.md](references/distributed-worker-oom-vs-code-bug.md)
  —— 特征性报错、Windows commit 上限诊断命令、并发选择规则。
- [scripts/verify_output_validity.py](scripts/verify_output_validity.py)
  —— 可直接跑的四问校验器（ID 命中率 / 非零占比 / 唯一值 / 维度）。