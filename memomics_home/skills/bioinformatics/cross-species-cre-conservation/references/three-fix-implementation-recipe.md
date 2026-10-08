# 三修复实施配方（FIX_v10）：统一元件网格 / 深度校正 / 消除全局漂移

**触发**：用户读完「同向率归因诊断」的"更好的算法六条"后，直接点名要做 ①统一元件网格 ②深度校正（PACS 一类）③消除全局漂移。
来源：2026-09-12 会话（跨物种衰老可替代性专利，人海马 vs 猕猴 ATAC，20 猴样本）。
产物目录：`E:/专利/M2/FIX_v10/{01_unified_grid,02_depth_correction,03_drift_removal,04_combined,99_report}/`
脚本：`results/<sid>/scripts/fix_v10_unified_grid_and_drift.py`、`fix_v10_depth_correction.py`

---

## 第一部分 · 三个静默失败 bug（numpy/pandas 区间锚定）

**共同特征：全部只表现为"数量不对"，不抛异常。** 做 tile/peak → 基因 锚定前先对着这三条自查。
**唯一的防线 = 跑完立刻打印 `tiles anchored / genes` 并与预期量级对比**——本次三个 bug 全靠这个打印暴露。

### Bug 1 — `np.isin(x, python_set)` 恒 False（静默）

```python
keep = {'gene1', 'gene2'}          # Python set
np.isin(gg, keep)                  # → 全 False，且不报错
```

**根因**：`np.asarray(set)` 不把 set 当序列，而是当成**单个 object 标量** → 0 维 object 数组；
`np.isin` 于是逐元素做「元素 == 这个 set 对象」比较 → 全 False。

**症状**：`human tiles anchored: 0 genes: 0`

```python
keep_np = np.asarray(sorted(keep_gids), dtype=object)   # ← 必须先转 ndarray
mask = np.isin(gg, keep_np)
```

**排查手法（可复用）**：把 `keep` 过滤整段删掉跑一次。若删掉后得到正常数量（本次 chr1 单染色体内 212,312/443,121 命中），
而带 `keep` 时为 0 → 问题在 `keep` 的**类型**，不在锚定逻辑。

### Bug 2 — 并行数组"部分过滤"（IndexError 或静默错行）

```python
mid = ((start + end) // 2).astype(np.int64)
m   = mid[sel]                    # ← 派生数组
idx = np.searchsorted(gs, m + W, side='right') - 1
ok  = (idx >= 0) & (ge[np.clip(idx,0,len(ge)-1)] >= m - W)
sel, idx = sel[ok], idx[ok]       # 🔴 漏了 m，m 与 sel 长度不再一致
...
rel = (m[sel] - gs[idx]) / glen   # → IndexError: index 979923 out of bounds for axis 0 with size 259785
```

**为什么危险**：`sel` 的语义是「原始 chunk 的**行索引**」而非位置索引，长度错配时不一定立刻越界，
有机会**静默取到错误行的数据**。

**修复原则：任何一次布尔/索引过滤，必须把所有同长度派生数组一起过滤，一个不漏。**
```python
sel, idx, m = sel[ok], idx[ok], m[ok]                       # ok 掩码
sel, idx, gg, mrow = sel[km], idx[km], gg[km], m[km]        # keep 掩码
```
> 本项目**同类 bug 出现两次**（先漏 keep、再漏 ok）⇒ 过滤代码要**一次写全**，不要分两轮补。

### Bug 3 — `searchsorted` 输入未排序 → 锚定数塌 1000 倍

```python
hdf = pd.DataFrame([...])                       # 顺序 = BED 文件行序（任意）
gsub = hdf[hdf.chrom == 'chr1']                 # groupby 也保留任意序
gs = gsub['start'].values                       # 🔴 未排序
np.searchsorted(gs, mid + WINDOW, side='right') # → 结果无意义
```

**症状**：人类 5,555,247 tile 只锚定 **4,147 个 / 78 基因**（正确值 **2,439,577 / 16,104**）——**塌了约 1000 倍**。

```python
hdf = hdf.sort_values(['chrom', 'start'], kind='mergesort').reset_index(drop=True)
mdf = mdf.sort_values(['chrom', 'start'], kind='mergesort').reset_index(drop=True)
```
> `groupby('chrom')` **不保证**组内按 start 有序——排序必须显式做，不能靠数据源顺序。
> 对照：正本 `repro_m3_from_M2.py` 的 `load_gene_coords()` 里有 `chroms[c].sort(key=lambda x: x[0])` 这一行——**它就是防这个坑的**，重写实现时容易漏掉。

