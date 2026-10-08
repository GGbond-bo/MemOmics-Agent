# 远端集群（remote_cluster）实现取证

**触发场景**：用户问「你这个远端集群是怎么实现的 / 稳定吗 / 跟 MobaXterm（或 Xshell、VSCode Remote）有什么区别」。
**取证日期**：2026-10-08。**取证文件**：`memomics/bio_tools/remote_cluster.py`（2542 行）
**基类**：`hermes-agent/tools/environments/ssh.py::SSHEnvironment`（文件自身 docstring `:1-62` 说明了这段继承关系）

---

## 一、分层地图（file:line，可直接引用）

| 层 | 实现 | 位置 |
|---|---|---|
| 连接层 | `ClusterSSH(SSHEnvironment)`；复用 `_build_ssh_command` / `_establish_connection` / `_detect_remote_home` / `_run_bash` / `execute` / `cleanup` | `:523-591` |
| 差异化两点 | ① 不调父类 `__init__` 的 `FileSyncManager.sync()`（否则把本机 credentials/skills/cache 推到共享登录节点）② `_before_execute()` 置空 | `:526-528`, `:586-588` |
| SSH 命令构造 | `BatchMode=yes` + `StrictHostKeyChecking=accept-new` + `ConnectTimeout=10`，`-p/-i`，`extra_options` 必须插在 host 之前 | `:565-584` |
| Windows mux 适配 | Win32-OpenSSH 无 mux → 先试 mux，命中 `getsockname`/`not a socket` 一类标记就**永久降级**为每次新建连接（`_MUX_KNOWN_UNSUPPORTED`，`use_mux = ... and os.name != "nt"`） | `:500-514`, `:541-561` |
| 连接池 | `_CONNS` + `threading.RLock`；键含密钥路径（同 host 不同 key 不复用）；`force_reconnect` / `_drop_conn` | `:496-497`, `:594-639` |
| scp 传输 | `scp -r -q`；有 mux 时复用 `ControlPath` socket；新版 scp 走 SFTP，对端禁 sftp-server 时回退 `-O`；超时 `max(timeout,120)` | `:759-798` |
| 调度器探测 | `sbatch/squeue`→slurm；`qsub+qstat`→用 `qsub -help` 版本行区分 Grid Engine vs PBS；都没有→`none`（无调度器后台跑） | `:805-855` |
| 作业脚本 | slurm `#SBATCH` / pbs `#PBS` / gridengine `#$`（GE 不吃 `-o %j`，会生成字面量叫 `%j` 的文件） | `:871-910+` |
| 多节点（MobaXterm 式命名） | `nodes:` 段支持 3 种写法（名字即主机名/别名、字符串=显式 host、全量字段含 `proxy_jump`）；`default_node`、`node_policy`、`allow_unlisted_nodes` | `:117-126`, `:250-361` |
| 选点策略 | 单节点静默用 / 指定名字必须命中（大小写不敏感）/ 有 `default_node` 用默认 / **多节点+没指定 → `status=needs_node` 硬拦**（不许自己挑） | `:370-440` |
| 作业账本 | 投递写 `hermes_home/remote/jobs.jsonl`；查作业**按节点名严格匹配**（ssh3/ssh5 可能同一台登录机，比 host 会串） | `:454-465`, `:682-722` |
| 连接错误识别 | `_is_conn_error()` 覆盖 connection closed/reset/refused、broken pipe、no route、kex_exchange_identification、host key、permission denied 等 | `:672-679` |
| 可发现性 | `remote_cluster_enabled()` = `check_fn`：没配 `remote:` 段 → 工具**不出现在工具列表** | `:234-243` |
| 配置 | `hermes_home/config.yaml` 的 `remote:` 段，可被 `MEMOMICS_REMOTE_*` 覆盖；配置解析失败只 warning 不崩 | `:33-62`, `:163-231` |

---

## 二、稳定性：分「工程处理」与「固有边界」两半说

