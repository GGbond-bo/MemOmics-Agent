# Windows 提交内存（commit limit）与重任务内存调优

> 来源：2026-09-24 人骨骼肌 snRNA-seq（MF_2000，2132 核）pySCENIC/GRNBoost2 实战。
> 连吃 4 次失败才定位真根因（前 3 次的根因判断都被后续实测推翻）。
> **目的：让下一次 5 分钟定位，而不是 4 轮返工。**

## 0. 一句话判据

> 报错数组只有 **MB 级**、而 `psutil` 显示物理内存**还剩十几 GB** ⇒
> **不是"物理内存不够"**。先查 **commit 余量** + 查 `dask memory_limit` 是否被设了小值。
> 两件都排除后，才轮到"减数据规模"。

## 1. 症状对照表

| 现象 | 真根因 | 别误判成 |
|---|---|---|
| `MemoryError((2132, 1620), dtype('float32'))` 刷屏（数组 ≈13.8 MB） | commit 触顶 **或** dask worker `memory_limit` 主动抛错 | 「机器内存不够」→ 白减细胞/基因 |
| `OSError: [WinError 1455] 页面文件太小，无法完成操作` | commit limit（RAM+pagefile）触顶 | 「pagefile 坏了」 |
| 大量 `WARNING: infer_data failed for target X' Retry (n/10)` | 同上（arboreto 在 worker 上反复重试同一分配） | 「基因名不匹配」→ 白改基因过滤 |
| 报错发生在 load DLL 阶段（如 `cufft64_11.dll`） | commit 紧张到连库加载都失败 | 「包装坏了」 |

## 2. 根因 A：Windows commit limit（真正的天花板）

物理内存 ≠ 可提交内存。进程每次分配都向 commit 记账，**上限 = 物理 RAM + pagefile**。

```python
import ctypes
class PERF(ctypes.Structure):
    _fields_ = [('cb', ctypes.c_ulong), ('CommitTotal', ctypes.c_size_t), ('CommitLimit', ctypes.c_size_t),
                ('CommitPeak', ctypes.c_size_t), ('PhysicalTotal', ctypes.c_size_t),
                ('PhysicalAvailable', ctypes.c_size_t), ('SystemCache', ctypes.c_size_t),
                ('KernelTotal', ctypes.c_size_t), ('KernelPaged', ctypes.c_size_t),
                ('KernelNonpaged', ctypes.c_size_t), ('PageSize', ctypes.c_size_t),
                ('HandleCount', ctypes.c_ulong), ('ProcessCount', ctypes.c_ulong),
                ('ThreadCount', ctypes.c_ulong)]
p = PERF(); p.cb = ctypes.sizeof(p)
ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(p), p.cb)
k = p.PageSize / 1e9
print(f"Commit {p.CommitTotal*k:.1f}/{p.CommitLimit*k:.1f} GB  headroom={(p.CommitLimit-p.CommitTotal)*k:.1f} GB")
```

实测基线（本机 2026-09-24）：
```
CommitLimit = 86.5 GB
CommitTotal = 76.6 GB   (88.5% of limit)   <-- 余量仅 9.2 GB
CommitPeak  = 86.5 GB   <-- 曾经触顶
PhysicalTotal 59.7 GB / Available 13.2 GB
Pagefile 26.8 GB（仅用 2.0 GB）
```
⇒ **物理还剩 13 GB，commit 只剩 9.2 GB**，且 peak 已到顶 ⇒ 十几 MB 的分配失败完全合理。

⚠️ `wmic` 在 **Windows 11 已被移除**（`'wmic' not found`），不要用 `wmic OS get FreePhysicalMemory` 探内存；
R 里也别用（`system("wmic ...")` 会把整段分析带崩——见坑表）。
现成探针：`scripts/check_commit_memory.py`。

## 3. 根因 B：dask worker 的 `memory_limit` 会**主动抛** MemoryError

arboreto 的 `grnboost2(..., client_or_address='local')` 是**默认值** → 它**自建**
`LocalCluster(n_workers=os.cpu_count(), threads_per_worker=1)`，而 dask 给每个 worker 一个内存预算：
- 不给参数：按系统总量均分（20 核机上 ≈ **2.4 GB/worker**）
- 手动设 `memory_limit="6GB"`：一样紧

