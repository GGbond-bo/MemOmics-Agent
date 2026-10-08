# debate_analysis 失败 → 串行辩论回退（完整修复配方，可交付其他 agent）

> 2026-08-01 实测验证。症状：`debate_analysis` 连续 7 次 8/8 角色全失败。
> 本文档可直接交付给其他 agent 照着改。

## 一、诊断路径（照这个查，别瞎试）

```
1. 找到辩论实现 → webui/server.py
   - _sync_debate_env()（约 line 987，给辩论注入 API key 环境变量）
   - _call_role_parallel() / _call_llm_sync()（约 line 385-430，8 角色并行调用）

2. 找 provider 配置 → webui/provider_keys.json（多个 provider 时逐个测）

3. 找当前模型配置 → model_config.json 里的 _current_model（用户正在用的模型）
   → 对应 provider = deepseek 官方

4. 实际 curl 测两个 API 端点（用 provider_keys.json 里的 key，不打印 key）：
   ❌ dcs-cloud (https://dcsapi.dcs.cloud/v1/chat/completions) → 401 Invalid API key
   ✅ deepseek 官方 (https://api.deepseek.com/v1/chat/completions) → 200 OK
```

## 二、根因（两层）

### 根因 1（致命）：API key 注入 bug
`_sync_debate_env()` 遍历 provider_keys 时：
```python
for pid, cfg in provider_keys.items():
    if "dcs" in pid.lower():      # ← dcs-cloud 抢先匹配
        os.environ["OPENAI_API_KEY"] = cfg["api_key"]   # ← 注入失效 key！
        break
```
- dcs-cloud 的 key 已失效（401）
- 有效 deepseek key 存在 _current_model 配置里，但原代码放最后 fallback，永远执行不到
- 结果：8 个角色全部打到 dcs-cloud → 全部 401 → 全失败

### 根因 2（加重）：8 路并行调用
```python
with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
    results = list(executor.map(...))   # ← 8 路同时打 API
```
即使 key 正确，8 路并发也容易触发 provider 并发/配额限制。串行更稳。

## 三、修复

### 改动 1：修 `_sync_debate_env()` —— 优先当前模型的有效 key
```python
def _sync_debate_env():
    """给 debate 注入 API key。优先使用当前会话模型（有效 key），
    再回退 deepseek 官方 provider，最后才遍历 provider_keys。"""
    # 1) 优先：当前模型配置（用户正在用的 = key 必然有效）
    cm = getattr(server_state, "_current_model", None) or {}
    prov = cm.get("provider", "")
    if prov:
        for pid, cfg in (PROVIDER_KEYS or {}).items():
            if prov.lower() in pid.lower():
                os.environ["OPENAI_API_KEY"] = cfg.get("api_key", "")
                os.environ["OPENAI_BASE_URL"] = cfg.get("base_url", "")
                return True
    # 2) 回退：deepseek 官方
    for pid, cfg in (PROVIDER_KEYS or {}).items():
        if "deepseek" in pid.lower():
            os.environ["OPENAI_API_KEY"] = cfg.get("api_key", "")
            os.environ["OPENAI_BASE_URL"] = cfg.get("base_url", "")
            return True
    # 3) 最后 fallback：原逻辑（保留，不破坏）
    ...
```

### 改动 2：串行化辩论调用
```python
def _call_role_serial(tasks):
    """串行调用所有角色（避免并发限流）。顺序：先正方 3 → 再反方 4 → 最后 judge。"""
    results = []
    for t in tasks:
        r = _call_llm_sync(t["prompt"], t["system"], t["role"])
        results.append(r)
    return results
```

### 改动 3：reasoning_content fallback（flash 模型必需）
```python
content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
if not content:   # ← deepseek-v4-flash 的 content 可能为空，回答在 reasoning_content
    content = data.get("choices", [{}])[0].get("message", {}).get("reasoning_content", "")
```

### 改动 4：独立串行辩论脚本（不依赖 server，重启 webui 前就能用）
`scripts/run_serial_debate.py` 直接读 `model_config.json` 的 key（绕过 _sync_debate_env bug）：
- 正方 3 角色（生物学/统计学/生信），各自独立 HTTP 调用，messages 只含自己的 prompt
- 反方 4 角色（生物学/统计学/生信/历史），互不可见也看不到正方
- 裁判：把所有 7 方论据拼进 prompt → 独立 LLM 调用 → 分数 + 裁决 + 置信度
- 归档到 `results/<session>/log/debate_<timestamp>_serial_<topic>.json`

## 四、验证（修完必测）

```bash
# 1. 验证两个 provider key 有效性（curl 直连）
curl -k https://api.deepseek.com/v1/chat/completions \
  -H "Authorization: Bearer <deepseek_key>" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'
# 期望：200 + content 非空

# 2. 验证 _sync_debate_env 注入的是哪个 key
# 期望：OPENAI_BASE_URL = https://api.deepseek.com/v1（不是 dcsapi.dcs.cloud）

# 3. 完整跑一次辩论 → 8/8 角色成功 + 归档 JSON 生成（pro 3 + con 4 + judge 都有内容）
```

## 五、实测结果

| 项 | 修复前 | 修复后 |
|----|--------|--------|
| provider | dcs-cloud（401） | deepseek 官方（200） |
| 调用 | 8 路并行 | 串行（pro→con→judge） |
| 辩论 | 7 次 8/8 全失败 | 8/8 全部成功（302.7s） |
| 归档 | 无 | debate_*.json（80KB，含裁判裁决 verdict=modify） |

## 六、关键文件

| 文件 | 改什么 |
|------|--------|
| `webui/server.py` | `_sync_debate_env()` 优先 _current_model；`_call_role_parallel` 改串行 |
| `webui/provider_keys.json` | 核对 dcs-cloud key（已失效，可删或更新） |
| `webui/model_config.json` | 确认 _current_model 的 provider 是 deepseek |

> ⚠️ server.py 修复需重启 webui 服务才让 debate_analysis 工具生效；不重启可用独立串行脚本。
