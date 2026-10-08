---
name: remote-cluster-execution
description: 远端 SSH 集群（SGE/Slurm/PBS）执行规程：环境清点、作业脚本、投递与产物回收。触发：集群/ssh3/用集群跑/在集群上跑/帮我看看集群/集群有哪些环境/集群环境/投递任务/qsub。
when_to_use: 任何要在远端集群上跑分析（remote_cluster 工具）之前的环境准备与执行。用户提到"集群/ssh 节点/云上算力/他把数据放集群上"时先加载本 skill。
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  memomics:
    tags: [remote-cluster, ssh, sge, slurm, conda-env, environment-inventory]
    difficulty: intermediate
    language: R+Python
    category: bioinformatics
---

# 远端集群执行规程（SSH + 调度器）

> 与 `dcs-cloud` 的区别：DCS 是华大云 Web/API 平台；本 skill 是 **SSH + 调度器**（remote_cluster 工具）的集群。

## 🔴 铁规 -1：先认清定位 —— 我是 API，不是终端（用户常拿 MobaXterm 比）

被问「你这远端集群怎么实现的 / 稳不稳 / 跟 MobaXterm 什么区别」时**不要凭印象答**：读源码后按固定骨架作答，
实现地图（逐行 file:line）+ 稳定性边界 + 对照表在
`skill_view("memomics-internals-qa", "references/remote-cluster-implementation.md")`。要点速记：

- 底层是**同一套 OpenSSH**（ssh/scp，共用 known_hosts/密钥/ProxyJump）；差别在服务对象——MobaXterm 给人
  （交互终端、密码登录、X11、手动 SFTP），remote_cluster 给 Agent（结构化 JSON、调度器感知、产物自动回传、门禁）。
- 因此**没有可手敲的终端**：排障只能靠 `status`/`logs` 回执；要现场改命令就切回 MobaXterm/Shell。
- 三个必须主动交代的固有边界：① `BatchMode=yes` → **只支持密钥登录**；② **无断线续跑队列**，长作业必须 `submit`；
  ③ 多节点没指定 → `needs_node` 硬拦（设计如此，不是故障）。
- 实现落点：`memomics/bio_tools/remote_cluster.py`（继承 memomics `SSHEnvironment`，只跳过 `~/.memomics` 同步）。

## 🔴 铁规 0：先清点环境，再写作业 — **环境名不可信，必须实测**

**这是本 skill 最重要的一条，来自 2026-10-08 ssh3 实测。**

- **conda env 目录名与实际包可以完全不符**：实测 `envs/cellchat` 里 `find.package("CellChat")` 为空（根本没装）；`envs/monocle3` 只有 14 个包、**没有 monocle3**；真正有 monocle3 的是 `R4.41`。按名字用 = 当场翻车。
- **用户口述的名字也会有偏差**：中文口述 "R441 / R443" → 磁盘上实际是 `R4.41` / `R4.3.3`（还有一个 `R4.2.2`）。**永远以 `ls envs/` 的真实输出为准**。
- 验证三件套（绝对路径调用，不依赖 activate）：
  ```bash
  M=<conda_root>
  ls -1 "$M/envs"                                  # ① 真实 env 名
  "$M/envs/<e>/bin/Rscript" -e 'print(.libPaths()); cat(as.character(find.package("PKG",quiet=TRUE)))'
  "$M/envs/<e>/bin/python" -c "import importlib.util as u; print(u.find_spec('mod'))"
  ```
  ⚠️ `requireNamespace()` / `find.package()` 返回空 = 该环境**真的没有**这个包，别因为目录叫这名就以为有。
  ⚠️ 同时看 `.libPaths()`：实测 `monocle3` 环境的 libPaths 指向 `~/R/x86_64-conda-linux-gnu-library/4.3`，说明包可能装在 env 之外，**一个环境的可用包 = env 内库 + libPaths 全部条目**。
- 一次跑完：`scripts/probe_cluster_envs.sh <conda_root> [pkgs...]`（列 env → 判类型+版本 → 关键包 → activate 测试）。

