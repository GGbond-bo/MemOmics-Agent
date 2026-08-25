# -*- coding: utf-8 -*-
"""会话自动标题总结回归测试：内容感知总结、手动名保护、防抖防重入、持久化。

不变量：
- 用户手动改名（title_source=manual）后，自动总结永不覆盖；
- 自动总结每 5 条消息/分析完成触发，后台异步、失败静默；
- 撞名自动续号（state.db title 唯一约束不炸）；
- title_source 经 kv 表持久化，重启可恢复。
"""
import os
import json
import uuid
import httpx
import pytest

import server

# 2026-08-26: 标题生成走真实 LLM（FakeLLM 仅覆盖部分场景），无 key 环境
# （CI）下 LLM 调用失败导致断言全挂 → 标记 live_llm，默认排除
pytestmark = [pytest.mark.api, pytest.mark.live_llm]


def _inject_user_msgs(sid, n):
    s = server._sessions[sid]
    for i in range(n):
        s["messages"].append({
            "role": "user",
            "content": f"第{i + 1}条消息：分析人类骨骼肌单细胞数据",
            "time": "",
        })


class FakeResp:
    """mock chat/completions 响应：固定总结出一个标题"""

    def __init__(self, title="人类骨骼肌单细胞分析"):
        self._title = title

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._title}}]}


class FakeLLM:
    """可路由 mock LLM：按 prompt 关键词返回不同标题（多用户隔离测试）。

    - route: {关键词: 标题}，命中返回对应标题；未命中返回 default
    - fail: raise_for_status 抛异常（服务端错误）
    - timeout: httpx.post 抛 TimeoutException（网络超时）
    - empty: 返回空标题（LLM 输出无效）
    - calls: 记录每次请求体，可断言 prompt 确实用了该会话的内容
    """

    def __init__(self, default="通用分析", route=None, fail=False, timeout=False, empty=False):
        self.default = default
        self.route = route or {}
        self.fail = fail
        self.timeout = timeout
        self.empty = empty
        self.calls = []

    def __call__(self, url, **kw):
        self.calls.append(kw)
        if self.timeout:
            raise httpx.TimeoutException("llm timeout", request=None)
        if self.fail:
            raise RuntimeError("llm unavailable")
        prompt = (kw.get("json") or {}).get("messages", [{}])[0].get("content", "")
        title = self.default
        for key, t in self.route.items():
            if key in prompt:
                title = t
                break
        if self.empty:
            title = ""
        return FakeResp(title)


def _set_user_msgs(sid, contents):
    """整批覆盖会话用户消息（多场景内容注入）。"""
    s = server._sessions[sid]
    s["messages"] = [
        {"role": "user", "content": c, "time": ""} for c in contents
    ]


def _run_summary(sid, fake):
    """同步执行一次自动总结（绕过线程），mock LLM 并清锁。"""
    server._title_summary_locks.discard(sid)
    s = server._sessions[sid]
    s["_title_summary_at_msg"] = 0
    server._auto_summarize_title(sid)
    return fake.calls


def test_manual_title_never_overwritten(new_session):
    """用户手动改名后，自动总结永不覆盖（title_source=manual 守卫）"""
    s = server._sessions[new_session]
    s["title"] = "我的专属会话名"
    s["title_source"] = "manual"
    server._persist_title_source(new_session, "manual")
    _inject_user_msgs(new_session, 10)
    s["_title_summary_at_msg"] = 0
    server._title_summary_locks.clear()
    server._schedule_title_summary(new_session)
    assert new_session not in server._title_summary_locks  # 没启动线程
    assert s["title"] == "我的专属会话名"  # 原封不动


def test_debounce_skips_early(new_session):
    """防抖：距上次总结不足 4 条用户消息 → 不调度"""
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    _inject_user_msgs(new_session, 5)
    s["_title_summary_at_msg"] = 3  # 距上次只有 2 条
    server._title_summary_locks.clear()
    server._schedule_title_summary(new_session)
    assert new_session not in server._title_summary_locks


