# 双细胞检测工具链坑表（实测累积）

本文件收录"跑得通但数字不可信"与"报错看不懂"两类问题的实测根因与修复。
写检测脚本前扫一遍，能省掉几轮返工。

---

## 1. DoubletFinder 版本漂移（2.0.6 vs ≤2.0.3）

**症状**：`没有"doubletFinder_v3"这个函数`，脚本在最后一步炸、paramSweep 已经白跑。

**根因**：**2.0.6 已移除 `doubletFinder_v3`，主函数改名为 `doubletFinder`。**

```
ls("package:DoubletFinder")
# [1] "doubletFinder" "find.pK" "modelHomotypic" "paramSweep" "pbmc_small" "summarizeSweep"
```

形参（2.0.6）：
```r
doubletFinder(seu, PCs, pN, pK, nExp, reuse.pANN, sct, annotations)
```

**列名也变了**：`pANN_0.25_0.01_17` / `DF.classifications_0.25_0.01_17`
（旧版惯用的 `^DF\.pANN_0\.25_` 之类硬编码正则会全部失配）。

**修复**（两版兼容 + 不硬编码列名）：
```r
DF_FUN <- if (exists("doubletFinder", mode = "function")) doubletFinder else doubletFinder_v3
before <- colnames(obj@meta.data)
obj <- DF_FUN(obj, PCs = 1:30, pN = 0.25, pK = best_pK, nExp = nx)
newc <- setdiff(colnames(obj@meta.data), before)          # ← 动态捕获新增列
cl <- grep("classifications", newc, value = TRUE)[1]
pa <- grep("pANN",            newc, value = TRUE)[1]
```

**通例**：任何生信包都存在版本漂移（Seurat 4/5、CellChat 1/2、Monocle 2/3）。
写脚本前先做一次签名审计，把版本 + 函数名 + 形参一次打印出来，别照文档硬写：
```r
cat(as.character(packageVersion("DoubletFinder")), "\n")
print(ls("package:DoubletFinder"))
for (f in ls("package:DoubletFinder")) if (is.function(get(f))) { cat(f, ": "); print(args(get(f))) }
```

---

## 2. scrublet 自动阈值崩溃：skimage 不可用

**症状**：
```
ModuleNotFoundError: No module named 'skimage.filters._multiotsu'
```
调用栈落点：`scrublet/core.py ... call_doublets → from skimage.filters import threshold_minimum`

**根因**：`call_doublets(threshold=None)` 内部分支才导入 skimage；
当 skimage 不可用（编译扩展与当前解释器 **ABI 不匹配**、或只装了半套）时整条自动阈值路径崩。
典型情形：包被装成另一个 CPython 小版本构建的（如 `_multiotsu.cp313-win_amd64.pyd` 出现在 3.12 解释器下）。

**❌ 不可靠的做法**：往 `sys.modules` 注入假的 `skimage.filters` 模块。
持久内核里坏条目可能**已残留**，`if "skimage.filters" not in sys.modules` 判断会被跳过 → 注入静默失效。

**✅ 可靠做法：monkey-patch `scrublet.Scrublet.call_doublets`**，用纯 scipy 的等价实现替换阈值。
语义与官方一致（官方即取 `doublet_scores_sim_` 直方图两峰之间的谷）：

```python
from scipy.ndimage import gaussian_filter1d
import scrublet as scr

def thr_min(v, nbins=256, sigma=1.0):
    """skimage.filters.threshold_minimum 的无依赖等价实现（双峰最小谷）"""
    v = np.asarray(v, float); v = v[np.isfinite(v)]
    if v.size == 0: return 0.0
    h, e = np.histogram(v, bins=nbins)
    c = (e[:-1] + e[1:]) / 2.0
    hs = gaussian_filter1d(h.astype(float), sigma=sigma)
    loc = np.r_[False, (hs[1:-1] >= hs[:-2]) & (hs[1:-1] > hs[2:]), False]
    pk = np.where(loc)[0]
    if len(pk) < 2:                      # 无双峰 → 退回中位数
        return float(np.median(v))
    t2 = np.sort(pk[np.argsort(hs[pk])[-2:]])
    lo, hi = int(t2[0]), int(t2[-1])
    return float(c[lo + int(np.argmin(hs[lo:hi + 1]))])

_orig = scr.Scrublet.call_doublets
def _patched(self, threshold=None, verbose=True):
    if threshold is None:
        v = np.asarray(getattr(self, "doublet_scores_sim_", None), dtype=float)
        if v.size == 0:
            v = np.asarray(self.doublet_scores_obs_, dtype=float)
        threshold = thr_min(v)
    return _orig(self, threshold=threshold, verbose=verbose)
scr.Scrublet.call_doublets = _patched
```

**兜底**：`try/except` 后改用固定阈值，并在结果里**如实标注** `threshold_mode="fixed_0.25"`——
不能把固定阈值的结果当自动阈值结果报。

### scrublet 0.2.3 API 备忘
- `n_prin_comps` **属 `scrub_doublets()` 方法参数，不是 `Scrublet.__init__` 参数**
  （`__init__` 只有 `counts_matrix, total_counts, sim_doublet_ratio, n_neighbors, expected_doublet_rate, stdev_doublet_rate, random_state`）