## 🔴 铁规 1：共享目录只读

别人的 conda 目录（`drwxr-xr-x`、属主他人）→ **能 source activate、能绝对路径调用，装不了包**。
要装包 → 自己 envs 下新建（`conda create -p ~/envs/<name>`），**不要在别人目录里 conda install**。
汇报时必须写清"只读可用"这个边界，否则用户会以为能往里装东西。

## 🔴 铁规 2：作业脚本必须显式定义解释器

集群系统级 `Rscript` / `python3` 常不在 PATH，裸跑直接 `command not found`（实测 ssh3 就是）。作业开头固定写：
```bash
source <conda_root>/bin/activate <env>      # 推荐
# 或 export PATH=<conda_root>/envs/<env>/bin:$PATH
```
投递前把这条写进脚本模板，别等报错再补。

## 🔴 铁规 3：探查是只读动作 —— 别问、别锁、别跑

用户说 **"先调查 / 帮我看看集群 / 集群有哪些环境"** 时：
- 直接跑只读探测（`remote_cluster action="run"` + `ls` / `--version` / `find.package`）—— 都是轻量命令，登录节点跑没问题，**不要**先弹确认表单；
- 交付**清单 + 按任务推荐**，但**不替用户锁定环境**。用户原话（2026-10-08）："你把 ssh3 能用的环境整理好，到时候固定使用哪个环境，**我会提前说明白**，先调查" → 调查类请求的交付物就是清单本身，锁定由用户拍板；
- 探测**不需要** rail_review(post) 的分析级口径（无图表产出，会被判 failed）——如实说明"口径不匹配、非分析任务"即可，不要补假产物。
- 反之，`submit` / `push` / `pull` / 真实分析属于高代价写操作 → 走铁律 35 意图确认。

## 🔴 铁规 4：路径与节点语义

- 本地路径（`E:/...`、`results/...`）与远端绝对路径（`/hwfssz3/...`）是**两套**，不能当同一个字符串混用。用户没说数据在哪 → 先 `remote_cluster action="locate"`，按 verdict（local/cluster/ambiguous/missing）决定在哪儿算；ambiguous/missing → 停手问用户，**不许自己挑、不许编路径**。
- 只配一个节点 → 直接用，不要多嘴问；配了多个且没给 node → 先问（或看 `action="nodes"` 的负载），除非配了 `default_node`。
- **产物分工**：大文件（BAM/FASTQ/中间矩阵/模型权重）留集群；表格/图/脚本/日志必须 `pull` 回 `results/<sid>/`，否则 WebUI 里看不到（WebUI 只浏览 work/ 和 results/）。

## 🔴 铁规 5：登录节点只跑轻量命令

`ls` / `head` / `which` / `--version` / `find.package` OK；重计算一律 `action="submit"`（SGE=`qsub`、Slurm=`sbatch`）。
调度器命令可能卡死：实测 `qstat` 在登录节点 3 分钟无响应 → **别死等**，加 timeout、报实情、给用户手动确认的建议。

## 🔴 铁规 6：探查**一次批量成一条命令**，不要分多轮

2026-10-08 实测教训：环境探查分了 3–4 轮 `action="run"`，每轮内容其实都不同，但**系统循环检测按"连续相似监控命令"判定为循环失控并强制干预**；同时铁律 24 的 terminal 门禁每轮都要求先 `record_run` 再 `rail_review`。

规避：
- **一轮把要查的全查完** —— 用 `scripts/probe_cluster_envs.sh <conda_root>`（列 env → 版本 → R 包 → Python 包 → activate 测试），或把多个 `echo "=== N. xxx ==="` 段落拼进**同一条**命令。
- 动手前先想清楚"这次探查要回答什么"，一次问完；不要"看一眼再决定下一眼看什么"。
- 已被判定循环时不要反复重试同类命令 —— 直接整理已有结果交付（多数情况信息已经够了）。

## 🔴 铁规 7：**用户锁定的环境映射是"持久声明"，不是探针缓存**（2026-10-08）

