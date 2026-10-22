# -*- coding: utf-8 -*-
"""编程套餐（Code Plan）provider 目录 + 模型自动拉取（2026-10-07）。

背景：主流厂商的订阅制 AI 编程套餐（Kimi For Coding、GLM 编程套餐、阿里云
百炼 Coding、阶跃 Step Plan）使用**独立端点 + 独立 key 体系**，与按量计费的
开放平台端点不通用（sk-kimi- 前缀的 key 只在 api.kimi.com/coding 生效等）。
本模块把这些套餐作为 WebUI「设置 → API 提供商」里的独立分组，并在用户保存
key 后自动向套餐端点拉取可用模型（拉到的模型会并入模型选择器与 MemOmics 底座）。

条目字段（与 server._CHINA_PROVIDERS 同构 + 扩展）：
  id/name/api/env_var/group/models —— 基础字段
  note      —— 设置页展示的套餐说明/使用限制
  key_hint  —— key 前缀提示（输入框 placeholder）
  auto_pull —— 保存 key 后自动拉模型
  models_url—— 覆盖默认 /models 候选（特殊网关）
  extra_headers —— 拉模型/请求所需额外请求头

端点依据（2026-10 实测）：hermes-agent providers 目录（kimi-coding / zai /
alibaba-coding-plan / stepfun 插件与 auth.py 常量），以及 DSH 插件
@linxin666/dsh-usage 的套餐适配器实现。
"""

from __future__ import annotations

import json as _json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

CODING_PLAN_GROUP = "💳 编程套餐"

_KIMI_MODELS = [
    {"id": "k3", "name": "Kimi K3（编程套餐旗舰）", "reasoning": True, "tool_call": True},
    {"id": "kimi-k3", "name": "Kimi K3（别名）", "reasoning": True, "tool_call": True},
    {"id": "kimi-k2.7-code", "name": "Kimi K2.7 Code", "reasoning": True, "tool_call": True},
]

_GLM_MODELS = [
    {"id": "glm-5.2", "name": "GLM-5.2（旗舰）", "reasoning": True, "tool_call": True},
    {"id": "glm-5.1", "name": "GLM-5.1", "reasoning": True, "tool_call": True},
    {"id": "glm-5v-turbo", "name": "GLM-5V Turbo", "reasoning": True, "tool_call": True},
    {"id": "glm-4.7", "name": "GLM-4.7", "reasoning": True, "tool_call": True},
]

_ALIBABA_CODING_MODELS = [
    {"id": "qwen3-coder-plus", "name": "Qwen3 Coder Plus", "reasoning": True, "tool_call": True},
    {"id": "qwen3-coder-next", "name": "Qwen3 Coder Next", "reasoning": True, "tool_call": True},
    {"id": "qwen3.7-plus", "name": "Qwen3.7-Plus", "reasoning": True, "tool_call": True},
    {"id": "qwen3.6-plus", "name": "Qwen3.6-Plus", "reasoning": True, "tool_call": True},
    {"id": "qwen3.5-plus", "name": "Qwen3.5-Plus", "reasoning": True, "tool_call": True},
    {"id": "kimi-k2.5", "name": "Kimi K2.5（套餐内第三方）", "reasoning": True, "tool_call": True},
    {"id": "glm-5", "name": "GLM-5（套餐内第三方）", "reasoning": True, "tool_call": True},
    {"id": "glm-4.7", "name": "GLM-4.7（套餐内第三方）", "reasoning": True, "tool_call": True},
    {"id": "MiniMax-M2.5", "name": "MiniMax M2.5（套餐内第三方）", "reasoning": True, "tool_call": True},
]

_STEP_MODELS = [
    {"id": "step-3.7-flash", "name": "Step 3.7 Flash", "reasoning": True, "tool_call": True},
    {"id": "step-3.5-flash", "name": "Step 3.5 Flash", "reasoning": True, "tool_call": True},
    {"id": "step-3.5-flash-2603", "name": "Step 3.5 Flash (2603)", "reasoning": True, "tool_call": True},
]

