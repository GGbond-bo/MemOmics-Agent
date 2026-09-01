# 重启持久性最终验证：守护重启后会话/消息是否完整
import json, sqlite3, os
import httpx

BASE = "http://localhost:8899"
HH = os.path.expanduser("~/memomics-test/MemOmics/hermes_home")

with httpx.Client(timeout=10) as c:
    h = c.get(BASE + "/api/health")
    print("health:", h.status_code, (h.json().get("sessions") if h.status_code == 200 else ""))
    s = c.get(BASE + "/api/sessions")
    sess = s.json().get("sessions", [])
    print("重启后会话总数:", len(sess))
    # 找记忆强化测试的两个会话（A: 记住ATAC, B: 复述成功）与 LLM 会话
    import re
    interesting = [x for x in sess if any(k in x["id"] for k in
                   ("a2bd91e0", "e0b5c675", "cf659495", "cf857de9", "01552d4b"))]
    for x in interesting:
        sid = x["id"]
        try:
            m = c.get(f"{BASE}/api/sessions/{sid}/messages?limit=100")
            msgs = m.json().get("messages", [])
            roles = [mm["role"] for mm in msgs]
            print(f"  {sid[:24]}: roles={roles} msgs={len(msgs)}")
        except Exception as e:
            print(f"  {sid[:24]}: 读消息失败 {str(e)[:60]}")

# state.db 里记忆会话的 MEMORY 落盘（pinned 记忆行）
conn = sqlite3.connect(os.path.join(HH, "state.db"))
cnt = conn.execute("SELECT COUNT(*) FROM messages WHERE content LIKE '%数字 7%' OR content LIKE '%数字 42%'").fetchone()[0]
print("并发记忆行落库:", cnt, "条")
conn.close()