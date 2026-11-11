# 会话命名与提问历史导航修复

日期：2026-11-12

## 基线与范围

- 官方仓库：GGbond-bo/MemOmics-Agent。
- 通过 GitHub Releases API 核对的最新正式发布：v2026-11-10。
- 基线提交：0a8b2f232290e051c037189efa13a8163b4f104d。
- 本地分支：codex/session-name-history-20261112。
- 本地源码：D:\mem20261105\work\MemOmics-source。
- 用户本次明确要求仅修本地源码，暂不提交 PR。没有更新运行安装版或重打冻结的 ZIP。

## 需求与实现

1. 用户手动命名后，首条消息、后台 LLM 自动命名、结果目录信息和微信首条消息不得覆盖名称；压缩续接后的会话也继承手动命名保护。
2. 手动名称与来源标记在同一数据库事务中保存；失败时不得显示改名成功。后台模型调用在锁外执行，写回时重新检查当前会话和手动来源。
3. 左侧刻度组顶部新增“…”按钮，与刻度整体居中。点击展开旁侧小窗，按顺序显示带编号的提问摘要，支持内部滚动、点击定位、当前项高亮和关闭。
4. 全量历史列表使用完整历史的编号，避免把分页窗口中的相对轮次当成完整历史编号。加载响应需检查会话与视图代次，防止切会话后串页；加载期间出现流式输出时避免覆盖当前聊天 DOM。
5. 手动改名后的前端拒绝迟到的自动标题事件。历史摘要采用安全文本渲染。

## 验证状态

最终审核：通过，无剩余阻断项。主代理与独立审核者均复跑了关键回归。

| 验证 | 结果 |
| --- | --- |
| `python webui/tests/test_title_write_regression_isolated.py` | 9/9 通过；真实函数抽取、隔离 SQLite、并发和事务失败验证 |
| `node webui/tests/conversation_rail_ui.test.js` | 通过，包含 300 问分页历史、关闭/跳转/会话隔离 |
| `node webui/tests/session_title_event_ui.test.js` | 通过，迟到自动/未标记事件保护与 manual 更新 |
| `node webui/tests/inline_scripts_v4_parse.test.js` | 5 个内联脚本语法通过 |
| `node webui/tests/project_sessions_ui.test.js` | 通过 |
| `node webui/tests/session_empty_reuse_v4_ui.test.js` | 通过 |
| Python 编译检查 | 通过；第 68 行原有无效转义 SyntaxWarning 未扩修 |
| `git -c core.whitespace=cr-at-eol diff --check` | 通过，保留原有 CRLF 文件格式 |

后端还验证了中间压缩节点手动命名后的继承、包含特殊字符的重名标题、保存失败不改内存、共享连接锁和自动/手动竞争。

修前发布版基线：
- conversation_rail_ui.test.js：通过。
- session_mutation_guards_v2.test.js：已有失败，testLateGoalAndTodoResponsesAreDropped，断言 switchSession must reset goal-bar ownership immediately after switching（原第 113 行）。不属于本次改动范围。

- `session_lifecycle_v2.test.js`：在 saveModel 的既有 mock 路径中失败（switchCall undefined，第 171 行）。实现者以 `git show v2026-11-10:webui/index.html` 注入同一测试重现，确认是发布版基线失败。

## 验证边界

- 后端测试使用抽取的真实函数与隔离 SQLite，不导入有启动副作用的 server.py，不使用个人模型、集群账号、聊天历史或现用数据库。
- 浏览器尝试访问 http://127.0.0.1:18999/preview 时，被保存的浏览器权限策略拒绝；未尝试绕过策略。因此没有完成实际浏览器视觉验收。
- 临时隔离预览服务已停止。
- 源码目录中已有的 memomics_home 未跟踪运行文件不纳入修复，不清理或提交。
- 本次不声称完整上游测试集全部通过，也不声称已完成安装版实机验收。
