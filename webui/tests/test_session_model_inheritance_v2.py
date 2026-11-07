"""Offline regression coverage for model inheritance and visible chat failures.

The module deliberately replaces the provider registry, persistence hooks, and
WebSocket emitter with fakes.  It never reads a real provider key, creates an
SSH connection, or calls an LLM.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

import pytest
from starlette.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect

import server


KEY_ALPHA = "alpha-key-1234567890"
KEY_BETA = "beta-key-0987654321"


def _registry():
    index = {
        "alpha": {"id": "alpha", "api": "https://alpha.invalid/v1"},
        "beta": {"id": "beta", "api": "https://beta.invalid/v1"},
    }
    keys = {
        "alpha": {"api_key": KEY_ALPHA, "base_url": "https://alpha.invalid/v1"},
        "beta": {"api_key": KEY_BETA, "base_url": "https://beta.invalid/v1"},
    }
    return index, keys


def _cfg(pid="alpha", model="alpha-old"):
    base = f"https://{pid}.invalid/v1"
    key = KEY_ALPHA if pid == "alpha" else KEY_BETA
    return {
        "provider": "openai",
        "provider_id": pid,
        "base_url": base,
        "api_key": key,
        "model": model,
    }


def _response_body(value):
    assert isinstance(value, JSONResponse)
    return json.loads(value.body.decode("utf-8"))


@pytest.fixture()
def isolated_model_state(monkeypatch):
    index, keys = _registry()
    monkeypatch.setattr(server, "_PROVIDERS_INDEX", index)
    monkeypatch.setattr(server, "_provider_keys", keys)
    monkeypatch.setattr(server, "_current_model", _cfg())
    monkeypatch.setattr(server, "_sessions", {})
    monkeypatch.setattr(server, "_save_model_config", lambda: None)
    monkeypatch.setattr(server, "_save_provider_keys", lambda: None)
    monkeypatch.setattr(server, "_sync_custom_providers_to_memomics", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_sync_debate_env", lambda: None)
    monkeypatch.setattr(server, "_get_session_db", lambda: None)
    return index, keys


def test_legacy_openai_transport_uses_unique_saved_provider_key():
    """`provider=openai` is a protocol label, not a provider-key selector."""
    index, keys = _registry()
    result = server.resolve_model_switch(
        {
            "model": "alpha-new",
            "base_url": "https://alpha.invalid/v1/",
            "provider": "openai",
            "api_key": "",
        },
        _cfg(),
        keys,
        index,
    )
    assert result["ok"] is True
    assert result["config"]["provider"] == "openai"
    assert result["config"]["provider_id"] == "alpha"
    assert result["config"]["api_key"] == KEY_ALPHA


def test_duplicate_endpoint_requires_provider_id_and_keeps_state_unchanged(isolated_model_state):
    index, keys = isolated_model_state
    index["alpha-copy"] = {"id": "alpha-copy", "api": "https://alpha.invalid/v1"}
    keys["alpha-copy"] = {"api_key": "copy-key-1234567890", "base_url": "https://alpha.invalid/v1"}
    before = dict(server._current_model)

    response = asyncio.run(server.switch_model({
        "model": "ambiguous", "base_url": "https://alpha.invalid/v1", "provider": "openai", "api_key": "",
    }))
    body = _response_body(response)
    assert response.status_code == 400
    assert body["error"] == "ambiguous_provider"
    assert server._current_model == before


def test_provider_id_url_conflict_and_cross_provider_empty_key_are_controlled(isolated_model_state):
    before = dict(server._current_model)
    conflict = asyncio.run(server.switch_model({
        "model": "bad", "provider_id": "alpha", "base_url": "https://beta.invalid/v1", "api_key": "",
    }))
    assert conflict.status_code == 400
    assert _response_body(conflict)["error"] == "provider_url_conflict"
    assert server._current_model == before

    # Target beta exists but has no stored key.  It must never inherit alpha's
    # global key just because the browser submitted an empty api_key field.
    server._provider_keys["beta"] = {"base_url": "https://beta.invalid/v1"}
    no_key = asyncio.run(server.switch_model({
        "model": "beta-new", "provider_id": "beta", "base_url": "https://beta.invalid/v1", "api_key": "",
    }))
    assert no_key.status_code == 400
    assert _response_body(no_key)["error"] == "need_key"
    assert server._current_model == before


def test_explicit_provider_key_delete_cannot_be_bypassed_by_empty_switch(isolated_model_state):
    follower = {"id": "follower", "model_config": _cfg(), "agent": None}
    locked_copy = {"id": "locked-copy", "model_config": _cfg(), "model_locked": True, "agent": None}
    server._sessions.update({follower["id"]: follower, locked_copy["id"]: locked_copy})
    removed = asyncio.run(server.delete_provider_key("alpha"))
    assert removed == {"ok": True}
    assert "alpha" not in server._provider_keys
    assert server._current_model["api_key"] == ""
    assert follower["model_config"]["api_key"] == ""
    assert locked_copy["model_config"]["api_key"] == ""

    response = asyncio.run(server.switch_model({
        "model": "alpha-again", "provider_id": "alpha", "base_url": "https://alpha.invalid/v1", "api_key": "",
    }))
    assert response.status_code == 400
    assert _response_body(response)["error"] == "need_key"


def test_local_provider_is_ready_without_key():
    result = server.resolve_model_switch(
        {
            "model": "llama-local",
            "provider_id": "local-ollama",
            "base_url": "http://127.0.0.1:11434/v1",
            "provider": "openai",
            "api_key": "",
        },
        {},
        {"local-ollama": {"local": True, "base_url": "http://127.0.0.1:11434/v1"}},
        {"local-ollama": {"id": "local-ollama", "api": "http://127.0.0.1:11434/v1"}},
    )
    assert result["ok"] is True
    assert result["config"]["api_key"] == ""
    assert server._model_config_ready(result["config"]) is True


def test_global_switch_propagates_only_unlocked_idle_sessions_and_never_leaks_key(isolated_model_state):
    class Agent:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    idle_agent = Agent()
    active_agent = Agent()
    locked = {"id": "locked", "model_config": _cfg("beta", "beta-locked"), "model_locked": True}
    active = {
        "id": "active", "model_config": _cfg("alpha", "alpha-active"),
        "running_agent": active_agent, "running_task": "in-flight", "_user_turn_active": True,
        "agent": active_agent,
    }
    idle = {"id": "idle", "model_config": _cfg("alpha", "alpha-idle"), "agent": idle_agent}
    server._sessions.update({"locked": locked, "active": active, "idle": idle})

    answer = asyncio.run(server.switch_model({
        "model": "alpha-global", "provider_id": "alpha", "base_url": "https://alpha.invalid/v1", "api_key": "",
        "provider": "openai",
    }))
    assert answer["ok"] is True
    assert "api_key" not in answer["current"]
    assert answer["current"]["provider_id"] == "alpha"
    assert answer["current"]["model_ready"] is True
    assert idle["model_config"]["model"] == "alpha-global" and idle_agent.closed is True
    assert locked["model_config"]["model"] == "beta-locked"
    assert active["model_config"]["model"] == "alpha-active"
    assert active["_pending_global_model_config"]["model"] == "alpha-global"


def test_session_override_locks_and_is_not_replaced_by_later_global_switch(isolated_model_state):
    session = {"id": "session-a", "model_config": _cfg(), "created": "", "last_active": ""}
    server._sessions[session["id"]] = session
    changed = asyncio.run(server.switch_model({
        "session_id": session["id"], "model": "beta-session", "provider_id": "beta",
        "base_url": "https://beta.invalid/v1", "api_key": "", "provider": "openai",
    }))
    assert changed["ok"] is True and changed["current"]["provider_id"] == "beta"
    assert "api_key" not in changed["current"]
    assert session["model_locked"] is True

    asyncio.run(server.switch_model({
        "model": "alpha-global", "provider_id": "alpha", "base_url": "https://alpha.invalid/v1", "api_key": "",
    }))
    assert session["model_config"]["model"] == "beta-session"
    assert session["model_config"]["provider_id"] == "beta"


def test_restore_without_db_is_always_a_config_and_lock_tuple(monkeypatch):
    monkeypatch.setattr(server, "_get_session_db", lambda: None)
    restored = server._restore_session_model_config("memomics-a1b2c3d4", _cfg())
    assert restored == (_cfg(), False)


def test_model_responses_are_redacted_and_include_readiness(isolated_model_state):
    models = asyncio.run(server.list_models())
    current = models["current"]
    assert current["provider_id"] == "alpha"
    assert current["model_ready"] is True
    assert current["has_key"] is True
    assert "api_key" not in current


def test_turn_error_prefers_the_running_request_id_over_a_later_input():
    session = {
        "id": "memomics-a1b2c3d4", "progress_log": [], "reasoning_log": [],
        "_running_request_id": "running-turn", "_active_request_id": "later-input",
    }
    server._session_emit(session, {"type": "error", "content": "offline failure"})
    event = session["progress_log"][-1]
    assert event["session_id"] == session["id"]
    assert event["request_id"] == "running-turn"


def test_websocket_request_id_is_sanitized_and_bounded():
    clean = server._clean_ws_request_id("A" * 200 + "<script>\n")
    assert clean == "A" * 128
    generated = server._clean_ws_request_id("\n\t")
    assert generated and len(generated) <= 128


class _FakeWebSocket:
    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.sent = []

    async def accept(self):
        return None

    async def receive_text(self):
        if self._payloads:
            return self._payloads.pop(0)
        raise WebSocketDisconnect(code=1000)

    async def send_text(self, text):
        self.sent.append(json.loads(text))


def _ws_session(sid, tmp_path, *, model_config=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "id": sid, "title": "新会话", "created": now, "last_active": now,
        "messages": [], "model_config": dict(model_config or _cfg()),
        "results_dir": str(tmp_path), "todos": [], "bg_running": False,
        "running_agent": None, "running_task": None, "lang": "zh",
        "progress_log": [], "reasoning_log": [], "_messages_loaded": True,
    }


def _patch_chat_setup(monkeypatch, events):
    """Remove unrelated filesystem/LLM work from WebSocket protocol tests."""
    monkeypatch.setattr(server, "_get_session_db", lambda: None)
    monkeypatch.setattr(server, "_thread_state", None)
    monkeypatch.setattr(server, "_attach_ws", lambda *_args: None)
    monkeypatch.setattr(server, "_ensure_session_messages_loaded", lambda *_args: None)
    monkeypatch.setattr(server, "_auto_anchor_turn", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_maybe_switch_task_dir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_classify_intent", lambda *_args, **_kwargs: ("chat", 1.0, {}))
    monkeypatch.setattr(server, "_build_skill_injection", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(server, "_pinned_expect_emit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_red_hit_emit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_skill_invoke_emit", lambda *_args, **_kwargs: None)

    def emit(session, message):
        item = dict(message)
        item.setdefault("session_id", session["id"])
        events.append(item)

    monkeypatch.setattr(server, "_session_emit", emit)


def test_second_same_session_chat_is_rejected_before_ack_or_history(monkeypatch, tmp_path):
    sid = "memomics-a1b2c3d4"
    session = _ws_session(sid, tmp_path)
    assert server._claim_session_user_turn(session, "first-request") == (True, "first-request")
    monkeypatch.setattr(server, "_sessions", {sid: session})
    monkeypatch.setattr(server, "_thread_state", None)
    ws = _FakeWebSocket([json.dumps({
        "type": "chat", "session_id": sid, "message": "second draft", "request_id": "second-request",
    })])

    asyncio.run(server.ws_endpoint(ws))

    assert ws.sent == [{
        "type": "error", "code": "turn_in_progress", "preserve_draft": True,
        "session_id": sid, "request_id": "second-request", "owner_request_id": "first-request",
        "content": "该会话正在处理上一条消息；本次草稿未提交，已保留，请等待完成后再发送。",
    }]
    assert session["messages"] == []
    assert session["_active_request_id"] == "first-request"
    assert session["_turn_claim_request_id"] == "first-request"


def test_run_agent_closures_freeze_a_and_b_turn_context(monkeypatch, tmp_path):
    """Delay both coroutines before first execution and inspect their defaults."""
    sid_a, sid_b = "memomics-a1b2c3d4", "memomics-b1c2d3e4"
    session_a, session_b = _ws_session(sid_a, tmp_path / "a"), _ws_session(sid_b, tmp_path / "b")
    events, captured = [], []
    monkeypatch.setattr(server, "_sessions", {sid_a: session_a, sid_b: session_b})
    monkeypatch.setattr(server, "_current_model", _cfg())
    _patch_chat_setup(monkeypatch, events)

    class Agent:
        tools = []
        tool_progress_callback = None
        _interrupt_requested = False
        _pending_steer = ""

        def clear_interrupt(self):
            self._interrupt_requested = False

        def close(self):
            pass

    class PendingTask:
        def __init__(self):
            self.callbacks = []

        def done(self):
            return False

        def cancel(self):
            return None

        def add_done_callback(self, callback):
            self.callbacks.append(callback)

    class Supervisor:
        def is_running(self, _sid):
            return False

        def register(self, *_args, **_kwargs):
            return None

    class Scheduler:
        async def acquire(self, *_args, **_kwargs):
            return None

    def fake_ensure(coro):
        name = getattr(getattr(coro, "cr_code", None), "co_name", "")
        if name == "run_agent":
            captured.append(coro)
            return PendingTask()
        coro.close()
        return PendingTask()

    monkeypatch.setattr(server, "_create_agent", lambda *_args, **_kwargs: Agent())
    monkeypatch.setattr(server, "_task_supervisor", Supervisor())
    monkeypatch.setattr(server, "_resource_scheduler", Scheduler())
    monkeypatch.setattr(server.asyncio, "ensure_future", fake_ensure)
    ws = _FakeWebSocket([
        json.dumps({"type": "chat", "session_id": sid_a, "message": "message for A", "request_id": "request-A"}),
        json.dumps({"type": "chat", "session_id": sid_b, "message": "message for B", "request_id": "request-B"}),
    ])
    try:
        asyncio.run(server.ws_endpoint(ws))
        assert len(captured) == 2
        frozen = [coroutine.cr_frame.f_locals for coroutine in captured]
        assert frozen[0]["_session"] is session_a
        assert frozen[0]["_request_id"] == "request-A"
        assert frozen[0]["_user_text"] == "message for A"
        assert frozen[1]["_session"] is session_b
        assert frozen[1]["_request_id"] == "request-B"
        assert frozen[1]["_user_text"] == "message for B"
    finally:
        for coroutine in captured:
            coroutine.close()


def _patch_run_agent_side_effects(monkeypatch):
    """Keep callback-lifetime tests offline and focused on turn ownership."""
    monkeypatch.setattr(server, "_loop_check", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_maybe_narration_nudge", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_snapshot_before_change", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_finalize_file_change", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_ensure_results_dir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_auto_system_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_weixin_push_progress", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_weixin_push_image", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_build_memory_digest", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(server, "_maybe_rollup_history", lambda _session, history: history)
    monkeypatch.setattr(server.context_arch, "memomics_replay", lambda _session, history, **_kwargs: history)
    monkeypatch.setattr(server, "_build_background_process_check", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(server, "_build_kb_tail_injection", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(server, "_build_ask_form_context", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(server, "_code_edit_mode", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(server, "_build_grill_prompt", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(server, "_build_intent_confirm_prompt", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(server, "_build_task_plan_context", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(server, "_build_alerts_context", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(server, "_build_task_resume_prompt", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(server, "_build_recent_turns_digest", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(server, "_build_pending_question_context", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(server, "_answer_anchor", lambda _history, text: text)
    monkeypatch.setattr(server, "_should_nudge_final_answer", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(server, "_persist_token_usage", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_schedule_self_check", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_save_assets_index", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_release_lease", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_clear_session_running", lambda *_args, **_kwargs: None)


def test_reused_agent_tool_callbacks_use_the_current_turn_log(monkeypatch, tmp_path):
    """A once-wrapped agent must not keep its first turn's tool-log callback."""
    sid = "memomics-a1b2c3d4"
    session = _ws_session(sid, tmp_path)
    session["results_dir"] = ""
    events = []
    _patch_chat_setup(monkeypatch, events)
    _patch_run_agent_side_effects(monkeypatch)
    monkeypatch.setattr(server, "_sessions", {sid: session})
    monkeypatch.setattr(server, "_current_model", _cfg())
    monkeypatch.setattr(server, "_thread_state", None)
    monkeypatch.setattr(server, "MEMOMICS_HOME_DIR", str(tmp_path))

    class Agent:
        tools = []
        _interrupt_requested = False
        _pending_steer = ""

        def __init__(self):
            self.calls = 0
            self.callback_pairs = []

        def clear_interrupt(self):
            self._interrupt_requested = False

        def close(self):
            pass

        def run_conversation(self, *_args, **_kwargs):
            self.calls += 1
            label = f"tool-round-{self.calls}"
            self.callback_pairs.append((
                self._memomics_turn_tool_start_cb,
                self._memomics_turn_tool_complete_cb,
            ))
            self.tool_start_callback(f"start-{self.calls}", label, {})
            self.tool_complete_callback(f"complete-{self.calls}", label, {}, "ok")
            return {"final_response": ""}

    class Supervisor:
        def is_running(self, _sid):
            return False

        def register(self, *_args, **_kwargs):
            return None

    class Scheduler:
        async def acquire(self, *_args, **_kwargs):
            return None

    agent = Agent()
    monkeypatch.setattr(server, "_create_agent", lambda *_args, **_kwargs: agent)
    monkeypatch.setattr(server, "_task_supervisor", Supervisor())
    monkeypatch.setattr(server, "_resource_scheduler", Scheduler())

    async def run_round(message, request_id):
        ws = _FakeWebSocket([json.dumps({
            "type": "chat", "session_id": sid, "message": message, "request_id": request_id,
        })])
        await server.ws_endpoint(ws)
        task = session.get("running_task")
        assert task is not None
        await task

    async def scenario():
        await run_round("first", "turn-1")
        first_wrapper = agent.tool_start_callback
        await run_round("second", "turn-2")
        assert agent.tool_start_callback is first_wrapper

    asyncio.run(scenario())

    completed = [event["content"] for event in events if event.get("type") == "complete"]
    assert completed == ["✅ 已完成: tool-round-1", "✅ 已完成: tool-round-2"]
    assert agent.calls == 2
    assert agent.callback_pairs[0][0] is not agent.callback_pairs[1][0]
    assert agent.callback_pairs[0][1] is not agent.callback_pairs[1][1]


