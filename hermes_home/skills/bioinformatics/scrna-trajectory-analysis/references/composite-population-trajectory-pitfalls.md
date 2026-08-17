# Composite Population Trajectory Pitfalls — 混合群体轨迹分析陷阱

> 来源：2026-07-30 骨骼肌 MF 肌纤维 10 群轨迹分析讨论

## 核心问题

当某个 cluster 是多起源混合群体时，**不能强行把它当作单一起源的轨迹终点**。Monocle3 的 `get_earliest_principal_node()` + `order_cells()` 假定一个连续渐变过程，混合群体的细胞来自不同起源，伪时间排序会在该群体处断裂或产生虚假分叉。

## 识别混合群体的信号

| 信号 | 含义 |
|------|------|
| cluster 同时高表达两种互斥的 lineage marker（如 MYH7 + MYH1） | 快慢肌混合，at least 两个子群体 |
| cluster 在不同条件下由不同子群体驱动变化（衰老→慢肌去神经成分 ↑，运动→快肌发育成分 ↑） | 不同子群体对条件响应模式相反 |
| 功能打分在 cluster 内方差很大（如再生打分和去神经打分都高但互斥） | 内部异质性远超其他 cluster |
| UMAP 上 cluster 位于两个经典群体之间的"桥"位置 | 可能是双起源汇聚点 |

## 案例：骨骼肌 Specialized MF

```
Specialized MF = 去神经慢肌浸润 (CHRNA1+MYH7+) + 正常发育快肌 (CHRNA1+MYH2+)

衰老上升的是去神经成分（慢肌基因高），运动增加的是快肌成分。
如果强行 Monocle3: Pure I → ... → Specialized MF，伪时间会把两个子群体压成一条线，
丢失了"双路线汇聚"的核心生物学发现。
```

## 错误做法 vs 正确做法

| ❌ 错误 | ✅ 替代 |
|--------|--------|
| Monocle3 `order_cells()` 全 10 群 | 只对同一起源的 4-5 个连续群做伪时间 |
| 手动指定 Pure Type I 为根节点，终点 Specialized MF | 先 sub-cluster Specialized MF 拆开，分别对两条路线做轨迹 |
| 强行解释"RSS 是从慢肌退化来的" | 读 UMAP 空间距离——RSS 靠近 Pure IIX（快肌），不是慢肌退化终点 |

## 决策树：能不能做 Monocle3 伪时间？

```
你的 cluster 是否有多起源证据？
  ├─ 否（单一发育/分化过程） → Monocle3 + 手动根节点 ✅
  └─ 是（混合群体） → 先回答：有哪些子群体？每条路线的起点和终点是什么？
      ├─ 能拆开（sub-clustering） → 对每条路线独立跑 Monocle3
      └─ 不能拆开（子群体特征模糊） → 放弃伪时间，改用以下替代：
          ├─ A. scVelo RNA velocity 矢量场（无需起点，从 splicing 推断方向）
          ├─ B. CellRank 命运概率（Waddington-OT，多起源自动处理）
          └─ C. 条件间矢量场：对每个群，Δ=(Old−Young, Old+Ex−Old)，在 PCA 上画箭头
              —— 不做"伪时间"，做"衰老矢量+运动矢量"
```

## 条件间矢量场详细做法

不做 pseudotime，而是做 **treatment effect vectors**：

```r
# 对每个 cluster，计算条件间平均表达变化
delta_aging <- avg_exp_old - avg_exp_young
delta_exercise <- avg_exp_old_ex - avg_exp_old

# PCA 降维 → 每个 cluster 一个箭头
# 箭头起点 = cluster 在 Young 的 PCA 位置
# 箭头方向 = (delta_aging_pc1, delta_aging_pc2)
# 箭头颜色 = 快肌/慢肌/特殊
```

优势：
- 不需要伪时间起点
- 直接回答"运动把哪个群推向哪个方向"
- 混合群体的两个子成分如果响应方向相反（去神经↑ vs 快肌发育↑），箭头会很短甚至无方向——这本身就是重要发现
