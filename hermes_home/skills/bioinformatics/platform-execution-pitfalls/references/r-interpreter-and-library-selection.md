# R 解释器 / 库版本选择配方（同一包里"装了却 load 不了"的根治）

> 实测来源：2026-09-24 骨骼肌 MF 细胞通讯会话（CellChat v1.6.1）。
> 触发场景：`library(X)` 报 `there is no package called 'X'`，但包**确实装在磁盘上**（或 `check_env` 说装了、`rail_review(pre)` 说没装）——先读完本文再动手，不要重装、不要反复改审查参数。

## 0. 一句话判据

**"包有没有装"是错的问法；正确问法是"包装在哪个 R 版本的库里，我这次用的解释器是不是那个版本"。**
平台 `execute_r` 持久内核固定走某一个 R（本项目为 R 4.5.3），**不会**因为包在别的 R 里就自动切过去。

## 1. 定位阶段（3 条命令，全部只读）

```bash
# ① 三处扫盘：R 库根目录都在这些位置
find "E:/R-libs" "C:/Users/<user>/AppData/Local/R" "C:/Program Files/R" \
     -maxdepth 3 -iname "<PkgName>" -type d 2>/dev/null

# ② 当前内核用的是哪个 R、有哪些库
#    execute_r:  cat(R.version.string); print(.libPaths())
#    → 实测输出示例
#      R version 4.5.3 (2026-03-11 ucrt)
#      "E:/R-libs/R-4.5.3"  "C:/Program Files/R/R-4.5.3/library"     ← 两个库都没有 CellChat/NMF

# ③ 目标版本解释器里各包版本
"C:/Users/<user>/AppData/Local/R/R-4.4.2/bin/x64/Rscript.exe" -e \
 'cat(R.version.string,"\n"); for (p in c("Seurat","CellChat","NMF","patchwork","ComplexHeatmap")) \
  cat(sprintf("%-16s %s\n", p, tryCatch(as.character(packageVersion(p)), error=function(e) "MISSING")))'
```

⚠️ `packageVersion()` 只读 DESCRIPTION、**不加载依赖** —— 它说 5.5.0 不代表 `library()` 能成功。
真正的判据永远是一次 `library()` 实测（用 `tryCatch` 包起来，别让整段崩）。

## 2. 依赖闭包体检（找出"还差哪几个包"）

```r
# .libPaths 必须收到「目标版本」的库，否则 installed.packages() 会把别版本的包也算进来
ip  <- rownames(installed.packages())
dep <- tools::package_dependencies("<PkgName>", db = installed.packages(), recursive = TRUE)[[1]]
cat("n_installed:", length(ip), " n_deps:", length(dep), "\n")
cat("MISSING:", paste(setdiff(dep, ip), collapse = ", "), "\n")
```

实测（CellChat 1.6.1，R 4.4.2 用户库 526 包）：**145 个依赖里只缺 `svglite`、`gridExtra`** —— 这类结论让下一步"补什么、补到哪"变成确定性动作，而不是逐个试错。
（`svglite` 是 CellChat 的 **Imports 硬依赖**，见 `CellChat/DESCRIPTION` 的 `Imports:` 行；`gridExtra` 是 Seurat 侧的依赖，缺它连 `library(Seurat)` 都进不去。）

## 3. 库路径组装规则（跨版本只允许"纯 R 包"）

| 包类型 | 能否跨小版本借用 | 说明 |
|---|---|---|
| 含编译代码（有 `libs/x64/*.dll`，如 svglite / NMF / Rcpp 系） | ❌ **绝不** | 实测 `无法载入共享目标对象 'E:/R-libs/R-4.5.3/svglite/libs/x64/svglite.dll' : LoadLibrary failure: 找不到指定的程序` |
| 纯 R 包（如 gridExtra） | ✅ 可以 | 挂在第二个库即可被解析，实测 `library(Seurat)` 因此成功 |

```bash
# 目标版本解释器 + 双库（目标版本库在前；第二库只用来补纯 R 包）
export R_LIBS="C:/Users/<user>/AppData/Local/R/R-4.4.2/library;E:/R-libs/R-4.5.3"
"C:/Users/<user>/AppData/Local/R/R-4.4.2/bin/x64/Rscript.exe" -e \
 'tryCatch({library(Seurat); library(CellChat); cat("LOAD_OK\n")},
           error=function(e) cat("FAIL:", conditionMessage(e), "\n"))'
```

## 4. 长任务启动（走统一包装器，便于面板观战/取消）

```bash
cd /e/MemOmics-Agent && python memomics/bio_tools/task_run.py \
  --type cellchat --title "<任务名>" --session-dir results/<sid> \
  --stages "读入,主分析,对照,敏感性,汇总" \
  --param 数据=<文件> --param 分组=<口径> \
  --script results/<sid>/scripts/01_build.R \
  -- "<目标版本 Rscript 绝对路径>" "E:/.../scripts/01_build.R"
```

脚本文本里打点（任何语言、零依赖）：`cat("#TASK:STAGE 主分析\n")` / `cat("#TASK:PROGRESS 0.35 ...\n")`。

## 5. 铁律 29 边界（什么时候必须问用户）

- 目标版本库**已经有**这个包 → 直接用该版本解释器跑，**不装任何东西**（本次正解）。
- 只差**纯 R 小包** → 优先从另一个已有库借（R_LIBS），仍然 **不装**。
- 只差**编译包**且无任何版本可用 → **按铁律 29 先问用户**，装进 **E 盘项目库**（如 `E:/R-libs/R-4.4.2`），命令示例：
  ```bash
  "<目标版本 Rscript>" -e 'install.packages(c("svglite","gridExtra"), lib="E:/R-libs/R-4.4.2",
                            repos="https://cloud.r-project.org", type="win.binary")'
  ```
  R 4.5.3 无 Rtools45 ⇒ 源码编译必失败，**一律 `type="win.binary"`**；
  注意 CRAN 的 win.binary 目录按 R 小版本分（4.4 / 4.5），要装进哪版就用哪版 Rscript 去装。
- ⛔ 不要为了"过审查"去改 `rail_review` 的 `required_packages` 或重装已存在的包；审查口径与真实执行环境无关（见 SKILL.md 主表 pre/post 那几行）。

## 6. 汇报模板（透明、可复现）

> 分析已就绪，但被环境问题卡住：`library(CellChat)` 报包不存在。
> 逐层排查确认：CellChat 1.6.1 + NMF 0.28 **只装在 R 4.4.2 用户库**，平台内核跑 R 4.5.3（两个库都没有）。
> CellChat 的 145 个依赖里，4.4.2 库只差 `svglite`（CellChat 的 Imports 硬依赖）与 `gridExtra`（Seurat 依赖）；
> 4.5.3 库里有这两个包但**编译版 DLL 跨小版本加载失败**，所以不能靠挂库绕过。
> 待用户确认安装命令后 → 用 R 4.4.2 解释器 + `task_run.py` 起分析。

**要点**：把"包在哪、差什么、为什么不能借、下一步一条命令"四件事一次讲清 —— 用户只需回一句「可以」。