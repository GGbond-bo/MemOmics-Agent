# 长任务内存调优与 spawn 失败分诊（dask / multiprocessing 实战）

> 来源：2026-09-24 在 Windows 上跑 pySCENIC（2132 nuclei）连吃 6 次失败后的实测定位。
> 通用性：任何**基于 dask / multiprocessing 的批量长任务**（SCENIC、arboreto、sklearn 并行、bigWig 批处理）都适用。

---

## 1. 内存不是「物理 RAM 够不够」，而是 **commit 余量**

**症状**：`MemoryError((2132, 1619), dtype('float32'))` —— 才 13.8 MB 的数组分配失败，
而 `psutil.virtual_memory()` 显示还有 13 GB 可用。

**根因**：Windows 可提交内存 = 物理 RAM + pagefile。实测该机 `CommitTotal 76.6 / CommitLimit 86.5 GB`（88.5%）、
`CommitPeak` 已触顶 ⇒ **余量只剩 9.2 GB 时，再小的分配也会失败**。同类报错还有 `WinError 1455 页面文件太小`。

**处置**：动手前先查 commit 余量（`platform-execution-pitfalls` 的 `scripts/check_commit_memory.py`），`>85%` 就先降任务需求。
⛔ 不要把它当「物理内存不足」去白减细胞数 / 基因数。

**附属坑**：`wmic` 在 Win11 已移除，查不了内存；`tasklist //FI`、`taskkill //F` 在 MSYS bash 下开关被当路径吃掉 →
杀进程树一律用 **psutil**（`Process(pid).children(recursive=True)` 逐个 kill，再 kill 父）。

---

## 2. dask 的三个反直觉行为（每个都踩过）

| 行为 | 实测表现 | 处置 |
|------|----------|------|
| **`memory_limit` 主动抛 MemoryError** | 设 `"6GB"` 与默认 `auto`（20 核 ≈2.4 GB/worker）**都**让 `infer_data` 刷 MemoryError 并 `Retry (10/10)` 后放弃 —— 不是 spill、不是警告 | **`memory_limit=0`（不限制）**。设小值 = 自毁 |
| **默认起满 CPU 数 worker** | `arboreto.grnboost2` 默认 `client_or_address='local'` → `LocalCluster(n_workers=os.cpu_count())`，**每 worker 持一份完整输入副本**；20 核机 = 20 份 | 显式建 `LocalCluster(n_workers=2~4, threads_per_worker=1, memory_limit=0)` 并**把 client 透传给分析函数** |
| **库函数内部自己有默认调度器** | `pyscenic.prune.prune2df` 默认 `client_or_address="dask_multiprocessing"` → `.compute(scheduler="processes", num_workers=num_workers or cpu_count())`（源码 `prune.py:349-354` 验证）→ 每个 worker 各加载一份 311 MB ranking DB → worker 被 OOM 杀 → `BrokenProcessPool: A process in the process pool was terminated abruptly` | **凡库函数带 `client_or_address` / `num_workers` 参数，一律显式传值**，不要依赖默认 |

🔑 **判据**：报 `BrokenProcessPool` / `A process in the process pool was terminated abruptly` ⇒
**先数 worker 数 × 每 worker 的数据副本大小**，而不是先去改算法或减数据。

> 萎缩/降内存的杠杆排序：**缩输入子集（最大）> 减 worker 数 > `memory_limit=0` > float32 > 临时目录换盘**。
> 实测：把 GRN 推断的 target 数从 17824 收到 3650（HVG∪TF），dask graph 由 153 MiB → 31.6 MiB，
> 原本 4 次必失败的任务一次跑通（550 s）。

---

## 3. multiprocessing spawn 崩溃分诊（**未解决，如实标注**）

**症状**
```
File "<string>", line 1, in <module>
File ".../multiprocessing/spawn.py", line 135, in _main
    return self._bootstrap(parent_sentinel)
TypeError: BaseProcess._bootstrap() takes 1 positional argument but 2 were given
```