def test_supervisor_fallback_releases_matching_thread_turn(monkeypatch, tmp_path):
    """The defensive supervisor race path must close its thread-state ledger."""
    sid = "memomics-a1b2c3d4"
    session = _ws_session(sid, tmp_path)
    events = []
    _patch_chat_setup(monkeypatch, events)
    monkeypatch.setattr(server, "_sessions", {sid: session})
    monkeypatch.setattr(server, "_current_model", _cfg())

    class Agent:
        tools = []
        _interrupt_requested = False
        _pending_steer = ""

        def clear_interrupt(self):
            self._interrupt_requested = False

    class ThreadState:
        def __init__(self):
            self.started = []
            self.ended = []

        async def begin_turn_serialized(self, sid_arg, source):
            self.started.append((sid_arg, source))
            return object()

        def mark_turn_end(self, sid_arg):
            self.ended.append(sid_arg)

    class Supervisor:
        def is_running(self, _sid):
            return True

    ledger = ThreadState()
    session["agent"] = Agent()
    monkeypatch.setattr(server, "_thread_state", ledger)
    monkeypatch.setattr(server, "_task_supervisor", Supervisor())

    ws = _FakeWebSocket([json.dumps({
        "type": "chat", "session_id": sid, "message": "race", "request_id": "race-1",
    })])
    asyncio.run(server.ws_endpoint(ws))

    assert ledger.started == [(sid, "user")]
    assert ledger.ended == [sid]
    assert session["_user_turn_active"] is False
    assert any(event.get("code") == "turn_in_progress" for event in events)


