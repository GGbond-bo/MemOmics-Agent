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

## 🔴 铁规 11：集群侧可见性 —— 用户会在 MobaXterm 现场核对（2026-10-08 实测）

用户会拿 MobaXterm 当"对照观察窗"问：「MemOmics 在集群执行任务的时候，我能在 MobaXterm 对应节点看到吗？」
→ 回答**必须分层给可见性矩阵**（不能只讲 MemOmics 侧回执），并主动给出"登哪个节点 + 敲什么命令"：

| 看什么 | 集群侧怎么看 | 可见？ | 原因（实测） |
|---|---|---|---|
| 产物（图/表/日志） | `ls /hwfssz3/PS_JLU/zhangbo/...` | ✅ | 工作盘 NFS **三节点共享** |
| R/python 进程 | `ps -ef \| grep Rscript` | ⚠️ **仅运行期间** | 作业结束进程即消失；同账号进程全局可见（无需 sudo） |
| SGE 队列 | `qstat` | ⚠️ 取决于 qmaster 可解析 | qstat 失败 → 工具判 `scheduler=none` → 走 **setsid 后台进程** → **队列里根本没有它**，只能靠 `ps` 看 |
| 工具账本 | `~/memomics_jobs/` | ❌ **跨节点看不到** | `/home` **不跨节点共享**（ssh3=`10.53.22.9:/vol_1t_sas_3`；ssh23=`10.53.20.27:/export/home`，独立卷）→ 账本只在本节点可见 |
| Agent 思考/会话/审查 | — | ❌ | 全在 MemOmics 本机侧，集群上没有任何痕迹 |

**由此定下的两条操作要求**：
1. **作业日志必须落工作盘**（`$WORKDIR/log/`；`scripts/run_cluster_job.sh` 已如此），**不要只落 `~/memomics_jobs`（HOME）**——否则作业跑完/换个节点就查不到。
2. 用户要现场核对 → 告诉他**登录提交时用的那个节点** + `ps -ef | grep Rscript`（或直接看工作盘产物目录），**别让他依赖 `qstat`**。

⚠️ 登录账号是 **`zhangbo11`**（uid 1003064），**不是**目录名 `zhangbo`——用户 MobaXterm 里也多半是这个账号；
跨节点"看不看得到"最终取决于**是否同一账号 + 是否同一个 NFS 卷**。

实测证据 / 排查方向 → `references/observability-from-cluster-side.md`。

**2026-10-08 二轮实测补充（htop 可见性实弹取证 + SGE 实况）**

- `ssh23` **已装 htop**（`/usr/bin/htop`）；htop 默认只列**当前用户**进程 → 用 `zhangbo11` 登录即可看到 MemOmics 作业。
- **实弹证据**：`submit` 一个 300 秒占位作业 → `ps -u zhangbo11` 看到完整链路
  `bash …/memomics_jobs/scripts/<job>.sh`（PPID=**1**，已脱离 SSH → 断连不死）→ 子进程本体；
  同期同表还看到**用户自己的两个 `htop`**（`pts/0` 子进程）→ 直接证明"同用户、同机、运行期间"三条件齐备即可见。
- ⚠️ **`submit` 会返回 `exit=124 / Command timed out after 20s` 的 error，但作业其实已经起来了**
  （工具 20s 等待窗口太短）。见到这个 error **不要判失败**，先 `ps` / `action="status"` 核实。
- 🔴 **SGE 在本集群不可用，且不是 DNS 小毛病**：qmaster `10.54.31.75:536` 从 ssh23 **TCP 不可达**
  （`/dev/tcp` 探测 `TCP536_FAIL`）+ `/etc/hosts` 缺 `cngb-ps-jlu` 条目（ssh3 有）；
  **`HOSTALIASES` 免 root 补解析实测无效**。→ 无 root/网络开通修不了；
  因此 `scheduler=none` + **setsid 是被迫的正确路径，不是降级**，且正好满足"htop 可见"的诉求。

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
- **跨节点校验也算重复**：2026-10-08 实测，因"先在 A 节点查一遍 `ls`/`df`/`qstat`、再在 B 节点查一遍同样的组合"，被判循环失控强制干预。跨节点比对要么**在同一条命令里遍历**（远端 `for` 循环 / 一次 `run` 带全部段落），要么**只查真正有差异的那一项**（例如问"`/home` 是否同一份卷"→ 只跑 `df -h $HOME`，别把整包探针重跑一遍）。

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
- ⚠️ 常驻 R 会话：**「读一次、一直用」的交互式分析现在有正规入口 `session_*`（见下节）** ——
  2026-10-09 用户拍板落地（「就做集群持久化，类似 kernel 那样」）。老写法（`qlogin`/`qrsh`/Rserve/
  裸 `screen`）仍不推荐：端口/依赖/walltime 问题。会话的代价照旧要讲清：占内存、节点清场即丢内存、
  靠 `mm_save` 检查点兜底。
