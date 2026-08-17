# Windows ArchR 双 R 环境 — 实战验证安装指南

> 最后验证: 2026-07-29, R 4.5.3 + Rtools44 (symlinked) + Bioconductor 3.22
> 耗时: ~45 分钟 (包括 697MB 人类基因组下载)

## 版本兼容性矩阵

| R 版本 | Rtools | Bioc | TFMPvalue | ArchR |
|--------|:---:|:---:|:---:|:---:|
| 4.4.2 | Rtools44 ✅ | 3.20 | ❌ 不存在 | ❌ |
| **4.5.3** | Rtools45 ✅ (461MB) 或 Rtools44+符号链接 | **3.22** | ✅ | ✅ **首选** | Rtools45 正确文件名: `rtools45-6768-6492.exe` (从 `rtools.html` 源码提取，错误文件名 `rtools45-6322-6322.exe` 返回 404) |
| 4.6.1 | Rtools46 未发布 ❌ | 3.23 | ✅ | ❌ 无编译工具 |

> **R 4.5.3 是黄金版本。** R 4.6.1 太新（2026-06-24 发布，Rtools46 尚未发布），R 4.4.2 太旧（Bioc 3.20 没有 TFMPvalue）。

## 第一步：下载 R 4.5.3

```bash
curl -L -o /tmp/R-4.5.3-win.exe \
  "https://cran.r-project.org/bin/windows/base/old/4.5.3/R-4.5.3-win.exe"
```

## 第二步：安装 R 4.5.3

```bash
# 静默安装，本体放 C:\Program Files（~100MB，可接受）
"/tmp/R-4.5.3-win.exe" /SILENT /DIR="C:\Program Files\R\R-4.5.3"
# 验证
ls "/c/Program Files/R/R-4.5.3/bin/Rscript.exe"
```

## 第三步：配置 Rtools

**方案 A（推荐）：直接装 Rtools45**

```bash
# 正确文件名: rtools45-6768-6492.exe（不是 6322-6322！从 rtools.html 源码提取）
curl -L -o /tmp/rtools45.exe \
  "https://cran.r-project.org/bin/windows/Rtools/rtools45/files/rtools45-6768-6492.exe"
# 静默安装
/tmp/rtools45.exe /SILENT /DIR="C:\\rtools45"
```

**方案 B（备选）：复用 Rtools44 + 符号链接**

```bash
# Rtools44 的 gcc 在非标准路径
# /c/rtools44/x86_64-w64-mingw32.static.posix/bin/gcc.exe

# 创建符号链接让 R 4.5.3 能找到
mkdir -p /c/rtools44/ucrt64/bin
for tool in gcc g++ gfortran ar as ld nm ranlib strip dlltool windres; do
  ln -sf /c/rtools44/x86_64-w64-mingw32.static.posix/bin/${tool}.exe \
         /c/rtools44/ucrt64/bin/${tool}.exe
done

# 验证
export PATH="/c/rtools44/ucrt64/bin:/c/rtools44/usr/bin:$PATH"
gcc --version  # 应输出: gcc.exe (GCC) 13.3.0
```

## 第四步：修复 .Rprofile（关键！）

`.Rprofile` 硬编码库路径会劫持所有 R 版本的包安装。修复：

```r
# ~/.Rprofile
local({
  r_ver <- paste(R.version$major, R.version$minor, sep = ".")
  mylib <- file.path("USER_R_LIBS", paste0("R-", r_ver))
  dir.create(mylib, showWarnings = FALSE, recursive = TRUE)
  .libPaths(c(mylib, .libPaths()))
})
```

## 第五步：安装 ArchR + 依赖

### 镜像配置

```
CRAN:        https://mirrors.tuna.tsinghua.edu.cn/CRAN/          (清华, 快)
Bioconductor: https://mirrors.westlake.edu.cn/bioconductor         (西湖, Bioc 包全)
```

⚠️ 清华镜像**没有** Bioconductor 包，CRAN 包正常。Bioc 必须用西湖或官方。

### 安装脚本

保存以下为 `install_archr.R`，然后用 R 4.5.3 执行：

