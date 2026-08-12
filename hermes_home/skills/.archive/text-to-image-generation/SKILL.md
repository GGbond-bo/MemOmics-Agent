---
name: text-to-image-generation
description: 文生图（text-to-image AI 绘画）— 调用已配置的 DashScope qwen-image-3.0 API，从文字描述生成概念图/示意图/封面插图。触发词：文生图、AI绘画、画个示意图、概念图、封面图、text-to-image、AI image generation、qwen-image、DashScope、通义万相。核心判定：有数据文件→代码画图（scipilot-figure-skill / nature-figure / scrna-cns-figure-design）；只有文字描述→文生图 API（本 skill）。精确标注图（基因名/箭头/通路）→ 推荐代码画（Graphviz），文生图文字易错。
category: bioinformatics
---

# 文生图（text-to-image via DashScope qwen-image）

## 什么时候用（判定逻辑 — 用户 2026-08 明确要求过）

```
用户要画图
  ├─ 有数据文件 → 代码画（数据可视化，像素忠于数据）
  │    ├─ CSV/通用数据 → scipilot-figure-skill
  │    ├─ Seurat/单细胞 → scrna-cns-figure-design
  │    └─ 发表级/投稿 → nature-figure
  ├─ 只有文字描述，要概念图/示意图/封面图 → 文生图 API（本 skill）
  │    ├─ 新会话（toolsets.py 注册了 image_gen toolset）→ 优先框架 image_generate 工具
  │    └─ 当前会话无 image_generate 工具 → execute_code 直接调 DashScope API
  └─ 精确示意图（基因名标注/箭头方向/通路逻辑）→ 推荐代码画（Graphviz 等）
       文生图 AI 生成文字/箭头经常出错，只适合文字不重要或无需标注的图
```

⚠️ **回答"画图逻辑/能力"类问题前必须调查**：先 `skills_list` + 读配置 + 查框架代码，禁止凭记忆声称某个 skill 存在。实测教训：SOUL.md 触发表引用的 `cns-visualization` **不存在**（skill_view 报 unsupported），实际画图 skill 只有 `scipilot-figure-skill` / `nature-figure` / `scrna-cns-figure-design`。

## 配置现状

- 配置文件：`<HERMES_HOME>/image_gen_config.json`（WebUI 设置页写入，优先级高于 config.yaml 的 image_gen 段）
- provider=dashscope, model=qwen-image-3.0（通义万相）
- 尺寸：square `1024*1024` / landscape `1280*720` / portrait `720*1280`（星号分隔，DashScope 格式）

## 正确调用（DashScope 原生 multimodal-generation）

- **端点**：`POST https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`
- **同步调用**：不要加 `X-DashScope-Async: enable` header（会 403 或走异步任务流，当前会话成功路径是同步）
- **不要用** OpenAI 兼容端点 `/images/generations`（404）也不要 `text2image/image-synthesis`（不是这个模型系列）
- **响应解析**：`result["output"]["choices"][0]["message"]["content"][0]["image"]` → 图片 URL → 下载保存
- key 读取路径：`cfg["dashscope"]["api_key"]`（**不是顶层**）

## 关键坑（已实测）

1. **API key 被 Hermes 工具层脱敏**：`read_file`/`execute_code` 输出里的 `sk-…` key 一律变成 `«redacted:sk-…»`。必须用 Python `open()` 直接读文件原始字节（脚本进程内读到的是真实内容），不要打印 key。
2. **key 在嵌套路径**：`image_gen_config.json` 里是 `dashscope.api_key`，不是顶层 `api_key`。
3. **qwen-image-3.0 走 multimodal-generation**，不是 OpenAI images 兼容口，也不是 text2image。
4. 框架自带 `image_generate` 工具（`toolsets.py` image_gen toolset，支持 9 家后端：dashscope/deepinfra/fal/krea/openai/openrouter/xai 等），但**工具集变更后新会话才暴露**；旧会话里只能用 execute_code 手动调 API。

## 脚本

`scripts/dashscope_text2image.py` — 可直接运行的文生图脚本（读配置→调 API→保存 PNG）。用法：
`python scripts/dashscope_text2image.py "科研风格的真核细胞示意图" --size 1024*1024 --out cell.png`

## 交付习惯

- 生成后报告保存路径 + 文件大小（用户会检查文件真实存在）
- 用户说"想调整"（风格/内容/尺寸）→ 直接重画，不追问
- 语言与用户一致（中文会话全程中文）