### 参考实现（已修三坑，可直接复用）

```python
def anchor_tiles(tiles_path, gdf, keep_gids=None, window=2000):
    """tile 中点 ±window 锚定到基因；返回 gid / rel(基因体相对位置) / z(signed Z)"""
    keep_np = np.asarray(sorted(keep_gids), dtype=object) if keep_gids is not None else None
    out = []
    for chunk in pd.read_csv(tiles_path, usecols=['chr','start','end','r','p'], chunksize=1_500_000):
        chunk['chr'] = chunk['chr'].astype(str).str.strip()
        chunk = chunk[chunk['chr'].isin(gdf['chrom'].values)]
        if chunk.empty:
            continue
        mid_all = ((chunk['start'].values + chunk['end'].values) // 2).astype(np.int64)
        chrom_all, r_all, p_all = chunk['chr'].values, chunk['r'].values, chunk['p'].values
        for chrom, gsub in gdf.groupby('chrom', sort=False):
            pos = np.nonzero(chrom_all == chrom)[0]
            if pos.size == 0:
                continue
            gs, ge, gid = gsub['start'].values, gsub['end'].values, gsub['gid'].values
            mid = mid_all[pos]
            idx = np.searchsorted(gs, mid + window, side='right') - 1
            ok = (idx >= 0) & (ge[np.clip(idx, 0, len(ge)-1)] >= mid - window)
            pos, mid, idx = pos[ok], mid[ok], idx[ok]          # ← 三个一起过滤
            if pos.size == 0:
                continue
            gg = gid[idx]
            if keep_np is not None:
                km = np.isin(gg, keep_np)
                pos, mid, idx, gg = pos[km], mid[km], idx[km], gg[km]
                if pos.size == 0:
                    continue
            glen = (ge[idx] - gs[idx]).astype(np.float64)
            glen[glen <= 0] = 1.0
            rel = np.clip((mid - gs[idx]) / glen, 0.0, 1.0)
            out.append(pd.DataFrame({'gid': gg, 'rel': rel, 'z': signed_z(r_all[pos], p_all[pos])}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=['gid','rel','z'])
```

`signed_z(r, p) = sign(r) · Φ⁻¹(1 − p/2)`（纯 numpy erf/erfinv 实现见脚本，零 scipy 依赖）。

---

## 第二部分 · 修复① 统一元件网格

**问题**：两侧 tile 各自用本物种基因注释 + liftOver 重建 ⇒ 比的是**不同物理区域**。
实测：两物种 tile 网格完全一致的基因（9.6%）同向 **50.5%**；网格重建过的（90.4%）只有 **46.0%**
（tile≥30 时 51.9% vs 45.4%，差 **+6.4pp**）⇒ 至少 5–6pp 的"不一致"来自方法缺陷。

**方案（liftOver chain 官方不存在时的通行替代）**：用**基因体相对坐标**定义同源元件——

```python
rel = (tile_mid - gene_start) / (gene_end - gene_start)   # ∈[0,1]
bin = min((rel * 20).astype(int), 19)                     # 20 个 5% 相对位置 bin
```

只保留**两侧同一 (基因对, bin) 都有 tile** 的位置 → 该 bin 即一个"同源元件"；
bin 内做 Stouffer 聚合成 bin 级 signed Z → 得到 (gene, bin) 级配对表。

**优势**：天然同一网格、同一物理语义；样本量从 1.6 万基因放大到**约 30 万 (gene,bin) 单元**。

**⚠️ 跨层比较阈值陷阱**：bin 级 Z 因 tile 数少而整体偏小，**沿用 τ_A=12 会几乎筛空** ⇒ 跨聚合层比较必须改用**分位数匹配阈值**（按 |Z_h| 的分位对齐，而不是沿用绝对值）。

---

## 第三部分 · 修复② 深度校正（PACS 一类）

**问题（C-3 实测）**：猴侧显著率随覆盖度 **33.9% → 67.1% 单调上升**，而**覆盖度最低的三个样本恰是最老的**
（V5 29y=60.6% / V6 31y=69.7% / V4 31y=70.9%）⇒ 朴素 N(0,1) 把"低深度导致的检验力/过度离散"当成信号。
方法出处：PACS, Miao et al. 2025, *Nat Commun*, **PMID 39757254**。

**实现（经验零分布校正，summary 层）**：

```python
d0 = np.median(z)                       # 全局漂移（与修复③同源）
s0 = 1.4826 * np.median(np.abs(z - d0)) # MAD → σ0；σ0 > 1 ⇒ 过度离散
z2 = (z - d0) / s0                      # 标准化后再聚合
```

