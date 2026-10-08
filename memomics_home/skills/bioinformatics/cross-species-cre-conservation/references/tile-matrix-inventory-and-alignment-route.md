# Tile 矩阵盘点与跨物种对齐路线（2026-09-15 实测，正确人侧矩阵首跑）

> 触发场景：拿到「正确的人侧 tile 矩阵」重跑跨物种衰老可及性证据链（L1 序列保守 / L2 跨物种可及性 / L3 衰老关联）；
> 或任何人猴 tile 级比较开始前需要确认**两侧网格是否同构、tile 身份从哪来、对齐走哪条路**。
> 上游交接文档：`E:/MemOmics-Agent/results/memomics-7839e23a/NEW_SESSION_HANDOFF.md`（4 Phase 一天出专利图）。
> ⚠️ 该交接文档 Phase 1 写「用 liftOver」，**与本项目实际产物不符**——见 §3。

---

## 1. 两个矩阵的事实卡（复验通过，可直接复用）

| 项 | 人侧 (hg38, GSE278576) | 猴侧 (T2T-MFA8) |
|---|---|---|
| 文件 | `E:/专利/file/human_tile_matrix_samples_x_tiles.rds` 544,744,648 B | `E:/专利/file/monkey_tile_matrix_samples_x_tiles.rds` 206,665,022 B |
| 维度 | **40 × 6,062,095** float32（已导出 npz） | **20 × 6,085,841** `dgCMatrix` |
| 值域 / 均值 | 0 – **0.77482** / 0.004416 | 0 – **0.99882** / 0.001863 |
| NaN / 稀疏 | 0 NaN，全零率 **8.35%** | nnzero 101,675,165（密度 16.5%） |
| tile 名 | `chr1:0-499` … `chrX:156040500-156040999` | `NC_088375.1:0-499` … |
| 序列数 | 23（chr1–chr22 + chrX，**无 chrY**） | 21（NC_088375.1 – NC_088395.1） |
| 逐样本非零 tile | 5,373,869 – 5,581,560（88.6–92.1%） | **3,686,698 – 5,566,123（60.6–91.5%）** |
| 样本名 | `GSM8549615_hc77` …（= human_meta_40donors.csv 的 sample 列） | `M1 M2 M3 M5 O1…Y7`（20 个，年龄表零缺失） |

**两侧都是 0-based + 500bp 定宽**（`np.diff(starts)` 在同染色体内恒 500）⇒ **网格天然同构，只差参考序列命名**（`chr*` vs `NC_*`）。
`6,085,841 − 6,062,095 = 23,746` 是**两个参考基因组的差异，不是 bug**——对齐靠映射，不靠数数。

> ⚠️ 交接文档 §3.1 写人侧是 `chr1:1-500`（1-based），**实测为 `chr1:0-499`（0-based）**。照文档硬编坐标会整体错位一个 tile。

## 2. 🔴 猴侧矩阵**列名全空** —— tile 身份只能按位置取

```r
colnames(M)   # 全是 ""（head/tail 均空串）
```

⇒ 任何用 `colnames(M)` 当 tile 名的代码**静默拿到空串**，下游 join 全 miss。
**正确取法 = 按位置**：`monkey_tile_coords.csv`（395,777,464 B，列 `tile / seqnames / start / end`）的**行 i 对应矩阵列 i**。

```r
stopifnot(nrow(co) == ncol(M))          # 6,085,841 == 6,085,841 ✓ 位置对应成立
```

只取染色体归属做分布统计时，**不要整表读 395MB**：

```r
co2 <- read.csv(p, colClasses = c("NULL", NA, "NULL", "NULL"))   # 只读 seqnames 列
```

## 3. 🔴 对齐路线：liftOver 单线不可行，锚定为主

L2 八角色辩论（2026-09-15）裁决 `need_more_info`，但**双方强共识**：

| 路线 | 可行性 | 依据 |
|---|---|---|
| B 全基因组 liftOver | ❌ **单线不可行** | 本地唯一 chain = `E:/专利/rheMac3ToHg38.over.chain.gz`（**2010 年 rheMac3 旧装配**），坐标体系与命名均与 T2T-MFA8 不兼容 → **静默产出错误映射（不报错）**；且 T2T-MFA8v1.1（2024 新组装）**无官方 →hg38 chain** |
| A 同源基因锚定 | ✅ **为主路线** | `anchor()`：`mid=(s+e)//2`，窗口 `mid±2000`，`searchsorted` 反查 + **first-overlap-wins 回溯**；零依赖 chain，与既有 16,029 基因对口径完全对齐 |

