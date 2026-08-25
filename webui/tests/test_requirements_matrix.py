# -*- coding: utf-8 -*-
"""提取规则测试矩阵（写端铜墙铁壁，2026-08-25）。

原则：路径类默认全录（digest 必达）——用户说过的重要信息必须在源头进
REQUIREMENTS.md，不依赖折叠摘要/模型主动检索。
覆盖：输出位置/输入数据路径/环境配置/路径别名/纠错/确认/多句并存/中英混合/
emoji 干扰/问句/一次性任务/助手指令/纯 marker/超长/同路径覆盖/纯路径陈述。
"""
import importlib.util
import os
import shutil
import sys

import pytest

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def server():
    import server as _s
    return _s


@pytest.fixture()
def sess(tmp_path):
    rd = str(tmp_path / "results")
    os.makedirs(rd, exist_ok=True)
    s = {"id": "req-matrix", "results_dir": rd, "todos": [], "messages": []}
    yield s
    shutil.rmtree(rd, ignore_errors=True)


def _extract(server, sess, text):
    rp = os.path.join(sess["results_dir"], "REQUIREMENTS.md")
    if os.path.exists(rp):
        os.remove(rp)
    server._extract_and_store_requirements(sess, text)
    return server._read_requirements(sess, limit=12)


# ═══════════════════════════════════════════════════════════════════════════
# A. 输出位置（必须记住）
# ═══════════════════════════════════════════════════════════════════════════

OUTPUT_CASES = [
    "把结果输出到 E:/my_output 目录",
    "结果放到 E:/my_output 里",
    "帮我分析 E:/data 并把结果输出到 E:/my_output",
    "输出到 E:/my_output，记得以后都用这个目录",
    "结果保存到 E:/figures",
    "用 E:/data 画一张图，图保存到 E:/figures",
    "把最终报告输出到 E:/reports/final",
    "结果写入 E:/out/table.csv",
    "生成到 E:/out",
    "导出到 E:/exports",
    "图表写到 E:/figures/panel1",
]


@pytest.mark.parametrize("text", OUTPUT_CASES)
def test_output_locations_remembered(server, sess, text):
    reqs = _extract(server, sess, text)
    assert reqs, f"{text!r} 必须记住（REQUIREMENTS 为空）"
    joined = " ".join(reqs)
    assert "E:/" in joined, f"{text!r} 缺路径: {reqs}"


def test_output_clause_clean(server, sess):
    """任务词+输出位置：只存输出子句，不污染任务动作。"""
    reqs = _extract(server, sess, "帮我分析 E:/data 并把结果输出到 E:/my_output")
    joined = " ".join(reqs)
    assert "输出到 E:/my_output" in joined and "帮我分析" not in joined


# ═══════════════════════════════════════════════════════════════════════════
# B. 输入数据路径（默认全录——长任务跨轮不丢数据位置）
# ═══════════════════════════════════════════════════════════════════════════

INPUT_CASES = [
    "读取 E:/data 分析一下",
    "数据在 E:/data 文件夹",
    "用 E:/data 的数据跑聚类",
    "输入文件是 E:/in.csv",
    "样本都在 E:/samples 目录",
    "分析 E:/scRNA/matrix.mtx 这个文件",
]


@pytest.mark.parametrize("text", INPUT_CASES)
def test_input_paths_remembered(server, sess, text):
    reqs = _extract(server, sess, text)
    assert reqs, f"输入路径 {text!r} 必须记住（路径类默认全录）"
    assert "E:/" in " ".join(reqs)


# ═══════════════════════════════════════════════════════════════════════════
# C. 环境配置
# ═══════════════════════════════════════════════════════════════════════════

ENV_CASES = [
    "R 装在 E:/R-4.5.3",
    "lib 目录是 E:/R-libs",
    "conda 环境在 E:/envs/scenic",
    "Seurat 包在 E:/R-libs/4.5.3",
    "服务器数据在 F:/raw 盘",
]


@pytest.mark.parametrize("text", ENV_CASES)
def test_env_paths_remembered(server, sess, text):
    reqs = _extract(server, sess, text)
    assert reqs, f"环境路径 {text!r} 必须记住"
    assert "E:/" in " ".join(reqs) or "F:/" in " ".join(reqs)


# ═══════════════════════════════════════════════════════════════════════════
# D. 路径别名/变体
# ═══════════════════════════════════════════════════════════════════════════

VARIANT_CASES = [
    "输出到 E:/a/b/c",
    r"输出到 E:\a\b\c",
    "输出到 E:/中文目录/结果",
    "输出到 E:/my dir with spaces",
    "保存到 E:/带(括号)目录",
]


@pytest.mark.parametrize("text", VARIANT_CASES)
def test_path_variants_remembered(server, sess, text):
    reqs = _extract(server, sess, text)
    assert reqs, f"路径变体 {text!r} 必须记住"
    assert "E:/" in " ".join(reqs) or "E:\\" in " ".join(reqs)


# ═══════════════════════════════════════════════════════════════════════════
# E. 纠错 / 确认
# ═══════════════════════════════════════════════════════════════════════════