def test_reentrancy_skips_running(new_session):
    """防重入：已有总结线程在跑 → 不重复调度"""
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    _inject_user_msgs(new_session, 8)
    s["_title_summary_at_msg"] = 0
    server._title_summary_locks.add(new_session)  # 模拟已有线程
    server._schedule_title_summary(new_session)
    assert new_session in server._title_summary_locks  # 集合保留，未启动新线程
    server._title_summary_locks.discard(new_session)


def test_auto_summary_updates_title(new_session, monkeypatch):
    """总结执行：mock LLM → 标题更新 + title_source=auto + state.db 同步 + WS 事件"""
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp())
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    s["title"] = "pytest-初始标题"
    _inject_user_msgs(new_session, 8)
    s["_title_summary_at_msg"] = 0
    server._title_summary_locks.clear()
    server._auto_summarize_title(new_session)
    assert new_session not in server._title_summary_locks  # finally 清理
    assert s["title"].startswith("人类骨骼肌单细胞分析")  # 容忍其他测试留下的同名
    assert s["title_source"] == "auto"
    db = server._get_session_db()
    if db:
        assert db.get_session_title(new_session) == "人类骨骼肌单细胞分析"
    # WS 推送事件已记录（切回该会话时前端靠它刷新标题）
    evs = [m for m in s.get("progress_log", []) if m.get("type") == "session_title"]
    assert evs and evs[-1]["title"] == "人类骨骼肌单细胞分析"


def test_auto_summary_title_collision_continues(new_session, monkeypatch):
    """撞名：state.db title 唯一约束 → 自动续号而非失败（用唯一标题，避免跨进程残留撞名）"""
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    s["title"] = "pytest-初始标题"
    _inject_user_msgs(new_session, 8)
    s["_title_summary_at_msg"] = 0
    db = server._get_session_db()
    other = None
    collide_title = f"人类骨骼肌单细胞分析-{uuid.uuid4().hex[:4]}"
    try:
        if db:
            other = server._create_session(title=f"占位-{uuid.uuid4().hex[:4]}")["id"]
            db.set_session_title(other, collide_title)  # 占用同名
        server._title_summary_locks.clear()
        monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp(collide_title))
        server._auto_summarize_title(new_session)
        assert s["title"].startswith(collide_title)
        assert s["title"] != collide_title  # 已续号
    finally:
        if other:
            server._sessions.pop(other, None)
            if db:
                try:
                    db.set_session_title(other, None)  # 清掉 db 里的标题，释放唯一约束
                except Exception:
                    pass


def test_title_source_kv_roundtrip(new_session):
    """kv 持久化：manual/auto 标记可恢复；未标记会话默认 auto（历史兼容）"""
    server._persist_title_source(new_session, "manual")
    assert server._load_title_source(new_session) == "manual"
    server._persist_title_source(new_session, "auto")
    assert server._load_title_source(new_session) == "auto"
    assert server._load_title_source(f"memomics-{uuid.uuid4().hex[:8]}") == "auto"


# ============================================================
# 多场景：不同内容类型、LLM 各种输出形态
# ============================================================

def test_scenario_chat_topic(new_session, monkeypatch):
    """场景：普通聊天（非生信）也能总结出合适标题"""
    fake = FakeLLM(route={"云南": "暑假云南旅行计划"})
    monkeypatch.setattr(httpx, "post", fake)
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    s["title"] = "pytest-初始标题"
    _set_user_msgs(new_session, [
        "我们暑假去云南吧",
        "想去大理和丽江",
        "预算大概多少合适",
        "需要提前订酒店吗",
        "行程怎么安排比较好",
    ])
    server._auto_summarize_title(new_session)
    assert s["title"] == "暑假云南旅行计划"
    assert s["title_source"] == "auto"


def test_scenario_too_few_messages(new_session, monkeypatch):
    """场景：消息太少（<4 条）→ 不调用 LLM，锁释放，标题不动"""
    fake = FakeLLM()
    monkeypatch.setattr(httpx, "post", fake)
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    s["title"] = "pytest-初始标题"
    _set_user_msgs(new_session, ["就一句话"])
    server._auto_summarize_title(new_session)
    assert fake.calls == []  # 没调 LLM
    assert new_session not in server._title_summary_locks  # 锁已释放
    assert s["title"] == "pytest-初始标题"