用户说"把环境信息补充到环境管理，以后新会话都能调用/补充/更新"时，落点**只有一个**：
`E:/MemOmics-Agent/environment.json` 的 `cluster` 段（可选再加 `env_notes`）。

- **为什么不能写进 `env_inventory` 缓存**：那是**探针自动生成**的（集群 10 分钟重扫、本机 1 小时），写进去会被下次重扫覆盖。分工是——探针答"**现在有什么**"，`environment.json` 答"**该用哪个、别碰哪些**"；后者是用户意图，必须持久。把声明塞进缓存 = 假装落库，下次会话就丢了。
- **新会话调用链**：读 `environment.json.cluster` → 拿节点 + 固定环境 + activate 命令 → `action="submit"`。实时负载/队列仍走 `env_inventory` 探针。
- **声明一旦落盘 → 只用声明的环境**：映射外的（含用户自己建、但没点名的）一律默认当不存在，要用先问。用户原话（2026-10-08）："**没有我的运行，不许使用陌生的环境**"。
- 改这份声明**只改指定项**，别顺手重排/润色别段（它是本机环境真源，`scripts/validate_env.py` 读它）。
- 机制细节（段 schema、`declared_env()`/`save_declared()`、WebUI 填写入口）见 `references/environment-declaration.md`。

## 🔴 铁规 8：三个登录口 ≠ 三个算力池；装包只有 `ssh0` 能上网（2026-10-08 实测）

| 节点 | 角色 | 规格 | 外网 |
|---|---|---|---|
| `ssh3` | **default_node** / 大内存 | 144 核 / 3.0 TB | ❌ |
| `ssh23` | 计算节点（常空，重活首选） | 112 核 / 503 GB（本地 `/tmp` **仅 24G**） | ❌ |
| `ssh0` | **安装节点** | 8 核 / 15.5 GB | ✅（唯一） |

- 三节点挂**同一份 NFS**（`hwfssz3.cngb.sz.hpc:/PS_JLU → /hwfssz3/PS_JLU`，120T / 余 24T / 81% 已用）+ **同一套 SGE 8.1.9**，工作路径 realpath 均 `/hwfssz3/PS_JLU/zhangbo`，可见环境一字不差 → **真决定跑在哪台的是调度器，不是登录口**：别按登录口分配任务、别跨节点搬文件。
- 🔴 装包 / 下数据 / 下参考基因组**只能在 `ssh0`**（其余节点无外网，`pip install`、下载会卡死超时）；装到共享盘后 `ssh3`/`ssh23` 立即可读。
- 中间文件写工作盘 `/hwfssz3/...`，**别用 `/tmp`**。
- 全表（含主机名、选点行为 `default_node=ssh3` / `node_policy=ask`）、工作/装包环境分工、改 `environment.json` 后的验证三件套 → `references/three-node-cluster-facts.md`。

## 🔴 铁规 9：长任务 = **一个作业跑完整链 + 检查点**，不要拆成一堆小作业（2026-10-08 用户拍板方案 A）

用户原话：「我要跑长程任务的时候，我总不能每次都读取一次吧？而且我这个才 600M，我的 MF 可是有 10G，
难道你也要每次读一下？」

- **被罚的不是「进程不持久」，而是把一条链拆成 n 个小作业** → 大输入被读 n 次。所以：
  ① 一个作业跑完整条链（大输入只 `readRDS` 一次）；② 读完立刻落**精简缓存**
  （reductions + meta ≈ 原文件 5%，丢稀疏矩阵）；③ 每个阶段落**检查点 + 参数指纹**，指纹一致就跳过。
- 模板（直接用，别重写）：`scripts/checkpoint_job.R`（三段式 + `tools::md5sum` 指纹，只用 base R）
  + `scripts/run_cluster_job.sh`（显式 PATH 的投递包装、日志落 `$WORKDIR/log/`、`#TASK:` 打点）。
- 语义：**同参数重投 → 跳过已完成阶段；改参数 → 只重跑受影响阶段；大输入不再重读**。
- ⚠️ 常驻 R 会话（`qlogin`/`qrsh`/Rserve/screen）**能但别默认用**：一直占核与内存、节点被清场即全丢、
  受 walltime 限制。只有「真·交互式反复调参」才值得，代价必须先跟用户讲清。
