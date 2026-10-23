"""溢写超大工具输出到磁盘（借鉴 DSH 的 spill 与 openai/codex PR #21069 思路）。

问题：MemOmics 现在对超长工具输出只做 head40%/tail60% 截断（terminal_tool.py:2820），
被砍掉的中间部分**彻底丢失**，模型既看不到也无法回查；而且截断只发生在 terminal，
其它工具（读文件、脚本 stdout、MCP 结果）仍可能把几十 KB 直接塞进上下文。

本模块在工具结果落成 message 的**唯一点**（agent.tool_dispatch_helpers.make_tool_result_message）
做一次统一处理：
  - 未超阈值：原样返回（零开销）
  - 超阈值：全文写盘（<MEMOMICS_HOME>/spill/<日期>/<时间>-<hash8>-<tool>.txt），
    返回「head 预览 + 省略说明 + 落盘路径 + tail 预览」，模型可再用 read_file/terminal 查全文

配置（config.yaml）::

    tool_output:
      spill: true          # 默认 true；false 关闭溢写（退回纯截断）
      spill_limit: 50000   # 超过该字符数就溢写；缺省沿用 tool_output.max_bytes
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import time
from typing import Optional

_DEFAULT_LIMIT = 50_000
_HEAD_CHARS = 4_000
_TAIL_CHARS = 2_000


def _cfg() -> dict:
    try:
        from hermes_cli.config import read_raw_config
        cfg = read_raw_config() or {}
        section = cfg.get("tool_output")
        return section if isinstance(section, dict) else {}
    except Exception:
        return {}


def is_enabled() -> bool:
    return bool(_cfg().get("spill", True))


def spill_limit() -> int:
    sec = _cfg()
    for key in ("spill_limit", "max_bytes"):
        try:
            v = int(sec.get(key) or 0)
        except (TypeError, ValueError):
            v = 0
        if v > 0:
            return v
    return _DEFAULT_LIMIT


def root_dir() -> str:
    """溢写根目录：MEMOMICS_SPILL_DIR > <MEMOMICS_HOME>/spill > 系统临时目录。"""
    p = os.environ.get("MEMOMICS_SPILL_DIR") or ""
    if p:
        return p
    for env in ("MEMOMICS_HOME", "HERMES_HOME"):
        home = os.environ.get(env) or ""
        if home:
            return os.path.join(home, "spill")
    return os.path.join(tempfile.gettempdir(), "memomics_spill")


def _write(text: str, tool_name: str) -> str:
    day = time.strftime("%Y%m%d")
    d = os.path.join(root_dir(), day)
    os.makedirs(d, exist_ok=True)
    digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:8]
    safe_tool = "".join(ch for ch in (tool_name or "tool") if ch.isalnum() or ch in "-_")[:24] or "tool"
    path = os.path.join(d, f"{time.strftime('%H%M%S')}-{digest}-{safe_tool}.txt")
    with open(path, "w", encoding="utf-8", errors="replace") as f:
        f.write(text)
    return path


def maybe_spill(text: str, *, tool_name: str = "tool", limit: Optional[int] = None) -> str:
    """超阈值则溢写并返回预览；否则原样返回。任何异常都**退回原文**（绝不丢结果）。"""
    if not isinstance(text, str) or not text:
        return text
    try:
        if not is_enabled():
            return text
        cap = int(limit) if limit else spill_limit()
        if len(text) <= cap:
            return text
        path = _write(text, tool_name)
        head = text[:_HEAD_CHARS]
        tail = text[-_TAIL_CHARS:] if len(text) > _HEAD_CHARS + _TAIL_CHARS else ""
        omitted = len(text) - len(head) - len(tail)
        note = (
            f"\n\n... [输出过长已溢写落盘：共 {len(text):,} 字符，此处省略 {omitted:,} 字符] ...\n"
            f"[全文路径] {path}\n"
            f"[提示] 需要完整内容时用 read_file 读该路径（或 terminal: grep/head/tail），不要凭预览猜。\n\n"
        )
        return head + note + tail
    except Exception:
        return text
