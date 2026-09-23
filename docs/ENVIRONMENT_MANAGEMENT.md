# 环境管理（Environment Management）

> 目标：**用户和 agent 都能一眼知道自己有什么环境**——本机装了什么 R / Python / 生信 CLI / conda / GPU，
> 集群有几个节点、多少核、现在忙不忙——不用再去翻 `environment.json`、不用手动敲 `Rscript --version`。
>
> 实现：`memomics/bio_tools/env_inventory.py`（只读探测 + 缓存）、`webui/server.py` 两个 HTTP 接口 +
> agent 提示词注入、`webui/index.html` 的「🧩 环境管理」面板（三个 tab）、只读工具 `env_inventory`。

## 1. 为什么需要它

在这之前，"我有什么环境"散落在四个地方：

| 来源 | 问题 |
| --- | --- |
| `environment.json` | 是**声明**不是实测：声明了 `D:/Python/site-packages` 共享库，实测没被任何解释器挂载 |
| `check_env` 工具 | 只查**这一个**能力缺不缺包，看不到全貌 |
| `execute_r` / `execute_python` 报错 | 出错才知道缺包，且只报当前那一个 |
| 用户自己翻终端 | 每次都要重来，agent 也学不到 |

环境管理把它们收敛成**一份实测清单 + 一个缓存文件 + 三个出口**（面板 / 工具 / agent 提示词），
三方读的是同一个 `hermes_home/env_inventory.json`，所以**面板看到的和 agent 用到的永远一致**。

## 2. 三个出口（同一份数据）

| 出口 | 给谁用 | 触发方式 |
| --- | --- | --- |
| 🧩 环境管理面板 | 人 | WebUI 左侧导航 → 🧩 环境管理（三个 tab） |
| `env_inventory` 工具 | agent 自己 | 对话里问"本机有什么环境" → agent 自动调用 |
| 环境卡片注入 | agent 每轮开场 | `_create_agent()` 把 `agent_digest()` 拼进 system prompt |

第三项是"agent 自己知道有什么环境"的关键：**每轮开场就有**，不需要它先调工具；
但注入的只有 **~1.8 KB 的缓存摘要**，只读缓存、绝不探测（否则每轮对话都要等 40 秒，还会打掉前缀缓存）。

### 面板三个 tab

1. **🐍 本机环境**：资源（CPU/内存/GPU/磁盘/WSL）、⚠️ 需要注意、Python（候选解释器 + 已装关键包 + 缺包）、
   R（各版本 + 包数 + 缺的关键包 + 跨版本加载的包）、命令行工具（✅/✗ 分开）、conda、已知坑、`environment.json` 标注。
2. **🖧 集群环境**：节点表（核数 / 负载 / 是否空闲 / workdir / 调度器）+ 汇总资源 + 每个可达节点探到的
   版本与工具路径；**没配置时**直接给出 `config.yaml` 路径、"在 `remote:` 段写 enabled: true" 的指引，
   以及一个「🖧 打开远端集群面板」按钮（数据来自 `remote_cluster`，所以和 🖧 控制台永远一致）。
3. **🤖 Agent 怎么用**：工具的动作清单、缓存文件位置，以及**逐字展示** agent 每轮看到的那张环境卡片。

## 3. 缓存与刷新语义（前端轮询依赖它）

| 键 | 含义 |
| --- | --- |
| `version` | 缓存结构版本（`_CACHE_VERSION`，结构变了就作废旧缓存） |
| `local` / `local_at` | 本机清单 + 完成时间戳，TTL `_LOCAL_TTL = 3600`（1 小时） |
| `cluster` / `cluster_at` | 集群清单 + 时间戳，TTL `_CLUSTER_TTL = 600`（10 分钟，SSH 慢、状态变得快） |
| `local_force` / `cluster_force` | 被 `invalidate()` 标脏（下次要真扫），但**数据仍保留** |
| `fingerprint` | 环境指纹（解释器 / site-packages / R 库 / conda 的 mtime），给 `verify()` 比"变没变"用 |

**持久性（2026-09-23 修）**：清单**过 TTL 不再丢掉**。以前一过 1 小时 `cached_local()` 就只回
`pending`，面板退回「还没扫过，正在后台扫描」，上次扫到的 R 版本/缺包/警告全部不可见（用户反馈
"环境清单没保存住"）。现在过期也照常返回内容（`stale: true` + `age_s`），同时 `needs_refresh`
让后台去重扫、扫完原子替换；**重扫失败也保留旧清单**（`invalidate()` 只清时间戳+立标记，不再置 `None`
—— 以前点「🔄 重新扫描」会先把旧清单删掉，这次万一扫失败旧清单就永久没了）。

