---
name: remote-cluster-execution
description: 远端 SSH 集群（SGE/Slurm/PBS）执行规程：环境清点、作业脚本、投递与产物回收。触发：集群/ssh3/用集群跑/在集群上跑/帮我看看集群/集群有哪些环境/集群环境/投递任务/qsub。
when_to_use: 任何要在远端集群上跑分析（remote_cluster 工具）之前的环境准备与执行。用户提到"集群/ssh 节点/云上算力/他把数据放集群上"时先加载本 skill。
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [remote-cluster, ssh, sge, slurm, conda-env, environment-inventory]
    difficulty: intermediate
    language: R+Python
    category: bioinformatics
---

# 远端集群执行规程（SSH + 调度器）

> 与 `dcs-cloud` 的区别：DCS 是华大云 Web/API 平台；本 skill 是 **SSH + 调度器**（remote_cluster 工具）的集群。

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

## 探查/执行速查

| 目的 | 动作 |
|---|---|
| 摸环境 | `action="run"` + `scripts/probe_cluster_envs.sh <conda_root>` |
| 数据在哪儿 | `action="locate" path="<用户原话路径>"` |
| 节点连通/负载 | `action="nodes"` |
| 跑重活 | `action="submit"`（先 `action="check"` 摸调度器/资源） |
| 看进度 | `action="status"` / `logs` |
| 收产物 | `action="pull"`（注意体积闸门，超限先问用户） |

## 已知集群清单（实测记录）

- `references/ssh3-zhangbo-inventory.md` — ssh3（CNGB 深圳超算，SGE 8.1.9）环境实测清单：R4.41 / R4.3.3 / ARCHR / sc-analysis / scenic 等，含每个环境的真实包内容与推荐映射。
- `references/environment-declaration.md` — 环境声明的机制：`environment.json` 的 `cluster` 段 schema、`declared_env()` / `save_declared()`、WebUI「🧩 环境管理」填写入口与 `POST /api/env/declared`。

**ssh3 已锁定映射（用户 2026-10-08 拍板，声明在 `environment.json.cluster.policy`）**：

| 方向 | R 环境 | Python 环境 | 负责对象 |
|---|---|---|---|
| RNA | `R4.41`（R 4.4.1；Seurat 5.3.0 / SeuratDisk / sceasy / monocle3 1.4.27 / DESeq2 / harmony） | `sc-analysis`（py3.9.23；scanpy 1.10.3 / anndata 0.10.9） | Seurat `.rds` + AnnData `.h5ad` |
| ATAC | `R4.3.3`（R 4.3.3；ArchR 1.0.3 / Signac 1.14.0） | — | ArchR 分析 |

`R4.41` 同时带 SeuratDisk + sceasy → **Seurat ↔ AnnData 互转不用另找环境**。
激活：`source /hwfssz3/PS_JLU/zhangxiao6/software/miniconda3/bin/activate <env>`（R4.41 / sc-analysis / R4.3.3）。
⚠️ 这两个 R 环境属主是 zhangxiao6（只读）→ 装包不可；用户自有 `zhangbo/envs/R4.4.1_zb` **不在映射内**，默认不用。