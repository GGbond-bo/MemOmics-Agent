# -*- coding: utf-8 -*-
"""刷新后"原封不动"恢复交互框 —— 2026-09-25。

需求（用户原话）：
    "还有，刷新之后，思考这些都不见了。我要刷新之后交互框已经展示的东西
     要原封不动的保留和展示"

也就是说：刷新（F5）之后，交互框里已经展示过的东西要原样回来，而不是重新从服务器
历史里"再长一遍"：
  1) 💭 思考行（含展开/收起状态、字数提示、全文）原样回来；
  2) 工具块、进度时间线、正在流式输出的那段文字原样回来；
  3) 滚动位置原样回来；
  4) 服务器确实有新消息时，不能让"原样"把新消息吞掉 —— 那种情况必须重新渲染历史。

三层验证：
1) 本文件 —— 静态接线断言：落盘/恢复的调用点真的在 index.html 里；
2) view_snapshot_frontend.cjs —— 真行为测试：把前端函数抠出来，在桩 DOM + 假
   localStorage + 假 IndexedDB 上跑，断言"存下来的画面 = 恢复出来的画面"（逐字节）；
3) CDP 真机 —— 浏览器里刷新一次，比对画面结构与字节数（另有记录）。
"""
import os
import subprocess

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(TESTS_DIR, "..", "index.html")

with open(HTML_PATH, encoding="utf-8") as _f:
    HTML = _f.read()

_START = HTML.index('// === 刷新后"原封不动"恢复交互框')
VIEW_CODE = HTML[_START:HTML.index("function showNewSessionWelcome(", _START)]


class TestSnapshotLayerExists:
    """落盘/恢复这一层真的在，而且是同一份实现（没有两套各写各的）。"""

    def test_section_present(self):
        assert '刷新后"原封不动"恢复交互框' in HTML

    @pytest.mark.parametrize("fn", [
        "_viewRecord", "_viewShrink", "_viewSafeItems", "_persistViewSnapshot", "_persistViewSoon",
        "_persistViewHot", "_viewHotRead", "_loadViewSnapshot", "_viewApplyToCache",
        "_restorePersistedView", "_dropViewSnapshot", "_settleRestoredView", "_insertMoreMsgsHint",
        "_afterViewReady", "_viewIsStreamEvent", "_viewRunStart", "_snapshotCurrentSession",
    ])
    def test_function_defined_once(self, fn):
        assert HTML.count("function %s(" % fn) == 1

    def test_three_tiers(self):
        # 内存缓存 → localStorage 热备（同步，扛得住 F5）→ IndexedDB（大画面）
        assert "var _VIEW_HOT_KEY = 'memomics_view_hot_'" in HTML
        assert "var _VIEW_DB = 'memomics_view_db'" in HTML
        assert "_VIEW_STORE = 'views'" in HTML

    def test_ttl_and_keep(self):
        assert "_VIEW_TTL_MS = 7 * 24 * 3600 * 1000" in HTML   # 7 天没动过就丢
        assert "_VIEW_KEEP = 8" in HTML                        # 最多留 8 个会话


class TestRecordShape:
    """存下去的东西必须够还原画面，而且不能把"在不在跑"写死。"""

    def test_record_keeps_html_and_counts(self):
        rec = VIEW_CODE[VIEW_CODE.index("function _viewRecord("):]
        rec = rec[:rec.index("\nfunction ", 10)]
        for field in ("html:", "fullText:", "reasoningText:", "items:", "scrollTop:", "msgCount:", "sid:", "ts:"):
            assert field in rec, field

    def test_running_not_persisted(self):
        rec = VIEW_CODE[VIEW_CODE.index("function _viewRecord("):]
        rec = rec[:rec.index("\nfunction ", 10)]
        # 快照只是画面；在不在跑由服务器说了算（否则刷新后会假装还在跑/假装已结束）
        assert "running:" not in rec
        assert "agentRunning" not in rec

    def test_streaming_assistant_persisted(self):
        assert "streamingAssistant: !!cache.streamingAssistant" in VIEW_CODE

    def test_safe_items_drops_unserializable(self):
        assert "function _viewSafeItems(" in VIEW_CODE
        assert "JSON.stringify(" in VIEW_CODE[VIEW_CODE.index("function _viewSafeItems("):VIEW_CODE.index("function _viewShrink(")]

    def test_shrink_has_three_levels(self):
        shrink = VIEW_CODE[VIEW_CODE.index("function _viewShrink("):]
        shrink = shrink[:shrink.index("\nfunction ", 10)]
        assert "items: []" in shrink
        assert "reasoningText: ''" in shrink