**🔴 诚实边界（必须在报告里写明）**：完整 PACS 需要 **tile×sample 计数矩阵**建零膨胀模型；
若手上只有 `(chr,start,end,r,p,q)` 这类 DA 汇总表，只能在 summary 层做经验零分布校正 + 深度分层诊断，
**不是**计数层重算。要计数层版本必须从 fragments/Arrow 重新计数（另一步、耗时大）。**不得把 summary 层校正说成"用了 PACS"。**

**深度分层稳健性诊断**：按每元素 tile 数（检出广度代理）分 Q1–Q4，各层报同向率。
- 各层同向率**稳定** ⇒ 深度不是驱动因素
- **单调** ⇒ 深度混杂仍在，须回计数层

---

## 第四部分 · 修复③ 消除全局漂移

无信号的 Z 分布应以 0 为中心。人侧 tile 级 signed Z **中位 +1.06 / 均值 +1.25**（猴侧 +0.07 / +0.09）
⇒ `|Z₁|≥τ_A` 筛出的"强效应"有相当部分是被**全局漂移**推上去的，不是实体特异的衰老信号。

**修复**：聚合前对 tile 级 signed Z 做**中位数居中**（`z -= median(z)`，**按物种分别做**）。

> 修复②的 δ₀ 与修复③是同一件事的两种表述；②顺带做了 σ₀ 方差重标定。
> 判据：任一侧 `|median(Z)| > 0.3` 即为漂移信号，须先居中/分位数标准化再谈富集。

---

## 第五部分 · 同向率基准（做任何 concordance 统计前必算）

**🔴 最容易犯的解读错误**：拿观测同向率直接与 50% 比。

两侧符号本身可能偏斜 ⇒ 独立配对的期望同向率 ≠ 0.5：

```python
p_m  = (Zm > 0).mean();  p_h = (Zh > 0).mean()
base = p_m * p_h + (1 - p_m) * (1 - p_h)     # ← 真基准，必须现算
```

实测（890 个猴侧方向可信元件）：`p₊ᵐ=58.3%`、`p₊ʰ=54.2%` ⇒ **基准 = 50.7%**，观测 40.1%。
→ 正确表述是**"显著低于随机"（z=−6.44）**，不是"没超过随机"。两者结论强度完全不同。
报表里**永远同时给 obs / base / delta_pp / z 四列**，缺一不可。

---

## 第六部分 · 阈值辨析（τ 1.96 vs τ_A 12）与交付约定

| 阈值 | 出处 | 取值 | 管什么 |
|---|---|---|---|
| **τ** | 权要 6 | **1.96**（p<0.05） | 「这个元件显不显著」 |
| **τ_A** | 权要 11 | **12**（≈前 9% 分位） | 「够不够强/靠不靠前」→ 把清单从一万压到一千 |

1. `|Z|≥1.96` 在本数据里过线 **10,854/16,029 = 67.7%** —— Z 是 tile 级 Stouffer **聚合量**（中位 66 tile/基因），聚合放大检验力，p<0.05 几乎人人过关，筛不出"少数派清单"。**这就是需要 τ_A=12 的原因。**
2. **τ_A=12 不是算出来的，是挑出来的**：专利原文写"由空分布第 95 百分位**上探**、或高分位（**如**约前 10%）**动态**导出"——三个模糊词连用 ⇒ 无唯一解。取 10 → 2,070 / 取 12 → 1,409 / 取 14 → 963，核心元件数·分母·富集倍数**全部跟着动**。
3. **Z=12 的单侧 p 已数值下溢到 0**（>10⁻³³）——单个调控元件不可能有这么小的 p ⇒ 反证 Z 是聚合量；`|Z_A|≥12` 的真实含义是"该基因下有大量方向一致的 tile"，**不是**"该元件单独极显著"。
4. **阈值必须做敏感性扫描并如实报区间**（本次 τ ∈ {1.96,4,8,12,20,30}，同向率全程低于基准，仅 τ=30 的 n=47 小样本翻正）。

**交付约定（本用户明确要求）**：
- 文件必须**标记好、放进对应目录**，按**修复项/任务项**分子目录，不按时间戳：
  `01_unified_grid/` `02_depth_correction/` `03_drift_removal/` `04_combined/` `99_report/`
- 每个子目录自带 `fixN_*_stats.json`（参数 + 关键数字）⇒ **结论与数字同处一目录可定位**
- 组合结果单独放 `04_combined/`（四/五条件同向率总对照表）
- 目录根名用语义名（`FIX_v10`），不用随机 session id
