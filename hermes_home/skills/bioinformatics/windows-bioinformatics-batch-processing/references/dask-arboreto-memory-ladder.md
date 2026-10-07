# Windows 重内存 Python 生信任务：dask / arboreto 内存阶梯

> 来源：2026-09-24 pySCENIC GRNBoost2（人骨骼肌 MF_2000，2,132 nuclei × 27,090 genes）实测。
> 症状在**任何**用 `dask.distributed` 或 `arboreto` 的 Windows 任务里都同形（GRNBoost2 / scvi-tools / 自建 dask pipeline），
> 不限于 pySCENIC。本文只讲**执行层**（内存预算、进程归属、判活），SCENIC 方法学本体见 `grn-pyscenic`。

---

## 1. 症状长什么样

```
'WARNING: infer_data failed for target ZFX'      Retry (3/10). Failure caused by MemoryError((2132, 1619), dtype('float32'))
'WARNING: infer_data failed for target ZNF559'   Retry (4/10). Failure caused by MemoryError((2132, 1619), dtype('float32'))
... 每个 target 重试到 10/10 → 整批失败
```

三个可辨识特征：

1. shape 是 **`(n_cells, n_TFs)`** 而不是 `(n_cells, n_genes)` —— 说明崩在 arboreto 的 **per-target** 建模阶段；
2. **每个 target 都独立报错并重试** —— 不是"一次大分配失败"，是每个 target 都要新建一份中间矩阵、累积把内存吃干；
3. float32 + 只有 1,619 列却报 MemoryError ⇒ **物理内存/提交上限到了，不是这个矩阵本身太大**（2,132×1,619×4 B ≈ 13.8 MB）。

## 2. 根因阶梯（按实测顺序，别跳级）

| # | 根因 | 判据 / 证据 |
|---|------|------------|
| ① | `arboreto.grnboost2` 默认 `client_or_address='local'` → 起 `LocalCluster(n_workers=os.cpu_count())`，**每个 worker 持一份完整表达矩阵** | 20 核机器 = 20 份矩阵；本机 2,132×27,090 float32 ≈ 231 MB/份 → 光矩阵就 >4.6 GB，再加 dask 中间数组 |
| ② | 给 worker 设了 `memory_limit` ⇒ dask **主动抛 MemoryError**（假性 OOM） | `memory_limit='6GB'` / 默认 auto(≈2.4 GB/worker) 都触发；`memory_limit=0`（不限）才是正解 |
| ③ | 降 worker 数（20→6→4→2）**只延后不解决** | 因为 ② 的假性上限仍在小 worker 上先命中 |
| ④ | Windows **提交上限**（RAM + pagefile）是硬顶，任务管理器里的"可用内存"就是它 | WinError 1455「页面文件太小，无法完成操作」= commit charge 打满 |
| ⑤ | **孤儿进程白占内存** | 本机实测：4 个残留 Rscript/python 内核共占 ~9.6 GB，跑前没清 |

## 3. 正解（按优先级）

### 3.1 显式建受限集群 + 把 client 传进去（关键）

```python
from dask.distributed import Client, LocalCluster

cluster = LocalCluster(
    n_workers=4,              # 按 commit 余量定，先小后大
    threads_per_worker=1,
    memory_limit=0,           # 🔴 必须 0（不限）。任何 per-worker 上限都会变成假性 MemoryError
    dashboard_address=None,   # 少一个端口/一个进程
    silence_logs=40,
)
client = Client(cluster)
...
run_complete_grn_workflow(..., client_or_address=client)   # ← 复用同一个受控集群
```

⚠️ `client_or_address` **不是 pySCENIC 官方参数** —— 是 MemOmics 给
`hermes_home/skills/bioinformatics/grn-pyscenic/scripts/run_grn_workflow.py`
补的可选参数（末位、默认 `None`，不传时行为与原来完全一致）。
若该参数不在（skill 被重装/回滚），先在 skill 脚本里补：签名末位加 `client_or_address=None`，
`grnboost2(...)` 调用处 `**({"client_or_address": client_or_address} if client_or_address is not None else {})`。

### 3.2 表达矩阵先切 HVG（降一个数量级）