class TestSnapshotTriggers:
    """什么时候落盘。"""

    def test_stream_events_trigger_run_timer(self):
        head = HTML[HTML.index("function handleMessage(msg) {"):]
        head = head[:head.index("\n", 200)]
        assert "_viewIsStreamEvent(msg.type)" in head
        assert "_viewRunStart()" in head
        # 别在这里写死 msg.type === 'reasoning'，会干扰"思考行只在一处处理"的静态检查
        assert "msg.type === 'reasoning'" not in head

    def test_stream_type_table(self):
        assert "var _VIEW_STREAM_TYPES = { delta: 1, reasoning: 1, thinking: 1" in HTML
        assert "function _viewIsStreamEvent(t) { return !!_VIEW_STREAM_TYPES[t]; }" in HTML

    def test_run_timer_persists_every_5s(self):
        run = VIEW_CODE[VIEW_CODE.index("function _viewRunStart("):]
        run = run[:run.index("\nfunction ", 10)]
        assert "if (!agentRunning) return;" in run      # 跑完自己收工
        assert "_snapshotCurrentSession();" in run
        assert "setTimeout(tick, 5000)" in run

    def test_debounce_2_5s(self):
        soon = VIEW_CODE[VIEW_CODE.index("function _persistViewSoon("):]
        soon = soon[:soon.index("\nfunction ", 10)]
        assert "}, 2500);" in soon

    def test_snapshot_records_msg_count(self):
        # _snapshotCurrentSession 是老函数（这次只加了两行），在快照代码段之前
        snap = HTML[HTML.index("function _snapshotCurrentSession("):]
        snap = snap[:snap.index("\nfunction ", 10)]
        assert "cache.msgCount = messagesEl.querySelectorAll('.message').length;" in snap
        assert "_persistViewSoon(currentSid);" in snap

    @pytest.mark.parametrize("hook", ["pagehide", "beforeunload", "visibilitychange"])
    def test_unload_hooks(self, hook):
        assert "addEventListener('%s'" % hook in VIEW_CODE

    def test_unload_uses_sync_hot_path(self):
        # IDB 是异步的，刷新瞬间可能被掐断 → 必须有同步兜底
        i = VIEW_CODE.index("addEventListener('pagehide'")
        assert "_persistViewHot()" in VIEW_CODE[i:i + 200]

    def test_idle_heartbeat(self):
        assert "setInterval(function() {" in VIEW_CODE
        assert "if (!currentSid || agentRunning) return;" in VIEW_CODE   # 跑的时候有 5 秒那条，不重复
        assert "_viewLastLen" in VIEW_CODE

    def test_switching_session_persists_previous(self):
        sw = HTML[HTML.index("function switchSession(sid)"):]
        sw = sw[:sw.index("\nfunction ", 10)]
        assert "var _prevSid = currentSid;" in sw
        assert "_persistViewSnapshot(_prevSid);" in sw

    def test_delete_session_drops_snapshot(self):
        # 会话删了，画面快照不能留着（否则下次切进来会"复活"已删的对话）
        assert HTML.count("_dropViewSnapshot(sid);") >= 2


class TestRestorePath:
    """切会话/刷新进来时怎么把画面摆回去。"""

    def test_switch_reads_hot_synchronously(self):
        sw = HTML[HTML.index("function switchSession(sid)"):]
        sw = sw[:sw.index("\nfunction ", 10)]
        i = sw.index("_viewHotRead(sid)")
        assert "_viewApplyToCache(sid, _hotView);" in sw[i:]
        assert "_restoreSessionSnapshot(cached);" in sw[i:]

    def test_waits_for_idb_before_history_render(self):
        # 两处 HTTP 渲染（历史消息、进度时间线）都要等快照先落地，否则会先闪一下空画面
        assert HTML.count("_afterViewReady(_viewReady, function") == 2

    def test_newer_snapshot_wins(self):
        load = VIEW_CODE[VIEW_CODE.index("function _loadViewSnapshot("):]
        load = load[:load.index("\nfunction ", 10)]
        assert "(hot.ts || 0) > (rec.ts || 0)" in load

    def test_does_not_reapply_older(self):
        rp = VIEW_CODE[VIEW_CODE.index("function _restorePersistedView("):]
        rp = rp[:rp.index("\nfunction ", 10)]
        assert "cache.viewTs" in rp
        assert "if (cache.hasSnapshot && !cache.fromPersist) return false;" in rp   # 同页面已有实时画面就别动
        assert "seq !== _switchSeq" in rp                                          # 会话已经切走了就别摆

    def test_apply_marks_from_persist_and_ts(self):
        ap = VIEW_CODE[VIEW_CODE.index("function _viewApplyToCache("):]
        ap = ap[:ap.index("\nfunction ", 10)]
        assert "cache.fromPersist = true;" in ap
        assert "cache.viewTs = rec.ts || 0;" in ap

    def test_restore_is_byte_identical(self):
        rs = HTML[HTML.index("function _restoreSessionSnapshot("):]
        rs = rs[:rs.index("\nfunction ", 10)]
        assert "messagesEl.innerHTML = cache.messageHtml || '';" in rs
        assert "_htmlOnAssign = messagesEl.innerHTML;" in rs     # 自检：还原瞬间的画面

    def test_reasoning_text_fallback_from_dom(self):
        rs = HTML[HTML.index("function _restoreSessionSnapshot("):]
        rs = rs[:rs.index("\nfunction ", 10)]
        assert "querySelector('.reasoning-block .reasoning-content')" in rs

    def test_restore_puts_streaming_bubble_back(self):
        rs = HTML[HTML.index("function _restoreSessionSnapshot("):]
        rs = rs[:rs.index("\nfunction ", 10)]
        assert "cache.streamingAssistant" in rs

    def test_selfcheck_hook(self):
        rs = HTML[HTML.index("function _restoreSessionSnapshot("):]
        rs = rs[:rs.index("\nfunction ", 10)]
        assert "window.__memomicsViewRestore" in rs
        assert "byteEqualOnAssign" in rs
        assert "byteEqual:" in rs

    def test_settle_clears_fake_running(self):
        st = VIEW_CODE[VIEW_CODE.index("function _settleRestoredView("):]
        st = st[:st.index("\nfunction ", 10)]
        assert "classList.remove('running')" in st
        assert "_rbMetaText(" in st

    def test_more_msgs_hint(self):
        mh = VIEW_CODE[VIEW_CODE.index("function _insertMoreMsgsHint("):]   # 这一段最后一个函数
        assert "more-msgs-hint" in mh
        assert "加载更早的消息" in mh
        assert "显示全部 " in mh


