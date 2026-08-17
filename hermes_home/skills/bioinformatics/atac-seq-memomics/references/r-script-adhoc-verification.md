# R 脚本自检模式（ad-hoc verification via execute_code）

## 问题

写完 R 分析脚本后，需要验证三件事才能放心交付给 background 执行：
1. 语法正确（`parse()` 不报错）
2. 依赖可加载（`library()` 成功）
3. 前置条件满足（RDS 文件存在等）

单独调用 `execute_r` 会阻塞整个分析上下文，直接跑脚本又怕 crash。

## 方案

用 `execute_code`（Python）写一个临时 R 脚本到 `tempfile`，用 `subprocess.run` 跑它，读完输出即删。

## 模板

```python
import tempfile, os, subprocess

R = r"C:\Program Files\R\R-4.5.3\bin\x64\Rscript.exe"  # 硬编码正确版本
SCRIPT_PATH = "E:/path/to/my_script.R"                   # 要验证的目标脚本

vf = os.path.join(tempfile.gettempdir(), "hermes-verify-temp.R")
with open(vf, 'w') as f:
    f.write(f'''
cat("=== PARSE CHECK ===\\n")
tryCatch({{ parse(file="{SCRIPT_PATH}"); cat("PASS: syntax valid\\n") }},
         error=function(e) {{ cat("FAIL:", conditionMessage(e), "\\n"); quit(status=1) }})

cat("\\n=== DEP CHECK ===\\n")
.libPaths(c("USER_R_LIBS/R-4.5.3", .libPaths()))
suppressPackageStartupMessages(library(ArchR))
addArchRGenome("hg38")
cat("PASS: ArchR + hg38 loaded\\n")

cat("\\n=== PREREQ CHECK ===\\n")
if (file.exists("E:/path/to/input.rds")) {{
  cat("PASS: input.rds exists\\n")
}} else {{
  cat("WAIT: input.rds not yet generated\\n")
}}

cat("\\n=== ALL PASSED ===\\n")
''')

result = subprocess.run([R, vf], capture_output=True, text=True, timeout=120,
                        env={**os.environ, 'TMPDIR': 'E:/tmp'})
print(result.stdout.rstrip())
if result.returncode != 0:
    print(f"FAILED with exit code {result.returncode}")

os.unlink(vf)
```

## 关键点

- **R 全路径**：不能靠 PATH 上的 `Rscript`（可能版本不对）
- **forward slashes**：`SCRIPT_PATH` 用 `/` 而非 `\`，否则 R 把 `\M` 当转义
- **TMPDIR**：设 `E:/tmp` 避免 C 盘空间不足
- **超时**：`timeout=120`，依赖加载一般 < 30s
- **清理**：`os.unlink(vf)`，不留垃圾

## 验证时机

1. 写完新脚本但还没跑之前
2. 修改了已存在的脚本后
3. 系统唤醒后（确认环境未被之前的 crash 损坏）
