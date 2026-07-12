#!/usr/bin/env python3
"""
session_list_fade_simulator.py — 模拟 WebUI session list 的全部生命周期
模拟真实的并发竞态：fetch 延迟、AbortController、fingerprint 防抖、filterSessions、switchSession
"""
import asyncio, json, sys, time

# ============== 模拟服务器 ==============
_sessions = {}
_next_id = 1

def create_sessions(n):
    """创建 n 个测试会话"""
    global _next_id
    for i in range(n):
        sid = f"memomics-test-{_next_id:04d}"
        _next_id += 1
        _sessions[sid] = {
            "id": sid,
            "title": f"Session {sid[-4:]}",
            "created": f"2026-07-{10+(i%20):02d}T{10+i%14:02d}:00",
            "is_running": False,
            "msg_count": (i + 1) * 10,
            "restored": i < 2,
            "bg_running": False
        }

def api_sessions():
    """模拟 /api/sessions 返回"""
    return {"sessions": list(_sessions.values())}

def api_delete(sid):
    """模拟 DELETE /api/sessions/{sid}"""
    if sid in _sessions:
        del _sessions[sid]

# ============== 模拟前端状态机 ==============
class SessionListSimulator:
    def __init__(self):
        self._allSessions = []
        self._lastSessionFingerprint = ''
        self.currentSid = None
        self._loadSessionsCtl = None  # mock AbortController
        self._rendered = []  # 记录每次 render 的 session 数量
        self._renderErrors = []  # 记录渲染错误
        self._activeErrors = []  # 记录 .active 高亮错误
        self._searchText = ''  # 搜索框文本
        self._isSearching = False
        self._domVisible = True
        self._consecutiveEmpty = 0  # 连续空响应计数

    # ---------- JS 函数模拟 ----------
    async def loadSessions(self):
        # 模拟 AbortController
        ctl = {"aborted": False}
        if self._loadSessionsCtl:
            self._loadSessionsCtl["aborted"] = True  # 取消旧请求
        self._loadSessionsCtl = ctl
        try:
            await asyncio.sleep(0.05)  # 网络延迟
            if ctl["aborted"]:
                raise asyncio.CancelledError("AbortError")
            d = api_sessions()
            sessions = d.get("sessions", [])
            # 连续空响应防护：需要连续2次空响应才接受
            if len(sessions) == 0 and len(self._allSessions) > 0:
                self._consecutiveEmpty += 1
                if self._consecutiveEmpty < 2:
                    return  # 忽略第1次空响应
            else:
                self._consecutiveEmpty = 0
            self._allSessions = sessions
            self.renderSessionList([s.copy() for s in sessions])
        except asyncio.CancelledError:
            pass

    def updateSessionList(self):
        asyncio.create_task(self.loadSessions())

    def renderSessionList(self, sessions):
        # 排序
        sessions.sort(key=lambda s: (
            1 if s.get("restored") else 0,
            s.get("created", "")
        ), reverse=bool(not sessions or not sessions[0].get("restored")))
        sessions.sort(key=lambda s: 1 if s.get("restored") else 0)
        
        # fingerprint
        fp = ",".join(
            f'{s["id"]}|{1 if s.get("is_running") else 0}|{s.get("msg_count", 0)}'
            for s in sessions
        )
        
        if self._searchText:
            # 如果搜索框有文本，这是 filterSessions 的调用
            pass
        elif len(self._allSessions) != len(sessions):
            self._renderErrors.append(
                f"renderSessionList received {len(sessions)} sessions, "
                f"but _allSessions has {len(self._allSessions)}"
            )
        
        if fp == self._lastSessionFingerprint:
            # 指纹匹配 → 只更新 .active
            if self.currentSid:
                found = any(s["id"] == self.currentSid for s in sessions)
                if not found and len(sessions) > 0:
                    self._activeErrors.append(
                        f"currentSid={self.currentSid} not in session list "
                        f"({len(sessions)} sessions)"
                    )
            return
        
        self._lastSessionFingerprint = fp
        self._rendered.append(len(sessions))
        self._domVisible = len(sessions) > 0

    def switchSession(self, sid):
        self.currentSid = sid
        self.updateSessionList()

    def filterSessions(self, kw):
        if not kw:
            self._searchText = ''
            if self._allSessions:
                self.renderSessionList([s.copy() for s in self._allSessions])
            return
        self._searchText = kw
        filtered = [s for s in self._allSessions
                     if kw.lower() in s.get("title", "").lower()]
        self.renderSessionList(filtered)

    def deleteSession(self, sid):
        api_delete(sid)
        if self.currentSid == sid:
            self.currentSid = None
        self.updateSessionList()


