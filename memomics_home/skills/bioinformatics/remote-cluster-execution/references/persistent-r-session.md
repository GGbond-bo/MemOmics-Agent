# 常驻 R 会话（kernel 式持久化）—— 协议、实测与踩坑

> 2026-10-09 落地。用户原始诉求：「我希望的持久化，是我读取了这个 rds 数据，这个数据就应该一直在……
> 你只是弄了 10.9MB 精简缓存，但是我还想继续做 findmarker、cellchat 其他分析呢？不会有问题吗？」
> → 「就做集群持久化，类似 kernel 那样。」
>
> 本文件是**实现底稿 + 验收记录**：为什么这么设计、协议长什么样、哪些兼容性坑会咬人。给未来
> 维护者/未来的 agent 看，不要求逐条记，但改代码前请先读「踩坑」一节。

## 1. 定位：和精简缓存是两件事，别互相替代

| | 精简缓存（方案 A，`large_cache` + `checkpoint_job.R`） | 常驻 R 会话（本文件） |
|---|---|---|
| 形态 | `light.rds`：reductions + meta（≈原文件 5%，丢稀疏矩阵） | 节点上一个**活着的 R 进程**，对象在内存里 |
| 解决 | 同一条链别重读；绘图/参数扫描 | 跨天/来回的交互式分析：FindMarkers、CellChat、反复调参 |
| 边界 | 需要重算表达量的步骤**仍要回原文件** | 只要进程活着，读到的东西**一直在**（含表达量矩阵） |
| 失效场景 | 无（文件在就有） | 节点清场/重启/进程被杀 → 内存对象没了，靠 `ckpt/*.rds` 兜底 |
| 入口 | `large_cache` CLI + `run_cluster_job.sh` | `remote_cluster` 的 `session_*` 动作（WebUI 控制台同款） |

**会话不能替代检查点，检查点也不能替代会话**：会话让「读一次一直用」成立，检查点让「进程死了还能回来」成立。

## 2. 为什么不用 Rserve / TCP socket / qlogin

实测事实（2026-10-09，三节点）：R4.41 里**没有 Rserve、没有 qs**（有 jsonlite，但本方案连它都不用）；
SGE qmaster 不可达（`scheduler: none`）；节点间是共享 NFS；用户会在 MobaXterm 里现场核对进程。

于是选**「文件队列 + 后台常驻进程」**，全部只用 base R + coreutils：

- **零三方依赖**：任何有 R 的环境都能跑，不为装个 Rserve 去污染别人的只读环境；
- **不开公网端口**：投递方（本机）和 daemon 通过**共享目录**通信，节点不监听任何端口；
- **可见性**：daemon 就是一个普通 Rscript 进程，`ps -u user` / htop 里看得见（满足铁规 11）；
- **抗断线**：`setsid`/`nohup` 脱离 ssh 会话，MobaXterm 关掉不影响它。

## 3. 目录布局与协议

会话目录（默认 `<workdir>/memomics_cache/sessions/<sid>/`）：

| 路径 | 作用 |
|---|---|
| `queue/<rid>.req.R` | 待执行请求（**是一个 R 源文件**，首行 `#MM-REQ id=… op=… created=…`） |
| `staging/<rid>.req.R` | 投递缓冲区：先用 base64 分块写这里，再**原子 `mv`** 进 `queue/`（见踩坑 3） |
| `run/<rid>.req.R` | daemon 用 `file.rename(queue→run)` **原子认领**；抢不到就下一轮 |
| `done/<rid>.res.txt` | 结果：头部 `key: value` + 四段 `---OUTPUT--- / ---WARNINGS--- / ---ERROR--- / ---READS---` |
| `done/<rid>.req.R` | 执行完的请求原文（留档，便于复盘「当时到底跑了什么」） |
| `ckpt/<名>.rds` | `mm_save()` 检查点（默认 `compress=TRUE`） |
| `out/` | 用户代码的产物目录（`file.path(dir, "out", ...)`） |
| `state.txt` | 心跳：`pid/status/current/jobs_done/readrds_calls/rss_kb/objects/updated`，每 2 秒刷新 |
| `session.log` | 事件流水（`begin/end/readRDS/ckpt saved/…`） |
| `daemon.lock/pid` | 单实例锁（同目录第二个 daemon 直接拒绝启动） |

`---READS---` 是**审计段**：daemon 把 `readRDS` 包了一层（记时间、字节、路径），所以结果里能直接看到
「这一步读没读文件」。`readrds_calls` 就是「读一次」的硬证据。

## 4. 客户端实现要点（`memomics/bio_tools/cluster_session.py`）

- **写文件**：文本按 UTF-8 → base64 → 8000 字符一块、单块单命令 `printf %s <b64> | base64 -d >> path`，
  最后 `chmod` + `md5sum` 校验。绕开引号/换行/编码/命令行长度所有坑（R 脚本推 daemon 也用同一条路）。
- **等结果**：**远端**一条命令自己轮询（`for i in $(seq 1 N); do [ -f res ] && break; sleep 1; done; cat res`），
  不是本机刷屏轮询；`wait<=0` 或 `async=true` 就只投递。
