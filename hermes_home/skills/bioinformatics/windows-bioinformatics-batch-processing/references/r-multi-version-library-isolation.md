# R 多版本共存 — 库路径隔离方案（Windows）

## 问题

Windows 上同时安装多个 R 版本（如 R 4.4.2 + R 4.6.1），但 `.Rprofile` 或 `.Renviron` 硬编码了旧版库路径，导致新版 R 的 `.libPaths()` 被劫持到旧版库目录。后果：
- 新版本 R 安装的包跑到旧版库目录
- `library()` 加载失败（包为旧 R 版本编译，新版不兼容）
- 每个 R 版本应该有自己的独立库路径

## 根因

`~/.Rprofile` 中的硬编码：
```r
r4lib <- normalizePath("C:/Users/xxx/AppData/Local/R/R-4.4.2/library", ...)
.libPaths(unique(c(r4lib, keep)))
```
此代码不检查当前 R 版本，强制所有 R session 使用 R 4.4.2 库。

## 修复：版本自感知 .Rprofile

```r
# ============================================================================
# .Rprofile — R 多版本库路径自动适配
# ============================================================================
local({
  r_ver <- paste(R.version$major, R.version$minor, sep = ".")
  r_lib <- normalizePath(
    file.path(Sys.getenv("USERPROFILE"), "R", paste0("R-", r_ver, "-library")),
    winslash = "/", mustWork = FALSE
  )
  if (!dir.exists(r_lib)) dir.create(r_lib, recursive = TRUE)
  .libPaths(c(r_lib, .libPaths()))
})
options(repos = c(CRAN = "https://mirrors.westlake.edu.cn/CRAN"))
options(BioC_mirror = "https://mirrors.westlake.edu.cn/bioconductor")
```

## 效果

| R 版本 | 库路径 |
|--------|--------|
| R 4.4.2 | `C:/Users/xxx/R/R-4.4.2-library` |
| R 4.6.1 | `C:/Users/xxx/R/R-4.6.1-library` |

每个版本独立，互不污染。

## 验证

```bash
# 验证 R 4.6.1
"C:/Program Files/R/R-4.6.1/bin/Rscript.exe" -e "cat(.libPaths()[1])"
# 输出: C:/Users/xxx/R/R-4.6.1-library

# 验证 R 4.4.2  
"C:/Users/xxx/AppData/Local/R/R-4.4.2/bin/x64/Rscript.exe" -e "cat(.libPaths()[1])"
# 输出: C:/Users/xxx/R/R-4.4.2-library
```

## 跨环境调用

```bash
# 用特定 R 版本运行脚本
"C:/Program Files/R/R-4.6.1/bin/Rscript.exe" archr_atac.R   # R 4.6.1
Rscript seurat_analysis.R                                      # 默认 R（PATH 中）
```

## 相关

- ArchR 需要 R ≥ 4.5.0（>= Bioc 3.23），而 Seurat/Signac 在 R 4.4.2 已稳定
- 双版本策略：R 4.4.2 跑 Seurat/Signac/SCENIC，R 4.6.1 跑 ArchR
- 两者通过磁盘文件（rds/h5）通信，不共用内存
