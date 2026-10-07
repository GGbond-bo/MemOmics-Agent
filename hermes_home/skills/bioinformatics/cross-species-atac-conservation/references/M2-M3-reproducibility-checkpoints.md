# M2→M3 复现检查点（用户自跑数据核对 · 2026-09-11 实锤）

> 用途：用户按旧脚本自己重跑 M2（tile 级 age-DA），要复现专利跨物种数字时，
> 必须用本检查点核对输入文件身份，否则复现结果与历史正本对不上账。

## 1. M2 输出对照（用户自跑已验证 2026-09-11）

| 检查项 | 人侧（40 例） | 猴侧（20 例） | 判定依据 |
|---|---|---|---|
| 文件名 | `human_ageDA_all.csv` | `monkey_ageDA_all.csv` | 列：chr,start,end,r,p,q（6 列） |
| 行数 | 5,555,247 | 5,296,656 | `<2*ncol` 过滤后 |
| tile 宽度 | 500bp（start 差 500，end=start+499） | 同左 | 打开 CSV 前几行看 start 间隔 |
| p<0.05 未校正 | 354,153 (6.38%) | 310,488 (5.86%) | **方向信息存在**，M3 方向门控用 p<0.05 未校正，不用 q |
| FDR q<0.1 | 50 | **0（全灭）** | 20 样本 + 全局 BH 校正 → 数学必然，**不是 bug** |
| up/down 文件 | up=22 / down=28 | **up=0 / down=0（空文件 = 正确）** | q<0.1 全灭的必然结果；猴侧 up/down 不是 M3 必需产物 |

**关键认知**：猴侧 up/down 空 ≠ 代码错。tile 级 FDR 不是本方案的主筛子——主筛子在基因级 Stouffer 之后（核心里程碑 537→336→37 全是基因级计数）。

## 2. ⚠️ 坐标网格版本漂移（复现最大坑，2026-09-11 全量验证）

专利有两份"猴子 ageDA"文件，**坐标网格相差 501bp，不是同一份数据**：

| 属性 | `E:/专利/M2/monkey_ageDA_all.csv`（用户自跑） | `E:/专利/monkey_ageDA_continuous.csv`（历史 v4b 正本输入） |
|---|---|---|
| 行数 | 5,296,656 | 5,674,191 |
| 首行坐标 | `NC_088375.1, 20001, 20500`（无引号） | `"NC_088375.1", 19500, 19999`（带引号） |
| tile 网格起点 | 20001 | 19500（差 **501bp**） |
| 格式 | 无引号 | 带引号 |

**后果（同一 Stouffer 锚定脚本，仅换猴侧输入）**：
- 加权 Spearman ρ：−0.081（continuous）→ **−0.196**（M2）
- 方向一致基因：6,662 (41.6%) → 7,431 (46.4%)
- 高置信保守基因：1,904 → **2,336**（+23%）

→ 若复现用错输入，κ/富集倍数/核心元件（336/37/12.5×）全部漂移。

**铁律**：用户说"按我的数据复现/我重跑了一遍你看看"时：
1. 先核对输入文件身份（行数 + 首行坐标 + MD5），与历史生成专利数字的正本比较；
2. 不一致 → 先查"哪份是专利正本"，把二选一摆给用户拍板，**不要自作主张选一份继续**；
3. 同名 CSV ≠ 同一份数据，版本文档（v3→v8）之外还要管**数据文件版本**。

## 3. ArchR 1.0.3 getGroupSE rowData 坐标坑（fix_ageDA_coords.R 原文）

```r
# 背景：ArchR 1.0.3 getGroupSE 的 rowData 里 start 列是 tile index（每染色体独立 1 起）
#       CSV 里 end 列 = (idx-1)*500（伪坐标）
# 修复：真实 start = (idx-1)*500+1；真实 end = idx*500；r/p/q 统计列不动
```

- **rowData 的 start 列是 tile 序号（idx），不是真实基因组坐标**——tile 级 r/p/q 计算不受影响（按行统计），但 M3 锚定基因会全错；
- 修复只动坐标列；**修复的是坐标，不是年龄类型**（用户自跑本就是连续年龄）；
- `divideN=FALSE` 是必须项：默认 divideN=TRUE 会除样本数，`rowSums>=2*ncol` 全过滤。

## 4. M3（同源锚定 + Stouffer 聚合）输入/输出清单

**输入（5 个，已确认存在）**：
1. `E:/专利/M2/human_ageDA_all.csv`（用户复现版）
2. `E:/专利/M2/monkey_ageDA_all.csv` 或 `E:/专利/monkey_ageDA_continuous.csv`（⚠️ 需拍板正本）
3. `E:/专利/P3_L1_data/monkey_human_orthologs_full.csv`（26,502 行，NCBI ortholog 桥）
4. `E:/专利/P3_L1_data/human_ortholog_hg38_full.csv`（人 hg38 坐标）
5. `E:/专利/P3_L1_data/GCF_037993035.2_T2T-MFA8v1.1_feature_table.txt.gz`（猴 T2T 特征表）

**输出**：`v4b_gene_conservation_continuous.csv`（~16,031 基因：symbol, Z_monkey, Z_human, p_monkey, p_human, n_tiles_m, n_tiles_h, same_direction）+ 统计摘要 txt。

**版本史**：旧 `m3_stepA/B/C_*.py` 用 **r_mean 算术均值**（正负抵消硬伤，导出 ρ=−0.063 假象）；正式版 `v4b_conservation_continuous.py` 用 **Stouffer Z 聚合** `Z = Σ[sign(r)·Φ⁻¹(1−p/2)]/√n`。复现必须用 v4b 版，引用专利数字时必须确认用的是 Stouffer 版结果。