# ============== 测试用例 ==============
FAIL = 0
PASS = 0

def check(condition, desc):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {desc}")
    else:
        FAIL += 1
        print(f"  FAIL: {desc}")

async def test_cases():
    global PASS, FAIL
    PASS = FAIL = 0

    # === T1: 正常初始化 ===
    print("\n--- T1: 初始化加载 5 个会话 ---")
    sim = SessionListSimulator()
    create_sessions(5)
    await sim.loadSessions()
    check(len(sim._allSessions) == 5, "加载 5 个会话")
    check(len(sim._rendered) == 1, "第一次渲染触发 1 次")
    check(sim._rendered[0] == 5, "渲染 5 个会话")
    check(sim._domVisible, "DOM 可见")

    # === T2: 点击会话不消失 ===
    print("\n--- T2: 点击会话后列表保持 5 个 ---")
    sim.switchSession(sim._allSessions[2]["id"])
    await asyncio.sleep(0.1)
    check(len(sim._allSessions) == 5, "点击后仍有 5 个会话")
    check(sim.currentSid == sim._allSessions[2]["id"], "currentSid 正确切换")
    check(sim._domVisible, "DOM 仍然可见")

    # === T3: 快速连续点击 5 个不同会话 ===
    print("\n--- T3: 快速连续点击 5 个不同会话 ---")
    for s in sim._allSessions:
        sim.switchSession(s["id"])
    await asyncio.sleep(0.2)
    check(len(sim._allSessions) == 5, "5 次快速点击后仍有 5 个会话")
    check(sim.currentSid is not None, "currentSid 不为空")
    check(sim._domVisible, "DOM 可见")
    last_sid = sim._allSessions[4]["id"]
    check(any(s_id["id"] == last_sid for s_id in sim._allSessions),
          "最后点击的 session 仍在列表中")

    # === T4: 搜索 → 还原，数据不丢 ===
    print("\n--- T4: 搜索后清空搜索，全量恢复 ---")
    kw = sim._allSessions[0]["title"]
    sim.filterSessions(kw)
    await asyncio.sleep(0.05)
    check(len(sim._allSessions) == 5, "_allSessions 仍是 5 个")
    sim.filterSessions("")  # 清空搜索
    await asyncio.sleep(0.05)
    check(sim._domVisible, "清空搜索后 DOM 可见")
    check(len(sim._allSessions) == 5, "清空搜索后 _allSessions 仍是 5")

    # === T5: 搜索无结果 → 还原 ===
    print("\n--- T5: 搜索无结果后清空搜索，全量恢复 ---")
    sim.filterSessions("NONEXISTENT_QUERY")
    await asyncio.sleep(0.05)
    check(len(sim._allSessions) == 5, "无结果搜索后 _allSessions 仍是 5")
    sim.filterSessions("")
    await asyncio.sleep(0.05)
    check(sim._domVisible, "清空搜索后 DOM 恢复可见")
    check(len(sim._allSessions) == 5, "全量恢复")

    # === T6: 删除当前会话 → 自动选最新 ===
    print("\n--- T6: 删除当前会话后列表减少 ---")
    before = len(sim._allSessions)
    del_sid = sim.currentSid
    sim.deleteSession(del_sid)
    await asyncio.sleep(0.1)
    check(len(sim._allSessions) == before - 1, f"删除后 {before} -> {len(sim._allSessions)}")
    check(del_sid not in [s["id"] for s in sim._allSessions], "已删除的 session 不在列表中")

    # === T7: 并发 calls — AbortController 取消旧请求 ===
    print("\n--- T7: 并发 loadSessions — 第一个被取消 ---")
    sim2 = SessionListSimulator()
    _sessions.clear()
    create_sessions(3)
    await sim2.loadSessions()
    check(len(sim2._allSessions) == 3, "初始 3 个会话")

    # 慢 call 被取消
    sim2.updateSessionList()  # 慢 call
    await asyncio.sleep(0.01)
    create_sessions(1)  # 服务器新增 1 个
    await sim2.loadSessions()  # 快 call，取消慢的
    await asyncio.sleep(0.1)
    check(len(sim2._allSessions) == 4, f"快 call 加载了最新的 {len(sim2._allSessions)} 个会话")

    # === T8: 删除全部后服务器返回空列表应正确展示 ===
    print("\n--- T8: 服务器返回空 sessions 正确展示空状态 ---")
    sim3 = SessionListSimulator()
    _sessions.clear()
    create_sessions(3)
    await sim3.loadSessions()
    check(len(sim3._allSessions) == 3, "初始 3 个会话")
    check(sim3._domVisible, "DOM 可见")
    
    # 模拟服务器清空（如全部删除） — 需要2次调用突破防护
    _sessions.clear()
    await sim3.loadSessions()  # 第1次空 → 被忽略
    check(len(sim3._allSessions) == 3, "第1次空响应被忽略")
    await sim3.loadSessions()  # 第2次空 → 被接受
    check(len(sim3._allSessions) == 0, "第2次空响应后 _allSessions 为空")
    check(not sim3._domVisible, "DOM 显示空状态")
    
    # 重新创建
    create_sessions(2)
    await sim3.loadSessions()
    check(len(sim3._allSessions) == 2, "重新创建后 2 个会话")

    # === T9: is_running 状态变化 → fingerprint 变化 → DOM 重建 ===
    print("\n--- T9: is_running 状态变化触发 DOM 重建 ---")
    sim4 = SessionListSimulator()
    _sessions.clear()
    create_sessions(3)
    await sim4.loadSessions()
    before_fp = sim4._lastSessionFingerprint
    render_count = len(sim4._rendered)
    
    s_key = list(_sessions.keys())[0]
    _sessions[s_key]["is_running"] = True
    await sim4.loadSessions()
    check(sim4._lastSessionFingerprint != before_fp, "is_running 变化导致 fingerprint 不同")
    check(len(sim4._rendered) > render_count, "触发了新的 DOM 重建")

    # === T10: 删除全部 → 空列表 → 新建会话 ===
    print("\n--- T10: 删除所有会话后为空，新建恢复 ---")
    sim5 = SessionListSimulator()
    _sessions.clear()
    create_sessions(2)
    await sim5.loadSessions()
    check(len(sim5._allSessions) == 2, "初始 2 个会话")
    sids = [s["id"] for s in sim5._allSessions]
    for sid in sids:
        # 本地先移除
        sim5._allSessions = [s for s in sim5._allSessions if s["id"] != sid]
        sim5.deleteSession(sid)
        await asyncio.sleep(0.06)
    check(len(sim5._allSessions) == 0, "删除全部后为空")
    create_sessions(1)
    await sim5.loadSessions()
    check(len(sim5._allSessions) == 1, "新建后 1 个会话")

    # === T11: 搜索结果中删除 → 全量恢复 ===
    print("\n--- T11: 搜索 → 删除 → 全量恢复 ---")
    sim6 = SessionListSimulator()
    _sessions.clear()
    create_sessions(5)
    await sim6.loadSessions()
    before_all = len(sim6._allSessions)
    # 用第3个 session 标题的后4位作为搜索词（保证命中）
    search_kw = sim6._allSessions[2]["title"][-4:]
    sim6.filterSessions(search_kw)
    await asyncio.sleep(0.05)
    check(len(sim6._allSessions) == before_all, f"搜索中 _allSessions 仍是 {before_all}")
    target = [s for s in sim6._allSessions if search_kw in s["title"]]
    check(len(target) >= 1, f"搜索 '{search_kw}' 找到 {len(target)} 个匹配")
    if target:
        sim6.deleteSession(target[0]["id"])
    await asyncio.sleep(0.15)
    check(len(sim6._allSessions) == before_all - 1, f"删除后 {before_all - 1} 个（实际 {len(sim6._allSessions)}）")
    sim6.filterSessions("")
    await asyncio.sleep(0.1)
    check(len(sim6._allSessions) == before_all - 1, f"全量恢复 {before_all - 1} 个（实际 {len(sim6._allSessions)}）")

    # === T12: fingerprint 不匹配时的边界 ===
    print("\n--- T12: fingerprint 不匹配但 session 数量相同 → 重建 DOM")
    sim7 = SessionListSimulator()
    _sessions.clear()
    create_sessions(2)
    await sim7.loadSessions()
    fp1 = sim7._lastSessionFingerprint
    render_before = len(sim7._rendered)
    
    s_key = list(_sessions.keys())[0]
    _sessions[s_key]["msg_count"] += 1
    await sim7.loadSessions()
    fp2 = sim7._lastSessionFingerprint
    check(fp1 != fp2, "msg_count 变化 → fingerprint 不同")
    check(len(sim7._rendered) > render_before, "触发了 DOM 重建")

    # === 总结 ===
    print(f"\n{'='*50}")
    total = PASS + FAIL
    print(f"总计: {PASS} PASS, {FAIL} FAIL")
    print(f"通过率: {PASS/total*100:.1f}%" if total > 0 else "0%")
    return FAIL == 0


if __name__ == "__main__":
    ok = asyncio.run(test_cases())
    sys.exit(0 if ok else 1)