- **异步**：`async=true` 投递完立即返回，之后 `session_status` 看 `busy/current_request`，或读
  `last_result_tail`（最近一次结果 tail，2026-10-09 加）。
- **ps 兼容**：用 `ps -p "$P" -o pid,rss,etime,stat,args | tail -n +2`（**不要** `-o pid=,rss=` 写法，
  见踩坑 2）；内存的权威数字仍以 `state.txt` 的 `rss_kb`（读 `/proc/<pid>/status`）为准。
- **启动兼容**：先探 `setsid -f` 是否可用，不可用退 `setsid`，再退 `nohup`（见踩坑 1）。
- **会话解析**：`session_exec/save/restore/status/stop` 不带 `node` 时，**从注册表（`sessions.json`）取
  该会话所在的节点**，避免落到 `default_node` 上连错机器；`session_list` 纯本地读账本，不连节点。
- **恢复路径**：`session_start(session_id=<旧 id>, restore='latest')` —— 复用同一目录（旧检查点还在），
  起新 daemon 后把对象灌回来，**不重读原文件**。

## 5. 实测验收（2026-10-09，用户指定口径）

用户验收标准（原话）：「测试就用读取 rds 跑 umap，隔几分钟再跑 findermarker，看看能否重新利用之前的
rds，而不是重新读取。」

- 输入：`/cluster/share/user/Muscle_96_38/Umap/MuSC_exercise_clean_dele_cluster_umap.rds`
  （661.8MB；与 `light.rds$src` 和 `musc_umap_prop_node1.R` 用的是**同一个文件**）；
- 节点：`node4`（compute-node，503GB 内存、余量 495GB；小节点也够）；
- 会话：`s-20261009-014300-vq48`，pid **109595**，R 4.4.1（`R4.41` env），daemon 脚本
  `memomics_cache/bin/r_session_daemon.R`。

| 时刻 | 事件 | 关键数字 |
|---|---|---|
| 01:40:53 | `session_start`（setsid 常驻） | pid 109595 |
| 01:41:06→01:41:22 | **唯一一次** `readRDS`（661.8MB） | **16.3s**，`readrds_calls=1` |
| 01:52:44 | `RunUMAP(harmony 1:30)` | **38.9s**，对象 2GB，RSS 2.5GB |
| 01:54:10→01:54:14 | `FindMarkers(lpMuSC vs dMuSC)` | **3.6s**，20,266 行，显著 1,323（上调 874），CSV 1.25MB |
| 全程 | 同一 pid、`readrds_calls` 始终 = 1 | **没有回读文件** |

`session_status` 的复核输出（节选）：`pid=109595 / alive=true / jobs_done=8 / readrds_calls=1 /
objects=19 / rss_h=3.0GB`，`done/` 下 8 个结果文件，`out/` 下 `umap_verify.png`(677KB)、
`findmarkers_lpMuSC_vs_dMuSC.csv`(1.25MB)。

## 6. 实测踩坑（改代码前必读）

1. **`setsid -f` 不是到处都有**：node4 的 setsid 不支持 `-f`（报 `invalid option -- 'f'`，直接死在启动）。
   现方案：`setsid -f` 可用就用，否则 `setsid`，再否则 `nohup`；配合 `>> session.log 2>&1 < /dev/null`。
2. **`ps -o pid=,rss=` 在这种 ps 上会被吃掉**（procps-ng 3.3.10 实测：`-o pid=,rss=` → `,rss=`，pid 列丢失）。
   用 `-o pid,rss,etime,stat,args | tail -n +2`。
3. **直接往 `queue/` 分块写 = daemon 会认领到写了一半的请求**（实测：投递方 `chmod` 报「No such file」，
   而请求其实已经执行）。→ `staging/` 先写、再 `mv` 进 `queue/`，daemon 看到的永远是完整文件。
4. **`library(Seurat)` 不会带 `ggplot2`**：会话是全新 R 进程，`ggtitle` 报 `could not find function`。
   会话代码要用的包**自己 `library()`**（或 `ggplot2::ggtitle`）。
5. **名字纪律**：`X <- RunUMAP(X, ...)` 要写回**同一个名字**。实测把结果写进 `obj`、而规范名
   `MuSC_…` 还指向旧对象 → 下次请求从规范名取回旧副本，UMAP 白跑一次（R 里两个名字一开始指同一份内存，
   一旦你不小心从旧名字重新赋值就分叉了）。
6. **别用 `system("grep VmRSS /proc/self/status")` 量 R 的内存**：那读到的是子 shell 的 684kB；
   要量就读 `state.txt` 的 `rss_kb`（daemon 自己读 `/proc/<pid>/status`）。

## 7. 运维口径

- **内存**：会话 = 真占内存（MuSC ~2.5–3GB；22GB 的 `MF_*.rds` 会到几十 GB）。同节点建议 ≤2 个
  （`remote.session.max_sessions`，超了 `session_start` 只**提示**不硬拦）；**用完 `session_stop`**。