- ⚠️ 缓存只留 reductions+meta → **需要重算表达量的步骤仍回原文件**；检查点指纹只覆盖显式参数
  （脚本内硬编码常量改了要手动 `rm ckpt/<stage>.done`）。

## 🔴 铁规 10：读 ≥100MB 输入前**必须弹窗问持久化**，并落任务标记（2026-10-08 用户要求）

用户原话：「检测到执行读取数据分析，弹窗询问用户要不要持久化，**大于 100M 的内容，都要推荐持久化**。
比如 RDS、h5ad，一些超大表格也是一样，并**做好任务标记，方便清理**。」

### ⛔ 触发点 = 前置门禁，不是"记得时做一下"（2026-10-08 二次教训：规矩写了但没接上入口）

**入口在「用户给了输入路径」→「写脚本 / 投作业」之间。** 只要下一步要读的输入 ≥100MB，
**先做完本流程再写脚本**——不许先投作业、事后补。

事故原样：本 skill 里已写好铁规 10，随后我仍直接对集群上 662MB 的
`MuSC_exercise_clean_dele_cluster_umap.rds` 写脚本 + `submit`，**无 scan、无弹窗、无标记**，
被用户当场追问「**你没有持久化吗？**」。根因**不是不懂规矩**，而是**规矩没接在执行路径上**
（从"拿到路径"到"投作业"之间没有任何强制前置步骤）。→ 本铁规必须当**前置门禁**执行。

### 🧱 现在有硬闸（2026-10-08 三次教训后落地）：`remote_cluster` 的 run/submit 会先过 `_persist_gate`

命令文本里出现**数据扩展名的远端绝对路径**（.rds/.h5ad/.bam/.csv/.tsv/...）→ 节点上批量 stat →
≥100MB 且 `cache_markers` 账本里没有它的 active 远端标记 → **返回 `status=needs_persist`，命令不执行**。
过闸就是下面三步；纯巡检行（`ls/stat/du/head` 开头）不触发；`scan --remote` 走内部 `scan_only` 通道不触发。
**答不出"违反了哪一步会拦住我"的时代结束：会被 run/submit 拦住。**

### 流程（固定三步，不许跳）

1. **判体积**（按输入在哪分支）：
   - **本机输入** → `python -m memomics.bio_tools.large_cache scan <路径...> --json` → 看 `recommend`。
   - **集群输入** → `python -m memomics.bio_tools.large_cache scan --remote --node <节点> <路径...> --json`
     （2026-10-08 起 `scan` 支持 `--remote`：经 remote_cluster 批量 stat/du，按 size+mtime 判，
     不取指纹）。⚠️ 不带 `--remote` 喂 `/hwfssz3/...` 只会得到 `exists:false` —— **别据此判"没有大文件"**。
     想顺带摸同目录一批：`action="run"` + `ls -la --time-style=long-iso <目录> | head -20`。
     判定 ≥100MB → 直接进第 2 步。
2. **弹窗**：≥100MB → **`ask_user(kind="intent", multi_select=true)`** 问要不要持久化
   （低于阈值**不打扰用户**；600MB 重读一次不到 40 秒）；用户答复后再动手。
3. **落标记**：`mark`（`--input` / `--cache-root` / `--artifact` / `--remote` / `--ttl-days`），
   收尾用 `list` / `verify` / `clean` 管账。
   ⚠️ 集群产物**必须带 `--remote`**：本机看不见远端文件系统，不带就会被 `os.path.exists=False`
   误导，且 `clean` 走不到"只打印 `rm -rf` 命令"的正确分支。
   2026-10-08 起 `--remote` 时输入/产物/cache_root **原样记账**（不再被 `os.path.abspath` 拼成
   `E:\...\/hwfssz3` 怪胎）；**用户拒绝持久化也要落标记**（`--note 用户选择不持久化`）——
   账本记的是"已问过"，不是"已持久化"，不落则硬闸每次都拦。

### 顺手做：给项目建「大输入清单」（避免换个文件名就重新漏）