- 写缓存：`_write_cache(**updates)` 先合并再 `os.replace` 原子替换（写一半被打断也不会留下坏 JSON）。
- 读缓存：`_read_cache()` 按 mtime 记忆化（`_CACHE_MEM`），进程内不反复读盘。
- **冷启动不阻塞**：首次约 10~45 秒（R 全量探测最贵）。`/api/env/inventory` 永远只回缓存，
  没缓存就返回 `pending: true` 并**后台起线程**去扫，前端每 3 秒轮询（最多 60 次）自动刷新。
- **集群配置态永远现算**：`cached_cluster()` 只在缓存里写着 `configured: true` 且没过期时才直接用缓存；
  否则重新调 `cluster_configured()`（纯本地、不 SSH）。这样用户在 🖧 面板刚填完配置，
  环境管理面板不会因为"缓存还有 9 分钟"继续显示"未配置"。

### HTTP 接口

| 接口 | 行为 |
| --- | --- |
| `GET /api/env/inventory?refresh=0&cluster=1&scope=` | **只读缓存**，秒回；`refresh=1` 时顺手踢一次后台扫描并返回 `state.triggered`。返回 `stale: true` 表示"给的是上次清单、正在重扫" |
| `POST /api/env/verify` | **便宜地"确认一遍"**：指纹没变直接复用清单（实测 **1 ms**），变了才真扫（首次 40 s）。跑在线程里，不阻塞事件循环 |
| `GET /api/env/report.md` | 给人看的完整 markdown 报告（`?download=1` 加 attachment 头） |

响应里的 `agent_digest` 就是注入给 agent 的那段文本，`state` 是扫描状态（`idle` / `running` / `ok` / `error`）。

## 4. 工具 `env_inventory`（agent 侧只读入口）

```
env_inventory(action="overview" | "local" | "cluster" | "refresh" | "markdown" | "verify", node="")
```

- `overview`（默认）：本机 + 集群全量清单，`force=False`。**缓存新鲜就直接用（秒回）；缓存过期会真扫**
  （本机全量约 10~45 秒，agent 调用时会等这么久）——想要秒回的信息，每轮开场注入的缓存摘要里已经有了。
- `local` / `cluster`：只清点一边；`cluster` 可带 `node` 只探某个节点。
- `refresh`：`force=True`，真探测（约 10~45 秒）；人点面板的「🔄 重新扫描」走的就是它。
- `verify`：**分析开工前的"再确认一遍"**（铁律 25 第 4 步）。毫秒级指纹比对（解释器 /
  site-packages / R 库 / conda 目录的 mtime + 大小）——没变就直接复用清单、一次探测都不做；
  变了（装/卸包、换 R 版本）才自动重扫。实测首次 40 s、之后 **1 ms**。
  它不替代 `refresh`：`refresh` 是"我现在就要最新全量"，`verify` 是"确认还能不能复用"。
- `markdown`：返回完整报告文本，agent 可以直接贴给用户。

工具**永不抛异常**：任何失败都返回 `{"ok": false, "status": "error", "error": "类型: 消息"}`。
注册在 `toolset="memomics"`，和 `check_env` 等并列（`hermes-agent/toolsets.py` 的 memomics 列表 + registry 自动合并）。

## 5. 探测口径（和真实执行保持一致，这是最重要的设计约束）

> 探测结果如果和真正执行时不一样，这个清单就是骗人的。

- **R 包**：注入 `environment.json` 里**声明过的全部** `lib_user` / `lib_site`（不按版本过滤），
  和 `execute_r`（`KERNEL_POOL._r_lib_env()`）、`check_env._r_lib_env()` 完全同一个 R_LIBS。
  实测口径差异很大：按版本过滤只看到 494 个包且 `ComplexHeatmap` 判为缺失，注入全部声明库后是 **739 个包**（真实可加载）。
  每个 R 安装还会用 `find.package()` 对关键包逐个问"你到底从哪个库加载的"，把包所属库 ≠ 安装版本的记成
  **跨版本加载**（实测 `ComplexHeatmap` ← `C:/Users/23136/R/R-4.6.1-library`，ABI 不保证，前端单独警告）。
