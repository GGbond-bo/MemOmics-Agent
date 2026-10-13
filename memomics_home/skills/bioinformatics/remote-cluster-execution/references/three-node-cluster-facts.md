# node1 / ssh0 / ssh23 —— 三节点规格、外网、环境分工（实测 2026-10-08）

> 唯一真源：`<安装目录>/environment.json` 的 `cluster` 段（用户锁定，持久声明、**不被探针重扫覆盖**）。
> 本文件是它的人读版 + 探针原始证据、安装链与验证配方；两者冲突以 `environment.json` 为准。
> 新会话要连集群：先读 `environment.json.cluster`，**不要重新探测**。

## 1. 节点表（config.yaml `remote.nodes` 登记 + 实测）

| name | host | 角色 | 核 | 内存 | 外网 | 备注 |
|---|---|---|---|---|---|---|
| `node1` | `login-host.login-host` | **default_node** / 大内存 | 144 | 3.0 TB | ❌ | 超大内存任务（10x 全量、ArchR、大矩阵） |
| `ssh23` | `compute-node.login-host` | 计算节点 | 112 | 503 GB（MemTotal 528,067,776 kB ≈ 503.6 GiB，可用 495 GiB） | ❌ | Xeon E7-4830 v4 @2.0GHz（主频低 → 单线程弱，适合多核并行）；本地 `/` 407G（余 379G）、`/tmp` **仅 24G**、`/home` 1.0T（共享，已用 667G） |
| `ssh0` | `cngb-software-0-1.login-host` | **安装节点** | 8 | 15.5 GB | ✅ | 唯一能上外网；只用来装包 / 下载 / 轻量脚本，⛔ 不跑重计算 |

共用：user=`user`、port=22、home=`/home/user`、workdir=`/cluster/share/user`（**三节点 realpath 一致**）。
config.yaml 里 ssh23 的 note 写「小内存节点」是相对 node1 的 3TB 而言，503 GB 实测并不小。

## 2. 共享存储 / 队列 / 选点行为

- 挂载：`cluster.login-host:/share → /cluster/share`，**三节点同一份 NFS**：120T 总 / 97T 已用 / **24T 可用（81%）**，全实验室共享 → 写大矩阵/BAM/索引前留意配额。
- 调度器：三节点同为 **SGE 8.1.9**（`/opt/gridengine/bin/lx-amd64/{qsub,qstat,qdel}`，无 Slurm）→ **同一套队列**。
- ⇒ **三个登录口只是入口不同，不是三个独立算力池**：别按登录口分配任务、别跨节点搬文件；真决定作业跑在哪台的是调度器。
- 选点：`default_node=node1`、`node_policy=ask`。只配 1 个 → 静默用；配多个未指定 → 用 default（node1）；**没配 default 才会返回 `needs_node` 硬拦**（那时必须先问用户，不许自己挑）。

## 3. 外网实测

| 目标 | ssh0 | node1 | ssh23 |
|---|:--:|:--:|:--:|
| baidu | 200 | 无响应 | 无响应 |
| pypi | 200 | — | — |
| codeload.github.com | 301 | — | — |

🔴 装包 / 下载数据 / 下参考基因组 **只能在 ssh0**；在 node1/ssh23 上 `pip install`、下载会直接卡死超时。

## 4. 环境可见性 + 工作/装包分工（用户 2026-10-08 澄清）

三节点可见环境清单**一字不差**：

- `zhangxiao6/software/miniconda3/envs` → 35 个（`R4.41` / `R4.3.3` / `ARCHR` / `sc-analysis` / `monocle3` / `scenic` …）
- 自有 `user/envs` → 只有 `R4.4.1_zb`（R 4.4.1 + Python 3.14.0）

| 角色 | 环境 | 规则 |
|---|---|---|
| **工作环境** | `R4.41`(RNA) / `R4.3.3`(ATAC) / `sc-analysis`(py) | 正常分析就用它；属主 zhangxiao6 → **只读，⛔ 禁止装包** |
| **装包环境** | `user/envs/R4.4.1_zb` | **只用来补装**映射环境缺的包 → 作业里 `export PATH=/cluster/share/user/envs/R4.4.1_zb/bin:$PATH` 引用 |

用户原话：「真正工作的是 RNA→R4.41 / ATAC→R4.3.3；`R4.4.1_zb` 这个只是用来装一些包的，以后装包可以在这里装，然后调用。因为真正工作的环境是 zhangxiao6 的，我不能随便在他这里安装包。正常工作在 zhangxiao 这里，缺少了一些分析包，在我自己这里安装。」

**安装链**：ssh0（有外网）装 → 落自有 env/库（在共享盘上） → node1/ssh23 立即可用。

## 5. 其它已验证的坑

- 三节点系统 PATH **都没有 `Rscript` / `python3`**（`which` 全 no），登录节点也无 module 系统 → 作业必须绝对路径调用或先 `activate`，否则 `command not found`。
- 环境名不可信：`envs/cellchat` 里没有 CellChat、`envs/monocle3` 里没有 monocle3（真包在 `R4.41`）→ 用前必须 `find.package()` / `find_spec()` 实测。
- `qstat` 在登录节点可能卡死（实测 3 分钟无响应）→ 别死等，加 timeout + 报实情。
- 中间文件写工作盘 `/cluster/...`，**别用 `/tmp`**（ssh23 只有 24G）。

## 6. 改 `environment.json` 后怎么验（三件套）

```bash
# ① JSON 结构断言 —— 改了哪节就断言哪节（lint only 说明语法，不证明语义）
.venv/Scripts/python.exe -c "import json;c=json.load(open('environment.json',encoding='utf-8'))['cluster'];print(sorted(c.keys()), list(c['nodes']))"
# ② 项目自带校验器 —— 该文件的权威检查
.venv/Scripts/python.exe scripts/validate_env.py --verbose        # 期望 [OK] All paths verified / exit 0
# ③ 全量 offline 套件 —— 证明没碰坏仓库其余部分
.venv/Scripts/python.exe -m pytest -q -m "not external and not network and not live_llm and not gpu and not ssh and not lab and not docker and not browser"
```

⚠️ 全库检索确认 `webui/`、`hermes-agent/` **都没有测试引用 `environment.json`** → 该文件无 pytest 覆盖，**`validate_env.py` 就是它的权威检查**；pytest 只用来证明无回归，不要因为「pytest 里没有针对它的用例」就以为无法验证。
⚠️ `pytest -q` 的汇总行会落在 warnings 块之后、易被 `tail` 截掉 → **以 `PYTEST_EXIT=0` 为判据**，别因为看不到 "N passed" 就重启一轮。