CODING_PLAN_PROVIDERS: List[Dict[str, Any]] = [
    {
        "id": "kimi-coding-plan",
        "name": "Kimi 编程套餐 (Kimi For Coding)",
        "api": "https://api.kimi.com/coding",
        "env_var": "KIMI_API_KEY",
        "group": CODING_PLAN_GROUP,
        "note": ("订阅制套餐：key 以 sk-kimi- 开头，端点走 Anthropic Messages 协议"
                 "（底座已自动适配）。保存后自动拉取套餐模型；用量窗口见上下文窗口面板。"),
        "key_hint": "sk-kimi-…",
        "auto_pull": True,
        "models_url": "https://api.kimi.com/coding/v1/models",
        "extra_headers": {"User-Agent": "claude-code/0.1.0"},
        "models": _KIMI_MODELS,
    },
    {
        "id": "zai-coding-global",
        "name": "GLM 编程套餐 · 国际 (Z.AI)",
        "api": "https://api.z.ai/api/coding/paas/v4",
        "env_var": "GLM_API_KEY",
        "group": CODING_PLAN_GROUP,
        "note": "订阅制套餐（Z.AI Coding Plan）：与按量计费的 api.z.ai/api/paas/v4 账户分开计费。保存后自动拉取模型。",
        "key_hint": "API Key",
        "auto_pull": True,
        "models": _GLM_MODELS,
    },
    {
        "id": "zai-coding-cn",
        "name": "GLM 编程套餐 · 国内 (智谱)",
        "api": "https://open.bigmodel.cn/api/coding/paas/v4",
        "env_var": "GLM_API_KEY",
        "group": CODING_PLAN_GROUP,
        "note": "订阅制套餐（智谱 GLM Coding Plan）：与开放平台按量计费分开计费。保存后自动拉取模型。",
        "key_hint": "API Key",
        "auto_pull": True,
        "models": _GLM_MODELS,
    },
    {
        "id": "alibaba-coding-plan",
        "name": "阿里云百炼编程套餐 (Qwen)",
        "api": "https://coding-intl.dashscope.aliyuncs.com/v1",
        "env_var": "ALIBABA_CODING_PLAN_API_KEY",
        "group": CODING_PLAN_GROUP,
        "note": "订阅制套餐（coding-intl）：套餐内除 Qwen 外还含 GLM / Kimi / MiniMax 第三方模型。保存后自动拉取模型。",
        "key_hint": "sk-…",
        "auto_pull": True,
        "models": _ALIBABA_CODING_MODELS,
    },
    {
        "id": "stepfun-step-plan",
        "name": "阶跃 Step Plan · 国际",
        "api": "https://api.stepfun.ai/step_plan/v1",
        "env_var": "STEPFUN_API_KEY",
        "group": CODING_PLAN_GROUP,
        "note": "订阅制套餐（StepFun Step Plan）。保存后自动拉取模型。",
        "key_hint": "API Key",
        "auto_pull": True,
        "models": _STEP_MODELS,
    },
    {
        "id": "stepfun-step-plan-cn",
        "name": "阶跃 Step Plan · 国内",
        "api": "https://api.stepfun.com/step_plan/v1",
        "env_var": "STEPFUN_API_KEY",
        "group": CODING_PLAN_GROUP,
        "note": "订阅制套餐（StepFun Step Plan 国内站）。保存后自动拉取模型。",
        "key_hint": "API Key",
        "auto_pull": True,
        "models": _STEP_MODELS,
    },
]

# 保存 key 后需要「自动拉模型」的 provider id 集合（内置目录里的套餐）
AUTO_PULL_IDS = {p["id"] for p in CODING_PLAN_PROVIDERS if p.get("auto_pull")}


