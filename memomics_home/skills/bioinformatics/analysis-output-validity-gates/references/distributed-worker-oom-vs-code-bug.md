# 归因：分布式 worker OOM ≠ 代码 bug（dask / distributed / 多进程）

（2026-09-24 真机实测定位）

## 特征性报错组合（看到这个组合，直接去查内存，别改代码）

```
worker 侧：
  MemoryError: cannot allocate memory for array
  numpy._core._exceptions._ArrayMemoryError: Unable to allocate 1.93 MiB for an array with shape (253096,)
  pyscenic.transform - ERROR - Unable to process "PRDM5" on database "..." because ran out of memory.

scheduler 侧：
  distributed.scheduler - ERROR - Removing worker 'tcp://127.0.0.1:63936' caused the cluster to lose
    scattered data, which can't be recovered: {'FeatherRankingDatabase-...', 'DataFrame-...'}

client 侧：
  distributed.client.FutureCancelledError: finalize-<hash> cancelled for reason: unknown.
    （栈：pyscenic.prune._distributed_calc → client.compute(create_graph(client), sync=True) → client.gather）
```

**判读**：
- `Unable to allocate 1.93 MiB` —— 连 **2MB** 都要不到，说明不是"数据太大"，是**进程/系统级内存额度耗尽**。
- `caused the cluster to lose scattered data` —— worker 死后 `client.scatter` 的数据没了，
  后续 task 全部连锁失败。
- `FutureCancelledError: finalize-... cancelled for reason: unknown` —— **这是 worker 被移除的结果，不是原因**。
  它是 dask 图里 finalize 任务被取消的表象，**不要**据此去改 pyscenic/dask 的调用代码。

## 为什么"上次同样的代码能跑通，这次就崩"

分布式任务的峰值内存 ≈ **worker 数 × (每 worker 一份常驻开销 + 每 task 峰值)**。
`prune2df(list)` 这类调用会把 motif annotations（≈GB 级的 DataFrame）**scatter 到每个 worker 各一份**，
再加 DB 子集与 numba JIT。所以：
- worker 数 ×1 → 常驻翻倍；
- **机器上其它进程的占用会直接决定成败**（本会话同一脚本，2 workers 崩、1 worker 9 分钟跑完）。

## 诊断命令（Windows：看 commit 上限，不是物理内存）

```powershell
# 系统 commit：已用 / 上限（<- 决定成败的就是这个）
$p = Get-Counter '\Memory\Committed Bytes','\Memory\Commit Limit' -ErrorAction SilentlyContinue
$p.CounterSamples | ForEach-Object { $_.Path + ' = ' + [math]::Round($_.CookedValue/1GB,2) + ' GB' }
# 物理内存余量（参考）
$o = Get-CimInstance Win32_OperatingSystem; [math]::Round($o.FreePhysicalMemory/1MB,2)
# 谁在吃内存（按 private bytes 排序；含命令行/启动时间归属判断）
Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='Rscript.exe'" |
  Select-Object ProcessId,Name,@{n='PRIV_MB';e={[math]::Round($_.PrivatePageCount/1MB,0)}},
    @{n='Started';e={$_.CreationDate}},@{n='CMD';e={$_.CommandLine}} |
  Sort-Object PRIV_MB -Descending | Format-Table -AutoSize
```
Linux：`free -g`（看 available + swap）、`ps -eo pid,rss,etime,cmd --sort=-rss | head`。

## 并发选择规则（先量再定，不要试错）

| commit 余量 | 建议 |
|-------------|------|
| > ~20GB | 可按 CPU 数取并发（但仍别用库默认的 `os.cpu_count()`） |
| ~10-20GB | N_WORKERS = 2 |
| < ~10GB | **N_WORKERS = 1**，并且先释放自己能释放的（自己的 kernel/中间对象），再跑 |

实测锚点：5277 个模块的 cisTarget 剪枝，1 worker ≈ **9 分钟**通过；同样代码 2 workers 在 ~90 秒
就 OOM 崩掉。**降到 1 worker 的代价（≈几分钟）远小于崩掉重跑一轮。**

## 释放内存的正确顺序（不动别人的进程）

1. **先释放自己的**：重启本会话 kernel / 清掉不再需要的大对象；确认自己进程的 PID
   （在 kernel 里 `import os; os.getpid()` 即得，用于区分"这是我的 worker"）。
2. **降并发**（上表）。
3. 还不够 → 列出进程的 private bytes + 启动时间 + 命令行，**区分归属**：
   属于其他会话/其他人的分析进程（如别的会话正在跑的 `Rscript scripts/xxx.R`）→
   **不许动**，先向用户说明并请示；只有确认是自己会话的遗孤进程才清理。
4. 清进程的纪律：**先有真实的 kill 工具调用，再有验证命令输出**（`killed <PID>` / 复查列表为空），
   最后才可以说"清理完成"——没有工具调用证据的完成声明视为虚报。

## 常见误判

| 误判 | 事实 |
|------|------|
| "代码有 bug，改改参数重试" | 是内存额度问题，改代码无效；先量后调并发 |
| "机器内存很大（物理 55GB）所以没问题" | Windows 看的是 **commit 上限**（本机 80.6GB，长期占用 72-78GB），物理余量会骗人 |
| "worker 数越多越快" | 每个 worker 各持一份 GB 级 annotations，人多反而必崩 |
| "有断点/checkpoint 就能续" | scatter 的 scattered 数据丢了不可恢复（无 checkpoint 时只能重跑该步） |