### 真做了工程处理（可以先讲这部分）
- **复用而非重写**：SSH 命令构造与执行语义与 hermes 完全一致 → 出问题可按 hermes 文档排查（`:29-31` 明确的自我约束）。
- **多重降级**：mux 不支持→自动降级；scp SFTP 被禁→`-O` 回退；配置坏了→取默认值；节点名非法→warning 跳过（`:295-297`）；工具导入失败→报明确原因（`:488-492`）。
- **连接错误识别 + 连接池**：可判别 11 类连接错误，为重连提供依据。
- **状态可追溯**：作业落盘 `jobs.jsonl`，跨会话/进程重启仍知道 `job_id` 属于哪个节点。

### 固有边界（不是 bug，主动说，别等用户抓）
| 边界 | 后果 | 对策 |
|---|---|---|
| `BatchMode=yes` → 只支持密钥登录 | 密码/交互式认证连不上 | 配密钥或 ssh-agent（`:56-57`） |
| 登录节点只跑轻量命令 | 重计算挂登录节点会被管理员封号 | 一律 `submit` |
| 共享节点 `qstat` 可能卡死（实测 3 分钟无响应） | `run` 超时，看起来像工具坏了 | 加 timeout + 如实报 + 建议用户手动确认 |
| **无断线续跑队列** | 网络/跳板机抖一下，在跑的 `run` 就失败 | 长任务走 `submit`（作业独立于 SSH 连接） |
| 多节点未指定 → `needs_node` 硬拦 | 不替你挑机器 | 设计如此；配 `default_node` 可免问 |
| `pull` 体积闸门（默认 512MB） | 超限拒绝下载 | 防手滑拖 BAM；确认后提 `max_mb`/`allow_large` |
| 依赖 `hermes-agent` 在 `sys.path` | 缺则导入报错 | 报错已写明原因 |

> 另有**非工具问题但必踩**的一类：**环境名不可信**（`envs/cellchat` 里没 CellChat、`envs/monocle3` 里没 monocle3，真正有的在 `R4.41`）——见 skill `remote-cluster-execution` 铁规 0。

---

## 三、vs MobaXterm（问答骨架，固定这张表）

| 维度 | MobaXterm | MemOmics remote_cluster |
|---|---|---|
| 定位 | 给人用的图形化 SSH/SFTP 客户端 | 给 Agent 用的结构化 API 工具 |
| 认证 | 密码 + 密钥 + 保存会话 | 仅密钥（BatchMode），无密码交互 |
| 交互 | 交互式 shell、看终端、拖文件、X11 | 无交互；返回 JSON（status/output/lines…） |
| 作业 | 自己敲 qsub/sbatch、自己盯终端 | 调度器感知：submit/status/logs/cancel + jobs.jsonl 账本 |
| 产物 | 手动 SFTP 拖回 | push/pull 自动路径映射，产物落 `results/<sid>/` 供报告引用 |
| 断线 | 会话保持/重连（交互式） | 连接池 + 错误识别；无断点续跑，靠 submit 规避 |
| 底层 | OpenSSH ssh/scp | 同一套 OpenSSH ssh/scp（共用 known_hosts/密钥/ProxyJump） |
| 门禁 | 无 | 意图确认（簇投递属高代价）、rail_review、登录节点轻量限制 |

**一句话**：MobaXterm 是「我坐进集群」（能看见终端、能救火改命令）；remote_cluster 是「我把集群接进分析管线」（投递/进度/产物回传自动化，但没有可手敲的终端，排障靠 `logs`/`status` 回执）。

---

## 四、回答这类问题的套路（本次已验证有效）
1. **结论先行 3 句**：实现是什么 → 稳定性分半说 → 与对照物的本质差别。
2. **配 mermaid 链路图**（配置门 → 选点 → SSH 构造 → mux 分支 → run/submit/push-pull → 产物回传），放在实现细节之前。
3. 源码表格逐行带 `file:line`；稳定性拆「真做的工程」与「固有边界」两块，边界给后果 + 对策。
4. 结尾 **📚 参考来源**：源码路径 + 基类 + 配置 + 实测记录（skill references）+ **KB 检索结果照实报**（本次 `search_knowledge` 57 条命中全是生物学参数，无平台机制条目 → 明说本问题证据类别是源码，不硬凑 PMID）。
5. ⛔ 不给「我们的集群很稳定」这类无证据结论；⛔ 不把 SOUL/README 自述当实现。