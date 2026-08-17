# AGENTS.md — MemOmics 协作规范

给在此仓库工作的 AI 代理（及人类协作者）的规则。违反这些规则的修改会被退回。

## 黄金规则

1. **改完必须测**：任何代码修改后，运行 `.venv/Scripts/python.exe -m pytest`（Windows）
   或 `uv run pytest`（Linux/macOS）。测试不绿 = 修改未完成。
2. **先测试后重构**：涉及 `webui/server.py`、`hermes-agent/tools/` 的改动，
   先确认相关测试存在；无测试覆盖的新功能必须补测试（见 tests 规范）。
3. **不删备份**：删除 `.bak*` / `.backups/` 前先确认内容；重要改动前先
   `git commit`（不是 `git stash`）。
4. **提交要小、信息要实**：一个提交一件事；提交信息写清"为什么"和验证结果。

## 测试规范（P0-3 起）

- 测试目录：`webui/tests/`，pytest + marker 门禁（`pytest.ini`）
- 默认运行只跑 offline：`-m "not external and not network and not live_llm
  and not gpu and not ssh and not lab and not docker and not browser"`
- 需要真实外部资源的测试打对应 marker（`@pytest.mark.network` 等），
  默认不跑；手动 `-m network` 跑
- 测试会话必须清理：用 `conftest.py` 的 `new_session` fixture 或
  `cleanup_session()`（内存 + state.db + results 目录），禁止污染生产数据
- 新接口/新模块：至少覆盖 正常路径 + 错误路径 + 边界

## 架构红线

- `webui/server.py`（7398 行）是巨型文件：新增功能优先放
  `hermes-agent/tools/` 独立模块，server 只做薄路由
- 核心执行层（`code_execution_tool.py` / `persistent_kernel.py`）改动必须
  跑 `webui/tests/test_kernel_pool.py` + 集成验证（execute_code 真实调用）
- 结果完成契约：分析结束用 `POST /api/results/manifest` 提交
  `analysis_manifest`（版本化 + 溯源），不要只丢散文件
- 可写路径白名单：`MEMOMICS_ALLOWED_WRITE_ROOTS`（server 自动注入
  results+uploads）；沙箱 degraded 模式写白名单外路径会被拒

## 历史教训（必须记住）

- 2026-08-08：知识库图谱功能因"改完不提交"丢失两次（git 无记录），
  **完成一轮功能立即 git add + commit**
- `.gitignore` 曾有 `test_*.py` 规则导致测试文件入库失败——新增测试后
  用 `git status` 确认文件真的被跟踪
- `last_active` 曾用分钟精度导致会话排序不稳——时间戳一律秒精度
- 备份还原时"只移植功能块"会漏关联改动——还原后跑全量测试对照

## 修改清单（改代码前自查）

- [ ] 我知道要改哪些文件（不盲改）
- [ ] 相关测试存在或本次新增
- [ ] 改完跑全量 pytest
- [ ] 提交信息含验证结果
- [ ] `git status` 确认该入库的都入库了