- **Python**：直接问解释器要 `sys.version` 和关键包版本；共享库声明会实测 `sys.path` 里有没有
  （`declared_shared_mounted`），**声明了但没挂载**要明说，否则用户以为靠它补的包能用。
- **CLI**：声明路径优先、其次 PATH，跑一次 `--version`；`ok=false` 分"登记了但没找到"（`declared_unavailable`）和
  "根本没装"（`missing`）——混在一起报会让人以为满屏都是问题。
- **conda**：除 `conda --version` 外，还带上 `environment.json` 的 `canonical_note`
  （实测：`conda 26.3.2` 命令能用，但规范口径是"已损坏（zstandard.backend_c 缺失）"，两者都要显示）。
- **集群**：走 `remote_cluster` 的 `nodes` / `check`，每节点最多探 `_MAX_CLUSTER_NODE_CHECKS = 4` 个
  （避免几十个节点时 SSH 排队把接口拖死），其余标记 `skipped`；节点连不上只写 warning，不失败。

## 6. 给用户看"要注意什么"

`_local_warnings()` + `_capabilities()` 产出 9 类人话警告（面板顶部「⚠️ 需要注意」+ 报告的 `## ⚠️ 需要注意`）：

- 主力 R 缺关键包 / 主力 Python 缺关键包（列出名字，并说明 `check_env` 用到时会自动装）；
- 跨版本加载的 R 包（ABI 风险）；
- `environment.json` 声明的共享库没被挂载（"靠它补的包现在其实用不了"）；
- conda 规范标注（已损坏）；
- `environment.json` 的四类标注：`R_legacy` / `R_deprecated` / `python_orphan` / 其它；
- 集群未配置 / 未启用（附 `config.yaml` 路径与配置方法）。

## 7. 怎么扩展

- **加一个生信 CLI**：在 `environment.json` 里加声明（`name` / `path` / `note`）即可，
  它会出现在 CLI 表里（`declared: true`），探测失败会归到 `declared_unavailable` 而不是"没装"。
- **加一个关键包**：改 `env_inventory._PY_KEY_PKGS` / `_R_KEY_PKGS`，缺包警告和 `capabilities` 会同步更新。
- **改缓存结构**：把 `_CACHE_VERSION` +1，老缓存自动作废。

## 8. 测试与验证现状

- 单测：`webui/tests/test_env_inventory.py`（33 个用例，`pytestmark = pytest.mark.unit`，全程不碰真实缓存）。
  用"**探测就报错**"的桩（`_boom`）钉死"HTTP 只读缓存、绝不探测"这条不变量；
  集群聚合喂 canned `nodes`/`check` JSON；含一条回归用例：
  **缓存里写着 `configured: false` 且没过期时，也必须现算配置态**（否则刚配好集群面板还显示未配置）。
- 真机实测：冷扫 45.3~46.4 秒；面板「🔄 重新扫描」实测 47 秒后 `state.status=ok`、清单时间刷新；
  `agent_digest` 1837 字符；`/api/env/inventory` 秒回（0.02 s）、`/api/env/report.md` 8657 字符。
- **agent 侧真机验证**（不是只看代码）：
  - `tools.registry` 里 `env_inventory` 的 `toolset=memomics`，`get_toolset("memomics", include_registry=True)`
    返回 36 个工具、含 `env_inventory`（和 `check_env` / `execute_r` / `execute_python` / `remote_cluster` 并列）；
  - 桩掉 `run_agent.AIAgent` 后调真的 `_create_agent()`：系统提示词 60638 字符，
    **末尾 1816 字符就是环境卡片**（`## 本机环境（env_inventory，…）`），`enabled_toolsets` 含 `memomics` ——
    即 agent 每轮开场确实带着"我有什么环境"。
- 前端 E2E（本机 Playwright，1680×950 与 1024×700）：三个 tab 正常渲染，
  **0 个 JS 报错 / 0 个 console error / 0 处横向溢出**，弹窗完整落在视口内、内容区内部滚动；
  中英切换正常（Environments / Local / Cluster / For the agent）。
- **未验证**：真实 SSH 集群路径（本机 `remote.enabled: false`、没有真实节点），
  节点探测/聚合逻辑只覆盖了 canned 数据；多节点并发、密钥失效、调度器差异要在真有集群时再验一次。