**已验证的关键事实**：该错在**两条互不相干的路径下都复现** ——
① 库自带的 `multiprocessing.Process` 子类（pyscenic 的 `prune.Worker`）；
② dask 自己的 `scheduler="processes"` 调度器。
⇒ **不是某个库的 bug**，是本机 `multiprocessing` spawn 状态/版本混配的普遍问题
（子进程 `__main__` 显示为 `File "<string>"`，指向 spawn 重执行父模块的机制）。
报错文本形如「`X` takes 1 positional argument but 2 were given」且指向 `spawn.py::_bootstrap`
⇒ 就是这一族，**不要**去改业务脚本或怀疑业务代码。

**父母进程会挂住**：worker 已死但任务仍 `status=running`、heartbeat 正常 → 必须主动 psutil 杀树。
（连带坑：管道 `| tee` 会吞掉非零退出码，回执写 `completed normally (exit code 0)` 却其实早崩了 ——
判活永远看「日志完成哨兵 + 产物落盘」，不看 exit code。）

**未验证的候选方向**（按序试，标注清楚别当结论）：
1. `python -c "import multiprocessing; print(multiprocessing.__file__)"` 查是否有旧版包遮蔽 stdlib；
2. 查 `sitecustomize` 是否改动了 `BaseProcess`（本机 sitecustomize 有 torch 补丁）；
3. 完全绕开 multiprocessing：单进程串行执行，或换 dask 的 distributed 客户端而非 processes 调度器。

⛔ **交付口径**：写「该阶段在本机被 multiprocessing spawn 环境问题阻断」，
**不要**写成「XX 工具不能用 / 跑不通」——同一条链上前面的阶段其实是成功的。

---

## 4. 「在算」还是「挂了」：用 psutil 区间采样，不要反复 tail

dask/arboreto 的**计算期完全不打印进度**，日志长时间零增长是**正常**的，
与「死锁」在表面指标上同形。判活要**主动取 CPU 证据**：

```python
import psutil, time
p = psutil.Process(PID)
fam = [p] + p.children(recursive=True)
for x in fam:
    x.cpu_percent(None)          # ← 必须先「预热」一次：首次调用一律返回 0.0（无参照系）
time.sleep(6)
tot = 0.0
for x in fam:
    tot += x.cpu_percent(None)   # ← 第二次才是区间内真实占用
    print(x.pid, x.name(), x.memory_info().rss / 1024**3)
print("进程树 CPU 合计 =", tot)     # 持续 >50% = 真在计算
```
⚠️ **不预热直接读 `cpu_percent()` 会得到一片 0.0**，据此判「挂了」是误判（本次差点踩）。
实测健康态：2 个 worker 各 ~95%，进程树合计 199.5%。

---

## 5. 断点续跑：把耗时步骤的产物当检查点

- 长任务的**第一步往往是最慢的**（GRNBoost2 9 min、CellBender 数小时）→ 给它的产物加「复用」开关：
  `if resume and os.path.exists(step1_out): load(step1_out) else: run_step1()`
- 续跑时**不要再建已经不需要的资源**（本次续跑仍建 dask 集群 = 白白多占 ~2.5 GB）。
- 落盘**输入子集/参数快照**（如 `gene_subset_hvg_tf.txt`）→ 既是复跑依据，也是交付溯源。
- 失败重试前先确认「上一步产物是否真的完好」（`ls -l` 看字节数），别盲目从头跑。

---

## 6. 收尾：交付里必须写清的局限

失败/降级过的长任务，报告里要**主动列局限**，不要含糊成「分析完成」：
1. 输入被缩过（如 GRN 基于 HVG∪TF 子集而非全基因）→ 说明影响方向与不影响的部分；
2. 与官方推荐配置的差异（如官方推荐多库混用、本次单库）；
3. **未跑通的阶段 + 根因 + 未验证的修复方向**，与已成功阶段分开陈述。