# 复现对账：逐基因 diff 定位根因（2026-09-11 M2-M7 复现实测）

场景：把跨物种衰老可替代性专利的 M2→M7 流水线（tile 级 age-DA → 基因锚定 → Stouffer Z → S 评分四分类 → 置换检验 → promoter CRE → 外推基线）从正本改写成纯 numpy 复现版，跑完后对账数字对不上。

## 症状

| 指标 | 专利正本 v5 | 首次复现 |
|------|------------|---------|
| ortholog 对 | 16031 | 16010 |
| A 保守可替代 | 1904 | 2335 |
| B 反向 | 3487 | **7091（翻倍）** |
| C 单侧 | 7562 | **3656（近减半）** |
| D 无 | 3078 | 2928 |
| perm_mean_A | 2012.71 | 2615.76 |
| perm_p | 0.0008 | 0.0 |

B+C 总量几乎不变（11049 vs 10747）= 典型的**分类边界语义错误**（基因在 B/C 之间迁移），不是随机噪音。

## 调试路径（关键步骤）

### 1. 逐基因 diff（不许只看统计量）
读 `P3_L1_data/v5_substitutability_all.csv`（正本）vs `M2/pipeline_out/v5_substitutability_all.csv`（复现），按 symbol 对齐比较：

```
AGBL2: ref Zm=-3.3395 (n=151) vs new Zm=-1.5678 (n=151)   ← 同 tile 数，Z 不同！
ACSF2: ref Zm=-0.2284 (n=12)  vs new Zm=+0.8018 (n=12)    ← 同 tile 数，符号都反了
```

### 2. 判别哪一侧有问题
- human 侧 Zh **完全一致**（0 个不同）→ human 输入文件/坐标/bridge 全对
- monkey 侧 Zm 12395/15963 不同（同 tile 数），3568 个基因 n_tiles 也不同 → **矛盾定位到 monkey 侧输入文件**

### 3. 检查输入文件版本（不是坐标代码！）
```
M2/monkey_ageDA_all.csv         5,296,657 行（all 版，误用）
E:/专利/monkey_ageDA_continuous.csv  5,674,191 行（continuous 版——正本 v4b/v5/v6 的实际输入）
```
两文件 tile 数都不同 → 同基因锚到的 tile 集合不同 → r 值体系完全不同。文件名同族 ≠ 同一版本：`_all` vs `_continuous`、1-based vs 0-based、divideN 口径差异都会让 r 值天差地别。

### 4. 定位正本生成脚本（关键技巧）
专利自有算法的 ground-truth 脚本不在论文官网——**在历史会话的 scripts/ 目录**：
```
find E:/MemOmics-Agent/results -name "*.py"  | grep -E "v4b|v5|v6"
E:/MemOmics-Agent/results/memomics-cd677556/scripts/v4b_conservation_continuous.py
E:/MemOmics-Agent/results/memomics-cd677556/scripts/v5_substitutability_score.py
E:/MemOmics-Agent/results/memomics-cd677556/scripts/v6_promoter_cre_score.py
```
读它们：正本输入路径 `E:/专利/monkey_ageDA_continuous.csv` + `E:/专利/human_ageDA_all.csv`，分类/置换语义逐行对比即可。

## 根因 1：classify 语义偏差（B 类定义）

| 语义 | 正本 v5（对） | 首次复现（错） |
|------|--------------|---------------|
| B 反向 | `zm*zh<0 and amin>=tau`（反向**且双侧显著**） | `(not same) and (sig_m or sig_h)`（反向**且至少一侧显著**） |
| C 单侧 | `amax>=tau`（任一侧显著） | `sig_m != sig_h` |
| S | `min(|Zm|,|Zh|)×sign(Zm·Zh)`（反向为负） | 反向时 S=0.0 |
| 置换 shuffle | Zh（`permutation(Zh)`） | Zm |
| n_perm | 10000 | 2000 |
| p | `min(P(A≥obs), P(A≤obs))×2` | 离均值距离双侧 p |
| Z 精度 | 从 v4b CSV 读（已 round 4 位） | 全精度直接分类 |