全基因（27 k）→ **HVG 3000** 时，内存需求约降 **6×**，且 GRNBoost2 的输入语义不变（它本就只该喂高变基因）。
判据：**先切 HVG 再谈 worker 数** —— 27 k 基因在 9 GB 可用内存的机器上不该硬跑。

### 3.3 跑前必做：清孤儿 + 量提交余量

```bash
# 量 commit 余量（Windows；wmic 在 Win11 已移除，用 CIM）
powershell -NoProfile -Command "Get-CimInstance Win32_OperatingSystem | Select-Object TotalVirtualMemorySize,FreeVirtualMemory | Format-List"
```

```python
# 列候选孤儿：区分「持久内核 worker」与「真任务」（判据见 platform-execution-pitfalls 坑表首行）
#   _kernel_worker.py / _kernel_worker.R  ⇒ 内核 worker，按设计空闲待命，绝不杀
#   Rscript xxx.R / python xxx.py          ⇒ 业务进程，可清
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"ProcessId=<pid>\" | Select-Object ProcessId,Name,CommandLine,CreationDate | Format-List"
```

⛔ **杀任何 PID 前必须先看 `CommandLine`**（platform-execution-pitfalls 有完整的同形坑）。

### 3.4 明确"不要做"的事

| 做法 | 结果 |
|------|------|
| 原样重跑（不改参数） | 每个 target 重试 10 次全灭 → 整批失败，纯烧时间 |
| 只把 `n_workers` 往下调 | 见根因 ②，假性 OOM 先命中 |
| 给 worker 设 `memory_limit='6GB'` 之类的"保护" | **反而主动制造** MemoryError |
| 缩短重试次数"让它快点失败" | 失败是确定的，只是把已知失败提前 |

## 4. 写脚本前先做 API/版本审计（同族纪律）

照文档假定的版本硬写 = 执行阶段才炸、白烧轮次。本会话实撞两例：

| 库 | 文档/旧写法 | 实测（本机版本） |
|----|------------|-----------------|
| ctxcore | `set(db.column_names)`（旧教程 / 本 skill 早期版本） | **ctxcore 0.2.0 无此属性** → `AttributeError: 'FeatherRankingDatabase' object has no attribute 'column_names'`；正确 = **`set(db.genes)`**（tuple，hg38 10k db = 27,090 HGNC 符号）。0.2.0 公开属性 = `ct_db/genes/geneset/load/load_full/name/total_genes` |
| arboreto | `from arboreto.algo import run_grnboost2` | 函数名是 **`grnboost2`** |
| pyscenic 依赖 | — | setuptools ≥81/83 不再默认捆绑 `pkg_resources` → `import ctxcore` 即 `ModuleNotFoundError`。**先换解释器**（本机 System Python312 的 pyscenic 0.12.1 + ctxcore 0.2.0 + arboreto 全通），不要往函数环境灌包 |

一次调用打印全部签名（放进任何分析脚本开头都值）：

```python
import inspect
from ctxcore.rnkdb import FeatherRankingDatabase
print([a for a in dir(FeatherRankingDatabase) if not a.startswith("_")])
import arboreto.algo as A
print([f for f in dir(A) if "grn" in f.lower()])
```

## 5. 判"跑完了"而不是"exit 0"

长任务一律用杀哨兵 + 产物双判据，**不看 exit code**（管道会吞）：

```bash
python -u 02_run_scenic.py > log/scenic_run.log 2>&1   # 用重定向，别 | tee
echo "exit=$?"
grep -c "DONE_SCENIC" log/scenic_run.log               # 哨兵
ls -la data/scenic/                                    # 产物：adjacencies.csv / regulons.csv / aucell_matrix.csv
```

## 6. 启动前检查清单

- [ ] 表达矩阵已切 HVG（全基因不用想）
- [ ] `memory_limit=0`，`n_workers` 按 commit 余量定（宁小勿大，跑得慢好过跑不成）
- [ ] `client_or_address=client` 已传入 workflow
- [ ] commit 余量实测 > 预估峰值；不等就先清孤儿/关桌面重应用/pagefile 迁盘
- [ ] 日志走重定向（不接管道），脚本末尾有完成哨兵
- [ ] 长任务走 `task_run.py` 包装器（WebUI ⏱ 任务面板可见、可取消）