发现某目录是**成批的大文件**时（实例：`/hwfssz3/PS_JLU/zhangbo/Muscle_96_38/Umap/` 下 6 个 RDS，
0.48–1.76 GB：FAP 1.76G / EC_pericyte 861M / Immune 832M / MuSC 662M / ANKRD1 581M / GALNTL6 483M），
**一次把同目录 ≥100MB 的项全部 `mark`**，形成该项目的清单 —— 而不是每换一个文件名重漏一次。

实测清单与 `scan` 的本地限制 → `references/big-input-inventory.md`。

**清理三道闸（删错比不删贵）**：① artifacts 命中原始输入 → 拒绝（原始数据永不删）；
② 产物必须在声明的 `cache_root` 内，未声明则整体拒绝（不猜范围）；③ 默认 dry-run，加 `--yes` 才真删；
④ **远端产物只打印 `rm -rf` 命令**（由 `remote_cluster run` 执行），不在本机假装删除；⑤ 清理后标记留痕
（`status=cleaned`），不物理删。

机制全表（schema / 阈值 / 估算口径 / 诚实边界）→ `references/large-input-cache-and-checkpoint.md`。

## 🧠 常驻 R 会话（kernel 式持久化）—— 「读一次、一直用」的正规入口（2026-10-09 落地）

用户原话：「我希望的持久化，是我读取了这个 rds 数据，这个数据就应该一直在……你只是弄了 10.9MB
精简缓存，但是我还想继续做 findmarker、cellchat 其他分析呢？不会有问题吗？……就做集群持久化，
类似 kernel 那样。」

**精简缓存（铁规 9 的方案 A）只解决「同一条链别重读」**；跨天/来回的交互式分析（今天 UMAP、明天
FindMarkers、后天 CellChat、反复调参）要的是**活着的进程**。现在它有正式入口，不用 qlogin/Rserve：

| 动作 | 干什么 | 关键参数 |
|---|---|---|
| `session_start` | 节点上起常驻 R（setsid 后台常驻，`ps`/MobaXterm 里看得见，不开公网端口）；带 `input=<大 rds>` 就先**同步读一次**（秒数/对象名/readRDS 审计都回报） | `node` / `input` / `object` / `env`(默认 R4.41) / `rscript` / `restore='latest'` |
| `session_exec` | 投 R 代码，在**同一进程、同一 globalenv** 接着跑（FindMarkers/CellChat/调参复用内存对象） | `session_id`（可省=该节点最近一个）/ `code` / `async=true` / `wait` |
| `session_save` | 落检查点 `ckpt/<名>.rds`（进程死掉/换节点靠它回来） | `name` / `objects`（默认全部会话对象） |
| `session_restore` | 从检查点把对象恢复进会话内存（默认最新一个） | `name`（可省） |
| `session_status` | pid 活没活 / busy 在跑什么 / RSS / 对象数 / **readRDS 审计** / 队列 / 最近检查点 / **最近一次结果 tail** | `session_id`（可省）/ `live` |
| `session_stop` | 让会话退出、释放内存（`save=true` 先落检查点） | `save` / `name` |
| `session_list` | 本机账本 `memomics_home/remote/sessions.json`（id/节点/输入/最近活跃/readRDS 次数） | `live=true` 逐台核实 |

**实测验收（2026-10-09，ssh23，`MuSC_exercise_clean_dele_cluster_umap.rds` 661.8MB）**：
`readRDS` 16.3s 灌进内存（01:41:06）→ `RunUMAP(harmony 1:30)` 38.9s、对象 2GB、进程 RSS 2.5→3.0GB
→ **约 7 分钟后**（01:54:10）跑 `FindMarkers(lpMuSC vs dMuSC)`：3.6s、20,266 行、1,323 个显著
（上调 874）、CSV 1.25MB 落 `out/`；**全程同一个 pid=109595、`readrds_calls` 始终 = 1**（没有回读文件）。
完整证据链与协议细节 → `references/persistent-r-session.md`。

**用法纪律（都是实测踩出来的）**：
- 会话里 `dir` 就是会话目录：图/表写 `file.path(dir, "out", ...)`；`queue/`（求情）、`done/`（结果）、
  `ckpt/`（检查点）、`staging/`（投递缓冲，别手动放）、`state.txt`（心跳）、`session.log`。