class _HttpStatusError(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(f"HTTP {status}: {reason}")
        self.status = status
        self.reason = reason


def _http_get_json(url: str, headers: Dict[str, str], timeout: float = 15.0) -> Any:
    req_headers = {"Accept": "application/json", "User-Agent": "MemOmics/1.0"}
    req_headers.update({k: v for k, v in (headers or {}).items() if v})
    try:
        import httpx  # memomics 底座依赖，优先使用（自带 certifi 信任库）
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers=req_headers)
            if resp.status_code >= 400:
                raise _HttpStatusError(resp.status_code, resp.reason_phrase or "")
            return resp.json()
    except _HttpStatusError:
        raise
    except ImportError:
        pass
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return _json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        raise _HttpStatusError(exc.code, str(exc.reason or "")) from exc


def _candidate_urls(provider: Dict[str, Any]) -> List[str]:
    base = str(provider.get("api") or "").rstrip("/")
    urls: List[str] = []
    override = str(provider.get("models_url") or "").strip()
    if override:
        urls.append(override)
    if base:
        for cand in (f"{base}/models", f"{base}/v1/models" if not base.endswith("/v1") else ""):
            if cand and cand not in urls:
                urls.append(cand)
    return urls


def _headers_for(provider: Dict[str, Any], api_key: str) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    extra = provider.get("extra_headers")
    if isinstance(extra, dict):
        for key, value in extra.items():
            headers[str(key)] = str(value)
    return headers


def _parse_models(data: Any) -> List[Dict[str, Any]]:
    raw = None
    if isinstance(data, dict):
        raw = data.get("data") or data.get("models")
    elif isinstance(data, list):
        raw = data
    if not isinstance(raw, list):
        return []
    models: List[Dict[str, Any]] = []
    seen = set()
    for item in raw:
        if isinstance(item, str):
            mid, name = item.strip(), item.strip()
        elif isinstance(item, dict):
            mid = str(item.get("id") or item.get("model") or "").strip()
            name = str(item.get("name") or item.get("display_name") or mid).strip()
        else:
            continue
        if not mid or mid in seen:
            continue
        seen.add(mid)
        models.append({"id": mid, "name": name or mid,
                       "reasoning": bool(item.get("reasoning")) if isinstance(item, dict) else False,
                       "tool_call": bool(item.get("tool_call", True)) if isinstance(item, dict) else True})
    return models


def fetch_plan_models(provider: Dict[str, Any], api_key: str, timeout: float = 15.0) -> Dict[str, Any]:
    """向任一 provider 端点拉取模型列表（OpenAI /models 兼容，含 Kimi Code 的 /coding/v1/models）。

    返回 {"ok": bool, "models": [...], "url_used": str, "error": str}
    """
    urls = _candidate_urls(provider)
    if not urls:
        return {"ok": False, "error": "该 provider 未配置 API 地址", "tried": []}
    headers = _headers_for(provider, api_key)
    last_err = ""
    for url in urls:
        try:
            data = _http_get_json(url, headers, timeout=timeout)
            models = _parse_models(data)
            if models:
                return {"ok": True, "models": models, "url_used": url}
            last_err = "端点返回空模型列表"
        except _HttpStatusError as exc:
            if exc.status in (401, 403):
                return {"ok": False, "url_used": url,
                        "error": f"HTTP {exc.status} —— API Key 无效或无权访问该端点", "tried": urls}
            last_err = f"HTTP {exc.status}: {exc.reason}"
        except Exception as exc:  # 网络/解析异常：继续试下一个候选
            last_err = str(exc)[:150]
    return {"ok": False, "error": f"模型拉取失败：{last_err or '无法连接'}", "tried": urls}


def is_coding_plan(provider_id: str) -> bool:
    return (provider_id or "").strip() in {p["id"] for p in CODING_PLAN_PROVIDERS}


