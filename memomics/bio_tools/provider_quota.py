#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""provider_quota.py — 查询 API 通道的余额 / 套餐额度 / 本机用量。

用户问「套餐还剩多少」「还有多少余额」「今天用了多少 token」时调用本工具。

- account：各厂商官方余额 / 套餐窗口端点（宿主侧直连，key 不出本机）：
  DeepSeek、Moonshot（国内·国际）、OpenRouter、SiliconFlow（国内·国际）、
  ZenMux 余额；Kimi For Coding、GLM 编程套餐（国内·国际）、OpenCode Go、
  MiniMax（国内·国际）套餐窗口。
- local：本机台账（results/*/token_usage.jsonl 回合级流水）今日 / 近 7 天
  用量，按「通道 × 模型」聚合；DeepSeek 官方通道附带 CNY 消费估算。

注册为 hermes 工具。
"""

from __future__ import annotations

import json
import os

_MEMOMICS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERMES_HOME = os.path.join(_MEMOMICS_DIR, "hermes_home")


def _provider_keys():
    path = os.path.join(_HERMES_HOME, "provider_keys.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _current_model_cfg():
    path = os.path.join(_HERMES_HOME, "model_config.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _fmt_tokens(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1000:
        return f"{value / 1000:.1f}K"
    return str(value)


def _resolve_target(explicit: str):
    """返回 (pid, saved)；explicit 为空时用当前模型 base_url 匹配，再退回唯一有 key 的通道。"""
    keys = _provider_keys()
    explicit = (explicit or "").strip()
    if explicit:
        pid = explicit
        if pid not in keys:
            lowered = explicit.lower()
            for cand in keys:
                if cand.lower() == lowered or lowered in cand.lower():
                    pid = cand
                    break
        return pid, keys.get(pid) or {}
    cur = _current_model_cfg()
    base = str(cur.get("base_url") or "").rstrip("/").lower()
    if base:
        for pid, saved in keys.items():
            cand = str((saved or {}).get("base_url") or "").rstrip("/").lower()
            if cand and cand == base:
                return pid, saved or {}
    keyed = [(pid, saved) for pid, saved in keys.items()
             if isinstance(saved, dict) and (saved.get("api_key") or saved.get("local"))]
    if len(keyed) == 1:
        return keyed[0]
    return "", {}


def _format_account(row: dict) -> str:
    display = row.get("display") or row.get("provider_id") or "?"
    if not row.get("ok"):
        return f"• {display}：{row.get('error', '查询失败')}"
    if row.get("kind") == "balance":
        balance = row.get("balance") or {}
        text = f"• {display}：余额 {balance.get('total', '?')} {balance.get('currency', '')}".strip()
        if row.get("lines"):
            text += "\n    " + " ｜ ".join(row["lines"])
        return text
    if row.get("kind") == "plan":
        windows = row.get("windows") or []
        parts = []
        for win in windows:
            pct = win.get("percent")
            pct_text = "—" if pct is None else f"{pct:.1f}%"
            reset = win.get("resets_at")
            parts.append(f"{win.get('label') or win.get('key')} 已用 {pct_text}"
                         + (f"（{reset} 重置）" if reset else ""))
        head = row.get("plan_name") or ""
        suffix = f"（{head}）" if head and head.lower() not in display.lower() else ""
        return f"• {display}{suffix}：" + " ｜ ".join(parts)
    return f"• {display}：{row.get('error', '无数据')}"


def _format_local(ledger: dict, only_pid: str = "") -> str:
    if not ledger.get("available"):
        return "本机台账：暂无数据（还没有可统计的会话流水）"
    today = ledger.get("today") or {}
    rows = today.get("rows") or []
    if only_pid:
        rows = [r for r in rows if r.get("provider_id") == only_pid
                or only_pid in str(r.get("provider", "")).lower()]
    source = "回合级流水" if ledger.get("source") == "turn_ledger" else "会话表估算"
    if not rows:
        return f"本机台账（{source}）：今日暂无用量记录"
    buckets = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
               "cache_write_tokens": 0, "reasoning_tokens": 0}
    turns = 0
    cost = 0.0
    lines = []
    for row in rows:
        for field in buckets:
            buckets[field] += int(row.get(field) or 0)
        turns += int(row.get("turns") or 0)
        cost += float(row.get("estimated_cost_cny") or 0.0)
        lines.append(f"    {row.get('provider')} · {row.get('model')}："
                     f"{_fmt_tokens(int(row.get('tokens') or 0))} tokens / {row.get('turns')} 回合")
    head = (f"本机台账（今日 · {source}）：{turns} 回合 · 输入 {_fmt_tokens(buckets['input_tokens'])}"
            f" / 输出 {_fmt_tokens(buckets['output_tokens'])}"
            f" / 缓存读 {_fmt_tokens(buckets['cache_read_tokens'])}")
    if cost > 0:
        head += f" · DeepSeek 消费估算 ¥{cost:.2f}"
    return head + "\n" + "\n".join(lines[:8])


def provider_quota(provider: str = "", kind: str = "both") -> str:
    """查询余额 / 套餐额度 / 本机用量，返回人类可读文本。"""
    try:
        from memomics import usage_quota
    except Exception as exc:
        return f"✗ 用量模块加载失败：{exc}"
    kind = (kind or "both").strip().lower()
    if kind not in ("account", "local", "both"):
        kind = "both"
    keys = _provider_keys()
    pid, saved = _resolve_target(provider)
    parts = []
    if provider:
        target_desc = f"通道 {pid or provider}"
    elif pid:
        target_desc = f"全部已配置通道（当前 {pid}）"
    else:
        target_desc = "全部已配置通道"
    parts.append(f"【{target_desc}】")
    if kind in ("account", "both"):
        try:
            if provider:
                if not saved:
                    parts.append(f"• {pid or provider}：未配置 API Key（在设置 → API 提供商里添加）")
                else:
                    row = usage_quota.probe_account(pid, saved.get("api_key", ""),
                                                    saved.get("base_url") or "")
                    parts.append(_format_account(row))
            else:
                configured = {p: {"api_key": (s or {}).get("api_key", ""),
                                  "base_url": (s or {}).get("base_url", "")}
                              for p, s in keys.items()}
                rows = usage_quota.probe_all(configured)
                if not rows:
                    parts.append("• 暂无可查询的通道（未配置 key 或通道无公开接口）")
                else:
                    if pid:
                        rows.sort(key=lambda r: 0 if r.get("provider_id") == pid else 1)
                    parts.extend(_format_account(r) for r in rows)
        except Exception as exc:
            parts.append(f"• 额度查询失败：{exc}")
    if kind in ("local", "both"):
        try:
            ledger = usage_quota.local_ledger(days=7)
            parts.append(_format_local(ledger, only_pid=pid if pid else ""))
        except Exception as exc:
            parts.append(f"本机台账查询失败：{exc}")
    parts.append("（数据本地查询；套餐窗口来自厂商官方端点，无公开接口的通道会明确说明）")
    return "\n".join(parts)


def register(registry):
    registry.register(
        name="provider_quota",
        toolset="memomics",
        schema={
            "type": "object",
            "name": "provider_quota",
            "description": (
                "查询 API 通道的余额 / 套餐额度（Kimi For Coding、GLM 编程套餐、"
                "OpenCode Go、MiniMax 的已用百分比与重置时间；DeepSeek、Moonshot、"
                "OpenRouter、SiliconFlow 的余额）以及本机今日用量台账。"
                "用户问「套餐还剩多少」「额度」「余额」「今天用了多少 token」时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {
                        "type": "string",
                        "description": "通道 id（如 deepseek、kimi-coding-plan、opencode-go）；留空=当前模型所在通道",
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["account", "local", "both"],
                        "default": "both",
                        "description": "account=余额/套餐额度；local=本机用量台账；both=都要",
                    },
                },
                "required": [],
            },
        },
        handler=lambda args, **kw: provider_quota(
            args.get("provider", ""),
            kind=args.get("kind", "both"),
        ),
        emoji="💠",
        max_result_size_chars=20_000,
    )


# 模块加载时自动注册
try:
    from tools.registry import registry as _registry
    register(_registry)
except Exception:
    pass