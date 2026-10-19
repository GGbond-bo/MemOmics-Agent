# -*- coding: utf-8 -*-
"""Loop-level regression: mid-turn steer landing during the FINAL API call.

2026-10-19（K1 根修，conversation_loop.py text_response 出口）：
最终答复出口前 drain 一次 steer——有预算就追加为真实 user 消息并延续当前轮；
预算/轮次将尽则留在槽里，交 turn_finalizer 的 result["pending_steer"] 兜底通道
（调用方据此转为下一轮，绝不静默丢失）。

Harness 复用 test_verification_continuation_budget.py 的脚本化模型模式。
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from run_agent import AIAgent


def _response(content="done"):
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        model="test/model",
        usage=None,
    )


@pytest.fixture
def agent(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    with (
        patch("run_agent.get_tool_definitions", return_value=[]),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("run_agent.OpenAI"),
    ):
        instance = AIAgent(
            session_id="steer-exit-test",
            api_key="test-key",
            base_url="https://example.invalid/v1",
            provider="openai-compat",
            model="test/model",
            max_iterations=4,
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
        )
    instance._cached_system_prompt = "stable test prompt"
    instance._session_db = None
    instance._session_json_enabled = False
    instance.save_trajectories = False
    instance.compression_enabled = False
    instance._cleanup_task_resources = lambda *_a, **_kw: None
    instance._save_trajectory = lambda *_a, **_kw: None
    instance.iteration_budget.max_total = 4
    return instance


def test_steer_during_final_call_continues_turn(agent):
    """插话在最后一次 API 调用进行期间到达 → 本轮不结束，追加 user 消息后续跑。"""
    answers = iter([_response("first answer"), _response("adjusted answer")])
    calls = {"n": 0}

    def model_call(_kwargs):
        calls["n"] += 1
        resp = next(answers)
        if calls["n"] == 1:
            agent.steer("把配色改成灰度")  # 模拟：API 调用进行期间用户插话
        return resp

    agent._interruptible_api_call = model_call
    with patch("hermes_cli.plugins.invoke_hook", return_value=[]):
        result = agent.run_conversation("画一张图")

    assert calls["n"] == 2
    assert result["final_response"] == "adjusted answer"
    assert result.get("pending_steer") is None
    roles = [m["role"] for m in result["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]
    steer_msg = result["messages"][2]
    assert "把配色改成灰度" in steer_msg["content"]
    assert "OUT-OF-BAND USER MESSAGE" in steer_msg["content"]
    assert steer_msg.get("_steer_continuation") is True


def test_steer_at_exit_stays_pending_when_budget_exhausted(agent):
    """预算将尽时不抢跑：插话留在槽里 → finalizer 交还 result["pending_steer"]。"""
    agent.max_iterations = 1
    agent.iteration_budget.max_total = 1

    def model_call(_kwargs):
        agent.steer("来不及了，下轮再说")
        return _response("only answer")

    agent._interruptible_api_call = model_call
    with patch("hermes_cli.plugins.invoke_hook", return_value=[]):
        result = agent.run_conversation("画一张图")

    assert result["final_response"] == "only answer"
    assert result.get("pending_steer") == "来不及了，下轮再说"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
