# -*- coding: utf-8 -*-
"""通道余额 / 编程套餐额度 / 本机用量台账（2026-10-07）。

对标 DSH「使用统计」插件（`@linxin666/dsh-usage`）的能力，落到 MemOmics：

1. **余额适配器**：DeepSeek 官方 / Moonshot（国内·国际）/ OpenRouter /
   SiliconFlow（国内·国际）/ ZenMux。
2. **套餐窗口适配器**：Kimi For Coding / GLM 编程套餐（国内·国际）/
   OpenCode Go / MiniMax（国内·国际）——已用百分比 + 重置时间。
3. **本机台账**：state.db `session_model_usage` 按「通道 × 模型」聚合
   （今日 / 近 N 天），并对 DeepSeek 官方通道按公布的峰谷价目表估算今日消费（CNY）。

约定：
- 所有探测都在宿主侧执行，API key 不进入浏览器/日志；
- 探测结果带 60s TTL 缓存（`fresh=True` 强制刷新），避免频繁轮询触发上游限流；
- 台账口径：早于插件化精确流水（token_usage.jsonl）的会话按「会话-模型行的
  最后活动时间」归日，属于估算；UI 上以「≈」标识。
- 未知/无公开接口的通道不推测：返回 `kind='unsupported'` 与提示语。

端点来源：DSH 插件 @linxin666/dsh-usage 的 adapters.ts（2026-10 实测版本），
外加 DeepSeek 官方价目表（api-docs.deepseek.com，2026-09-10 12:00 北京时间生效）。
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

# ============================================================================
# 基础工具
# ============================================================================

_CACHE_TTL_SEC = 60.0
_cache_lock = threading.Lock()
_cache: Dict[str, Tuple[float, Any]] = {}


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def state_db_path() -> str:
    """state.db 路径：允许环境变量覆盖（测试/多实例）。"""
    override = os.environ.get("MEMOMICS_STATE_DB", "").strip()
    if override:
        return override
    return os.path.join(_repo_root(), "hermes_home", "state.db")


def _to_num(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _str_(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _clamp_pct(value: float) -> float:
    return max(0.0, min(100.0, value))


def _money(value: float) -> str:
    return f"{value:.2f}"


def _used_percent(used: Any, limit: Any) -> Optional[float]:
    used_n, limit_n = _to_num(used), _to_num(limit)
    if used_n is None or limit_n is None or limit_n <= 0:
        return None
    return _clamp_pct((used_n / limit_n) * 100.0)


def _to_iso(value: Any) -> Optional[str]:
    """毫秒/秒 epoch（数字或纯数字字符串）或 ISO 文本 → 本地可读 ISO。"""
    num = _to_num(value)
    if num is None and isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return dt.astimezone().strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return text[:19]
    if num is None:
        return None
    if num <= 0:
        return None
    if num > 1e12:  # 毫秒
        ts = num / 1000.0
    elif num > 1e9:  # 秒
        ts = num
    else:  # 更小的数字当毫秒处理（兼容插件里 < 1e12 视作秒的写法）
        ts = num
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return None


def _http_get_json(url: str, headers: Dict[str, str], timeout: float = 10.0) -> Tuple[int, Any]:
    """GET → (status, parsed_json_or_text)。HTTP 4xx/5xx 不抛异常，交给 parse 判断。"""
    req_headers = {"Accept": "application/json", "User-Agent": "MemOmics-Usage/1.0"}
    req_headers.update({k: v for k, v in (headers or {}).items() if v})
    try:
        import httpx  # hermes 底座依赖，优先；
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers=req_headers)
            raw = resp.content
            status = resp.status_code
    except ImportError:
        req = urllib.request.Request(url, headers=req_headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                status = resp.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
    try:
        return status, json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return status, None


def _provider_error_message(status: int, body: Any) -> str:
    message = None
    if isinstance(body, dict):
        nested = body.get("error")
        message = _str_(body.get("message")) or _str_(body.get("msg"))
        if message is None and isinstance(nested, dict):
            message = _str_(nested.get("message"))
    detail = f"：{message[:120]}" if message else ""
    return f"HTTP {status}{detail}"


# ============================================================================
# 适配器（余额 / 套餐）
# ============================================================================
# 每个规则:
#   ids      —— 按 provider_id 命中的别名
#   host     —— 按 base_url 主机命中的子串（更精确，优先）
#   kind     —— 'balance' | 'plan'
#   display  —— 展示名
#   origin   —— 余额端点归属的源（防止代理/中转商被误报为官方账号余额）
#   build    —— (api_key, base_url, host) -> {'url','headers'}
#   parse    —— (status, body) -> dict | None
# ============================================================================


def _parse_deepseek(status: int, body: Any) -> Optional[Dict[str, Any]]:
    if status != 200 or not isinstance(body, dict):
        return None
    infos = body.get("balance_infos")
    if not isinstance(infos, list) or not infos:
        return None
    first = infos[0]
    if not isinstance(first, dict):
        return None
    currency = _str_(first.get("currency"))
    total = _str_(first.get("total_balance"))
    if currency is None or total is None:
        return None
    lines = []
    for label, key in (("充值余额", "topped_up_balance"), ("赠送余额", "granted_balance")):
        val = _str_(first.get(key))
        if val is not None:
            lines.append(f"{label} {val} {currency}")
    return {"balance": {"currency": currency, "total": total}, "lines": lines}


def _parse_moonshot(currency: str) -> Callable[[int, Any], Optional[Dict[str, Any]]]:
    def _parse(status: int, body: Any) -> Optional[Dict[str, Any]]:
        if status != 200 or not isinstance(body, dict):
            return None
        data = body.get("data")
        if not isinstance(data, dict):
            return None
        available = _to_num(data.get("available_balance"))
        if available is None:
            return None
        lines = []
        cash = _to_num(data.get("cash_balance"))
        voucher = _to_num(data.get("voucher_balance"))
        if cash is not None:
            lines.append(f"现金余额 {_money(cash)} {currency}")
        if voucher is not None:
            lines.append(f"代金券 {_money(voucher)} {currency}")
        return {"balance": {"currency": currency, "total": _money(available)}, "lines": lines}

    return _parse


def _parse_openrouter(status: int, body: Any) -> Optional[Dict[str, Any]]:
    if status != 200 or not isinstance(body, dict):
        return None
    data = body.get("data")
    if not isinstance(data, dict):
        return None
    credits = _to_num(data.get("total_credits"))
    used = _to_num(data.get("total_usage")) or 0.0
    if credits is None:
        return None
    return {
        "balance": {"currency": "USD", "total": _money(max(0.0, credits - used))},
        "lines": [f"总额 ${_money(credits)} · 已用 ${_money(used)}"],
    }


def _parse_siliconflow(currency: str) -> Callable[[int, Any], Optional[Dict[str, Any]]]:
    def _parse(status: int, body: Any) -> Optional[Dict[str, Any]]:
        if status != 200 or not isinstance(body, dict):
            return None
        data = body.get("data")
        if not isinstance(data, dict):
            return None
        total = _str_(data.get("totalBalance"))
        if total is None:
            return None
        lines = []
        balance = _str_(data.get("balance"))
        if balance is not None:
            lines.append(f"可用余额 {balance} {currency}")
        return {"balance": {"currency": currency, "total": total}, "lines": lines}

    return _parse


def _parse_zenmux(status: int, body: Any) -> Optional[Dict[str, Any]]:
    if status != 200 or not isinstance(body, dict):
        return None
    data = body.get("data")
    if not isinstance(data, dict):
        return None
    credits = _to_num(data.get("total_credits"))
    if credits is None:
        return None
    return {"balance": {"currency": "USD", "total": _money(credits)}, "lines": []}


# ---------------------------------------------------------------------------
# 套餐窗口
# ---------------------------------------------------------------------------

_WINDOW_LABELS = {
    "5h": "5 小时",
    "week": "每周",
    "month": "每月",
    "window": "窗口",
}


def _window_label(key: str) -> str:
    if key in _WINDOW_LABELS:
        return _WINDOW_LABELS[key]
    if key.startswith("w-"):
        return f"{key[2:]} 分钟窗口"
    return key


def _parse_kimi_coding(status: int, body: Any) -> Optional[Dict[str, Any]]:
    """Kimi For Coding 配额：limits[] 各窗口 + usage 为每周总览。"""
    if status != 200 or not isinstance(body, dict):
        return None
    windows: List[Dict[str, Any]] = []
    limits = body.get("limits")
    if isinstance(limits, list):
        for entry in limits:
            if not isinstance(entry, dict):
                continue
            detail = entry.get("detail")
            window = entry.get("window")
            if not isinstance(detail, dict):
                continue
            duration = _to_num(window.get("duration")) if isinstance(window, dict) else None
            unit = _str_(window.get("timeUnit")) if isinstance(window, dict) else None
            if duration == 300 and unit == "TIME_UNIT_MINUTE":
                key = "5h"
            elif duration is not None:
                key = f"w-{int(duration)}"
            else:
                key = "window"
            windows.append({
                "key": key,
                "label": _window_label(key),
                "name": _str_(detail.get("name")) or _window_label(key),
                "percent": _used_percent(detail.get("used"), detail.get("limit")),
                "resets_at": _to_iso(detail.get("resetTime")),
            })
    usage = body.get("usage")
    if isinstance(usage, dict):
        windows.append({
            "key": "week",
            "label": _window_label("week"),
            "name": "每周",
            "percent": _used_percent(usage.get("used"), usage.get("limit")),
            "resets_at": _to_iso(usage.get("resetTime")),
        })
    if not windows:
        return None
    user = body.get("user")
    membership = user.get("membership") if isinstance(user, dict) else None
    plan_name = _str_(membership.get("level")) if isinstance(membership, dict) else None
    return {"plan_name": plan_name, "windows": windows}


_GLM_UNIT_KEYS = {3: "5h", 5: "month", 6: "week"}


def _glm_credit_percent(row: Dict[str, Any]) -> Optional[float]:
    used = _to_num(row.get("currentValue"))
    limit = _to_num(row.get("usage"))
    if used is not None and limit is not None and limit > 0:
        return _clamp_pct((used / limit) * 100.0)
    pct = _to_num(row.get("percentage"))
    return None if pct is None else _clamp_pct(pct)


def _parse_glm_plan(status: int, body: Any) -> Optional[Dict[str, Any]]:
    """GLM 编程套餐：unit 3/5/6 = 5小时/每月/每周；TIME_LIMIT 是 MCP 请求限额，跳过。"""
    if status != 200 or not isinstance(body, dict) or body.get("success") is not True:
        return None
    data = body.get("data")
    if not isinstance(data, dict):
        return None
    limits = data.get("limits")
    if not isinstance(limits, list):
        return None
    windows: List[Dict[str, Any]] = []
    for entry in limits:
        if not isinstance(entry, dict):
            continue
        kind = _str_(entry.get("type"))
        if kind in (None, "TIME_LIMIT"):
            continue
        unit = _to_num(entry.get("unit"))
        key = _GLM_UNIT_KEYS.get(int(unit)) if unit is not None else None
        if key is None:
            continue
        if kind == "CREDIT_LIMIT":
            percent = _glm_credit_percent(entry)
        elif kind == "TOKENS_LIMIT":
            pct = _to_num(entry.get("percentage"))
            percent = None if pct is None else _clamp_pct(pct)
        else:
            continue
        windows.append({
            "key": key,
            "label": _window_label(key),
            "name": _window_label(key),
            "percent": percent,
            "resets_at": _to_iso(entry.get("nextResetTime")),
        })
    if not windows:
        return None
    return {"plan_name": _str_(data.get("level")) or "GLM Coding Plan", "windows": windows}


def _parse_opencode_go(status: int, body: Any) -> Optional[Dict[str, Any]]:
    if status != 200 or not isinstance(body, dict):
        return None
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return None
    windows: List[Dict[str, Any]] = []
    for field, key in (("rolling", "5h"), ("weekly", "week"), ("monthly", "month")):
        entry = usage.get(field)
        if not isinstance(entry, dict):
            continue
        pct = _to_num(entry.get("percent"))
        windows.append({
            "key": key,
            "label": _window_label(key),
            "name": _window_label(key),
            "percent": None if pct is None else _clamp_pct(pct),
            # percent 0 时 resetsAt 是占位值（now + 窗口），不展示
            "resets_at": None if pct in (None, 0) else _to_iso(entry.get("resetsAt")),
        })
    if not windows:
        return None
    return {"plan_name": "OpenCode Go", "windows": windows}


def _parse_minimax(status: int, body: Any) -> Optional[Dict[str, Any]]:
    if status != 200 or not isinstance(body, dict):
        return None
    remains = body.get("model_remains")
    if not isinstance(remains, list):
        return None
    general = None
    for entry in remains:
        if isinstance(entry, dict) and entry.get("model_name") == "general":
            general = entry
            break
    if general is None:
        return None
    windows: List[Dict[str, Any]] = []
    interval = _to_num(general.get("current_interval_remaining_percent"))
    if interval is not None:
        windows.append({
            "key": "5h",
            "label": _window_label("5h"),
            "name": "5 小时剩余",
            "percent": _clamp_pct(100.0 - interval),
            "resets_at": _to_iso(general.get("end_time")),
        })
    if general.get("current_weekly_status") == 1:
        weekly = _to_num(general.get("current_weekly_remaining_percent"))
        if weekly is not None:
            windows.append({
                "key": "week",
                "label": _window_label("week"),
                "name": "每周剩余",
                "percent": _clamp_pct(100.0 - weekly),
                "resets_at": _to_iso(general.get("weekly_end_time")),
            })
    if not windows:
        return None
    return {"plan_name": "MiniMax Coding Plan", "windows": windows}


def _bearer(api_key: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _build_deepseek(api_key: str, base_url: str, host: str) -> Dict[str, Any]:
    return {"url": "https://api.deepseek.com/user/balance", "headers": _bearer(api_key)}


def _build_moonshot(host: str, api_key: str) -> Dict[str, Any]:
    return {"url": f"https://{host}/v1/users/me/balance", "headers": _bearer(api_key)}


def _build_kimi_coding(api_key: str, base_url: str, host: str) -> Dict[str, Any]:
    return {"url": "https://api.kimi.com/coding/v1/usages", "headers": _bearer(api_key)}


def _build_glm(host: str, api_key: str) -> Dict[str, Any]:
    # 注意：GLM 监控接口用 raw key（不带 Bearer 前缀）
    return {
        "url": f"https://{host}/api/monitor/usage/quota/limit",
        "headers": {"Authorization": api_key, "accept-language": "en-US,en"},
    }


def _build_opencode_go(api_key: str, base_url: str, host: str) -> Dict[str, Any]:
    return {"url": "https://opencode.ai/zen/go/v1/usage", "headers": _bearer(api_key)}


def _build_minimax(host: str) -> Dict[str, Any]:
    return {"url": f"https://{host}/v1/api/openplatform/coding_plan/remains"}


_ADAPTERS: List[Dict[str, Any]] = [
    {
        "ids": {"deepseek", "deepseek-official"}, "host": "api.deepseek.com",
        "kind": "balance", "display": "DeepSeek", "origin": "https://api.deepseek.com",
        "build": _build_deepseek, "parse": _parse_deepseek,
    },
    {
        "ids": {"moonshotai-cn", "moonshot-cn"}, "host": "api.moonshot.cn",
        "kind": "balance", "display": "Moonshot（国内）",
        "build": lambda k, b, h: _build_moonshot("api.moonshot.cn", k),
        "parse": _parse_moonshot("CNY"),
    },
    {
        "ids": {"moonshotai", "moonshot"}, "host": "api.moonshot.ai",
        "kind": "balance", "display": "Moonshot（国际）",
        "build": lambda k, b, h: _build_moonshot("api.moonshot.ai", k),
        "parse": _parse_moonshot("USD"),
    },
    {
        "ids": {"openrouter"}, "host": "openrouter.ai",
        "kind": "balance", "display": "OpenRouter",
        "build": lambda k, b, h: {"url": "https://openrouter.ai/api/v1/credits", "headers": _bearer(k)},
        "parse": _parse_openrouter,
    },
    {
        "ids": {"siliconflow-cn", "siliconflow"}, "host": "api.siliconflow.cn",
        "kind": "balance", "display": "SiliconFlow（国内）",
        "build": lambda k, b, h: {"url": "https://api.siliconflow.cn/v1/user/info", "headers": _bearer(k)},
        "parse": _parse_siliconflow("CNY"),
    },
    {
        "ids": {"siliconflow-intl"}, "host": "api.siliconflow.com",
        "kind": "balance", "display": "SiliconFlow（国际）",
        "build": lambda k, b, h: {"url": "https://api.siliconflow.com/v1/user/info", "headers": _bearer(k)},
        "parse": _parse_siliconflow("USD"),
    },
    {
        "ids": {"zenmux"}, "host": "zenmux.ai",
        "kind": "balance", "display": "ZenMux",
        "build": lambda k, b, h: {"url": "https://zenmux.ai/api/v1/management/payg/balance", "headers": _bearer(k)},
        "parse": _parse_zenmux,
    },
    {
        "ids": {"kimi-coding-plan", "kimi-coding"}, "host": "api.kimi.com",
        "kind": "plan", "display": "Kimi For Coding",
        "build": _build_kimi_coding, "parse": _parse_kimi_coding,
    },
    {
        "ids": {"zai-coding-cn", "zai-coding", "zai-coding-plan"}, "host": "open.bigmodel.cn",
        "kind": "plan", "display": "GLM 编程套餐（国内）",
        "build": lambda k, b, h: _build_glm("open.bigmodel.cn", k),
        "parse": _parse_glm_plan,
    },
    {
        "ids": {"zai-coding-global", "zai"}, "host": "api.z.ai",
        "kind": "plan", "display": "GLM 编程套餐（国际）",
        "build": lambda k, b, h: _build_glm("api.z.ai", k),
        "parse": _parse_glm_plan,
    },
    {
        "ids": {"opencode-go"}, "host": "opencode.ai",
        "kind": "plan", "display": "OpenCode Go",
        "build": _build_opencode_go, "parse": _parse_opencode_go,
    },
    {
        "ids": {"minimax-cn"}, "host": "api.minimaxi.com",
        "kind": "plan", "display": "MiniMax Coding Plan（国内）",
        "build": lambda k, b, h: _build_minimax("api.minimaxi.com"),
        "parse": _parse_minimax,
    },
    {
        "ids": {"minimax"}, "host": "api.minimax.io",
        "kind": "plan", "display": "MiniMax Coding Plan（国际）",
        "build": lambda k, b, h: _build_minimax("api.minimax.io"),
        "parse": _parse_minimax,
    },
]

# 已知但没有公开查询接口的通道：给出明确说明，不静默
_NO_API_NOTES = {
    "dcs-cloud": "DCS Cloud 无公开余额接口：费用/欠费请在 DCS 控制台查看（面板的欠费标记来自项目信息）。",
    "alibaba-cn": "阿里云百炼无公开余额接口：额度请在阿里云费用中心查看。",
    "zhipuai": "智谱按量计费无公开余额接口：额度请在 open.bigmodel.cn 控制台查看。",
    "volcengine": "火山引擎无公开余额接口：额度请在火山控制台查看。",
    "baidu": "百度千帆无公开余额接口：额度请在百度云控制台查看。",
    "tencent": "腾讯混元无公开余额接口：额度请在腾讯云控制台查看。",
}


def _match_adapter(provider_id: str, base_url: Optional[str]) -> Optional[Dict[str, Any]]:
    pid = (provider_id or "").strip().lower()
    host = ""
    if base_url:
        try:
            host = (urllib.parse.urlparse(base_url).hostname or "").lower()
        except ValueError:
            host = ""
    # 主机匹配优先（同一 provider_id 可能被中转/别名指向不同源）
    if host:
        for rule in _ADAPTERS:
            rule_host = rule.get("host") or ""
            if rule_host and rule_host in host:
                return rule
    for rule in _ADAPTERS:
        if pid and pid in rule["ids"]:
            return rule
    return None


def probe_account(provider_id: str, api_key: str, base_url: Optional[str] = None,
                  timeout: float = 10.0) -> Dict[str, Any]:
    """探测单个通道的余额或套餐窗口。永不抛异常。"""
    pid = (provider_id or "").strip()
    display = pid or "unknown"
    rule = _match_adapter(pid, base_url)
    if rule is None:
        note = _NO_API_NOTES.get(pid.lower())
        if note:
            return {"provider_id": pid, "display": display, "ok": False,
                    "kind": "unsupported", "error": note}
        return {"provider_id": pid, "display": display, "ok": False,
                "kind": "unsupported", "error": "该通道无公开余额/套餐接口（额度请在供应商控制台查看）"}
    display = rule.get("display") or display
    if not api_key:
        return {"provider_id": pid, "display": display, "ok": False, "kind": "no_key",
                "error": "未配置 API Key"}
    try:
        host = ""
        if base_url:
            try:
                host = (urllib.parse.urlparse(base_url).hostname or "").lower()
            except ValueError:
                host = ""
        spec = rule["build"](api_key, base_url or "", host)
        status, body = _http_get_json(spec["url"], spec["headers"], timeout=timeout)
        parsed = rule["parse"](status, body)
        if parsed is None:
            return {"provider_id": pid, "display": display, "ok": False,
                    "kind": rule["kind"], "error": _provider_error_message(status, body)}
        out = {"provider_id": pid, "display": display, "ok": True, "kind": rule["kind"],
               "probed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        out.update(parsed)
        return out
    except Exception as exc:  # 网络异常/解析异常一律降级为错误行
        return {"provider_id": pid, "display": display, "ok": False,
                "kind": rule["kind"], "error": f"探测失败：{str(exc)[:150]}"}


def _is_valid_key(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    s = value.strip()
    if len(s) < 8:
        return False
    if any(tok in s.lower() for tok in ("your_api_key", "changeme", "placeholder", "sk-xxx")):
        return False
    return True


def probe_all(configured: Dict[str, Dict[str, Any]], display_names: Optional[Dict[str, str]] = None,
              timeout: float = 10.0) -> List[Dict[str, Any]]:
    """并发探测所有已配置通道（仅含有适配器的）。configured: pid -> {api_key, base_url}。"""
    display_names = display_names or {}
    targets = []
    for pid, saved in (configured or {}).items():
        saved = saved or {}
        rule = _match_adapter(pid, saved.get("base_url"))
        if rule is None:
            continue
        api_key = saved.get("api_key") or ""
        if not _is_valid_key(api_key):
            continue
        targets.append((pid, api_key, saved.get("base_url")))
    results: List[Dict[str, Any]] = []
    if not targets:
        return results
    with ThreadPoolExecutor(max_workers=min(6, len(targets))) as pool:
        futures = [pool.submit(probe_account, pid, key, base, timeout) for pid, key, base in targets]
        for fut in futures:
            try:
                row = fut.result(timeout=timeout + 5)
            except Exception as exc:
                row = {"provider_id": "", "ok": False, "error": f"探测失败：{exc}"}
            if display_names and row.get("provider_id") in display_names:
                row["display"] = display_names[row["provider_id"]]
            results.append(row)
    # 套餐优先（用户更关心额度），其次按名称
    results.sort(key=lambda r: (0 if r.get("kind") == "plan" else 1, str(r.get("display") or "")))
    return results


# ============================================================================
# DeepSeek 官方峰谷计价（CNY / 百万 tokens，2026-09-10 12:00 北京时间生效）
# ============================================================================

_PEAK_WINDOWS = ((9 * 60, 12 * 60), (14 * 60, 18 * 60))
_BEIJING_OFFSET_MS = 8 * 3600 * 1000
_V4_PRO_FOLDED_INTO_FLASH_MS = 1789358400000  # 2026-09-14 12:00 北京时间（= Date.UTC(2026,8,14,4,0)）

_FLASH_PRICE = {"cache_hit": (0.02, 0.04), "input_miss": (1.0, 2.0), "output": (4.0, 8.0)}
_PRO_PRICE = {"cache_hit": (0.15, 0.3), "input_miss": (4.5, 9.0), "output": (13.5, 27.0)}


def deepseek_period_at(now_ms: Optional[float] = None) -> Dict[str, Any]:
    """当前 DeepSeek 计费时段（北京时间工作日 09:00-12:00 / 14:00-18:00 为高峰）。"""
    now_ms = now_ms if now_ms is not None else time.time() * 1000.0
    shifted = datetime.utcfromtimestamp((now_ms + _BEIJING_OFFSET_MS) / 1000.0)
    weekday = shifted.weekday()  # 0=周一
    minute = shifted.hour * 60 + shifted.minute
    peak = False
    if weekday < 5:
        for start, end in _PEAK_WINDOWS:
            if start <= minute < end:
                peak = True
                break
    # 距离时段翻转的分钟数（展示用）
    boundary_minutes: Optional[int] = None
    if peak:
        for start, end in _PEAK_WINDOWS:
            if start <= minute < end:
                boundary_minutes = end - minute
                break
    else:
        if weekday < 5:
            for start, _end in _PEAK_WINDOWS:
                if minute < start:
                    boundary_minutes = start - minute
                    break
        if boundary_minutes is None:
            boundary_minutes = None  # 跨天/周末，前端只展示"空闲"
    return {
        "peak": peak,
        "label": "高峰时段（双倍计费）" if peak else "空闲时段（半价）",
        "multiplier": 2.0 if peak else 1.0,
        "boundary_minutes": boundary_minutes,
        "beijing_time": shifted.strftime("%Y-%m-%d %H:%M"),
    }


def deepseek_model_spend(model: str, cache_read: int, cache_write: int, input_tokens: int,
                         output_tokens: int, at_ms: float) -> float:
    """单行 DeepSeek 用量折算 CNY（口径对齐 dsh-usage pricing.ts）。"""
    name = (model or "").lower()
    pro_priced = ("v4-pro" in name) and at_ms < _V4_PRO_FOLDED_INTO_FLASH_MS
    price = _PRO_PRICE if pro_priced else _FLASH_PRICE
    col = 1 if deepseek_period_at(at_ms)["peak"] else 0
    spend = (cache_read * price["cache_hit"][col]
             + (input_tokens + cache_write) * price["input_miss"][col]
             + output_tokens * price["output"][col]) / 1_000_000.0
    return round(spend, 6)


# ============================================================================
# 本机台账（state.db）
# ============================================================================


def _local_midnight_ts() -> float:
    now = datetime.now()
    return datetime(now.year, now.month, now.day).timestamp()


_RESULTS_DIR = os.path.join(_repo_root(), "results")

# 非适配器但值得命名的通道（本机台账展示用）
_EXTRA_LABELS = (
    ("dcsapi.dcs.cloud", "DCS Cloud"),
    ("opencode.ai", "OpenCode Go"),
)


def _session_base_map(db_path: Optional[str] = None) -> Dict[str, str]:
    """session_id → billing_base_url（回合流水没有通道字段，用会话表回填）。"""
    import sqlite3

    path = db_path or state_db_path()
    mapping: Dict[str, str] = {}
    if not os.path.isfile(path):
        return mapping
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        try:
            for sid, base in conn.execute(
                    "SELECT id, COALESCE(billing_base_url,'') FROM sessions"):
                if sid:
                    mapping[str(sid)] = str(base or "")
        finally:
            conn.close()
    except Exception:
        return mapping
    return mapping


def _scan_turn_ledger(since_ts: float, results_dir: Optional[str] = None,
                      db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """扫描 results/*/token_usage.jsonl 的回合级精确流水（带本地时间戳）。"""
    base = results_dir or _RESULTS_DIR
    if not os.path.isdir(base):
        return []
    sid_map = _session_base_map(db_path)
    out: List[Dict[str, Any]] = []

    def _delta(rec_deltas: Dict[str, Any], key: str) -> int:
        try:
            val = int(rec_deltas.get(key) or 0)
        except (TypeError, ValueError):
            val = 0
        return max(0, val)  # 会话重置可能出现负差分，按 0 计

    for name in os.listdir(base):
        path = os.path.join(base, name, "token_usage.jsonl")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(rec, dict):
                        continue
                    try:
                        ts = datetime.fromisoformat(str(rec.get("ts") or "")).timestamp()
                    except ValueError:
                        continue
                    if ts < since_ts:
                        continue
                    deltas = rec.get("deltas") if isinstance(rec.get("deltas"), dict) else {}
                    sid = str(rec.get("session_id") or "")
                    out.append({
                        "ts": ts,
                        "session_id": sid,
                        "model": str(rec.get("model") or "未知模型"),
                        "base_url": sid_map.get(sid, ""),
                        "input_tokens": _delta(deltas, "input_tokens"),
                        "output_tokens": _delta(deltas, "output_tokens"),
                        "cache_read_tokens": _delta(deltas, "cache_read_tokens"),
                        "cache_write_tokens": _delta(deltas, "cache_write_tokens"),
                        "reasoning_tokens": _delta(deltas, "reasoning_tokens"),
                    })
        except OSError:
            continue
    return out


def local_ledger(days: int = 30, db_path: Optional[str] = None,
                 results_dir: Optional[str] = None) -> Dict[str, Any]:
    """本机用量台账：今日 / 近 N 天，按「通道 × 模型」聚合。

    口径：优先用回合级精确流水 token_usage.jsonl（含时间戳，能准确归日）；
    完全没有流水时才回退到 state.db（按会话-模型行的最后活动日归属，属估算）。
    """
    midnight = _local_midnight_ts()
    since = time.time() - days * 86400.0
    out: Dict[str, Any] = {
        "today": {"rows": [], "row_count": 0, "buckets": {}, "turns": 0,
                  "estimated_cost_cny": 0.0, "has_deepseek": False},
        "series": [], "days": days, "source": "none", "available": False,
    }
    turns = _scan_turn_ledger(min(since, midnight), results_dir, db_path)
    if turns:
        out["available"] = True
        out["source"] = "turn_ledger"
        today_rows: Dict[Tuple[str, str], Dict[str, Any]] = {}
        buckets = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
                   "cache_write_tokens": 0, "reasoning_tokens": 0}
        calls = 0
        by_day: Dict[str, Dict[str, int]] = {}
        for turn in turns:
            provider = _label_for(turn["base_url"], "")
            pid = _pid_for(turn["base_url"], "")
            label = f"{provider} · {turn['model']}"
            total = (turn["input_tokens"] + turn["output_tokens"]
                     + turn["cache_read_tokens"] + turn["cache_write_tokens"])
            day = datetime.fromtimestamp(turn["ts"]).strftime("%Y-%m-%d")
            slot = by_day.setdefault(day, {})
            slot[label] = slot.get(label, 0) + total
            if turn["ts"] < midnight:
                continue
            key = (provider, turn["model"])
            row = today_rows.get(key)
            if row is None:
                row = today_rows[key] = {
                    "provider": provider, "provider_id": pid, "model": turn["model"],
                    "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
                    "cache_write_tokens": 0, "reasoning_tokens": 0, "turns": 0,
                    "tokens": 0, "last_ts": turn["ts"],
                }
            for field in ("input_tokens", "output_tokens", "cache_read_tokens",
                          "cache_write_tokens", "reasoning_tokens"):
                row[field] += turn[field]
                buckets[field] += turn[field]
            row["turns"] += 1
            row["tokens"] += total
            row["last_ts"] = max(row["last_ts"], turn["ts"])
            calls += 1
        rows = sorted(today_rows.values(), key=lambda r: r["tokens"], reverse=True)
        for row in rows:
            if row["provider_id"] == "deepseek" or "deepseek" in row.get("provider", ""):
                row["estimated_cost_cny"] = deepseek_model_spend(
                    row["model"], row["cache_read_tokens"], row["cache_write_tokens"],
                    row["input_tokens"], row["output_tokens"], row["last_ts"] * 1000.0)
            row.pop("last_ts", None)
        out["today"] = {
            "rows": rows[:12], "row_count": len(rows), "buckets": buckets,
            "turns": calls,
            "estimated_cost_cny": round(sum(r.get("estimated_cost_cny", 0.0) for r in rows), 4),
            "has_deepseek": any(r.get("estimated_cost_cny") is not None for r in rows),
        }
        out["series"] = [{"date": day, "items": [{"label": k, "tokens": v} for k, v in items.items()]}
                         for day, items in sorted(by_day.items())]
        return out

    # ── 回退：state.db（老会话没有回合流水）──
    import sqlite3

    path = db_path or state_db_path()
    if not os.path.isfile(path):
        return out
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        try:
            db_rows = conn.execute(
                "SELECT model, COALESCE(billing_base_url,''), COALESCE(billing_provider,''),"
                " COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0),"
                " COALESCE(SUM(cache_read_tokens),0), COALESCE(SUM(cache_write_tokens),0),"
                " COALESCE(SUM(reasoning_tokens),0), COALESCE(SUM(api_call_count),0),"
                " COALESCE(MAX(last_seen),0)"
                " FROM session_model_usage WHERE COALESCE(last_seen,0) >= ?"
                " GROUP BY model, billing_base_url, billing_provider",
                (since,),
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return out
    out["available"] = True
    out["source"] = "state_db_estimate"
    today_rows = []
    buckets = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
               "cache_write_tokens": 0, "reasoning_tokens": 0}
    calls = 0
    by_day: Dict[str, Dict[str, int]] = {}
    for model, base_url, billing_provider, inp, outp, cr, cw, rz, cnt, last_seen in db_rows:
        last_seen = float(last_seen or 0)
        provider = _label_for(base_url, billing_provider)
        row = {
            "provider": provider, "provider_id": _pid_for(base_url, billing_provider),
            "model": model or "未知模型",
            "input_tokens": int(inp), "output_tokens": int(outp),
            "cache_read_tokens": int(cr), "cache_write_tokens": int(cw),
            "reasoning_tokens": int(rz), "api_calls": int(cnt),
            "tokens": int(inp) + int(outp) + int(cr) + int(cw),
        }
        if row["provider_id"] == "deepseek":
            row["estimated_cost_cny"] = deepseek_model_spend(
                model or "", int(cr), int(cw), int(inp), int(outp),
                (last_seen * 1000.0) if last_seen else time.time() * 1000.0)
        if last_seen >= midnight:
            today_rows.append(row)
            for k in buckets:
                buckets[k] += row[k]
            calls += int(cnt)
        day = datetime.fromtimestamp(last_seen).strftime("%Y-%m-%d") if last_seen else "未知"
        slot = by_day.setdefault(day, {})
        label = f"{provider} · {row['model']}"
        slot[label] = slot.get(label, 0) + row["tokens"]
    today_rows.sort(key=lambda r: r["tokens"], reverse=True)
    out["today"] = {
        "rows": today_rows[:12], "row_count": len(today_rows), "buckets": buckets,
        "turns": calls,
        "estimated_cost_cny": round(sum(r.get("estimated_cost_cny", 0.0) for r in today_rows), 4),
        "has_deepseek": any(r.get("estimated_cost_cny") is not None for r in today_rows),
    }
    out["series"] = [{"date": day, "items": [{"label": k, "tokens": v} for k, v in items.items()]}
                     for day, items in sorted(by_day.items())]
    return out


def _label_for(base_url: str, billing_provider: str) -> str:
    host = ""
    if base_url:
        try:
            host = (urllib.parse.urlparse(base_url).hostname or "").lower()
        except ValueError:
            host = ""
    for rule in _ADAPTERS:
        rule_host = rule.get("host") or ""
        if rule_host and rule_host in host:
            return rule["display"]
    for frag, label in _EXTRA_LABELS:
        if frag in host:
            return label
    if billing_provider:
        return billing_provider
    if host:
        return host
    return "其它/早期会话"


def _pid_for(base_url: str, billing_provider: str) -> str:
    host = ""
    if base_url:
        try:
            host = (urllib.parse.urlparse(base_url).hostname or "").lower()
        except ValueError:
            host = ""
    for rule in _ADAPTERS:
        rule_host = rule.get("host") or ""
        if rule_host and rule_host in host:
            return sorted(rule["ids"])[0]
    for frag, label in _EXTRA_LABELS:
        if frag in host:
            return label.lower().replace(" ", "-")
    return billing_provider or ""


# ============================================================================
# 总览（带 TTL 缓存）
# ============================================================================


def overview(configured: Dict[str, Dict[str, Any]], display_names: Optional[Dict[str, str]] = None,
             current: Optional[Dict[str, Any]] = None, days: int = 30, fresh: bool = False,
             db_path: Optional[str] = None, results_dir: Optional[str] = None,
             timeout: float = 10.0) -> Dict[str, Any]:
    """用量总览：账户探测 + 本机台账 + DeepSeek 时段。默认 60s 缓存。"""
    now = time.time()
    with _cache_lock:
        hit = _cache.get("overview")
        if hit and not fresh and (now - hit[0]) < _CACHE_TTL_SEC:
            cached = dict(hit[1])
            cached["cached"] = True
            cached["cache_age_sec"] = round(now - hit[0], 1)
            if current is not None:
                cached["current"] = current
            if display_names:
                for row in cached.get("accounts", []):
                    if row.get("provider_id") in display_names:
                        row["display"] = display_names[row["provider_id"]]
            return cached
    accounts = probe_all(configured, display_names, timeout=timeout)
    ledger = local_ledger(days=days, db_path=db_path, results_dir=results_dir)
    data = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "accounts": accounts,
        "ledger": ledger,
        "deepseek_period": deepseek_period_at(now * 1000.0),
        "current": current or {},
        "cached": False,
        "cache_age_sec": 0.0,
        "cache_ttl_sec": _CACHE_TTL_SEC,
    }
    with _cache_lock:
        _cache["overview"] = (now, {k: v for k, v in data.items()})
    return data


def clear_cache() -> None:
    with _cache_lock:
        _cache.pop("overview", None)