# ── 模型可用性探针（2026-10-22）────────────────────────────────────────────
# 背景（用户反馈「点『配置 Key / 拉取模型』拉到的模型不能使用」）：拉取只打
# /models 列目录，**不代表每个模型都经由 OpenAI /chat/completions 协议对当前
# 套餐开放**。实测 opencode.ai/zen/go 一把 key 下 36 个模型里：
#   · 25 个正常出话；
#   · grok-4.7 / gpt-6-luna / claude-haiku-5-5 等 6 个返回 400
#     ModelProtocolUnsupported（走 Anthropic Messages / Responses 协议）；
#   · muse-spark-* / gemini-4-argon 受「Go 模型训练期」限制、mimo-v2.5-pro
#     模式不支持、longcat-2.0 端点停用（402）。
# 所以这里补一层「真发一条最小请求」的探针，把结论落进 provider_keys.json，
# 让模型下拉能标出哪些不能用，而不是等用户选中了才吃一嘴报错。

_PROTO_ERR_HINTS = (
    "ModelProtocolUnsupported",
    "does not support this protocol",
    "unsupported protocol",
    "protocol not supported",
)

_UPSTREAM_UNAVAILABLE_HINTS = (
    "Endpoint is unavailable",
    "endpoint is unavailable",
    "not available",
    "model is unavailable",
    "no available channel",
)


def _post_chat_json(url: str, headers: Dict[str, str], payload: Dict[str, Any],
                    timeout: float = 45.0) -> Dict[str, Any]:
    """POST 一条 JSON 到 chat 端点，**不按状态码抛异常**（探针要看错误正文分类）。

    返回 {"ok": bool, "status": int, "text": str, "error": str}。
    """
    try:
        import httpx  # memomics 底座依赖，与 _http_get_json 同一优先序
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.post(url, headers=headers, json=payload)
            return {"ok": resp.status_code < 400, "status": resp.status_code,
                    "text": (resp.text or "")[:800], "error": ""}
    except ImportError:
        pass
    except Exception as exc:  # 连接/超时/SSL：当作探针失败，不抛给上层
        return {"ok": False, "status": 0, "text": "", "error": f"{type(exc).__name__}: {exc}"[:200]}
    try:
        body = _json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"ok": 200 <= resp.status < 400, "status": resp.status,
                    "text": resp.read().decode("utf-8", "replace")[:800], "error": ""}
    except urllib.error.HTTPError as exc:
        try:
            text = exc.read().decode("utf-8", "replace")[:800]
        except Exception:
            text = ""
        return {"ok": False, "status": int(exc.code or 0), "text": text, "error": ""}
    except Exception as exc:
        return {"ok": False, "status": 0, "text": "", "error": f"{type(exc).__name__}: {exc}"[:200]}


def _classify_probe_failure(status: int, text: str, error: str) -> str:
    """把探针失败翻译成一句用户能看懂的话（决定要不要继续试别的模型）。"""
    low = (text or "").lower()
    for hint in _PROTO_ERR_HINTS:
        if hint.lower() in low:
            return "该模型不支持 OpenAI /chat/completions 协议（走 Anthropic Messages / Responses 等），换协议才能用"
    for hint in _UPSTREAM_UNAVAILABLE_HINTS:
        if hint.lower() in low:
            return "上游端点当前不可用（停用/维护/无可用通道）"
    if status == 401:
        return "401 —— API Key 无效或无权限（换一把有效 key 后重试）"
    if status == 402:
        return "402 —— 欠费或该模型需单独付费/订阅"
    if status == 403:
        return "403 —— 上游拒绝：多因套餐未开通、模型未授权或被风控拦截"
    if status == 404:
        return "404 —— 该端点不存在这个模型（网关路径或模型名不符）"
    if status == 429:
        return "429 —— 触发上游限流（稍后重试，或降并发）"
    if status == 400:
        detail = text[:160] if text else "上游未给出原因"
        return f"400 —— 上游拒绝该请求：{detail}"
    if status == 0:
        return f"连不上端点：{error or '网络/超时'}"
    if status >= 500:
        return f"{status} —— 上游服务端错误（多为临时故障，可稍后重试）"
    return f"HTTP {status}：{(text or error or '上游未给出原因')[:160]}"


