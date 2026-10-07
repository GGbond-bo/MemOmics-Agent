# 持久内核崩溃（exit 0xC0000142）时的「先落日志 + 改独立进程」配方

> 来源：2026-09-24 会话（MF_2000 细胞周期打分）。同一套脚本在持久内核里连崩 3 次，改用独立 Rscript 进程后一次跑通；
> 且因为**每个脚本开头都 sink 了日志**，崩溃前算出的 ICC / 置换 p / marker 检出率全部保住了。

## 1. 症状识别（判据）
- 回执只有 `[Exit code: 3221225794]` / `R exited with code 3221225794`
  —— 3221225794 = `0xC0000142` = `STATUS_DLL_INIT_FAILED`，是**进程级**失败
- **stdout 全丢**（工具只回 stderr），看起来像"脚本一行没跑"，很容易误判成脚本逻辑错
- 复现性：同一脚本连投 3 次都停在**同一节**；而**同一份代码**在独立 `Rscript` 进程里能跑完
- 本例触发点：`AddModuleScore()` 连续调用（10 次随机基因集）× 之后的重矩阵操作（`LayerData` 全矩阵 + `rowMeans`）

🔑 **判据**：`Exit code 3221225794` + 日志停在某一节 ⇒ 内核进程级问题，**不要再去改脚本内容**，
换执行方式（独立进程）或把重活拆小。

## 2. 第一件事：脚本自带日志（崩溃也保住结果）
```r
LOG <- "results/<sid>/log/01_cellcycle.log"
dir.create(dirname(LOG), showWarnings = FALSE, recursive = TRUE)
con <- file(LOG, open = "wt", encoding = "UTF-8"); sink(con, split = TRUE)   # split=TRUE 同时打屏
suppressPackageStartupMessages({library(Seurat); library(ggplot2)})
setwd("results/<sid>")                       # 或绝对路径
# ... 正文：每节都 write.csv + cat 进度 ...
sink(); close(con)
```
- 崩溃时日志**保留到最后一节** → 能精确定位崩在哪、已拿到哪些数字（本例靠日志取回 ICC/设计效应/置换 p/基线表达等）
- 配套：**每节单独 `write.csv`**，不要把落盘全堆在脚本末尾（否则崩溃 = 全部白跑）

## 3. 分区自诊断（可选，读侧用）
```r
ok <- function(tag, ex) { r <- tryCatch({force(ex); "OK"},
                         error = function(e) paste("FAIL:", conditionMessage(e)))
  cat(sprintf("[%-18s] %s\n", tag, r)); invisible(r) }
```
⚠️ 只用于**读侧诊断**（版本/加载/读文件）；`ok()` 里用 `<<-` 给全局变量赋值在某些内核状态下会报
`object 'x' not found`——赋值逻辑写在正文里。

## 4. 崩溃后的处置顺序（不要原样重投第 3 次）
1. **读一次日志**确认跑到哪一节（一次即可，不要连环 tail）。
2. 把脚本**按节拆成小块**，编号 `05_*.R` / `06_*.R` / `07_*.R`，一块一个进程（打分 → 统计 → 出图 → 稳健性）。
3. 改**独立 Rscript 进程**（bash 里直调绝对路径，正斜杠）：
```bash
cd /e/MemOmics-Agent/results/<sid> && "/c/Program Files/R/R-4.5.3/bin/x64/Rscript.exe" --vanilla scripts/06_final_robustness.R > log/06_stdout.txt 2>&1; echo "exit=$?"; cat log/06_final.log
```
   - ⛔ 不要写 `cmd //c "\"...Rscript.exe\" ..."`：MSYS 吃掉引号，回执里只出现 cmd 的版本 banner，
     **exit=0 但脚本一行没跑**（同族坑见 SKILL.md 坑表「cmd.exe /c 调带空格路径的 exe」）
   - foreground timeout 硬上限 600s；再长就 `background=True + notify_on_complete=True`
4. 内存面：一节跑完就 `rm(大对象); gc()`；独立进程退出即释放（持久内核则不释放）。

## 5. 可复用的「分片」经验
- 一次进程只做**一块能在 1–2 分钟内完成**的活；出图单独一块；统计单独一块
- 随机基因集/置换这类**循环重计算**容易压垮内核 → 放独立进程，且用 `Matrix::colMeans` 等轻量算法替代
  `AddModuleScore`（后者会复制对象并做 bin 校正，量大得多）
- 崩溃后**不要**为了"确认一下"重复跑同一脚本：属静态判定类问题，重跑不改结果，只赚循环告警
  （判据见 SKILL.md 坑表「静态文本类 issue 不重跑」）