# Bash+R Segfault → cmd.exe 包装工作流

**验证日期**: 2026-07-29
**验证环境**: Windows 11 + git-bash (MSYS2) + R 4.5.3 + ArchR 1.0.3
**验证数据**: 猴海马 scATAC-seq, 35K cells, 21 clusters, Arrow files ~5GB

## 问题

在 git-bash 下运行 ArchR R 脚本时，随机 segfault (exit code 139)：

```bash
# 直接跑 — segfault
/c/Program\ Files/R/R-4.5.3/bin/Rscript.exe script.R
→ Segmentation fault (exit 139)

# terminal(background=True) — 仍然 segfault
terminal(command="Rscript script.R", background=True)
→ exit_code: 139
```

## 根因

bash 与 R 的动态库加载器（rhdf5、Matrix 等包加载时）冲突。`terminal(background=True)` 并不能绕过 bash——它仍是 bash 子进程。

## 解决方案：cmd.exe /c 包装

**Step 1**: 写 `.R` 脚本，使用 Windows 绝对路径：

```r
# script.R
.libPaths(c("USER_R_LIBS/R-4.5.3", .libPaths()))
library(ArchR)
addArchRGenome("hg38")
addArchRThreads(threads = 1)

proj <- readRDS("E:/专利/ArchR_Output/project_clustered.rds")
proj <- addGroupCoverages(proj, groupBy = "Clusters", force = TRUE)
saveRDS(proj, "E:/专利/ArchR_Output/project_cov.rds")
cat("DONE\n")
```

**Step 2**: 写 `.bat` 包装器：

```bat
@echo off
echo Started: %DATE% %TIME%
"C:\Program Files\R\R-4.5.3\bin\Rscript.exe" "E:\path\to\script.R" > "E:\path\to\output.log" 2>&1
echo EXIT_CODE=%ERRORLEVEL%
echo Finished: %DATE% %TIME%
```

**Step 3**: 通过 Hermes terminal 启动（background + notify）：

```
terminal(
  command='cmd.exe /c "E:\\path\\to\\run.bat"',
  background=True,
  notify_on_complete=True,
  timeout=3600
)
```

## 注意事项

- 路径用反斜杠 `\\`（cmd.exe 风格），不是 bash 的 `/`
- `.bat` 中的 `> 2>&1` 负责捕获 R 的 stdout+stderr
- R 通过 cmd.exe 运行时 stdout 会缓冲——日志不会实时更新，每 20-30 秒刷一批
- 心跳监控必须读日志文件的 `file.size`/`wc -l` 判断进度，不能依赖 `tail -f` 行为
- `notify_on_complete=True` 是必需的——任务完成后自动通知

## 对比

| 方法 | segfault? | 日志实时? | 推荐? |
|------|:---:|:---:|:---:|
| bash 直接跑 Rscript | ✅ 高概率 | ✅ | ❌ |
| terminal(background=True) | ✅ 仍会 | ✅ | ❌ |
| cmd.exe /c + .bat | ❌ | 🟡 缓冲 | ✅ |
