---
name: dashscope-image-generation
description: 通过 DashScope 通义万相 API (qwen-image-3.0) 做文生图。使用场景：用户说"文生图/AI绘画/生成图片/画个图"(非生信数据图)时，先查本机已配置的 DashScope 文生图 API，不要先建议安装 ComfyUI 等本地工具。
when_to_use: 用户要求文生图/图像生成/AI绘画/生成概念图或示意图；或需要调用 qwen-image 系列模型；或本机 image_gen_config.json 已配置 DashScope 文生图 API
---

# DashScope 文生图（qwen-image-3.0）

本机已配置 DashScope 文生图 API。用户说"画图/文生图"时**先查 `hermes_home/image_gen_config.json`，确认已有 API 再动手，不要先建议安装 ComfyUI/本地模型**（2026-08-12 用户纠正："但是我不是有图像生成的API吗？"——Agent 未先查配置就推荐了本地安装）。

## 关键事实

- 配置文件：`MEMOMICS_HOME/hermes_home/image_gen_config.json`
  - provider: `dashscope`（阿里云通义万相），model: `qwen-image-3.0`
  - size: `1024*1024`（横图 `1280*720` / 竖图 `720*1280`）
  - api_key 存在（read_file 输出会 redact 为 `«redacted:sk-…»`，脚本里用 json.load 读真实值，不要依赖 read_file 明文）
- 正确端点：`https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`（同步返回，无需轮询任务）
- 结果保存约定：`MEMOMICS_HOME/results/<sid>/image_gen/`，不丢桌面

## 调用

复用脚本 `scripts/generate_image.py`：

```bash
python scripts/generate_image.py "一只金毛幼犬在向日葵田里，写实，黄金时刻光线" --size 1024*1024 --out MEMOMICS_HOME/results/<sid>/image_gen/
```

Payload（multimodal-generation 格式）：

```json
{
  "model": "qwen-image-3.0",
  "input": {"messages": [{"role": "user", "content": [{"text": "PROMPT"}]}]},
  "parameters": {"size": "1024*1024", "n": 1}
}
```

响应解析：`output.choices[0].message.content[]` 数组，元素含 `image`(OSS 临时 URL 或 data:base64) 和 `type: "image"`。URL 有 Expires 签名，必须立即下载保存。usage 里有 output_width/height 可验证尺寸。

## Pitfalls

1. ⛔ OpenAI 兼容端点 `/compatible-mode/v1/images/generations` → **404**（qwen-image-3.0 未暴露在该端点，2026-08-12 实测）
2. ⛔ `/api/v1/services/aigc/text2image/image-synthesis` → **400 InvalidParameter "url error, please check url"**（qwen-image 系列不支持该端点，2026-08-12 实测）
3. ⛔ **禁止加 `X-DashScope-Async: enable` header**（异步模式）→ **403 Forbidden**。multimodal-generation 对 qwen-image-3.0 是同步返回，直接 POST 即可，不要 header + task_id 轮询那套（2026-08-12 实测：加了 async header 直接 403）
4. ⛔ **api_key 在嵌套路径 `cfg["dashscope"]["api_key"]`**，不是顶层 `cfg["api_key"]`。用顶层读取会得到空 key → 401 Unauthorized。且 read_file 工具输出对 sk- 脱敏，必须用 Python `open()` 读原始字节（2026-08-12 实测踩坑）
5. 先查配置再建议安装：用户已有 API 时不要推荐 ComfyUI/本地模型/在线付费服务
6. 生信"画图"（UMAP/热图/火山图等）≠ 文生图：先按 SOUL 画图 Skill 选择策略分流，用户明确说"文生图/AI绘画"才走本 skill
7. ⚠️ **答画图逻辑/能力类问题前必须调查**：2026-08-12 用户问"什么时候用画图API什么时候用正常生图"，Agent 凭记忆列了 `cns-visualization` → 用户纠正"你没有调查"。实测 `cns-visualization` **不存在**（skills_list 无此名、skill_view 报 unsupported、磁盘无此目录），SOUL.md 画图触发表已过时。答此类问题先 `skills_list` + 读配置 + 查框架代码，禁止凭记忆声称某 skill 存在。

## 判定逻辑（用户 2026-08-12 明确要求过的分流）

```
用户要画图
  ├─ 有数据文件 → 代码画（数据可视化，像素忠于数据）
  │    ├─ CSV/通用数据 → scipilot-figure-skill
  │    ├─ Seurat/单细胞 → scrna-cns-figure-design
  │    └─ 发表级/投稿 → nature-figure
  ├─ 只有文字描述，要概念图/示意图/封面图 → 文生图 API（本 skill）
  │    ├─ 新会话（toolsets.py 注册了 image_gen toolset）→ 优先框架 image_generate 工具
  │    └─ 当前会话无 image_generate 工具 → 脚本直调 DashScope API（见上）
  └─ 精确示意图（基因名标注/箭头方向/通路逻辑）→ 推荐代码画（Graphviz 等）
       文生图 AI 生成文字/箭头经常出错，只适合文字不重要或无需标注的图
```

实际可用的画图 skill（不存在 cns-visualization）：`scipilot-figure-skill` / `nature-figure` / `scrna-cns-figure-design`。

## 验证

生成后检查：文件存在 + 大小 > 100KB（PNG 正常 ~1-2MB）+ 尺寸符合 size 参数。无产出文件 = 调用失败，读完整响应排查（HTTP 4xx 多半是端点/参数问题）。