def test_scenario_llm_failure_keeps_title(new_session, monkeypatch):
    """场景：LLM 服务端错误 → 静默保留旧名，锁必须释放（finally）"""
    fake = FakeLLM(fail=True)
    monkeypatch.setattr(httpx, "post", fake)
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    s["title"] = "pytest-初始标题"
    _set_user_msgs(new_session, [f"内容{i}" for i in range(6)])
    server._auto_summarize_title(new_session)
    assert s["title"] == "pytest-初始标题"
    assert new_session not in server._title_summary_locks


def test_scenario_llm_timeout_keeps_title(new_session, monkeypatch):
    """场景：LLM 超时 → 静默保留旧名，锁释放"""
    fake = FakeLLM(timeout=True)
    monkeypatch.setattr(httpx, "post", fake)
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    s["title"] = "pytest-初始标题"
    _set_user_msgs(new_session, [f"内容{i}" for i in range(6)])
    server._auto_summarize_title(new_session)
    assert s["title"] == "pytest-初始标题"
    assert new_session not in server._title_summary_locks


def test_scenario_empty_output_aborted(new_session, monkeypatch):
    """场景：LLM 返回空/无效内容 → 放弃总结"""
    fake = FakeLLM(empty=True)
    monkeypatch.setattr(httpx, "post", fake)
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    s["title"] = "pytest-初始标题"
    _set_user_msgs(new_session, [f"内容{i}" for i in range(6)])
    server._auto_summarize_title(new_session)
    assert s["title"] == "pytest-初始标题"
    assert new_session not in server._title_summary_locks


def test_scenario_long_title_truncated(new_session, monkeypatch):
    """场景：LLM 输出超长（50 字）→ 截断到 30 字"""
    long_title = "很长的分析标题" * 10  # 50 字
    fake = FakeLLM(default=long_title)
    monkeypatch.setattr(httpx, "post", fake)
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    s["title"] = "pytest-初始标题"
    _set_user_msgs(new_session, [f"内容{i}" for i in range(6)])
    server._auto_summarize_title(new_session)
    assert len(s["title"]) <= 30
    assert s["title"].startswith("很长的分析标题")


def test_scenario_noisy_title_cleaned(new_session, monkeypatch):
    """场景：LLM 输出带引号/编号/破折号 → 清理后入库"""
    fake = FakeLLM(default='  "1. -hdWGCNA 网络构建参数选择" ')
    monkeypatch.setattr(httpx, "post", fake)
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    s["title"] = "pytest-初始标题"
    _set_user_msgs(new_session, [f"内容{i}" for i in range(6)])
    server._auto_summarize_title(new_session)
    assert s["title"] == "hdWGCNA 网络构建参数选择"
    assert not s["title"].startswith(("1.", '"', "-"))


def test_scenario_same_title_skipped(new_session, monkeypatch):
    """场景：总结结果与现名相同 → 不写回、不发事件（幂等）"""
    fake = FakeLLM(default="人类骨骼肌单细胞分析")
    monkeypatch.setattr(httpx, "post", fake)
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    s["title"] = "人类骨骼肌单细胞分析"  # 已是最佳名
    _set_user_msgs(new_session, [f"内容{i}" for i in range(6)])
    evs_before = len(s.get("progress_log", []))
    server._auto_summarize_title(new_session)
    assert s["title"] == "人类骨骼肌单细胞分析"
    assert len(s.get("progress_log", [])) == evs_before  # 无新事件


# ============================================================
# 多角度：机制细节（投影/审计/节流/内容校验）
# ============================================================

def test_angle_meta_projection_synced(new_session, monkeypatch, tmp_path):
    """角度：results_dir 下 session.meta.json 的 display_name 同步更新"""
    fake = FakeLLM(default="人类骨骼肌单细胞分析")
    monkeypatch.setattr(httpx, "post", fake)
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    s["title"] = "pytest-初始标题"
    meta_path = tmp_path / "session.meta.json"
    meta_path.write_text('{"session_id": "x", "display_name": "旧名"}', encoding="utf-8")
    s["results_dir"] = str(tmp_path)
    _set_user_msgs(new_session, [f"内容{i}" for i in range(6)])
    server._auto_summarize_title(new_session)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["display_name"] == "人类骨骼肌单细胞分析"
    assert "renamed_at" in meta