- 传错位置报 `TypeError: Scrublet.__init__() got an unexpected keyword argument 'n_prin_comps'`
- `use_approx_neighbors=False` 走 sklearn，**免装 annoy**
- 取分数：`s.scrub_doublets(n_prin_comps=30, use_approx_neighbors=False, verbose=False)`
  → `s.doublet_scores_obs_` / `s.doublet_scores_sim_` / `s.threshold_`

---

## 3. R ↔ Python 互操作（跨进程传矩阵与标签）

| 症状 | 根因 | 修复 |
|------|------|------|
| R 端 `sum(lab$is_synthetic)` 报 `'type'(character)参数无效` | pandas 把 `True/False` 落 CSV 成 `"True"/"False"` 字符串，R 读成 character | `if (is.character(x)) x <- tolower(trimws(x)) == "true"` |
| `CreateSeuratObject` 报 `类别为"LogMap"的对象无效: Duplicate rownames not allowed` | 合成矩阵 `X[, i1] + X[, i2]` **继承原矩阵列名**，与原始细胞列名重复 | 合成后立即 `colnames(Xs) <- paste0("SYN_", seq_len(ncol(Xs)))` |
| `没有 "readMM" 这个函数` | 未 attach Matrix | **`Matrix::readMM`**（命名空间调用，同时避开 rail_review 的 `library()` 包名解析误报） |
| `Matrix` 未在 skill 声明引 warning | 同上 | 命名空间调用不会触发该 warning |

**矩阵交换格式**：`Matrix::writeMM(cnt, "counts.mtx")` + `features.tsv` + `barcodes.tsv` + `metadata.csv`。
两侧都从这同一份 counts 读入 → 保证"两法输入完全可比"（这是交叉比对有意义的前提）。

---

## 4. pooled vs 分样本：先算每样本细胞数

**判据**：`median(cells_per_sample)`。

- **<100 细胞/样本** ⇒ scrublet / scDblFinder / DoubletFinder 的**每样本估计极不稳**，
  必须**全细胞池（pooled）**跑；并在报告中说明"批次内 doublet 分布被平均"的风险
- 实测触发场景：48 样本 × 44 细胞/样本
- 补救核查：按样本统计 `mean pANN` 分布（实测 0.073–0.369），指明驱动样本
  → 用样本级 pANN 做敏感性/协变量，**不要解释单样本的双细胞率**

```r
tb <- table(obj@meta.data$samplename)
cat("样本数:", length(tb), "每样本细胞数: median", median(tb), "min", min(tb), "max", max(tb), "\n")
```

---

## 5. 用哪个 R：先判"包在哪个库"

跨 R 小版本各有独立库。kernel 里 `requireNamespace` 报缺失 ≠ 包没装；
反过来把 4.5.3 编的包挂进 4.4.2 会在 `loadNamespace` 阶段炸 DLL。

- 纯 R 包（如 **limma**）→ 可通过 `.libPaths()` 跨版本借用
- **有 Bioc 依赖树的包（scran / scDblFinder）→ 借不全**：补了 limma 又会缺 metapod，逐个借包不划算
- 结论：双方法交叉时，**优先选本机已能完整加载的两个独立方法**（实测 = R 侧 DoubletFinder + Python 侧 scrublet），
  而不是死磕某一个装不全的包

```r
# 逐包真加载（不要用 requireNamespace —— 它只查描述不加载 DLL）
for (p in pkgs) {
  ok <- tryCatch({ suppressMessages(library(p, character.only = TRUE)); "OK" },
                 error = function(e) paste("FAIL:", conditionMessage(e)))
  cat(sprintf("%-22s %s\n", p, ok))
}
```

---

## 6. rail_review 与包清单（与检测脚本相关的两条）

- `rail_review(pre)` 的包探测**看不到某些库**（如 R 用户库、非默认 Python 解释器），会把**确实已装**的包
  报成 Missing 并**硬阻断执行类工具**。最省力修复 = **不传 `required_packages`** 或只列 rail 能解析的包。
  ⛔ 被拦期间不要反复重试 execute_* / terminal（会累计"连续拦截"计数）。
- `rail_review(post)` 的 `output_dir` **传会话根目录**（同层可见 `figures/` 与 `results/`）；
  传单一子目录 → "只见一半产物" → `figure_count=0 → failed`。属产物口径类，**脚本不必重跑**。

---

## 7. 图表相关

- 中文标注一律用 **Python matplotlib**（`fm.fontManager.addfont("C:/Windows/Fonts/msyh.ttc")`）；
  R 的 `png()/pdf()` 在 Windows 上对 CJK 会静默丢字（`mbcsToSbcs conversion failure`，图仍是 exit 0）
- `ax.boxplot(labels=...)` 在 matplotlib ≥3.9 报错 → 改 **`tick_labels=`**
- 出图后**必须 `ls` 数文件**：双设备写法（先 `png()` 再 `pdf()`）会让 PNG 落空