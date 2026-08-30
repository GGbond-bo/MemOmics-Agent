# MemOmics Agent — 项目上下文

## 项目路径（动态：由安装位置决定，启动时自动扫描写入）
- 项目根目录：`{MEMOMICS_ROOT}`（hermes_home 的父目录，见 hermes_home/.install_path）
- Hermes 框架：`{MEMOMICS_ROOT}/hermes-agent/`
- 知识库：`{MEMOMICS_ROOT}/memomics/knowledge_base/`
- 技能库：`{MEMOMICS_ROOT}/hermes_home/skills/bioinformatics/`
- 分析结果：`{MEMOMICS_ROOT}/results/`
- 文献下载：`{MEMOMICS_ROOT}/work/papers/`

> **重要**：`{MEMOMICS_ROOT}` 不是固定值，而是**当前安装目录**。每次启动时 server.py 会自动扫描并写入 `hermes_home/.install_path`。Agent 读取 `.install_path` 获取真实路径，**绝不使用硬编码路径**。

## 工作流约定
1. 分析前先 scan_data 扫描数据
2. 分析前先 search_knowledge 搜索知识库
3. 分析结果按 results/<模块>/<方法>/{figures,results,scripts,data,log} 存储
4. 每个子分析执行前后铁轨审查
5. 待办完成后标记 completed
6. **所有输出（脚本、图、报告）都在 `results/<sid>/` 下，绝对不放桌面、不放 work/、不放其他任意位置**
## 更新 / 发布（新会话必读）
- 默认只更新 MemOmics-update.zip（老用户一键更新）；全量 5 包仅新装机需要。
- 版本号 = 真实当天日期（如 v2026-08-31）；禁止未来日期/旧 tag 覆盖。
- 完整流程 + SHA + 坑位见 docs/UPDATE_WORKFLOW.md（打包时随包发布）。
- 绝不打包：API key / provider_keys / auth / weixin / channel_directory / model_config / state.db / sessions / results / uploads / work / .memory / 本机路径 / 测试数据。
- 最新：2026-08-31 · v2026-08-31（记忆分层 L0 结论失败注册表 + L3 索引、待确认绑定、L2 轮速览、辩论 v2、BGI 技能、渲染/超时修复）。