class TestHistoryFallback:
    """服务器有新消息时，宁可重新渲染，也不能把新消息吞掉。"""

    def test_freshness_guard_in_history_path(self):
        i = HTML.index("fetch('/api/sessions/' + sid + '/messages?limit=100')")
        seg = HTML[i:i + 6000]
        assert "cached.fromPersist" in seg
        assert "_srvCount <= cached.msgCount" in seg

    def test_drop_when_server_has_more(self):
        i = HTML.index("fetch('/api/sessions/' + sid + '/messages?limit=100')")
        seg = HTML[i:i + 6000]
        j = seg.index("_srvCount <= cached.msgCount")
        assert "_dropViewSnapshot(sid)" in seg[j:]

    def test_containment_fallback(self):
        # 条数只差一点点（统计口径差异）时，再看最后一条消息是否已经在画面里，是就别冲掉画面
        i = HTML.index("fetch('/api/sessions/' + sid + '/messages?limit=100')")
        seg = HTML[i:i + 6000]
        assert "_srvCount <= cached.msgCount + 3" in seg
        assert "_viewText.indexOf(_tail) >= 0" in seg

    def test_hint_when_trimmed(self):
        assert "_insertMoreMsgsHint(sid" in HTML

    def test_drop_helper_clears_both_stores(self):
        dr = VIEW_CODE[VIEW_CODE.index("function _dropViewSnapshot("):]
        dr = dr[:dr.index("\nfunction ", 10)]
        assert "localStorage.removeItem(_VIEW_HOT_KEY + sid);" in dr
        assert "_viewDbDelete(sid);" in dr


class TestFailuresAreSwallowed:
    """隐私模式/配额满/坏数据都不能把聊天页面搞崩。"""

    def test_idb_errors_swallowed(self):
        for fn in ("_viewDbOpen", "_viewDbPut", "_viewDbGet", "_viewDbAll", "_viewDbDelete"):
            body = VIEW_CODE[VIEW_CODE.index("function %s(" % fn):]
            body = body[:body.index("\nfunction ", 10)]
            assert ".catch(" in body or "reject(" in body or "try {" in body, fn

    def test_hot_write_failure_swallowed(self):
        i = VIEW_CODE.index("localStorage.setItem(_VIEW_HOT_KEY + sid")
        assert "try {" in VIEW_CODE[i - 200:i]

    def test_hot_read_tolerates_junk(self):
        hr = VIEW_CODE[VIEW_CODE.index("function _viewHotRead("):]
        hr = hr[:hr.index("\nfunction ", 10)]
        assert "try {" in hr and "catch" in hr

    def test_hot_max_guards_quota(self):
        assert "var _VIEW_HOT_MAX = 3000000;" in HTML
        hot = VIEW_CODE[VIEW_CODE.index("function _persistViewHot("):]
        hot = hot[:hot.index("\nfunction ", 10)]
        assert "_VIEW_HOT_MAX" in hot


class TestFrontendHarness:
    """真行为测试：抠出真实函数在桩 DOM 上跑。"""

    def test_harness_passes(self):
        node = shutil_which_node()
        if not node:
            pytest.skip("本机没有 node")
        r = subprocess.run([node, os.path.join(TESTS_DIR, "view_snapshot_frontend.cjs")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
        assert "0 fail" in (r.stdout or "")


def shutil_which_node():
    import shutil
    return shutil.which("node")