- **名字纪律**：结果写回**同一个对象名**（`X <- RunUMAP(X, ...)`）。实测踩坑：改写到了 `obj`，下次请求
  又从规范名拿回旧副本 → UMAP 白跑一次。同一份内存对象可以有多个名字，但别再从旧名字取。
- 代码要用的包**自己 `library()`**：会话是全新 R 进程，`library(Seurat)` 不会顺带 `ggplot2`——
  实测 `ggtitle` 报 "could not find function" 就是这么来的（补 `library(ggplot2)` 即好）。
- 长命令（FindMarkers/CellChat 几分钟~几十分钟）用 `async=true` 投递，再 `session_status` 查；
  同步等待容易把 ssh 连接挂死。
- 会话占内存（MuSC ~2.5GB；MF 那种 22GB rds 会到几十 GB）：**用完 `session_stop`**；同节点建议 ≤2 个
  （`remote.session.max_sessions`，超了只提示不硬拦）。
- 铁规 10 口径：**用户要求开常驻会话 = 已经回答了「要不要持久化」**（`session_start` 自动落
  `not_included=[]` 的标记，不再背「精简缓存没矩阵」的语义）；但**不许在用户拒绝持久化时偷偷开会话**。
- 进程被清场/节点重启 → 内存对象没了：`session_start(session_id=<旧 id>, restore='latest')` 从检查点
  拉回来（不必重读原文件）；没存检查点就只能重读（600MB ≈ 20 秒，先跟用户讲清代价）。
- 工作环境/装包环境的分工不变：会话默认用 zhangxiao6 的 `R4.41`（只读，⛔ 不装包）；缺包在
  `zhangbo/envs/R4.4.1_zb` 装好后从会话里 `.libPaths()` / `PATH` 引用。

## 探查/执行速查

| 目的 | 动作 |
|---|---|
| 摸环境 | `action="run"` + `scripts/probe_cluster_envs.sh <conda_root>` |
| 大输入该不该持久化 | **本机**：`large_cache scan <路径> --json`；**集群**：`large_cache scan --remote --node <节点> <路径> --json` → ≥100MB 弹窗 → `large_cache mark ... --remote`；**硬闸**：run/submit 读到未标记大输入 → `needs_persist` 拒执行 |
| 常驻会话（读一次一直用） | `action="session_start" input="<大 rds>"` → `action="session_exec" code="..."`（长任务 `async=true`）→ `session_status`（含 readRDS 审计与结果 tail）→ `session_save`/`session_restore` → 用完 `action="session_stop"` |
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
- `references/observability-from-cluster-side.md` — **用户在 MobaXterm 里能核对到什么**（铁规 11 的实测底稿）：账号 `zhangbo11`、工作盘共享 vs `/home` 不共享、`ps`/`qstat`/账本三层可见性、`qstat` 失败 → 退化为 setsid 的因果链、以及回答这类问题的固定骨架。
- `references/big-input-inventory.md` — **大输入清单 + `large_cache` 的真实边界**（铁规 10 的底稿）：`scan` 只认本机路径（无 `--remote`，喂集群路径返回 `exists:false` 不报错）、`mark --remote` 的必要性、`Muscle_96_38/Umap/` 实测 6 个 0.48–1.76 GB RDS 清单、以及复查用的三条只读命令。
- `references/persistent-r-session.md` — **常驻 R 会话的协议与实测**（2026-10-09 落地）：文件队列（`staging`→`queue` 原子 mv）为什么必须有、`state.txt`/`done/*.res.txt`/`ckpt/` 格式、`setsid -f` 不可用与 busybox `ps` 的兼容处理、MuSC 验收全过程（16.3s 读入 → 38.9s UMAP → 6 分钟后 FindMarkers 仍 `readrds_calls=1`）、以及 4 个实测踩坑。

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
| - | - | - | 2026-10-08 | ssh23_visibility_probe.sh | - | - |  |
| - | - | - | 2026-10-08 | ssh23_visibility_probe.sh | - | - |  |
| - | - | - | 2026-10-08 | ssh23_htop_visibility_live_demo.sh | - | - |  |
| human | skeletal_muscle | exercise | 2026-10-08 | musc_umap_prop_ssh3.R | - | - |  |
| human | skeletal_muscle | exercise | 2026-10-09 | r_session_daemon.R（常驻会话：MuSC 读一次 → RunUMAP 38.9s → 6 分钟后 FindMarkers，readrds_calls=1） | - | - |  |
| - | - | - | 2026-10-09 | test_cluster_session.py（19 用例） | - | - |  |
