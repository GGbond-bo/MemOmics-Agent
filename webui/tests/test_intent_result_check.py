# -*- coding: utf-8 -*-
"""意图分类回归（2026-08-21 a 改造）：result_check 新意图 + 多意图分类矩阵。

覆盖用户实测痛点："怎么没有结果呢" 不应再被规则当 chat；同时确保 analysis/
research_plan/direct_exec/cancel_task/knowledge_ask/self_intro/progress_check 不受扰动。
全部离线（只调 _classify_intent，不触发 LLM 兜底路由）。
"""
import pytest

import server

pytestmark = pytest.mark.unit


def _intent(text):
    return server._classify_intent(text)[0]


RESULT_CASES = [
    "怎么没有结果呢？",
    "结果呢？",
    "出图了吗？",
    "图出来了吗？",
    "结果出来没？",
    "结果文件在哪？",
    "还没出结果吗",
    "结果怎么样？",
    "图呢？",
    "做完没？",
    "为什么还没有结果？",
    "图做好了没？",
]

PROGRESS_CASES = [
    "还在跑吗",
    "跑完了吗",
    "进度怎么样",
    "卡住了吗",
    "后台任务状态",
]

CHAT_CASES = [
    "你好",
    "今天天气不错",
    "谢谢",
    "哈哈",
]

OTHER_EXPECT = [
    ("你是谁", "self_intro"),
    ("介绍一下你自己", "self_intro"),
    ("什么是批次效应", "knowledge_ask"),
    ("Seurat 怎么算归一化", "knowledge_ask"),
    ("用 Seurat 对 E:/data/ 做单细胞聚类分析", "analysis"),
    ("跑单细胞聚类", "analysis"),
    ("帮我设计一个研究方案", "research_plan"),
    ("直接跑", "direct_exec"),
    ("把任务停掉", "cancel_task"),
    ("取消分析", "cancel_task"),
]


@pytest.mark.parametrize("text", RESULT_CASES)
def test_result_check_queries(text):
    it = _intent(text)
    assert it == "result_check", f"{text!r} -> {it} (expect result_check)"


@pytest.mark.parametrize("text", PROGRESS_CASES)
def test_progress_check_preserved(text):
    it = _intent(text)
    assert it == "progress_check", f"{text!r} -> {it} (expect progress_check)"


@pytest.mark.parametrize("text", CHAT_CASES)
def test_chat_preserved(text):
    it = _intent(text)
    assert it == "chat", f"{text!r} -> {it} (expect chat)"


@pytest.mark.parametrize("text,expect", OTHER_EXPECT)
def test_other_intents_unchanged(text, expect):
    it = _intent(text)
    assert it == expect, f"{text!r} -> {it} (expect {expect})"


def test_result_check_does_not_steal_data_path_task():
    """带新数据路径 + 执行词的任务不应被 result_check 抢走。"""
    it = _intent("用 Seurat 处理 E:/骨骼肌锻炼/MF_AUCell_meta.csv 做聚类出图")
    assert it == "analysis", f"data-path task misrouted -> {it}"