worker 一旦超预算，dask 抛的就是 **MemoryError**（不是警告、不落盘、不 spill）。
而 arboreto 的 `_infer_data` 对**每一个 target** 都要构建 `(n_cells × n_TF)` 矩阵并在 worker 上累积多份中间数据
—— 2132×1620 时单份仅 13.8 MB，但 1620 个 target × 多个 partition 并发累积，轻易越过几 GB 的预算线。

⇒ **`memory_limit` 必须设 0（= 不限制）**。设小值等于自己给自己下套。

> 这解释了为什么"限制 worker 数到 6 + `memory_limit="6GB"`"**仍然失败**：
> 两个约束里，真正卡死的是 **memory_limit 本身**，降 worker 数并不解决它。

## 4. 修复配方

```python
from dask.distributed import Client, LocalCluster

cluster = LocalCluster(
    n_workers=2,              # commit 余量 <10 GB → 2~4；余量充足可 8
    threads_per_worker=1,
    memory_limit=0,           # 🔴 0 = 不限制（设小值 = 主动抛 MemoryError 的开关）
    dashboard_address=None,
    silence_logs=40,
)
client = Client(cluster)
# 再把 client 传给具体分析函数（需该函数支持 client 透传，例如已加过
# run_complete_grn_workflow(..., client_or_address=client) 这类可选参数）
```

配套四件：
1. 表达矩阵转 **float32**（`np.asarray(m.T.todense(), dtype=np.float32)`）
2. 跑之前 `rm()` 掉 R 内核里不再用的大对象（Seurat 对象 / 中间矩阵）+ `gc()`
3. `TMPDIR` / `TEMP` / `TMP` 指到大盘（`TMPDIR=/e/tmp`），避免 C 盘写满
4. 仍不够 → **退到 HVG 子集**（3000~5000），并在交付里**如实标注该折衷**

### 定容算术

| 项 | 公式 | 2132×17824 float32 实例 |
|---|---|---|
| 表达矩阵本体 | `n_cells × n_genes × 4B` | 152 MB |
| `_infer_data` 单份 | `n_cells × n_TF × 4B` | 13.8 MB（TF=1620） |
| 每 worker 峰值 | 矩阵副本 + 并发 task × infer 矩阵 | ≈ 0.5–1.5 GB |
| 建议 worker 数 | `⌊commit 余量 × 0.5 / 每worker峰值⌋` | 余量 9.2 GB ⇒ **2~4** |

⚠️ HVG **不会**缩小 `(n_cells × n_TF)` 那个矩阵（宽度只由 TF 数决定），它降低的是矩阵本体与下游 AUCell 的占用。

## 5. ⛔ 不要为了腾内存去杀进程树（本会话最贵的一次错）

**实测**：`python.exe`（1.41 GB）挂着 7 个 `Rscript.exe` 子进程，其 **PPID 已不存在**
→ 看着就是"孤儿进程树" → 杀掉 → **terminal 回执 `exit 15`、零输出**，重试仍是 15。
原因：那个 `python.exe` 是**活跃的 MemOmics server**，其 Rscript 子进程是 **kernel 池的正常 worker**；
杀掉 server 的进程树 = 把自己所在的命令链一起 SIGTERM。

三条铁律：
1. **PPID 已不存在 ≠ 可杀**。server / kernel 池的父启动器常已退出，但本体仍正常服务。
2. **MemOmics server + kernel 池常驻 ~10 GB 属正常占用**，不是残留垃圾——
   内存诊断里看到它们占大头，不要当成"可以回收的空间"。
3. 动手前先查 CommandLine：
   `powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter 'ProcessId=<pid>' | Select-Object ProcessId,Name,CommandLine,CreationDate | Format-List"`
   判据：命令行含 `_kernel_worker.py` / `_kernel_worker.R` / `webui/server.py` ⇒ **平台基础设施，绝不杀**。

🔑 **判据：回执 `exit 15` + 零输出 ⇒ 命令很可能被自己动的进程树带走了。**

正确方向是 **降任务自身需求**（worker 数 / memory_limit / HVG / float32 / 释放 kernel 大对象），
而不是回收平台基础设施。