def test_correction_replaces_old(server, sess):
    """纠错（改成 E:/new）→ 新路径成为要求并替换旧路径，不残留旧条目。"""
    _extract(server, sess, "输出到 E:/old_dir")
    reqs2 = _extract(server, sess, "改成 E:/new_dir 输出")
    joined = " ".join(reqs2)
    assert "E:/new_dir" in joined, f"改成后的新路径必须记住: {reqs2}"
    assert "E:/old_dir" not in joined, f"旧路径应被替换: {reqs2}"


def test_confirm_marked(server, sess):
    reqs = _extract(server, sess, "就用 E:/this 目录")
    assert reqs and any("(已确认)" in r for r in reqs), f"确认句应带标记: {reqs}"


def test_cancel_removes(server, sess):
    """先记后取消 → 条目被移除。"""
    _extract(server, sess, "输出到 E:/doomed")
    rp = os.path.join(sess["results_dir"], "REQUIREMENTS.md")
    _extract(server, sess, "取消输出到 E:/doomed")
    reqs = _read(server, sess)
    assert not any("E:/doomed" in r for r in reqs), f"取消后应移除: {reqs}"


def _read(server, sess):
    return server._read_requirements(sess, limit=12)


# ═══════════════════════════════════════════════════════════════════════════
# F. 多句并存 / 中英混合 / emoji
# ═══════════════════════════════════════════════════════════════════════════

def test_multi_sentence_both_remembered(server, sess):
    reqs = _extract(server, sess, "结果输出到 E:/a，图保存到 E:/b")
    joined = " ".join(reqs)
    assert "E:/a" in joined and "E:/b" in joined, f"多句并存都要记住: {reqs}"


def test_multi_sentence_read_and_out(server, sess):
    reqs = _extract(server, sess, "先读 E:/d 的数据，输出到 E:/o")
    joined = " ".join(reqs)
    assert "E:/o" in joined, f"输出位置必须记住: {reqs}"


def test_english_phrase(server, sess):
    reqs = _extract(server, sess, "output to E:/eng out")
    assert reqs and "E:/eng" in " ".join(reqs), f"英文输出指令应记住: {reqs}"


def test_cjk_path(server, sess):
    reqs = _extract(server, sess, "保存到 E:/中文目录")
    assert reqs and "中文目录" in " ".join(reqs)


def test_emoji_interference(server, sess):
    reqs = _extract(server, sess, "保存到 E:/out 🧬 记得用")
    assert reqs and "E:/out" in " ".join(reqs), f"emoji 不应干扰: {reqs}"


# ═══════════════════════════════════════════════════════════════════════════
# G. 不应入库（豁免保留）
# ═══════════════════════════════════════════════════════════════════════════

NOT_REMEMBER = [
    "画一张 UMAP 图",              # 无路径一次性任务
    "统计一下样本数",              # 无路径
    "帮我分析这个数据",            # 无路径
    "把结果输出到桌面",            # 无具体绝对路径
    "还记得输出到哪吗？",          # 问句
    "输出到 E:/x 了吗？",          # 问句（含路径也不录）
    "你记得 E:/old 吗",            # 问句
    "不要调用任何工具",            # 助手指令
    "只用一句话回复",              # 助手指令
    "先别执行，不要跑",            # 助手指令
]


@pytest.mark.parametrize("text", NOT_REMEMBER)
def test_not_remembered(server, sess, text):
    reqs = _extract(server, sess, text)
    assert not reqs, f"{text!r} 不应入库: {reqs}"


# ═══════════════════════════════════════════════════════════════════════════
# H. 边界
# ═══════════════════════════════════════════════════════════════════════════

def test_marker_only_requirement(server, sess):
    reqs = _extract(server, sess, "以后都用中文回复")
    assert reqs, "纯 marker 要求（以后）应入库"


def test_overlong_sentence_skipped(server, sess):
    long_text = "把结果输出到 " + "E:/x" + " 记住" + "好" * 250
    reqs = _extract(server, sess, long_text)
    assert not any("E:/x" in r for r in reqs), "超长句（>200）不应入库"


def test_same_path_dedup(server, sess):
    """同路径重复陈述 → 只保留一条。"""
    _extract(server, sess, "输出到 E:/dedup")
    reqs2 = _extract(server, sess, "输出到 E:/dedup 目录")
    hits = [r for r in reqs2 if "E:/dedup" in r]
    assert len(hits) == 1, f"同路径应去重: {reqs2}"


def test_plain_path_statement(server, sess):
    reqs = _extract(server, sess, "结果路径是 E:/plain")
    assert reqs and "E:/plain" in " ".join(reqs), "纯路径陈述应记住"


def test_digest_carries_all_remembered(server, sess):
    """多路径记忆后 digest 携带（模型每轮可见）。"""
    _extract(server, sess, "输出到 E:/out1 和保存到 E:/out2 和输入在 E:/in")
    digest = server._build_memory_digest(sess, "继续")
    assert "会话要求" in digest, "digest 应有要求块"
    assert "E:/out1" in digest or "E:/out2" in digest or "E:/in" in digest
