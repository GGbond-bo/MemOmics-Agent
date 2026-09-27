# -*- coding: utf-8 -*-
"""自我介绍不再"绕过 LLM 发固定文案" 契约测试（2026-09-26 用户要求）。

用户原话："memOmics 总是涉及介绍的时候，完全不使用大模型，我想把这个去掉，
然后不要单凭触发'介绍'这两个字就直接发送写好的介绍，我希望能够结合上下文语境。"

历史实现有三条"写好的介绍"通路：
  1. WebUI：_intent == "self_intro" → 直接 append 固定文案 + continue，跳过 agent；
  2. 微信：_wx_intent == "self_intro" → 直接发固定文案并 return；
  3. 注入层：intent == "self_intro" → 提示词里写"必须逐字输出以下内容"，模型不许发挥。
三条都已删除。现在只保留一份"事实参考"交给模型，由模型判断用户到底在问什么。

本文件锁死三件事：
  A. 固定文案与两条绕过 LLM 的分支彻底不存在（源码级，防回归）；
  B. self_intro 的注入是"先判断语境再作答"，不是逐字文案；
  C. 关键词误命中不再有害 —— 即使用户其实在问别的，注入也明确要求正常回答那个问题。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEBUI = os.path.join(ROOT, "webui")
for _p in (ROOT, WEBUI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import server  # noqa: E402


def _src():
    with io.open(server.__file__, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


# ==================== A. 绕过 LLM 的通路必须消失 ====================

def test_a1_canned_intro_constants_removed():
    src = _src()
    assert "_SELF_INTRO_ZH" not in src, "固定中文自我介绍文案应已删除"
    assert "_SELF_INTRO_EN" not in src, "固定英文自我介绍文案应已删除"
    assert "我不是聊天机器人，而是能帮你**跑完完整生信分析**的自主 Agent。给我数据" not in src, \
        "成品文案（带 markdown 排版的整段介绍）不应再留在代码里"


def test_a2_webui_no_bypass_branch():
    src = _src()
    assert "跳过 agent 调用" not in src, "WebUI 不应再有绕过 agent 的快速回复分支"
    assert 'if _intent == "self_intro" and not _explicit_inv["resolved"]' not in src, \
        "self_intro 不应再有独立的快速回复入口"
    assert "_inj_intent = _intent" in src, "self_intro 应和其他意图一样构建注入并走 agent"


def test_a3_weixin_no_bypass_branch():
    src = _src()
    assert "微信Agent回复(自介快回)" not in src, "微信路径不应再有自介快回"
    assert "微信自介回复发送失败" not in src, "微信路径不应再有自介快回的发送分支"


def test_a4_no_verbatim_instruction():
    src = _src()
    assert "必须逐字输出以下内容" not in src, "不应再要求模型逐字输出固定文案"
    assert "禁止自己编" not in src, "不应再有'禁止自己编'式硬约束"


# ==================== B. 注入是"按语境作答 + 事实参考" ====================

def test_b1_injection_asks_model_to_judge_context():
    inj = server._build_skill_injection("self_intro", "", "zh", "你是谁")
    assert inj, "self_intro 仍应给模型一份参考资料"
    for token in ("先判断用户在问什么", "不要整段照抄", "不要输出能力清单", "正常回答那个问题"):
        assert token in inj, f"注入缺少语境判断要求: {token}"


def test_b2_injection_is_reference_not_finished_copy():
    inj = server._build_skill_injection("self_intro", "", "zh", "你是谁")
    assert "## 核心能力" not in inj, "不应把成品文案的标题结构塞给模型"
    assert "有什么需要帮忙的，直接告诉我" not in inj, "不应把成品文案的收尾语塞给模型"
    assert "供你参考" in inj, "事实清单要标明是参考材料"


def test_b3_injection_follows_session_language():
    zh = server._build_skill_injection("self_intro", "", "zh", "你是谁")
    en = server._build_skill_injection("self_intro", "", "en", "who are you")
    assert "关于 MemOmics 的真实事实" in zh and "reference material" not in zh
    assert "reference material" in en and "关于 MemOmics 的真实事实" not in en


def test_b4_injection_keeps_prefixes():
    """self_intro 以前只返回逐字文案，把显式/置顶/RED 前缀全丢了。"""
    src = _src()
    i = src.find('if intent == "self_intro":')
    assert i > 0
    seg = src[i:i + 900]
    assert "explicit_prefix + pinned_prefix + red_prefix" in seg, \
        "self_intro 注入必须保留显式/置顶/RED 前缀"


# ==================== C. 关键词误命中不再有害 ====================

def test_c1_identity_questions_still_classified():
    for text in ("你是谁", "介绍一下你自己", "你能做什么", "自我介绍"):
        assert server._classify_intent(text)[0] == "self_intro", text


def test_c2_user_self_intro_not_hijacked():
    """用户主动介绍自己的进度（主语=我）不能被当成身份提问。"""
    for text in ("我先跟你介绍一下我当前的进度，数据已经跑完 QC",
                 "我跟你介绍一下我这个项目"):
        assert server._classify_intent(text)[0] != "self_intro", text


def test_c3_keyword_false_positive_is_harmless():
    """就算"介绍"两字误命中，模型也会被要求回答用户真正问的那个问题。"""
    for text in ("介绍一下我这个数据集", "介绍一下这段代码在干嘛"):
        intent = server._classify_intent(text)[0]
        inj = server._build_skill_injection(intent, "", "zh", text)
        if intent == "self_intro":
            assert "不要输出能力清单" in inj and "正常回答那个问题" in inj, text
        else:
            assert inj == "" or "不要输出能力清单" not in inj


def test_c4_no_intro_reasoning_claims_no_llm():
    src = _src()
    assert "无需调用 LLM" not in src, "文案里不应再声称'无需调用 LLM'"