**⚠️ 标签陷阱（复踩）**：交接文档写「liftOver」，但既有产物 `E:/专利/P3_L1_data/crecs_tile_hg38_monkey_map.csv`
列名是 `tile_chr, tile_start, monkey_chr, monkey_coord, anchor_dist`——`anchor_dist` = **锚定产物**。
与既有「文件名/注释当口径用」同族：**实现路线只能靠生成脚本的输入常量 + 产物列语义确认，文档叙述不可信。**

**三项已知缺陷（辩论双方判「必须先处理」，不是可选）**——沿用主线前必须给出口径：

| 缺陷 | 实测值 | 处置判据 |
|---|---|---|
| 归属歧义 | chr1 443,121 tile 中 **1.02%** 的 ±2kb 窗口落在 ≥2 个正交基因内 | 网格打 `multi_map` 标记 + tie-break 敏感性 |
| 基因组覆盖 | Σn_tiles_h 2,432,901 / 5,555,247 = **43.8%** | 说明书写 n 必须写明分母口径；不得宣称全基因组 |
| 长度混杂 | ±2kb + Stouffer `ΣZ/√n`：强端 z **−7.55 → +5.08**（符号翻转） | 改统一网格 bin 级 + 长度中性 `z̄=Z/√n`；**符号能被混杂翻转的指标不能当主张基础** |

## 4. 读入配方（持久内核可直接跑）

**人侧**（上会话已从 RDS 导出，避免重复解析 519MB RDS）：

```python
BASE = r"E:/MemOmics-Agent/results/memomics-7839e23a/results"
M      = np.load(f"{BASE}/human_tile_mean_samples_x_tiles.npz")[key]   # 40 × 6,062,095 float32
starts = np.load(f"{BASE}/human_token_start.npy")    # int32
chrc   = np.load(f"{BASE}/human_token_chr.npy")       # uint8，⭐0-based 编码
order  = np.load(f"{BASE}/human_token_chr_order.npy", allow_pickle=True)  # ['chr1',…,'chrX']
name   = lambda i: f"{order[int(chrc[i])]}:{int(starts[i])}-{int(starts[i])+499}"
```

⚠️ **`chrc` 是 0-based 编码**（`0 → order[0] = 'chr1'`）。我第一版写成 `order[code-1] if code>=1 else 'CODE{code}'` → 首 tile 显示成 `CODE0:0-499`，看着像数据坏了，其实是自己**下标偏移一格**。

**猴侧**：`readRDS` 后全程走稀疏（`rowSums(M > 0)` / `rowMeans(M)`），**绝不转 dense**（40×6.06M dense ≈ 190GB → OOM）。

## 5. 本次产出（Phase 0 就绪门禁）

| 产物 | 内容 |
|---|---|
| `results/phase0_human_check.json` | 人侧全字段校验（维度/值域/样本名/tile 名/逐样本统计/每染色体 tile 数） |
| `results/phase0_monkey_check.json` | 猴侧同上 + `colnames_empty` / `tile_identity_source` 判定字段 |
| `figures/phase0_human_tile_qc.png` 144,132 B | 4 面板 QC：值分布(log) / 逐样本非零 tile / 逐样本平均覆盖 / 每染色体 tile 数 |
| `figures/phase0_monkey_tile_qc.png` 52,942 B | 同上（猴侧） |
| `scripts/phase0a_verify_human_matrix.py` · `scripts/phase0b_verify_monkey_matrix.R` | 可复跑；产出物由脚本直接生成 |

**为什么校验脚本也要出图**：rail_review(post) 的「每步至少 1 张图」对只读校验脚本同样生效；
而这张 QC 面板**本身就是交付内容**——逐样本非零 tile 的极差（人 3.8% vs 猴 **31%**）是后续所有跨物种比较必须先看到的深度异质性证据。

## 6. 猴侧年龄结构（解释「猴侧只出方向不出强度」）

`monkey_sample_age.csv` 20 样本，实际只有 **4 个离散簇**：Y = 5，M = 10–12，O = 22–23，V = 28–31 岁
（对照人侧 40 供体 **20–95 连续**）⇒ 年龄轴有效分辨率 ≈ 4 档，**这是猴侧方向门控不可信的物理约束，靠调参救不回来**。
