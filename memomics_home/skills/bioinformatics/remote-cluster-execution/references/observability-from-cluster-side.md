# 集群侧可见性：用户在 MobaXterm 里能核对到什么（实测 2026-10-08）

> 配套 SKILL.md 铁规 11。用户问的是**行为**（"我能在 mobaX 对应节点看到吗"），
> 所以答案必须是**实测的可见性矩阵**，不是推断；并且要给出"登哪个节点 + 敲什么命令"。

## 1. 实测原始证据（node4 = compute-node / node1 = login-host）

| 探针 | node4 结果 | node1 结果 |
|---|---|---|
| `whoami; id` | `user` `uid=1003064` gid=2906(ST_PRECISION) | `user`（同账号） |
| `hostname` | `login-host` | `login-host` |
| `pwd`（默认 cwd） | `/cluster/share/user` | 同 |
| `df -h $HOME` | `10.53.20.27:/export/home` 1.0T 用 667G (66%) | `10.53.22.9:/vol_1t_sas_3` 1.0T 用 3.3G (1%) |
| `df -h /cluster/share/user` | `login-host:/share` 120T 用 97T 余 24T (81%) | 同（同一份） |
| `ls ~/memomics_jobs` | 存在，mtime Oct 8 16:07（**本次工具创建**） | 也存在，但是 Oct 8 02:57 的旧账本（`memomics_direct.log/.pid`） |
| `ps -ef \| grep -E "Rscript\|python\|qsub"` | **0 个** R/python 分析进程（仅 root 的 fail2ban/tuned python2 系统服务） | — |
| `qstat` | `error: unable to send message to qmaster using port 536 on host "cluster-login": can't resolve host name` | 返回**空**（不报错、也无内容） |
| `getent hosts cluster-login` | 失败（rc=2）→ 域名解析不了 | — |
| `SGE_ROOT` | `/opt/gridengine` | — |
| `ls /opt/gridengine/bin/lx-amd64/qsub` | ✅ 存在（但**不在默认 PATH**） | — |

## 2. 结论：三层可见性

1. **工作盘 = 共享**（`/cluster/share`，NFS）→ 产物/日志/脚本，**任一节点都看得见**。
2. **`/home` = 不共享**（两节点挂的是不同 NFS 卷，IP 与用量都不同）→ 工具账本 `~/memomics_jobs/`
   **只在本节点可见**；换个节点就看不到。
   ⚠️ 注意两个节点上都有 `memomics_jobs` 目录，**别误以为共享**——它们是各自节点独立的目录。
3. **进程**：Linux 默认 `ps -ef` 对同机所有用户可见 → MobaXterm 登录**同一节点**即可看到 `user` 的 `Rscript`，
   但**只在作业运行期间**（作业结束 → 进程消失，本轮实测就是 0 个）。

## 3. `qstat` 失败会改变作业的"形态"（重要因果链）

```
qstat 报 qmaster 解析失败
  → remote_cluster 探测调度器时判定 scheduler = "none"
  → submit 退化为 setsid 后台进程（脚本落 ~/memomics_jobs/scripts，日志落 ~/memomics_jobs/logs）
  → 这个作业【不在 SGE 队列里】
  → 即使 qstat 修好了，队列里也看不到它；只能靠 ps / 产物目录核对
```

要恢复"正式队列作业"（qstat 可见、可 `qdel`），需要先让 qmaster 主机名可解析——
排查方向（症状是 `can't resolve host name`，不是"工具坏了"）：
`/etc/hosts` 是否漏了 `cluster-login`、DNS/`/etc/resolv.conf`、`$SGE_ROOT/$SGE_CELL/common/act_qmaster` 里的主机名、
以及是否需要 `module load` 或走特定登录节点。**这类是网络/环境侧配置，交用户或管理员确认**。

## 4. 回答这类问题时的固定骨架（照抄即可）

1. **一句话直答**：部分能看 —— 产物能、进程运行期间能、队列/账本不一定。
2. **矩阵表**：产物 / 进程 / 队列 / 账本 / Agent 层，逐行给"可见？+ 原因（实测）"。
3. **因果图**（mermaid）：作业怎么走 → 决定你能在哪看到它。
4. **三条实操建议**：登哪个节点敲什么命令；日志落工作盘；要看全局就用 `status`/`logs`/WebUI 面板。
5. **诚实交代**：哪些是只读探查（不触发 rail_review(post) 分析级口径）、哪些是环境侧待确认（如 qmaster 解析）。

## 5. 顺手可查但别陷进去

- 只读探查**不需要** `rail_review(post)`（无图表产出，会判 failed）——如实说明口径不匹配即可（同 SKILL.md 铁规 3）。
- 一次把要查的全查完（铁规 6），**跨节点也别分两轮**（本轮因此被循环检测拦下）。