def _candidate_chat_urls(base: str) -> List[str]:
    """chat 端点候选路径（与 _candidate_urls 同思路：不同网关路径规则不一样）。

    Kimi 编程套餐的 chat 在 /coding/v1/chat/completions（base 是 /coding），
    opencode 与 DCS 的 base 已经含 /v1 —— 所以要先试 base，再试 base + /v1。
    """
    base = str(base or "").rstrip("/")
    urls: List[str] = []
    if not base:
        return urls
    urls.append(f"{base}/chat/completions")
    if not base.endswith("/v1"):
        urls.append(f"{base}/v1/chat/completions")
    return urls


def probe_chat_model(provider: Dict[str, Any], api_key: str, model_id: str,
                     timeout: float = 45.0, max_tokens: int = 1,
                     user_agent: str = "MemOmics/1.0") -> Dict[str, Any]:
    """真发一条最小请求，判定某个模型**现在**能不能出话。

    与 fetch_plan_models 的差别：那是「列目录」，这是「试点火」。只发
    max_tokens=1、内容 'hi' 的最小请求，成本可忽略；失败时按响应正文分类，
    让界面能说清「为什么不能用」。

    返回 {"id", "usable": bool, "status": int, "error": str, "ms": int}
    """
    base = str(provider.get("api") or "").rstrip("/")
    if not base:
        return {"id": model_id, "usable": False, "status": 0,
                "error": "该 provider 未配置 API 地址", "ms": 0}
    headers = {"Content-Type": "application/json", "User-Agent": user_agent}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    # extra_headers（opencode.ai 的 x-opencode-session、Kimi Code 的 UA 等）必须带上，
    # 否则会得到「假失败」：实测不带 x-opencode-session 一律 400 MissingSessionID。
    extra = provider.get("extra_headers")
    if isinstance(extra, dict):
        for key, value in extra.items():
            if value:
                headers[str(key)] = str(value)
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": int(max_tokens),
        "stream": False,
    }
    # 2026-10-22：按候选路径试（Kimi 套餐在 /coding/v1/chat/completions，固定拼
    # <base>/chat/completions 会 404，把 4 个能用的模型全误判成不可用）。
    # 只有 404/405 才换下一个候选；其它错误是本模型的真实结论，直接采纳。
    t0 = time.time()
    last = None
    url_used = ""
    for cand in _candidate_chat_urls(base):
        res = _post_chat_json(cand, headers, payload, timeout=timeout)
        last = res
        url_used = cand
        if res.get("ok"):
            return {"id": model_id, "usable": True, "status": int(res.get("status") or 200),
                    "error": "", "ms": int((time.time() - t0) * 1000), "url_used": cand}
        if int(res.get("status") or 0) not in (404, 405):
            break
    res = last or {}
    # 2026-10-22（对齐 DSH 的容错口径）：单次失败可能是限流/抖动 —— 重试一次再判死，
    # 避免把「刚好抽风一次」的模型误摘掉（用户实测 beam-free 等免费模型会这样）。
    _st = int(res.get("status") or 0)
    if _st not in (401, 402, 403):          # 认证/欠费/风控类不重试（重试也没用）
        time.sleep(1.2)
        for cand in _candidate_chat_urls(base):
            _res2 = _post_chat_json(cand, headers, payload, timeout=timeout)
            if _res2.get("ok"):
                return {"id": model_id, "usable": True, "status": int(_res2.get("status") or 200),
                        "error": "", "ms": int((time.time() - t0) * 1000),
                        "url_used": cand, "retried": True}
            if int(_res2.get("status") or 0) not in (404, 405):
                res, url_used = _res2, cand
                break
    ms = int((time.time() - t0) * 1000)
    reason = _classify_probe_failure(int(res.get("status") or 0), res.get("text") or "", res.get("error") or "")
    return {"id": model_id, "usable": False, "status": int(res.get("status") or 0),
            "error": reason, "ms": ms, "url_used": url_used}