- ⚠️ 缓存只留 reductions+meta → **需要重算表达量的步骤仍回原文件**；检查点指纹只覆盖显式参数
  （脚本内硬编码常量改了要手动 `rm ckpt/<stage>.done`）。

## 🔴 铁规 10：读 ≥100MB 输入前**必须弹窗问持久化**，并落任务标记（2026-10-08 用户要求）

用户原话：「检测到执行读取数据分析，弹窗询问用户要不要持久化，**大于 100M 的内容，都要推荐持久化**。
比如 RDS、h5ad，一些超大表格也是一样，并**做好任务标记，方便清理**。」

流程（固定三步，不许跳）：
1. `python -m memomics.bio_tools.large_cache scan <输入路径...> --json` → 看 `recommend`；
2. `recommend` 非空 → **`ask_user(kind="intent", multi_select=true)` 弹窗**问要不要持久化
   （≥100MB 才推荐；低于阈值**不打扰用户**，600MB 重读一次不到 40 秒）；用户答复后再动手；
3. `mark` 落标记（`--input` / `--cache-root` / `--artifact` / `--remote` / `--ttl-days`），
   收尾用 `list` / `verify` / `clean` 管账。

**清理三道闸（删错比不删贵）**：① artifacts 命中原始输入 → 拒绝（原始数据永不删）；
② 产物必须在声明的 `cache_root` 内，未声明则整体拒绝（不猜范围）；③ 默认 dry-run，加 `--yes` 才真删；
④ **远端产物只打印 `rm -rf` 命令**（由 `remote_cluster run` 执行），不在本机假装删除；⑤ 清理后标记留痕
（`status=cleaned`），不物理删。

机制全表（schema / 阈值 / 估算口径 / 诚实边界）→ `references/large-input-cache-and-checkpoint.md`。

## 探查/执行速查

| 目的 | 动作 |
|---|---|
| 摸环境 | `action="run"` + `scripts/probe_cluster_envs.sh <conda_root>` |
| 大输入该不该持久化 | `python -m memomics.bio_tools.large_cache scan <路径> --json` |
| 长任务投递（读一次+检查点） | `scripts/run_cluster_job.sh <INPUT> <WORKDIR>` → `action="submit"` |
| 标记管账/清理 | `large_cache list|verify|clean [--yes]` |
| 数据在哪儿 | `action="locate" path="<用户原话路径>"` |
| 节点连通/负载 | `action="nodes"` |
| 跑重活 | `action="submit"`（先 `action="check"` 摸调度器/资源） |
| 看进度 | `action="status"` / `logs` |
| 收产物 | `action="pull"`（注意体积闸门，超限先问用户） |

## 已知集群清单（实测记录）

- `references/ssh3-zhangbo-inventory.md` — ssh3（CNGB 深圳超算，SGE 8.1.9）环境实测清单：R4.41 / R4.3.3 / ARCHR / sc-analysis / scenic 等，含每个环境的真实包内容与推荐映射。
- `references/environment-declaration.md` — 环境声明的机制：`environment.json` 的 `cluster` 段 schema、`declared_env()` / `save_declared()`、WebUI「🧩 环境管理」填写入口与 `POST /api/env/declared`。
- `references/three-node-cluster-facts.md` — 三节点（`ssh3`/`ssh0`/`ssh23`）规格与外网矩阵、共享 NFS + 同一套 SGE 队列、**工作环境 vs 装包环境分工**、推荐安装链、以及改 `environment.json` 后的**验证三件套**（JSON 断言 / `validate_env.py` / 全量 offline pytest）。

**ssh3 已锁定映射（用户 2026-10-08 拍板，声明在 `environment.json.cluster.policy`）**：

