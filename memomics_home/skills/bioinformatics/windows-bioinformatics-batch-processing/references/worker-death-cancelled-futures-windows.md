# Windows 上"worker 被系统杀掉"型崩溃：识别、收尸、只补跑失败步骤

> 真机取证 2026-09-24（pySCENIC prune2df，本机 Python 3.12 / dask distributed）。
> 适用于**任何多进程 worker 架构**的长任务：dask distributed、joblib、multiprocessing、
> arboreto GRNBoost2、pySCENIC prune2df/AUCell。核心逻辑与具体库无关。

---

## 1. 症状签名：上层报 cancelled，真因在下层被杀

典型报错（dask distributed 家族）：

```
distributed.client.FutureCancelledError: finalize-<hash> cancelled for reason: unknown
```

调用栈通常长这样（pySCENIC 0.12.1 实例）：

```
pyscenic/prune.py:424  prune2df → _distributed_calc
pyscenic/prune.py:362  return client.compute(create_graph(client), sync=True)
distributed/client.py  compute → gather → raise
```

**关键识别点**：刷在报错之前的 stdout 里往往有一行**先兆**，别被日志淹没：

```
(stimulus_id='handle-worker-cleanup-1790252714.057847')     ← worker 被回收/死亡
```

含义：**worker 进程在 compute 期间死掉 → 依赖它的 future 全部 cancelled → 在 gather 处抛错**。
报错文本（"cancelled for reason: unknown"）只是下游症状，**不要照着文本去搜"为什么 future 被取消"**，
要顺着 worker 为什么死去找。

Windows 上按概率排序的诱因（逐个实测排除，别直接下结论）：

| 诱因 | 特征 |
|---|---|
| **commit charge / pagefile 耗尽** | 常伴随 `WinError 1455 页面文件太小`；worker 被 Windows 直接终止 |
| **孤儿 worker / 上轮残留 python 进程抢占内存** | 本机并发跑过其他分析（或上一轮任务半死）时高发 |
| 传了**外部 client** 且在调用链中途被关闭 | 自己建 client 又交给库内部复用/关闭的写法 |
| 并发度过高 | `num_workers` 按 `os.cpu_count()` 默认值起 → 单机峰值内存爆炸 |

---

## 2. 恢复顺序（⛔ 铁律：不要原样重试）

原样重试 = 把最贵的一步再烧一遍，且大概率同样死在同一个地方。固定顺序：

```
① 收尸   列进程 → 清理孤儿 python/dask worker → 确认只剩当前任务
         Windows: tasklist / wmic process get name,ProcessId,WorkingSetSize  （bash 下可用 tasklist）
② 查资源 pagefile 大小 + commit charge + 当前可用物理内存
③ 降并发 num_workers 从 2 起步；或换到"库默认调度族"而不是自造进程池
④ 只补跑失败的那一步 —— 复用已落盘的中间产物，见 §3
```

调度路径选择的历史教训（同一机上连续踩过，勿重复）：

| 调度路径 | 结果 |
|---|---|
| 自定义 multiprocessing 路径 | Windows `spawn` 崩溃：`BaseProcess._bootstrap() takes 1 positional argument but 2 were given` |
| 不传 client/地址，用库默认 | 按 `os.cpu_count()` 起 worker → MemoryError / BrokenProcessPool |
| 显式低并发（如 `num_workers=2`）+ 库默认调度族 | 可用基线；再触发 worker 死亡就回到 ①②③ |

---

## 3. 铁律：昂贵中间产物必须先落盘（失败才便宜）

判断某一个步骤"失败后代价多大"的标准只有一个：**它能否从已落盘的表/矩阵重算**。

- 管线里**最贵且可复用**的那一步（如 GRNBoost2 的 adjacencies、CellBender 的 cleaned h5、
  降维后的 embedding），一跑完**立刻落盘成 CSV/TSV/h5**，后续步骤一律"从它读起"；
- 下游步骤（剪枝、打分、统计、出图）失败 → **只重跑下游**，绝不连带重烧上游；
- 反模式：脚本设计成"一步错、全流程从头再来"，一个 worker 死亡就吃掉几小时。

## 4. 拿到"成功"输出先验结构，再往下接分析

本次真机同源教训：pySCENIC 0.12.1 的 `prune2df`（dask 聚合路径）返回的 `TargetGenes` 列
可能是**字符串** `"GENE1;GENE2;GENE3"` 而不是下游期望的 list —— 用它构造的 regulon 对象
在 AUCell 里失效，错误直到三步之后才以无关报错爆出来。

**规程**：任何工具产出的关键列/结构，在写下游代码前**先验 dtype 和形状**
（一行 `df.dtypes` / `type(x)` 打印即可），不要假设"上一步成功了，结构就一定对"。
命中脏结构时的正确姿势是**解析+重建**（解析字符串 → 重建对象 → 重算该层），
而不是回头重跑上游。

---

## 5. 长任务包装与日志（与本 skill 铁规配合）

dask/SCENIC 这类 >60s 任务用统一包装器起，别 `start /b` 裸跑：

```bash
python memomics/bio_tools/task_run.py --type scenic --title "SCENIC: prune+AUCell" \
  --session-dir results/<sid> --stages "读入,剪枝,解析,重建,AUCell,出图" \
  --script results/<sid>/scripts/<step>.py \
  -- "C:/.../python.exe" -u results/<sid>/scripts/<step>.py
```

- 脚本内 `print("#TASK:STAGE …")` / `print("#TASK:PROGRESS 0.4 …")` 打点（任何语言可用）；
- 失败详情在 `results/<sid>/log/<type>-<ts>.log`：**先读日志尾部拿到真实调用栈+先兆行**，
  再决定收尸还是改代码；只看"exit code 1"会误判。