分类判定顺序（正本）：A（同向且双侧显著）→ B（反向且双侧显著）→ C（任一侧显著）→ D（双侧均不显著）。

## 根因 2：M6 promoter 口径

正本 v6 是「tile 中点 ∈ [TSS−2kb, TSS+2kb]」直接锚定（猴 strand 精确 TSS：`tss = start if strand=='+' else end`；人无 strand 用 start 近似），不是「gene-body 窗口 ±2kb + promoter_only 过滤」两段式。

## 修复后对账目标

- v5: 16031 / 1904 / 3487 / 7562 / 3078 / perm_mean_A=2012.71 / perm_p=0.0008
- v6: 15178 / 402 / 222 / 5840 / 8714 / perm_mean_A=300.35 / perm_p=0.0
- v7: formula `Z_h = -0.1626 + 1.0437*Z_m`, R2_same=0.2785, LOOCV_R2=0.2781, A_class_pearson_r=0.6833

## 纯 numpy 正态函数实现坑

numpy 没有 `np.erf` / `np.erfinv`。实现：

```python
import math as _math
_erf_vec = np.frompyfunc(_math.erf, 1, 1)

def _erf(x):
    xa = np.asarray(x, dtype=np.float64)
    out = _erf_vec(np.atleast_1d(xa)).astype(np.float64)
    return out[0] if xa.ndim == 0 else out   # ← 标量解包，frompyfunc 对标量返回 Python float

def norm_cdf(x):
    return 0.5 * (1.0 + _erf(np.asarray(x, dtype=np.float64) * _HALF_SQRT2))

def _erfinv(y):  # Winitzki 初值 + 6 轮牛顿，精度 ~1e-12
    y = np.asarray(y, dtype=np.float64)
    y = np.clip(y, -1 + 1e-300, 1 - 1e-300)
    a = 0.147
    ln = np.log(1 - y * y)
    t = 2.0 / (np.pi * a) + ln / 2.0
    x = np.sign(y) * np.sqrt(np.sqrt(t * t - ln / a) - t)
    for _ in range(6):
        x = x - (_erf(x) - y) / (2.0 / np.sqrt(np.pi) * np.exp(-x * x))
    return x

def norm_ppf(p):
    return np.sqrt(2.0) * _erfinv(2.0 * np.asarray(p, dtype=np.float64) - 1.0)
```

锚点校验：erf(0)=0, erf(1)=0.8427007929497149, norm_ppf(0.975)=1.959963984540054, norm_ppf(0.5)=0。

⚠️ 崩点实录：`stouffer` 逐基因调用 `norm_ppf(1 - p/2)`（p 是标量）→ `_erf` 收到 0 维数组 → `frompyfunc` 返回 Python float → `.astype()` 报 `'float' object has no attribute 'astype'`。修复 = `np.atleast_1d` + 标量解包（见上）。

## 用户工作流要求（本会话明确）

「你在写对应脚本之前，需要一些列名，需要自己先查看一下文件列名，然后写。你修复后，确认无误，重新跑 M2-M7。」
- 写 loader 前先 `head -2 <file>` / `zcat <feature_table> | head -1 | tr '\t' '\n'` 看真实表头
- 修复后先数值验证（锚点 + 单位测试）再全量重跑
- 重跑后逐项对账正本数字，不许只改报告文字

正本文件列名实录（本会话核实）：
- `monkey_ageDA_*.csv` / `human_ageDA_all.csv`: `chr,start,end,r,p,q`（continuous 版带引号 `"chr","start",...`）
- `GCF_037993035.2_T2T-MFA8v1.1_feature_table.txt.gz` gene 行列索引：p[6]=genomic_accession(NC_088375.1), p[7]=start, p[8]=end, p[9]=strand, p[14]=symbol, p[15]=GeneID
- `human_ortholog_hg38_full.csv`: gid, chr(无 'chr' 前缀), start, end → 加载时补 `'chr'+` 前缀对齐 tile 的 chr1
- `monkey_human_orthologs_full.csv`: macaque_gene_id, human_gene_id, human_symbol