| 方向 | R 环境 | Python 环境 | 负责对象 |
|---|---|---|---|
| RNA | `R4.41`（R 4.4.1；Seurat 5.3.0 / SeuratDisk / sceasy / monocle3 1.4.27 / DESeq2 / harmony） | `sc-analysis`（py3.9.23；scanpy 1.10.3 / anndata 0.10.9） | Seurat `.rds` + AnnData `.h5ad` |
| ATAC | `R4.3.3`（R 4.3.3；ArchR 1.0.3 / Signac 1.14.0） | — | ArchR 分析 |

`R4.41` 同时带 SeuratDisk + sceasy → **Seurat ↔ AnnData 互转不用另找环境**。
激活：`source /hwfssz3/PS_JLU/zhangxiao6/software/miniconda3/bin/activate <env>`（R4.41 / sc-analysis / R4.3.3）。

### 🔴 工作环境 vs 装包环境 —— 两套并存，不是二选一（2026-10-08 用户澄清）

| 角色 | 环境 | 规则 |
|---|---|---|
| **工作环境** | zhangxiao6 的 `R4.41`(RNA) / `R4.3.3`(ATAC) / `sc-analysis` | **正常分析就用它**；属主他人 → **只读，⛔ 禁止在其中装任何包** |
| **装包环境** | 自有可写 `zhangbo/envs/R4.4.1_zb`（R 4.4.1 + Python 3.14.0） | **只用来补装**：映射环境缺的分析包装这里 → 作业里 `export PATH=/hwfssz3/PS_JLU/zhangbo/envs/R4.4.1_zb/bin:$PATH` 引用它 |

用户原话：「真正工作的是 RNA→R4.41 / ATAC→R4.3.3；`R4.4.1_zb` 这个只是用来装一些包的，**以后装包可以在这里装，然后调用**。因为真正工作的环境是 zhangxiao6 的，**我不能随便在他这里安装包**。正常工作在 zhangxiao 这里，缺少了一些分析包，**在我自己这里安装**。」

⚠️ 本 skill 旧版把 `R4.4.1_zb` 记成「不在映射内，默认不用」——**该说法已作废**：它是**装包落点**，缺包时的指定去处（config.yaml 的 ssh3 note 指向它，不是与 policy 冲突，是分工）。
装包链：**必须走 `ssh0`（三节点唯一有外网）** → 落到自有 env/库 → 共享 NFS，`ssh3`/`ssh23` 立即可用。

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| - | - | - | 2026-10-08 | environment.json#cluster | - | - |  |
| - | - | - | 2026-10-08 | validate_env.py | - | - |  |
| - | - | - | 2026-10-08 | pytest_env_subset | - | - |  |
| - | - | - | 2026-10-08 | pytest_full_offline | - | - |  |
| - | - | - | 2026-10-08 | environment.json#env_usage | - | - |  |
| human | skeletal_muscle | exercise | 2026-10-08 | ssh23_probe_Muscle_96_38_Umap.sh | - | - |  |
| - | - | - | 2026-10-08 | test_large_cache.py | - | - |  |
| - | - | - | 2026-10-08 | test_large_cache.py | - | - |  |
| - | - | - | 2026-10-08 | test_large_cache.py | - | - |  |
| - | - | - | 2026-10-08 | test_large_cache.py | - | - |  |
| - | - | - | 2026-10-08 | test_large_cache.py | - | - |  |
| - | - | - | 2026-10-08 | large_cache.py | - | - |  |
| - | - | - | 2026-10-08 | large_cache.py | - | - |  |
| - | - | - | 2026-10-08 | large_cache.py | - | - |  |
| - | - | - | 2026-10-08 | large_cache.py | - | - |  |
| - | - | - | 2026-10-08 | large_cache.py | - | - |  |
| - | - | - | 2026-10-08 | large_cache.py | - | - |  |
| - | - | - | 2026-10-08 | large_cache.py | - | - |  |
| - | - | - | 2026-10-08 | large_cache.py | - | - |  |
| - | - | - | 2026-10-08 | large_cache.py | - | - |  |
| - | - | - | 2026-10-08 | large_cache.py | - | - |  |
| - | - | - | 2026-10-08 | large_cache.py | - | - |  |
