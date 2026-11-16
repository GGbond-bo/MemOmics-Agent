# -*- coding: utf-8 -*-
"""文献片段翻译：输出体检 + 分层兜底（2026-11-16）。

事故背景：对照页把模型的思考过程原样覆盖到了 PDF 上，截图里能看到
``[reasoning] 思考过程: We need answer only final JSON array 8 Chinese translations``
和 ``Input items:`` / ``Translation:`` 这类调试文本。三个根因叠在一起：

1. ``raw_out.index("[")`` 先命中了 ``[reasoning]`` 的方括号，切出来的片段必然不是 JSON；
2. JSON 解析失败后退化成按行拆分，行数巧合相等时就把思考文本当成了译文；
3. 解析结果没有任何体检，污染文本一路返回给前端渲染。

本模块把这三件事收口：先剥思考标签/代码围栏，再用 ``json.JSONDecoder.raw_decode``
在文本里找真正能解析的数组（天然跳过 ``[reasoning]`` 这种非法 JSON），逐条过
``validate``；判为污染的段落返回空串（前端标「未译出」），判为空输出的段落沿用
旧契约回填原文，保证既有调用方行为不变。
"""
from __future__ import annotations

import json
import re

# <think ...>...</think>、<thinking/>，以及各种代码围栏
_THINK_RE = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.I | re.S)
_FENCE_RE = re.compile(r"```[A-Za-z0-9_+.-]*\s*(.*?)```", re.S)
# 行首的 [reasoning] / [thinking] / [思考] 之类标签
_LEAD_TAG_RE = re.compile(r"^\s*\[(?:reasoning|thinking|thought|思考|分析)[^\]]{0,40}\]\s*", re.I)
_LIST_PREFIX_RE = re.compile(r"^\s*(?:[-*•·]|\d{1,3}[.、)）])\s*")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

# 出现任意一条就判定为「模型把过程/模板吐出来了」，不可当译文
BAN_MARKERS = (
    "[reasoning",
    "reasoning草稿",
    "思考过程",
    "input items",
    "translation:",
    "we need answer",
    "json array",
    "只输出一个",
    "the instruction",
    "here is the translation",
    "以下是翻译",
    "译文如下",
    "assistant:",
    "system prompt",
    # 模型对「无可译内容」的元话术，同样不能当译文落盘
    "未提供需要翻译",
    "未提供可翻译",
    "可翻译的英文文本",
    "没有需要翻译",
    "没有可翻译",
    "无可翻译",
    "无需翻译",
    "不需要翻译",
    "no translatable",
    "no english text",
    "nothing to translate",
    # 任务复述 / 自我推理（理论上 no_think 已关，但实测仍会漏）
    "我们需要回答",
    "我们要回答",
    "任务：",
    "任务:",
    "只输出译文",
    "不要解释",
    "最终结果",
    "常见翻译",
    "翻成中文",
    # _llm_content 内部占位符
    "辩论生成失败",
    "[文献片段",
)


def strip_artifacts(text) -> str:
    """剥掉思考块、代码围栏、行首标签，返回可展示文本。"""
    t = str(text or "")
    t = _THINK_RE.sub("", t)
    t = _FENCE_RE.sub(lambda m: m.group(1), t)
    t = _LEAD_TAG_RE.sub("", t)
    return t.strip().strip('"').strip("'").strip()


def looks_polluted(text) -> bool:
    low = str(text or "").lower()
    return any(m in low for m in BAN_MARKERS)


def cjk_count(text) -> int:
    return len(_CJK_RE.findall(str(text or "")))


def is_zh_target(target) -> bool:
    """调用方可能传 zh / zh-CHS / 中文 / Chinese，统一判成中文目标。"""
    t = str(target or "").strip().lower()
    return t.startswith("zh") or "中文" in t or t in ("chinese", "zh-chs", "zh_cn", "zh-hans")


def validate(text, source, target: str = "zh"):
    """单条译文的体检。返回 (ok, reason)。"""
    t = str(text or "").strip()
    if not t:
        return False, "empty"
    if "```" in t:
        return False, "fence"
    if looks_polluted(t):
        return False, "polluted"
    src = str(source or "").strip()
    if src and t == src:
        return False, "same-as-source"
    if is_zh_target(target):
        cjk = cjk_count(t)
        if cjk == 0:
            return False, "no-cjk"
        # 出现任意中文就认为译者给出过译文；整段无中文由 no-cjk 拦下。
        # 不按中英比例判罚：引用条目、机构名这类行本来就该保留原样。
    if src and len(t) > max(120, len(src) * 5):
        return False, "too-long"
    # 短原文却给出长输出，基本是模型在复述任务而不是给译文
    if src and len(src) <= 60 and len(t) > max(40, len(src) * 2):
        return False, "echo-for-short-source"
    return True, "ok"


