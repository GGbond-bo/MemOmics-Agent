# 环境声明机制（用户点名"补充到环境管理"时的落点）

> 来自 2026-10-08 ssh3 会话。用户原话："把这些信息默认补充到环境管理去，以后新会话，都能及时调用、补充、更新对应的环境和安装包信息"。

## 1. 两层结构 —— 别写错层

| 层 | 文件 / 模块 | 谁生成 | 刷新 | 答什么问题 |
|---|---|---|---|---|
| **持久声明** | `E:/MemOmics-Agent/environment.json` 的 `cluster` / `env_notes` 段 | **人/用户**（或 agent 代写） | 永不自动覆盖 | **该用哪个环境、别碰哪些**（用户意图） |
| **实时清点** | `memomics/bio_tools/env_inventory.py` 缓存（`hermes_home/env_inventory.json`） | 探针自动 | 本机 1h / 集群 10min | 现在有什么、版本、负载 |

**判据**：写进缓存 = 下次重扫被覆盖 = 没落库。凡是"用户指定的固定映射 / 别用某环境"这类**意图**，一律进 `environment.json`。

`environment.json` 是本机环境唯一真源，`scripts/validate_env.py` 读它做三阶段验证（读缓存→验证→自动修复）→ **改它之后必跑**：
```bash
.venv/Scripts/python.exe scripts/validate_env.py --verbose   # 期望 exit=0
```

## 2. `cluster` 段 schema（实际落盘形态）

```json
"cluster": {
  "_rule": "只用声明的环境；要换先问用户",
  "nodes": {
    "ssh3": {"host": "...", "user": "zhangbo11", "workdir": "/hwfssz3/PS_JLU/zhangbo",
              "scheduler": "SGE 8.1.9", "conda_activate": "source <conda_root>/bin/activate <env>"}
  },
  "policy": {
    "RNA":  {"r_env": "R4.41",  "r_version": "4.4.1", "py_env": "sc-analysis", "scope": "Seurat .rds + AnnData .h5ad"},
    "ATAC": {"r_env": "R4.3.3", "r_version": "4.3.3", "scope": "ArchR 1.0.3"}
  },
  "probed_not_assigned": { "ARCHR": "...", "scenic": "..." },
  "pitfalls": ["R441 是错名，实为 R4.41", "envs/cellchat 里没有 CellChat", "..."]
}
```

约定：`_` 前缀键（`_rule`）是非数据元信息，渲染时跳过；`policy` 只在有 `r_env`/`py_env` 时算"已锁定"。

## 3. 读写接口（`env_inventory.py`）

| 函数 | 作用 |
|---|---|
| `declared_env()` | 读 `cluster` + `env_notes` 两段，没有返回 `{}`（空段不算声明） |
| `save_declared(payload)` | 面板写回。`payload = {"declared": {...}}`；**只认这两段**，其余键原样保留；写前 `copy2` → `.bak`，写后 `os.replace` 原子替换；`_last_updated` 打时间戳；超 64KB 拒绝 |

- 非法 payload（非 dict / 缺 `declared` / 段名不在白名单 / 段为空 / 超限）→ **抛 `ValueError` 且一个字都不写**（测试断言文件字节不变）。
- `build_report(cluster=True)` 把 `declared_env()` 挂到 `report["cluster"]["declared"]`；**`cluster=False` 时不能凭空多出 `declared`**（否则面板把"没查"当"查过了"）。
- 三处下发共用：面板（`cluster.declared`）、markdown 报告（`_declared_md_lines()`）、agent 卡片（`_declared_digest_lines()`，**压缩成 1–3 行**，别撑爆 2500 字预算）。

## 4. WebUI 面板接线（要新增端点时照抄这套）

- 后端：`webui/server.py` 加薄路由 `POST /api/env/declared` → `await asyncio.to_thread(mod.save_declared, payload)`（小文件 IO 也别占事件循环，仓库惯例走 `to_thread`）。
- 🔴 **必须同步 `webui/middleware_routes.json`**：`"/api/env/declared": "local"`。这是**冻结清单**，
  `webui/tests/test_p2_1_middleware.py::test_frozen_route_manifest_matches_real_app` 会拿真实 app 审计，
  漏登记 = drift 失败。重生成：`python webui/entry_middleware.py --snapshot`。
- 前端：`webui/index.html` 加 `emDeclHtml/emDeclEdit/emDeclApply/emSaveDecl` + 表单字段。
  **新用户场景**：集群 `pending` / 未配置时也要够得着填写入口（`emDeclHtml(cl)` 必须排在 `if (!cl.configured)` **之前**），否则第一次用的人没有环境可填。
- 中英文案 `em_*` key **必须成对**（有测试比对 keys_zh == keys_en 且 ≥20 个）。

## 5. 坑

- 写完不跑 `validate_env.py` → 不知道有没有破坏 paths 段。
- 只改 `middleware_routes.json` 不核对真实 app → 冻结清单 drift 测试失败。
- 把"别用某环境"写进缓存或只写进对话 → 新会话丢失（本轮就是因为此前只落进会话锚点，用户才要求"补充到环境管理"）。
- 改这份声明时顺手重排/润色其它段 → 它是环境真源，**只改指定项**。