def test_angle_rename_event_audited(new_session, monkeypatch):
    """角度：自动改名也写审计（rename_events.jsonl，source=auto）"""
    fake = FakeLLM(default="人类骨骼肌单细胞分析")
    monkeypatch.setattr(httpx, "post", fake)
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    s["title"] = "pytest-初始标题"
    _set_user_msgs(new_session, [f"内容{i}" for i in range(6)])
    server._auto_summarize_title(new_session)
    log_path = os.path.join(server.HERMES_HOME_DIR, "sessions", "rename_events.jsonl")
    if not os.path.isfile(log_path):
        pytest.skip("rename_events.jsonl 不存在（HERMES_HOME 未初始化）")
    last = json.loads(open(log_path, encoding="utf-8").read().strip().split("\n")[-1])
    assert last["session_id"] == new_session
    assert last["source"] == "auto"
    assert last["new_title"] == "人类骨骼肌单细胞分析"


def test_angle_prompt_uses_session_content(new_session, monkeypatch):
    """角度：prompt 确实带上该会话的用户消息（总结基于真实内容）"""
    fake = FakeLLM(route={"hdWGCNA": "hdWGCNA 网络构建"})
    monkeypatch.setattr(httpx, "post", fake)
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    _set_user_msgs(new_session, [
        "hdWGCNA 跑网络构建",
        "soft power 选 12",
        "模块合并阈值 0.25",
        "hub 基因怎么挑",
        "模块与表型关联分析",
    ])
    server._auto_summarize_title(new_session)
    assert fake.calls, "应调用一次 LLM"
    prompt = fake.calls[0]["json"]["messages"][0]["content"]
    assert "hdWGCNA" in prompt  # 内容确实进入 prompt
    assert "soft power" in prompt
    assert s["title"] == "hdWGCNA 网络构建"


def test_angle_consecutive_summaries_throttled(new_session, monkeypatch):
    """角度：总结成功后 _title_summary_at_msg 推进 → 第二次调度被防抖拦截"""
    fake = FakeLLM(default="人类骨骼肌单细胞分析")
    monkeypatch.setattr(httpx, "post", fake)
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    s["title"] = "pytest-初始标题"
    _set_user_msgs(new_session, [f"内容{i}" for i in range(8)])
    server._auto_summarize_title(new_session)
    assert s["title"] == "人类骨骼肌单细胞分析"
    assert int(s["_title_summary_at_msg"]) == 8  # 指针推进
    n_calls = len(fake.calls)
    server._schedule_title_summary(new_session)  # 没有新增消息
    assert new_session not in server._title_summary_locks  # 防抖拦截，未启动
    assert len(fake.calls) == n_calls  # 未再调 LLM


# ============================================================
# 多用户：多会话并存、隔离、撞名递增、故障隔离
# ============================================================

def test_multi_user_sessions_isolated(new_session, monkeypatch):
    """多用户：两个会话内容不同 → 各自总结互不污染"""
    other = server._create_session(title=f"其他用户-{uuid.uuid4().hex[:4]}")["id"]
    try:
        fake = FakeLLM(route={"骨骼肌": "人类骨骼肌单细胞分析", "ATAC": "小鼠脑 ATAC 峰值分析"})
        monkeypatch.setattr(httpx, "post", fake)
        s1 = server._sessions[new_session]
        s1["title_source"] = "auto"
        s1["title"] = "pytest-初始标题"
        _set_user_msgs(new_session, [
            "人类骨骼肌单细胞数据",
            "UMAP 聚类看分群",
            "marker 基因注释",
            "细胞类型比例差异",
        ])
        s2 = server._sessions[other]
        s2["title_source"] = "auto"
        s2["title"] = "pytest-初始标题"
        _set_user_msgs(other, [
            "小鼠脑 ATAC-seq 数据",
            "peak calling 用 MACS2",
            "motif 富集分析",
            "差异开放区域",
        ])
        server._auto_summarize_title(new_session)
        server._auto_summarize_title(other)
        assert s1["title"] == "人类骨骼肌单细胞分析"
        assert s2["title"].startswith("小鼠脑 ATAC 峰值分析")
        assert len(fake.calls) == 2  # 两次独立调用
    finally:
        server._sessions.pop(other, None)
        db = server._get_session_db()
        if db:
            try:
                db.set_session_title(other, None)
            except Exception:
                pass


