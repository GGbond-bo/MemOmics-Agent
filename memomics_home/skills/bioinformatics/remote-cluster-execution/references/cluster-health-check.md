# 集群体检实测回执（2026-11-09 · node1/node3/node4）

用户原话：「你还能连接集群吗？看看集群的情况」——纯只读巡检，**不投递、不写盘、不在登录节点算**。
本文是铁规 12 的实测底稿：真实回执 + 当时的解读。数字会变，**判读方法不会变**。

## 1. `action="nodes"` —— 一次拿到「能不能连 + 谁空着」

| 节点 | host | 规格 | load1/5/15 | reachable |
|---|---|---|---|---|
| node1（default_node） | login-host | 144 核 / 3TB | 0.84 / 0.67 / 0.65 | ✅ |
| node3 | login-host | 8 核 | 0.00 / 0.01 / 0.05 | ✅ |
| node4 | compute-node | 112 核 | 0.00 / 0.01 / 0.05 | ✅ |

顶层回执：`"configured": 3, "reachable": 3, "idle_now": ["node1","node3","node4"]`，
`"summary": "3/3 个节点可连；负载较低"`。

工作盘（三节点共享）：`cluster.login-host:/share 120T 98T 23T 82% /cluster/share`
→ **剩 23T，但已用 82%**，报余量时要同时报占用率（只说"还剩 23T"会让人以为很宽松）。

⚠️ 陷阱：这里 `"scheduler": "gridengine"` 是**假阳性**，见第 2 节。

## 2. `action="check", node="node1"` —— 调度器与工具链的真话

- `"scheduler": "none"`（尽管 `bins` 里 qsub/qstat/qdel 都在，`qsub_ver=SGE 8.1.9`）
- 内存：`Mem: 3023 total / 1856 used / 290 free / 1160 available`（3TB 池，可用 ~1.16TB）
- `Rscript=-`、`R=-`、`python3=-`、`conda=-`、`module=module`、`python=/usr/bin/python`
  → 登录节点 PATH **没有 R**，跑东西必须绝对路径：RNA→`envs/R4.41`，ATAC→`envs/R4.3.3`
- 可写工作目录 `/cluster/share/user`，`workdir_missing: false`
- 自动把节点环境同步进 `environment.json → cluster.nodes.node1.probed`

**判读**：`nodes` 的 scheduler 字段只证明"二进制存在"，`check` 才是"qmaster 通不通"。
本集群 qmaster 从 node4 TCP 不可达（见 `references/observability-from-cluster-side.md`），
故两处必然打架 → 汇报按 `check`，投递走 setsid。

## 3. `action="jobs", node="node1"` —— 队列 + 本机投递账本

`scheduler: none`、`"没有本工具提交的作业在跑"`，账本最近 5 条是 11-02 / 11-03 的
`memomics_node1` 与 `Imm5_s1..s4_node1`（分片投递）。**账本只能说明"我投过什么"，不能说明"现在有什么在跑"**。

## 4. `action="run"` 一条 `ps` —— 真进程普查（关键证据）

```bash
ps -u user -o pid,etime,pcpu,pmem,cmd --sort=-pcpu | head -15
```

实测看到（节选）：

| PID | ELAPSED | 进程 |
|---|---|---|
| 58648 | 02:22:03 | htop（用户自己的） |
| 75683 | 13-13:17:13 | IRkernel（Jupyter 内核） |
| 52633 | 11-14:34:23 | IRkernel |
| 93923 | 10-03:40:51 | `r_session_daemon.R --dir .../sessions/s-20261029-215224-z0ua` |
| 27514 | 3-07:56:02 | `r_session_daemon.R --dir .../sessions/s-20261105-173721-hsz3` |
| 100206 | 3-13:30:01 | `r_session_daemon.R --dir .../sessions/s-20261105-120321-urb5`（用的是 `envs/R4.4.1_zb`） |
| 128303 | 6-06:55:36 | `r_session_daemon.R --dir .../sessions/s-20261102-183743-q8lr` |
| 16400 | 84-04:12:57 | `[R] <defunct>`（僵尸，无害但可提） |

→ **4 个 daemon 在跑**，而 `session_list` 5 条全 `stopped` 且**不含这 4 个 session id**。
这就是铁规 12 / 4.1 的原始证据。普查要点：
- 用 `ps -u <user>` 按用户抓，不必 `-ef | grep` 全表；
- daemon 的会话目录在 `--args --dir .../sessions/<id>` 里，**用这个和账本对账**；
- 判"有没有大计算在跑"看 `%CPU` 与 cmd：daemon 空转是 0.4–1.7%，真在跑 FindMarkers 会顶到几十上百。

## 5. 同轮踩到的坑：`du -sh` 超时

```bash
du -sh /cluster/share/user/Muscle_96_38 /cluster/share/user/memomics_cache
# → 120s 后 exit_code=124，ps 输出已回，du 段空白
```

**教训**：体检里任何扫大目录的命令都要能被打断。要么 `--max-depth=1 | sort -h | tail`，
要么直接用 `df`（`nodes`/`check` 已免费给）。想拿单文件体积用 `stat -c%s <file>`，别用 `du`。

## 6. 收尾话术（用户认可的形状）

① 一句话结论（能连 / 几比几）② 节点表（规格·负载·可连）③ 两个"要注意的点"（调度器真口径、遗留进程）
④ 环境提醒（绝对路径）⑤ **可选动作 + 代价**（清 daemon 会丢内存对象、要重读 rds）→ 等用户点头。
不做破坏性动作，不在只读体检里顺手 submit。