- **检查点**：`session_save`（可 `objects=` 只存小对象，几秒；全存大对象要几分钟+GB 级磁盘）；
  `session_stop(save=true)` 会先存再退。
- **清场/重启后**：`session_start(session_id=<旧>, restore='latest')`。
- **可见性**：MobaXterm 里 `ps -u user | grep R` 能看到 daemon；`htop` 同用户同机可见；
  `tail -f <会话目录>/session.log` 看实时事件。
- **配置**：`memomics_home/config.yaml` 的 `remote.session`（`env` 默认 `R4.41`、`roots` 找 Rscript 的
  根目录、`dir` 会话根、`load_timeout`/`wait`/`save_wait` 等待上限）；节点级可覆盖
  `remote.nodes.<名字>.session`。
- **测试**：`webui/tests/test_cluster_session.py`（28 用例，离线；含「staging→mv 入队」、
  「live=true 不再把 dict 当字符串」两条回归，以及**本机真起 Rscript 跑 daemon 的抓图实测**）。

## 8. 抓图与 📓 Notebook 总端（2026-10-09 第二批）

**要解决的问题**：非交互 R 进程里画图会掉进 `Rplots.pdf` 或干脆不落盘 —— 「像 Jupyter 一样看到图」
就差这一层。WebUI 于是没有一个统一的「看会话里跑过什么」的地方。

**协议扩展（daemon v2）**：

| 位置 | 变化 |
|---|---|
| `<会话>/plots/` | 新增产物目录：每张图一个 PNG，名 `<请求号>_NN.png`（1440×1080 @144dpi，白底） |
| 绘图设备 | `options(device = .mm_device)`：R 一旦要开默认设备，就开成写进 `plots/` 的 `png()` |
| 请求执行 | `.mm_eval_code()` 取代 `source()`：**逐顶层表达式** eval + 可见值 print，**每个表达式后关掉我们开的设备** → 一个表达式一张图 |
| 结果文件 | 头部新增 `plots:` / `plots_skipped:`；新增第五个分段 `---PLOTS---`（`路径<TAB>字节数`） |
| `state.txt` | 新增 `plots_total=`（会话累计）/ `plots_last=`（上一个 cell 抓了几张） |
| 会话内 | `mm_plots(n)` 列最近抓到的图；`mm_info()` 里也带一行 |

**为什么必须「每个表达式收尾」**：R 的默认设备是**复用的**——`plot()` 开一个 png，
紧接着的 `hist()` 会画在**同一个**设备上，第二次落盘直接覆盖第一张。实测第一版就是「画两张只剩一张」，
本机真跑 R 抓出来后改成逐表达式 `dev.off()`（只关自己开的那个，记在 `plots$dev`，不误伤用户的设备）。
边界仍在：**同一个表达式里画多张（如 for 循环连续 plot）只留最后一张**；cell 结束时还开着的设备会被
自动关掉并在 `warnings` 里记一条。

**读侧（agent / WebUI 共用，无新增 HTTP 路由）**：

| 动作 | 说明 |
|---|---|
| `session_cells` | 一条 ssh 拿回最近 N 个 cell：`==CELL==/==CODE==/==OUTPUT==/==WARNINGS==/==ERROR==/==PLOTS==` 六段（`limit` 默认 12、上限 60；输出尾 60 行、代码 120 行） |
| `session_plot` | 取一张图：`path` 必须在会话目录内（`case "$F" in "$D"/*` 闸门）、类型限 png/jpg/svg/pdf、`max_bytes` 默认 4MB，返回 `{mime, b64, data_uri_prefix}` |

⚠️ **`session_plot` 必须走 `_exec_full`（不要 `_exec_env`）**：`bounded_capture` 默认只留约 50KB，
base64 会被截成半张图（`hermes-agent/tools/environments/base.py` 的 `get_max_bytes()`）。

**WebUI**：输入框区域最上面是「📓 总端条」（状态点/会话名/一行状态），点开是覆盖式面板
（`#nb-mask`）——顶部状态行、运行中 cell 的 ⏳ 卡片（`plots_recent` 过滤出**当前请求**的图，
所以长 cell 也能边跑边冒图）、历史 cell 列表（代码/输出/警告/报错/图）、底部新 cell 输入框
（Enter 运行 = `session_exec async=true`，投递后立刻插一张「已投递」卡）。
面板开着 2.5s 轮询 `session_status`，只在 `plots_total/plots_last` 变了、或上一次在跑这次跑完、
或手动刷新时才拉 `session_cells`；关面板即停轮询，条上另有一条 30s 慢拍。图按需取（一次最多 4 张、
缓存 40 张）。面板只看**集群常驻会话**；本地 `execute_r/execute_python` 的变量与图不在这里，
`plotly/htmlwidgets` 这类交互图退化成静态 PNG（daemon 抓的就是静态图）。

**本机可复现的验收**：`webui/tests/test_cluster_session.py::test_daemon_plot_capture_end_to_end`
（Rscript 起 daemon → 投两格 → 断两个表达式两张图、第二个 cell 零张、PNG 魔数、`state.plots_total`）。