def test_multi_user_collision_sequence(new_session, monkeypatch):
    """多用户：多个会话总结出同名 → 唯一约束自动续号且互不覆盖"""
    fake = FakeLLM(default="hdWGCNA 网络构建")
    monkeypatch.setattr(httpx, "post", fake)
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    s["title"] = "pytest-初始标题"
    _set_user_msgs(new_session, [f"内容{i}" for i in range(6)])
    db = server._get_session_db()
    others = []
    try:
        if db:
            others.append(server._create_session(title=f"占位-{uuid.uuid4().hex[:4]}")["id"])
            db.set_session_title(others[0], "hdWGCNA 网络构建")  # 已占用
        server._auto_summarize_title(new_session)
        t1 = s["title"]
        assert t1 != "hdWGCNA 网络构建"  # 续号
        assert t1.startswith("hdWGCNA 网络构建")
        # 第二个用户也总结出同名 → 继续递增，不与第一个冲突
        s2 = server._sessions[new_session]
        s2["title"] = "pytest-初始标题"
        s2["title_source"] = "auto"
        _set_user_msgs(new_session, [f"更多内容{i}" for i in range(6)])
        server._auto_summarize_title(new_session)
        t2 = s2["title"]
        assert t2 != t1
        assert t2.startswith("hdWGCNA 网络构建")
    finally:
        for o in others:
            server._sessions.pop(o, None)
            if db:
                try:
                    db.set_session_title(o, None)
                except Exception:
                    pass


def test_multi_user_manual_and_auto_coexist(new_session, monkeypatch):
    """多用户：manual 会话（用户自定义名）与 auto 会话并存，互不干扰"""
    other = server._create_session(title=f"手动用户-{uuid.uuid4().hex[:4]}")["id"]
    try:
        fake = FakeLLM(default="人类骨骼肌单细胞分析")
        monkeypatch.setattr(httpx, "post", fake)
        # auto 会话正常总结
        s1 = server._sessions[new_session]
        s1["title_source"] = "auto"
        s1["title"] = "pytest-初始标题"
        _set_user_msgs(new_session, [f"内容{i}" for i in range(6)])
        # manual 会话：用户自己起的名字
        s2 = server._sessions[other]
        s2["title_source"] = "manual"
        s2["title"] = "我的专属会话名"
        server._persist_title_source(other, "manual")
        _set_user_msgs(other, [f"内容{i}" for i in range(6)])
        server._auto_summarize_title(new_session)
        server._auto_summarize_title(other)
        assert s1["title"] == "人类骨骼肌单细胞分析"
        assert s2["title"] == "我的专属会话名"  # 手动名未被覆盖
    finally:
        server._sessions.pop(other, None)


def test_multi_user_failure_isolated(new_session, monkeypatch):
    """多用户：一个会话 LLM 失败，不影响另一个会话总结"""
    other = server._create_session(title=f"用户B-{uuid.uuid4().hex[:4]}")["id"]
    try:
        # 第一次调用失败（会话A），第二次成功（会话B）
        calls = {"n": 0}

        def flaky(url, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("llm down")
            return FakeResp("用户B的分析标题")

        monkeypatch.setattr(httpx, "post", flaky)
        s1 = server._sessions[new_session]
        s1["title_source"] = "auto"
        s1["title"] = "pytest-A"
        _set_user_msgs(new_session, [f"内容{i}" for i in range(6)])
        s2 = server._sessions[other]
        s2["title_source"] = "auto"
        s2["title"] = "pytest-B"
        _set_user_msgs(other, [f"内容{i}" for i in range(6)])
        server._auto_summarize_title(new_session)  # 失败
        server._auto_summarize_title(other)  # 成功
        assert s1["title"] == "pytest-A"  # 失败方保留旧名
        assert s2["title"].startswith("用户B的分析标题")  # 成功方正常更新
        assert new_session not in server._title_summary_locks
        assert other not in server._title_summary_locks
    finally:
        server._sessions.pop(other, None)
        db = server._get_session_db()
        if db:
            try:
                db.set_session_title(other, None)
            except Exception:
                pass