def test_agent_and_ws_errors_do_not_echo_fake_secret(monkeypatch, tmp_path):
    sid = "memomics-a1b2c3d4"
    secret = "fake-secret-key-path-C:/private/demo.pem"
    session = _ws_session(sid, tmp_path)
    events = []
    monkeypatch.setattr(server, "_sessions", {sid: session})
    monkeypatch.setattr(server, "_current_model", _cfg())
    _patch_chat_setup(monkeypatch, events)
    monkeypatch.setattr(server, "_create_agent", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)))
    ws = _FakeWebSocket([json.dumps({
        "type": "chat", "session_id": sid, "message": "hello", "request_id": "secret-agent",
    })])
    asyncio.run(server.ws_endpoint(ws))
    agent_error = next(item for item in events if item.get("type") == "error")
    rendered = json.dumps(agent_error, ensure_ascii=False)
    assert agent_error["code"] == "agent_initialization_failed"
    assert agent_error["session_id"] == sid and agent_error["request_id"] == "secret-agent"
    assert "fake-secret" not in rendered and "RuntimeError" not in rendered and "C:/" not in rendered

    # Top-level failures after parsing a session id are equally scoped and
    # generic, with neither a traceback nor an exception string in the frame.
    monkeypatch.setattr(server, "_get_or_create_session", lambda _sid: (_ for _ in ()).throw(RuntimeError(secret)))
    ws_top = _FakeWebSocket([json.dumps({
        "type": "chat", "session_id": sid, "message": "again", "request_id": "secret-ws",
    })])
    asyncio.run(server.ws_endpoint(ws_top))
    top_error = ws_top.sent[-1]
    rendered_top = json.dumps(top_error, ensure_ascii=False)
    assert top_error["code"] == "websocket_error"
    assert top_error["session_id"] == sid and top_error["request_id"] == "secret-ws"
    assert "fake-secret" not in rendered_top and "RuntimeError" not in rendered_top and "C:/" not in rendered_top