def extract_json_list(raw):
    """在模型输出里找第一个真正的 JSON 数组；``[reasoning]`` 这类非法片段被跳过。"""
    text = str(raw or "")
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "[":
            continue
        try:
            obj, _end = decoder.raw_decode(text, idx)
        except Exception:
            continue
        if isinstance(obj, list):
            return obj
    return None


def _line_split(raw):
    """按行兜底：只保留不像污染的行。"""
    out = []
    for line in str(raw or "").splitlines():
        line = _LIST_PREFIX_RE.sub("", line).strip()
        if not line or looks_polluted(line):
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        out.append(line)
    return out


def _parse(raw, n: int):
    """把模型输出解析成 n 条候选文本（可能不足 n，用空串补齐）。"""
    arr = extract_json_list(raw)
    vals = None
    if isinstance(arr, list):
        vals = [str(x if x is not None else "").strip() for x in arr]
    if vals is None:
        lines = _line_split(raw)
        # 行数必须对得上，否则宁可整批作废也不猜
        vals = lines if len(lines) == n else None
    if vals is None:
        return [""] * n
    if len(vals) < n:
        vals += [""] * (n - len(vals))
    elif len(vals) > n:
        vals = vals[: n - 1] + [" ".join(vals[n - 1 :])]
    return vals


def _postprocess(raw, chunk, target):
    """解析 + 逐条清洗体检。返回 (vals, blocked)：blocked 表示「污染，别回填原文」。"""
    n = len(chunk)
    parsed = _parse(raw, n)
    vals, blocked = [""] * n, set()
    for i, cand in enumerate(parsed):
        cleaned = strip_artifacts(cand)
        ok, reason = validate(cleaned, chunk[i], target)
        if ok:
            vals[i] = cleaned
            continue
        if reason == "polluted":
            blocked.add(i)
        elif cleaned:
            # 非污染但体检不过（大半英文/超长）→ 也标为可疑，交给单段重试
            blocked.add(i)
    return vals, blocked


def _batch_prompt(chunk, target: str) -> str:
    return (
        "你是学术文献翻译器。把下面 JSON 数组里的每个片段翻成%s。\n"
        "要求：① 保留基因名/蛋白名/物种拉丁名/数字/单位/引用编号原样；"
        "② 术语用生命科学通用译法；③ 不解释、不总结、不合并；"
        "④ 只输出一个 JSON 数组，长度与输入完全一致（共 %d 项），元素是纯译文。\n"
        "输入：%s" % (target, len(chunk), json.dumps(chunk, ensure_ascii=False))
    )


def _single_prompt(text, target: str) -> str:
    return (
        "把下面这段学术英文直接翻成%s，只输出译文，不要解释，"
        "不要输出任何思考过程、字段名或说明：\n%s" % (target, text)
    )


def translate_chunk(chunk, target, llm):
    """整批翻译一组片段，返回与输入等长的列表。

    - 译文通过体检 → 原样返回；
    - 模型给出空输出 → 沿用旧契约回填原文（调用方行为不变）；
    - 输出被判污染且重试仍污染 → 返回空串，交给前端标「此段暂未译出」。
    """
    chunk = [str(c or "") for c in (chunk or [])]
    n = len(chunk)
    if not n:
        return []
    raw = llm(
        _batch_prompt(chunk, target),
        "文献片段翻译",
        temperature=0.1,
        max_tokens=min(4000, 600 + 60 * n),
        no_think=True,
    )
    vals, blocked = _postprocess(raw, chunk, target)

    missing = [i for i, v in enumerate(vals) if not v]
    if missing:
        for i in missing:
            try:
                one = llm(
                    _single_prompt(chunk[i], target),
                    "文献片段翻译_单段",
                    temperature=0.1,
                    max_tokens=1200,
                    no_think=True,
                )
            except Exception:
                continue
            one = strip_artifacts(one)
            ok, reason = validate(one, chunk[i], target)
            if ok:
                vals[i] = one
                blocked.discard(i)
            elif reason == "polluted":
                blocked.add(i)

    for i, v in enumerate(vals):
        if not v and i not in blocked:
            vals[i] = chunk[i]
    return vals
