# -*- coding: utf-8 -*-
"""LoopX 融合全面测试：API 全量 + 多会话隔离 + 唤醒链路"""
import json, io, sys, time, sqlite3, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, 'memomics')
from loopx_bridge import LoopXBridge

R = []
def log(x): R.append(x); print(x, flush=True)

# ── T1: LoopX API 全量（真实会话）──
log('▶ T1 LoopX API 全量')
b = LoopXBridge('memomics-1135ed52', r'E:\MemOmics-Agent\results\memomics-1135ed52', user_online=True)
st = b.collect(limit=80)
log(f'  collect: ok={st.get("ok")} goal_count={st.get("goal_count")} run_count={st.get("run_count")}')
sr = b.should_run()
log(f'  should_run: state={sr.get("state")} decision={sr.get("decision")} gate_waived={sr.get("gate_waived")}')
iv = b.next_poll_interval(default_seconds=300)
log(f'  next_poll_interval: {iv}s')
hb = b.heartbeat_prompt(mode='compact')
log(f'  heartbeat_prompt: {repr(hb[:100])}')
hn = b.handoff_note(max_lines=8)
log(f'  handoff_note: {len(hn)} chars')
ev = b.append_event('test_wakeup', {'ts': time.time()})
log(f'  append_event: {ev}')

# ── T2: 多会话 .loopx 隔离 ──
log('▶ T2 多会话 .loopx 隔离')
b2 = LoopXBridge('memomics-f0962cee', r'E:\MemOmics-Agent\results\memomics-f0962cee', user_online=False)
r1 = b.registry_path.read_text(encoding='utf-8') if b.registry_path.exists() else ''
r2 = b2.registry_path.read_text(encoding='utf-8') if b2.registry_path.exists() else ''
log(f'  会话A registry 含 A 的 goal: {"memomics-1135ed52" in r1}')
log(f'  会话A registry 含 B 的 goal: {"memomics-f0962cee" in r1}（应 False）')
log(f'  会话B registry 含 B 的 goal: {"memomics-f0962cee" in r2}')
# user_online=False 时 operator_gate 不应 waive
sr2 = b2.should_run()
log(f'  会话B(user_online=False) should_run: state={sr2.get("state")} should={sr2.get("should_run")}')

# ── T3: quota 状态模拟（构造 goal 带高花销 → 应停止）──
log('▶ T3 quota 停止唤醒（高花销场景）')
import shutil
try:
    sim_dir = r'E:\MemOmics-Agent\results\_loopx_sim_test'
    shutil.rmtree(sim_dir, ignore_errors=True)
    import os
    os.makedirs(os.path.join(sim_dir, '.loopx'), exist_ok=True)
    from pathlib import Path
    reg = {"schema_version": "loopx_registry_v0", "goals": [{
        "id": "sim-goal", "repo": sim_dir, "status": "active",
        "quota": {"allowed_slots": 5, "spent_slots": 5, "mode": "slots"},
    }]}
    Path(sim_dir, '.loopx', 'registry.json').write_text(json.dumps(reg, ensure_ascii=False), encoding='utf-8')
    sb = LoopXBridge('sim-goal', sim_dir, user_online=True)
    dec = sb.should_run()
    log(f'  高花销(5/5) should_run: {dec.get("should_run")} state={dec.get("state")} reason={str(dec.get("reason"))[:60]}')
    shutil.rmtree(sim_dir, ignore_errors=True)
except Exception as e:
    log(f'  T3 异常: {e}')

# ── T4: 服务端唤醒链路（等播种自检 → 唤醒消息含 LoopX 状态）──
log('▶ T4 唤醒链路（等待播种自检，5 分钟）')
def api(path):
    return json.loads(urllib.request.urlopen('http://127.0.0.1:8899' + path, timeout=15).read())
time.sleep(300)
msgs = api('/api/sessions/memomics-1135ed52/messages')
msgs = msgs if isinstance(msgs, list) else msgs.get('messages', [])
last = msgs[-1] if msgs else {}
log(f'  最后消息: role={last.get("role")} | {str(last.get("content",""))[:150].replace(chr(10)," ")}')
log(f'  含 📊 LoopX 状态: {"📊" in str(last.get("content","")) or "LoopX" in str(last.get("content",""))}')

print('\n===== 汇总 =====', flush=True)
for r in R:
    print(r, flush=True)
