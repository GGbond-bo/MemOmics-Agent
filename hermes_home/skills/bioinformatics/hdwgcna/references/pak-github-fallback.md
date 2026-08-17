# pak: GitHub R 包安装回退方案

## 问题

`remotes::install_github("user/repo")` 在以下场景频繁失败：
- GitHub API 限流（未认证请求每小时仅 60 次）
- 特定网络环境下 GitHub 不可达
- 大仓库克隆超时

## 解决方案：pak

`pak` 是 r-lib 团队开发的新一代 R 包管理器，替代 `install.packages()` + `remotes::install_github()`。

### 优势
- 使用独立的 GitHub 认证通道（与 remotes 不同）
- 支持并行下载
- 更智能的依赖解析
- 锁文件支持（类似 renv）

### 安装 pak（如果未预装）

```r
install.packages("pak", repos = "https://r-lib.github.io/p/pak/stable/")
```

### 安装 GitHub 包

```r
# 等价于 remotes::install_github("user/repo")
pak::pak("user/repo")

# 具体示例：hdWGCNA
pak::pak("smorabit/hdWGCNA")

# 指定分支/标签
pak::pak("user/repo@branch")
pak::pak("user/repo@v1.0.0")

# 指定 subdir（monorepo 中的子包）
pak::pak("user/repo/subdir")
```

### 本环境状态

| 项目 | 状态 |
|------|------|
| pak 版本 | 0.9.4 ✅ 已安装 |
| R 版本 | 4.4.x |
| 系统 | Windows 11 |

### 适用场景

不只是 hdWGCNA — **所有通过 GitHub 安装的 R 包**都可以优先尝试 `pak::pak()`：

- `pak::pak("satijalab/seurat")` — Seurat 开发版
- `pak::pak("jinworks/CellChat")` — CellChat
- `pak::pak("velocyto-team/velocyto.R")` — velocyto.R
- 任何 Bioconductor devel 包

### 何时使用 pak vs remotes

| 场景 | 推荐 |
|------|------|
| CRAN 包 | `pak::pak()` (更快) |
| Bioconductor | `pak::pak()` (自动处理 BioC 镜像) |
| GitHub — 正常网络 | 两者均可 |
| GitHub — remotes 超时 | `pak::pak()` ✅ |
| 需要锁文件 | `pak::lockfile_create()` + `pak::lockfile_install()` |
