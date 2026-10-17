# -*- coding: utf-8 -*-
"""风险分级（降低回合内审查时延，2026-10-18）。

背景（实测）：一个 6 基因 / 12 样本的小分析，`execute_python` 只花 0.45s，但回合内自动触发的
`debate_analysis` 跑了 **550s**（judge 路由连续 ReadTimeout + 回退链），用户感知就是"卡住/繁琐"。
本模块给"这个任务到底多大"一个确定性判定，供 enforcement 决定**是否值得上重审查**：

    trivial  只读/格式化/echo 这类，秒级
    low      小规模分析（数据文件 < 2MB 或没给数据），无高风险动作
    medium   常规分析（数据规模未知或偏大）
    high     入库/报告/发表/投递/集群/全量批次 —— 保持最严审查

配置：config.yaml → review.tiering（on 默认 / off = 退回"一律严审"）。
"""
from __future__ import annotations

import os
import re

TIERS = ("trivial", "low", "medium", "high")
RANK = {"trivial": 0, "low": 1, "medium": 2, "high": 3}

_HIGH_HINTS = ("入库", "save_knowledge", "知识库写入", "报告", "终稿", "发表", "投稿", "论文",
               "投递", "集群", "cluster", "dcs", "云平台", "上机", "测序", "全量", "批量",
               "pipeline", "生产环境", "临床", "结题", "审计", "复核", "最终结论")
_TRIVIAL_HINTS = ("echo", "ls ", "dir ", "cat ", "只读", "查看", "看一下", "格式化",
                  "版本", "hello", "打印", "算一下", "求和", "计数")
_ANALYSIS_HINTS = ("分析", "差异", "统计", "检验", "富集", "聚类", "降维", "回归", "相关性",
                   "画图", "绘图", "比对", "注释", "预处理", "建模", "预测")
_PATH_RE = re.compile(r"([A-Za-z]:\\[^\s,，;；\"']+|\b[\w.\-]+\.(?:csv|tsv|xlsx|xls|rds|h5ad|h5|txt|json)\b)")
_SMALL_FILE = 2 * 1024 * 1024   # 2MB 以下算小规模


def tiering_enabled() -> bool:
    try:
        import yaml
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "memomics_home", "config.yaml")
        if os.path.exists(p):
            d = yaml.safe_load(open(p, encoding="utf-8")) or {}
            v = (d.get("review") or {}).get("tiering", True)
            return bool(v)
    except Exception:
        pass
    return True


def _small_input(user_text: str) -> bool:
    """文本里出现的第一个数据文件若存在且 < 2MB → 小规模。"""
    for m in _PATH_RE.finditer(user_text or ""):
        cand = m.group(1)
        try:
            if os.path.isfile(cand) and os.path.getsize(cand) < _SMALL_FILE:
                return True
        except Exception:
            continue
    return False


def classify(user_text: str = "", tool_name: str = "", args=None, es=None) -> str:
    """返回 trivial/low/medium/high。失败一律回 high（宁严不松）。"""
    try:
        if not tiering_enabled():
            return "high"
        t = str(user_text or "")
        low = t.lower()
        # 继承本轮已判定的分级（同一回合内不因工具调用反复重算）
        if es is not None and getattr(es, "risk_tier", ""):
            return str(es.risk_tier)
        if any(h in t or h.lower() in low for h in _HIGH_HINTS):
            return "high"
        if any(h in low for h in _TRIVIAL_HINTS) and not any(v in t for v in _ANALYSIS_HINTS):
            return "trivial"
        if any(v in t for v in _ANALYSIS_HINTS):
            return "low" if _small_input(t) else "medium"
        return "trivial" if len(t) < 40 else "low"
    except Exception:
        return "high"


def current_tier(es=None) -> str:
    """优先用会话上已判定的分级，其次按 topic_hint 现场判。"""
    try:
        if es is not None:
            v = getattr(es, "risk_tier", "")
            if v in RANK:
                return v
            hint = getattr(es, "topic_hint", "") or ""
            if hint:
                return classify(hint, es=None)
    except Exception:
        pass
    return "medium"


def rank(tier: str) -> int:
    return RANK.get(str(tier or ""), 2)


def max_debate_level(tier: str) -> int:
    """该分级允许的最高辩论级别：0=L0 不辩，1=L1 轻量，2=L2。"""
    return {"trivial": 0, "low": 0, "medium": 1, "high": 2}.get(str(tier or ""), 2)


def rail_block_allowed(tier: str) -> bool:
    """rail_review(pre) 的问题是否允许**硬阻断执行**（低风险小任务不阻断，只记录）。"""
    return rank(tier) >= RANK["medium"]


def describe(tier: str) -> str:
    return {
        "trivial": "只读/秒级操作：跳过重审查",
        "low": "小规模分析（数据 <2MB 或无数据）：不辩论，rail 问题不硬拦",
        "medium": "常规分析：最多 L1 轻量辩论 + rail 正常把关",
        "high": "高影响（入库/报告/投递/集群/全量）：全审查",
    }.get(str(tier or ""), "")
