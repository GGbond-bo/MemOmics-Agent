# 知识库可视化方案（已完成）

日期：2026-08-06
状态：✅ 已完成并验证
备份：
- `.backups/kb-visualize-20260806-120836/`（memomics/webui 旧副本改动前）
- `.backups/kb-visualize-prod-20260806-121751/`（生产文件改动前，md5 校验一致）

## ⚠️ 关键发现（实施中）
- **生产文件 = 顶层 `E:/MemOmics-Agent/webui/server.py` + `webui/index.html`**
- `memomics/webui/` 是旧副本（改它不生效）
- 用户实例（127.0.0.1:8899, PID 52772）跑旧代码，**需重启才生效**，未擅自重启
- 真实运行时 KB_DIR = `E:/MemOmics-Agent/memomics/knowledge_base`（单层，95 YAML）

## 目标
用户能在 MemOmics WebUI 中像浏览 Obsidian 一样查看知识库：目录树、结构化内容渲染、全文搜索、图谱视图。LLM 调用侧（search_knowledge）已完备，不动。

## 不做（明确排除）
- ❌ 不做编辑（只读浏览；写知识仍走 LLM 解析器）
- ❌ 不做 Obsidian vault 导出（P2 备选）
- ❌ 不动 search_knowledge / KB 数据 / LLM 链路

## 现状盘点（已存在，不重写）
| 已有 | 位置 |
|---|---|
| 📚 知识库导航入口 | index.html:417 |
| 目录树浏览 browseKb | index.html:2485 |
| 文件内容预览 previewKb | index.html:2504 |
| /api/kb 目录列表 | server.py:2844 |
| /api/file/read 文件读取 | server.py:2822 |

## 缺口（本次新增）
1. **模块A**：YAML 结构化渲染（现在纯文本）
2. **模块B**：全文搜索（95 个文件线性扫 <50ms）
3. **模块C**：图谱视图（cytoscape.js 力导向，节点=物种/组织/方向/分类/文件，边=层级+内容关联）

## 改动点
| 文件 | 改动 |
|---|---|
| memomics/webui/server.py | +3 只读路由：/api/kb/file、/api/kb/search、/api/kb/graph（~100 行） |
| memomics/webui/index.html | kb 视图：搜索框 + YAML 渲染 + 图谱 tab（~250 行） |

## 验证标准
- /api/kb/file：正常 YAML 返回 parsed，坏文件回退纯文本
- /api/kb/search：关键词命中 + snippet，毫秒级
- /api/kb/graph：节点/边数量合理，层级边+内容关联边
- 页面：搜索可点开、图谱可展开、CDN 失败降级文本链接
