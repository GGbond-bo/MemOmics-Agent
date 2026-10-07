# DCS Cloud API 参考（2026-09-11 实测）

DCS Cloud 是用户使用的聚合平台（"一个 key 切换所有模型"），base_url:
`https://dcsapi.dcs.cloud/api/aigress/unified/v1`

## 端点（用户提供的 curl 原样）

### Responses API 格式
```bash
curl -X POST 'https://dcsapi.dcs.cloud/api/aigress/unified/v1/responses' \
-H 'Content-Type: application/json' \
-H 'Authorization: Bearer <YOUR_API_KEY>' \
-d '{
    "model": "deepseek-flash",
    "input": "hello",
    "stream": true
}'
```

### Chat Completions 格式（OpenAI 兼容，实测可用）
```bash
curl -X POST 'https://dcsapi.dcs.cloud/api/aigress/unified/v1/chat/completions' \
-H 'Content-Type: application/json' \
-H 'Authorization: Bearer <YOUR_API_KEY>' \
-d '{
    "model": "deepseek-flash",
    "messages": [{"role": "user", "content": "hello"}],
    "stream": true
}'
```

## 实测记录（2026-09-11）

- `POST .../chat/completions` with `model: "deepseek-flash"`, `max_tokens: 10`, `stream: false`
  → **HTTP 200**，响应 `model` 字段归一化为 `deepseek/deepseek-flash`
  → content 为空的原因大概率是 max_tokens=10 太小或内容落在 reasoning_content，
    不视为失败；HTTP 200 + model 字段回显 = 模型名有效
- api key 来自 `hermes_home/provider_keys.json` 的 `dcs-cloud` 条目
  （key 前缀 sk-MoS…，有效）
- 历史警告（2026-08 会话）：dcs-cloud 的 key 曾因过期返回 401——添加模型前
  先实测端点，401 时先找用户更新 key

## 已知模型（添加后）

实测验证过 API 接受 `deepseek-flash`（响应名 `deepseek/deepseek-flash`）。
配置中 dcs-cloud 的 models 列表（`webui/server.py` `_CHINA_PROVIDERS` +
`hermes_home/config.yaml` custom_providers）已有：
deepseek-v4-pro / deepseek-v4-flash / deepseek-flash / glm-5.2 / glm-5.1 /
kimi-k3 / kimi-k2.7-code / kimi-k2.6 / qwen3.8-max / qwen3.7-max / MiniMax-M3

## 其他 provider 参考

- opencode-go（聚合）base_url `https://opencode.ai/zen/go/v1`，需要
  `extra_headers: x-opencode-session`（uuid，缺了 400 MissingSessionID）
- deepseek 官方 base_url `https://api.deepseek.com/v1`