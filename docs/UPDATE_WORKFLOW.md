# MemOmics-Agent 更新/发布工作流（持久记录，新会话必读）

> 本文档 + hermes_home/AGENTS.md 为「跨会话记忆」：任何会话接手「更新/打包/发布」任务时，先读本文。
> 最后更新：2026-08-31（当天最新 tag = v2026-08-31）

## 1. 更新什么、更新到哪里

| 项 | 规则 |
|---|---|
| 默认只更新 | MemOmics-update.zip（老用户一键更新/解压覆盖代码，保留 hermes_home/results/.venv） |
| 全量包 | MemOmics-Windows.zip / Linux.tar.gz / macOS-arm64 / macOS-x86_64 / Cluster.tar.gz —— 仅新装用户需要；一般不必每次重打，但同一天发布时建议全打保持一致 |
| 更新到哪里 | GitHub release：https://github.com/GGbond-bo/MemOmics-Agent/releases/tag/v<当天日期> |
| 版本号 | 必须=真实当天日期（如 v2026-08-31）；禁止未来日期、禁止旧 tag 覆盖（WebUI 按 tag 字符串比对） |
| 本地 VERSION | 打包时写 v<当天>；打完恢复 vdev-<当天> |

## 2. 标准流程（每一步都做）

1. 改代码 → 跑离线测试（pytest 全量相关套件，见 §0 提示）；
2. 编译检查：python -m py_compile webui/server.py conclusion_store.py；
3. VERSION 改为 v<当天>；
4. 打包：E:\release\_rebuild_v4.ps1（只 update 用 -Win；全量不带开关）；
5. 打包前确认 requirements.txt UTF-8；打包脚本内置凭据守卫（禁止 provider_keys/auth/weixin/channel_directory/model_config/state.db 等进包）；
6. 验证：E:\release\_test_update.ps1 -Version v<当天>（若脚本 exit 2 但 booted/HTTP 200 通过，再手动解包启动一次兜底）；
7. 更新 E:\release\RELEASE_NOTES.md（标题=当天、追加变更、同步全部资产 SHA256）；
8. 发布：gh release create v<当天> --repo GGbond-bo/MemOmics-Agent --notes-file E:/release/RELEASE_NOTES.md；再 upload（--clobber）；同天全量包按需一并 upload；最后 release edit 更新说明；
9. 恢复 VERSION=vdev-<当天>；
10. 提交 docs/UPDATE_WORKFLOW.md + hermes_home/AGENTS.md + VERSION 到 git。

## 3. 绝不打包的内容（凭据守卫 + 手动双查）

- provider_keys.json、auth.json、weixin_account.json、channel_directory.json、model_config.json、state.db；
- hermes_home/sessions/、hermes_home/memories/、results/、uploads/、work/、.memory/、.install_path；
- 本机路径（C:/Users/23136、E:/MemOmics-Agent、E:/R-libs）、真实 API key；
- 用户测试数据/专利数据/微信聊天/个人记忆文件。

> 打包后务必逐个 zip/tar 解包抽查名字再上传。

## 4. 更新历史（最近）

| 日期 | tag | 内容 |
|---|---|---|
| 2026-08-31 | v2026-08-31 | 记忆分层 L0 结论/失败注册表 + L3 索引、待确认绑定、L2 最近轮速览、辩论 v2、BGI 技能、渲染/超时修复、全量 5 包重建 |
| 2026-08-27 | v2026-08-27 | 早期辩论/技能/稳定性（历史） |

## 5. 备注

- gh 路径：C:/Users/23136/AppData/Local/gh-cli/bin/gh.exe；默认代理 127.0.0.1:6478，不可用时 unset 后直连（已实测可用）。
- _test_update.ps1 尾部 exit 2 历史怪象：功能校验通过即可；发布前再手动解包启动一次。
- Windows 编码坑：.bat 是 GBK；含中文 .ps1 必须 UTF-8 BOM。