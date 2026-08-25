# -*- coding: utf-8 -*-
"""输出目录记忆回归测试（2026-08-25 实证修复）。

背景：用户指定输出目录最自然的说法（任务词+输出位置并存）曾因"一次性任务
不入库"规则被整句丢弃 → 下一轮 digest 无路径 → 模型不知道文件放哪 → 重复跑。
修复：含输出位置词（输出到/保存到/放到…）的句子必须入库，任务动作部分剥离。
"""
import importlib.util
import os
import sys

import pytest

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pytestmark = pytest.mark.unit

REMEMBER_CASES = [
    "把结果输出到 E:/my_output 目录",
    "结果放到 E:/my_output 里",
    "帮我分析 E:/data 并把结果输出到 E:/my_output",
    "输出到 E:/my_output，记得以后都用这个目录",
    "结果保存到 E:/figures",
    "用 E:/data 画一张图，图保存到 E:/figures",
    "把最终报告输出到 E:/reports/final",
    "结果写入 E:/out/table.csv",
    "生成到 E:/out",
]

NOT_REMEMBER_CASES = [
    "帮我分析一下这个数据",          # 无路径的一次性任务
    "画一张 UMAP 图",                # 无路径无输出位置
    "统计一下样本数",                # 纯任务
    "把结果输出到桌面",              # 无具体路径 → 不持久
    "读取 E:/data 看看",             # 读取类任务无输出位置 → 一次性
]


@pytest.fixture(scope="module")
def server():
    import server as _s
    return _s


@pytest.fixture()
def sess(tmp_path):
    rd = str(tmp_path / "results")
    os.makedirs(rd, exist_ok=True)
    s = {"id": "req-test", "results_dir": rd, "todos": [], "messages": []}
    yield s
    import shutil
    shutil.rmtree(rd, ignore_errors=True)


def _remembered(server, sess, text):
    rp = os.path.join(sess["results_dir"], "REQUIREMENTS.md")
    if os.path.exists(rp):
        os.remove(rp)
    server._extract_and_store_requirements(sess, text)
    return server._read_requirements(sess, limit=6)


def test_output_locations_are_remembered(server, sess):
    for t in REMEMBER_CASES:
        reqs = _remembered(server, sess, t)
        assert reqs, f"{t!r} 必须记住（REQUIREMENTS 为空）"
        joined = " ".join(reqs)
        assert "E:/" in joined or "E:/out" in joined, f"{t!r} 记住的内容缺路径: {reqs}"


def test_task_words_extracted_not_whole_sentence(server, sess):
    """任务词+输出位置：只记住输出子句，任务动作不进持久要求。"""
    reqs = _remembered(server, sess, "帮我分析 E:/data 并把结果输出到 E:/my_output")
    joined = " ".join(reqs)
    assert "输出到 E:/my_output" in joined
    assert "帮我分析" not in joined, "任务动作部分不得入库: " + joined

    reqs2 = _remembered(server, sess, "把最终报告输出到 E:/reports/final")
    assert "输出到 E:/reports/final" in " ".join(reqs2)
    assert "报告" not in " ".join(reqs2).replace("输出到", ""), "任务词残留: " + " ".join(reqs2)


def test_one_off_tasks_not_remembered(server, sess):
    """无输出位置的一次性任务仍不入库（原规则保留）。"""
    for t in NOT_REMEMBER_CASES:
        reqs = _remembered(server, sess, t)
        assert not reqs, f"{t!r} 不应入库: {reqs}"


def test_digest_carries_remembered_path(server, sess):
    """下一轮 digest 必须带记住的输出目录（模型可见）。"""
    _remembered(server, sess, "把最终报告输出到 E:/reports/final")
    digest = server._build_memory_digest(sess, "继续")
    assert "E:/reports/final" in digest, "digest 必须带输出目录"


def test_output_clause_extractor(server):
    cases = [
        ("帮我分析 E:/data 并把结果输出到 E:/my_output", "把结果输出到 E:/my_output"),
        ("用 E:/data 画一张图，图保存到 E:/figures", "图保存到 E:/figures"),
        ("把最终报告输出到 E:/reports/final", "输出到 E:/reports/final"),
        ("结果保存到 E:/figures", "保存到 E:/figures"),  # 提取输出子句（调用方仅在含任务词时调用）
    ]
    for inp, want in cases:
        out = server._extract_output_clause(inp)
        assert out == want, f"{inp!r} → {out!r}（期望 {want!r}）"
