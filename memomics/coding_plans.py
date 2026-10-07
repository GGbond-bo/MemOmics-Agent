# -*- coding: utf-8 -*-
"""编程套餐（Code Plan）provider 目录 + 模型自动拉取（2026-10-07）。

背景：主流厂商的订阅制 AI 编程套餐（Kimi For Coding、GLM 编程套餐、阿里云
百炼 Coding、阶跃 Step Plan）使用**独立端点 + 独立 key 体系**，与按量计费的
开放平台端点不通用（sk-kimi- 前缀的 key 只在 api.kimi.com/coding 生效等）。
本模块把这些套餐作为 WebUI「设置 → API 提供商」里的独立分组，并在用户保存
key 后自动向套餐端点拉取可用模型（拉到的模型会并入模型选择器与 Hermes 底座）。

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
        import httpx  # hermes 底座依赖，优先使用（自带 certifi 信任库）
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