def test_websocket_ack_precedes_visible_missing_config_error(monkeypatch, tmp_path):
    sid = "memomics-a1b2c3d4"
    session = {
        "id": sid, "title": "新会话", "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "messages": [],
        "model_config": {"provider": "openai", "base_url": "https://missing.invalid/v1", "api_key": "", "model": "missing"},
        "results_dir": str(tmp_path), "todos": [], "bg_running": False, "running_agent": None,
        "running_task": None, "lang": "zh", "progress_log": [], "reasoning_log": [],
        "_messages_loaded": True,
    }
    events = []
    monkeypatch.setattr(server, "_sessions", {sid: session})
    monkeypatch.setattr(server, "_current_model", dict(session["model_config"]))
    monkeypatch.setattr(server, "_get_session_db", lambda: None)
    monkeypatch.setattr(server, "_thread_state", None)
    monkeypatch.setattr(server, "_attach_ws", lambda *_args: None)
    monkeypatch.setattr(server, "_ensure_session_messages_loaded", lambda *_args: None)
    monkeypatch.setattr(server, "_auto_anchor_turn", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_maybe_switch_task_dir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_classify_intent", lambda *_args, **_kwargs: ("chat", 1.0, {}))
    monkeypatch.setattr(server, "_build_skill_injection", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(server, "_pinned_expect_emit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_red_hit_emit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_skill_invoke_emit", lambda *_args, **_kwargs: None)

    def emit(_session, message):
        item = dict(message)
        item.setdefault("session_id", _session["id"])
        events.append(item)

    monkeypatch.setattr(server, "_session_emit", emit)
    ws = _FakeWebSocket([json.dumps({"type": "chat", "session_id": sid, "message": "hello", "request_id": "r-1"})])
    asyncio.run(server.ws_endpoint(ws))

    assert ws.sent[0] == {"type": "chat_accepted", "session_id": sid, "request_id": "r-1"}
    error = next(item for item in events if item.get("type") == "error")
    assert error["session_id"] == sid and error["request_id"] == "r-1"
    assert error["need_setup"] is True
    assert session["_user_turn_active"] is False
