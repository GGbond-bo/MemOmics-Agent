# 改 WebUI 后怎么验（`webui/server.py` / `index.html` / `middleware_routes.json`）

> 来自 2026-10-08「环境声明接进「🧩 环境管理」面板」一役。AGENTS.md 黄金规则：改完必须跑 pytest。

## 0. 仓库既有约定（先知道，别自创）

`webui/tests/` **不启 FastAPI**（server.py 两万行，太重）。测试只有三种形态：
1. 模块函数级（真读真写，用 `tmp_path` + `monkeypatch`）；
2. 源码**静态断言**（`open(server.py).read()` / `_read_index()` 里 `assert token in text`）；
3. 冻结清单审计（`test_p2_1_middleware.py::test_frozen_route_manifest_matches_real_app` 拿**真实 app** 比对 `middleware_routes.json`）。

所以别写 `TestClient` 端到端测试——不符合约定，也重。按 1–3 形态补。

## 1. pytest 的结论行会被 warnings 淹掉 🔴

**现象**：`pytest ... | tail -30` 出来**全是 `DeprecationWarning: on_event is deprecated`**，看不到 `passed/failed`。
本轮第一次跑就踩了：exit_code 是 0，但输出里一个结论行都没有，等于"不知道过没过"。

**做法**：
```bash
.venv/Scripts/python.exe -m pytest <target> -q -p no:warnings 2>&1 | tail -15; echo "EXIT=${PIPESTATUS[0]}"
```
- `-p no:warnings` 关掉 warning 汇总；`-q` 让每个测试只出一个点。
- **`PIPESTATUS[0]` 必须带上** —— 管道后 `$?` 是 `tail` 的退出码，不是 pytest 的。不加就等于没验。
- 汇报时给**点状进度行 + passed 数 + EXIT**，不要只说"测过了"（用户会审计这一步，原话"你都不检查的"）。

## 2. 新增端点必须登记冻结路由清单 🔴

`webui/middleware_routes.json` 是**冻结的全部路由模板与归类**：
- 新增 `@app.post("/api/xxx")` → 必须加 `"/api/xxx": "local"`（或 `public` / `session`）。
- 漏了 → `test_frozen_route_manifest_matches_real_app` 报 `added != []` 失败。
- 重生成：`python webui/entry_middleware.py --snapshot`（会重写整份清单）。
- 归类不能乱写：本机/会话相关的走 `local`，无需登录的走 `public`。
- 手改清单后**必须真跑那个审计测试**，别假设顺序/归类对。

## 3. 内联 JS 改完用 `node --check` 自检

`webui/index.html` 里有 3 个内联 `<script>` 块（主块 1.5 万行）。改完抽块 → 临时 `.js` → `node --check`：
```bash
.venv/Scripts/python.exe <skill_dir>/scripts/check_index_inline_js.py
```
输出形如 `block 0: OK (212 lines)` … `RESULT: OK`。**别开浏览器试**（慢且看不到语法错误行）。
脚本自带仓库根自动发现（向上找含 `webui/index.html` 的目录），放在哪都能跑。

## 4. `patch` 模糊匹配可能改错缩进 → 用确定性脚本兜底

**现象**：对缩进敏感的块（`if/else` 多分支、表格行）用 `patch` 连续替换，模糊匹配（9 策略）会**把缩进改歪**，
而且 diff 看着"成功"。本轮一次中招，产出文件语法已坏。

**做法**：同一段连续 patch 失败/可疑 → **停手**，改用确定性脚本（读文件 → `re.sub` 精确替换 → 写回，保留 CRLF），
紧跟一次编译校验（`py_compile` / `node --check` / `json.load`）。**不要第三次再试同一种 patch**。

## 5. 全量 pytest 失败归因（别急着说"是我的改动"）

本轮全量 3 个失败，**没有一个来自我改的 5 个文件**：
- `test_skills_registry.py::test_index_is_reproducible_from_committed_metadata` → **新建的 skill 目录还没 `git add`**（`skill.json` 未入库），全新 checkout 的索引会多/少行。修法是 `git add`，不是改代码。
- `test_skill_routing_matrix.py::test_every_red_skill_is_covered` → 每个 **RED 技能**必须在 `webui/tests/fixtures/skill_routing_matrix.json` 的 `cases` 里有一条真实用户口径用例（确属不可测的写 `coverage_exempt` + 理由）。
- 剩下那条 DNS/netguard 与本任务无关。

**归因方法**：先看失败断言指向的文件/目录，比对该文件是否在自己的改动清单里；不放心就跑单条失败测试看断言原文。
汇报时**明确写出"与本次改动无关 + 原因"**，不要把别人的失败认领成自己的。

## 6. 相关

- 环境声明端点（`POST /api/env/declared`）的完整接线配方 → `remote-cluster-execution` 的 `references/environment-declaration.md`。
- 中英文案 `em_*` key 必须成对（有测试比对 `keys_zh == keys_en` 且 ≥20 个），加前端文案时一起补。