## 6. 附带坑：`taskkill` 在 MSYS bash 下不可用

```bash
taskkill //F //T //PID 60728
# → 无效参数/选项 - '//F'      （MSYS 把 //X 吃掉/转换，进程一个没杀）
```
杀进程树改用 psutil（也能顺带打印每棵子树的 RSS）：
```python
import psutil
proc = psutil.Process(pid)
for ch in proc.children(recursive=True):
    ch.kill()
proc.kill()
```
`scripts/check_commit_memory.py --kill-tree <pid>` 即封装了这一路径。

## 7. 附带坑：`patch` 工具会**归一化 `.py` 的缩进**

给缩进敏感的 `.py` 插代码时，`patch(mode='replace')` 会按 old_string 首行重新对齐 `new_string`，
插入块整体多/少 4 空格 → `IndentationError: unexpected indent`，**且再 patch 一次修不回来**（越改越乱）。

处置优先级：
1. **`execute_code` 行级编辑**：`lines = src.splitlines(True)` → 按内容定位起止行 → `lines[start:end+1] = [新块]` → `''.join()` 写回 → **`py_compile.compile(p, doraise=True)` 自校验**
2. 整文件结构已知 → 直接 `write_file` 重写
3. 非要用 `patch` → old_string/new_string **每一行都写全缩进**（含首行），别让工具推断

⚠️ `patch` 返回 `success: true` **不代表缩进正确** —— 改完 `.py`/`.R` 必须做一次语法校验。
（同族：本 skill 坑表里的「patch 静默丢行」「patch 从标签中间命中」两行。）

## 8. worker 被杀 → 上层报 `cancelled` futures（§2/§3 的下游表现）

真机（2026-09-24，pySCENIC `prune2df` 的 dask distributed 路径）：

```
distributed.client.FutureCancelledError: finalize-<hash> cancelled for reason: unknown
  prune.py:424 prune2df → prune.py:362 _distributed_calc
  → client.compute(create_graph(client), sync=True) → client.gather(futures) → raise
```

traceback **之前**的先兆行（容易被日志淹没，务必往上翻）：

```
(stimulus_id='handle-worker-cleanup-1790252714.057847')
```

含义：**worker 进程在 compute 期间死亡/被回收** ⇒ 依赖它的 future 全部 cancelled ⇒ 在 gather 处抛错。
根因就落在 §2（commit 触顶）与 §3（`memory_limit` 设小值）上——**"cancelled for reason: unknown" 是症状，不是待查的原因**，
别照着报错文本去搜"为什么 future 会被取消"。

### 处置顺序（⛔ 不要原样重试同一调用）

1. **收尸**：列进程清孤儿 worker（psutil，见 §6）；先查 CommandLine，⛔ 不碰 `_kernel_worker.*` / `server.py`（§5）
2. **查资源**：commit 余量探针（§2）；`>85%` ⇒ 先降任务需求再重跑
3. **降并发 / 放开限制**：worker 数下调，`memory_limit=0`（§4 配方）
4. **只补跑失败的那一步**：GRNBoost2 的 `adjacencies` 这类**昂贵且可复用**的中间产物必须先落盘，
   prune / AUCell 失败一律"从表读起"重算该层，**绝不连带重烧上游**（否则一个 worker 死亡吃掉几小时）

### 同源教训：拿到"成功"输出先验结构，再往下接

"上一步成功" ≠ "输出的结构对"。关键列在下游使用前先打一行 dtype / 形状：

- 实测：pySCENIC 0.12.1 `prune2df`（dask 聚合路径）返回的 `TargetGenes` 列是
  **字符串** `"GENE1;GENE2;GENE3"` 而非 list ⇒ 用它构造的 regulon 在 AUCell 里失效，
  错误直到**三步之后**才以完全无关的报错形式爆出。
- 命中脏结构的正确姿势：**解析 + 重建该层**（解析字符串 → 重建 regulon 对象 → 重算 AUCell），
  **不要重跑上游**（最贵的一步不该为一个下游可修的问题买单）。

📄 完整取证（调用栈、调度路径对比表、长任务包装器用法、TargetGenes 恢复步骤）→
`windows-bioinformatics-batch-processing/references/worker-death-cancelled-futures-windows.md`