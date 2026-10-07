# M2→M7 端到端复现流水线 · 坐标网格溯源与复现清单

> 2026-09-11 会话实测沉淀。用户按旧脚本自跑 M2 后要求"用 M2 的 monkey_ageDA_all 完成下面的分析，做成流水线"。这是把历史多版本脚本固化成单文件流水线的完整配方。

## 1. 输入文件身份核对（写进流水线的自检逻辑）

用户自跑 M2 后，磁盘上可能同时存在多个"猴子 ageDA"文件，**同名/近名 ≠ 同一份数据**：

| 属性 | `E:/专利/M2/monkey_ageDA_all.csv`（用户自跑） | `E:/专利/monkey_ageDA_continuous.csv`（历史 v4b 正本输入） |
|---|---|---|
| 行数 | 5,296,656 | 5,674,191 |
| 首行坐标 | 20001 | 19500 |
| 坐标体系 | 1-based（生物坐标，fix_ageDA_coords.R 修复产物） | 0-based（BED 风格） |
| 列 | chr,start,end,r,p,q（无引号） | 带引号 `"chr","start","end"` |
| tile 宽 | 500（end=start+500） | 500（end=start+499） |

**判定方法**：读首 2 行坐标 → 计算步长与相位（start mod 500 的值）。同一套 bin 的两种坐标表示差 +1（continuous 19500 ↔ M2 19501），不是两套 bin；若第一行恰好相差 501bp（bin 号错一位）是"第一行隔了一个 bin"的假象，不可据此断言网格不同。

## 2. 坐标网格溯源技术（0-based vs 1-based 判定）

```python
# 流式读取较优：几千 MB 的 CSV 用 pd.read_csv(usecols=['chr','start','end'], nrows=100) 抽头部即可
# 判定步骤：
# ① 步长 = start 差值（应 500）
# ② 相位 = start % 500（0-based 相位 0；1-based 相位 1）
# ③ 同 bin 关系：0-based X ↔ 1-based X+1（同一 bin 只差 +1）
# ④ r 值一致性：若同 bin r 完全相同 → 同一份数据两种坐标表示；
#    若 r 不同 → 不是同一次计算（常见原因：divideN 口径不同、过滤阈值不同、坐标修复脚本版本不同）
```

**r 值不一致不等于坐标不一致**：divideN=FALSE（原始总 counts）vs 默认 divideN=TRUE（counts 除以细胞数）会改变 CPM 计算 → r/p/q 全部不同。r 体系性差异（如 M2 版 r 均值 +0.028 vs continuous 版 −0.032）是统计口径变化，不是坐标问题。

## 3. 端到端流水线脚本骨架（repro_full_pipeline.py）

```
输入（写死已确认版本）：
  E:/专利/M2/human_ageDA_all.csv       555万行 × (chr,start,end,r,p,q)
  E:/专利/M2/monkey_ageDA_all.csv      530万行 × 同左
  E:/专利/P3_L1_data/monkey_human_orthologs_full.csv   同源桥 (macaque_gene_id, human_gene_id, human_symbol)
  E:/专利/P3_L1_data/human_ortholog_hg38_full.csv      人基因坐标（列名 human_gene_id！）
```

**列名陷阱**：基因坐标表列名是 `human_gene_id` 不是 `gene_id`——脚本里写错会 KeyError 打断整条执行。写流水线前先 `pd.read_csv(..., nrows=2).columns` 核对列名。

流程（每步带数字对账点）：
- M3 tile→基因锚定(±2kb) → Stouffer 聚合 `Z=Σ[sign(r)·Φ⁻¹(1−p/2)]/√n` → ortholog 桥接 → 基因级配对表（对账 16031 基因对）
- M4 主-参考非对称评分 S = Z_human × w(Z_monkey)（w: 同向+1/反向−1/p≥0.05→0）
- M5 置换检验（shuffle 年龄标签→空分布→τ、τ_A）
- M6 评分分级：核心元件 / 最高置信子集（对账 336 / 37）
- M7 富集验证：富集倍数 + 方向一致统计（对账 12.5× / 24.3×）

输出目录：`E:/专利/M2/pipeline_out/`（m3_gene_pairs.csv / m4_scores.csv / m5_thresholds.json / m6_classification.csv / m7_enrichment.json / REPRO_SUMMARY.md）

## 4. 交付验证

- **pipeline_out/ 空目录 ≠ 已生成**：目录存在只说明 `os.makedirs` 执行过；文件存在（且非空）才算跑通
- 进程列表为空 + pipeline_out 空 = 脚本可能启动后报错中断（查看上次 KeyError 是否修复）

## 5. 用户核心诉求（本铁律的起源）

> "你修改了脚本，为什么不能直接用脚本生成出来呢？不然人家复现，还要修正一下吗？"

→ 交付 = 一条端到端脚本 + REPRO_SUMMARY 对账报告，禁止给用户一堆要自己拼装的分散脚本。