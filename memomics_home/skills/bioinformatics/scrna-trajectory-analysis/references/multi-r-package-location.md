# 多 R 版本共存：先定位包的真身，再决定用哪个 R 跑

**触发场景**：`library(monocle3)` / `library(slingshot)` 报 *there is no package called 'X'*，但 `check_env` / `rail_review` 说"已安装"；或某个 R 版本能加载包、另一个不能。

**根因（2026-09-24 实测）**：机器上有多个 R 安装，各自有各自的 library。`check_env` 探测到的库 ≠ `execute_r` 持久内核实际使用的库，所以"已装"经常是假象。
实测分布（人骨骼肌轨迹任务）：

| R 安装 | library | 关键包 |
|---|---|---|
| `E:/R-libs/R-4.5.3`（execute_r 内核实际用的库，321 包） | — | **Seurat ✅ / SingleCellExperiment ✅ / monocle3 ❌ / slingshot ❌** |
| 用户级 `C:/Users/<u>/AppData/Local/R/R-4.4.2/library` | — | **monocle3 ✅ 1.4.27 / slingshot ✅ / lme4 ✅ / Seurat ❌(loadNamespace 失败) / tradeSeq ❌** |
| `C:/Program Files/R/R-4.5.3/library`、`R-4.6.1/library` | — | 仅基础包（约 30 个） |

## 第 0 步：枚举所有 R 安装与库（别猜）

```python
import os, glob
for pat in ["C:/Program Files/R/*", "C:/Users/<u>/AppData/Local/R/*",
            "E:/R-libs/*", "C:/Users/<u>/AppData/Local/R/win-library/*",
            "C:/Users/<u>/Documents/R/win-library/*"]:
    for lib in glob.glob(pat):
        if os.path.isdir(lib):
            pkgs = os.listdir(lib) if os.path.isdir(lib) else []
            hits = [p for p in pkgs if p.lower() in ("monocle3","slingshot","tradeseq","seurat","singlecellexperiment","leidenbase")]
            print(lib, len(pkgs), hits)
# 深搜兜底（AppData 下的用户级安装自带库常被忽略）
for root in ["C:/Users/<u>/AppData/Local/R", "E:/R-libs", "C:/Program Files/R"]:
    for dp, dn, fn in os.walk(root):
        for d in dn:
            if d.lower() == "monocle3": print(os.path.join(dp, d))
```

## 第 1 步：真加载测试（不是 requireNamespace）

`requireNamespace()` 只查 DESCRIPTION，不加载 DLL → 会给出"坏包假象"。必须真加载：

```r
# 用目标 R 的 Rscript 跑；Windows 下 bash(MSYS) 直调 R 4.5.3 可能 segfault → 用 cmd.exe 包裹
for (p in c("monocle3","Seurat","slingshot","SingleCellExperiment","tradeSeq","lme4")) {
  cat(p, isTRUE(tryCatch({suppressMessages(library(p, character.only=TRUE)); TRUE}, error=function(e) FALSE)), "\n") }
```
```bash
cmd.exe /c "C:\Users\<u>\AppData\Local\R\R-4.4.2\bin\x64\Rscript.exe" "E:\...\probe.R"
```

## 第 2 步：按"谁能干什么"分工，用中间产物中转

典型组合（Seurat 在 A、monocle3 在 B，两边无法共存）：

1. **在能加载 Seurat 的 R 里读对象并导出**（本例 R-4.5.3 + `E:/R-libs/R-4.5.3`）：
   ```r
   .libPaths(c("E:/R-libs/R-4.5.3", .libPaths())); suppressMessages({library(Seurat); library(Matrix)})
   obj <- readRDS(path); ct <- GetAssayData(obj, assay="RNA", layer="counts")
   saveRDS(ct, "data/counts_rna.rds"); write.csv(obj@meta.data, "data/meta.csv")
   write.csv(Embeddings(obj,"umap"), "data/umap_seurat.csv")   # 有 harmony 就一起导出，供复用/敏感性
   ```
2. **在能加载 monocle3/slingshot 的 R 里跑轨迹**（本例 R-4.4.2）：
   ```r
   .libPaths(c("E:/R-libs/R-4.4.2", "C:/Users/<u>/R/R-4.4.2-library", .libPaths()))
   counts <- readRDS("data/counts_rna.rds"); meta <- read.csv("data/meta.csv", row.names=1, check.names=FALSE)
   umap <- as.matrix(read.csv("data/umap_seurat.csv", row.names=1, check.names=FALSE))
   cds <- new_cell_data_set(counts, cell_metadata=meta,
            gene_metadata=data.frame(gene_short_name=rownames(counts), row.names=rownames(counts)))
   cds <- preprocess_cds(cds, num_dim=50)
   cds@int_colData$reducedDims$UMAP <- umap[colnames(cds), , drop=FALSE]
   ```
   ⚠️ 中转后仍有完整 `counts`，所以 `graph_test()` 需要的 Size_Factor 由 `preprocess_cds()` 现算即可；不要跑 `align_cds()`（会洗掉上游 Harmony 校正）。

3. **中间产物全部落 `results/<sid>/data/`**（counts/meta/UMAP + cds RDS），下一步脚本只读这些，可复跑、可审计。

## 常见坑

- 别因为一个 R 版本加载失败就断定"包没装"或"环境坏了"——先按上面枚举（多数情况是**装在另一个 R 的 library 里**）。
- 用户级安装的 R（`AppData/Local/R/R-x.y.z`）自带的 `library/` 容易被漏掉，深搜时务必包含。
- 需要补装缺包时按铁律 29：先问用户，装到**项目内库**（R：`install.packages(p, lib=Sys.getenv("R_LIBS"))`），不要污染用户的 R 或系统库。
- 把探测结论写进 `task_plan.md` 的 Environment 段（哪个 R、哪个库、哪些包可用），后续步骤直接读，不要每轮重探。