```r
# === install_archr.R ===
mylib <- 'USER_R_LIBS/R-4.5.3'
dir.create(mylib, showWarnings = FALSE, recursive = TRUE)
.libPaths(c(mylib, .libPaths()))
options(repos = c(CRAN = 'https://mirrors.tuna.tsinghua.edu.cn/CRAN/'))
options(BioC_mirror = 'https://mirrors.westlake.edu.cn/bioconductor')

# 1. BiocManager
if (!require('BiocManager', quietly = TRUE)) install.packages('BiocManager')
library(BiocManager)

# 2. 核心依赖 (逐个装，每个输出日志)
for (p in c('TFMPvalue', 'TFBSTools', 'motifmatchr', 'chromVAR',
            'BSgenome', 'DirichletMultinomial', 'nabor')) {
  cat('\n---', p, '---\n')
  BiocManager::install(p, update = FALSE, ask = FALSE)
}

# 3. 基因组 (大文件，697MB hg38 + 猕猴)
for (g in c('BSgenome.Hsapiens.UCSC.hg38', 'BSgenome.Mmulatta.UCSC.rheMac10')) {
  cat('\n---', g, '---\n')
  BiocManager::install(g, update = FALSE, ask = FALSE)
}

# 4. ArchR (GitHub)
install.packages('remotes')
remotes::install_github('GreenleafLab/ArchR', dependencies = FALSE,
                        upgrade = 'never')

# 5. 验证
library(ArchR)
cat('\n*** ArchR v', as.character(packageVersion('ArchR')), ' ***\n')
```

### 执行

```bash
PATH="/c/rtools44/ucrt64/bin:/c/rtools44/usr/bin:$PATH"
"C:/Program Files/R/R-4.5.3/bin/Rscript.exe" --vanilla install_archr.R
```

> ⚠️ **用 background 模式跑** — Bash+R 偶发 segfault (exit 139, tcsetattr)，background 模式可缓解。

## 第六步：监控安装进度

不要 fire-and-forget。主动轮询：

```bash
# 每 60 秒检查一次库目录的包数量
watch -n 60 'ls USER_R_LIBS/R-4.5.3/ | wc -l'

# 预期进度：
#   ~3 个  → BiocManager + TFMPvalue + Rcpp
#  ~64 个 → TFBSTools + 全部依赖装完
#  ~90 个 → motifmatchr + ggplot2 生态装完
# ~129 个 → 全部 Bioc 依赖装完，基因组下载中
# ~131 个 → 基因组装完，ArchR 编译中
# ~132 个 → ArchR 装完！
```

## 调用方式

```bash
# Seurat/Signac → 默认 R (4.4.2)
Rscript seurat_analysis.R

# ArchR → 显式指定 R 4.5.3
PATH="/c/rtools44/ucrt64/bin:/c/rtools44/usr/bin:$PATH" \
  "C:/Program Files/R/R-4.5.3/bin/Rscript.exe" --vanilla archr_atac.R
```

## Arrow 文件格式说明

ArchR Arrow 文件是**自定义格式**，不是 Apache Arrow IPC，也不是 Parquet。
- ❌ `pyarrow.ipc.open_file()` → "Not an Arrow file"
- ❌ `pyarrow.parquet.read_table()` → 读不了
- ✅ 只能用 `ArchR::loadArchRProject()` 或相关函数读取

## 已知失败模式

| 错误 | 根因 | 修复 |
|------|------|------|
| `TFMPvalue: Needs R >= 4.5.0` | R 版本太旧 | 用 R 4.5.3，不是 4.4.2 |
| `Could not find tools necessary to compile` | 没有 Rtools | 配置 Rtools44 符号链接 |
| `'lib="C:/Program Files/.../library"'不可写` | `.libPaths()` 没生效 | 检查 `.Rprofile` |
| `exit code 139 (segfault)` | Bash+R 冲突 | 用 `terminal(background=True)` |
| `exit code 2/5` (Rtools45 安装器) | 安装器 bug | 复用 Rtools44 |
| Bioconductor 下载卡住 | 清华镜像没有 Bioc 包 | 换西湖镜像 |
