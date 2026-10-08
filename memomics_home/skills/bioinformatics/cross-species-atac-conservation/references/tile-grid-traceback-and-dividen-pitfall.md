# Tile 坐标网格溯源 + divideN 口径一致性（2026-09-11 实测 · monkey/human age-DA tiles）

## 场景
对比两份"同源" pre-computed age-DA tile CSV（如 `monkey_ageDA_continuous.csv` vs `M2/monkey_ageDA_all.csv`）时，回答："是同一套 bin 只是偏移，还是两套不同 bin？"以及"专利数字到底出自哪份？"

## 溯源方法（三步，缺一不可）

1. **网格属性扫描**（流式读，不载入内存）：提取 phase(start%500)、相邻步长(start−prev_end)、每 chr 首/末 tile、tile 总数。
   - 500bp bin 网格应满足：phase ∈ {0,1}，相邻步长=1（无缝衔接），步长 >1 的全是 chr 切换 gap。
2. **对齐配对**：0-based(BED) ↔ 1-based 坐标恰好差 **+1**。用 (chr, st+1, en+1) 找配对，统计匹配率。**不要**拿两版第一行直接比坐标差（首行可能恰好隔一个 bin，制造出"501bp 偏移"的假象）。
3. **🔴 r 值一致性验证（最关键，坐标对齐≠统计一致）**：对 +1 对齐的同 bin，直接对比 r 列。判定标准：
   - r 一致率 >90%（Δr<1e-3）→ 同一计算管线，差异仅输出精度（write.csv 默认 digits=7 会砍到 6 位有效数字）
   - r 一致率低 + r 均值/|r| 体系性偏移 → **两版不是同一计算管线**，即使坐标完全对齐

## 实测结果（monkey age-DA，2026-09-11）

| 属性 | continuous 版 | M2 版 |
|---|---|---|
| 行数 | 5,674,190 | 5,293,900 |
| 坐标体系 | 0-based（BED）：start=19500,20000… 相位 0 | 1-based：start=20001,20501… 相位 1 |
| 同 bin 坐标差 | +1（同一套 500bp bin） | — |
| r 均值 | −0.0319 | +0.0281 |
| \|r\| 均值 | 0.1458 | 0.1991 |
| +1 对齐后 r 一致率(Δr<1e-3) | **0.53%** | — |
| 71% bin 上 M2 r > continuous r | 体系性偏移，非噪声 | — |

**结论**：坐标网格是同一套（0-based vs 1-based 表示差 1bp），但 r/p/q **不是同一次计算**。"501bp 网格差 = 两套不同 bin"是**误判**（两版首行隔一个 bin 的假象）。

## 根因：getGroupSE 的 divideN 参数

- 旧脚本 `l3_monkey_ageDA_fix_rowData.R`：`getGroupSE(..., scaleTo=NULL)` **未写 divideN** → 默认 divideN=TRUE（counts 除以 ncol）→ 过滤(keep=rowSums>=2*ncol)与 CPM 归一化全不同 → r 体系性漂移。
- 正确口径：`getGroupSE(proj, useMatrix="TileMatrix", groupBy=..., scaleTo=NULL, divideN=FALSE)`（原始总 counts），与 `l3_human_ageDA.R` / 用户 M2 代码一致。
- `fix_ageDA_coords.R`（坐标修复）：真实 start=(idx−1)*500+1；真实 end=idx*500；**r/p/q 统计列不动**——坐标修复不改变 r 值。

## 教训/铁律

1. **坐标对齐 ≠ 统计一致**：两版 tile 坐标完全对齐，r 值仍可完全不同（本例一致率 0.53%）。任何"用新输入复现历史结论"的任务，必须同时验证坐标网格 AND r 值一致性。
2. **别急着下"不是同一份数据"结论**：先做系统性网格溯源（第一步→第二步→第三步），再开口。第一行坐标差 501bp 不足以判断两套网格。
3. **专利数字必须锁死数据链**：跨物种 label transfer 的 ρ / 高置信基因数 / 核心元件数 / 富集倍数全部由 tile 的 r 值驱动；切换输入（continuous 链 vs M2 divideN=FALSE 链）必须整链重推 M3-M7，交底书同步改，禁止混用。