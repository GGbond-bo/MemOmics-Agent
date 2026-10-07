# ATAC 侧：重叠基因座的可及性统计设计

> 来源：2026-10-02 实测（MEF2C / MEF2C-AS1 案，用户转述合作方设想）。
> 配套：SKILL.md §七（摘要版）、§一（坐标几何）、§六（回信口径）。

## 一、合作方原话与裁定

> 「他的意图是想让我用 ATAC 的真实数据去查看、去统计，因为我们在锻炼之后 MEF2C-AS1 是显著上升的，
> MEF2C 几乎没有变化，所以只要在 ATAC 数据上统计到 MEF2C-AS1 和 MEF2C 的重合区域在运动前后变多变少，
> 是不是说明运动也对 MEF2C 有影响了？」

**裁定**：① 看位置/看重合/能否区分 —— 已做到 ✅（≠ 归属问题，见 §一/§四）。
② 用 ATAC 统计 —— **方向对，统计单位错**。不能回绝（可答），也不能照做（循环论证）。

## 二、TSS 窗口坐标怎么取（可直接实现）

从同一份 GTF（本例 GENCODE v32 GRCh38）取**两个基因各自的 TSS**，**不能取基因跨度中点**：

```python
# GTF 1-based inclusive；正链 TSS = start；负链 TSS = end
tss = start if strand == '+' else end
win = (tss - 2000, tss + 2000)          # ±2 kb，够容纳启动子 + 近端调控元件
```

- `MEF2C`（− 链，chr5:88,717,117–88,904,257）⇒ TSS ≈ **88,904,257** ⇒ 右界窗口
- `MEF2C-AS1`（+ 链，chr5:88,883,328–89,466,398）⇒ TSS ≈ **88,883,328** ⇒ 左界窗口
- 两窗口相距 **20.9 kb**，落在同一个 span overlap 内、但**互不重叠** ⇒ 可分别计数（这才是能拆开的前提）

⚠️ 不要用「span overlap 的中点 ± x」「整段 bin 化后取两端」等替代法 —— 中点没有生物学含义，且会把
两个启动子的信号混进同一 bin。

## 三、循环论证的完整拆解（给合作方解释时用这套话）

1. 反义 lncRNA 被转录时，**Pol II 占据该区 → 核小体被置换 → 该区可及性上升**。这是转录的**伴生现象**。
2. 所以「AS1 显著上升」与「AS1 所在段可及性升高」在数据上是**同一个事件的两种测量**，**不是两条独立证据**。
3. 整段 span overlap 平均成一个数 ⇒ 测到的主要就是 AS1 自己的活动。
4. 用它去证明「运动影响了 MEF2C」= **用 AS1 的变化证明 AS1 的变化**。
5. 破解只有一条路：**把统计单位从「基因」换成「TSS 窗口」，两侧分开算**，让二者的信号物理可分。

判别表（合作方真正想知道的）：

| ATAC 结果 | 生物学含义 | 结论能到哪句 |
|---|---|---|
| 只有 AS1 侧 TSS 变 | AS1 独立响应，宿主基因未被牵动 | 运动作用于该 lncRNA 自身调控区 |
| **两侧都变** | 共享区整体重塑 | 宿主基因启动子区被牵动 ← **支持合作方猜测的那一格** |
| AS1 侧开、宿主侧闭 | 转录干扰 / Pol II 碰撞 | 与「宿主基因表达不变」有张力，需补 nascent RNA |

## 四、结论三级措辞（写报告/回信直接照抄）

| 级 | 可写 | 需要什么证据 |
|---|---|---|
| L1 | 「运动重塑了 MEF2C 启动子区的**可及性**」 | ATAC 差异可及性即可 |
| L2 | 「运动**牵动**了 MEF2C 的调控区」 | L1 + 两侧 TSS 都有变化 |
| L3 | 「运动**影响 MEF2C 表达**」 | ⛔ ATAC 单独达不到，必须补 RNA（最佳：nascent/内含子 reads，可区分转录活性与稳态） |

⛔ 常见越界：把 L1 的证据写成 L3 的结论。开放是转录的**必要不充分**条件。

## 五、已核文献清单（2026-10-02，检索层；引用前须补摘要/全文）

| PMID | 标题（逐字） | 刊/年 | 用途 |
|---|---|---|---|
| 40623475 | Endurance training promotes chromatin closure and timely repression of the post-exercise immediate early stress response | Mol Metab 2025, DOI 10.1016/j.molmet.2025.102206 | **方向不能预设**：训练后倾向闭合 |
| 42019922 | The long non-coding RNA landscape of endurance exercise training | Mol Metab 2026, DOI 10.1016/j.molmet.2026.102358 | 运动 lncRNA 全景，方法学参考 |
| 40393809 | Integrated single-cell multiome analysis reveals muscle fiber-type gene regulatory circuitry modulated by endurance exercise | Genome Res 2025, DOI 10.1101/gr.280051.124 | RNA+ATAC **同细胞**配对范式（想同时答可及性+表达时走这条） |
| 39706290 | PRR14 mediates mechanotransduction and regulates myofiber identity via MEF2C in skeletal muscle | Metabolism 2025, DOI 10.1016/j.metabol.2024.156109 | MEF2C 与机械转导的既有联系 |

**空白检索（= 卖点）**：`query_ncbi(db='pubmed', query='MEF2C-AS1')` 命中 6 篇，全部为肿瘤 ceRNA /
5q14.3 结构重排 / 血液肿瘤，**0 篇骨骼肌或运动**。⇒「AS1 变 → MEF2C 变」**无文献支持**；
反义 lncRNA 常由自身启动子独立受调控，只能靠证据，不能靠假定。

## 六、动手前的弹窗口径（数据来源不能替用户假定）

用 `ask_user(kind="clarify", options=[...])`，四选项（本轮实际用过，用户认可）：

1. 我自己有骨骼肌 ATAC（运动前后）—— 需给 fragments / bigWig；按两个 TSS ±2 kb 做**供体配对**统计
2. 用公共数据（如人骨骼肌运动 multiome）—— 可同时看可及性与表达
3. 先不做，只想确认合作方的意图理解对不对 —— 本轮回答即结论
4. 先把「AS1 上升」这个前提验一遍 —— 先查链特异性/多重比对，再谈 ATAC

⚠️ 高代价（真跑 / 集群 / 入库 / 出报告）另需按 MemOmics 铁律 35 走意图确认表单；
本轮只是**可行性裁定 + 数据来源澄清**，用 clarify 即可，不要顺手开跑。

## 七、本轮回答结构（可复用的交付形状）

1. 一句话裁定（方向对 / 统计单位错）
2. 逐点回应用户的两条转述（① 已做到 ✅ ② 要改）
3. 两张 dsh-ui 表：**能/不能做什么** + **拆开后的三种判读**（控制在一个 fence、≤3 组件）
4. 三点边界：可及性 ≠ 表达、前提先验、文献空白
5. 参考来源（标注核实层级）+ 一个 clarify 弹窗

⚠️ 篇幅纪律：dsh-ui JSON 别堆太长（大表/长流程走独立 ```mermaid 或拆 fence），
超长会在流式生成中被截断成半截 JSON。