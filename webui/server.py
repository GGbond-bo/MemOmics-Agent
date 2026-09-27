"""MemOmics WebUI Server v2 — 完整版 FastAPI + WebSocket 后端。

功能:
  - 多会话管理 (新建/历史/切换)
  - 模型切换 (API key + base URL + model)
  - 配色切换 (浅白/深色/蓝色)
  - 文件浏览 + 下载
  - 知识库浏览 + 查看
  - Skill 浏览 + 查看
  - 分析结果目录 (每个会话独立)
  - 待办列表 (实时更新)
  - 后台长任务 (不阻塞聊天)
  - 思考内容 (折叠展示)
  - 辩论/审查/工具调用实时展示
"""
import os
import sys
import json
import asyncio
import traceback
import uuid
import re
import time
import hashlib
import shutil
from pathlib import Path
from datetime import datetime

# === Hermes UTF-8 bootstrap (Windows 中文支持) ===
# 必须在所有其他 import 之前，确保 Windows 上 stdio 用 UTF-8
try:
    import hermes_bootstrap  # noqa: F401
except ModuleNotFoundError:
    pass

# === MemOmics-Agent 独立运行 ===
MEMOMICS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERMES_HOME_DIR = os.path.join(MEMOMICS_DIR, "hermes_home")
os.environ["HERMES_HOME"] = HERMES_HOME_DIR
# 2026-08-14: verify-on-stop 排除运行时产物目录（results/ 下的分析脚本不触发 pytest 验证回路）
os.environ.setdefault("HERMES_VERIFY_ON_STOP_EXCLUDE", "results/;.backups/;backups/;logs/")

# === 启动时路径扫描：写入 .install_path 供 Agent 读取，避免硬编码路径 ===
_install_path_file = os.path.join(HERMES_HOME_DIR, ".install_path")
try:
    with open(_install_path_file, "w", encoding="utf-8") as _f:
        _f.write(MEMOMICS_DIR.replace("\\", "/") + "\n")
except Exception:
    pass  # 写入失败不影响启动

HERMES_DIR = os.path.join(MEMOMICS_DIR, "hermes-agent")
if HERMES_DIR not in sys.path:
    sys.path.insert(0, HERMES_DIR)
if MEMOMICS_DIR not in sys.path:
    sys.path.insert(0, MEMOMICS_DIR)

# 重新尝试 hermes_bootstrap（此时 sys.path 已含 hermes-agent）
try:
    import hermes_bootstrap  # noqa: F401
except ModuleNotFoundError:
    pass

# === computer_use：cua-driver 定位引导（2026-09-25）===
# 必须在 Hermes 的 tools.computer_use 被 import 之前跑：cua_backend 在 import 时读一次
# HERMES_CUA_DRIVER_CMD，之后只用 shutil.which() 判断可用性。官方安装器把二进制放进
# 用户目录并追加到 User PATH，而 PATH 是进程启动时的快照 —— 不重开终端就找不到，
# computer_use 会整个从模型工具表里消失（现象＝"MemOmics 不能操控电脑"）。
try:
    from webui import cua_bootstrap
except ImportError:
    import cua_bootstrap
try:
    cua_bootstrap.ensure_cua_driver_env(log=print)
except Exception as _cua_err:  # 定位失败绝不影响服务启动
    print("[computer_use] cua-driver 定位异常: %r" % (_cua_err,))

# === MiMo-Code 上下文架构迁移（2026-08-21）：P1-P5（预算/writer/四层记忆/分段重建/增量压缩）===
try:
    from webui import context_arch
except ImportError:
    import context_arch

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="MemOmics WebUI v2")

# === P2-1 入口侧中间件链（2026-09-23）：request_id / 路由归类 / 会话守卫 / 限流 / 审计 ===
# 设计前提：只观察不拦截，默认行为与接链之前完全一致（A/B 对拍见
# webui/tests/test_p2_1_middleware.py）；要拦必须显式设环境变量：
#     MEMOMICS_MW=0                 整条链不生效（连请求头都不加）
#     MEMOMICS_MW_SESSION_ENFORCE=1 会话守卫真的返回 404
#     MEMOMICS_MW_RATE_LIMIT=120    每 60 秒每 IP+路径前缀的请求上限
#     MEMOMICS_MW_ERROR_ENVELOPE=1  未捕获异常返回带 request_id 的 JSON 500
# 中间件出任何问题都不许影响启动，所以这里包一层 try/except。
_entry_mw = None
_MW_INSTALLED = False
try:
    try:
        from webui import entry_middleware as _entry_mw
    except ImportError:
        import entry_middleware as _entry_mw
    _MW_INSTALLED = bool(_entry_mw.install(app))
except Exception as _mw_err:  # pragma: no cover - 只在环境异常时走到
    _entry_mw = None
    _MW_INSTALLED = False
    print("[WARN] 入口中间件未挂载: %s" % _mw_err)


@app.get("/api/middleware/audit")
async def middleware_audit(limit: int = 50, routes: int = 0):
    """入口链的只读状态：最近 N 条请求记录 + 计数器（本机调试用）。
    routes=1 时附带「真实路由 vs 冻结清单」的漂移报告，用于门禁自查。"""
    if _entry_mw is None:
        return JSONResponse({"enabled": False, "installed": False, "items": [], "stats": {}})
    try:
        payload = {
            "enabled": _entry_mw.enabled(),
            "installed": _MW_INSTALLED,
            "stats": _entry_mw.stats(),
            "threads": (_thread_state.stats() if _thread_state is not None else {}),
            "items": _entry_mw.recent(limit),
        }
        if routes:
            ra = _entry_mw.route_audit(app)
            payload["routes"] = {
                "total": len(ra["actual"]),
                "added": ra["added"],
                "removed": ra["removed"],
                "reclassified": ra["reclassified"],
                "unclassified": ra["unclassified"],
            }
        return JSONResponse(payload)
    except Exception as _e:
        return JSONResponse({"error": str(_e)}, status_code=500)


@app.get("/api/sandbox/audit")
async def sandbox_audit(limit: int = 50, codes: int = 0):
    """P2-3：能力沙箱的只读状态（默认观察模式——判定照算、账照记，但不拦人）。
    codes=1 时附带按拒绝码聚合的计数，便于看清"如果要强制，会拦掉什么"。"""
    try:
        from webui import sandbox as _sandbox
        body = _sandbox.audit(limit=limit, codes=bool(codes))
        if _net_guard is not None:      # 出网侧视角：多少钉住 IP、多少走代理（代理钉不住 IP）
            body["netguard"] = _net_guard.stats()
        return JSONResponse(body)
    except Exception as _e:
        return JSONResponse({"error": str(_e)}, status_code=500)

import logging
# Enable Hermes weixin debug logging
logging.getLogger("gateway.platforms.weixin").setLevel(logging.DEBUG)
logging.getLogger("gateway.platforms.weixin").addHandler(logging.StreamHandler())
logger = logging.getLogger("memomics")

# === 启动预热：预构建 skills snapshot（避免首次分析请求冷扫描 355 个 SKILL.md） ===
_SKILLS_WARMED = False

@app.on_event("startup")
async def _warm_skills_snapshot():
    """启动时调用 build_skills_system_prompt() 一次，将 355 个 SKILL.md 的
    元数据快照写入 hermes_home/.skills_prompt_snapshot.json。
    此后每次新会话首次请求都从快照读取（~10ms），而非冷扫描（~1-3s）。
    同时预导入 AIAgent，消除首次 _create_agent() 的 ~640ms 模块加载。
    自动注册新 skill：补全缺失的 skill.json + SKILLS_INDEX 条目。"""
    # === 记忆治理初始化（2026-08-14）：启动时生成索引 + 每日后台维护 ===
    try:
        from memomics.memory_governance import governor
        governor.init_index(verbose=False)
        logger.info("[MemOmics] 记忆治理索引初始化完成")

        async def _memory_governor_loop():
            while True:
                try:
                    await asyncio.sleep(24 * 3600)
                    governor.init_index(verbose=False)
                except Exception as e:
                    logger.warning(f"[MemoryGovernor] 日循环异常: {e}")

        asyncio.ensure_future(_memory_governor_loop())
    except Exception as e:
        logger.warning(f"[MemOmics] 记忆治理初始化失败: {e}")
    # === Hermes 插件发现（image_gen 等 backend 插件） ===
    # 插件发现默认只在 CLI/gateway 启动时执行（gateway/run.py:7550）；
    # MemOmics 进程内集成必须手动触发，否则 image_gen_registry 为空，
    # image_generate 工具没有可用后端，agent 感知不到图像生成能力。
    try:
        from hermes_cli.plugins import PluginManager
        PluginManager().discover_and_load()
        from agent import image_gen_registry as _igr
        _n = len(_igr.list_providers())
        logger.info(f"[MemOmics] Hermes 插件发现完成，image_gen 后端 {_n} 个已注册")
    except Exception as e:
        logger.warning(f"[MemOmics] Hermes 插件发现失败: {e}（图像生成功能将不可用）")
    # 已保存过图像生成配置的用户：启动时把 provider 同步进 config.yaml，
    # 否则 image_generate 工具 check_fn 判定不可用（修复 2026-08-12 之前保存的配置没有这一步）
    _sync_imagegen_provider_to_hermes()
    try:
        from webui import auto_register
        auto_register.init(
            os.path.join(HERMES_HOME_DIR, "skills", "bioinformatics"),
            os.path.join(HERMES_HOME_DIR, "SKILLS_INDEX.md"),
            os.path.join(HERMES_HOME_DIR, "SOUL.md"),
        )
        result = auto_register.scan_and_register_all()
        if result.get("json_generated", 0) > 0 or result.get("index_added", 0) > 0:
            print(f"[auto-register] Startup scan: {result}", flush=True)
    except Exception as e:
        print(f"[auto-register] Startup scan failed: {e}", flush=True)
    global _SKILLS_WARMED
    try:
        from run_agent import AIAgent  # 预导入，消除首次请求的模块加载延迟
        from agent.prompt_builder import build_skills_system_prompt
        result = build_skills_system_prompt()
        _SKILLS_WARMED = True
        logger.info(
            f"[MemOmics] Skills snapshot warmed: {len(result)} chars prompt, "
            f"snapshot at {os.path.join(HERMES_HOME_DIR, '.skills_prompt_snapshot.json')}"
        )
    except Exception as e:
        logger.warning(f"[MemOmics] Skills snapshot warm failed (will cold-scan on first request): {e}")
    
    # === 微信自动重连 ===
    try:
        if _weixin_state.get("connected") and _weixin_state.get("token"):
            import asyncio as _asyncio
            _asyncio.get_event_loop().call_soon_threadsafe(
                lambda: _asyncio.ensure_future(_auto_reconnect_weixin())
            )
            logger.info("[MemOmics] 检测到已保存的微信凭据，将在后台自动重连...")
    except Exception as e:
        logger.warning(f"[MemOmics] 微信自动重连调度失败: {e}")

# === Hermes Cron Ticker — 在 MemOmics 进程中启动原生 cron 调度器 ===
import threading as _threading
_cron_stop_event = _threading.Event()

@app.on_event("startup")
async def _seed_self_check_startup():
    """故障自愈播种（修复 2026-08-07）：
    自检原本只在 agent 回合结束时调度 —— 服务重启/agent 断连后没有新回合，
    唤醒链永不恢复（用户必须手动发消息才重新触发）。
    启动时为"有活跃工作"的会话（task_plan.md 或 batch 批处理活跃）重建 agent
    并播种自检调度，唤醒链自动恢复，无需任何用户交互。

    修复 2026-08-08：原实现直接在 startup 钩子里同步 _create_agent()。
    _create_agent() 内含 models.dev 网络探测 + env_probe 子进程（最坏 ~35s），
    且是同步阻塞函数——即使放进 async 钩子也会卡死整个事件循环，
    uvicorn 停在 "Waiting for application startup"，浏览器打开时 server
    未就绪 → 用户看到"打不开"。现改为后台线程播种，startup 立即返回。
    """
    try:
        _loop = asyncio.get_event_loop()
    except Exception:
        return

    def _seed_worker():
        try:
            time.sleep(2)  # 等会话状态稳定
            _seeded = 0
            for sid, s in list(_sessions.items()):
                if s.get("running_agent") or s.get("running_task"):
                    continue
                _rd = s.get("results_dir", "") or ""
                _active = _task_plan_active(_rd) or _session_has_active_work(s)
                if not _active:
                    continue
                _agent = s.get("agent")
                if _agent is None:
                    try:
                        _agent = _create_agent(s.get("model_config") or _current_model, session_id=sid, session=s)
                        s["agent"] = _agent
                    except Exception as _e:
                        print(f"[MemOmics] 播种 agent 失败 {sid[:12]}: {_e}", flush=True)
                        continue
                # _schedule_self_check 内部用 asyncio.ensure_future 调度，
                # 只能在主事件循环线程安全地调用
                try:
                    _loop.call_soon_threadsafe(_schedule_self_check, s, _agent, _loop)
                    _seeded += 1
                    print(f"[MemOmics] 自愈播种自检: {sid[:12]}", flush=True)
                except Exception as _e:
                    print(f"[MemOmics] 播种调度失败 {sid[:12]}: {_e}", flush=True)
            if _seeded:
                print(f"[MemOmics] 自愈播种完成: {_seeded} 个活跃会话", flush=True)
        except Exception as e:
            print(f"[MemOmics] 自愈播种失败: {e}", flush=True)

    _threading.Thread(target=_seed_worker, daemon=True, name="self-check-seed").start()


@app.on_event("startup")
async def _start_process_completion_poller():
    """notify_on_complete push 链（2026-08-16 修复）。

    terminal(background=True, notify_on_complete=True) 的进程退出时，Hermes 把
    完成事件写进 process_registry.completion_queue，但 MemOmics WebUI 从不消费
    它 —— 之前只能靠自检轮询（60s~5min 延迟）才发现进程结束。这里起守护线程消费
    队列，按 session_key（= session id，见 terminal_tool 的 session_key 接线）
    路由回对应会话并立即唤醒 agent 处理结果。
    """
    try:
        _loop = asyncio.get_event_loop()
    except Exception:
        return

    def _poller():
        from tools.process_registry import process_registry, format_process_notification
        while True:
            try:
                evt = process_registry.completion_queue.get(timeout=0.5)
            except Exception:
                continue
            try:
                if evt.get("type") == "completion" and process_registry.is_completion_consumed(evt.get("session_id", "")):
                    continue
                _sid = str(evt.get("session_key") or "")
                if not _sid or _sid not in _sessions:
                    continue  # 无主/会话已关 → 丢弃
                _s = _sessions[_sid]
                text = format_process_notification(evt)
                if not text:
                    continue
                if _s.get("running_agent") or _s.get("running_task"):
                    # 会话忙 → 重排回队列，稍后再投递
                    process_registry.completion_queue.put(evt)
                    time.sleep(0.25)
                    continue
                _s.setdefault("messages", []).append({
                    "role": "system",
                    "content": "⏰ 后台进程完成通知，请立即查看结果并推进主线：\n\n" + text,
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "source": "process_completion",
                })
                _loop.call_soon_threadsafe(
                    lambda _s=_s, _t=text: asyncio.ensure_future(_trigger_agent_turn(_s, _t))
                )
            except Exception as e:
                logger.warning("[process-poller] dispatch failed: %s", e)

    _threading.Thread(target=_poller, daemon=True, name="process-completion-poller").start()
    logger.info("[MemOmics] process completion poller started")


@app.on_event("startup")
async def _apply_fix_bundle_startup():
    """旧安装自愈（2026-08-16）：启动时应用文件级修复（config 限额等）。

    Linux/macOS/Cluster 的 launcher 直接跑 server.py（不走 start.bat），
    这里兜底执行幂等迁移；代码级修复仍需换新包文件，old 时打警告日志。
    """
    try:
        from memomics.fix_bundle import apply_fix_bundle, BUNDLE
        _rep = apply_fix_bundle(HERMES_HOME_DIR)
        if not _rep.get("up_to_date"):
            logger.info("[FixBundle] 已应用文件级迁移: %s", _rep)
            print(f"[FixBundle] 已应用文件级迁移: {_rep}", flush=True)
        print(f"[FixBundle] 当前修复级别: {BUNDLE}", flush=True)
    except Exception as e:
        logger.warning(f"[FixBundle] 启动迁移失败(不阻塞): {e}")


def _stall_hard_seconds(s: dict) -> int:
    """stall watchdog 硬中断阈值（2026-08-31：长任务不被 5 分钟误杀）。

    - 回合开始即静默（connect 后零输出 = 网关挂起典型）→ 300s 快速恢复；
    - 回合中段静默（此前有过模型输出/推理/工具活动 = 长思考/长生成）→ 600s
      （env MEMOMICS_STALL_HARD_SECONDS 可调），靠"有前科"区分挂起与慢。
    """
    try:
        hard = int(os.environ.get("MEMOMICS_STALL_HARD_SECONDS", "600"))
    except Exception:
        hard = 600
    _start = s.get("_turn_start_ts") or 0
    _act = s.get("_turn_activity_ts") or 0
    if not (_act and (_act - _start) > 5):
        return 300
    return max(300, hard)


@app.on_event("startup")
async def _start_agent_stall_watchdog():
    """LLM 卡死自动恢复：5 分钟无事件输出 → 中断 agent 并报错。

    opencode.ai 等聚合网关会间歇性挂起新连接的 TLS 握手（Windows 上
    ssl do_handshake 卡死时 connect 超时失效），agent 永久卡在"思考"，
    用户只能干等或手动停止。watchdog 每 20s 扫描，自动中断并提示重试。
    """
    async def _watch():
        while True:
            await asyncio.sleep(20)
            now = time.time()
            for sid, s in list(_sessions.items()):
                agent_ref = s.get("running_agent")
                if not agent_ref:
                    continue
                # 2026-08-16 任务进程采样：每 tick 采样本会话内核/后台进程（窗口 300s），
                # 供"任务在算 vs 真卡死"判定
                _sample_task_procs(s)
                _live = str(s.get("_live_tool") or "").strip()
                _act = s.get("_turn_activity_ts")
                last_ts = _act if _act else (s.get("_last_event_ts") or now)
                if now - last_ts <= 300:
                    continue  # 5 分钟内有过事件输出，无需干预
                # ── 工具在飞：用进程级证据（CPU/IO）区分"在算"与"卡死" ──
                if _live:
                    _verdict, _info = _task_liveness(s)
                    if _verdict == "working":
                        # 任务在推进（CPU/IO 在动）→ 不中断
                        if now - s.get("_stall_notice_last", 0) > 300:
                            s["_stall_notice_last"] = now
                            _session_emit(s, {"type": "notice", "content": f"⏳ {_info}（模型无输出但任务在推进，不中断）", "session_id": sid})
                        _since = s.get("_live_tool_ts") or 0
                        if _since and (now - _since) > 1800 and not s.get("_live_tool_warned"):
                            s["_live_tool_warned"] = True
                            _session_emit(s, {"type": "notice", "content": f"⏳ 工具 {_live} 已运行超过 30 分钟（{_info}），仍在推进，请耐心等待。", "session_id": sid})
                        continue
                    if _verdict == "frozen":
                        # 进程存在但 CPU/IO 完全冻结（死锁/挂起）→ 唤醒 AI 诊断解决
                        s["_stall_diag"] = (
                            f"⚠️ [任务卡死诊断] {_info}。请立即调查：\n"
                            "1) read_file 读任务日志尾部（找 error/traceback/停在哪一步）\n"
                            "2) terminal 查该进程状态（Windows: tasklist /FI \"PID eq <pid>\"；Linux: ps -p <pid> -o pid,pcpu,rss,stat）\n"
                            "3) 判断原因（死锁/内存耗尽/数据问题）后修复并重跑\n"
                            "4) 确认卡死可强杀该 PID（Windows: taskkill /PID <pid> /F；Linux: kill -9 <pid>）——"
                            "卡住的旧回合会自动解绑，kernel 下次调用自动重建\n"
                            "不要直接放弃，找出原因继续解决。"
                        )
                        s["_urgent_wakeup"] = True
                        s["_force_tool_check"] = True
                        try:
                            if hasattr(agent_ref, "interrupt"):
                                agent_ref.interrupt()
                        except Exception:
                            pass
                        _session_emit(s, {"type": "error", "content": f"⚠️ {_info}。已唤醒 Agent 诊断处理（不直接放弃）。", "session_id": sid})
                        _clear_session_running(sid)
                        # 2026-08-16 补: 被卡线程可能永远不返回（卡死在 kernel 工具内），
                        # 其 finally 不会执行 → _urgent_wakeup 永不消费 → AI 永远不会被叫醒。
                        # 直接武装 3 秒后的诊断回合；dedupe 防与旧线程 finally 双发。
                        _diag_txt = str(s.get("_stall_diag", ""))

                        async def _frozen_wake(_s=s, _diag=_diag_txt):
                            await asyncio.sleep(3)
                            if _s.get("running_agent") or _s.get("running_task"):
                                return  # 旧线程已自然结束并重排，让它走
                            if _s.get("_stall_wake_active"):
                                return
                            _s["_stall_wake_active"] = True
                            try:
                                await _trigger_agent_turn(_s, _diag)
                            finally:
                                _s.pop("_stall_wake_active", None)
                                _s.pop("_stall_diag", None)

                        asyncio.ensure_future(_frozen_wake())
                        continue
                    # insufficient / no_task：无进程证据 → 工具自身超时兜底 + 长工具提醒
                    _since = s.get("_live_tool_ts") or 0
                    if _since and (now - _since) > 1800 and not s.get("_live_tool_warned"):
                        s["_live_tool_warned"] = True
                        _session_emit(s, {"type": "notice", "content": f"⏳ 工具 {_live} 已运行超过 30 分钟且无进程证据（{_info}），如疑似卡死请手动停止。", "session_id": sid})
                    continue
                # ── 无工具在飞 + 300s 无事件 ──
                # 2026-08-31 升级（用户反馈：长任务不该被 5 分钟规则中断）：
                # ① 后台进程（terminal background 注册表）活跃 → 永不中断，提示进行中
                # ② 回合"中段静默"（此前有过输出/推理/工具）→ 300s 提醒 → 600s
                #    （MEMOMICS_STALL_HARD_SECONDS 可调）才中断——长思考/长生成不误杀
                # ③ 回合开始即静默（无任何前科，网关挂起典型）→ 保持 300s 快速中断
                # ④ 中断前落日志（此前零日志，复现全靠猜）
                try:
                    from tools.process_registry import process_registry
                    _bg_active = [
                        p for p in process_registry.list_sessions(session_key=sid)
                        if p.get("status") == "running"
                    ]
                except Exception:
                    _bg_active = []
                if _bg_active:
                    if now - s.get("_stall_notice_last", 0) > 300:
                        s["_stall_notice_last"] = now
                        _session_emit(s, {"type": "notice",
                                          "content": f"⏳ 本会话后台任务仍在运行（{len(_bg_active)} 个），回合静默等待中，不会中断。",
                                          "session_id": sid})
                    continue
                _start = s.get("_turn_start_ts") or 0
                _act = s.get("_turn_activity_ts") or 0
                _has_event = bool(_act and (_act - _start) > 5)
                _hard = _stall_hard_seconds(s)
                _silent = int(now - last_ts)
                if _silent < _hard:
                    if now - (s.get("_stall_noevent_ts") or 0) > 240:
                        s["_stall_noevent_ts"] = now
                        _left = int(_hard - _silent)
                        _session_emit(s, {"type": "notice",
                                          "content": (f"⏳ 模型已静默 {_silent}s（无输出/推理/工具活动）。"
                                                      f"长任务/长思考会继续等待，{_left // 60} 分钟后仍无任何活动才中断。"),
                                          "session_id": sid})
                    continue
                logger.warning(
                    "[MemOmics] stall watchdog interrupt: session=%s silent=%ds has_event=%s live=%r",
                    sid[:12], _silent, _has_event, _live,
                )
                try:
                    if hasattr(agent_ref, "interrupt"):
                        agent_ref.interrupt()
                except Exception:
                    pass
                try:
                    _session_emit(s, {"type": "error",
                                      "content": (f"⏱ Agent 已 {_silent}s 无任何模型输出（含推理/工具活动），自动中断并清理本回合。"
                                                  f"可能原因：① 模型网关/API 连接挂起（最常见）；② 模型长思考超过 {_hard}s。"
                                                  f"后台任务/长任务在跑不会被中断——若确认无后台任务，请重试或切换模型。"),
                                      "session_id": sid})
                except Exception:
                    pass
                _clear_session_running(sid)
    try:
        asyncio.create_task(_watch())
        logger.info("[MemOmics] Agent stall watchdog started — 5min no-event auto-interrupt")
    except Exception as e:
        logger.warning(f"[MemOmics] stall watchdog start failed: {e}")

@app.on_event("startup")
async def _start_memory_governance():
    """记忆治理自动调度（2026-08-14）：每天一次 L1→L2 下沉 / L3 归档，
    防止 MEMORY.md 在超长会话中无限膨胀（TencentDB L0-L3 分层的 MemOmics 版）。"""
    async def _loop():
        while True:
            try:
                _marker = os.path.join(HERMES_HOME_DIR, "memories", ".governance_last")
                _last = 0.0
                if os.path.isfile(_marker):
                    try:
                        _last = float(open(_marker, "r", encoding="utf-8").read().strip() or "0")
                    except Exception:
                        pass
                if time.time() - _last > 86400:
                    from memomics.memory_governance.governor import init_index, run_governance
                    init_index(verbose=False)
                    _rep = run_governance(dry_run=False, verbose=False)
                    # 2026-08-14: KB 陈旧度周检（每周一次，写报告 + 在线会话提示）
                    _kb_marker = os.path.join(HERMES_HOME_DIR, "memories", ".kb_staleness_last")
                    _kb_last = 0.0
                    if os.path.isfile(_kb_marker):
                        try:
                            _kb_last = float(open(_kb_marker, "r", encoding="utf-8").read().strip() or "0")
                        except Exception:
                            pass
                    if time.time() - _kb_last > 7 * 86400:
                        try:
                            from memomics.bio_tools.kb_search import _find_kb_root
                            import yaml as _yaml
                            _kbr = _find_kb_root()
                            _stale_dirs = []
                            if _kbr:
                                for _p in Path(_kbr).rglob("*.yaml"):
                                    try:
                                        with open(_p, encoding="utf-8", errors="replace") as _pf:
                                            _d = _yaml.safe_load(_pf.read(200000))
                                        _lu = str((_d or {}).get("last_updated") or "")
                                        if _lu:
                                            _dt = datetime.strptime(_lu[:10], "%Y-%m-%d")
                                            if (time.time() - _dt.timestamp()) > 90 * 86400:
                                                _stale_dirs.append(str(_p.relative_to(_kbr)).replace("\\", "/"))
                                    except Exception:
                                        continue
                            with open(os.path.join(HERMES_HOME_DIR, "memories", "kb_staleness.json"), "w", encoding="utf-8") as _sf:
                                json.dump({"checked_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "stale": _stale_dirs[:50], "count": len(_stale_dirs)}, _sf, ensure_ascii=False, indent=2)
                            with open(_kb_marker, "w", encoding="utf-8") as _mf:
                                _mf.write(str(time.time()))
                            if _stale_dirs:
                                for _sid2, _ss2 in list(_sessions.items()):
                                    try:
                                        _session_emit(_ss2, {"type": "info", "content": f"📚 知识库周检: {len(_stale_dirs)} 个条目超过 90 天未更新（如 {_stale_dirs[0]}）。可在知识库面板查看覆盖矩阵。", "session_id": _ss2["id"]})
                                    except Exception:
                                        pass
                            logger.info(f"[KB-Staleness] 周检完成: {len(_stale_dirs)} 个陈旧条目")
                        except Exception as _ke:
                            logger.warning(f"[KB-Staleness] 周检失败(非阻塞): {_ke}")
                    try:
                        with open(_marker, "w", encoding="utf-8") as _f:
                            _f.write(str(time.time()))
                    except Exception:
                        pass
                    logger.info(f"[MemoryGovernor] 每日治理完成: L2下沉={len(_rep.get('moved_to_l2', []))} L3归档={len(_rep.get('moved_to_l3', []))}")
            except Exception as _e:
                logger.warning(f"[MemoryGovernor] 每日治理失败(非阻塞): {_e}")
            await asyncio.sleep(6 * 3600)
    try:
        asyncio.create_task(_loop())
        logger.info("[MemOmics] Memory governance scheduler started — daily L1→L2→L3")
    except Exception as e:
        logger.warning(f"[MemOmics] memory governance start failed: {e}")


@app.on_event("startup")
async def _start_hermes_cron_ticker():
    """在 MemOmics FastAPI 进程中启动 Hermes 原生 cron ticker。
    
    cron ticker 每 60 秒扫描一次 hermes_home/cron/jobs.json，
    执行到期的 cron job。这是长任务心跳监控的核心引擎。
    """
    # 2026-09-10: 启动时同步一次 custom_providers 到 Hermes 底座——补齐 base_url 与
    # per-provider extra_headers（opencode.ai 网关的 x-opencode-session），
    # 让已装用户无需重新保存 key 即可修复。失败不阻塞启动。
    try:
        _sync_custom_providers_to_hermes()
    except Exception as _e_sync:
        logger.warning(f"[MemOmics] 启动同步 custom_providers 失败（不阻塞）: {_e_sync}")
    try:
        from cron.scheduler_provider import InProcessCronScheduler
        # 确保 HERMES_HOME 正确：cron 数据存在 hermes_home/cron/ 下
        os.environ.setdefault("HERMES_HOME", HERMES_HOME_DIR)
        _ticker_thread = _threading.Thread(
            target=lambda: InProcessCronScheduler().start(
                _cron_stop_event,
                adapters=None,   # 不需要消息平台投递
                loop=None,       # 不需要 live adapter
                interval=60,     # 60s tick，与 Hermes 默认一致
            ),
            daemon=True,
            name="memomics-cron-ticker",
        )
        _ticker_thread.start()
        logger.info("[MemOmics] Cron ticker started — hermes_home/cron/jobs.json, interval=60s")
    except Exception as e:
        logger.warning(f"[MemOmics] Cron ticker 启动失败（长任务心跳不可用）: {e}")
    # 2026-08-23 迁移 MiMo-Code：启动后台自动检查更新（静默失败，不阻塞启动）
    try:
        _background_update_check()
        logger.info("[MemOmics] 后台自动检查更新已启动（策略: %s）", _get_update_config()["autoupdate"])
    except Exception:
        pass

@app.on_event("shutdown")
async def _stop_hermes_cron_ticker():
    """优雅停止 cron ticker。"""
    _cron_stop_event.set()
    logger.info("[MemOmics] Cron ticker stopped")

# 挂载静态文件目录 (assets/ 下的图片等)
_static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
if os.path.isdir(_static_dir):
    app.mount("/assets", StaticFiles(directory=_static_dir), name="assets")

# 挂载用户上传图片目录
_uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(_uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_uploads_dir), name="uploads")

def _is_data_destroy_command(cmd: str) -> bool:
    """检测 terminal 命令是否会删除数据。
    允许删除已知临时文件（.heartbeat_stop/PROGRESS.md/task_plan.md/alerts.json/logs）。"""
    c = cmd.lower().replace("'", "").replace('"', "")
    
    # ✅ 白名单：已知临时文件，允许自动清理
    _CLEANUP_SAFE = [".heartbeat_stop", "progress.md", "alerts.json", "task_plan.md",
                     "pipeline.log", ".err", "monitor.log", ".heartbeat_"]
    if any(safe in c for safe in _CLEANUP_SAFE) and not any(
        dangerous in c for dangerous in ["*.h5", "*.h5ad", "*.csv", "*.png", "*.svg", 
                                          "*.pdf", "*.html", "*.rds", "*.rdata", "*.mtx"]):
        return False  # 只删临时文件，不删结果文件 → 放行
    
    if "rm -rf" in c or "rm -r " in c or "rmdir" in c:
        if not any(s in c for s in ["/tmp/", "tmp/", "__pycache__"]):
            return True
    if ("del /s" in c or "del /q" in c or "rmdir /s" in c) and "node_modules" not in c:
        return True
    if ("rm -rf" in c or "rm -r " in c) and "cellbender_output" in c:
        return True
    return False


def _is_code_destroy(code: str) -> bool:
    """检测 Python 代码是否会删除文件/目录。
    允许删除已知临时文件。"""
    c = code.lower()
    
    # ✅ 白名单：已知临时文件，允许自动清理
    _CLEANUP_SAFE = [".heartbeat_stop", "progress.md", "alerts.json", "task_plan.md",
                     "pipeline.log"]
    if any(safe in c for safe in _CLEANUP_SAFE) and not any(
        dangerous in c for dangerous in [".h5", ".h5ad", ".csv", ".png", ".svg", 
                                          ".pdf", ".html", ".rds", ".rdata"]):
        return False  # 只删临时文件 → 放行
    
    destroy_funcs = ["shutil.rmtree", "os.remove", "os.unlink", "pathlib.path",
                     ".unlink(", ".rmdir(", "send2trash"]
    for f in destroy_funcs:
        if f in c:
            # 排除安全的临时目录清理
            if "tmp" not in c and "__pycache__" not in c:
                return True
    return False


def _is_launch_command(cmd_str: str) -> bool:
    """检测终端命令是否为启动长任务管线的命令。

    2026-08-16 收窄（memomics-2274ab75 教训）：去掉 "rscript"/"python -c"——
    画图/普通脚本属正常任务，不触发长任务启动验证（verify_launch）。
    """
    c = str(cmd_str).lower()
    keywords = ["cellbender", "subprocess.popen", "popen", "run_cellbender",
                "run_serial", "run_pipeline", "no_window", "create_no_window"]
    return any(k in c for k in keywords)


def _is_suicide_command(cmd: str) -> bool:
    """检测命令是否会杀死 MemOmics 自己的进程。"""
    c = cmd.lower().replace("'", "").replace('"', "")
    # taskkill /IM python* → 会杀死所有 Python 进程
    if "taskkill" in c and ("/im python" in c or "/im python3" in c):
        return True
    # killall / pkill python → Linux 下同样危险
    if ("killall" in c or "pkill" in c) and "python" in c:
        return True
    # shutdown/重启命令（Windows: /s /r /p /h；Linux: -h -r now）→ 直接关机器
    if "shutdown" in c and any(x in c for x in ("/s", "/r", "/p", "/h", "-h", "-r", " now")):
        return True
    return False


# === Hermes SessionDB (state.db) — 原生会话持久化 ===
_session_db = None
def _get_session_db():
    """惰性初始化 Hermes SessionDB"""
    global _session_db
    if _session_db is None:
        try:
            from hermes_state import SessionDB
            _session_db = SessionDB()
            # 确保 kv 表存在（微信会话映射持久化）
            if hasattr(_session_db, '_conn'):
                _session_db._conn.execute(
                    "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT)"
                )
                _session_db._conn.commit()
        except Exception as e:
            print(f"[MemOmics] SessionDB 初始化失败: {e}", flush=True)
    return _session_db


def _restore_session_model_config(sid, base_cfg):
    """从 Hermes state.db 恢复会话级模型配置（会话级切换后重启/重连恢复）。

    只认 sessions.model_config 列（会话级切换时写入的完整 JSON，含 api_key）；
    该列没有值 = 该会话从未做过会话级切换 → 跟随全局 base_cfg。
    不回退 model/billing 列：那两列是 Hermes 首次调用时自动填的，
    可能过时（全局切换后未更新），会导致重启后会话用了旧模型。
    """
    try:
        db = _get_session_db()
        if not db or not db._conn:
            return dict(base_cfg)
        row = db._conn.execute(
            "SELECT model_config FROM sessions WHERE id = ?", (sid,)
        ).fetchone()
        if row and row[0]:
            import json as _json
            parsed = _json.loads(row[0])
            if isinstance(parsed, dict) and parsed.get("model") and parsed.get("base_url"):
                # 该会话做过会话级切换 → locked=True，全局切换不再覆盖它
                return dict(parsed), True
    except Exception:
        pass
    # 从未做过会话级切换 → 跟随全局
    return dict(base_cfg), False


def _build_session_stats(session_id, agent=None):
    """构建 session token 统计：以 state.db 持久化累计为准（Hermes 每轮 API 调用后
    自动 update_token_counts 增量写入 sessions 表）。

    修复(2026-08-07)：原实现优先 agent 内存（session_*_tokens），切换模型重建 agent
    后内存归零/变小，累计 token 显示会丢；现在 DB 是唯一权威，重启/重连/切模型都不丢。
    """
    stats = {
        "prompt_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 0,
        "api_calls": 0,
        "llm_ms": 0,
        "turns": 0,
    }
    db = _get_session_db()
    if db and hasattr(db, "_conn"):
        try:
            row = db._conn.execute(
                "SELECT input_tokens, output_tokens, cache_read_tokens, "
                "cache_write_tokens, reasoning_tokens, api_call_count, llm_ms "
                "FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row:
                stats["input_tokens"] = row[0] or 0
                stats["output_tokens"] = row[1] or 0
                stats["cache_read_tokens"] = row[2] or 0
                stats["cache_write_tokens"] = row[3] or 0
                stats["reasoning_tokens"] = row[4] or 0
                stats["api_calls"] = row[5] or 0
                stats["llm_ms"] = row[6] or 0
            # 用户轮次 = messages 表中用户消息数（排除 system/assistant/工具回执）
            try:
                _tr = db._conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user' AND active = 1",
                    (session_id,),
                ).fetchone()
                if _tr:
                    stats["turns"] = _tr[0] or 0
            except Exception:
                pass
        except Exception:
            pass
    stats["prompt_tokens"] = stats["input_tokens"]
    # 派生统计（口径对齐 DSH/MiMo token meter）：
    # billed input = 未缓存输入 + 缓存读 + 缓存写（三个不相交计费桶）
    stats["billed_input_tokens"] = (stats["input_tokens"] or 0) + (stats["cache_read_tokens"] or 0) + (stats["cache_write_tokens"] or 0)
    _billed = stats["billed_input_tokens"]
    stats["cache_hit_percent"] = round(100.0 * (stats["cache_read_tokens"] or 0) / _billed) if _billed > 0 else None
    _llm_sec = (stats["llm_ms"] or 0) / 1000.0
    stats["llm_seconds"] = round(_llm_sec, 1)
    stats["tokens_per_sec"] = round((stats["output_tokens"] or 0) / _llm_sec, 1) if _llm_sec > 0 else None
    return stats


_TOKEN_USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens",
                       "cache_write_tokens", "reasoning_tokens", "llm_ms", "api_calls")


def _persist_token_usage(session, turn_kind="user"):
    """回合级 token 消耗持久化：追加写入 <results_dir>/token_usage.jsonl（永不覆盖）。

    - 源数据：state.db sessions 表累计（_build_session_stats，重启/切模型不丢）。
    - 差分：本回合消耗 = 当前累计 - 文件最后一行累计（首次记录 = 当前累计，历史并入首笔）。
    - 文件：JSON Lines 追加，每行一个回合；断连/重启/更新模型均不覆盖历史。
    """
    import json as _json
    try:
        sid = session.get("id", "")
        results_dir = session.get("results_dir", "") or ""
        if not sid or not results_dir:
            return None
        stats = _build_session_stats(sid, session.get("agent"))
        cur = {f: int(stats.get(f) or 0) for f in _TOKEN_USAGE_FIELDS}
        path = os.path.join(results_dir, "token_usage.jsonl")
        prev = None
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            prev = _json.loads(line)
            except Exception:
                prev = None
        prev = prev or {}
        prev_cum = prev.get("cumulative") or {}
        deltas = {f: cur[f] - int(prev_cum.get(f) or 0) for f in _TOKEN_USAGE_FIELDS}
        total_delta = deltas["input_tokens"] + deltas["output_tokens"]
        cumulative_total = cur["input_tokens"] + cur["output_tokens"]
        record = {
            "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "session_id": sid,
            "turn_kind": turn_kind,
            "model": (session.get("model_config") or {}).get("model", ""),
            "deltas": deltas,
            "total_delta": total_delta,
            "cumulative": cur,
            "cumulative_total": cumulative_total,
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(_json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
        return record
    except Exception:
        return None


def _last_turn_stats(results_dir):
    """读取最近一个回合的差分统计（token_usage.jsonl 最后一行 deltas）。

    回合级口径（对齐 DSH token meter 的 per-step 展示）：
    - last_output_tokens / last_llm_ms → 最近回合平均输出速率（tok/s）
    - last_cache_read / last_billed_input → 最近回合缓存命中率
    历史回合（llm_ms 未记录前）llm_ms 差分并入首笔，速率可能偏大，属已知口径。
    """
    import json as _json
    try:
        if not results_dir:
            return {}
        path = os.path.join(results_dir, "token_usage.jsonl")
        if not os.path.isfile(path):
            return {}
        last = None
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last = _json.loads(line)
        if not last:
            return {}
        d = last.get("deltas") or {}
        llm_ms = int(d.get("llm_ms") or 0)
        out = int(d.get("output_tokens") or 0)
        billed = (int(d.get("input_tokens") or 0)
                  + int(d.get("cache_read_tokens") or 0)
                  + int(d.get("cache_write_tokens") or 0))
        cached = int(d.get("cache_read_tokens") or 0)
        return {
            "ts": last.get("ts", ""),
            "output_tokens": out,
            "llm_ms": llm_ms,
            "llm_seconds": round(llm_ms / 1000.0, 1) if llm_ms else 0.0,
            "tokens_per_sec": round(out / (llm_ms / 1000.0), 1) if llm_ms > 0 else None,
            "cache_read_tokens": cached,
            "billed_input_tokens": billed,
            "cache_hit_percent": round(100.0 * cached / billed) if billed > 0 else None,
            "api_calls": int(d.get("api_calls") or 0),
        }
    except Exception:
        return {}


def _get_headroom_stats():
    """读取 headroom 工具的内存压缩统计。"""
    try:
        from memomics.bio_tools.headroom_tool import _STATS as _hs, _COMPRESS_CACHE as _hc
        return {
            "compressions": _hs.get("compressions", 0),
            "tokens_saved": _hs.get("tokens_saved_est", 0),
            "original_chars": _hs.get("original_chars", 0),
            "compressed_chars": _hs.get("compressed_chars", 0),
            "cache_entries": len(_hc),
        }
    except Exception:
        return {"compressions": 0, "tokens_saved": 0}


def _auto_create_task_plan(session, plan_path):
    """自动创建 task_plan.md 初始版本（用户没手动创建时的兜底保护）。

    同时自动检测用户消息中的路径，更新 results_dir 以对齐心跳扫描。
    """
    messages = session.get("messages", [])
    goal = "生信分析任务"
    for m in messages:
        if m.get("role") == "user":
            text = m.get("content", "")
            if isinstance(text, str) and len(text) > 3:
                goal = text[:80].replace("\n", " ")
                # 尝试提取用户指定的路径（如 F:/CellBender_v2）
                import re
                _path_match = re.search(r"([A-Za-z]:[/\\][^\s,，。]+)", text)
                if _path_match:
                    _user_dir = _path_match.group(1).rstrip("/\\")
                    if os.path.isdir(_user_dir):
                        # 记录分析目录（用于心跳扫描），但不覆盖 results_dir（结果面板需要隔离）
                        session["analysis_dir"] = _user_dir
                        logger.info(f"[MemOmics] task_plan 检测到分析目录: {_user_dir}")
                break

    # task_plan.md 写入 results_dir（此时已对齐到用户指定目录）
    plan_path = os.path.join(session["results_dir"], "task_plan.md")

    # 完成契约兼容（2026-08-16，memomics-2274ab75 案例）：CellBender 专用验算项
    # 只在真正的 CellBender 任务预置。否则默认模板的未勾选框会卡死非 CellBender
    # 任务的自动归档（_completion_contract_check 要求主线区无 "- [ ]"），
    # 造成"任务已终态但持续唤醒"死循环。
    _is_cellbender = "cellbender" in goal.lower()
    _checklist_block = (
        """每个样本跑完后自动验证：
- [ ] output_filtered.h5 存在且 > 10MB
- [ ] 无 OOM / traceback 在日志尾部
- [ ] ptrepack 成功（如适用）

Phase 全部完成后：
- [ ] 产出文件数 = 预期数
- [ ] pipeline_status.json → completed"""
        if _is_cellbender
        else """（待 LLM 根据任务填写具体验证项，完成一项勾选一项）"""
    )
    # 2026-08-16 任务类型：默认普通任务——画图/轻量分析前台执行即可，
    # 不要诱导 agent 走后台运行+心跳（那是长任务管线才需要的设施）。
    _phase1_hint = ("直接开始执行（加载 skill → 写脚本 → 后台运行 → 部署心跳）"
                    if _is_cellbender
                    else "直接开始执行（加载 skill → 写脚本 → 前台运行并检查产出）")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rd = session.get("results_dir", "")
    content = f"""# Task Plan: {goal}

## Goal
{goal}

## Current Phase
Phase 1

## Phases

### Phase 1: 执行用户任务
- [ ] {_phase1_hint}
**Status:** in_progress

## Runtime State
| Field | Value |
|-------|-------|
| current_pid | 待填充 |
| log_path | 待填充 |
| alerts_path | {rd}/alerts.json |
| started_at | {now} |

## Verification Checklist
{_checklist_block}

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
|       |         |            |

## Decisions Made
| Decision | Rationale |
|----------|-----------|
|          |           |

---
> ⚠️ 此文件由系统自动创建（{now}）。请 LLM 根据用户的实际需求更新 Phase 列表。
> 每完成一个 Phase 更新 Status 和 Current Phase。
"""
    try:
        os.makedirs(os.path.dirname(plan_path), exist_ok=True)
        with open(plan_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"[MemOmics] 自动创建 task_plan.md: {plan_path}")
    except Exception as e:
        logger.warning(f"[MemOmics] 自动创建 task_plan.md 失败: {e}")
        return None

    return (
        "[SYSTEM] ⚠️ 系统已自动创建 task_plan.md（磁盘文件）。"
        "你当前正在进行分析任务，上下文可能被压缩丢失目标。\n\n"
        "**你必须做的事**：\n"
        "1. 用 read_file 读取 task_plan.md 查看当前状态\n"
        "2. 根据用户需求完善 Phase 列表（每个 Phase 对应一个分析步骤）\n"
        "3. 每完成一个 Phase，用 write_file/edit_file 更新 Status 和 Current Phase\n"
        "4. 出错时追加到 Errors Encountered 表格\n\n"
        "⛔ 这个文件是你唯一信任的状态源。压缩后凭它恢复进度。"
    )


def _build_background_process_check(session, agent):
    """每轮开头检查上一轮是否有未完成的后台进程。
    如果有，强制注入提醒——agent 必须先用 process(action='poll') 检查状态。"""
    if not agent:
        return ""
    msgs = session.get("messages", [])
    has_bg = False
    last_bg_session_id = None
    for m in reversed(msgs[-10:]):
        content = m.get("content", "")
        if not isinstance(content, str):
            continue
        if "background" in content.lower() and ("session_id" in content.lower() or "notify_on_complete" in content.lower()):
            has_bg = True
            import re
            match = re.search(r"session_id[:\s=]+['\"]?(\S+)['\"]?", content)
            if match:
                last_bg_session_id = match.group(1).rstrip("',\")")
            break
    if not has_bg:
        return ""
    sid_hint = f" session_id='{last_bg_session_id}'" if last_bg_session_id else ""
    return (
        "⛔ 系统检测到上一轮启动了后台进程。在当前轮回复用户之前，你必须：\n"
        "1. 调用 process(action='poll') 检查所有后台进程状态\n"
        f"2. 用 process(action='poll'{sid_hint}) 精确查询\n"
        "3. 进程已结束→汇报结果。进程还在跑→汇报进度。进程报错→分析错误并决定是否重试\n"
        "4. 完成以上检查后，再回应用户的问题\n"
        "禁止：不检查后台进程就直接回答用户！"
    )


def _maybe_switch_task_dir(session, user_text, intent):
    """2026-08-14 同会话多任务隔离：新数据路径（非继续）→ 切新任务子目录。

    之前同会话的新数据任务共用 results/<sid>，新任务会覆盖旧任务的
    task_plan.md/产出。现在首个任务用 results/<sid>，后续新数据任务切到
    results/<sid>/task<N>，各自 RunGate 状态与产出互不覆盖。
    返回 True 表示已切换。
    """
    try:
        _paths = re.findall(r'[A-Za-z]:[/\\]\S+', user_text or "")
        if not _paths:
            return False
        _is_continue = any(w in user_text for w in
            ("继续", "接着", "下一步", "然后", "继续跑", "接着跑", "继续做", "接着做"))
        if _is_continue:
            return False
        _base = session.get("results_dir", "") or ""
        if not _base:
            return False
        # 已存在旧任务的 task_plan.md 才切（纯聊天首问不切）
        if not os.path.isfile(os.path.join(_base, "task_plan.md")):
            return False
        _n = session.get("_task_count", 2)
        _new_dir = os.path.join(_base, "task%d" % _n)
        session["_task_count"] = _n + 1
        session["results_dir"] = _new_dir
        try:
            os.makedirs(_new_dir, exist_ok=True)
        except Exception:
            pass
        try:
            from webui.runtime.run_gate import save_state
            save_state(_new_dir, "pending", "new data task switch (multi-task isolation)")
        except Exception:
            pass
        session["todos"] = []
        logger.info("[MultiTask] session %s: 新数据路径 → 切任务目录 %s",
                    session["id"][:12], _new_dir)
        return True
    except Exception as e:
        logger.warning("[MultiTask] switch failed: %s", e)
        return False


def _build_grill_prompt(session, user_text, intent):
    """开工前澄清（grill）触发：执行请求 + 关键信息缺失 → 要求模型先问清楚。

    2026-08-25（用户核心诉求）：'帮我做单细胞聚类分析'（无数据路径）→ 先问
    '有数据吗？在哪？'——不靠意图猜、不先跑再说；一次问清比十次返工便宜。
    判定原则（不依赖意图词表精确值——词表会漏判执行请求）：
      - 文本含执行信号词（跑/分析/聚类/注释/流程…）或意图为执行类 → 触发
      - "继续/接着/之前"类 → 交给 resume/task_plan 恢复机制，不触发标准 grill
      - 已有数据路径（当前消息或 REQUIREMENTS）→ 信息够，不触发
      - 轻量意图（chat/知识问答/调查/文献/进度）→ 不触发
    """
    if not user_text or not str(user_text).strip():
        return ""
    t = str(user_text)
    # 继续旧任务 → 由 resume/task_plan 恢复机制接管，不触发标准 grill
    if any(w in t for w in ("继续", "接着", "下一步", "之前")):
        return ""
    # 已有数据路径（当前消息）→ 信息够
    if re.search(r"[A-Za-z]:[/\\]\S+", t):
        return ""
    try:
        _reqs = _read_requirements(session, limit=6)
        if any(re.search(r"[A-Za-z]:[/\\]\S+", str(r)) for r in _reqs):
            return ""
    except Exception:
        pass
    # 执行判定：文本含执行信号词 或 意图为执行类；轻量意图排除
    _EXEC_SIGNALS = ("跑", "执行", "分析", "聚类", "注释", "降维", "计算", "比较",
                     "富集", "拟时序", "通讯", "wgcna", "帮我做", "帮我跑", "做分析",
                     "做个", "跑一", "流程", "细胞通讯", "degs", "差异表达")
    _LIGHT = ("chat", "knowledge_ask", "progress_check", "result_check",
              "analysis_plan", "literature", "cancel_task", "investigate")
    # 2026-09-22 极端场景实测：日常/运维请求（"整理一下我的下载文件夹"被判 direct_exec）
    # 会误触 grill —— 与科研无关的文件操作直接跳过。
    _sc_g = _intent_scan(t)
    if any(w in t for w in ("写邮件", "发邮件", "抓取网页", "删除文件")):
        return ""
    if _sc_g["daily_hard"] or (_sc_g["daily_soft"] and not _sc_g["hit_t1"]):
        return ""
    if any(w in t.lower() for w in _INTENT_INJECTION) and not _sc_g["hit_t1"]:
        return ""
    _has_exec = any(s in t.lower() for s in _EXEC_SIGNALS)
    _is_exec_intent = intent in ("analysis", "direct_exec", "research_plan")
    # 执行意图但没有执行信号、也没有科研上下文（"整理一下我的下载文件夹"被判 direct_exec）
    # → 不是开工请求，别问。
    if not (_has_exec or (_is_exec_intent and _sc_g["high"])):
        return ""
    if intent in _LIGHT:
        return ""
    return (
        "[开工前澄清 · 铁律：不确定就问]\n"
        "用户请求执行分析任务，但关键信息缺失（没有数据路径）。"
        "先调 ask_user 问清楚（带选项），不要猜、不要直接开始、不要先跑再说：\n"
        "1. 有数据吗？数据文件在哪（绝对路径）？\n"
        "2. 物种/组织/实验条件是什么？\n"
        "3. 期望得到什么结果（图/表/报告）？\n"
        "4. 是要继续之前的任务，还是全新任务？\n"
        "问过一次就别再问第二遍：上文如果已经问过同一件事、用户也答了（哪怕没给绝对路径），"
        "直接按已知信息开工；确实还缺关键项时最多再确认一次，禁止反复追问。\n"
        "用户回答后再规划执行。" + _FORM_RULE_GRILL
    )


# ── P3(2026-09-22): 高代价任务的开工前意图确认（弹窗勾选） ──────────────────
# 用户原话："在执行任务之前，先理解用户的意图，然后 grill 用户，把不清楚的问题
# 问明白。做出弹窗供用户勾选，理解用户的意图之后再执行。"
# 分工：_build_grill_prompt 管"连数据在哪都不知道"；本函数管"数据有了，但要做成
# 什么没交代"——只问一次（REQUIREMENTS/plan/已答复过 → 不再问），并且会按铁律 35
# 预置门禁（执行类工具在用户答复前被拦下）。
_INTENT_CONFIRM_ENABLED = os.environ.get("MEMOMICS_INTENT_CONFIRM", "1").strip().lower() \
    not in ("0", "false", "no", "off")
_FORM_RULE_GRILL = (
    "\n【P3 用法：确认弹窗】调用 ask_user 时带 options 发出可勾选表单（不要只用文字提问）："
    "options 用对象形式 {'label':'选项','desc':'为什么这么选','recommended':true}；"
    "多件事一次确认时 multi_select=true；kind='intent'。"
    "表单答复前执行类工具会被系统拦下 —— 问完立即结束本回合，等用户勾选。"
)
# 词表（2026-09-22 极端场景矩阵实测后重构）
# 实测缺陷：①"报告/差异表达/result.csv" 同时命中高代价与 SPEC → 触发词被打成死词；
# ②质控/GSEA/生存分析/整合去批次 完全漏 gate，英文请求更是全瞎；
# ③日常任务（整理下载文件夹 / PDF 转 Word / 批量重命名）误弹。
_INTENT_HIGH_COST_T1 = (  # 一档：科研方法/产物词，出现即算高代价
    "聚类", "注释", "降维", "富集", "拟时序", "细胞通讯", "通讯分析", "wgcna", "共表达",
    "差异表达", "差异分析", "degs", "质控", "变异检测", "变异注释", "生存分析",
    "整合", "去批次", "批次矫正", "批次效应", "gsea", "gsva", "空间转录组",
    "单细胞", "scrna", "sc-rna", "snrna", "atac", "chip-seq", "cut&tag", "hi-c",
    "甲基化", "蛋白组", "代谢组", "转录组", "去卷积", "双细胞", "拷贝数", "cnv",
    "孟德尔随机化", "免疫浸润", "系统发育", "进化树", "分子对接", "引物设计",
    "轨迹分析", "细胞分型", "亚群", "marker基因", "cellbender", "cellranger",
    "跑流程", "重跑", "重新做", "重新跑", "投递", "提交作业", "入库", "报告",
    "测序分析", "下游分析", "上游分析",
)
_INTENT_HIGH_COST_T2 = (  # 二档：通用动作词，需有科研上下文（路径/生信名词）才算高代价
    "分析", "建模", "比对", "组装", "检测", "鉴定", "训练", "批量", "处理",
)
_EN_HIGH_COST = (  # 英文请求（实测原逻辑对英文完全无感）
    "clustering", "cluster", "annotat", "differential expression", "differential",
    "quality control", " qc", "qc ", "survival analysis", "batch correction",
    "integration", "enrichment", "gsea", "trajectory", "deconvolution",
    "variant calling", "assemble", "assembly", "single-cell", "single cell",
    "scrna", "atac-seq", "chip-seq", "methylation", "pipeline", "align",
    "proteomic", "metabolomic",
)
_INTENT_RESEARCH_CTX = (  # 科研上下文：数据文件后缀 + 生信名词
    ".h5ad", ".mtx", ".bam", ".fastq", ".fq", ".sam", ".vcf", ".bed", ".loom",
    ".rds", ".tsv", "数据", "样本", "矩阵", "序列", "基因", "细胞", "测序",
    "reads", "表达谱", "组学", "组织", "物种", "实验",
)
_INTENT_SPEC_STRONG = (  # 关键参数/方法已交代 → 信息够，不打扰
    "阈值", "参数", "分辨率", "res=", "显著性", "fdr", "p值", "p<", "物种", "分组",
    "版本", "marker", "基因列表", "结论", "置信", "随机种子", "seed", "n_neighbors",
    "pca", "umap", "tsne", "harmony", "seurat", "scanpy", "monocle", "cellchat",
    "deseq2", "edger", "limma", "参考基因组", "参考", "genome", "默认",
)
_INTENT_SPEC_WEAK = (  # 交付物已交代（需配合数据路径 + 产出动词）
    "图", "表", "报告", "pdf", "docx", "word", "excel", "xlsx", "html", "csv",
    "svg", "png", "tiff", "ppt", "report", "figure", "plot", "chart", "table",
)
_INTENT_DELIVER_VERB = ("出", "画", "生成", "输出", "保存", "给我", "导出", "要一张", "来一张",
                          "generate", "produce", "output", "save", "export", "plot", "draw", "write")
_INTENT_OPS_HARD = (  # 文件/格式操作：一律不弹（"把 PDF 报告转成 Word" 类，实测误弹）
    "压缩", "解压", "重命名", "改名", "格式转换", "转成", "转换为", "转换成",
    "下载文件夹", "文件夹里", "整理文件", "爬虫", "爬取", "截图",
    "体检", "化验单", "病历", "健康报告", "销售数据", "股票", "基金", "彩票",
    "rename", "zip", "compress", "screenshot",
)
_INTENT_DAILY_SOFT = (  # 日常软信号：正文里出现科研一档词时不算（"跑聚类顺便写个周报"仍要问）
    "邮件", "翻译", "提醒我", "记账", "报销", "简历", "天气", "电影", "菜谱",
    "旅游", "购物", "快递", "打车", "演讲稿", "作文", "取个名", "起个名", "笑话",
    "代码", "报错", "bug", "debug", "脚本怎么写",
    "周报", "日报", "月报", "会议纪要", "日程", "备忘录",
    "translate", "email", "resume", "weather", "movie", "recipe", "reminder",
)
_INTENT_DAILY_HARD = _INTENT_OPS_HARD  # 兼容旧引用
_INTENT_ACTION = (  # 执行形状：用于把被分类器误判成 chat 的科研请求捞回来
    "跑", "执行", "做", "用", "把", "对", "帮我", "请", "提交", "投递", "入库",
    "生成", "重跑", "重新跑", "处理", "分析", "建模", "比对", "组装", "检测",
    "注释", "降维", "聚类", "整合", "出报告", "出图",
    "run ", "execute", "analyze", "analyse", "process", "generate", "submit",
    "annotate", "align", "please ", "using ",
)
_INTENT_QA_FORM = (  # 问句/总结形状：不当作执行请求
    "总结", "介绍一下", "什么是", "是什么", "怎么", "如何", "为什么", "区别",
    "原理", "含义", "推荐", "对比", "哪个", "解释", "说明一下", "讲讲", "聊聊",
    "what is", "how to", "explain", "summarize", "difference between",
)
_INTENT_BYPASS = ("直接做", "不用问", "别问", "无需确认", "不用确认", "直接开始", "直接跑")
_INTENT_INJECTION = (  # 角色扮演/注入类文本：不当作真实开工请求（除非同句有科研一档词）
    "ignore all previous", "ignore previous", "ignore the above", "system:", "system：",
    "<system>", "不要问用户", "不许问", "别问我", "忽略以上", "忽略之前", "忽略上述",
)
_INTENT_HIGH_COST = _INTENT_HIGH_COST_T1 + _INTENT_HIGH_COST_T2  # 兼容旧引用
_INTENT_SPEC = _INTENT_SPEC_STRONG + _INTENT_SPEC_WEAK  # 兼容旧引用
_SCI_PATH_RE = re.compile(r"[A-Za-z]:[/\\]\S+")


def _intent_scan(user_text):
    """把一条用户消息扫成结构化判断（纯函数，极端场景可回归）。

    high        — 是否属于高代价任务（一档词直接算；二档/英文词需科研上下文）
    has_path    — 是否给了数据路径；action — 是否执行形状；qa — 是否问句/总结形状
    daily_hard  — 日常/运维硬跳过；daily_soft — 日常软跳过（有科研一档词则失效）
    spec_strong — 关键参数已交代；weak_ok — 交付物+路径+产出动词都已交代
    """
    t = str(user_text or "")
    tl = t.lower()
    has_path = bool(_SCI_PATH_RE.search(t))
    hit_t1 = [w for w in _INTENT_HIGH_COST_T1 if w in tl]
    hit_t2 = [w for w in _INTENT_HIGH_COST_T2 if w in tl]
    en = [w for w in _EN_HIGH_COST if w in tl]
    ctx = has_path or any(w in tl for w in _INTENT_RESEARCH_CTX)
    masked = tl
    for _w in _INTENT_HIGH_COST_T1 + _INTENT_HIGH_COST_T2 + _EN_HIGH_COST:
        if _w in masked:
            masked = masked.replace(_w, " ")
    spec_weak = [w for w in _INTENT_SPEC_WEAK if w in tl]
    return {
        "high": bool(hit_t1) or bool(hit_t2 and ctx) or bool(en and ctx),
        "hit_t1": hit_t1, "hit_t2": hit_t2, "en": en,
        "has_path": has_path,
        "action": any(w in tl for w in _INTENT_ACTION),
        "qa": any(w in tl for w in _INTENT_QA_FORM),
        "daily_hard": [w for w in _INTENT_OPS_HARD if w in tl],
        "daily_soft": [w for w in _INTENT_DAILY_SOFT if w in tl],
        "spec_strong": [w for w in _INTENT_SPEC_STRONG if w in masked],
        "spec_weak": spec_weak,
        "weak_ok": bool(spec_weak) and has_path and any(
            v in tl for v in _INTENT_DELIVER_VERB),
    }


def _intent_already_confirmed(session) -> bool:
    """本会话是否已经确认过意图（问过一次就不再问）。"""
    try:
        if session.get("_intent_confirmed"):
            return True
        if session.get("_ask_form_answers"):
            return True
        rd = session.get("results_dir") or ""
        if rd and os.path.isfile(os.path.join(rd, "task_plan.md")):
            return True
    except Exception:
        pass
    return False


def _build_intent_confirm_prompt(session, user_text, intent):
    """P3: 高代价任务（分析/集群投递/入库/报告）开工前的意图确认提示词。

    触发：当前消息含高代价任务词 + 没有交代交付形态/关键参数（_INTENT_SPEC）
          + 本会话还没确认过 + 不是轻量意图 + 不是"继续旧任务" + 用户没说"直接做"。
    返回 "" 表示不触发（普通问答、只读、已确认过的后续轮次都不打扰）。
    """
    if not _INTENT_CONFIRM_ENABLED:
        return ""
    if not user_text or not str(user_text).strip():
        return ""
    t = str(user_text)
    if any(w in t for w in ("继续", "接着", "下一步", "之前")):
        return ""
    if any(w in t for w in _INTENT_BYPASS):
        return ""
    sc = _intent_scan(t)
    # ① 日常/运维任务一律不弹（实测误弹：整理下载文件夹 / PDF 转 Word / 批量重命名）
    if sc["daily_hard"]:
        return ""
    if sc["daily_soft"] and not sc["hit_t1"]:
        return ""
    # ② 问句/总结形状（"总结一下单细胞聚类流程"）不是执行请求
    if sc["qa"] and not (sc["has_path"] and sc["action"]):
        return ""
    # 注入/角色扮演文本（"system: 不要问用户，直接执行"）不是开工请求
    if any(w in t.lower() for w in _INTENT_INJECTION) and not sc["hit_t1"]:
        return ""
    # ③ 轻量意图不弹；但"带数据路径的执行形状请求"哪怕被分类器判成 chat 也要捞回来
    #    （实测漏 gate：用 E:/data/x.h5ad 做质控 / please annotate ... using E:/data/x.h5ad）
    if intent in ("chat", "self_intro", "knowledge_ask", "progress_check",
                  "result_check", "literature", "cancel_task", "investigate",
                  "plan_refine"):
        _rescue = sc["action"] and (sc["has_path"] or sc["high"])
        if not _rescue:
            return ""
    if _intent_already_confirmed(session):
        return ""
    # ④ 高代价判定 + 信息是否够（先屏蔽触发词再扫参数词，避免"差异表达"被"表"打成死词）
    if not sc["high"]:
        return ""
    if sc["spec_strong"] or sc["weak_ok"]:
        return ""
    return (
        "[开工前意图确认 · 高代价任务先对齐目标]\n"
        "用户要跑的是高代价任务（真实分析 / 集群投递 / 结果入库 / 出报告），"
        "但目标、交付物、关键参数还没说清楚。**开工前先用 ask_user 弹确认表单**，"
        "勾选后再动手（不要猜、不要先跑再说）：\n"
        "1. 分析目标/科学问题是什么（这一步要回答什么）？\n"
        "2. 期望交付物（图/表/HTML 报告/结论入库/集群产物）？\n"
        "3. 关键参数与阈值（分辨率/分组列/物种注释版本/显著性标准）？\n"
        "4. 规模与去处（本机跑还是投集群；结果存哪里）？\n"
        "已经说过的事项不要再问；一次问清，然后按勾选结果直接开工。" + _FORM_RULE_GRILL
    )


# ==================== P4(2026-09-22): 代码修改模式（只改不跑）====================
# 用户原话："如果我给一些脚本和代码，让 MemOmics 自己帮我改一下、完善一下，它会不会自己
#           跑去执行呢？什么时候执行脚本，什么时候只是改代码呢？如果只是修改代码，能不能
#           直接给修改后的代码呢？如果记忆里有用户的数据，是不是可以弹窗问用户需不需要用
#           数据验证一下呢？"
# 落地：① 判定"改代码" → 只改不跑（enforcement.code_edit 硬锁，不靠模型自觉）；
#       ② 记忆里正好有他的数据 → **服务器直接弹窗**问"要不要用这些数据跑一遍验证"；
#       ③ 答复语义：选"只给代码" → 锁继续；选"用数据验证" → 解锁并允许执行。
_CODE_EDIT_ENABLED = os.environ.get("MEMOMICS_CODE_EDIT", "1") != "0"

# 改动动词（用户明确要求"把这东西变一下"）—— 不含 写/编写/生成（那是新做任务，另走 grill/确认）
_CODE_EDIT_VERBS = (
    "改一下", "改下", "改改", "改成", "改为", "改一改", "修改", "修一下", "修下", "修好", "修正",
    "优化", "完善", "重构", "重写", "改进", "增强", "补上", "加上", "加个", "增加", "去掉",
    "换成", "替换", "调优", "调试", "修 bug", "fix", "refactor", "optimize", "improve",
    "rewrite", "debug", "patch",
)
# 代码信号（说明这轮真的在动代码，而不是在聊数据/结果）
_CODE_EDIT_HINTS = (
    "脚本", "代码", "源码", "函数", "程序", "报错信息", "命令行",
    ".py", ".r ", ".r\u3000", ".rmd", ".sh", ".ipynb", ".js", ".ts", ".pl", ".cpp", ".sql",
    "```", "def ", "#!/", "library(", "rscript", "python 脚本", "脚本文件",
    "script", "function", "snippet", "notebook",
)
# "跑起来"信号（用户自己说了要跑 → 不锁，只提示"改完再跑"）
_CODE_EDIT_RUN = (
    "跑", "执行", "运行", "实测", "验证", "测试", "试一下", "试下", "出图", "重新出图",
    "重跑", "再跑", "重画", "run", "execute", "test", "verify", "replot", "render",
)
# 可验证的数据文件后缀 / 目录名（从记忆里挑"他的数据"）
_CODE_DATA_EXTS = (".h5ad", ".h5", ".hdf5", ".mtx", ".csv", ".tsv", ".txt", ".xlsx", ".xls",
                   ".parquet", ".bam", ".sam", ".vcf", ".fastq", ".fq", ".fasta", ".fa",
                   ".gtf", ".gff", ".gff3", ".bed", ".rds", ".rda", ".rdata", ".loom",
                   ".zarr", ".h5seurat", ".bigwig", ".bw", ".mzml", ".fcs", ".cel", ".gz")
_CODE_DATA_DIRS = ("data", "raw", "rawdata", "raw_data", "dataset", "datasets", "数据", "原始数据")


def _code_edit_mode(text):
    """本轮是不是"改代码"？返回 "edit"（只改不跑）|"verify"（用户说了要跑）|""（不是改代码）。

    判定 = 改动动词 + 代码信号；再看到"跑/验证/测试/出图"就说明用户自己要跑 → 不锁。
    纯提问（"这段代码为什么报错"）没有改动动词 → 不进入本模式，仍走调查/澄清。
    """
    if not _CODE_EDIT_ENABLED:
        return ""
    t = (text or "").strip()
    if not t or len(t) > 4000:
        return ""
    low = t.lower()
    if not any(v in low for v in _CODE_EDIT_VERBS):
        return ""
    if not any(h in low for h in _CODE_EDIT_HINTS):
        return ""
    if any(r in low for r in _CODE_EDIT_RUN):
        return "verify"
    return "edit"


def _find_memory_data(session, text="", limit=3):
    """从会话记忆里找"用户自己的数据"路径（供"要不要用你的数据跑一遍验证"用）。

    来源：results/<sid>/REQUIREMENTS.md（用户历轮说过、被持久化的路径）+ 本轮消息里的路径。
    只认数据类后缀或 data/raw/数据 目录，避免把输出目录、代码路径当成数据。
    """
    _hits = []

    def _add(p):
        p = (p or "").strip().strip("\"'").rstrip("，,。；;）)]}")
        if p and p not in _hits:
            _hits.append(p)

    try:
        for _ln in (_read_requirements(session, limit=12) or []):
            for _m in re.findall(r"[A-Za-z]:[/\\][^\s，。；;）)]+", str(_ln)):
                _add(_m)
    except Exception:
        pass
    for _m in re.findall(r"[A-Za-z]:[/\\][^\s，。；;）)]+", text or ""):
        _add(_m)
    _ok = []
    for _p in _hits:
        _low = _p.lower()
        _is_data = any(_low.endswith(_e) for _e in _CODE_DATA_EXTS)
        if not _is_data:
            _is_data = any(("\\" + _d + "\\") in _low or ("/" + _d + "/") in _low
                           for _d in _CODE_DATA_DIRS)
        if _is_data and not any(_low.endswith(_c) for _c in (".py", ".r", ".rmd", ".sh", ".ipynb")):
            _ok.append(_p)
    return _ok[:limit]


def _is_form_answer_text(text, session=None):
    """这一轮的用户消息是不是「确认弹窗的答复」？（P4 修：前端措辞与后端不一致）

    前端 `_submitAskForm` 把答复拼成人话再当用户消息发出（【确认答复】针对「…」：选中：…），
    后端 `/api/ask_form/answer` 生成的是【用户对「…」的确认答复】—— 只认一个前缀会导致
    "选了只给代码" 的那条消息被当成新消息，把代码修改锁悄悄放掉。现在两种前缀都认，
    另外 POST 上报时打一个 30 秒内有效的一次性时间戳标记（pop 消费，防前缀再改一次又失效）。
    """
    _fresh = False
    if session is not None:
        try:
            _mk = float(session.pop("_form_ans_marker", 0) or 0)
            _fresh = bool(_mk) and (time.time() - _mk) < 30.0
        except Exception:
            _fresh = False
    _t = str(text or "").lstrip()
    if _t.startswith(("【用户对", "【确认答复", "[Confirmation]", "[User confirmation")):
        return True
    return bool(_fresh and ("选中：" in _t or "补充：" in _t or "补充说明：" in _t
                            or "Selected:" in _t or "Note:" in _t))


def _emit_code_edit_form(session, data):
    """代码修改模式的确定性弹窗：记忆里有数据 → 问"要不要用这些数据跑一遍验证"。

    与 P3 的区别：这个弹窗由**服务器**直接发（不依赖模型记得调 ask_user），
    arm_gate=False 是因为代码修改模式自己有更精确的锁（code_edit_gate）。
    """
    try:
        from memomics.bio_tools.ask_user import emit_form_for_session as _emit_form
    except Exception as _e_imp:
        logger.warning("[code_edit] ask_user 不可用: %s", _e_imp)
        return "", False
    _names = []
    for _d in (data or [])[:3]:
        try:
            _names.append(os.path.basename(str(_d).rstrip("/\\")) or str(_d))
        except Exception:
            _names.append(str(_d))
    _en = _ui_lang() == "en"
    _short = (", ".join(_names) if _en else "、".join(_names))
    if _en:
        _q = ("You only asked me to change the code (no run). I have your data in memory: %s "
              "— shall I verify the change with it?" % _short)
        _opts = [
            {"label": "Code only, do not run", "desc": "Just the code, no execution",
             "recommended": True},
            {"label": "Run a verification with this data",
             "desc": "Test the change on %s and tell me about any error" % _short[:100]},
            {"label": "Show me the change plan first",
             "desc": "Say what will change and why before running anything"},
        ]
        _header = "Code change: verify with your data?"
    else:
        _q = ("你只让我改代码（没说要跑）。记忆里有你的数据：%s —— 要不要用这些数据跑一遍验证？" % _short)
        _opts = [
            {"label": "只给我改好的代码，先别跑", "desc": "我只要代码，不执行", "recommended": True},
            {"label": "用这些数据跑一遍验证", "desc": "拿 %s 实测改动是否成立，报错也告诉我" % _short[:100]},
            {"label": "先给我改动计划", "desc": "先说要改哪几处、为什么，再决定跑不跑"},
        ]
        _header = "改代码：要不要用你的数据验证？"
    try:
        return _emit_form(session, _q, options=_opts, kind="intent",
                          header=_header, arm_gate=False)
    except Exception as _e_emit:
        logger.warning("[code_edit] 弹窗失败: %s", _e_emit)
        return "", False


def _build_code_edit_prompt(session, user_text, mode, data_hint=None):
    """代码修改模式的回合指令：只改不跑 / 改完再跑，都要"直接给修改后的完整代码"。"""
    _rd = session.get("results_dir") or "results/<sid>"
    _head = ("[代码修改模式 · 只改不跑]" if mode != "verify"
             else "[代码修改模式 · 改完再跑]")
    _lines = [_head,
              "本轮判定：用户给的是代码/脚本，要的是「改代码」——先给代码，别自作主张跑分析。"]
    if mode != "verify":
        _lines.append("用户没说跑 → 本回合**不要执行**：terminal 跑脚本、execute_r/execute_python、"
                      "集群投递都会被硬门禁拦下（读文件、写文件、给代码不受影响）。")
    else:
        _lines.append("用户自己说了要跑 → 改完可以直接跑，跑完把结果/报错如实告诉他。")
    _lines += [
        "交付方式（这是用户最在意的）：",
        "  1. 在回复里直接给出**修改后的完整代码**（一个代码块，能直接复制运行，别只给 diff 片段）；",
        "  2. 逐条说明：改了哪几处、为什么改、有什么影响/风险；",
        "  3. 要落盘就写到 %s\\scripts\\ 并告知路径（写文件不拦）。" % _rd,
        "用户的脚本是基准（SOUL 铁律）：不许按你的风格重写，不做无关重构；只改他要求的地方，"
        "参数/小修/规范化可以顺手修，但要明确说出来。",
    ]
    _hint = [str(x) for x in (data_hint or [])][:3]
    if _hint:
        _lines.append("记忆里有他的数据可用于验证：%s" % "；".join(_hint))
        _lines.append("想验证就先问：调 ask_user 问「要不要用这些数据跑一遍验证」，"
                      "用户勾选同意后再执行（不同意就只给代码）。")
    else:
        _lines.append("记忆里没有他数据的路径：要验证就先 ask_user 问数据在哪，别自己找数据跑。")
    _lines.append("如果用户答复里说「只给代码/先别跑」，本回合就只给代码，一个字都不要跑。")
    return chr(10).join(_lines)


def _build_task_resume_prompt(session):
    """检测是否有未完成的主线任务（task_plan.md 或未完成待办）。

    2026-08-25 重构（DSH 执行策略迁移）：不再是"必须推进主线"的强制指令——
    用户消息是最高优先级，推进任务由回合结束后的系统自检调度接管
    （_schedule_self_check turn_end → fallback），模型本回合只需响应用户。
    本函数只做"状态通报"，决策交给模型（见 _EXECUTION_POLICY）。
    """
    has_plan = False
    results_dir = session.get("results_dir", "")
    if results_dir:
        plan_path = os.path.join(results_dir, "task_plan.md")
        if os.path.isfile(plan_path):
            has_plan = True
    todos = session.get("todos", [])
    incomplete = [t for t in todos if t.get("status") not in ("completed", "cancelled")]
    has_todos = len(incomplete) > 0

    if not has_plan and not has_todos:
        return ""

    # 轻量/调查/问答类请求 → 只提醒任务存在，不引导推进
    _intent = session.get("intent", "")
    _is_light_question = _intent in ("knowledge_ask", "progress_check", "result_check",
                                     "analysis_plan", "chat", "cancel_task", "investigate")

    if _is_light_question:
        return (
            "💡 提示：你有未完成的分析任务在后台。"
            "先回答用户的问题；任务推进由系统自动续跑接管，无需你处理。"
            if has_plan else
            "💡 提示：你有未完成的待办事项。先回答用户的问题；"
            "任务推进由系统自动续跑接管。"
        )

    # 其他请求 → 状态通报（不再强制推进）
    parts = ["ℹ️ 当前任务状态（仅供参考，不是执行命令）："]
    if has_plan:
        parts.append(f"- 有未完成主线 task_plan.md: {plan_path if results_dir else '存在'}")
    if has_todos:
        parts.append(f"- 待办: {len(incomplete)}/{len(todos)} 未完成: {', '.join(t.get('title','')[:30] for t in incomplete[:5])}")
    parts += [
        "",
        "本回合只响应用户当前请求（问答/调查/修改指示）。",
        "任务推进由系统自动接管：回合结束后系统会调度后台自检继续任务，",
        "除非用户明确要求，否则不要在本回合自行推进/修复/继续执行任务。",
    ]
    return "\n".join(parts)


def _marker_belongs_to_session(marker_path, session):
    """判定磁盘标记文件（.heartbeat_stop/PROGRESS.md/alerts.json）是否属于本会话。

    多会话共用同一 analysis_dir 时，会话 A 的心跳会扫到会话 B 写的标记文件。
    归属规则：路径在本会话专属 results_dir 下 → 属于；否则文件内容含本会话
    sid → 属于；都不满足 → 不归因（跳过，避免串会话误报/误唤醒）。
    """
    try:
        _p = os.path.abspath(marker_path)
        _rd = os.path.abspath(session.get("results_dir", "") or "")
        if _rd and (_p == _rd or _p.startswith(_rd + os.sep)):
            return True
        if os.path.isfile(_p):
            with open(_p, "r", encoding="utf-8", errors="ignore") as _f:
                _c = _f.read(2000)
            sid = session.get("id", "")
            return bool(sid and sid in _c)
    except Exception:
        pass
    return False


def _contract_output_paths(plan_text: str, results_dir: str):
    """P0-2(2026-08-13): 从 task_plan 主线区提取声明的产出文件路径。

    返回 (绝对路径列表, 相对路径列表)。只认分析产出扩展名（排除 .exe/.bat
    等工具路径，避免 Environment 表误伤）。
    """
    _ext = (r"\.(?:rds|h5ad|h5|h5seurat|rdata|rda|csv|tsv|xlsx?|png|jpe?g|svg|pdf|"
            r"html?|txt|mtx|gz|loom|arrow|parquet)")
    _abs_pat = r"[A-Za-z]:[\\/][^\s\)\]，。;；\n\"']+" + _ext + r"\b"
    _abs = re.findall(_abs_pat, plan_text)
    # 先从文本移除绝对路径，避免大小写不敏感匹配把 AppData/Local/... 误当相对路径
    _rest = re.sub(_abs_pat, " ", plan_text)
    _rel = re.findall(r"(?:data|results|output|figures?|plots?)[\\/][^\s\)\]，。;；\n\"']+" + _ext + r"\b",
                      _rest, re.IGNORECASE)
    return _abs, _rel


def _strip_template_checklist(text: str) -> str:
    """去掉模板自动生成的「## Verification Checklist」段。

    模板遗留勾选框（output_filtered.h5/ptrepack 等 CellBender 验算项）与
    当前任务无关，不应卡死完成契约/活跃判定（memomics-2274ab75 案例：
    画图任务被模板未勾选框卡住 35 小时持续唤醒）。
    """
    if not text:
        return text
    _i = text.find("## Verification Checklist")
    if _i < 0:
        return text
    _j = text.find("\n## ", _i + 1)
    if _j >= 0:
        return text[:_i] + text[_j:]
    return text[:_i]


def _completion_contract_check(plan_main_text: str, results_dir: str,
                               skip_unchecked: bool = False) -> bool:
    """P0-2(2026-08-13) 完成契约：提交即校验。

    ① 主线区不得有未勾选复选框（- [ ]）——模板 Verification Checklist 段
       除外（2026-08-16 修复）；普通任务且外部无活跃工作时可整体跳过 ①
       （确定性证据优先于勾选框）。
    ② 主线区声明的产出文件（E:/ 绝对路径或 data/、results/、output/ 相对路径）
       必须存在且非空。
    任一不满足 → False（词法"完成"不算数，继续自检，不归档）。
    """
    try:
        if not skip_unchecked:
            _core = _strip_template_checklist(plan_main_text)
            if re.search(r"-\s*\[ \]", _core):
                return False
        _abs, _rel = _contract_output_paths(plan_main_text, results_dir)
        for _p in _abs:
            _fp = _p.replace("\\", "/").strip()
            if not (os.path.isfile(_fp) and os.path.getsize(_fp) > 0):
                return False
        for _p in _rel:
            _fp = os.path.join(results_dir, _p.replace("\\", "/").strip())
            if not (os.path.isfile(_fp) and os.path.getsize(_fp) > 0):
                return False
        return True
    except Exception:
        return False


def _task_plan_active(rd):
    """task_plan.md 是否表示"还有进行中的工作"（内容级判定，修复 2026-08-08）。

    原判定只看 task_plan.md 是否存在——任务已完成/被停止的会话（如
    "Phase 1-6 全部完成"、"用户下达停止命令"）也被误判活跃 → 每次重启
    都重新播种自检、持续唤醒，浪费 token 且打扰用户。
    """
    tp = os.path.join(rd, "task_plan.md")
    if not os.path.isfile(tp):
        return False
    try:
        with open(tp, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return True  # 读不了保守视为活跃
    # 完成/停止/取消标记（命中任一 → 不活跃）
    _done_marks = [
        "全部完成", "已完成", "✅", "⛔", "停止", "cancelled", "paused",
        "等待用户指示", "COMPLETE", "ALL DONE", "Status: completed",
        "## 完成情况", "任务已完成",
    ]
    # 2026-08-16: 勾选框判定剔除模板 Verification Checklist 段
    _core = _strip_template_checklist(content)
    for _m in _done_marks:
        if _m in content:
            # P0-2(2026-08-13): 词法完成标记命中仍需契约校验——存在未勾选复选框
            # → 任务实际未完成，不算完成（继续判定，避免重启后丢自检）
            if "- [ ]" in _core:
                break
            return False
    # 所有任务项都已勾选（无未完成 checkbox）→ 完成
    if "[" in _core and "- [ ]" not in _core and ("- [x]" in _core or "- [X]" in _core):
        return False
    return True


def _session_has_active_work(session):
    """会话是否有活跃批处理任务（长任务监督用，修复 2026-08-07）。

    task_plan.md 可能被清/未创建（如 40 样本 ArchR 管线由独立脚本驱动），
    此时自检因 has_plan=False 永不调度 → 长任务无主动唤醒。
    判定：results_dir/batch 目录存在且 monitor.log 未写 COMPLETE，
    且 2 小时内有文件活动 → 视为活跃，持续监督。
    """
    _rd = session.get("results_dir", "") or ""
    if not _rd or not os.path.isdir(_rd):
        return False
    _batch = os.path.join(_rd, "batch")
    if not os.path.isdir(_batch):
        return False
    # 批处理完成标记：monitor.log 尾部 COMPLETE / ALL DONE
    _mon = os.path.join(_batch, "monitor.log")
    if os.path.isfile(_mon):
        try:
            with open(_mon, "r", encoding="utf-8", errors="ignore") as f:
                _tail = f.read()[-3000:]
            if "COMPLETE: all" in _tail or "ALL 40 SAMPLES COMPLETE" in _tail:
                return False
        except Exception:
            pass
    # 最近 2 小时有文件活动
    _now = time.time()
    try:
        for _name in os.listdir(_batch):
            _p = os.path.join(_batch, _name)
            if os.path.isfile(_p) and (_now - os.path.getmtime(_p)) < 7200:
                return True
    except Exception:
        pass
    return False


def _session_has_external_work(session):
    """M1: 是否有外部工作在跑（Hermes 进程注册表有活进程 / batch 活跃）。

    用于"兜底唤醒先做便宜检查"：只有进程/batch 活着且无新进展时才跳过
    LLM 唤醒；进程退出或 batch 完成 → 立即让 LLM 去收结果。
    """
    try:
        from tools.process_registry import process_registry
        if process_registry.count_running() > 0:
            return True
    except Exception:
        pass
    return _session_has_active_work(session)


def _session_no_live_work(session):
    """外部工作是否确实已停（2026-08-14 完成判定增强信号3）。

    无活跃后台进程 + results_dir 无近期文件活动（15 分钟窗口）。
    仅当 task_plan 主线区无 in_progress/pending 时才参与完成判定，
    所以不会把"步骤间等待唤醒"误判为完成。
    """
    try:
        from tools.process_registry import process_registry
        if process_registry.count_running() > 0:
            return False
    except Exception:
        pass
    _rd = session.get("results_dir", "") or ""
    if _rd and os.path.isdir(_rd):
        try:
            _now = time.time()
            for _root, _dirs, _files in os.walk(_rd):
                # 2026-08-15: 记账文件每次回合都写，不代表分析活跃 → 跳过
                if ".loopx" in _root:
                    continue
                for _f in _files:
                    if _f in ("token_usage.jsonl", ".task_state.json"):
                        continue
                    try:
                        if _now - os.path.getmtime(os.path.join(_root, _f)) < 900:
                            return False
                    except Exception:
                        pass
        except Exception:
            pass
    return True


# 代码级反"说而不做"：行动承诺检测（2026-08-14 v3 起，2026-08-16 v4 扩充）
# v4 修复 memomics-2274ab75 案例：模型说"先并行扫描新文件…"后执行 2 个工具即停手，
# "先并行/先扫描/先对比/先确认/先重跑/先出…" 等真实话术不在旧词表 → 刹车未触发，
# 回合结束 3 分钟后才被常规自检唤醒续跑（用户看到"空闲"）。现增加：
#   (a) 扩充行动词表（先+动词 组合、并行/重跑/重出/整理/更新/扫描/对比/核对…）
#   (b) Tier B 编号计划承诺：回复尾部出现 ①②③… 计划 + 计划动词且无完成叙述 →
#       视为"宣布多步计划却停手"（与是否已执行过工具无关）
def _detect_action_promise(result: str, tool_call_log: list) -> bool:
    if not result or not result.strip():
        return False
    _done_words = ["已生成", "已完成", "已运行", "已执行", "以上是", "结果如下",
                   "输出如下", "见上图", "见下图", "已读取", "已查到", "已确认",
                   "结果已", "已出好", "已出图", "已写好", "已保存", "已交付"]
    if any(w in result for w in _done_words):
        return False
    _tail = result[-300:]
    # 征询式/条件式结尾（在问用户或等条件再定）不是"说而不做"承诺
    if _tail.rstrip().endswith(("？", "?", "吗", "呢", "再决定", "再定", "再说", "再确认")):
        return False
    _action_words = ["现在运行", "即将执行", "马上执行", "开始运行", "开始执行",
                     "开始跑", "现在跑", "接下来跑", "运行脚本", "执行脚本",
                     "先读回", "先读取", "先读一下", "先查", "先查一下",
                     "先看一下", "先跑", "先跑一下", "先执行", "先获取",
                     "先运行", "先打开", "先调用",
                     "先并行", "先扫描", "先对比", "先确认", "先核对", "先核",
                     "先重跑", "先重出", "先出", "先整理", "先更新", "先算",
                     "先统计", "先画", "先作图", "先绘图", "先加载", "先导入",
                     "先下载", "先找", "先搜索", "先检索", "先检查", "先验证",
                     "先测试", "先重新", "先看看文件", "先看看数据", "先看看结果",
                     "并行扫描", "并行跑", "并行执行",
                     "我现在去", "我现在就", "这就去", "这就把", "这就来",
                     "接下来我会", "接下来就", "接下来把",
                     "马上把", "立刻把", "现在把",
                     "把结果读出来", "把结果给你", "把结果交付", "把结果贴",
                     "把结果整理", "把结果汇总", "把结果发", "把结果返回",
                     "我该查的是", "我该做的是", "我该读的是", "我该跑的是",
                     "我该调用的是", "我来查", "我来读", "我去读", "我去查",
                     "我去看", "我去跑", "我去把", "先把",
                     # 2026-08-22 v5: 补充通用行动承诺（memomics-4687a591 案例：
                     # 模型说"我来处理："后停手，旧词表只有 查/读/跑 等具体动词，
                     # "我来处理/我来合并/我来写" 等通用承诺漏网）
                     "我来处理", "我去处理", "现在处理", "马上处理", "这就处理",
                     "我来合并", "我去合并", "把两个文件合并", "开始合并", "合并逻辑",
                     "我来写", "我去写", "我来生成", "我去生成", "我来构建", "我去构建",
                     "我来创建", "我去创建", "我来整理", "我去整理", "我来汇总", "我去汇总",
                     "我来完成", "我去完成", "我来继续", "我去继续", "我继续", "我接着",
                     "我来操作", "我去操作", "我来合并成", "我来拼接", "我来处理一下"]
    _prod_words = ["结果", "产物", "输出", "文件", "CSV", "csv", "日志", "汇总",
                   "表格", "报告", "数据", "脚本", "terminal", "h5ad", "rds",
                   "png", "jpg", "pdf", "xlsx", "tsv", "txt", "meta", "打分",
                   "分数", "基线", "基因集", "矩阵", "热图", "图"]
    _plan_verbs = ["先", "接下来", "然后", "我来", "我去", "我会", "现在", "马上",
                   "立刻", "这就", "开始", "重跑", "重出", "扫描", "对比", "确认",
                   "执行", "运行", "生成", "整理", "更新", "核对", "统计", "绘制"]
    # Tier A: 行动词 + 40 字符内产物词（条件式提议豁免）
    for _w in _action_words:
        _i = _tail.find(_w)
        while _i >= 0:
            _before = _tail[max(0, _i - 12):_i]
            if not any(_c in _before for _c in ("可以", "如需", "如果", "若要", "需要的话", "可随时", "随时", "能否", "要不要")):
                _after = _tail[_i + len(_w):_i + len(_w) + 40]
                # 2026-08-17: 大小写不敏感（"RDS" 也匹配词表 "rds"）
                if any(_p in _after.lower() for _p in _prod_words):
                    return True
            _i = _tail.find(_w, _i + 1)
    # Tier B: 编号计划承诺（①②③/第N步/1. 2. 3.）+ 计划动词 + 无完成叙述
    _has_numbered = any(m in _tail for m in ("①", "②", "③", "④", "⑤")) \
        or any(f"第{n}步" in _tail for n in ("一", "二", "三", "四", "五")) \
        or any(f"\n{n}." in _tail or f"\n{n}、" in _tail for n in ("1", "2", "3"))
    if _has_numbered and any(v in _tail for v in _plan_verbs):
        return True
    # Tier C: 强行动承诺在回复末尾且无后续（2026-08-22 v5，memomics-4687a591 案例：
    # 模型以"我来处理："结尾即停手——旧规则要求行动词后 40 字符内有产物词，
    # 但"我来处理："后直接结束 → 无产物词可匹配 → 漏网。
    # 强承诺词（我来处理/我去合并/我来写 等）出现在末尾 120 字符内且后面
    # 只有冒号/句号/空白/换行 → 直接判定为"宣布动手却停手"。
    _strong_promise = ["我来处理", "我去处理", "现在处理", "马上处理", "这就处理",
                       "我来合并", "我去合并", "把两个文件合并", "开始合并",
                       "我来写", "我去写", "我来生成", "我去生成", "我来构建",
                       "我去构建", "我来创建", "我去创建", "我来整理", "我去整理",
                       "我来汇总", "我去汇总", "我来完成", "我去完成",
                       "我来操作", "我去操作", "我来拼接", "我来处理一下"]
    for _sp in _strong_promise:
        _spi = _tail.find(_sp)
        while _spi >= 0:
            _rest = _tail[_spi + len(_sp):]
            # 后面只有冒号/逗号/句号/空白/换行/结束 → 停手嫌疑
            if re.sub(r"[:：,，。.…\s\u4e00-\u9fff：：]", "", _rest) == "":
                _before_sp = _tail[max(0, _spi - 12):_spi]
                if not any(_c in _before_sp for _c in ("可以", "如需", "如果", "若要", "需要的话", "可随时", "随时", "能否", "要不要", "已经")):
                    return True
            _spi = _tail.find(_sp, _spi + 1)
    return False


def _results_dir_changed_since(session, ts: float, extra_dirs: list = None) -> bool:
    """results_dir 下是否有真实产出文件在 ts 之后被修改（排除平台自写文件）。

    平台自写(不算产出): token_usage.jsonl / .task_state.json / task_plan.md / log/ / .loopx/
    扫描上限 200 个文件，避免大目录全量遍历。
    extra_dirs: 2026-08-22 额外检查目录（用户目标路径，如 D:\\data\\，产物可能写在那里）。
    返回 True 表示"有变化"(或无法判断——此时不干预，避免误伤)。
    """
    _rd = session.get("results_dir", "") or ""
    _roots = [p for p in ([_rd] + (extra_dirs or [])) if p and os.path.isdir(p)]
    if not _roots or not ts:
        return True
    _skip_names = {"token_usage.jsonl", ".task_state.json", "task_plan.md"}
    for _root in _roots:
        _targets = []
        for _sub in ("figures", "scripts", "results", "data", "datasets"):
            _p = os.path.join(_root, _sub)
            if os.path.isdir(_p):
                try:
                    _targets.extend(os.path.join(_p, f) for f in os.listdir(_p))
                except Exception:
                    pass
        try:
            _targets.extend(os.path.join(_root, f) for f in os.listdir(_root))
        except Exception:
            pass
        _seen = 0
        for _f in _targets:
            try:
                _base = os.path.basename(_f)
                if _base in _skip_names or ".loopx" in _f or os.sep + "log" in _f:
                    continue
                _seen += 1
                if _seen > 200:
                    break
                # 2026-08-22: 产物必须非空（0 字节不算交付产物，空文件视为未完成）
                if os.path.isfile(_f) and os.path.getmtime(_f) >= ts \
                        and os.path.getsize(_f) > 0:
                    return True
            except Exception:
                pass
    return False


def _task_class(results_dir: str) -> str:
    """当前任务类型：normal（默认，画图/轻量分析）| long_running（长任务管线）。

    运行时证据（后台进程/管线启动/cron 心跳）自动升级为 long_running。
    """
    if not results_dir:
        return "normal"
    try:
        from webui.runtime.run_gate import get_task_class
        return get_task_class(results_dir)
    except Exception:
        return "normal"


def _mark_task_long_running(session) -> None:
    """运行时证据 → 任务类型升级 long_running（幂等，不改变 state/reason）。"""
    try:
        from webui.runtime.run_gate import get_task_class, set_task_class
        _rd = session.get("results_dir", "") or ""
        if _rd and get_task_class(_rd) != "long_running":
            set_task_class(_rd, "long_running")
            logger.info("[TaskClass] session %s: normal -> long_running (%s)",
                        str(session.get("id", ""))[:12], os.path.basename(_rd))
    except Exception:
        pass


# ── 任务进程证据（2026-08-16）：CPU/内存/IO 采样 + 卡死判定 ─────────────────
_TRACKED_PROC_HIST_WINDOW = 300  # 与 stall watchdog 的 5 分钟无事件阈值对齐


def _tracked_process_pids(session, live_tool: str = ""):
    """本会话当前任务的进程 PID 集合（按在飞工具类型收敛，避免误采无关进程）。

    execute_r/execute_python/execute_code → 持久内核 worker（R/Python）；
    terminal → 本会话注册的后台进程；其余工具 → 空（无进程证据，工具自身超时兜底）。
    """
    _pids = set()
    if live_tool in ("execute_r", "execute_python", "execute_code"):
        try:
            from memomics.bio_tools.execute_r import _session_task_id
            _task = _session_task_id(session.get("id") or "")
        except Exception:
            _task = session.get("id") or ""
        try:
            from tools.persistent_kernel import KERNEL_POOL
            for _w in KERNEL_POOL.worker_snapshot(task_id=_task):
                if _w.get("pid"):
                    _pids.add(int(_w["pid"]))
        except Exception:
            pass
    if live_tool == "terminal":
        try:
            from tools.process_registry import process_registry
            for _p in process_registry.list_sessions(session_key=session.get("id")):
                _pid = _p.get("pid")
                if _pid:
                    try:
                        _pids.add(int(_pid))
                    except (TypeError, ValueError):
                        pass
        except Exception:
            pass
    return _pids


def _sample_task_procs(session) -> None:
    """watchdog 每 tick 采样一次本会话任务进程（窗口 300s，供卡死判定）。"""
    try:
        from memomics.proc_stats import sample_processes
    except Exception:
        return
    _now = time.time()
    _hist = session.setdefault("_proc_hist", [])
    _pids = _tracked_process_pids(session, str(session.get("_live_tool") or "").strip())
    _samples = [
        (s["pid"], s["cpu_seconds"], s["io_read"] + s["io_write"], s["rss_bytes"])
        for s in sample_processes(_pids)
    ]
    _hist.append((_now, _samples))
    while _hist and _now - _hist[0][0] > _TRACKED_PROC_HIST_WINDOW:
        _hist.pop(0)
    while len(_hist) > 32:  # 防无限增长
        _hist.pop(0)


def _task_liveness(session) -> tuple:
    """区分"任务在算 / 真卡死 / 无任务"（进程级证据，2026-08-16）。

    working      = 任一追踪进程窗口内 CPU 累计时间增长 > 0.2s 或 IO 字节增长
                   （readRDS/大矩阵/训练都在推进）→ 不中断；
    frozen       = 进程存在但窗口内 CPU/IO 全部冻结（死锁/挂起）→ 唤醒 AI 诊断；
    no_task      = 没有可追踪进程（只剩模型在等网关）→ 网关挂起原逻辑。
    返回 (verdict, info)；verdict 额外有 insufficient（采样不足，继续观察）。
    """
    _hist = session.get("_proc_hist", [])
    _now = time.time()
    _pids = _tracked_process_pids(session, str(session.get("_live_tool") or "").strip())
    if not _pids:
        return ("no_task", "无内核/后台进程可追踪")
    if not _hist:
        return ("insufficient", "无采样历史")
    _last = _hist[-1][1]
    if not _last:
        return ("no_task", f"追踪进程已退出: {sorted(_pids)}")
    if len(_hist) < 2:
        return ("insufficient", "采样窗口不足，继续观察")
    _cpu_delta = 0.0
    _io_delta = 0
    _rss_mb = 0.0
    _fm = {pid: (cpu, io) for pid, cpu, io, rss in _hist[0][1]}
    for _pid, _cpu, _io, _rss in _last:
        _prev = _fm.get(_pid)
        if _prev:
            _cpu_delta = max(_cpu_delta, _cpu - _prev[0])
            _io_delta = max(_io_delta, _io - _prev[1])
        _rss_mb = max(_rss_mb, _rss / 1048576.0)
    _window = int(_now - _hist[0][0])
    if _cpu_delta > 0.2 or _io_delta > 0:
        return ("working",
                f"任务仍在计算：PID {sorted(_pids)} | 窗口 {_window}s 内 ΔCPU {_cpu_delta:.1f}s / "
                f"ΔIO {_io_delta / 1048576.0:.1f}MB | RSS {_rss_mb:.0f}MB")
    return ("frozen",
            f"任务疑似卡死：PID {sorted(_pids)} | 窗口 {_window}s 内 CPU/IO 零变化 | RSS {_rss_mb:.0f}MB")


def _schedule_self_check(session, agent, loop, trigger="turn_end"):
    """本轮结束后，如果有未完成的主线任务，延迟后自动触发下一轮自检。
    但如果 task_plan 被标记为 cancelled 或 paused，则跳过。

    trigger（2026-08 M1 事件驱动唤醒，DSH 思想迁移）：
      turn_end   — 用户/自检回合结束（默认）：按 LoopX 退避调度，兜底先查签名
      task_done  — 后台任务完成事件：3 秒内尽快唤醒（DSH jobs 结算通知语义）
      fallback   — 兜底重排：唤醒前先做便宜检查（外部工作在跑且无新进展 →
                    跳过 LLM 唤醒，只重排兜底——轮询文件系统而非轮询 LLM）
    """
    if not agent or not loop:
        return
    # 2026-08-14 P0 修复：紧急标记提前 pop——六闸门在 urgent 时不得吞掉"说而不做/心跳错误"的唤醒
    urgent = session.pop("_urgent_wakeup", False)
    force_tool = session.pop("_force_tool_check", False)
    has_todos = any(t.get("status") not in ("completed", "cancelled") 
                    for t in session.get("todos", []))
    results_dir = session.get("results_dir", "")
    # ── RunGate 退役闸门（P1-A 接线，2026-08-12）：task_state == done/cancelled
    #    → 自动唤醒一律拦截（防"唤醒→写记录→签名变→再唤醒"死循环的最终兜底）──
    try:
        from webui.runtime.run_gate import check_gate
        if results_dir:
            _verdict, _reason = check_gate(results_dir, is_auto_wake=True)
            if _verdict == "stop" and not urgent:
                logger.info(f"[SelfCheck] session {session['id'][:12]}: RunGate 拦截自动唤醒 ({_reason})")
                return
    except Exception as e:
        logger.warning(f"[SelfCheck] RunGate 检查失败(fail-open): {e}")
    has_plan = results_dir and os.path.isfile(os.path.join(results_dir, "task_plan.md"))
    if not has_todos and not has_plan:
        # 修复(2026-08-07): task_plan.md 被清/未创建但 batch 批处理仍活跃
        # （40 样本 ArchR 管线由独立脚本驱动）→ 持续监督唤醒，不静默
        # 2026-08-14: urgent 唤醒不受此闸门拦截
        if not _session_has_active_work(session) and not urgent:
            return
        # 2026-08-15 制动: 无计划/待办且外部确实无工作(无进程+15分钟无真实产出) → 停止唤醒
        if not urgent and _session_no_live_work(session):
            logger.info(f"[SelfCheck] session {session['id'][:12]}: 无计划/待办/活跃工作 → 停止唤醒（制动）")
            return
    # 🔧 任务完成 → 归档 task_plan.md + mark_done，停止自检（心跳随之关闭）
    # 判定：待办全部完成/取消 + 主线区（🏁 唤醒记录区之前）无 in_progress/pending + 出现完成标记。
    # 修复(2026-08-12)：旧版扫全文被唤醒记录里的"无 in_progress Phase"字样锁死（自写词阻止完成判定）；
    # 旧版 os.remove 丢主线文档 → 改为归档 task_plan.done.md + RunGate mark_done。
    if not has_todos and has_plan:
        _plan_path = os.path.join(results_dir, "task_plan.md")
        try:
            with open(_plan_path, "r", encoding="utf-8") as f:
                _plan_text = f.read()
            # 只统计主线任务区：唤醒记录区（## 🏁）之前；无 🏁 则全文
            _main = _plan_text.split("## 🏁")[0]
            _pt_lower = _main.lower()
            if "in_progress" not in _pt_lower and "pending" not in _pt_lower:
                # 2026-08-14 增强完成信号：不再只靠完成关键词（LLM 忘写就多唤醒烧 token），
                # 三种信号任一命中即进入完成契约校验：
                # 1) 完成关键词（旧逻辑） 2) 复选框全勾 3) 外部工作确实停了（无进程+无近期产出）
                # 2026-08-16 任务类型修复：复选框判定剔除模板 Verification Checklist 段
                # （模板遗留项与任务无关，曾卡死画图类普通任务的自动归档）。
                _main_core = _strip_template_checklist(_main)
                _core_lower = _main_core.lower()
                _has_done_word = any(m in _core_lower for m in ("completed", "closed", "完成", "已停止", "done"))
                _all_checked = ("- [x]" in _core_lower or "- [X]" in _core_lower) and "- [ ]" not in _core_lower
                _no_live_work = _session_no_live_work(session)
                if _has_done_word or _all_checked or _no_live_work:
                    # P0-2(2026-08-13) 完成契约：提交即校验 — 复选框全勾 + 产出文件存在且非空。
                    # 契约未满足 → 不归档不 mark_done，继续自检（唤醒 agent 补齐）。
                    # 2026-08-14: urgent 唤醒在完成归档闸门处放行（紧急介入优先）。
                    # 2026-08-16: 普通任务且外部无活跃工作 = 确定性完成证据，
                    # 勾选框不再拦（长任务仍走严格契约）。
                    _skip_unchecked = _task_class(results_dir) == "normal" and _no_live_work
                    if not _completion_contract_check(_main, results_dir, skip_unchecked=_skip_unchecked):
                        logger.info(f"[SelfCheck] session {session['id'][:12]}: 词法判定完成但完成契约未满足（未勾选复选框或产出文件缺失/为空）→ 继续自检")
                    elif not urgent:
                        try:
                            from webui.runtime.run_gate import mark_done
                            mark_done(results_dir, "task completed (self-check)")
                        except Exception:
                            pass
                        try:
                            _done_path = os.path.join(results_dir, "task_plan.done.md")
                            if os.path.exists(_done_path):
                                os.remove(_done_path)
                            os.rename(_plan_path, _done_path)
                        except Exception:
                            try:
                                os.remove(_plan_path)
                            except Exception:
                                pass
                        logger.info(f"[SelfCheck] session {session['id'][:12]}: 任务完成，已归档 task_plan.done.md + mark_done，停止自检（心跳关闭）")
                        return
        except Exception:
            pass
    # ⛔ 检查 task_plan 是否被取消/暂停
    if has_plan:
        try:
            with open(os.path.join(results_dir, "task_plan.md"), "r", encoding="utf-8") as f:
                plan_text = f.read()
            if "cancelled" in plan_text.lower() or "**Status:** paused" in plan_text or "**Status:** closed" in plan_text.lower() or "🔒 CLOSED" in plan_text or "已停止" in plan_text or "停止" in plan_text and "task_plan" in plan_text.lower():
                logger.info(f"[SelfCheck] session {session['id'][:12]}: task_plan is cancelled/paused/closed, skipping self-check")
                return
        except Exception:
            pass
    # ── LoopX 融合（2026-08-07）：quota 状态机决定"该不该继续唤醒" ──
    # 注意：LoopX quota 深度绑定 Codex 工作项模型（无 Codex 工作 → waiting/skip），
    # MemOmics 无 Codex 工作项，waiting/operator_gate 类判定不适用——只尊重
    # 明确硬停止状态（blocked/paused/throttled 等 BLOCKED_QUOTA_STATES 子集）；
    # 其余（waiting/operator_gate/eligible）继续唤醒（MemOmics 交互式轻量监督）。
    try:
        from memomics.loopx_bridge import LoopXBridge
        _rd2 = session.get("results_dir", "") or ""
        if _rd2:
            _bridge = LoopXBridge(session["id"], _rd2, user_online=True)
            _dec = _bridge.should_run()
            _state = str(_dec.get("state") or "")
            _HARD_STOP = {"blocked", "blocked_health", "paused", "throttled"}
            if not _dec.get("should_run") and _state in _HARD_STOP and not urgent:
                _reason = str(_dec.get("reason") or "loopx quota 判定停止")[:80]
                logger.info(f"[SelfCheck] session {session['id'][:12]}: LoopX {_state} 停止唤醒 ({_reason})")
                return
    except Exception as e:
        logger.warning(f"[SelfCheck] LoopX 检查失败(fail-open): {e}")
    _sc = session.setdefault("_self_check_count", 0)
    # 修复(2026-08-07): 原上限 20 次 ≈ 40 分钟，长任务（40 样本管线）监督窗口耗尽后
    # 永久静默。改为"无进展才累计"：监督目录有进展（样本日志在写/task_plan 更新）
    # → 重置计数持续唤醒；真卡死（20 轮无进展）→ 停止，防无限烧 token。
    try:
        _sig = _session_progress_signature(session)
        if _sig > session.get("_self_check_last_sig", 0.0):
            _sc = 0
        session["_self_check_last_sig"] = _sig
    except Exception:
        pass
    if _sc >= 20 and not urgent:
        return
    # 2026-08-14: urgent 唤醒重置无进展计数（紧急介入不被"20 轮无进展"拦住）
    if urgent:
        _sc = 0
    session["_self_check_count"] = _sc + 1
    sid = session["id"]
    
    # 🔧 动态延迟：根据当前 in_progress 待办的预估时间
    delay = _calc_self_check_delay(session)
    # urgent 已在函数开头 pop：紧急唤醒 3 秒
    if urgent:
        delay = 3  # 3秒后立即唤醒
        logger.info(f"[SelfCheck] session {sid[:12]}: urgent wakeup triggered")
    elif trigger == "task_done":
        # M1: 后台任务完成事件 → 尽快唤醒（DSH jobs 结算通知语义）
        delay = 3
        logger.info(f"[SelfCheck] session {sid[:12]}: task-done wakeup triggered")
    
    async def _wakeup():
        await asyncio.sleep(delay)
        try:
            if sid not in _sessions: return
            s = _sessions[sid]
            if s.get("running_agent") or s.get("running_task") or s.get("_user_turn_active"):
                # 2026-08-16: 冻结分支已直接武装诊断回合 → 本唤醒不重排（防双发）
                # 2026-08-20: 用户回合进行中(_user_turn_active)同等视为忙——避免自检
                # 唤醒与用户回合在同一 agent 上并发交错流, 把工具参数流截断成空
                if s.get("_stall_wake_active"):
                    return
                # 2026-08-14 P0: 早退重排——被并发回合吞掉的唤醒重新调度（最多 3 次）
                _retry_n = s.setdefault("_wakeup_retry_n", 0)
                if _retry_n < 3:
                    s["_wakeup_retry_n"] = _retry_n + 1
                    s["_urgent_wakeup"] = True
                    logger.info(f"[SelfCheck] session {sid[:12]}: 唤醒遇运行中回合，重排 #{_retry_n + 1}/3")
                    _schedule_self_check(s, agent, loop, trigger=trigger)
                else:
                    s.pop("_wakeup_retry_n", None)
                return
            # ── M1 兜底闸门：外部工作在跑且无新进展 → 不唤醒 LLM，只重排兜底 ──
            # （省 token 的关键：轮询文件系统/进程表，而不是轮询 LLM；
            #   DSH"无产出就不唤醒"的落地）
            if trigger in ("turn_end", "fallback") and not urgent and not force_tool:
                try:
                    _sig_now = _session_progress_signature(s)
                    # 注意：签名是 hash%2^31 的不透明值，非单调——"有变化"必须用 != 判定
                    # （<= 会把哈希值变小误判为"无进展"→ 外部工作永远不唤醒 LLM）
                    if _sig_now == s.get("_self_check_last_sig", 0.0) and _session_has_external_work(s):
                        # 等待外部工作不算无进展：计数清零，重排兜底
                        s["_self_check_count"] = 0
                        logger.info(f"[SelfCheck] session {sid[:12]}: M1 兜底跳过（外部工作活跃且无新进展）→ 重排，不唤醒 LLM")
                        _schedule_self_check(s, agent, loop, trigger="fallback")
                        return
                except Exception:
                    pass
            # ── M3 硬轮数预算：真正注入唤醒才 +1（DSH roundsStarted 语义）──
            try:
                from webui.runtime.run_gate import admit_round
                _rd_b = s.get("results_dir", "") or ""
                # 无任务目录或预算耗尽/任务退役 → 一律不注入
                # （极端测试修复：原 `if _rd_b and not admit_round(...)` 在
                #   results_dir 为空时整个跳过检查 → 无任务会话也会唤醒 LLM）
                if not _rd_b or not admit_round(_rd_b):
                    logger.info(f"[SelfCheck] session {sid[:12]}: 轮数预算耗尽/无任务目录/任务退役，停止注入唤醒")
                    return
            except Exception:
                pass
            # 判断唤醒类型
            todos = s.get("todos", [])
            in_progress = [t for t in todos if t.get("status") == "in_progress"]
            waiting_review = [t for t in todos if t.get("status") == "waiting_review"]
            
            # ── LoopX 融合（2026-08-07）：心跳汇报带结构化状态（goal/todo/quota）──
            _loopx_ctx = ""
            try:
                from memomics.loopx_bridge import LoopXBridge
                _lrd = s.get("results_dir", "") or ""
                if _lrd:
                    _lctx = LoopXBridge(sid, _lrd, user_online=True).heartbeat_prompt(mode="compact")
                    if _lctx:
                        _loopx_ctx = f"📊 LoopX 状态：\n{_lctx}\n\n"
            except Exception:
                pass
            if waiting_review:
                wake_msg = (
                    _loopx_ctx +
                    f"⏰ [系统唤醒 #{_sc}] 有待审阅任务！\n"
                    f"以下步骤已完成，等待辩论/审查：\n" +
                    "\n".join(f"  - {t.get('title','')[:60]}" for t in waiting_review[:5]) +
                    "\n\n请立即：\n"
                    "1. 检查产出文件质量\n"
                    "2. 执行 debate_analysis() 辩论\n"
                    "3. 执行 rail_review(phase='post') 审查\n"
                    "4. 通过→标记 completed，继续下一步\n"
                    "5. 不通过→修复→重跑"
                )
            elif in_progress:
                titles = ", ".join(t.get("title","")[:40] for t in in_progress[:3])
                wake_msg = (
                    _loopx_ctx +
                    f"⏰ [系统唤醒 #{_sc}] 主线任务进行中: {titles}\n"
                    "请执行以下检查：\n"
                    "1. process(action='list') 检查后台进程\n"
                    "2. process(action='poll') 查每个进程状态和日志\n"
                    "3. search_files 看 results_dir 最新产出\n"
                    "4. 报错→读日志分析原因→修复→重试\n"
                    "5. 完成→标记 completed，启动下一步\n"
                    "6. 需要审查→标记 waiting_review"
                )
            else:
                # 2026-08-26: 无进行中/待审任务时，仅当 task_plan.md 真实存在才唤醒
                # 检查进度——否则任务已完成（plan 归档为 task_plan.done.md）的会话会被
                # 无限「检查主线任务进度」唤醒空转（实测：memomics-cd677556 任务完成后
                # 唤醒 #5/#6 继续注入 → 模型反复读不存在的 plan → 5 分钟无输出被看门狗
                # 中断；LoopX goal:active 为残留状态误导）
                _plan_p = os.path.join(s.get("results_dir", ""), "task_plan.md") if s.get("results_dir") else ""
                if not (_plan_p and os.path.isfile(_plan_p)):
                    logger.info(f"[SelfCheck] session {sid[:12]}: 无活跃 task_plan（任务已完成/退役），跳过无任务唤醒")
                    return
                # 2026-08-27 最后防线：task_plan 文本已标完成（_plan_is_complete_text，
                # 整体级信号）→ 即使 task_state 被误重置 pending，也不注入唤醒——
                # 已完成任务直接休息，等用户明确的新指令（实测：ask_user 否定回答曾复活
                # done 任务 → 模型被反复叫醒重复输出同一回答 4 次）
                try:
                    with open(_plan_p, "r", encoding="utf-8") as _pf:
                        _ptext = _pf.read()
                    if _plan_is_complete_text(_ptext):
                        logger.info(f"[SelfCheck] session {sid[:12]}: task_plan 已标完成 → 休息，不唤醒")
                        return
                except Exception:
                    pass
                wake_msg = (
                    _loopx_ctx +
                    f"⏰ [系统唤醒 #{_sc}] 检查主线任务进度\n"
                    "1. 读 task_plan.md 看当前 Phase\n"
                    "2. search_files 看最新产出\n"
                    "3. 继续执行下一个待办"
                )
            # 2026-08-14: 唤醒成功——重排计数清零
            s.pop("_wakeup_retry_n", None)
            # 2026-08-16 任务卡死诊断：watchdog 冻结判定留下的诊断指令优先注入
            _stall_diag = s.pop("_stall_diag", None)
            if _stall_diag:
                wake_msg = _stall_diag + "\n\n" + wake_msg
            _force_prefix = "⛔ 强制工具调用（系统要求）：本轮必须先调用工具实际执行，禁止纯文本回复！\n\n" if force_tool else ""
            s.setdefault("messages", []).append(
                {"role": "system", "content": _force_prefix + wake_msg + "\n\n⛔ 工具优先！直接调工具，禁止只说'马上查'而不行动！", "time": datetime.now().strftime("%H:%M:%S"), "source": "self_check"})
            s["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await _trigger_agent_turn(s, wake_msg)
        except Exception as e:
            logger.warning(f"[SelfCheck] _wakeup 异常: {e}")
    
    # 使用传入的 event loop 调度，确保在正确的线程上执行
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(_wakeup(), loop)
    else:
        asyncio.ensure_future(_wakeup())


def _session_progress_signature(session):
    """会话进展签名：task_plan.md 主线区内容哈希 + batch/logs 最新日志 mtime。

    长任务监督用（修复 2026-08-07）：自检计数据此重置——
    样本日志持续写入（Rscript 输出）或 agent 更新主线区 → 签名变化
    → 有进展的长任务（如 40 样本 ArchR 管线）持续唤醒；
    真卡死（日志/计划都停更）→ 签名不变 → 20 轮后停止，防无限烧 token。

    修复(2026-08-12)：task_plan 用"主线区内容哈希"代替文件 mtime——
    agent 每次唤醒都向 🏁 唤醒记录区追加记录（改 mtime 但主线区不变），
    旧版 mtime 导致"唤醒→写记录→签名变→计数清零→再唤醒"自食其果死循环。
    """
    _sig = 0.0
    _rd = session.get("results_dir", "") or ""
    _plan = os.path.join(_rd, "task_plan.md") if _rd else ""
    if _plan and os.path.isfile(_plan):
        try:
            with open(_plan, "r", encoding="utf-8") as f:
                _text = f.read()
            # 只统计主线任务区（## 🏁 之前；无 🏁 则全文）
            _main = _text.split("## 🏁")[0]
            _sig = float(hash(_main) % (2 ** 31))
        except Exception:
            _sig = max(_sig, os.path.getmtime(_plan))
    _logs = os.path.join(_rd, "batch", "logs") if _rd else ""
    if _logs and os.path.isdir(_logs):
        try:
            _m = max(os.path.getmtime(os.path.join(_logs, f)) for f in os.listdir(_logs))
            _sig = max(_sig, _m)
        except Exception:
            pass
    return _sig


def _calc_self_check_delay(session):
    """计算下次自检延迟（秒）。

    优先 LoopX 调度退避（memomics/loopx_bridge.py，2026-08-07 接入）：
      run_now（有活干）→ 60s 勤查；backoff/waiting → 翻倍退避封顶 40min；
      normal/checkpoint → 默认。比固定延迟更省 token：没事干自动拉长间隔。
    降级（vendor 不可用/异常）→ 回退到原逻辑：in_progress 待办预估时间×0.8。
    """
    try:
        from memomics.loopx_bridge import LoopXBridge
        _rd = session.get("results_dir", "") or ""
        if _rd:
            _bridge = LoopXBridge(session["id"], _rd, user_online=True)
            _iv = _bridge.next_poll_interval(default_seconds=300)
            if isinstance(_iv, (int, float)) and _iv >= 30:
                return int(_iv)
    except Exception:
        pass
    # ── 原逻辑（降级）──
    todos = session.get("todos", [])
    for t in todos:
        if t.get("status") == "in_progress":
            est = t.get("estimated_minutes", 0)
            if isinstance(est, (int, float)) and est > 1:
                return max(30, min(900, int(est * 60 * 0.8)))  # 80% of estimate, 30s-15min
    return 300  # default 5 min


def _build_self_check_wake_history(session):
    """自检唤醒精简上下文（2026-08-14 成本优化 + 2026-08-22 缓存优化）。

    之前每次唤醒走 agent 内部全量对话历史（实测 67K input tokens/次，
    占全部 token 消耗 66%）。改为只带：
    1) 最近一条用户消息（原始诉求）
    2) 最近一条助手回复（上次做到哪）
    3) task_plan.md 主线区摘要（含 Goal/Phase 状态）——放**最后**（尾部）
    用户回合仍走 run_agent 的全量历史路径，不受影响。

    2026-08-22 缓存优化：task_plan 摘要是唤醒上下文里变化最频繁的部分
    （每次任务进展都重写），原实现放第 1 条 → task_plan 一更新整个唤醒
    前缀失效（实测唤醒命中率 66-76%）。改为放最后：前缀 = 最近
    user/assistant 消息（唤醒之间稳定，除非主循环跑过），task_plan 变化
    只影响尾部 → 唤醒命中率可回 95%+。
    """
    history = []
    _msgs = session.get("messages", [])
    for _m in reversed(_msgs[-10:]):
        if _m.get("role") == "user" and isinstance(_m.get("content"), str) and _m.get("content").strip():
            history.append({"role": "user", "content": _m["content"][:1000]})
            break
    for _m in reversed(_msgs[-10:]):
        if _m.get("role") == "assistant" and isinstance(_m.get("content"), str) and _m.get("content").strip():
            history.append({"role": "assistant", "content": _m["content"][:2000]})
            break
    # 尾部：task_plan 摘要（变化源 → 放最后，前缀固定化）
    _rd = session.get("results_dir", "") or ""
    _plan = os.path.join(_rd, "task_plan.md") if _rd else ""
    if _plan and os.path.isfile(_plan):
        try:
            with open(_plan, "r", encoding="utf-8", errors="ignore") as f:
                _text = f.read()
            _main = _text.split("## 🏁")[0]
            _lines = [l for l in _main.split("\n") if l.strip()][:80]
            if _lines:
                history.append({"role": "system", "content":
                    "[自检唤醒上下文：task_plan.md 主线区摘要（完整计划见磁盘）]\n" + "\n".join(_lines)})
        except Exception:
            pass
    # 2026-08: 数据读取配方 —— 唤醒回合没有历史/工具记录，模型最容易
    # "忘了怎么读"；把此前成功读取命令确定性带回（tool_calls_log 提取）
    try:
        _recipes = _build_read_recipes(session)
        if _recipes:
            history.append({"role": "system", "content": _recipes})
    except Exception:
        pass
    # 2026-08 L1: kernel 生命周期事件 —— 续跑前让模型知道"kernel 被回收过、
    # 变量已丢失"（与读取配方配套：知道丢了 → 知道怎么重载）
    try:
        from tools.persistent_kernel import KERNEL_POOL
        _kevs = KERNEL_POOL.kernel_events(session.get("id", ""))
        if _kevs:
            history.append({"role": "system", "content":
                "[kernel 状态提醒] 本会话 kernel 近期发生过状态丢失，此前定义的变量已不可用：\n"
                + "\n".join(f"- {e}" for e in _kevs[:4])
                + "\n如需继续使用之前加载的数据，先按上方[数据读取配方]重新加载。"})
    except Exception:
        pass
    return history


async def _trigger_agent_turn(session, message):
    """从服务端触发一轮 agent 对话（不等用户消息）。

    2026-08-16: 不再用 300s wait_for —— 长工具（大文件 readRDS/长计算）会被
    误杀且 executor 线程继续跑成孤儿。回合生命周期交给 stall watchdog
    （无工具在飞 5 分钟才中断）与工具自身超时（terminal 180s / kernel 1800s）兜底。
    """
    # 惰性加载兜底：自检唤醒也会读/写 session['messages']
    _ensure_session_messages_loaded(session)
    agent = session.get("agent")
    if not agent:
        # 2026-08-14 P0: agent 为 None 时重建（会话恢复后 agent 可能被清理）
        try:
            logger.info(f"[SelfCheck] session {session['id'][:12]}: agent 为 None，重建")
            agent = _create_agent(session.get("model_config") or {}, session_id=session["id"], session=session)
            session["agent"] = agent
        except Exception as e:
            logger.warning(f"[SelfCheck] 重建 agent 失败: {e}")
            _session_emit(session, {"type": "error", "content": f"系统唤醒失败（agent 不可用）: {e}", "session_id": session["id"]})
            return
    try:
        if getattr(agent, "_interrupt_requested", False):
            agent.clear_interrupt()
        session["running_agent"] = agent
        # 修复(2026-08-07): 立即 emit 事件刷新 _last_event_ts —— 否则 stall watchdog
        # 用很久前的最后事件时间判定"5分钟无事件"→ 误杀刚启动的唤醒回合
        # （实测：唤醒回合 4.9s 就被 interrupt "waiting for model response"）。
        _session_emit(session, {"type": "thinking", "content": "⏰ 系统唤醒中...", "session_id": session["id"]})
        # 2026-08-14: 自检唤醒回合的运行基线（与主回合一致）
        session["_turn_start_ts"] = time.time()
        session["_api_calls"] = 0
        session["_live_tool"] = ""
        session["_live_tool_ts"] = time.time()
        session["_proc_hist"] = []  # 2026-08-16: 进程采样历史（回合级窗口）
        session["_stall_notice_last"] = 0
        loop = asyncio.get_event_loop()
        def _run():
            # P1-13(2026-08-13): 自检唤醒 executor 线程内设置会话上下文（kernel 会话隔离）
            try:
                from memomics.bio_tools.debate_analysis import set_session_context
                _set_debate_session_context(session)
            except Exception:
                pass
            # 2026-08-14 成本优化：唤醒用精简上下文（task_plan 摘要 + 最近用户/助手消息），
            # 不带全量历史（67K input/次 → ~4K）
            _wake_history = _build_self_check_wake_history(session)
            # 2026-08-31: 自检唤醒不再把 [会话要求…] 脚手架拼进用户消息（否则被持久化成
            # 大量 user 消息 → 模型每轮当成新问题重复回答，实证 870 条）。
            # 改为：digest 走 system 尾巴；唤醒文本加 [系统唤醒] 前缀由显示/卫生层过滤。
            _whist = list(_wake_history or [])
            try:
                _wdigest = _build_memory_digest(session, message)
                if _wdigest:
                    _whist.append({"role": "system", "content": _wdigest})
            except Exception:
                pass
            _wake_msg = ("[系统唤醒] " + str(message or "")).strip()
            return agent.run_conversation(_wake_msg, conversation_history=_whist or None, task_id=session["id"])
        # 2026-08-16: 去 wait_for —— 让长工具自然跑完；网关挂起由 stall watchdog 中断
        result = await loop.run_in_executor(None, _run)
        final = result.get("final_response", "") if isinstance(result, dict) else str(result)
        # 2026-08-31: 自检回合输出加 [系统唤醒] 前缀 → 前端按注入消息过滤，不再刷屏成“重复回答”；
        # 关键信息仍由 _build_memory_digest 以 system 尾注入（不会丢）。
        _wake_out = ("[系统唤醒] " + final) if final else final
        session.setdefault("messages", []).append(
            {"role": "assistant", "content": _wake_out, "time": datetime.now().strftime("%H:%M:%S"), "source": "self_check"})
        _session_emit(session, {"type": "complete", "content": _wake_out[:200], "session_id": session["id"]})
        # 2026-08-16: 自检回合同样检测"说而不做"（此前只覆盖用户回合；
        # 虚假完成检测依赖回合级 _real_exec_this_turn 接线，自检回合无，只做承诺检测）
        if _detect_action_promise(final, []):
            _wake_n = session.get("_saying_wakeup_n", 0)
            if _wake_n < 2:
                session["_saying_wakeup_n"] = _wake_n + 1
                session["_urgent_wakeup"] = True
                session["_force_tool_check"] = True
                logger.info("[MemOmics] 自检回合检测到说而不做 → 立即强制重跑 (#%d/2)", _wake_n + 1)
    except asyncio.TimeoutError:
        _session_emit(session, {"type": "timeout", "content": "自检超时(5分钟)", "session_id": session["id"]})
    except Exception as e:
        pass
    finally:
        session["running_agent"] = None
        session["running_task"] = None
        # ── LoopX 执行层（2026-08-07）：回合交付记录 → cadence 退避真实生效 ──
        try:
            from memomics.loopx_bridge import LoopXBridge
            _rd = session.get("results_dir", "") or ""
            if _rd:
                _final = locals().get("final", "") or ""
                _outcome = "primary_goal_outcome" if _final and "completed" in str(_final).lower() else "outcome_progress"
                LoopXBridge(session["id"], _rd, user_online=True).record_turn_delivery(
                    outcome=_outcome,
                    summary=str(_final)[:150],
                    model=(session.get("model_config") or {}).get("model", ""),
                )
        except Exception:
            pass
        # ── token 消耗持久化（2026-08-07）：回合级追加写入 token_usage.jsonl，永不覆盖 ──
        try:
            _persist_token_usage(session, turn_kind="self_check")
        except Exception:
            pass
        _schedule_self_check(session, agent, asyncio.get_event_loop(), trigger="turn_end")
        # 2026-08-25: 回合结束刷新产出资产索引（供 digest 跨轮复用）
        try:
            _save_assets_index(session)
        except Exception:
            pass


def _build_alerts_context(session):
    """读取 analysis_dir 下的 alerts.json，注入未处理错误摘要。"""
    analysis_dir = session.get("analysis_dir", "")
    if not analysis_dir:
        return None
    alerts_path = os.path.join(analysis_dir, "alerts.json")
    if not os.path.isfile(alerts_path):
        return None
    # 归属校验：共享 analysis_dir 时其他会话的告警不得注入本会话
    if not _marker_belongs_to_session(alerts_path, session):
        return None
    try:
        import json
        with open(alerts_path, "r", encoding="utf-8") as f:
            alerts = json.load(f)
    except Exception:
        return None
    if not alerts:
        return None
    # 只取最近 3 条未处理的高优先级错误
    unhandled = [a for a in alerts if not a.get("handled") and a.get("urgency") == "HIGH"]
    if not unhandled:
        unhandled = alerts[:3]
    if not unhandled:
        return None
    lines = ["⚠️ 磁盘上有未处理的错误 (alerts.json):"]
    for a in unhandled[:3]:
        lines.append(f"- [{a.get('ts','?')}] {a.get('type','?')}: {a.get('msg','?')[:120]}")
        if a.get("auto_fix"):
            lines.append(f"  可自动修复: {a.get('fix','')[:100]}")
    lines.append("请处理或回复'忽略'跳过。")
    return "\n".join(lines)


def _build_task_plan_context(session):
    """读取 task_plan.md 并提取状态摘要，注入到每轮对话中。"""
    results_dir = session.get("results_dir", "")
    if not results_dir:
        return None
    plan_path = os.path.join(results_dir, "task_plan.md")

    _intent = session.get("intent", "")
    _is_analysis = _intent not in ("", "chat", "self_intro", "knowledge_ask", "progress_check", "result_check")
    _has_messages = len(session.get("messages", [])) >= 2

    if not os.path.isfile(plan_path):
        # 🔑 自动创建 task_plan.md 的严格条件：
        # ① 有数据路径 ② 有执行关键词 ③ 意图不是轻量类型
        _msgs = session.get("messages", [])
        _last_msg = _msgs[-1].get("content", "") if _msgs else ""
        # 2026-08-25 链路审计：grill 场景（执行请求+关键信息缺失）→ 先问清楚再建 plan，
        # 避免用户还没确认数据就产生"幽灵 task_plan"（会干扰 RunGate/唤醒/完成判定）
        try:
            if _build_grill_prompt(session, _last_msg, _intent):
                return None
        except Exception:
            pass
        _has_data_path = bool(re.search(r'[A-Za-z]:[/\\]\S+', _last_msg))
        _has_exec_kw = any(kw in _last_msg for kw in 
                          ("跑", "执行", "开始", "启动", "运行", "run", "start", "execute", "analyze",
                           "帮我做", "帮我跑", "做分析", "跑分析"))
        _is_exec = _intent in ("analysis", "direct_exec", "research_plan")
        # 2026-08-25 修复：原引用不存在的意图 "analysis_exec"（恒 False），导致
        # 无数据路径的执行请求（"帮我做单细胞聚类分析"）永不自动创建 task_plan →
        # 任务目标没有服务器兜底，全靠模型自觉（真实会话实证：多数无 task_plan）。
        # 改用真实意图列表——执行类意图即使无路径也自动建 plan（Goal=用户原话前80字）
        # 三个条件同时满足才创建：explicit exec intent OR (data+exec keywords), AND not light intent
        _LIGHT_FOR_PLAN = ("chat", "self_intro", "knowledge_ask", "progress_check", "result_check", "analysis_plan")
        if (_is_exec or (_has_data_path and _has_exec_kw)) and _intent not in _LIGHT_FOR_PLAN and len(_msgs) >= 2:
            return _auto_create_task_plan(session, plan_path)
        return None
    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None

    # 只提取关键行：Goal、Current Phase、Phase 状态
    lines = content.split("\n")
    summary_lines = []
    in_goal = False
    in_current = False
    phase_count = 0
    for line in lines:
        stripped = line.strip()
        # Goal 段落
        if stripped.startswith("## Goal") or stripped.startswith("# Goal"):
            in_goal = True
            summary_lines.append(line)
            continue
        if in_goal:
            if stripped.startswith("##"):
                in_goal = False
            elif stripped:
                summary_lines.append(line)
                continue
        # Current Phase
        if stripped.startswith("## Current Phase"):
            in_current = True
            summary_lines.append(line)
            continue
        if in_current:
            if stripped.startswith("##"):
                in_current = False
            elif stripped:
                summary_lines.append(line)
                continue
        # Phase 状态行（只取标题和 Status）
        if stripped.startswith("### Phase"):
            phase_count += 1
            summary_lines.append(line)
            continue
        if stripped.startswith("**Status:**"):
            summary_lines.append(line)
            continue

    if not summary_lines:
        return None

    summary = "\n".join(summary_lines)
    return (
        "[SYSTEM] 以下是磁盘上 task_plan.md 的当前状态摘要。"
        "你正在进行一个长任务，上下文可能已被压缩，"
        "请以此文件为准恢复当前进度：\n\n"
        + summary
        + "\n\n⛔ 不要重新执行已标记 complete 的 Phase。"
        "先从 Current Phase 的 pending/in_progress 项继续。"
    )

# === 全局状态 ===
_sessions = {}       # session_id -> {id, title, created, messages, model_config, results_dir, todos, agent}

# === P2-1 入口中间件：把「会话是否存在」注入会话守卫 ===
# 守卫拿到 False 且开了 MEMOMICS_MW_SESSION_ENFORCE 才会拦；任何异常都放行，
# 绝不因为中间件把人挡在门外（fail-open）。
if _entry_mw is not None:
    try:
        _entry_mw.configure(session_exists=lambda _sid: bool(_sid) and _sid in _sessions)
    except Exception:
        pass

# === P2-2 显式 ThreadState（2026-09-23）：把「一个会话的活状态」从裸字典键收进显式对象 ===
# 体检实测：会话字典上 95 个隐式键、207 个写入点、499 个读取点，没有 schema、没有锁；
# 全文件仅 2 把锁且都不护会话状态，而 308 个同步 handler 跑在线程池里（约 40 线程）。
# 唯一被当"并发护栏"的 session["_user_turn_active"] 只有 1 个读取点（自检/心跳忙判定），
# 用户第二条消息进来根本不看它 → 同一会话可以两个回合同时在飞。
# 本层默认**只记账**：不发事件、不阻塞、不改任何返回值；重叠回合被计成 conflicts，
# 可在 GET /api/middleware/audit 的 threads 字段观察。要真拦并发见 MEMOMICS_THREAD_SERIALIZE。
_thread_state = None
_THREAD_STATE_INSTALLED = False
try:
    try:
        from webui import thread_state as _thread_state
    except ImportError:
        import thread_state as _thread_state
    _THREAD_STATE_INSTALLED = True
except Exception as _ts_err:  # 环境异常绝不影响主流程（fail-open）
    print("[WARN] ThreadState 未挂载: %s" % _ts_err)

# === P2-3b 出网闸门（2026-09-23）：WebUI 自己发起的出网请求统一从这里走 ===
# 默认观察模式：判定照算、账照记，但请求仍走老路径，行为零变更；要真拦见 MEMOMICS_SANDBOX_ENFORCE。
# 强制模式下钉住批准的 IP 再连（防 DNS rebinding 的那道 TOCTOU 缝），重定向逐跳重新过门。
_net_guard = None
try:
    try:
        from webui import netguard as _net_guard
    except ImportError:
        import netguard as _net_guard
except Exception as _ng_err:  # 环境异常绝不影响主流程（fail-open）
    print("[WARN] NetGuard 未挂载: %s" % _ng_err)
_SERVER_STARTED_STR = datetime.now().strftime("%m-%d %H:%M")
_bg_tasks = {}       # session_id -> background task info
# === WebSocket 多连接注册表：一个浏览器连接可同时服务多个会话 ===
# 旧实现每会话单 ws_ref，switch_session 会把切走会话的 ws_ref 置 None，
# 导致切走会话的 agent 事件发不出去（表现为"另一个会话不动"）。
# 现在每个会话可挂多个 (ws, loop)，_session_emit 广播到全部，前端按
# session_id 分流缓冲（快照系统切回时重放）。
_ws_clients_by_session: dict = {}  # sid -> set[(ws, loop)]
_ws_sessions_by_ws: dict = {}      # ws -> set[sid]（断开时反向清理）
_current_model = {   # 默认模型配置 (打包后为空, 首次启动配置)
    "provider": "openai",
    "base_url": os.environ.get("MEMOMICS_BASE_URL", ""),
    "api_key": os.environ.get("MEMOMICS_API_KEY", ""),
    "model": os.environ.get("MEMOMICS_MODEL", ""),
}

# === 模型配置持久化 ===
_MODEL_CONFIG_FILE = os.path.join(HERMES_HOME_DIR, "model_config.json")

def _atomic_write_json(path: str, obj) -> None:
    """原子写 JSON：临时文件 + fsync + os.replace，避免进程中止留下半个文件"""
    tmp = os.path.join(os.path.dirname(path) or ".", f".{os.path.basename(path)}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def _save_model_config():
    """保存当前模型配置到文件（原子写）"""
    try:
        _atomic_write_json(_MODEL_CONFIG_FILE, _current_model)
    except Exception as e:
        print(f"[WARN] 保存模型配置失败: {e}")

def _hermes_config_read():
    """读取 Hermes 底座 config.yaml（真相源）。

    用 Hermes 自己的 load_config()（展开 env 引用、deep-merge 默认值），
    另用 read_raw_config() 判断键是否真的在磁盘上设置过。
    """
    try:
        from hermes_cli.config import load_config, read_raw_config
        return load_config() or {}, read_raw_config() or {}
    except Exception as e:
        print(f"[WARN] 读取 hermes config.yaml 失败: {e}")
        return {}, {}


def _hermes_config_write(updates: dict) -> bool:
    """原子合并写 Hermes config.yaml（用 Hermes 自己的 atomic_config_write）。"""
    try:
        from hermes_cli.config import read_raw_config, atomic_config_write, get_config_path
        cfg = read_raw_config() or {}
        cfg.update(updates)
        atomic_config_write(get_config_path(), cfg)
        return True
    except Exception as e:
        print(f"[WARN] 写入 hermes config.yaml 失败: {e}")
        return False


def _load_model_config():
    """从 Hermes 底座 config.yaml 加载模型配置（唯一真相源，修复 2026-08-08）。

    原来 MemOmics 维护自己的 model_config.json，与 Hermes 底座的 config.yaml
    各自独立 → 两套配置漂移（UI 显示 A、底座实际用 B）。现统一：
    1. config.yaml 有 api_key+api_base → 以其为准（load_config 已展开 env 引用）
    2. 没有 → 回退旧 model_config.json 并一次性迁移回写 config.yaml
    """
    global _current_model
    # ── 迁移方向（2026-08-08）：以 model_config.json 为准（用户在 UI 最近设置的
    # 实际生效配置），并回写 Hermes config.yaml —— 一次迁移后 config.yaml 成为
    # 唯一真相源，两套配置不再漂移。model_config.json 缺失时才读 config.yaml。
    _legacy = None
    if os.path.exists(_MODEL_CONFIG_FILE):
        try:
            with open(_MODEL_CONFIG_FILE, "r", encoding="utf-8") as f:
                _legacy = json.load(f)
        except Exception:
            _legacy = None
    if _legacy and _legacy.get("api_key") and _legacy.get("base_url") and _legacy.get("model"):
        for k in ("provider", "base_url", "api_key", "model"):
            if _legacy.get(k):
                _current_model[k] = _legacy[k]
        print(f"[INFO] 已加载模型配置: model={_current_model['model']}, base_url={_current_model['base_url'][:40]} (回写 Hermes config.yaml)")
        _save_model_config()
        return
    # 回退：Hermes config.yaml（load_config 会把 model 规范化为 dict:
    # {default, provider, base_url}，此处兼容两种形态）
    _full, _raw = _hermes_config_read()
    if _raw.get("api_key") and _raw.get("api_base"):
        _m = _full.get("model")
        _m_dict = _m if isinstance(_m, dict) else {}
        _model_name = _m_dict.get("default") or (None if isinstance(_m, dict) else _m)
        _model_provider = _m_dict.get("provider") or _full.get("provider")
        _model_base = _m_dict.get("base_url") or _full.get("api_base")
        _model_key = _full.get("api_key")
        if _model_name:
            _current_model["model"] = _model_name
        if _model_base:
            _current_model["base_url"] = _model_base
        if _model_key:
            _current_model["api_key"] = _model_key
        _current_model["provider"] = _model_provider or _current_model.get("provider", "openai")
        print(f"[INFO] 已从 Hermes config.yaml 加载模型配置: model={_current_model['model']}, base_url={_current_model['base_url'][:40]}")
        try:
            _atomic_write_json(_MODEL_CONFIG_FILE, _current_model)  # 镜像同步（兼容）
        except Exception:
            pass
        return
    # 回退：旧 model_config.json（一次性迁移）
    if os.path.exists(_MODEL_CONFIG_FILE):
        try:
            with open(_MODEL_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for k in ("provider", "base_url", "api_key", "model"):
                if saved.get(k):
                    _current_model[k] = saved[k]
            print(f"[INFO] 已加载旧 model_config.json（迁移回写 Hermes config.yaml）: model={_current_model['model']}")
            _hermes_config_write({
                "provider": _current_model["provider"],
                "api_base": _current_model["base_url"],
                "api_key": _current_model["api_key"],
                "model": _current_model["model"],
            })
        except Exception as e:
            print(f"[WARN] 加载模型配置失败: {e}")


def _save_model_config():
    """写 Hermes config.yaml（真相源）+ 镜像 model_config.json（兼容旧读取方）。"""
    _hermes_config_write({
        "provider": _current_model.get("provider", "openai"),
        "api_base": _current_model.get("base_url", ""),
        "api_key": _current_model.get("api_key", ""),
        "model": _current_model.get("model", ""),
    })
    try:
        _atomic_write_json(_MODEL_CONFIG_FILE, _current_model)
    except Exception:
        pass

# 启动时加载
_load_model_config()

# === 任务账本 + 资源治理（借鉴重构版：JobStore/TaskSupervisor/ResourceScheduler）===
try:
    from webui.runtime import JobStore, TaskSupervisor, ResourceScheduler, ResourceCapacity
except ImportError:
    from runtime import JobStore, TaskSupervisor, ResourceScheduler, ResourceCapacity

_job_store = JobStore(os.path.join(HERMES_HOME_DIR, "runtime", "jobs.json"))
_task_supervisor = TaskSupervisor(store=_job_store)
_resource_scheduler = ResourceScheduler(ResourceCapacity.detect())


def _on_supervised_task_done(record):
    """M1（事件驱动唤醒）：后台任务完成 → 立即调度唤醒。

    label == agent_conversation 的回合任务已由 run_agent finally 自行调度
    （_schedule_self_check at turn end），此处只处理真正的后台任务，
    避免"回合结束 → 3 秒后必再醒一轮"的双触发。
    """
    try:
        if not record or record.get("label") == "agent_conversation":
            return
        _sid2 = record.get("session_id", "")
        _s2 = _sessions.get(_sid2)
        if not _s2 or not _s2.get("agent"):
            return
        _schedule_self_check(_s2, _s2["agent"], asyncio.get_event_loop(), trigger="task_done")
    except Exception:
        logger.warning("[SelfCheck] supervised-task done 唤醒失败", exc_info=True)


_task_supervisor.add_done_listener(_on_supervised_task_done)


def _session_resource_request(session):
    """会话资源配额（默认 1 核 / 2 GB / 0 GPU，宽松满足）"""
    try:
        from webui.runtime import ResourceRequest
    except ImportError:
        from runtime import ResourceRequest
    cfg = session.get("resource_request") or {}
    try:
        return ResourceRequest(
            cpu_cores=max(1, int(cfg.get("cpu_cores", 1))),
            memory_gb=max(0.5, float(cfg.get("memory_gb", 2.0))),
            gpu_slots=max(0, int(cfg.get("gpu_slots", 0))),
        )
    except (TypeError, ValueError):
        return ResourceRequest()


def _queue_label(session):
    """资源队列里显示"谁在排队"：会话标题优先，退而求其次用最近一句用户话。"""
    try:
        title = str(session.get("title") or "").strip()
        if title and title not in ("新会话", "New Chat"):
            return title[:60]
        for m in reversed(session.get("messages") or []):
            if isinstance(m, dict) and m.get("role") == "user":
                txt = " ".join(str(m.get("content") or "").split())
                if txt:
                    return txt[:60]
    except Exception:
        pass
    return ""


def _register_job_limits(session, req):
    """把 Job Object 硬限制注入会话 terminal 环境（不碰全局 os.environ）"""
    try:
        from tools.terminal_tool import register_task_env_overrides
        host_cpu = max(1, os.cpu_count() or 1)
        cpu_rate = max(1, min(10000, round(req.cpu_cores / host_cpu * 10000)))
        limits = {
            "MEMOMICS_INTERNAL_JOB_SESSION_ID": session["id"],
            "MEMOMICS_INTERNAL_JOB_MEMORY_BYTES": str(int(req.memory_gb * 1024 ** 3)),
            "MEMOMICS_INTERNAL_JOB_CPU_RATE": str(cpu_rate),
        }
        register_task_env_overrides(session["id"], {"env": limits})
    except Exception as e:
        logger.warning(f"[MemOmics] job limits injection failed: {e}")


def _clear_session_running(sid):
    """按会话 id 精确清理运行状态（done_callback 用，绕过闭包变量陷阱）"""
    s = _sessions.get(sid)
    if s is not None:
        s["running_agent"] = None
        s["running_task"] = None


def _release_lease(session_id, lease):
    """任务结束后释放资源租约（线程安全，不阻塞回调）"""
    if lease is None:
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            return
        loop.create_task(_resource_scheduler.release(lease))
    except Exception:
        pass

# === 国内/国际 Provider 列表 + 热门模型 ===
# 每个 provider: id, name, api(base_url), env_var, group, models[]
_CHINA_PROVIDERS = [
    # === DCS Cloud (推荐, 一个 key 切换所有模型) ===
    {
        "id": "dcs-cloud", "name": "DCS Cloud (一个 key 切换所有模型)",
        "api": "https://dcsapi.dcs.cloud/api/aigress/unified/v1", "env_var": "DEEPSEEK_API_KEY",
        "group": "★ DCS Cloud (推荐)",
        "models": [
            {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro (旗舰 1.6T MoE)", "reasoning": True, "tool_call": True},
            {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash (快速 284B MoE)", "reasoning": True, "tool_call": True},
            {"id": "deepseek-flash", "name": "DeepSeek Flash (DCS Cloud)", "reasoning": True, "tool_call": True},
            {"id": "glm-5.2", "name": "GLM-5.2 (智谱旗舰)", "reasoning": True, "tool_call": True},
            {"id": "glm-5.1", "name": "GLM-5.1", "reasoning": True, "tool_call": True},
            {"id": "kimi-k3", "name": "Kimi K3 (月之暗面旗舰)", "reasoning": True, "tool_call": True},
            {"id": "kimi-k2.7-code", "name": "Kimi K2.7 Code (最强 Coding)", "reasoning": True, "tool_call": True},
            {"id": "kimi-k2.6", "name": "Kimi K2.6 (多模态智能体)", "reasoning": True, "tool_call": True},
            {"id": "qwen3.8-max", "name": "Qwen3.8-Max (通义旗舰)", "reasoning": True, "tool_call": True},
            {"id": "qwen3.7-max", "name": "Qwen3.7-Max (通义)", "reasoning": True, "tool_call": True},
            {"id": "MiniMax-M3", "name": "MiniMax M3 (1M 上下文 原生多模态)", "reasoning": True, "tool_call": True},
        ],
    },
    # === 聚合平台 ===
    {
        "id": "opencode-go", "name": "OpenCode Go (聚合, Reasonix 同款)",
        "api": "https://opencode.ai/zen/go/v1", "env_var": "OPENCODE_GO_API_KEY",
        "group": "聚合平台",
        "models": [
            {"id": "glm-5.2", "name": "GLM-5.2 (智谱旗舰)", "reasoning": True, "tool_call": True},
            {"id": "glm-5.1", "name": "GLM-5.1", "reasoning": True, "tool_call": True},
            {"id": "kimi-k3", "name": "Kimi K3 (旗舰)", "reasoning": True, "tool_call": True},
            {"id": "kimi-k2.7-code", "name": "Kimi K2.7 Code", "reasoning": True, "tool_call": True},
            {"id": "kimi-k2.6", "name": "Kimi K2.6", "reasoning": True, "tool_call": True},
            {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", "reasoning": True, "tool_call": True},
            {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "reasoning": True, "tool_call": True},
            {"id": "qwen3.8-max", "name": "Qwen3.8-Max (通义旗舰)", "reasoning": True, "tool_call": True},
            {"id": "mimo-v2.5-pro", "name": "MiMo V2.5 Pro (小米)", "reasoning": True, "tool_call": True},
            {"id": "mimo-v2.5", "name": "MiMo V2.5 (小米)", "reasoning": True, "tool_call": True},
        ],
    },
    {
        "id": "openrouter", "name": "OpenRouter (全球聚合)",
        "api": "https://openrouter.ai/api/v1", "env_var": "OPENROUTER_API_KEY",
        "group": "聚合平台",
        "models": [
            {"id": "openrouter/auto", "name": "Auto Router (自动路由最优模型)", "reasoning": True, "tool_call": True},
            {"id": "deepseek/deepseek-v4-pro", "name": "DeepSeek V4 Pro", "reasoning": True, "tool_call": True},
            {"id": "qwen/qwen3.8-max", "name": "Qwen3.8-Max", "reasoning": True, "tool_call": True},
            {"id": "anthropic/claude-opus-5", "name": "Claude Opus 5", "reasoning": True, "tool_call": True},
            {"id": "openai/gpt-5.6-luna-pro", "name": "GPT-5.6 Luna Pro", "reasoning": True, "tool_call": True},
            {"id": "google/gemini-3.6-flash", "name": "Gemini 3.6 Flash", "reasoning": True, "tool_call": True},
            {"id": "moonshotai/kimi-k3", "name": "Kimi K3", "reasoning": True, "tool_call": True},
            {"id": "minimax/minimax-m3", "name": "MiniMax M3", "reasoning": True, "tool_call": True},
            {"id": "x-ai/grok-4.5", "name": "Grok 4.5", "reasoning": True, "tool_call": True},
            {"id": "meta-llama/llama-4-maverick", "name": "Llama 4 Maverick (开源旗舰)", "reasoning": True, "tool_call": True},
        ],
    },
    # === 国内服务 ===
    {
        "id": "deepseek", "name": "DeepSeek (官方)",
        "api": "https://api.deepseek.com/v1", "env_var": "DEEPSEEK_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro (旗舰 1.6T MoE)", "reasoning": True, "tool_call": True},
            {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash (快速 284B MoE)", "reasoning": True, "tool_call": True},
            {"id": "deepseek-v3.2", "name": "DeepSeek V3.2 (通用)", "reasoning": False, "tool_call": True},
            {"id": "deepseek-chat", "name": "DeepSeek Chat (通用)", "reasoning": False, "tool_call": True},
            {"id": "deepseek-reasoner", "name": "DeepSeek R1 (推理)", "reasoning": True, "tool_call": True},
        ],
    },
    {
        "id": "zhipuai", "name": "智谱 AI (GLM)",
        "api": "https://open.bigmodel.cn/api/paas/v4", "env_var": "ZHIPUAI_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "glm-5.2", "name": "GLM-5.2 (旗舰 753B 1M上下文)", "reasoning": True, "tool_call": True},
            {"id": "glm-5.1", "name": "GLM-5.1 (754B MoE 198K)", "reasoning": True, "tool_call": True},
            {"id": "glm-5", "name": "GLM-5", "reasoning": True, "tool_call": True},
            {"id": "glm-4.7", "name": "GLM-4.7", "reasoning": False, "tool_call": True},
            {"id": "glm-4.7-flash", "name": "GLM-4.7-Flash (快速)", "reasoning": False, "tool_call": True},
            {"id": "glm-4-plus", "name": "GLM-4-Plus", "reasoning": False, "tool_call": True},
            {"id": "glm-4-long", "name": "GLM-4-Long (长上下文)", "reasoning": False, "tool_call": True},
            {"id": "glm-4-flash-250414", "name": "GLM-4-Flash (免费)", "reasoning": False, "tool_call": True},
        ],
    },
    {
        "id": "moonshotai-cn", "name": "月之暗面 (Kimi)",
        "api": "https://api.moonshot.cn/v1", "env_var": "MOONSHOT_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "kimi-k3", "name": "Kimi K3 (旗舰)", "reasoning": True, "tool_call": True},
            {"id": "kimi-k2.7-code", "name": "Kimi K2.7 Code (最强 Coding 256K)", "reasoning": True, "tool_call": True},
            {"id": "kimi-k2.7-code-highspeed", "name": "Kimi K2.7 Code 高速版 (180 T/s)", "reasoning": True, "tool_call": True},
            {"id": "kimi-k2.6", "name": "Kimi K2.6 (多模态智能体 256K)", "reasoning": True, "tool_call": True},
            {"id": "kimi-k2.5", "name": "Kimi K2.5 (视觉+思考模式)", "reasoning": True, "tool_call": True},
            {"id": "moonshot-v1-128k", "name": "Moonshot V1 128K (通用)", "reasoning": False, "tool_call": True},
            {"id": "moonshot-v1-32k", "name": "Moonshot V1 32K (通用)", "reasoning": False, "tool_call": True},
        ],
    },
    {
        "id": "alibaba-cn", "name": "阿里通义千问 (DashScope)",
        "api": "https://dashscope.aliyuncs.com/compatible-mode/v1", "env_var": "DASHSCOPE_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "qwen3.8-max", "name": "Qwen3.8-Max (最新旗舰 1M 上下文)", "reasoning": True, "tool_call": True},
            {"id": "qwen3.7-max", "name": "Qwen3.7-Max (旗舰)", "reasoning": True, "tool_call": True},
            {"id": "qwen3.7-plus", "name": "Qwen3.7-Plus", "reasoning": True, "tool_call": True},
            {"id": "qwen3.7-flash", "name": "Qwen3.7-Flash (视觉推理)", "reasoning": True, "tool_call": True},
            {"id": "qwen3.6-flash", "name": "Qwen3.6-Flash", "reasoning": True, "tool_call": True},
            {"id": "qwen3.5-omni-plus", "name": "Qwen3.5-Omni-Plus (多模态)", "reasoning": False, "tool_call": True},
            {"id": "qwen-long", "name": "Qwen-Long (长上下文)", "reasoning": False, "tool_call": True},
        ],
    },
    {
        "id": "baidu", "name": "百度文心一言 (ERNIE)",
        "api": "https://qianfan.baidubce.com/v2", "env_var": "BAIDU_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "ernie-4.0-8k-latest", "name": "ERNIE 4.0 (8K)", "reasoning": False, "tool_call": True},
            {"id": "ernie-4.0-turbo-8k", "name": "ERNIE 4.0 Turbo", "reasoning": False, "tool_call": True},
            {"id": "ernie-3.5-8k", "name": "ERNIE 3.5", "reasoning": False, "tool_call": True},
            {"id": "ernie-speed-128k", "name": "ERNIE Speed (128K)", "reasoning": False, "tool_call": True},
        ],
    },
    {
        "id": "tencent", "name": "腾讯混元 (Hunyuan)",
        "api": "https://api.hunyuan.cloud.tencent.com/v1", "env_var": "HUNYUAN_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "hy3", "name": "混元 Hy3 (腾讯最新旗舰)", "reasoning": True, "tool_call": True},
            {"id": "hy3-preview", "name": "混元 Hy3 Preview", "reasoning": True, "tool_call": True},
            {"id": "hunyuan-t1", "name": "混元 T1 (深度思考)", "reasoning": True, "tool_call": True},
            {"id": "hunyuan-turbo", "name": "混元 Turbo (快速)", "reasoning": False, "tool_call": True},
        ],
    },
    {
        "id": "stepfun", "name": "阶跃星辰 (StepFun)",
        "api": "https://api.stepfun.com/v1", "env_var": "STEPFUN_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "step-3.7-flash", "name": "Step 3.7 Flash (最新)", "reasoning": True, "tool_call": True},
            {"id": "step-3.5-flash", "name": "Step 3.5 Flash", "reasoning": True, "tool_call": True},
            {"id": "step-2.5-pro", "name": "Step 2.5 Pro", "reasoning": True, "tool_call": True},
        ],
    },
    {
        "id": "lingyiwanwu", "name": "零一万物 (Yi)",
        "api": "https://api.lingyiwanwu.com/v1", "env_var": "LINGYIWANWU_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "yi-lightning", "name": "Yi-Lightning (快速旗舰)", "reasoning": False, "tool_call": True},
            {"id": "yi-large", "name": "Yi-Large", "reasoning": False, "tool_call": True},
        ],
    },
    {
        "id": "minimax-cn", "name": "MiniMax",
        "api": "https://api.minimax.chat/v1", "env_var": "MINIMAX_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "MiniMax-M3", "name": "MiniMax M3 (1M 上下文 原生多模态)", "reasoning": True, "tool_call": True},
            {"id": "MiniMax-M2.7", "name": "MiniMax M2.7", "reasoning": True, "tool_call": True},
            {"id": "MiniMax-M2.5", "name": "MiniMax M2.5", "reasoning": True, "tool_call": True},
        ],
    },
    {
        "id": "siliconflow-cn", "name": "硅基流动 (SiliconFlow)",
        "api": "https://api.siliconflow.cn/v1", "env_var": "SILICONFLOW_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "deepseek-ai/DeepSeek-V4-Pro", "name": "DeepSeek V4 Pro", "reasoning": True, "tool_call": True},
            {"id": "deepseek-ai/DeepSeek-V4-Flash", "name": "DeepSeek V4 Flash", "reasoning": True, "tool_call": True},
            {"id": "deepseek-ai/DeepSeek-V3.2", "name": "DeepSeek V3.2", "reasoning": False, "tool_call": True},
            {"id": "moonshotai/Kimi-K3", "name": "Kimi K3", "reasoning": True, "tool_call": True},
            {"id": "moonshotai/Kimi-K2.7-Code", "name": "Kimi K2.7 Code", "reasoning": True, "tool_call": True},
            {"id": "zai-org/GLM-5.2", "name": "GLM-5.2", "reasoning": True, "tool_call": True},
            {"id": "Qwen/Qwen3.8-Max", "name": "Qwen3.8-Max", "reasoning": True, "tool_call": True},
            {"id": "Qwen/Qwen3.6-35B-A3B", "name": "Qwen3.6 35B-A3B", "reasoning": True, "tool_call": True},
            {"id": "MiniMaxAI/MiniMax-M2.5", "name": "MiniMax M2.5", "reasoning": True, "tool_call": True},
            {"id": "XiaomiMiMo/MiMo-V2.5-Pro", "name": "MiMo V2.5 Pro", "reasoning": True, "tool_call": True},
            {"id": "XiaomiMiMo/MiMo-V2-Flash", "name": "MiMo V2 Flash", "reasoning": False, "tool_call": True},
        ],
    },
    {
        "id": "volcengine", "name": "火山引擎 (豆包)",
        "api": "https://ark.cn-beijing.volces.com/api/v3", "env_var": "ARK_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "doubao-1.5-pro-256k", "name": "Doubao 1.5 Pro (256K)", "reasoning": False, "tool_call": True},
            {"id": "doubao-1.5-pro-32k", "name": "Doubao 1.5 Pro (32K)", "reasoning": False, "tool_call": True},
            {"id": "doubao-1.5-lite-32k", "name": "Doubao 1.5 Lite (32K)", "reasoning": False, "tool_call": True},
            {"id": "doubao-pro-256k", "name": "Doubao Pro (256K)", "reasoning": False, "tool_call": True},
        ],
    },
    {
        "id": "iflytek", "name": "讯飞星火 (Spark)",
        "api": "https://spark-api-open.xf-yun.com/v1", "env_var": "SPARK_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "spark-v4.0", "name": "Spark V4.0", "reasoning": False, "tool_call": True},
            {"id": "generalv3.5", "name": "Spark V3.5", "reasoning": False, "tool_call": True},
            {"id": "generalv3", "name": "Spark V3.0", "reasoning": False, "tool_call": True},
        ],
    },
    {
        "id": "xiaomi-mimo", "name": "小米 MiMo",
        "api": "https://platform.xiaomi.com/api/v1", "env_var": "XIAOMI_API_KEY",
        "group": "国内服务",
        "models": [
            {"id": "mimo-v2.5-pro", "name": "MiMo V2.5 Pro", "reasoning": True, "tool_call": True},
            {"id": "mimo-v2.5", "name": "MiMo V2.5", "reasoning": True, "tool_call": True},
            {"id": "mimo-v2.5-dflash", "name": "MiMo V2.5 DFlash", "reasoning": True, "tool_call": True},
            {"id": "mimo-v2-flash", "name": "MiMo V2 Flash", "reasoning": False, "tool_call": True},
            {"id": "mimo-v2-pro", "name": "MiMo V2 Pro", "reasoning": False, "tool_call": True},
            {"id": "mimo-v2-omni", "name": "MiMo V2 Omni (多模态)", "reasoning": False, "tool_call": True},
        ],
    },
    # === 国际大厂 ===
    {
        "id": "openai", "name": "OpenAI (官方)",
        "api": "https://api.openai.com/v1", "env_var": "OPENAI_API_KEY",
        "group": "国际大厂",
        "models": [
            {"id": "gpt-5.6-luna-pro", "name": "GPT-5.6 Luna Pro (最新旗舰)", "reasoning": True, "tool_call": True},
            {"id": "gpt-5.6-luna", "name": "GPT-5.6 Luna", "reasoning": True, "tool_call": True},
            {"id": "gpt-5.6-terra-pro", "name": "GPT-5.6 Terra Pro", "reasoning": True, "tool_call": True},
            {"id": "gpt-5.6-terra", "name": "GPT-5.6 Terra", "reasoning": True, "tool_call": True},
            {"id": "gpt-5.6-sol", "name": "GPT-5.6 Sol (快速)", "reasoning": True, "tool_call": True},
            {"id": "gpt-5.4", "name": "GPT-5.4", "reasoning": True, "tool_call": True},
            {"id": "gpt-5.4-mini", "name": "GPT-5.4 Mini", "reasoning": True, "tool_call": True},
            {"id": "o4-mini", "name": "o4-mini (推理)", "reasoning": True, "tool_call": True},
        ],
    },
    {
        "id": "anthropic", "name": "Anthropic (Claude)",
        "api": "https://api.anthropic.com", "env_var": "ANTHROPIC_API_KEY",
        "group": "国际大厂",
        "models": [
            {"id": "claude-opus-5", "name": "Claude Opus 5 (最新旗舰)", "reasoning": True, "tool_call": True},
            {"id": "claude-opus-5-fast", "name": "Claude Opus 5 Fast", "reasoning": True, "tool_call": True},
            {"id": "claude-sonnet-5", "name": "Claude Sonnet 5", "reasoning": True, "tool_call": True},
            {"id": "claude-fable-5", "name": "Claude Fable 5", "reasoning": True, "tool_call": True},
            {"id": "claude-haiku-4-5", "name": "Claude Haiku 4.5 (快速)", "reasoning": False, "tool_call": True},
        ],
    },
    {
        "id": "google", "name": "Google (Gemini)",
        "api": "https://generativelanguage.googleapis.com/v1beta", "env_var": "GOOGLE_API_KEY",
        "group": "国际大厂",
        "models": [
            {"id": "gemini-3.6-flash", "name": "Gemini 3.6 Flash (最新)", "reasoning": True, "tool_call": True},
            {"id": "gemini-3.5-flash", "name": "Gemini 3.5 Flash", "reasoning": True, "tool_call": True},
            {"id": "gemini-3.5-flash-lite", "name": "Gemini 3.5 Flash-Lite", "reasoning": False, "tool_call": True},
            {"id": "gemini-3.1-pro", "name": "Gemini 3.1 Pro", "reasoning": True, "tool_call": True},
        ],
    },
    {
        "id": "xai", "name": "xAI (Grok)",
        "api": "https://api.x.ai/v1", "env_var": "XAI_API_KEY",
        "group": "国际大厂",
        "models": [
            {"id": "grok-4.5", "name": "Grok 4.5 (最新)", "reasoning": True, "tool_call": True},
            {"id": "grok-4.3", "name": "Grok 4.3", "reasoning": True, "tool_call": True},
            {"id": "grok-4", "name": "Grok 4", "reasoning": True, "tool_call": True},
        ],
    },
    {
        "id": "mistral", "name": "Mistral AI",
        "api": "https://api.mistral.ai/v1", "env_var": "MISTRAL_API_KEY",
        "group": "国际大厂",
        "models": [
            {"id": "mistral-large-2512", "name": "Mistral Large 3 (2512)", "reasoning": True, "tool_call": True},
            {"id": "mistral-medium-3-5", "name": "Mistral Medium 3.5", "reasoning": True, "tool_call": True},
            {"id": "codestral-2508", "name": "Codestral 2508 (Coding)", "reasoning": True, "tool_call": True},
        ],
    },
    {
        "id": "perplexity", "name": "Perplexity (Sonar)",
        "api": "https://api.perplexity.ai", "env_var": "PERPLEXITY_API_KEY",
        "group": "国际大厂",
        "models": [
            {"id": "sonar-pro", "name": "Sonar Pro (联网搜索)", "reasoning": False, "tool_call": True},
            {"id": "sonar-reasoning-pro", "name": "Sonar Reasoning Pro", "reasoning": True, "tool_call": True},
            {"id": "sonar", "name": "Sonar (快速)", "reasoning": False, "tool_call": True},
            {"id": "sonar-deep-research", "name": "Sonar Deep Research", "reasoning": True, "tool_call": True},
        ],
    },
    {
        "id": "groq", "name": "Groq (极速推理)",
        "api": "https://api.groq.com/openai/v1", "env_var": "GROQ_API_KEY",
        "group": "国际大厂",
        "models": [
            {"id": "llama-4-maverick", "name": "Llama 4 Maverick (开源旗舰)", "reasoning": True, "tool_call": True},
            {"id": "llama-4-scout", "name": "Llama 4 Scout (快速)", "reasoning": True, "tool_call": True},
            {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B", "reasoning": False, "tool_call": True},
        ],
    },
]
# 构建索引: provider_id -> provider dict
_PROVIDERS_INDEX = {p["id"]: p for p in _CHINA_PROVIDERS}

# === 多 Provider Key 存储 ===
_PROVIDER_KEYS_FILE = os.path.join(HERMES_HOME_DIR, "provider_keys.json")

_provider_keys = {}  # provider_id -> {api_key, base_url}

def _save_provider_keys():
    try:
        _atomic_write_json(_PROVIDER_KEYS_FILE, _provider_keys)
    except Exception as e:
        print(f"[WARN] 保存 provider keys 失败: {e}")

# 2026-09-10: 占位符 key 判定 —— 打包模板里的 YOUR_API_KEY_HERE 等绝不能被当成
# "已配置"。此前首启把占位符同步进 provider_keys.json，导致设置页显示"已保存"、
# 首次运行向导不弹、聊天直接 401（用户反馈"没有输入 API 的界面"）。
_PLACEHOLDER_KEY_TOKENS = (
    "your_api_key", "your-api-key", "yourkey", "your_key", "insert_key",
    "changeme", "change_me", "replace_me", "placeholder", "sk-xxx", "sk-xxxx",
    "api_key_here", "在这里", "请填写", "空",
)


def _is_valid_api_key(value) -> bool:
    """真实可用 key 判定：非空、非占位符、长度像样。"""
    if not isinstance(value, str):
        return False
    s = value.strip()
    if len(s) < 12:
        return False
    low = s.lower()
    if low in ("none", "null", "undefined", "todo", "xxx", "dummy", "test"):
        return False
    if low.startswith(("<", "${")):
        return False
    for tok in _PLACEHOLDER_KEY_TOKENS:
        if tok in low:
            return False
    # 全是同一个字符（如 xxxxxxxx）也不是真 key
    if len(set(s)) <= 3:
        return False
    return True


def _load_provider_keys():
    global _provider_keys
    try:
        if os.path.exists(_PROVIDER_KEYS_FILE):
            with open(_PROVIDER_KEYS_FILE, "r", encoding="utf-8") as f:
                _provider_keys = json.load(f)
        # 自愈：剔除历史被写入的占位符条目（否则设置页永远显示"已保存"）
        _dropped = [k for k, v in list(_provider_keys.items())
                    if isinstance(v, dict) and v.get("api_key") and not _is_valid_api_key(v.get("api_key"))]
        if _dropped:
            for _k in _dropped:
                _provider_keys.pop(_k, None)
            try:
                _save_provider_keys()
            except Exception:
                pass
            print(f"[MemOmics] 已清理 {len(_dropped)} 个占位符/无效 key 的 provider 条目: {_dropped}")
    except Exception:
        _provider_keys = {}

_load_provider_keys()

# === 自定义 Provider 定义存储（2026-08-27：任意 OpenAI 兼容提供商 + 自定义模型）===
# 与 provider_keys.json 分工：本文件存"定义"（名称/base_url/模型列表），key 仍走
# provider_keys.json（现有同步/联动逻辑不变）。启动时 merge 进 _PROVIDERS_INDEX。
_CUSTOM_PROVIDERS_FILE = os.path.join(HERMES_HOME_DIR, "custom_providers.json")

_custom_providers = {}  # pid -> {id, name, api, models[]}

def _load_custom_providers():
    global _custom_providers
    try:
        if os.path.exists(_CUSTOM_PROVIDERS_FILE):
            with open(_CUSTOM_PROVIDERS_FILE, "r", encoding="utf-8") as f:
                _custom_providers = json.load(f)
        for _pid, _def in _custom_providers.items():
            if isinstance(_def, dict) and _def.get("id") and _def.get("api"):
                _PROVIDERS_INDEX[_pid] = _def
    except Exception:
        _custom_providers = {}

def _save_custom_providers():
    try:
        _atomic_write_json(_CUSTOM_PROVIDERS_FILE, _custom_providers)
    except Exception as e:
        print(f"[WARN] 保存自定义 provider 失败: {e}")

_load_custom_providers()

# === 图像生成配置（image_gen_config.json，独立于 Hermes 主配置） ===
_IMAGE_GEN_CONFIG_FILE = os.path.join(HERMES_HOME_DIR, "image_gen_config.json")
_IMAGE_GEN_DEFAULTS = {
    "provider": "openai-compatible",
    "openai_compatible": {
        "base_url": "",
        "api_key": "",
        "model": "",
        "size": "1024x1024",
        "landscape_size": "2K",
        "portrait_size": "2K",
    },
    "dashscope": {
        "api_key": "",
        "model": "qwen-image-3.0",
        "size": "1024*1024",
        "landscape_size": "1280*720",
        "portrait_size": "720*1280",
    },
}

_image_gen_config: dict = {}


def _load_image_gen_config():
    global _image_gen_config
    try:
        if os.path.exists(_IMAGE_GEN_CONFIG_FILE):
            with open(_IMAGE_GEN_CONFIG_FILE, "r", encoding="utf-8") as f:
                _image_gen_config = json.load(f) or {}
    except Exception:
        _image_gen_config = {}
    if not isinstance(_image_gen_config, dict):
        _image_gen_config = {}
    for _k, _v in _IMAGE_GEN_DEFAULTS.items():
        if _k not in _image_gen_config:
            _image_gen_config[_k] = _v
        elif isinstance(_v, dict) and isinstance(_image_gen_config[_k], dict):
            for _kk, _vv in _v.items():
                _image_gen_config[_k].setdefault(_kk, _vv)
    if _image_gen_config.get("provider") not in ("openai-compatible", "dashscope"):
        _image_gen_config["provider"] = "openai-compatible"


def _save_image_gen_config():
    try:
        _atomic_write_json(_IMAGE_GEN_CONFIG_FILE, _image_gen_config)
    except Exception as e:
        print(f"[WARN] 保存图像生成配置失败: {e}")


def _sync_imagegen_provider_to_hermes():
    """把图像生成配置同步为 Hermes config.yaml 的 image_gen.provider。

    修复 2026-08-12：image_generate 工具的 check_fn
    （check_image_generation_requirements）只认 config.yaml 的 image_gen.provider
    —— 不写这里，工具永远不会被收集（check_fn 返回 False），agent 感知不到
    图像生成能力，即使设置页已保存 key。保存配置时同步一份到 config.yaml，
    与 _sync_custom_providers_to_hermes 同一范式。
    """
    try:
        from hermes_cli.config import read_raw_config, atomic_config_write, get_config_path
        provider = _image_gen_config.get("provider") or "openai-compatible"
        cfg = read_raw_config() or {}
        section = cfg.get("image_gen")
        if not isinstance(section, dict):
            section = {}
        section["provider"] = provider
        cfg["image_gen"] = section
        atomic_config_write(get_config_path(), cfg)
        logger.info(f"[MemOmics] 已同步 image_gen.provider={provider} 到 Hermes config.yaml")
    except Exception as exc:
        logger.warning(f"[WARN] 同步 image_gen.provider 到 config.yaml 失败: {exc}")


_load_image_gen_config()


def _sync_debate_env():
    """Inject API key + base_url into environ for debate_analysis independent LLM calls.
    修复(2026-08-01): 优先使用 _current_model (model_config.json 里实际配置的 provider/key,
    用户当前真正在用的模型)。此前遍历 _provider_keys 时 dcs-cloud 因 'dcs' in pid 匹配抢先注入,
    但 dcs-cloud 的 key 已失效 (401 Invalid API key), 导致 debate_analysis 连续 7 次 8/8 全失败。
    现在改为: ① 若 _current_model 有 key 直接用它 (最可靠, 用户正在用的); ② 否则遍历
    provider_keys 时跳过验证失败的 provider, 优先 deepseek 官方。
    """
    # ① 优先：当前模型配置（用户实际在用的 provider/key，已验证可用）
    if _current_model.get("api_key"):
        os.environ["DEEPSEEK_API_KEY"] = _current_model["api_key"]
        os.environ["DEEPSEEK_BASE_URL"] = _current_model.get("base_url", "").rstrip("/")
        os.environ["DEEPSEEK_MODEL"] = _current_model.get("model", "deepseek-v4-flash")
        print(f"[INFO] Debate env injected from _current_model: URL={_current_model.get('base_url','')} MODEL={_current_model.get('model','?')}")
        return
    # ② 回退：遍历 provider_keys，优先 deepseek 官方（其 key 有效），跳过 dcs-cloud（已验证 401）
    for pid, info in _provider_keys.items():
        ak = info.get("api_key", "")
        bu = info.get("base_url", "")
        # 优先 deepseek 官方；dcs-cloud 若存在但被跳过
        if ak and _is_valid_api_key(ak) and pid.lower() == "deepseek":
            os.environ["DEEPSEEK_API_KEY"] = ak
            if bu:
                os.environ["DEEPSEEK_BASE_URL"] = bu.rstrip("/")
            os.environ["DEEPSEEK_MODEL"] = _current_model.get("model", "deepseek-v4-flash")
            print(f"[INFO] Debate env injected from provider_keys (deepseek): URL={bu} MODEL={_current_model.get('model','?')}")
            return
    for pid, info in _provider_keys.items():
        ak = info.get("api_key", "")
        bu = info.get("base_url", "")
        if ak and _is_valid_api_key(ak) and ("dcs" in pid.lower() or "dcs" in bu.lower() or "deepseek" in pid.lower()):
            os.environ["DEEPSEEK_API_KEY"] = ak
            if bu:
                os.environ["DEEPSEEK_BASE_URL"] = bu.rstrip("/")
            os.environ["DEEPSEEK_MODEL"] = _current_model.get("model", "deepseek-v4-flash")
            print(f"[INFO] Debate env injected (fallback): URL={bu} MODEL={_current_model.get('model','?')}")
            return

# 启动同步：如果 _current_model 有 key 但 provider_keys 为空，
# 自动按 base_url 反查 provider 并同步 key，保证交互框下拉框能显示模型
if _is_valid_api_key(_current_model.get("api_key")) and not _provider_keys:
    _cur_base = _current_model.get("base_url", "")
    for _p in _CHINA_PROVIDERS:
        if _p["api"] == _cur_base:
            _provider_keys[_p["id"]] = {"api_key": _current_model["api_key"], "base_url": _cur_base}
            _save_provider_keys()
            print(f"[INFO] 已自动同步 provider key: {_p['id']} (从 model_config.json)")
            break

# 为 debate_analysis 等需要独立 LLM 调用的模块注入环境变量
_sync_debate_env()


def _set_debate_session_context(session, results_dir: str = None):
    """设置辩论/工具链路的会话上下文（2026-09-13）。

    除 sid/results_dir 外，把该会话「当前使用的模型配置」一并注入。
    debate_analysis 的独立 LLM 调用（含裁判）据此走「当前使用模型的提供商」，
    再在「可用提供商」之间兜底 —— 此前辩论只认 server 启动时注入一次的 DEEPSEEK_*
    env，界面换模型后仍走旧通道（judge 还被 config 写死到 opencode-go）。
    """
    try:
        from memomics.bio_tools.debate_analysis import set_session_context
        session = session or {}
        mc = session.get("model_config") or _current_model
        if not results_dir:
            results_dir = session.get("results_dir", "")
        set_session_context(sid=session.get("id", ""), results_dir=results_dir, model_config=mc)
    except Exception:
        pass

# 预设模型 (兼容旧 API, 从 _CHINA_PROVIDERS 生成)
_preset_models = []
for p in _CHINA_PROVIDERS:
    _pname = p["name"].split("(")[0].strip()
    for m in p.get("models", []):
        _preset_models.append({"id": m["id"], "name": m["name"] + " (" + _pname + ")", "provider": "openai", "provider_id": p["id"], "base_url": p["api"], "provider_name": _pname})

SKILLS_DIR = os.path.join(MEMOMICS_DIR, "skills")
KB_DIR = os.path.join(MEMOMICS_DIR, "memomics", "knowledge_base")
_lit_cache = {}  # P5: literature dedup cache { query_hash: (timestamp, results_json) }
# P6-3 路径可移植：work/results 默认就在安装目录下（解压到哪就是哪，不绑定任何开发机路径）；
# 需要把数据放到大盘/独立卷时，设置环境变量 MEMOMICS_DATA_DIR 即可（代码目录仍固定在安装位置）。
DATA_DIR = os.path.abspath(os.environ.get("MEMOMICS_DATA_DIR") or MEMOMICS_DIR)
WORK_DIR = os.path.join(DATA_DIR, "work")
RESULTS_DIR = os.path.join(DATA_DIR, "results")
# P1-4：注入可写路径白名单（沙箱 degraded 模式拦截用；可被外部 env 覆盖）
os.environ.setdefault("MEMOMICS_ALLOWED_WRITE_ROOTS", ";".join([RESULTS_DIR, _uploads_dir]))

# === 生信契约（借鉴重构版：输入检查/工作流验证/QC/参考资源注册表）===
from webui.bioinformatics import ReferenceRegistry
try:
    from webui.api.bioinformatics import create_bioinformatics_router
except ImportError:
    create_bioinformatics_router = None

_bio_reference_registry = ReferenceRegistry(
    os.path.join(HERMES_HOME_DIR, "bioinformatics", "references.json"),
    allowed_roots=[MEMOMICS_DIR, RESULTS_DIR, _uploads_dir],
)
if create_bioinformatics_router is not None:
    app.include_router(create_bioinformatics_router(_bio_reference_registry, [MEMOMICS_DIR, RESULTS_DIR, _uploads_dir]))
SOUL_PATH = os.path.join(HERMES_HOME_DIR, "SOUL.md")
SKILLS_INDEX_PATH = os.path.join(HERMES_HOME_DIR, "SKILLS_INDEX.md")
_SKILLS_INDEX_CACHE = None  # 模块级缓存：服务器启动后只读一次，所有会话共享
_SKILLS_INDEX_MTIME = None  # 缓存对应的文件 mtime，用于热更新检测

# 允许浏览的根目录
_BROWSE_ROOTS = {
    "work": WORK_DIR,
    "results": RESULTS_DIR,
}


# === 辅助函数 ===

def _read_skills_index():
    """读取技能目录 (SKILLS_INDEX.md)，作为 ephemeral_system_prompt 注入。
    预加载缓存：首次调用时读取，后续返回缓存，避免每次会话都读 27KB 文件。
    mtime 感知：SKILLS_INDEX.md 被外部修改（如 auto_register 重建）后自动重读，
    无需重启 server。SOUL.md 由 Hermes 框架从 HERMES_HOME 自动加载，此处不重复加载。"""
    global _SKILLS_INDEX_CACHE, _SKILLS_INDEX_MTIME
    try:
        cur = os.path.getmtime(SKILLS_INDEX_PATH) if os.path.isfile(SKILLS_INDEX_PATH) else -1
    except OSError:
        cur = -1
    if _SKILLS_INDEX_CACHE is None or cur != _SKILLS_INDEX_MTIME:
        if os.path.isfile(SKILLS_INDEX_PATH):
            with open(SKILLS_INDEX_PATH, encoding="utf-8") as f:
                _SKILLS_INDEX_CACHE = f.read()
        else:
            _SKILLS_INDEX_CACHE = ""
        _SKILLS_INDEX_MTIME = cur
        if cur != -1 and _SKILLS_INDEX_CACHE:
            print(f"[skills-index] reloaded ({len(_SKILLS_INDEX_CACHE)} bytes, mtime={cur})", flush=True)
    return _SKILLS_INDEX_CACHE


# RED 必触发 skill 触发词缓存（解析自 SKILLS_INDEX.md）
# 规则契约见 contracts/skill_triggers.json；规则值由
# webui/tests/test_skill_trigger_contract.py 逐条钉住（改语义必须同时改契约）。
_RED_TRIGGER_CACHE = None  # [(skill_name, [triggers...]), ...]
_RED_TRIGGER_CACHE_MTIME = None  # 缓存对应的 SKILLS_INDEX mtime：索引重建后必须重解析
# 英文多词触发词的停用词（= contracts/skill_triggers.json → matching.stopwords）
_EN_STOPWORDS = frozenset({
    "this", "that", "the", "a", "an", "for", "to", "with",
    "is", "are", "of", "and", "or", "in", "on", "my", "me",
    "i", "you", "can", "do", "does", "be", "it", "its", "as",
})
# 本地文献库豁免（批K 2026-08-16）= contracts/skill_triggers.json → exemptions.local_literature
_LOCAL_LIT_RED_EXEMPT = frozenset({
    "literature-review", "paper-summary", "paper-download",
    "paper-translate", "academic-paper-writing",
})
_LOCAL_LIT_EXEMPT_TRIGGERS = ("文献库", "文献库里", "/papers", ".pdf")
# 短 ASCII 缩写（<=3 位）必须不与其它英文字母相邻
# （= contracts/skill_triggers.json -> matching.short_ascii_boundary）
# 旧实现纯子串匹配让 science->SCI、algorithm->go、mRNA->MR、degree->DEG 全部误触发；
# 汉字/数字/空白相邻仍算命中（"做QC"、"SCI图"）。
_SHORT_ASCII_KW_MAX = 3
_SHORT_ASCII_RE_CACHE = {}


def _short_ascii_kw_re(kw_l: str):
    """短缩写触发词的正则（前后都不能紧贴英文字母），按词缓存。"""
    r = _SHORT_ASCII_RE_CACHE.get(kw_l)
    if r is None:
        r = _SHORT_ASCII_RE_CACHE[kw_l] = re.compile(
            r"(?<![a-z])%s(?![a-z])" % re.escape(kw_l))
    return r


def _short_ascii_kw_match(kw_l: str, t: str) -> bool:
    return bool(_short_ascii_kw_re(kw_l).search(t))


# CJK/ASCII 边界空白归一：中文用户写英文术语时常随手加空格（"做 QC" / "CNS 级别"），
# 而触发词写的是紧凑形式（"CNS级别"）；不归一会造成「同一句话带空格不触发」的随机漏召回。
_CJK_ASCII_GAP_RE = re.compile(
    r"(?<=[0-9A-Za-z])[ \t]+(?=[^\x00-\x7f])|(?<=[^\x00-\x7f])[ \t]+(?=[0-9A-Za-z])")


def _tighten_cjk_ascii(s: str) -> str:
    """去掉 ASCII 与中日韩字符之间的空白：'CNS 级别'→'CNS级别'，'做 QC'→'做QC'。"""
    return _CJK_ASCII_GAP_RE.sub("", s)


def _match_red_skill_hits(user_text: str) -> list:
    """解析 SKILLS_INDEX.md 中 RED 必触发行的触发词，与用户消息做匹配。
    返回命中列表（按索引顺序）：[{"name","keyword","rule"}]；空消息/无命中 → []。

    匹配语义（契约 contracts/skill_triggers.json → matching）：
      · 大小写无关；中文等无空格关键词走子串匹配（"质控" 命中 "先做质控和双细胞去除"）；
      · 含空格的英文关键词走「实词全中」——去掉停用词后每个词都要出现在
        用户消息按空格切出的词集合里（"deg analysis" 需要 deg 与 analysis 同时出现）。
        2026-09-23 P0-2 由「任一实词命中」收紧：旧规则下用户只说 analysis 就会命中
        deg-analysis / survival-analysis / power analysis 等 6 个技能（过度触发）。
      · 不用词边界（\b）判断：中文里英文词常与汉字紧贴（"做QC"、"跑DESeq2"），
        词边界会把这类真实说法判死。
      · 但纯 ASCII 且 <=3 位的缩写（SCI/GO/QC/MR/KM/DEG/PPT/EDA）额外要求前后不紧贴英文字母：
        "science" 不再命中 SCI、"algorithm" 不再命中 GO（P0-2b 极端测试实抓）。
    缓存绑定 SKILLS_INDEX mtime（P0-2 修复：旧实现只在 None 时构建一次，
    索引被 auto_register/技能编辑重建后仍用旧触发词，新技能永远匹配不到）。

    P0-3（2026-09-23）：在原有匹配之上只多记一件事——「为什么命中」：
    keyword = 索引里真实存在的那条触发词，rule = 命中所走的规则名
    （substring / cjk-gap / short-ascii / multiword）。_match_red_skill_triggers 是本函数的
    名字投影，路由结果逐句不变（契约测试 + 路由矩阵逐条钉住）。
    """
    global _RED_TRIGGER_CACHE, _RED_TRIGGER_CACHE_MTIME
    if not user_text:
        return []
    idx = _read_skills_index()
    if _RED_TRIGGER_CACHE is None or _RED_TRIGGER_CACHE_MTIME != _SKILLS_INDEX_MTIME:
        _RED_TRIGGER_CACHE = []
        _RED_TRIGGER_CACHE_MTIME = _SKILLS_INDEX_MTIME
        for line in idx.splitlines():
            if not line.startswith("|"):
                continue
            cells = line.split("|")
            if len(cells) < 6:
                continue
            # 兼容两种格式：老 | N | name | desc | kw | trigger |，新 | name | desc | kw | trigger |
            if cells[1].strip().isdigit():
                name, kw_cell, trig = cells[2].strip(), cells[4].strip(), cells[5].strip()
            else:
                name, kw_cell, trig = cells[1].strip(), cells[3].strip(), cells[4].strip()
            if "RED" not in trig:
                continue
            triggers = [k.strip() for k in kw_cell.split(",") if k.strip()]
            if triggers:
                _RED_TRIGGER_CACHE.append((name, triggers))
    t = user_text.lower()
    t_words = set(t.split())  # 英文词级匹配用
    t_tight = _tighten_cjk_ascii(t)  # 边界空白归一后的文本（"CNS 级别" -> "cns级别"）
    hits = []
    for name, triggers in _RED_TRIGGER_CACHE:
        for kw in triggers:
            kw_l = kw.lower()
            if len(kw_l) < 2:
                continue
            rule = ""
            # 短 ASCII 缩写走「字母边界」匹配，避免 science/algorithm/mRNA/degree 这类词片段误触发（P0-2b）
            if kw_l.isascii() and len(kw_l) <= _SHORT_ASCII_KW_MAX and kw_l.isalnum():
                if _short_ascii_kw_match(kw_l, t):
                    rule = "short-ascii"
            elif kw_l in t:
                rule = "substring"
            elif _tighten_cjk_ascii(kw_l) in t_tight:
                # 归一后再判一次："CNS级别" ← "CNS 级别"、"AI腔" ← "AI 腔"（见 _tighten_cjk_ascii）
                rule = "cjk-gap"
            elif " " in kw_l and t_words:
                # 英文多词触发词：实词全中（"review paper" 需要 review 与 paper 同时出现）
                kw_words = set(w for w in kw_l.split() if w not in _EN_STOPWORDS)
                if kw_words and kw_words <= t_words:
                    rule = "multiword"
            if rule:
                hits.append({"name": name, "keyword": kw, "rule": rule})
                break
    # 批K(2026-08-16)：本地文献库操作豁免全局文献类 RED skills——
    # "总结文献库里…" 不应被 literature-review(触发词'总结') / paper-summary(触发词'paper')
    # 抢占 skill_view，本地文献库有专用工具（summarize_paper / kb_extract_from_paper / literature_import）。
    _lower = user_text.lower()
    if hits and any(t in user_text or t in _lower for t in _LOCAL_LIT_EXEMPT_TRIGGERS):
        hits = [h for h in hits if h["name"] not in _LOCAL_LIT_RED_EXEMPT]
    return hits


def _match_red_skill_triggers(user_text: str) -> list:
    """命中 RED 技能名列表（按索引顺序）。

    P0-3 起是 _match_red_skill_hits 的名字投影：匹配语义、命中顺序、本地文献豁免
    完全一致，只是不再丢弃「命中理由」（理由由 _match_red_skill_hits 返回、由
    _red_hit_emit 推给前端）。保持本函数签名与语义不变——契约测试与路由矩阵依赖它。
    """
    return [h["name"] for h in _match_red_skill_hits(user_text)]


# === P8(置顶 skill): 会话级优先技能 + skill 元数据 + 文件树 ===
# 需求：用户在前端把某个 skill「置顶」到本会话 → 优先而非独占：
#   1) 每回合注入「置顶优先」路由指令（优先级高于自动路由）；
#   2) 用户消息命中该 skill 触发词时，额外预载 SKILL.md 全文（硬注入兜底，对齐 RED 的不可跳过强度）；
#   3) 与自动路由命中的其他 skill（含 RED）冲突时，以置顶 skill 为准。

_SKILL_META_CACHE = {}       # name -> (sig, meta)
_PINNED_SKILLS_CACHE = {}    # sid -> [names]
_PINNED_MAX = 5              # 单会话最多置顶数
_PINNED_FULLTEXT_BUDGET = 40000   # 命中触发词时预载 SKILL.md 的字符上限


def _skill_roots():
    """skill 搜索根（与 /api/skills 扫描目录保持一致）"""
    from pathlib import Path as _P8
    cands = [
        _P8(SKILLS_DIR),
        _P8(HERMES_HOME_DIR) / "skills" / "bioinformatics",
        _P8(HERMES_HOME_DIR) / "skills" / "plotting",
    ]
    out = []
    for c in cands:
        try:
            if c.is_dir() and c not in out:
                out.append(c)
        except Exception:
            continue
    return out


def _find_skill_dir(name: str):
    """按名字定位 skill 目录（含路径穿越防护；找不到返回 None）"""
    name = (name or "").strip()
    if (not name) or (".." in name) or ("/" in name) or ("\\" in name) or name.startswith("."):
        return None
    for root in _skill_roots():
        d = root / name
        try:
            if d.is_dir():
                return d
        except Exception:
            continue
    return None


def _skill_frontmatter(text: str) -> dict:
    """解析 SKILL.md 的 YAML frontmatter（部分 skill 没有 skill.json，用原生元数据兜底）"""
    if not text or not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    out = {}
    for line in text[3:end].splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        k, v = line.split(":", 1)
        k = k.strip().lower()
        v = v.strip().strip('"').strip("'")
        if not k or not v:
            continue
        if k in ("name", "description", "when_to_use", "category", "language", "domain", "trigger_level"):
            out[k] = v
        elif k in ("tags", "aliases", "trigger_keywords"):
            v2 = v.strip()
            if v2.startswith("[") and v2.endswith("]"):
                v2 = v2[1:-1]
            items = [x.strip().strip('"').strip("'") for x in v2.split(",")]
            out[k] = [x for x in items if x]
    return out


def _skill_meta(name: str) -> dict:
    """skill 元数据：skill.json 优先、SKILL.md frontmatter 兜底；按 mtime 缓存，找不到返回 {}"""
    d = _find_skill_dir(name)
    if d is None:
        return {}
    sj = d / "skill.json"
    md = d / "SKILL.md"
    try:
        sig = tuple(int(p.stat().st_mtime) for p in (sj, md) if p.exists())
    except Exception:
        sig = ()
    hit = _SKILL_META_CACHE.get(name)
    if hit and hit[0] == sig:
        return hit[1]
    data = {}
    if sj.exists():
        try:
            with open(sj, encoding="utf-8", errors="replace") as f:
                data = json.load(f) or {}
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
    md_text = ""
    if md.exists():
        try:
            with open(md, encoding="utf-8", errors="replace") as f:
                md_text = f.read()
        except Exception:
            md_text = ""
    fm = _skill_frontmatter(md_text)

    def _pick(*keys):
        for src in (data, fm):
            for k in keys:
                v = src.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        return ""

    def _list(*keys):
        out = []
        for src in (data, fm):
            for k in keys:
                v = src.get(k)
                if isinstance(v, str):
                    v = [x.strip() for x in v.split(",")]
                if isinstance(v, (list, tuple)):
                    for x in v:
                        x = str(x).strip()
                        if x and x not in out:
                            out.append(x)
        return out

    meta = {
        "name": name,
        "display": _pick("name") or name,
        "description": _pick("description", "detailed_description")[:400],
        "when_to_use": _pick("when_to_use", "trigger_scenario")[:600],
        "category": _pick("category", "domain"),
        "language": _pick("language"),
        "trigger_level": _pick("trigger_level"),
        "trigger_keywords": _list("trigger_keywords"),
        "aliases": _list("aliases"),
        "tags": _list("tags"),
        "dir": str(d).replace("\\", "/"),
        "has_skill_md": md.exists(),
        "has_skill_json": sj.exists(),
        "skill_md_size": len(md_text),
    }
    _SKILL_META_CACHE[name] = (sig, meta)
    return meta


# P0-2d(2026-09-23)：置顶 skill 触发判定的词边界。
# 旧实现是纯子串匹配（`kl in low`），纯英文短词会从别的单词肚子里命中：
#   cell ⊂ excellent、core ⊂ score、GO ⊂ category/logout、find ⊂ DoubletFinder、
#   flow ⊂ workflow、set ⊂ dataset、code ⊂ encode、sites ⊂ websites、
#   genomic ⊂ 10xgenomics、processing ⊂ preprocessing、grn ⊂ sgrna。
# 规则分两档（档 1 与 RED 路由共用同一套 short_ascii_boundary，档 2 只用于置顶判定）：
#   档 1 纯 ASCII 且 <=3 位（GO/SCI/QC/set/map）：左右都不许紧贴英文字母（复用 _short_ascii_kw_match）；
#   档 2 更长的 ASCII（find/flow/code/processing）：左边不许贴字母数字（词首边界），
#        右边允许常见词形变化（cells/primers/genes/combined）或非字母，其余一律不算命中。
# 含 CJK/标点的关键词仍走子串：中文没有词边界（"做primer设计"、"网络调研" 必须照命中）。
_KW_INFLECT_SUFFIXES = ("ing", "es", "ed", "s", "d")
_KW_LEFT_BLOCK_RE = re.compile(r"[a-z0-9]")


def _is_en_letter(ch: str) -> bool:
    """只认英文字母：Python 的 str.isalpha() 对汉字也返回 True（"设计".isalpha()），
    用它会把 'primer' 在 '做primer设计' 里判成「尾巴接字母」而误杀（P0-2d 实测踩到）。"""
    return bool(ch) and ch.isascii() and ch.isalpha()


def _kw_inflected(tail: str) -> bool:
    """命中尾巴是不是词形变化（cells / primers / genes / combined）。"""
    for suf in _KW_INFLECT_SUFFIXES:
        if tail.startswith(suf):
            nxt = tail[len(suf):len(suf) + 1]
            if not _is_en_letter(nxt):
                return True
    return False


def _kw_boundary_hit(text_low: str, kw_l: str) -> bool:
    """ASCII 触发词的边界命中判定（P0-2d）。非 ASCII（CJK/混合）不用本函数。"""
    if kw_l.isascii() and len(kw_l) <= _SHORT_ASCII_KW_MAX and kw_l.isalnum():
        return _short_ascii_kw_match(kw_l, text_low)
    n = len(kw_l)
    start = 0
    while True:
        i = text_low.find(kw_l, start)
        if i < 0:
            return False
        if i == 0 or not _KW_LEFT_BLOCK_RE.match(text_low[i - 1]):
            tail = text_low[i + n:i + n + 4]
            if not _is_en_letter(tail[:1]) or _kw_inflected(tail):
                return True
        start = i + 1


def _kw_any_hit(text_low: str, kw_l: str) -> bool:
    """一个候选词（含 CJK/多词短语）在文本里算不算命中。"""
    return _kw_boundary_hit(text_low, kw_l) if kw_l.isascii() else (kw_l in text_low)


def _skill_trigger_hit(meta: dict, user_text: str):
    """置顶 skill 的触发判定：用该 skill 自己的 trigger_keywords/aliases/名字（比 RED 的领域级关键词更细）

    P0-2d(2026-09-23)：由「纯子串」收紧为「词边界」——
      · ASCII 候选走 _kw_boundary_hit（档 1 短缩写左右都不贴字母；档 2 词首边界 + 允许词形变化尾巴）；
      · 多词短语的「实词全中」兜底同样逐词走边界，修掉 "cell cycle" 只因句子散落着 cell 与 cycle 就命中；
      · 含 CJK/标点的候选仍走子串（中文无词边界，"做primer设计"/"网络调研" 照旧命中）。
    量化（439 篇 SKILL.md、424 万字符语料）：1226 个 ASCII 候选里 216 个存在「词中命中」，
    全部 89933 次出现里有 13839 次（15.4%）落在别的单词内部；改后 24 处误命中归零、
    真阳性零丢失（12 句真实说法 + 480000 组「句子×技能」对，新命中恒为旧命中的子集）。"""
    if not user_text or not meta:
        return []
    low = user_text.lower()
    hits = []
    seen = set()
    cands = []
    for k in list(meta.get("trigger_keywords") or []) + list(meta.get("aliases") or []):
        cands.append(k)
    nm = meta.get("name") or ""
    dp = meta.get("display") or ""
    if len(nm) >= 3:
        cands.append(nm)
    if len(dp) >= 3 and dp != nm:
        cands.append(dp)
    for k in cands:
        kl = str(k or "").lower().strip()
        if not kl or kl in seen:
            continue
        seen.add(kl)
        if len(kl) >= 2 and _kw_any_hit(low, kl):
            hits.append(k)
        elif " " in kl:
            # 多词短语的兜底：允许词序散开，但每个实词都要自己踩在词首边界上（P0-2d）
            parts = [p for p in kl.split() if len(p) >= 3]
            if parts and all(_kw_any_hit(low, p) for p in parts):
                hits.append(k)
    return hits[:8]


def _read_skill_md_text(name: str, limit: int = 0) -> str:
    """读 SKILL.md 全文（limit>0 时截断并标注）"""
    d = _find_skill_dir(name)
    if d is None:
        return ""
    md = d / "SKILL.md"
    if not md.exists():
        return ""
    try:
        with open(md, encoding="utf-8", errors="replace") as f:
            txt = f.read()
    except Exception:
        return ""
    if limit and len(txt) > limit:
        return txt[:limit] + "\n\n[... SKILL.md 过长已截断，仅保留前 " + str(limit) + " 字符；完整内容请调用 skill_view(name='" + name + "') ...]"
    return txt


def _build_pinned_skill_block(names, user_text: str = "", lang: str = "zh") -> str:
    """置顶 skill 注入块：优先而非独占。普通情况给路由优先级 + 冲突裁决；
    命中触发词时额外预载 SKILL.md 全文（硬注入兜底）。"""
    metas = []
    missing = []
    for n in (names or []):
        m = _skill_meta(n)
        if m:
            metas.append(m)
        elif str(n or "").strip():
            missing.append(str(n).strip())
    if not metas and not missing:
        return ""
    zh = (lang != "en")
    hits_all = []
    for m in metas:
        h = _skill_trigger_hit(m, user_text)
        if h:
            hits_all.append((m, h))
    L = []
    if zh:
        L.append("【系统指令：用户置顶技能 — 优先级高于自动路由，不可跳过】")
        L.append("用户已在本会话置顶以下技能（优先使用，不是独占：与置顶技能无关的任务照常走自动路由）：")
    else:
        L.append("[SYSTEM: user-pinned skills — HIGHER priority than automatic routing, do not skip]")
        L.append("The user pinned the following skills for this session (preferred, NOT exclusive: unrelated tasks still use normal routing):")
    for m in metas:
        head = "- " + m["name"]
        dp = m.get("display") or ""
        if dp and dp != m["name"]:
            head += " (" + dp + ")"
        L.append(head)
        if m.get("description"):
            L.append("    " + ("description: " if not zh else "说明：") + m["description"][:200])
        if m.get("when_to_use"):
            L.append("    " + ("use when: " if not zh else "适用场景：") + m["when_to_use"][:300])
        kw = (m.get("trigger_keywords") or [])[:14]
        if kw:
            L.append("    " + ("triggers: " if not zh else "触发词：") + ", ".join(kw))
    for n in missing:
        if zh:
            L.append("- " + n + "（⚠ 未找到该技能：本机不存在或已被删除。不要假装使用它，也不要凭名字编造它的流程；请如实告诉用户置顶技能缺失。）")
        else:
            L.append("- " + n + " (⚠ skill not found on this machine. Do NOT pretend to use it or invent its workflow; tell the user the pinned skill is missing.)")
    if zh:
        L.append("")
        L.append("⚙ 路由规则（必须遵守）：")
        L.append("1. 只要本轮任务落在置顶技能的适用范围内（用户点名、或任务与该适用场景相符），必须优先调用 skill_view(name='<置顶技能名>') 加载其完整指令，并按它的流程/规范/参数执行。")
        L.append("2. 置顶技能与自动路由命中的其他 skill（含 RED 必触发技能、领域技能）规则冲突时，一律以置顶技能为准；其他 skill 只能补充信息，不得覆盖置顶技能规定的输出规范、流程与参数。")
        L.append("3. 置顶技能不是禁用其他技能：与置顶技能无关的任务，照常按自动路由使用其他 skill。")
        L.append("4. 若置顶技能缺少完成任务所需的关键信息（如输出语言/参数），先向用户确认，不要擅自替换成别的 skill。")
    else:
        L.append("")
        L.append("Routing rules (mandatory):")
        L.append("1. If this turn falls into a pinned skill's scope (user named it, or the task matches its use-when), you MUST call skill_view(name='<pinned skill>') first and follow its workflow/rules/parameters.")
        L.append("2. When a pinned skill conflicts with any other auto-routed skill (including RED mandatory skills), the pinned skill wins; others may only add information, never override its output spec, workflow or parameters.")
        L.append("3. Pinning is NOT disabling: unrelated tasks still follow normal routing.")
        L.append("4. If the pinned skill needs missing key inputs (output language/params), ask the user — do not silently substitute another skill.")
    if hits_all:
        m0, h0 = hits_all[0]
        full = _read_skill_md_text(m0["name"], _PINNED_FULLTEXT_BUDGET)
        if zh:
            L.append("")
            L.append("【置顶技能已命中触发词 → 立即执行，禁止跳过】")
            L.append("用户消息命中置顶技能「" + m0["name"] + "」的触发词：" + ", ".join(str(x) for x in h0))
            L.append("1. 第一件事：调用 skill_view(name='" + m0["name"] + "') 加载完整指令（禁止跳过、禁止凭固有知识直接处理）。")
        else:
            L.append("")
            L.append("[Pinned skill trigger matched — execute now, do not skip]")
            L.append("User message matched pinned skill '" + m0["name"] + "' on: " + ", ".join(str(x) for x in h0))
            L.append("1. First action: call skill_view(name='" + m0["name"] + "') to load its full instructions (never skip).")
        if full:
            if zh:
                L.append("2. 以下是该技能 SKILL.md 全文（已预载为兜底；仍须调用 skill_view 以获得脚本/模板等关联文件）：")
            else:
                L.append("2. Full SKILL.md is preloaded below as a fallback (still call skill_view to get linked scripts/templates):")
            L.append("<<<PINNED_SKILL_MD_BEGIN>>>")
            L.append(full)
            L.append("<<<PINNED_SKILL_MD_END>>>")
    if missing and zh:
        L.append("⚠ 置顶技能缺失时：照常按自动路由处理本轮任务，不要因为缺技能就停下不动。")
    elif missing:
        L.append("⚠ When a pinned skill is missing: proceed with normal routing for this turn; do not stall.")
    L.append("")
    return "\n".join(L) + "\n"


def _pinned_skills_get(sid: str) -> list:
    """读会话置顶 skill（内存 → state.db kv → []）"""
    if not sid:
        return []
    s = _sessions.get(sid)
    if isinstance(s, dict) and isinstance(s.get("pinned_skills"), list):
        return list(s["pinned_skills"])
    if sid in _PINNED_SKILLS_CACHE:
        return list(_PINNED_SKILLS_CACHE[sid])
    names = []
    try:
        db = _get_session_db()
        if db is not None and hasattr(db, "_conn"):
            row = db._conn.execute("SELECT value FROM kv WHERE key=?", ("pinned_skills:" + sid,)).fetchone()
            if row and row[0]:
                v = json.loads(row[0])
                if isinstance(v, list):
                    names = [str(x) for x in v if str(x).strip()]
    except Exception as e:
        logger.debug("[pinned] 读取失败: %s", e)
    _PINNED_SKILLS_CACHE[sid] = list(names)
    if isinstance(s, dict):
        s["pinned_skills"] = list(names)
    return names


def _pinned_skills_set(sid: str, names) -> list:
    """写会话置顶 skill（内存 + state.db kv），返回清洗后的列表"""
    clean = []
    for n in (names or []):
        n = str(n or "").strip()
        if n and n not in clean:
            clean.append(n)
    clean = clean[:_PINNED_MAX]
    _PINNED_SKILLS_CACHE[sid] = list(clean)
    s = _sessions.get(sid)
    if isinstance(s, dict):
        s["pinned_skills"] = list(clean)
    try:
        db = _get_session_db()
        if db is not None and hasattr(db, "_conn"):
            db._conn.execute(
                "INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)",
                ("pinned_skills:" + sid, json.dumps(clean, ensure_ascii=False)),
            )
            db._conn.commit()
    except Exception as e:
        logger.warning("[pinned] 落盘失败: %s", e)
    return clean


def _skill_usage_get(sid: str) -> dict:
    """本会话实际加载过哪些 skill（内存优先；重启/切会话后从 tool_calls_log 重建）"""
    if not sid:
        return {}
    s = _sessions.get(sid)
    if isinstance(s, dict) and isinstance(s.get("_skills_used"), dict) and s["_skills_used"]:
        return dict(s["_skills_used"])
    used = {}
    try:
        import sqlite3 as _p8_sqlite
        conn = _p8_sqlite.connect(os.path.join(HERMES_HOME_DIR, "state.db"), timeout=10)
        conn.execute("PRAGMA busy_timeout=5000")
        rows = conn.execute(
            "SELECT args_json FROM tool_calls_log WHERE session_id=? AND tool_name='skill_view' ORDER BY id DESC LIMIT 200",
            (sid,),
        ).fetchall()
        conn.close()
        for r in rows:
            try:
                nm = (json.loads((r[0] or "{}")) or {}).get("name")
            except Exception:
                nm = None
            if nm:
                nm = str(nm)
                used[nm] = used.get(nm, 0) + 1
    except Exception as e:
        logger.debug("[skill_usage] 回读失败: %s", e)
    if isinstance(s, dict):
        s["_skills_used"] = dict(used)
    return used


def _skill_usage_note(sid: str, name: str, session=None) -> None:
    """记录一次 skill 加载 + 推 skill_used 事件（前端据此点亮「已使用」徽标）"""
    if not sid or not name:
        return
    s = session if isinstance(session, dict) else _sessions.get(sid)
    cnt = 1
    if isinstance(s, dict):
        used = s.get("_skills_used")
        if not isinstance(used, dict):
            used = {}
        used[str(name)] = int(used.get(str(name), 0)) + 1
        s["_skills_used"] = used
        cnt = used[str(name)]
    try:
        _session_emit(s if isinstance(s, dict) else {"id": sid},
                      {"type": "skill_used", "skill": str(name), "session_id": sid, "used": cnt})
    except Exception:
        pass


def _skill_files_tree(name: str, max_files: int = 600) -> dict:
    """skill 目录下的完整文件树（绝对路径直接交给查看器预览；跳过隐藏文件）"""
    d = _find_skill_dir(name)
    if d is None:
        return {}
    files = []

    def walk(cur, rel=""):
        try:
            entries = sorted(cur.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except Exception:
            return
        for p in entries:
            if len(files) >= max_files:
                return
            if p.name.startswith("."):
                continue
            r = (rel + "/" + p.name) if rel else p.name
            try:
                if p.is_dir():
                    files.append({"name": p.name, "rel": r, "path": str(p).replace("\\", "/"),
                                  "is_dir": True, "size": 0, "ext": ""})
                    walk(p, r)
                else:
                    st = p.stat()
                    files.append({"name": p.name, "rel": r, "path": str(p).replace("\\", "/"),
                                  "is_dir": False, "size": st.st_size,
                                  "ext": p.suffix.lower().lstrip("."), "mtime": int(st.st_mtime)})
            except Exception:
                continue

    walk(d)
    files.sort(key=lambda x: (x["rel"] not in ("SKILL.md", "skill.json"), x["rel"]))
    return {"name": name, "dir": str(d).replace("\\", "/"), "files": files[:max_files],
            "truncated": len(files) > max_files, "total": len(files)}


def _pinned_item(name: str) -> dict:
    """前端 chip 需要的置顶条目（使用次数由端点补）"""
    m = _skill_meta(name)
    if not m:
        return {"name": name, "display": name, "missing": True, "description": "", "when_to_use": "",
                "trigger_keywords": [], "trigger_level": "", "category": "", "dir": ""}
    m = dict(m)
    m["missing"] = False
    return m


def _pinned_expect_emit(session, user_text: str) -> list:
    """P8: 本回合命中触发词的置顶 skill → 前端显示「本轮应加载」，未加载则在回合结束时告警。"""
    try:
        pinned = _pinned_skills_get(session.get("id") or "")
    except Exception:
        pinned = []
    exp = []
    for n in pinned:
        m = _skill_meta(n)
        if not m:
            continue
        hits = _skill_trigger_hit(m, user_text)
        if hits:
            exp.append({"name": n, "hits": hits[:6]})
    try:
        session["_pinned_expected"] = [x["name"] for x in exp]
    except Exception:
        pass
    if exp:
        try:
            _session_emit(session, {"type": "skill_expect", "skills": exp,
                                    "ts": datetime.now().strftime("%H:%M:%S"),
                                    "session_id": session.get("id")})
        except Exception:
            pass
    return exp


# === P0-3(2026-09-23): 命中可见性 + 显式 /skill-name 调用 ===
# 痛点 1（命中不可见）：用户看到 agent 用了某个技能，却不知道「为什么是它」——触发词藏在
#   SKILLS_INDEX.md 的表格里，命中了哪条、走哪条匹配规则，人和模型都看不到，出了问题无从排查。
# 痛点 2（只能靠猜）：想指定某个技能，只能把触发词碰运气写进句子里；触发词一改就断链。
# 本区块只做两件事：
#   A. 把命中理由说清楚：_match_red_skill_hits 给出 name+keyword+rule（路由本身逐句不变），
#      _red_hit_emit 推 skill_hit 事件 → 前端 chip 直接显示「命中哪条触发词、走哪条规则」；
#   B. 给一个确定性入口：/skill-name → _parse_skill_invocations 解析 → _build_explicit_skill_block
#      硬注入（预载 SKILL.md 全文），优先级：显式调用 > 置顶技能 > RED 自动命中。

_EXPLICIT_MAX = 4                  # 单条消息最多生效的显式调用数（防一句话塞 20 个技能）
_EXPLICIT_CANDIDATE_MAX = 5        # 歧义 / 相近建议最多列几个
_EXPLICIT_UNKNOWN_MAX = 3          # 未知技能最多提醒几个
_EXPLICIT_FULLTEXT_BUDGET = 40000  # 每个显式技能预载 SKILL.md 的字符上限（与置顶一致）
# 应用级斜杠命令：本身不是技能名（真实技能名优先命中，见 _parse_skill_invocations）
_SLASH_RESERVED = ("papers", "help", "clear")
# 本机最长技能名 60 字符（analyze_accelerated_stability_of_pharmaceutical_formulations），
# 80 以上绝不可能是技能名（哈希/路径残片），静默忽略——但绝不截断后当成技能名报出来。
_SLASH_TOKEN_MAX = 80
# 斜杠后必须紧跟 ASCII 字母数字或下划线（技能目录里有 _debates 这类内部技能），
# 名字里只允许技能目录名的实际字符集 [A-Za-z0-9._-]；以 . 开头的一律不算（/.. 穿越）。
# 刻意不设长度上限：正则截断会把 /<200 个字符> 变成「64 个字符的技能名」，
# 用户看到的将是他没打过的名字；长度过滤放在匹配之后（见 _SLASH_TOKEN_MAX）。
_SLASH_TOKEN_RE = re.compile(r"/([A-Za-z0-9_][A-Za-z0-9._-]*)")
# 斜杠左侧允许的边界字符：空白 / 中英标点 / 括号。除此之外的字符（字母数字、: / \ = 、<）
# 说明这个斜杠属于 URL、路径或分数（http://a/b、work/papers/x、E:/work、1/2、//x）→ 不算调用。
# 注意这里刻意不含 ASCII 冒号：Windows 盘符路径 E:/work 的斜杠左边正是冒号。
_SLASH_BOUNDARY = set(" \t\r\n，,、。；;！!？?“”\"'‘’()[]{}【】<>《》")
_SKILL_NAME_CACHE = None           # {小写技能名: 真实技能名}
_SKILL_NAME_CACHE_SIG = None       # 技能目录签名（变了才重建）


def _skill_name_sig():
    """技能目录签名（每个根目录的 mtime + 子目录数）。目录没变就不重建名字索引。

    不用逐个 stat 355 个技能目录：每句话都要解析斜杠命令，签名本身必须便宜。
    """
    sig = []
    for r in _skill_roots():
        try:
            st = r.stat()
            n = sum(1 for p in r.iterdir() if p.is_dir())
            sig.append((str(r), int(st.st_mtime), n))
        except Exception:
            sig.append((str(r), 0, 0))
    return tuple(sig)


def _skill_name_index() -> dict:
    """{小写技能名: 真实技能名}（扫盘一次后缓存，目录签名变了自动重建）"""
    global _SKILL_NAME_CACHE, _SKILL_NAME_CACHE_SIG
    sig = _skill_name_sig()
    if _SKILL_NAME_CACHE is not None and _SKILL_NAME_CACHE_SIG == sig:
        return _SKILL_NAME_CACHE
    idx = {}
    for r in _skill_roots():
        try:
            for p in r.iterdir():
                if p.is_dir() and not p.name.startswith("."):
                    idx.setdefault(p.name.lower(), p.name)
        except Exception:
            continue
    _SKILL_NAME_CACHE = idx
    _SKILL_NAME_CACHE_SIG = sig
    return idx


def _normalize_skill_token(tok) -> str:
    """斜杠 token 归一：去空白、转小写、去掉尾部多打的 - . _

    刻意不 strip 开头的下划线：技能目录里有 _debates 这类内部技能，"_" 是名字的一部分，
    吃掉它会把 /_deb 误解析成 debate-core（极端测试实抓）。
    """
    return str(tok or "").strip().lower().rstrip("-._")


def _tight_seps(s) -> str:
    """去掉 - _ . 空格 后的小写形式：singlecell ↔ single-cell ↔ single_cell 视为同一个名字。"""
    return re.sub(r"[-_.\s]+", "", str(s or "").lower())


def _suggest_skills(token, limit: int = _EXPLICIT_CANDIDATE_MAX) -> list:
    """给拼错/没写全的技能名找相近技能：前缀 → 名字是 token 的前缀 → 互为子串 → difflib。

    完全不像就返回 []——宁可如实说「本机没有这个技能」，也不硬凑一个错的技能给用户。
    """
    t = _normalize_skill_token(token)
    if len(t) < 3:
        return []
    idx = _skill_name_index()
    low = list(idx.keys())
    out = []

    def _take(seq):
        for n in seq:
            real = idx.get(n)
            if real and real not in out:
                out.append(real)

    _take(sorted(n for n in low if n.startswith(t)))
    if len(out) < limit:
        # 分隔符变体：/singlecell 应该能想到 single-cell-*（用户不会记得是连字符还是下划线）
        tight_t = _tight_seps(t)
        if len(tight_t) >= 3:
            _take(sorted(n for n in low if _tight_seps(n).startswith(tight_t)))
    if len(out) < limit:
        _take(sorted(n for n in low if len(n) >= 3 and t.startswith(n)))
    if len(out) < limit:
        _take(sorted(n for n in low if len(n) >= 4 and (t in n or n in t)))
    if len(out) < limit:
        try:
            import difflib
            _take(difflib.get_close_matches(t, low, n=limit, cutoff=0.75))
        except Exception:
            pass
    return out[:limit]


def _parse_skill_invocations(user_text: str) -> dict:
    """解析消息里的 /skill-name 显式调用（确定性入口，优先级最高）。

    只认「真的技能名」：
      · 斜杠左边必须是空白/中英标点/括号——URL（http://a/b）、路径（work/papers/x、E:/work）、
        分数（1/2）、双斜杠（//name）的斜杠左边是字母数字或 : / \\ = → 一律不算调用；
      · 应用级命令（/papers /help /clear）不算技能，也不算「未知技能」（用户没犯错）；
      · 技能名大小写不敏感；下划线写法等价连字符写法（/scrna_qc → scrna-qc）；
      · 唯一前缀自动补全（/academic-researc → academic-research）；前缀有 ≥2 个候选时
        绝不猜，交回候选让用户确认；找不到就报 unknown + 相近建议（不许静默丢弃）。

    超过 _EXPLICIT_MAX 的调用进 overflow（不是静默丢弃）：模型会被告知「这几个没生效」，
    由它转告用户分批点名——用户以为点名了 6 个，实际只生效 4 个，这事必须说。

    返回 {"raw": [...], "resolved": [{"token","name"}], "unknown": [...],
          "ambiguous": [{"token","candidates"}], "overflow": [name]}；没有斜杠 → 全空（零开销早退）。
    """
    out = {"raw": [], "resolved": [], "unknown": [], "ambiguous": [], "overflow": []}
    text = user_text or ""
    if "/" not in text:
        return out
    idx = _skill_name_index()
    low = list(idx.keys())
    seen = set()
    for m in _SLASH_TOKEN_RE.finditer(text):
        i = m.start()
        if i > 0 and text[i - 1] not in _SLASH_BOUNDARY:
            continue                      # URL / 路径 / 分数 / 双斜杠里的斜杠
        if m.end() < len(text) and text[m.end()] == "/":
            continue                      # 像路径（/etc/passwd、/data/raw），不是技能命令
        tok = m.group(1).rstrip('-._')
        if not tok or tok.isdigit():
            continue                      # 空名、纯数字（/2026）都不是技能
        if len(tok) > _SLASH_TOKEN_MAX:
            continue                      # 超长乱串（哈希/长路径残片），不是技能名也不是用户笔误
        key = _normalize_skill_token(tok)
        if not key or key in seen:
            continue
        seen.add(key)
        name = idx.get(key)
        if name is None:
            for v in (key.replace("_", "-"), key.replace("-", "_")):
                if v != key and v in idx:
                    name = idx[v]
                    break
        if name is None and key in _SLASH_RESERVED:
            continue                      # 应用级命令：不是技能，也不是未知技能
        out["raw"].append(tok)
        if name:
            if len(out["resolved"]) < _EXPLICIT_MAX:
                out["resolved"].append({"token": tok, "name": name})
            else:
                out["overflow"].append(name)
            continue
        starts = sorted(n for n in low if n.startswith(key))
        if len(starts) == 1:
            if len(out["resolved"]) < _EXPLICIT_MAX:
                out["resolved"].append({"token": tok, "name": idx[starts[0]]})
            else:
                out["overflow"].append(idx[starts[0]])
            continue
        if len(starts) > 1:
            out["ambiguous"].append({"token": tok,
                                     "candidates": [idx[n] for n in starts[:_EXPLICIT_CANDIDATE_MAX]]})
            continue
        if len(out["unknown"]) < _EXPLICIT_UNKNOWN_MAX:
            out["unknown"].append(tok)
    return out


def _build_explicit_skill_block(inv: dict, lang: str = "zh") -> str:
    """显式 /skill-name 注入块：优先级高于置顶技能与 RED 自动命中，点名即预载 SKILL.md 全文。

    未知技能与歧义名前缀也在这里说清楚（给出相近建议 / 候选清单 + 要求先跟用户确认），
    避免模型「假装加载了一个不存在的技能」。没有任何显式调用 → 返回空串（不污染普通回合）。
    """
    if not isinstance(inv, dict):
        return ""
    res = list(inv.get("resolved") or [])
    unk = list(inv.get("unknown") or [])
    amb = list(inv.get("ambiguous") or [])
    if not res and not unk and not amb:
        return ""
    zh = (lang != "en")
    L = []
    if zh:
        L.append("【系统指令：用户显式点名技能 — 最高优先级，不可跳过】")
    else:
        L.append("[SYSTEM: user explicitly invoked skills — TOP priority, do not skip]")
    if res:
        if zh:
            L.append("用户在本轮消息里用斜杠命令显式点名了以下技能（这是确定性指令，不是自动路由的猜测）：")
        else:
            L.append("The user explicitly named these skills with a slash command this turn (a deterministic instruction, not a routing guess):")
        for r in res:
            nm = r.get("name") or ""
            tk = r.get("token") or nm
            L.append("- " + nm + ("（用户输入 /" + tk + "）" if zh else " (user typed /" + tk + ")"))
        L.append("")
        if zh:
            L.append("执行规则（必须遵守）：")
        else:
            L.append("Rules (mandatory):")
        for r in res:
            nm = r.get("name") or ""
            if zh:
                L.append("1. 第一件事：调用 skill_view(name='" + nm + "') 加载该技能的完整指令（禁止跳过、禁止凭固有知识直接作答）。")
            else:
                L.append("1. First action: call skill_view(name='" + nm + "') to load its full instructions (never skip, never answer from your own knowledge first).")
        if zh:
            L.append("2. 显式调用优先级最高：与置顶技能、RED 必触发技能、领域自动路由冲突时，一律以显式点名的技能为准，其他技能只能补充信息。")
            L.append("3. 显式点名意味着「按这个技能的流程做」：不要用别的技能替换它，也不要只介绍这个技能是什么。")
        else:
            L.append("2. Explicit invocation outranks everything: user-pinned skills, RED mandatory skills and automatic domain routing all yield to the explicitly named skill; others may only add information.")
            L.append("3. An explicit invocation means \"run this skill's workflow\": do not substitute another skill, and do not merely describe what the skill is.")
        if zh:
            L.append("4. 以下是该技能 SKILL.md 全文（已预载为兜底；仍须调用 skill_view 以获得脚本/模板等关联文件）：")
        else:
            L.append("4. Full SKILL.md is preloaded below as a fallback (still call skill_view to get linked scripts/templates):")
        ove = [str(x) for x in (inv.get("overflow") or [])]
        if ove:
            joined_o = "、".join(ove) if zh else ", ".join(ove)
            if zh:
                L.append("⚠ 本机一次最多处理 " + str(_EXPLICIT_MAX) + " 个显式点名；下面这些名字这轮没生效：" + joined_o +
                         "。请如实告诉用户「一次最多 4 个，请分批点名」，不要假装已经加载了它们。")
            else:
                L.append("⚠ At most " + str(_EXPLICIT_MAX) + " explicit skills per message; these were NOT loaded this turn: " + joined_o +
                         ". Tell the user plainly (at most 4 per message, please name them in batches) and never pretend they were loaded.")
        for r in res:
            nm = r.get("name") or ""
            full = _read_skill_md_text(nm, _EXPLICIT_FULLTEXT_BUDGET)
            L.append("<<<EXPLICIT_SKILL_MD_BEGIN>>>")
            L.append("### /" + nm)
            L.append(full if full else ("（未能读取 SKILL.md：请调用 skill_view(name='" + nm + "') 获取）" if zh else "(SKILL.md not readable here; call skill_view(name='" + nm + "') instead)"))
            L.append("<<<EXPLICIT_SKILL_MD_END>>>")
    for a in amb:
        tk = a.get("token") or ""
        cands = [str(x) for x in (a.get("candidates") or [])]
        joined = "、".join(cands) if zh else ", ".join(cands)
        if zh:
            L.append("- " + tk + "（⚠ 名字有歧义：本机有多个技能以此为前缀 —— " + joined +
                     "。先向用户确认要用哪一个（把候选列出来），得到确认前不要自己选一个执行。）")
        else:
            L.append("- " + tk + " (⚠ ambiguous: several skills on this machine share this prefix — " + joined +
                     ". Ask the user which one they mean (list the candidates); do not pick one on your own.)")
    for tok in unk:
        sug = _suggest_skills(tok)
        joined = ("、".join(sug) if zh else ", ".join(sug)) or ("无" if zh else "none")
        if zh:
            L.append("- " + tok + "（⚠ 本机没有这个技能：可能拼错、已改名或已删除。相近技能：" + joined +
                     "。请先如实告诉用户「本机没有这个技能」，把相近技能列出来让用户确认要不要改用；" +
                     "不要假装加载它，也不要凭名字编造它的流程。）")
        else:
            L.append("- " + tok + " (⚠ no such skill on this machine: misspelled, renamed or deleted. Close matches: " + joined +
                     ". Tell the user plainly that the skill does not exist, list the close matches and let them decide;" +
                     " never pretend to load it and never invent its workflow from the name.)")
    L.append("")
    return "\n".join(L) + "\n"


def _red_hit_emit(session, user_text: str) -> list:
    """P0-3：把本回合 RED 命中「为什么」推给前端（skill_hit），并在会话里留存。

    前端 chip 直接显示命中哪条触发词、走哪条规则；会话里的 _red_hits 供重连/刷新复现。
    未命中 → 不发事件（不打扰用户）。
    """
    try:
        hits = _match_red_skill_hits(user_text or "")
    except Exception:
        hits = []
    if not hits:
        return []
    payload = [{"name": h["name"], "keyword": h["keyword"], "rule": h["rule"], "level": "RED"} for h in hits]
    try:
        session["_red_hits"] = payload
    except Exception:
        pass
    try:
        _session_emit(session, {"type": "skill_hit", "skills": payload,
                                "ts": datetime.now().strftime("%H:%M:%S"),
                                "session_id": session.get("id")})
    except Exception:
        pass
    return hits


def _skill_invoke_emit(session, inv: dict) -> dict:
    """P0-3：显式 /skill-name 调用事件（skill_invoke）→ 前端回显点名结果。

    resolved / unknown / ambiguous 三类都要如实回显：用户输入的东西不能被静默丢弃。
    没有显式调用 → 返回 None 且不发事件。
    """
    if not isinstance(inv, dict):
        return None
    res = list(inv.get("resolved") or [])
    unk = list(inv.get("unknown") or [])
    amb = [dict(a) for a in (inv.get("ambiguous") or [])]
    ove = list(inv.get("overflow") or [])
    if not res and not unk and not amb and not ove:
        return None
    payload = {"type": "skill_invoke", "resolved": res, "unknown": unk, "ambiguous": amb,
               "overflow": ove,
               "suggestions": {t: _suggest_skills(t) for t in unk},
               "ts": datetime.now().strftime("%H:%M:%S"),
               "session_id": session.get("id")}
    try:
        _session_emit(session, payload)
    except Exception:
        pass
    return payload


# === P0-3 end ===

# === P8 end ===


# === 问题9: 进度语言一致性 — 会话级语言检测 + 文本映射表 ===
import re as _re_mod


def _detect_lang(text):
    """检测文本语言: 中文返回 'zh', 否则返回 'en'"""
    if not text:
        return "zh"  # 默认中文
    cjk = len(_re_mod.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text))
    ascii_alpha = len(_re_mod.findall(r'[a-zA-Z]', text))
    if cjk > 0 and cjk >= ascii_alpha:
        return "zh"
    if ascii_alpha > 0 and ascii_lang_ratio(text) > 0.7:
        return "en"
    return "zh"

def _user_lang_instruction(text):
    """显式语言指令: 返回 'en'/'zh'/None。
    用户说"用英文回答/answer in english"等 → 强制该语言并粘滞整个会话。"""
    t = (text or "").lower()
    en_kw = ("用英文", "用英语", "说英文", "说英语", "英文回答", "英语回答", "请用英文",
             "请用英语", "answer in english", "respond in english", "in english please",
             "english please", "write in english", "speak english")
    zh_kw = ("用中文", "说中文", "中文回答", "请用中文", "用汉语", "中文交流",
             # 2026-08-24 修复: 翻译类指令缺失 → "英文段落 + 翻译成中文" 被 _detect_lang 误判 en，
             # 导致 MemOmics 用英文回复翻译任务。翻译指令必须显式锁定中文。
             "翻译成中文", "翻译成汉语", "翻译成国语", "翻译一下", "中文翻译",
             "翻译为中文", "帮我翻译", "请翻译", "翻译这篇文章", "翻译这段",
             "翻译这个", "翻译这段话", "翻译一下这段", "翻译成中文吧",
             "answer in chinese", "respond in chinese", "in chinese please", "chinese please",
             "translate to chinese", "translate into chinese", "translate it to chinese",
             "say it in chinese", "speak chinese", "write in chinese")
    if any(k in t for k in en_kw):
        return "en"
    if any(k in t for k in zh_kw):
        return "zh"
    return None

def ascii_lang_ratio(text):
    """ASCII 字母占比"""
    total = len(text.strip())
    if total == 0:
        return 0
    return len(_re_mod.findall(r'[a-zA-Z]', text)) / total


def _auto_search_knowledge(user_text: str) -> str:
    """分析任务启动时自动预查知识库。从 user_text 提取物种/组织/方向，调用 search_knowledge。
    返回 JSON 或空字符串。失败时返回空，不阻断分析流程。
    """
    try:
        from memomics.bio_tools.kb_search import search_knowledge
        t = user_text.lower()
        # 提取物种
        species = ""
        for s in ["human", "人", "mouse", "小鼠", "rat", "大鼠", "zebrafish", "斑马鱼",
                   "drosophila", "果蝇", "c.elegans", "线虫", "arabidopsis", "拟南芥",
                   "pig", "猪", "monkey", "猴子", "macaque", "猕猴"]:
            if s in t or s.lower() in t:
                species = s
                break
        # 提取组织
        tissue = ""
        for ti in ["liver", "肝脏", "肝", "brain", "脑", "大脑", "lung", "肺", "heart", "心脏",
                    "kidney", "肾脏", "肾", "blood", "血液", "血", "spleen", "脾", "脾脏",
                    "intestine", "肠道", "肠", "skin", "皮肤", "muscle", "肌肉", "bone", "骨",
                    "marrow", "骨髓", "pancreas", "胰腺", "tumor", "肿瘤", "癌"]:
            if ti in t:
                tissue = ti
                break
        # 提取方向
        direction = ""
        for d in ["aging", "衰老", "cancer", "癌症", "development", "发育", "分化", "differentiation",
                   "immunity", "免疫", "inflammation", "炎症", "infection", "感染", "metabolism", "代谢",
                   "regeneration", "再生", "fibrosis", "纤维化", "apoptosis", "凋亡", "autophagy", "自噬",
                   "senescence", "衰老", "氧化应激", "oxidative stress"]:
            if d in t:
                direction = d
                break
        # 从方向再修一下 species（如"小鼠肝脏衰老"中"小鼠"可能被"衰老"的 sen- 部分匹配到 species）
        if not species:
            for s in ["human", "mouse", "小鼠", "rat", "大鼠"]:
                if s in t:
                    species = s
                    break
        
        query = user_text[:200]  # 截取前 200 字符
        result_json = search_knowledge(query=query, species=species, tissue=tissue, direction=direction)
        result = json.loads(result_json)
        if result.get("total", 0) == 0:
            return ""  # 无 KB 匹配，不注入空内容
        # 格式化 KB 结果为可读文本
        lines = [f"物种={species or '未识别'}, 组织={tissue or '未识别'}, 方向={direction or '未识别'}",
                 f"匹配条目: {result.get('total', 0)}"]
        for item in result.get("results", [])[:5]:
            fname = item.get("file", "")
            snippet = item.get("snippet", "")
            if fname:
                lines.append(f"\n### {fname}")
            if snippet:
                lines.append(str(snippet)[:500])
        return "\n".join(lines)
    except Exception:
        return ""  # 失败不阻断


def _detect_domain_from_text(text: str) -> str:
    """检测用户消息所属的领域（用于 skill 匹配优化）
    
    受 PantheonOS 团队路由启发：在会话级别确定领域上下文，
    帮助 LLM 缩小 skill 搜索范围。
    
    Returns:
        领域代码 (01_RNA, 02_ATAC, ...) 或空字符串（无法确定）
    """
    if not text:
        return ""
    t = text.lower()
    
    # 11 个领域的关键词映射
    domain_patterns = [
        ("01_RNA", ["scrna", "scrna-seq", "rna", "单细胞", "转录", "transcript", "rna-seq", "single cell", "单细胞rna", "gene expression", "基因表达", "cell type", "细胞类型", "clustering", "聚类", "umap", "tsne", "trajectory", "拟时序", "pseudotime", "velocity", "rna velocity", "qc", "质量控制", "cellbender", "细胞通讯", "cellchat", "cell chat", "cell-cell", "富集", "GO ", "KEGG", "pathway", "sctour"]),
        ("02_ATAC", ["atac", "atac-seq", "scatac", "chromatin", "染色质", "open chromatin", "peak calling", "motif", "cis-regulatory", "cre"]),
        ("03_空间组", ["spatial", "空间", "stereo-seq", "merfish", "xenium", "visium", "空间转录组", "spatial transcriptomics", "image"]),
        ("04_Bulk", ["bulk", "bulk rna", "bulk rna-seq", "rnaseq", "deseq2", "edger", "limma", "differential expression", "差异表达", "差异分析", "deg", "gsea", "通路", "pathway", "chip-seq", "wgbs", "全基因组", "whole genome"]),
        ("05_蛋白", ["protein", "蛋白", "proteomics", "质谱", "mass spec", "flow", "流式", "cytof", "western", "elisa", "immune", "免疫", "抗体", "antibody"]),
        ("06_微生物植物", ["microbiome", "微生物", "16s", "metagenomics", "宏基因", "bacteria", "菌群", "plant", "植物", "arabidopsis", "拟南芥", "crop"]),
        ("07_药物临床", ["drug", "药物", "clinical", "临床", "pharma", "pharmacology", "药理学", "disease", "疾病", "biomarker", "诊断", "diagnosis", "therapeutic", "治疗", "生存", "survival"]),
        ("08_报告", ["report", "html", "报告", "summary", "总结", "dashboard", "可视化", "visualization", "ppt", "pdf", "热图", "heatmap", "火山图", "volcano", "violin", "散点图", "scatter", "小提琴图"]),
        ("09_内置", ["function", "计算", "math", "stat", "统计", "test", "system", "系统"]),
        ("10_多组学整合", ["multi-omics", "multiomics", "多组学", "integrate", "整合", "multi-modal", "cross-omics", "联合分析", "wgcna", "network"]),
        ("11_文献搜索", ["literature", "文献", "paper", "论文", "search", "搜索", "pubmed", "find papers", "query", "检索"]),
    ]
    
    scores = []
    for domain, keywords in domain_patterns:
        score = 0
        for kw in keywords:
            if kw in t:
                score += 1
        if score > 0:
            scores.append((domain, score))
    
    if not scores:
        return ""
    
    # 按分数降序排列
    scores.sort(key=lambda x: -x[1])
    best_domain, best_score = scores[0]
    
    # 如果有两个以上的领域得分相同，不做决定
    top_count = sum(1 for _, s in scores if s == best_score)
    if top_count >= 2:
        return ""
    
    return best_domain


# === 自我介绍：不再有"写好的介绍"（2026-09-26 用户要求）===
# 历史做法：命中"介绍"类关键词就把一段固定文案直接发给用户（完全不经过大模型），
# 或者在提示词里硬要求"必须逐字输出"。两个问题：
#   1) 关键词误命中 —— "介绍一下我这个数据集/这段代码"也会被吃掉，答非所问；
#   2) 回答永远是同一段，不看上下文、不看用户当前进度、不看用户语言。
# 现在只保留一份"事实参考"给模型看（不是发给用户的成品文案），由模型结合上下文
# 自己组织回答：真在问身份就用这些事实自然作答，在问别的就正常回答那个问题。
_SELF_FACTS_ZH = (
    "关于 MemOmics 的真实事实（供你参考，不是要照抄的文案）：\n"
    "- 身份：基于 Hermes 框架的自进化多组学生信分析平台；不是聊天机器人，而是能自己扫描数据、分析、出报告的自主 Agent，用户不用写代码。\n"
    "- 数据扫描：自动识别 scRNA-seq / scATAC-seq / 空间转录组 / Bulk RNA-seq 等格式，检测物种、组织、细胞数、注释状态，推荐分析路径。\n"
    "- 完整流程：QC（去污染→双胞过滤→归一化）→ 降维 → 聚类 → 细胞注释 → 差异表达 → 通路富集 → 细胞通讯 → 轨迹推断 → SCENIC → 生存分析 → 报告生成。\n"
    "- 双引擎：默认 R/Seurat，数据量大于 60 万细胞自动切 Python/Scanpy；缺包自动安装（BiocManager/remotes/pip/conda）。\n"
    "- 技能库：内置 270+ 生信技能模板（Seurat、Scanpy、CellChat、Monocle3、SCENIC、CellBender、Harmony、squidpy 等），分析时自动套用对应技能的参数与模板。\n"
    "- 铁轨审查：环境检查 → 缺失包安装 → 参数校验 → 结果质量评估 → 图表检查 → 代码审查，不通过就阻断纠正。\n"
    "- 知识库：内置生信知识库（物种/组织/方向三维索引），分析时自动检索生物学背景并结合文献先验。\n"
    "- 结果管理：结果按 results/<模块>/<方法>/{figures,results,scripts,data} 分目录存放，可追溯可复现。\n"
)
_SELF_FACTS_EN = (
    "Facts about MemOmics (reference material, not text to copy verbatim):\n"
    "- Identity: a self-evolving multi-omics bioinformatics platform built on the Hermes framework; an autonomous agent that scans data, runs analyses and writes reports - users write no code.\n"
    "- Data scanning: auto-detects scRNA-seq / scATAC-seq / spatial transcriptomics / bulk RNA-seq, plus species, tissue, cell counts and annotation status; recommends an analysis path.\n"
    "- Pipeline: QC (decontamination -> doublet filtering -> normalization) -> dimensionality reduction -> clustering -> annotation -> DE -> pathway enrichment -> cell communication -> trajectory -> SCENIC -> survival analysis -> report.\n"
    "- Dual engine: R/Seurat by default, auto-switches to Python/Scanpy above 600K cells; auto-installs missing packages (BiocManager/remotes/pip/conda).\n"
    "- Skills: 270+ built-in bioinformatics skill templates (Seurat, Scanpy, CellChat, Monocle3, SCENIC, CellBender, Harmony, squidpy, ...).\n"
    "- Rail review: environment check -> package install -> parameter validation -> result quality -> figure check -> code review; blocks and corrects on failure.\n"
    "- Knowledge base: species/tissue/direction 3D index, combined with literature priors.\n"
    "- Results: stored under results/<module>/<method>/{figures,results,scripts,data}; traceable and reproducible.\n"
)

# === 图路由：意图分类 + 技能触发注入 ===
# 五级意图：self_intro > chat > research_plan > direct_exec > analysis
# SOUL.md 三级操作级别（轻量/统计/分析级）在 agent 内部独立判断，意图不覆盖
def _classify_intent(text: str):
    """五级意图识别。Returns: (intent, confidence, meta_dict)
    
    Intent flow:
      self_intro    — 身份/能力提问，正常走 LLM（按语境作答，不再有固定文案）
      chat          — 纯闲聊，不注入skill
      research_plan — 设计研究方案，文献驱动
      direct_exec   — 参数已定，直接执行（跳过规划，保留审查）
      analysis      — 标准分析流程（默认）
    """
    if not text:
        return ("chat", 0.0, {})
    t = text.lower().strip()
    meta = {}  # extra context for downstream handlers

    # === Priority 1: self-intro (fast-reply, no LLM) ===
    SELF_INTRO_KW = ["你是谁", "介绍你自己", "介绍下自己", "介绍你的", "你能做什么", "自我介绍",
                     "who are you", "what can you do", "introduce yourself"]
    if any(kw in t for kw in SELF_INTRO_KW):
        return ("self_intro", 0.99, {})
    # "介绍一下你自己/介绍一下你的功能"："绍"后跟"一"导致"介绍你自己"子串断链，
    # 用 "介绍一下"+人称 组合补齐（2026-08-14 实测）；纯"介绍一下Seurat怎么用"仍落 knowledge
    # 2026-08-27 修复：排除"我(先)(跟你/给你)介绍一下…"句式——用户主动介绍自己的
    # 进度/背景（主语=我），不是询问系统身份（实测："我先跟你介绍一下我当前的进度…"
    # 被误判 self_intro，正经分析问题走了自我介绍模板）
    if "介绍一下" in t and any(x in t for x in ["你", "自己", "你们"]):
        _pre = t[:t.index("介绍一下")].rstrip()
        # 排除"用户主动介绍"句式（主语=我）：我/我先/我跟你/我和你/我给大家/我向/让我/跟你/给你
        # 注意："给我/跟我/帮我/请你/我想让你"结尾的"我"不在此列——那是请求系统介绍（2026-08-27 实测边界）
        _user_intro = (_pre == "我") or _pre.endswith(("我先", "我跟你", "我和你", "我给大家", "我向",
                                                       "让我", "跟你", "给你"))
        if not _user_intro:
            return ("self_intro", 0.99, {})

    # === Priority 1.3: cancel_task (用户明确要求取消/停止任务) ===
    CANCEL_KW = ["取消任务", "取消分析", "停止任务", "停止分析", "不要跑了",
                 "停掉", "取消吧", "不跑了", "别跑了", "停下来", "暂停任务",
                 "cancel", "abort", "stop the task", "stop task",
                 "stop the analysis", "stop analysis",
                 "kill the job", "terminate",
                 ]
    if any(kw in t for kw in CANCEL_KW):
        return ("cancel_task", 0.90, {"reason": "explicit_cancel"})
    # 停止/暂停/取消/不要/别 + 任务相关词 → cancel
    # 2026-08-31 极端评测修复：粘贴的长引用文本（如千问评价"不要用这组基因…"）
    # 曾触发 cancel 误杀。改为"触发词 + 就近(10字内)任务词"组合，"不要用这组基因"不再命中。
    if any(kw in t for kw in ["停止", "暂停", "取消", "不要", "别"]) and (
        any(kw in t for kw in ["任务", "分析", "cellbender", "训练", "计算", "进程", "job"])
        and _re_mod.search(r"(停止|暂停|取消|不要|别)[^。！？!?\n]{0,10}(任务|分析|训练|计算|进程|跑了|继续|执行)", t)
    ):
        return ("cancel_task", 0.85, {"reason": "stop_with_context"})
    # 取消 + 任务相关词 → cancel（排除问句）
    if "取消" in t and not any(kw in t for kw in ["怎么", "如何", "什么", "为什么", "哪里"]):
        if any(kw in t for kw in ["任务", "分析", "跑", "之前", "正在", "全部"]):
            return ("cancel_task", 0.83, {"reason": "cancel_with_context"})

    # === 工具名常量（多处复用）===
    TOOL_NAMES = ["seurat", "scanpy", "deseq2", "edger", "limma", "monocle",
                  "cellchat", "cellbender", "harmony", "scenic", "sctransform",
                  "velocyto", "diffxpy", "clusterprofiler", "fgsea", "gseapy",
                  "scrublet", "soupX", "soupx", "doubletfinder", "archr", "signac"]
    _has_data_path_early = bool(_re_mod.search(r'[A-Za-z]:[/\\]\S+', t))

    # === Priority 1.5: knowledge_ask / progress_check / analysis_plan（在 chat fallback 之前）===
    # 这些意图即使消息很短也应该优先识别，避免被 short_no_bio 误判为 chat
    
    # 1.5a: progress_check
    PROGRESS_KW = ["还在跑吗", "还在运行", "跑完了吗", "跑完没", "进度", "怎么样了",
                   "什么状态", "现在状态", "目前状态", "任务状态", "当前状态", "现在情况",
                   "nvidia-smi", "gpu", "显卡", "显存", "内存",
                   "后台", "后台任务", "后台进程", "卡住了", "停了",
                   "还要多久", "多久了", "跑了多久", "跑多久", "跑到哪",
                   "check progress", "how long", "status", "still running",
                   # 2026-08-31 极端评测补丁：进度抱怨口语（"等了两天了还在跑"实测误判 chat）
                   # 注意：裸词"状态"太宽——引用文本"细胞功能状态"曾误触发 progress_check，
                   # 因此只保留短语形式（见上）。
                   "还在跑", "还在等", "等了两天", "等了几天", "还在弄", "跑了好几天", "还在转"]
    if any(kw in t for kw in PROGRESS_KW):
        return ("progress_check", 0.85, {"reason": "progress_or_status_query"})

    # 1.5a2: result_check —— 用户问"结果呢/出图了吗/结果在哪/还没结果"（过去时/产出查询），
    # 不是新任务、不是纯闲聊：路由到先查 task_plan + results_dir + 工具日志再回答的意图，
    # 避免被短句规则误判为 chat 后 Agent 只聊不查状态（2026-08-21 memomics-2274ab75 实测）。
    RESULT_KW = ["结果呢", "出结果", "结果出来", "出图了吗", "图出来了吗", "图呢",
                 "结果文件", "结果在哪", "产物", "还没有结果", "没有结果",
                 "结果怎么样", "结果如何", "出图没", "图好了吗", "图出来没",
                 "做完没", "完成没", "拿到结果", "给我结果", "看下结果",
                 "结果出来没", "结果做出来没", "图做好了没", "图在哪"]
    _result_neg_re = _re_mod.search(
        r"(怎么|为什么|为何|咋|干嘛|到底|还).{0,8}(没|不|还|未|没有).{0,8}(结果|图|输出|产物|报告|文件|东西)", t)
    _is_result_q = any(kw in t for kw in RESULT_KW) or bool(_result_neg_re)
    if _is_result_q and not _has_data_path_early:
        return ("result_check", 0.88, {"reason": "result_or_output_query"})

    # 1.5b: knowledge_ask（知识/错误/润色/参数问题 — 无数据路径）
    KNOWLEDGE_QUESTION_KW = ["什么意思", "是什么", "什么是", "参数", "怎么选",
                             "怎么设", "怎么调", "区别", "vs", "对比",
                             "推荐", "建议", "选哪个", "哪个好", "最佳",
                             "怎么用", "用途", "作用", "原理", "含义",
                             "解释", "说明", "介绍一下",
                             "哪些", "用什么方法", "怎么修", "怎么处理",
                             "润色", "怎么写", "如何选择", "如何设置",
                             "报错了", "不工作", "出错了", "失败了", "怎么解决",
                             "怎么算", "怎么算的", "怎么分", "怎么比较", "如何计算", "怎么算出来"]
    _has_knowledge_q = any(kw in t for kw in KNOWLEDGE_QUESTION_KW)
    _is_planning_q = any(kw in t for kw in ["怎么设计", "如何设计", "方案", "路线",
                                             "研究框架", "分析框架", "实验设计"])
    # 错误/修复上下文：即使有"跑"也不当执行动作
    _is_error_context = any(kw in t for kw in ["报错", "出错", "错误", "不工作", "失败", "怎么修", "怎么解决"])
    # 2026-08-25: 调查/诊断类问句（"检查为什么报错"/"看看日志分析原因" → 只调查不执行，
    # DSH 用户优先策略迁移）。调查信号词本身即触发，不要求伴随"报错"字样。
    _INVESTIGATE_KW = ["为什么", "为何", "原因", "检查一下", "排查", "诊断", "调查一下",
                       "看下.*日志", "看下.*报错", "分析.*原因", "查一下.*报错", "查一下.*日志",
                       "什么问题", "哪里出错", "怎么挂的", "怎么失败的", "为何失败",
                       "什么原因", "出错原因", "失败原因", "怎么发生", "怎么出现"]
    _is_investigate = any(
        _re_mod.search(p, t) if ("*" in p or "." in p) else p in t
        for p in _INVESTIGATE_KW)
    if _is_investigate:
        return ("investigate", 0.82, {"reason": "error_investigation_request"})
    _has_exec_action = not _is_error_context and any(kw in t for kw in 
        ["跑", "执行", "运行", "帮我做", "开始做", "run ", "start ", "do ", "execute"])
    if _has_knowledge_q and not _has_data_path_early and not _has_exec_action and not _is_planning_q:
        return ("knowledge_ask", 0.82, {"reason": "knowledge_question_no_data"})
    # 工具名 + 参数问句 → knowledge_ask
    TOOL_PARAM_ASK = ["参数", "argument", "option", "flag", "设置"]
    _has_tool_kw = any(tool in t for tool in TOOL_NAMES)
    _has_param_ask = any(kw in t for kw in TOOL_PARAM_ASK)
    if _has_tool_kw and _has_param_ask and not _has_data_path_early:
        return ("knowledge_ask", 0.84, {"reason": "tool_param_question"})

    # 1.5c: analysis_plan（技术路线图/分析方案 — 无数据路径）
    ANALYSIS_PLAN_KW = ["技术路线", "分析路线", "路线图", "流程图",
                        "怎么做.*分析", "分析流程", "分析步骤",
                        "数据.*怎么分析", "怎么分析.*数据",
                        "atac.*路线", "rna.*路线", "单细胞.*路线",
                        "pipeline", "workflow", "分析框架"]
    _has_plan_query = any(kw in t for kw in ANALYSIS_PLAN_KW)
    _has_plan_regex = any(_re_mod.search(pat, t) for pat in [
        r"怎么做.*分析", r"分析流程", r"分析步骤", r"分析路线",
        r"数据.*怎么分析", r"怎么分析.*数据",
        r"atac.*路线", r"rna.*路线", r"单细胞.*路线",
    ])
    if (_has_plan_query or _has_plan_regex) and not _has_data_path_early:
        return ("analysis_plan", 0.85, {"reason": "analysis_roadmap_query"})

    # === Priority 1.8: install / kb 动作意图（先于 short_no_bio，避免短句误判为 chat）===
    # 2026-08-14 实测："安装cellbender"/"创建一个新skill" 曾被 short_no_bio 误判为 chat
    INSTALL_EARLY_KW = ["安装", "install", "配置环境", "setup", "依赖", "dependency",
                        "创建skill", "create skill", "新skill", "新 skill", "注册skill"]
    _is_install_q = any(kw in t for kw in ["怎么安装", "如何安装", "怎么装", "如何装",
                                            "怎么配置", "如何配置", "怎么搭建", "如何搭建"])
    if _is_install_q:
        # "这个包怎么安装" → 问方法，不是装包动作（2026-08-14 实测）
        return ("knowledge_ask", 0.84, {"reason": "install_method_question"})
    if any(kw in t for kw in INSTALL_EARLY_KW):
        return ("install", 0.88, {"reason": "install_action_early"})
    if ("装" in t or "配置" in t) and any(tool in t for tool in TOOL_NAMES):
        # "装cellbender" / "配置seurat" → install
        return ("install", 0.86, {"reason": "install_tool_early"})
    KB_EARLY_KW = ["知识库", "knowledge base", "knowledgebase"]
    if any(kw in t for kw in KB_EARLY_KW):
        return ("knowledge", 0.85, {"reason": "kb_action_early"})

    # === Priority 1.9: 查看/检查类动作（有数据路径 → analysis，2026-08-14 实测）===
    # "检查一下E:/data/里的表达矩阵" 原先无任何 kw 命中 → chat
    VIEW_EARLY_KW = ["检查一下", "检查", "查看", "看看", "看一下", "打开"]
    if any(kw in t for kw in VIEW_EARLY_KW) and _has_data_path_early:
        return ("analysis", 0.85, {"reason": "view_inspect_with_data"})

    # === Priority 1.95: 交付类执行短句（2026-08-31 极端评测补丁）===
    # "把人和猴脑对齐的亚群和基因给我"/"把8大类的基因都给我"/"帮我整理一下它的数据"
    # 这类是明确的执行请求，此前无路径无生物词，被 short_no_bio 误判 chat。
    # 排除：问句（"怎么弄"）、解释类（"讲讲/解释"）、无任务名词的纯闲聊。
    _EXEC_NOUNS = ("代码", "表格", "基因", "亚群", "注释", "marker", "文件", "清单",
                   "脚本", "结果", "数据", "列表", "报告", "名字", "命名")
    # 注意：不含"方案"——"给我方案"是规划请求（research_plan），2026-08-31 实测误伤
    _has_exec_noun = any(n in t for n in _EXEC_NOUNS)
    _is_exec_deliver = any(k in t for k in ("给我", "帮我整理", "帮我列", "列出来", "列出", "整理一下"))
    _is_question = any(k in t for k in ("怎么", "如何", "为什么", "多少", "什么", "哪", "? ", "？"))
    # 决策征询句不是执行请求（"你觉得…还是…给我方案" → research_plan）
    _is_consult = any(k in t for k in ("你觉得", "还是", "给我方案", "建议", "推荐"))
    if _is_exec_deliver and _has_exec_noun and not _is_question and not _has_data_path_early \
            and not _is_consult:
        return ("direct_exec", 0.82, {"reason": "deliverable_exec_short"})

    # === Priority 2.6: 单篇文献解读/总结（先于 chat 与 research_plan，2026-08-24 修复）===
    # 问题(memomics-aa368e59 同类实测): "让我知道作者的研究思路，做了什么" 含 PLAN_KW
    # '研究思路' → 被误判 research_plan → 强制 3 工具调研(skill_view academic-research +
    # search_knowledge + search_papers) + memomics_pipeline，用户只要精读总结单篇文献。
    # 此外短句 "这篇文章讲了什么"(8字) / "帮我概括这篇文章的核心要点"(14字) 会被
    # short_no_bio 规则(<15字→chat) 拦截——所以本分支必须放在 Priority 2 chat 之前。
    # 这里是文献解读，不是方案设计：命中"这篇X + 解读类动词"→ 直接 literature，轻量精读。
    _PAPER_READ_INDIC = ["这篇文章", "这篇文献", "这篇论文", "该文献", "该文章", "该论文",
                         "说一下这篇文章", "讲讲这篇文章", "介绍这篇文章", "解读这篇文章",
                         "总结这篇文章", "总结一下这篇文章", "总结一下这篇", "精读",
                         "概括这篇文章", "概括这篇", "概括一下这篇文章", "核心要点",
                         "这篇文章讲", "这篇文献讲", "这篇论文讲", "讲了什么", "说了什么",
                         "评价这篇文章", "评价这篇", "怎么评价这篇", "如何评价这篇",
                         "作者做了什么", "作者的研究思路", "研究思路，做了什么",
                         "review this paper", "summarize this paper", "explain this paper",
                         "summarize this article", "review this article"]
    if any(kw in t for kw in _PAPER_READ_INDIC):
        # 排除：明确要基于该文献做方案/分析/写作 → 不抢（落 research_plan / analysis / literature 写作分支）
        _excl_paper_plan = any(kw in t for kw in ["设计方案", "研究方案", "实验设计", "分析", "跑",
                                                  "执行", "写论文", "写成方案", "怎么做", "如何设计",
                                                  "design", "analy", "write a"])
        if not _excl_paper_plan:
            return ("literature", 0.90, {"reason": "single_paper_reading"})

    # === Priority 2: chat (non-bioinfo, casual) ===
    CHAT_KW = ["你好", "嗨", "hello", "hi", "谢谢", "感谢", "再见", "拜拜",
               "天气", "今天天气", "怎么样", "好吗",
               "怎么用", "如何使用", "能不能", "可不可以",
               "有趣", "好玩", "厉害", "牛逼", "哈哈", "呵呵",
               "吃饭", "睡觉", "周末", "节日", "放假",
               "你觉得", "你认为", "你的看法",
               "好烦", "烦死了", "气死", "无语", "崩溃", "心态",
               "加油", "辛苦了", "太棒了", "nice", "good job"]
    BIO_KW = ["分析", "跑", "做", "执行", "计算", "画图", "出图",
              "处理", "统计", "差异", "富集", "聚类", "降维", "注释",
              "数据", "基因", "细胞", "表达", "qc", "deg", "rna", "atac",
              "方案", "设计", "规划", "思路", "路线", "seq", "蛋白", "药物",
              "umap", "tsne", "可视化", "热图", "火山图", "小提琴图", "散点图",
              "轨迹", "通路", "通讯", "调控", "模块",
              "结果", "输出", "文献", "文献综述", "专利", "patent", "法律", "申报", "论文", "报告", "综述",
              # 画图/出图相关
              "画", "图", "柱状图", "箱线图", "折线图", "分布图", "相关性矩阵",
              "dotplot", "featureplot", "spatialplot", "sankey", "violin",
              "figure", "投稿", "发表", "期刊", "cns", "nature",
              "配色", "legend", "坐标轴", "字体", "分辨率", "dpi"]
    has_chat = any(kw in t for kw in CHAT_KW)
    has_bio = any(kw in t for kw in BIO_KW)
    if has_chat and not has_bio:
        return ("chat", 0.90, {"reason": "casual_no_bio"})
    if not has_bio and len(t) < 15:
        return ("chat", 0.70, {"reason": "short_no_bio"})

    # === Priority 3: research_plan (literature-driven plan design) ===
    # 先检查 plan_refine 关键词（如'生成方案'），避免被 PLAN_KW 抢先
    REFINE_KW = ["生成方案", "出方案", "出完整方案", "出研究方案", "生成研究方案",
                 "开始做", "开始方案",
                 "帮我写", "写成方案", "做方案", "生成完整", "出完整"]
    if any(kw in t for kw in REFINE_KW):
        if "论文" in t or "文献" in t or "报告" in t or "综述" in t:
            pass  # 写作类落 P5 literature/report，不是方案（2026-08-14 实测"帮我写论文"）
        else:
            return ("plan_refine", 0.88, {"phase2": True})
    PLAN_KW = ["设计方案", "出个方案", "出方案", "规划一下", "规划",
               "查文献", "找文献", "文献调研",
               "实验设计", "研究设计", "研究思路", "分析路线", "分析策略",
               "下一步做", "接下来做", "下一步怎么", "接下来怎么",
               "怎么设计", "如何设计", "方案设计",
               "研究框架", "分析框架", "科研设计", "课题设计",
               "设计研究方案", "研究方案", "设计分析方案", "分析方案",
               "研究计划", "实验方案", "制定方案", "设计一个方案",
               "帮忙设计", "给我设计", "制定分析", "设计.*方案",
               "多组学.*整合", "整合.*数据", "整合分析",
               "新细胞群", "未知群", "新群体", "鉴定.*群体",
               "novel", "unknown cluster", "rare population",
               "atac.*rna.*整合", "rna.*atac.*整合",
               "怎么研究", "如何研究", "研究这个", "深入分析",
               "atac.*和.*rna", "rna.*和.*atac", "怎么.*鉴定",
               "表征", "验证这个群", "发育过程", "细胞命运",
               "加入.*分析", "加上.*分析", "加入.*组学"]
    # 重新生成/不满意 → force plan_refine (not research_plan)
    REGEN_KW = ["重新生成", "换个方案", "不满意", "重新设计", "方案不行", "方案不好"]
    if any(kw in t for kw in REGEN_KW):
        return ("plan_refine", 0.90, {"regen": True, "reason": "用户不满意当前方案"})
    if any(kw in t for kw in PLAN_KW):
        meta["modalities"] = _detect_modalities_from_text(t)
        return ("research_plan", 0.92, meta)
    # regex fallback for patterns like "多组学.*整合"
    PLAN_RE = ["多组学.*整合", "整合.*数据", "鉴定.*群体",
               "atac.*rna.*整合", "rna.*atac.*整合", "atac.*和.*rna",
               "rna.*和.*atac", "怎么.*鉴定", "设计.*方案"]
    for pat in PLAN_RE:
        if _re_mod.search(pat, t):
            meta["modalities"] = _detect_modalities_from_text(t)
            return ("research_plan", 0.90, meta)
    # "设计" + "方案" 同时出现在文中（宽松匹配）
    if ("设计" in t or "制定" in t) and ("方案" in t or "路线" in t or "思路" in t):
        meta["modalities"] = _detect_modalities_from_text(t)
        return ("research_plan", 0.88, meta)
    # === Priority 3.5: direct_exec (checked before ANALYSIS_INTENT_KW to avoid ambiguity) ===
    DIRECT_KW_2 = ["直接跑", "直接执行", "直接做", "照这个做", "按这个做",
                 "参数写好了", "确定了", "代码写好了", "已经写好了",
                 "就按这个", "只用执行", "照着做", "就做这个", "只做这个",
                 "就按参数", "就这个参数", "跑一下就行", "直接按",
                 "做吧", "就按这个做吧", "照这个方案做", "照这个来"]
    if any(kw in t for kw in DIRECT_KW_2):
        return ("direct_exec", 0.90, {"skip_planning": True})
    
    # 工具名直接使用检测："用Seurat做" → analysis（必须在ANALYSIS_INTENT_KW之前）
    if any(f"用{tool}" in t or f"with {tool}" in t or f"run {tool}" in t for tool in TOOL_NAMES):
        return ("analysis", 0.88, {"reason": "direct_tool_usage"})
    if any(tool in t for tool in TOOL_NAMES):
        # Tool name present without plan keywords → analysis
        has_plan = any(kw in t for kw in ["方案","设计","路线","思路","怎么","如何","规划","框架"])
        if not has_plan:
            return ("analysis", 0.84, {"reason": "specific_tool_no_plan"})
    # 数据分析需求检测：用户说"我要分析/想分析/帮分析XXX" → research_plan
    ANALYSIS_INTENT_KW = [
        "我要分析", "我想分析", "帮我分析", "帮我看", "分析一下",
        "看看这个数据", "看一下数据", "探索数据", "数据探索",
        "数据分析方案", "分析思路", "该怎么分析", "该怎么办",
        "想分析", "要做分析", "需要分析", "分析需求",
        "研究一下", "看一下数据", "帮我看看",
        "做分析", "做数据分析", "跑分析", "跑一下",
        "预处理", "做预处理", "进行", "做个分析",
        "看看结果", "帮我解读", "给我分析", "数据在哪里",
        "空间组", "蛋白", "蛋白质", "微生物组", "代谢组", "脂质组", "药物组",
        "atac测序", "基因组测序", "芯片数据", "药物筛选",
        "蛋白表达", "多组学", "单细胞测序", "空间转录组",
        # English equivalents
        "i want to analyze", "i need to analyze", "can you analyze",
        "help me analyze", "help me design", "design a plan",
        "design an analysis", "make a plan", "create a plan",
    ]
    if any(kw in t for kw in ANALYSIS_INTENT_KW):
        # 2026-08-14 实测：执行/查看动作 + 数据路径 → 直接 analysis，不再误判 research_plan
        EXEC_ACTION_KW = ["跑一下", "跑分析", "做分析", "做个分析", "做数据分析",
                          "预处理", "做预处理", "分析一下", "帮我分析", "给我分析",
                          "帮我看看", "帮我看", "看看这个数据", "看一下数据", "探索数据", "数据探索"]
        if any(kw in t for kw in EXEC_ACTION_KW) and _has_data_path_early:
            return ("analysis", 0.85, {"reason": "exec_action_with_data"})
        meta["modalities"] = _detect_modalities_from_text(t)
        return ("research_plan", 0.82, meta)
    # Questions about HOW to analyze (must fire before lit/kb/report)
    if "怎么分析" in t or "如何分析" in t or "怎样分析" in t:
        meta["modalities"] = _detect_modalities_from_text(t)
        return ("research_plan", 0.85, meta)
    if "怎么做" in t:
        meta["modalities"] = _detect_modalities_from_text(t)
        return ("research_plan", 0.84, meta)


    # === Priority 5: report / literature / install (existing intents, preserved) ===
    report_kw = ["html", "报告", "report", "做报告", "生成报告", "分析报告",
                  "总结报告", "生成html", "html报告", "做ppt", "slides"]
    install_kw = ["安装", "install", "配置", "配置环境", "setup", "依赖", "dependency",
                  "创建skill", "create skill", "新skill", "新 skill", "注册skill", "创建"]
    lit_kw = ["文献", "论文", "literature", "paper", "pubmed", "下载论文",
              "找文献", "查论文", "搜索文献", "search paper", "find paper",
              "专利", "patent", "知识产权", "权利要求", "ip", "技术交底", "综述"]
    kb_kw = ["知识库", "knowledge", "搜索知识", "查找方法", "protocol", "流程"]
    
    rpt_s = sum(1 for kw in report_kw if kw in t)
    ins_s = sum(1 for kw in install_kw if kw in t)
    lit_s = sum(1 for kw in lit_kw if kw in t)
    kb_s = sum(1 for kw in kb_kw if kw in t)
    
    if rpt_s >= 1:
        # 如果同时有分析+数据路径，不是纯报告请求
        _has_analysis_kw = any(kw in t for kw in ["分析", "执行", "跑", "流程", "analyze", "pipeline"])
        _has_data = bool(_re_mod.search(r'[A-Za-z]:[/\\]\S+', t))
        if not (_has_analysis_kw and _has_data):
            return ("report", min(rpt_s * 0.3, 1.0), {})
    if lit_s >= 2 or (lit_s >= 1 and ins_s == 0):
        return ("literature", min(lit_s * 0.4, 1.0), {})
    if lit_s >= 1:
        return ("literature", 0.5, {})
    if ins_s >= 1:
        return ("install", min(ins_s * 0.4, 1.0), {})
    if kb_s >= 1:
        # 如果有数据路径+分析关键词，不是纯知识库查询
        _has_path = bool(_re_mod.search(r'[A-Za-z]:[/\\]\S+', t))
        _has_analysis = any(kw in t for kw in ["分析", "执行", "跑", "流程", "analyze", "pipeline", "处理", "测序"])
        if not (_has_path and _has_analysis):
            return ("knowledge", min(kb_s * 0.3, 1.0), {})

    # === Default: analysis (standard bioinfo flow) ===
    analysis_kw = [
        "分析", "analysis", "建库", "测序", "seq", "组学", "omics",
        "差异", "differential", "聚类", "clustering", "轨迹", "trajectory",
        "批次", "batch", "整合", "integration", "harmony", "注释", "annotation",
        "富集", "enrichment", "gsea", "go ", "kegg", "pathway",
        "qc", "质量控制", "cellbender", "deg", "scrna", "rna ",
        "atac", "空间", "spatial", "蛋白", "protein", "药物", "drug",
        "拷贝数", "cnv", "细胞通讯", "cell chat", "cellchat", "cell-cell",
        "拟时序", "pseudotime", "velocity", "rna velocity",
        "单细胞", "single cell", "sc-", "10x", "多组", "multiom",
        "降维", "umap", "tsne", "pca", "标准化", "normalize",
        "统计", "survival", "机器学习", "machine learning",
        "比对", "alignment", "peak", "motif", "mutation", "突变",
        "基因编辑", "crispr", "质粒", "plasmid", "引物", "primer",
        "酶切", "restriction", "表达量", "expression", "热图", "heatmap",
        "火山图", "volcano", "小提琴", "violin", "cns", "nature",
        "探索一下", "探索这个数据", "结果怎么样", "结果如何",
        "看看结果", "结果", "出结果", "跑完", "跑得",
        # 画图出图
        "画", "图", "figure", "plot", "chart", "graph",
        "柱状图", "箱线图", "散点图", "折线图",
        "dotplot", "featureplot", "sankey", "配色",
        "投稿", "发表", "期刊", "manuscript",
    ]
    analysis_s = sum(1 for kw in analysis_kw if kw in t)
    if analysis_s >= 2:
        return ("analysis", min(analysis_s * 0.15, 1.0), {})
    if analysis_s >= 1:
        # 边界情况：单独一个分析关键词 + 情绪词 → chat（如"分析跑崩了 好烦"）
        EMOTION_KW = ["好烦", "烦死了", "气死", "无语", "崩溃", "心态", "加油", "辛苦了",
                      "好看", "好美", "漂亮", "厉害", "牛逼", "太棒了", "nice", "good job",
                      "好好看", "好漂亮", "好厉害", "太强了"]
        _has_emotion = any(kw in t for kw in EMOTION_KW)
        if _has_emotion and analysis_s == 1:
            return ("chat", 0.60, {"reason": "analysis_ref_with_emotion"})
        return ("analysis", 0.50, {})

    return ("chat", 0.0, {})


def _detect_modalities_from_text(text: str) -> list:
    """Quick modality detection for routing before agent runs."""
    t = text.lower()
    mods = []
    if any(kw in t for kw in ["scrna", "单细胞", "single cell", "10x", "seurat", "scanpy"]):
        mods.append("scrna")
    if any(kw in t for kw in ["atac", "scatac", "开放染色质", "chromatin", "archr", "signac"]):
        mods.append("scatac")
    if any(kw in t for kw in ["bulk rna", "bulk-rna", "转录组测序", "rna-seq", "rnaseq", "deseq2", "edger"]):
        mods.append("bulk_rna")
    if any(kw in t for kw in ["蛋白", "proteom", "质谱", "蛋白质", "docking", "ppp"]):
        mods.append("proteomics")
    if any(kw in t for kw in ["药物", "drug", "靶点", "靶向", "admet", "重定位"]):
        mods.append("drug")
    if any(kw in t for kw in ["微生物", "microbiom", "菌群", "16s", "宏基因"]):
        mods.append("microbiome")
    if any(kw in t for kw in ["空间", "spatial", "visium"]):
        mods.append("spatial")
    if any(kw in t for kw in ["脂质", "lipidom"]):
        mods.append("lipidomics")
    if any(kw in t for kw in ["gwas", "遗传", "变异", "variant", "mendelian", "prs"]):
        mods.append("genetics")
    if any(kw in t for kw in ["生存", "survival", "cox", "kaplan", "预后"]):
        mods.append("clinical")
    return mods if mods else ["scrna"]


def _build_kb_tail_injection(user_text: str, intent: str, is_heavy: bool) -> str:
    """KB 预查询 + 领域路线引导 → 尾部 system 消息（2026-08-21 缓存优化）。

    原实现注入 ephemeral_system_prompt（= 请求前缀头部），内容随用户消息变化，
    每次回合都破坏 DeepSeek 前缀缓存（实测连续回合命中率仅 12-22%）。
    改为返回文本，由调用方作为历史末尾的 system 消息追加——前缀保持稳定，
    REQUIREMENTS/索引更新也不会再让整段前缀失效。
    """
    if not is_heavy:
        return ""
    try:
        _kb_result = _auto_search_knowledge(user_text)
        if _kb_result and ('"total": 0' not in _kb_result.split('\n')[0] if _kb_result else False):
            return (
                "\n\n## 📚 知识库预查询（线索，非文献来源）\n"
                "以下是系统自动从知识库检索的内容，**仅作为分析线索和背景参考**。\n"
                "⚠️ KB 中的文献引用可能缺少 PMID/DOI，**不可直接作为辩论引用来源**。\n\n"
                "**铁律 5 强制要求**：\n"
                "1. 辩论前必须先调 `search_papers()` 获取带 PMID/DOI 的真实文献\n"
                "2. KB 内容作为 `knowledge_base_info` 传入辩论，提供生物学背景\n"
                "3. 辩论中**只能引用 search_papers 返回的真实文献**\n\n"
                + _kb_result
            )
        if intent in ("analysis", "research_plan", "analysis_plan"):
            _detected_domain = _detect_domain_from_text(user_text)
            _domain_hint = f"（系统推断领域: {_detected_domain}）" if _detected_domain else ""
            _domain_list = f"skill_list_by_domain(domain=\"{_detected_domain}\")" if _detected_domain else "skill_list_by_domain(domain=<推断的领域>)"
            return (
                f"\n\n## 📋 分析路线引导（KB 无精确匹配，请使用 Skill 体系）{_domain_hint}\n"
                "当前知识库中未找到精确匹配。请**不要用预训练知识编造**，按以下步骤从 skill 体系构建路线：\n\n"
                f"1. **按领域精确查询**：调用 `{_domain_list}` 列出该领域所有技能\n"
                "2. **关键词搜索**：调用 `skill_search(query=\"<用户问题核心词>\")` 补充搜索\n"
                "3. **加载关键 skill**：对匹配的 skill 调用 `skill_view(name=\"skill名\")` 获取方法论、参数、参考文献\n"
                "4. **从 skill 构建路线图**：skill 中的 Pipeline/Workflow 节 = 分析路线图；References 节 = 文献支撑\n"
                "5. **必要时补充文献**：skill 中的 References 可能不够新 → 调 `search_papers()` 补充最新文献\n\n"
                f"⛔ 领域限定：用户问题推断为 {_detected_domain or '通用'} 领域，请只查询该领域相关 skill。\n"
                "⛔ 不要用 LLM 预训练知识凭空编造分析路线。skill_index 里的 368 个 skill 是权威来源。"
            )
    except Exception:
        pass
    return ""


def _build_skill_injection(intent: str, domain: str, session_lang: str = "zh", user_text: str = "",
                           pinned: list = None, explicit: dict = None) -> str:
    """根据意图+领域构建系统指令（硬注入，LLM无法跳过）

    P8: pinned = 用户在本会话置顶的 skill 名字列表（优先而非独占，见 _build_pinned_skill_block）。
    P0-3: explicit = _parse_skill_invocations 的解析结果（用户斜杠点名）。优先级：
          显式调用 > 置顶技能 > RED 自动命中——三段注入按这个顺序拼接。
    """
    # === RED 必触发预检：用户消息命中 RED skill 触发词 → 前置强约束先 skill_view ===
    # 审稿/润色/拆解等文献类任务常被意图分类器分到弱约束分支（literature/chat），
    # agent 会跳过 skill_view 直接按固有知识处理。这里在意图注入之外兜底：
    # 命中 RED 触发词 → 注入最高优先级指令，强制先加载对应 skill。
    # 注意：不覆盖原意图注入，作为前置段拼接。
    # P0-3: 用户斜杠点名的技能（显式调用）——最高优先级，先于置顶与 RED 注入
    explicit_inv = explicit if isinstance(explicit, dict) else _parse_skill_invocations(user_text)
    explicit_prefix = _build_explicit_skill_block(explicit_inv, session_lang)
    red_prefix = ""
    red_hits = _match_red_skill_triggers(user_text)
    # P8: 置顶 skill 块 —— 优先级高于自动路由；命中触发词时预载 SKILL.md 全文
    pinned_prefix = _build_pinned_skill_block(pinned or [], user_text, session_lang)
    if red_hits:
        zh = session_lang == "zh"
        red_prefix = "\n".join([
            "【系统指令：RED 必触发 skill 检测 — 最高优先级，不可跳过】",
            f"检测到用户消息命中以下必触发技能：{', '.join(red_hits)}",
            "你必须按以下顺序执行：",
            "1. 立即调用 skill_view(name='<命中的技能名>') 加载该技能的完整指令（Pipeline/Workflow/规则段），禁止跳过、禁止凭固有知识直接处理！",
            "2. 严格按 skill 指令执行任务。",
            "3. 若需要材料（文件/文本）而用户未提供，先向用户索要，不要自行猜测或跳过。",
            "⛔ 禁止在 skill_view 之前调用 OCR/搜索/terminal 等替代手段绕开本指令。",
            "",
        ] if zh else [
            "【SYSTEM: RED mandatory skill detected — highest priority, do not skip】",
            f"User message matches mandatory skills: {', '.join(red_hits)}",
            "You MUST execute in this order:",
            "1. Immediately call skill_view(name='<matched skill>') to load its full instructions (Pipeline/Workflow/rules). Do NOT skip it or rely on your own knowledge!",
            "2. Follow the skill instructions strictly.",
            "3. If materials (files/text) are needed but not provided, ask the user — do not guess or skip.",
            "⛔ Do NOT call OCR/search/terminal as a workaround BEFORE skill_view.",
            "",
        ]) + "\n"
    if intent == "chat":
        return explicit_prefix + pinned_prefix + red_prefix
    if intent == "self_intro":
        # 2026-09-26: 不再硬注入"必须逐字输出"的成品文案 —— 改成给模型事实参考 +
        # 语境判断要求，由模型决定怎么答（这才是"结合上下文语境"）。
        return explicit_prefix + pinned_prefix + red_prefix + (
            "【身份问题参考资料 —— 先判断用户在问什么，再决定怎么答】\n"
            "判断规则：\n"
            "1) 用户在问你的身份/能力（你是谁、你能做什么、介绍一下你自己…）：用下面的事实结合当前对话语境自然作答。"
            "用户已经知道的不必重复；他正在做的事可以顺带对上（例如刚给了数据、刚跑完某一步）。"
            "用用户的语言回答，篇幅按问题大小来，不要整段照抄。\n"
            "2) 用户其实在问别的（某个数据集/代码/流程/结果文件/参数）：正常回答那个问题，不要输出能力清单，也不要自我介绍。\n"
            "3) 拿不准时按用户字面问题回答。\n\n"
            + (_SELF_FACTS_ZH if session_lang == "zh" else _SELF_FACTS_EN) + "\n"
        )
    zh = session_lang == "zh"
    lines = ["【系统指令：自动路由 - 必须遵守】",
             f"意图类型：{intent} | 领域：{domain or '自动检测'}", ""]
    
    if intent in ("cancel_task",):
        lines += [
            "⛔ 用户要求取消/停止任务。这是最高优先级指令。",
            "你必须立即执行以下操作（不等、不问、不继续当前工作）：",
            "1. 确认目标：回复用户正在停止的任务名称",
            "2. task_plan.md → 所有 in_progress 的 Phase → 改为 **Status:** cancelled",
            "3. cronjob(action='pause'|'remove') — 停止心跳监控",
            "4. terminal('taskkill /F /PID <PID>') — 杀掉后台计算进程",
            "5. 回复用户：'已停止。<任务名>的 task_plan 已标记 cancelled，心跳已停，进程已杀。'",
            "⛔ 不要问'确定吗？'。用户已经说取消了，直接执行。",
            "⛔ 如果有多个任务在跑，先确认用户要停哪个，再停。",
            "",
        ] if zh else [
            "⛔ User requested task cancellation. Highest priority.",
            "1. Confirm which task to stop",
            "2. task_plan.md → mark all in_progress as cancelled",
            "3. cronjob(action='pause'|'remove') — stop heartbeat",
            "4. terminal('taskkill /F /PID <PID>') — kill background processes",
            "5. Report: 'Stopped. task_plan cancelled, heartbeat stopped, processes killed.'",
            "",
        ]
    
    elif intent in ("knowledge_ask",):
        lines += [
            "用户正在询问知识/参数问题。这不是分析任务执行。",
            "🔴 铁律 -4：涉及生信/生物/医学的专业知识，禁止仅靠预训练知识回答！",
            "1. 先调用 search_knowledge() 搜索本地知识库",
            "2. 再调用 search_papers() 搜索 PubMed 文献（至少找 1-2 篇验证）",
            "3. 必要时 web_search() 或 web_extract() 查官方文档/最新资料",
            "4. 交叉验证后给出准确答案，标注信息来源",
            "📚 回答格式：正文后附 '📚 参考来源：' 列出 KB/PMID/URL",
            "⛔ 不要创建 task_plan。不要输出触发检查清单。不要追问'要不要跑'。",
            "⛔ 不要调用 terminal 执行代码。这是纯知识问答。",
            "⛔ 不要仅凭预训练知识回答专业问题——不查就答 = 可能编造。",
            "",
        ] if zh else [
            "User is asking a knowledge/parameter question. This is NOT an analysis execution.",
            "🔴 Iron Law -4: For bioinformatics/biology/medicine questions, NEVER answer from pretrained knowledge alone!",
            "1. Call search_knowledge() to search the local knowledge base",
            "2. Call search_papers() to search PubMed (at least 1-2 papers for verification)",
            "3. Use web_search()/web_extract() for official docs/latest info if needed",
            "4. Cross-validate and cite your sources",
            "📚 Format: answer body + '📚 References:' with KB/PMID/URL",
            "⛔ Do NOT create task_plan. Do NOT output trigger checklist.",
            "⛔ Do NOT call terminal. This is pure knowledge QA.",
            "⛔ NEVER answer professional questions from pretrained knowledge alone.",
            "",
        ]
    
    elif intent in ("progress_check",):
        lines += [
            "用户正在查询进度/状态。只做三源交叉验证，不做分析。",
            "⛔ 即使你认为答案显而易见（如'没有后台任务'），也必须调工具验证！",
            "⛔ 不调工具直接说'没有' = 违反铁律-2（不查就答=撒谎）。",
            "1. terminal('nvidia-smi') — GPU状态",
            "2. terminal('tasklist | findstr cellbender') 或 process(action='list') — 进程",
            "3. search_files 或 terminal('dir <输出目录>') — 磁盘产出",
            "三个查完 → 交叉验证一致 → 才能开口汇报。",
            "⛔ 不要新建 task_plan。不要启动新任务。",
            "",
        ] if zh else [
            "User is checking progress. Three-source verification REQUIRED.",
            "⛔ Even if the answer seems obvious (e.g. 'no tasks'), you MUST call tools!",
            "1. terminal('nvidia-smi') — GPU",
            "2. terminal('tasklist') or process(action='list') — processes",
            "3. search_files or terminal('dir <dir>') — disk output",
            "Verify all three → then report. Never answer without tools.",
            "",
        ]
    
    elif intent in ("result_check",):
        lines += [
            "用户正在查询之前任务的结果/产出（图、表格、报告在哪）。只汇报已落盘的真实结果，绝不凭记忆编。",
            "⛔ 必须先调工具核实，不许凭记忆编结果（不查就答 = 撒谎）：",
            "1. read_file 读 task_plan.md 看任务状态（进行中 / 已归档 / 已取消）",
            "2. search_files 或 terminal('dir <输出目录>') 列出 figures/ results/ scripts/ 下最新文件（带文件名与时间）",
            "3. 有产物 → 把真实文件路径交给用户（绝对路径 + 文件名 + 是否本轮新生成）；无产物 → 明说'当前还没有产出文件'并简述卡在哪一步",
            "4. 任务未完成且用户想继续 → 读 task_plan 的下一步继续执行；用户没要求继续就别擅自启动新任务",
            "⛔ 不要新建 task_plan。不要凭空说'已生成/已完成/图已出'。",
            "",
        ]

    elif intent in ("analysis_plan",):
        lines += [
            "用户正在询问分析方案/技术路线图。使用只读工具构建方案，不执行代码。",
            "1. skill_list_by_domain(domain='推断的领域') 列出相关技能",
            "2. skill_view() 加载关键技能的 Pipeline/Workflow 节获取方法论",
            "3. 整理成清晰的路线图（步骤→方法→工具→预期产出）",
            "4. 如果涉及文献支撑：search_papers() 补充最新文献",
            "⛔ 不要调用 terminal 执行代码。不要创建 task_plan。",
            "⛔ 这是方案讨论阶段，不是分析执行阶段。",
            "",
        ] if zh else [
            "User is asking for an analysis plan/roadmap. Use read-only tools, do NOT execute.",
            "1. skill_list_by_domain(domain='inferred domain') to list relevant skills",
            "2. skill_view() to load methodology from Pipeline/Workflow sections",
            "3. Organize into a clear roadmap (step → method → tool → expected output)",
            "4. search_papers() to supplement with latest literature if needed",
            "⛔ Do NOT call terminal. Do NOT create task_plan.",
            "⛔ This is planning/discussion, NOT execution.",
            "",
        ]
    
    elif intent == "analysis":
        lines += [
            "这是一个生物信息学分析任务。你必须严格执行以下步骤，不可跳过：",
            "1. 调用 skill_search(query='你的分析需求', stage='auto') 查找合适的 skill（stage参数自动缩小搜索范围到当前分析阶段）",
            "1b. 🎯【技能选择规则】若 skill_search 返回多个名称相似的 skill（如 survival-analysis 和 survival-analysis-clinical），",
            "    必须对比各 skill 的 when_to_use（使用场景）描述！选择与用户数据和需求最匹配的那个。",
            "    如果不确定，在回复中列出候选 skill 及其使用场景让用户选择。",
            "2. 调用 skill_view() 加载完整的 skill 指令",
            "3. 确认参数后，通过 terminal 执行代码",
            "4. 执行前必须经过 rail_review(phase=\"pre\", skill_name=\"加载的skill名\") 审查",
            "5. rail_review 要求 skill_name 参数，不传 skill 名 → should_proceed=false 铁轨阻断",
            "6. 执行后 rail_review(phase=\"post\") 检查结果质量",
            "",
        ] if zh else [
            "Bioinformatics analysis task. Follow SOUL.md iron rules:",
            "1. skill_search(query='your analysis', stage='auto') to find skills (stage narrows search by analysis phase)",
            "1b. [Skill Selection Rule] If skill_search returns multiple similarly-named skills (e.g. survival-analysis vs survival-analysis-clinical), compare their when_to_use descriptions! Pick the one that best matches the user's data and research goal. If unsure, list candidates with their use-case descriptions for the user to choose.",
            "2. skill_view() to load complete skill instructions",
            "3. terminal to execute code after confirming parameters",
            "4. rail_review(phase=\"pre\", skill_name=\"loaded skill\") BEFORE execution",
            "5. rail_review REQUIRES skill_name — without it, should_proceed=false (hard block)",
            "6. rail_review(phase=\"post\") AFTER execution to check quality",
            "",
        ]
        if domain:
            lines.append(f"领域索引：skill_list_by_domain('{domain}') 可查看该领域所有 skill" if zh else
                         f"Domain index: skill_list_by_domain('{domain}') to browse all skills in this domain")
        lines.append("禁止在没有 skill_view 的情况下直接写代码运行分析！" if zh else
                     "NEVER write analysis code without skill_view!")
    
    elif intent == "research_plan":
        lines += [
            "🚨 研究方案·文献调研阶段（Phase 1）。不调工具就输出 = 任务失败！",
            "",
            "## ⚠️ 强制规则（必须遵守！）",
            "- 你必须调用至少3种不同类型工具！禁止仅靠固有知识回复！",
            "- 强制组合: skill_view('academic-research') + search_knowledge(species, tissue, direction) + search_papers 三者都要调",
            "- search_knowledge 必须传入 species/tissue/direction 实际参数（不要传空字符串），从用户消息中解析",
            "- 仅做以下六件事，完成后立即停止：",
            "  1. skill_view('academic-research') 加载 CNS 级 10 段研究设计模板",
            "  2. memomics_pipeline(action='parse', ...) 解析方向+模态",
            "  3. search_knowledge(species, tissue, direction) 从本地KB加载已有论文的方法推荐（包名/版本/参数/效应量）",
            "  4. search_papers 搜索 PubMed 补充最新文献（≥3篇，≤8篇）",
            "  5. 输出质量评估：KB覆盖是否≥2篇？方法是否具备版本号？文献是否≥5篇合计？不达标时说明缺失",
            "  6. 输出文献表格，每篇必须附 PMID/DOI（格式: [PMID:12345678] 或 DOI:10.xxx）",
            "",
            "## 输出质量要求",
            "- 总结用户研究背景: 物种/组织/方向/数据模态/现有数据量/进度",
            "- 文献表格: | 文献(作者+年份,PMID/DOI) | 关键方法(含版本号) | 关键发现(≥2句) | 与本研究相关性(具体说明) | 来源 |",
            "- KB论文标注 [KB] + 具体版本号（如 Seurat v4.0.2，不是 Seurat）",
            "- PubMed文献标注 [PMID:xxx]，优先非综述型原始研究",
            "- KB论文 <2 篇或无版本号 → 透明告知用户局限性",
            "",
            "## 结尾问题（必须问）",
            "最后问用户：【需要我基于以上文献，生成包含假说驱动、统计方案、Figure策略和实验验证路径的CNS级完整研究方案吗？】",
            "禁止在本轮生成研究方案或待办列表！不调用工具输出文本 = 任务彻底失败！",
            "",
        ]
    elif intent == "plan_refine":
        # plan_refine可能是: A)Phase2-文献后生成完整方案 B)修改已有方案
        lines += [
            "🚨 CNS 级方案规划模式（禁止执行分析代码！）",
            "",
            "## ⚠️ 强制规则（必须遵守，违规 = 任务失败）",
            "1. 你必须调用至少3种不同类型工具！禁止只输出文本不调工具！唯一例外：纯修改已有方案",
            "2. 严禁：execute_python / terminal / scan_data / 任何数据分析代码",
            "3. 允许：memomics_pipeline / skill_search / skill_view / search_knowledge / search_papers",
            "4. 方案中的每个分析方法必须注明来源：[KB] 或 [PMID:xxx]",
            "5. 推荐的工具/版本号优先级：KB论文版本 > NCBI/PubMed文献 > 通用默认值",
            "6. 方案必须包含 skill_view('academic-research') 中的完整 10 段 CNS 模板：",
            "   核心假说(H₀/H₁+预测链) / 创新性声明 / 文献依据 / 方法与论证 / 统计方案 / Figure策略 / 实验验证 / 备选方案 / 可复现 / 可执行待办",
            "7. 每个方法必须附 ≥1 句实质性理由（禁止常用/标准/参考已有研究），必须与方法所验证的假说预测对应",
            "8. 统计方案必须包含：功效分析+多重检验校正+效应量阈值+阴阳性对照",
            "9. Figure 策略必须 ≥3 张，每张对应一条预测 + 预期结果 + 如不符的备选方案",
            "",
            "## 执行步骤（严格按顺序，缺一不可）",
            "Step 1 [必须]→ skill_view('academic-research') 加载 CNS 级 10 段模板",
            "Step 2 [必须]→ skill_search(query='需要的分析类型') 找到真实skill名。如返回多个名称相似的skill，对比when_to_use选择最匹配的。",
            "Step 3 [必须]→ search_knowledge(species, tissue, direction) 加载KB方法推荐（须注入方案文本，版本号来自KB）",
            "Step 4 [可选]→ search_papers(query, max_results=5) 搜索PubMed补充最新文献",
            "Step 5 [必须]→ 按 10 段 CNS 模板输出完整方案, 每篇文献必须附 PMID/DOI",
            "Step 6 [必须]→ 逐项自检 Loop Gate 10 项（见 SKILL.md），标注每项是否通过",
            "Step 7 [必须]→ 方案末尾加入：\"本分析可得出什么生物学结论、如全部预测被证伪如何处理\"",
            "Step 8 [必须，不可跳过]→ memomics_pipeline(action='todos', selected_modules=[...])",
            "  禁止只写方案不调 tools！禁止执行任何分析代码！调不到3种工具 = 失败！",
            "  方案太浅(缺假说/统计/实验验证)→重新生成；太短(<800字)→重新生成",
            "",
        ]
    elif intent == "direct_exec":
        lines += [
            "用户参数/代码已确定，只需执行。",
            "",
            "跳过: literature_search, memomics_pipeline, kb_search, module_select, todo",
            "",
            "保留(SOUL.md三级操作级别不受影响):",
            "1. skill_view(相关skill) 加载模板参数。若多个候选skill，对比when_to_use选择最匹配场景的。",
            "2. check_env() 环境检查",
            "3. search_knowledge_base() (统计级及以上保留)",
            "4. rail_review(phase='pre') (统计级及以上保留)",
            "5. terminal 执行用户指定的代码/参数",
            "6. rail_review(phase='post') (所有级别保留)",
            "7. debate_analysis() (分析级保留)",
            "8. record_run() 记录执行",
            "",
            "直接执行用户给定的参数，不要改写！该审查的不能跳过。",
            "",
        ]
    elif intent == "report":
        lines.append("用户要求生成报告。先调用 skill_view('bioinformatics-html-report')，"
                     "使用 ReportBuilder + auto_fill_from_logs() 自动收集所有分析数据。" if zh else
                     "Report. Call skill_view('bioinformatics-html-report') first.")
    
    elif intent == "install":
        lines.append("安装任务。先 env_check 检测环境，如需新 skill 则调用 skill_view('create-bio-skill')。" if zh else
                     "Install task. env_check first, then skill_view('create-bio-skill') if needed.")
    
    elif intent == "literature":
        # Detect patent sub-intent
        if any(kw in user_text for kw in ["专利", "patent", "知识产权", "权利要求", "技术交底"]):
            lines += [
                "🚨 专利分析任务！必须加载专利专用 skill：",
                "1. skill_view('patent-analysis') 加载专利撰写规范和防御策略",
                "2. 专利检索三轮验证：①具体技术圈 ②抽象方法圈 ③IPC分类号G16B",
                "3. 独权撰写必须严格遵循公式：数据输入形式 + 不可替代技术组件 + 计算机实现步骤 + 可验证技术效果",
                "4. 必须在说明书第一段精确定义「可代替性」的含义",
                "5. 生成专利方案后 rail_review(phase='post') 检查专利铁律",
                "",
            ]
            return explicit_prefix + pinned_prefix + red_prefix + "\n".join(lines)
        # Detect paper-writing sub-intent
        lit_text = user_text if zh else user_text.lower()
        paper_write_kw = ["写论文", "写文章", "论文写作", "写一篇", "manuscript", "paper writing",
                         "write a paper", "draft a paper", "帮我写", "投稿", "学术论文"]
        paper_research_kw = ["研究方案", "实验设计", "方案设计", "设计实验", "研究计划",
                            "research plan", "research proposal", "技术路线"]
        paper_read_kw = ["这篇文章", "这篇文献", "这篇论文", "该文献", "该文章", "该论文",
                        "总结这篇文章", "总结一下这篇", "解读这篇", "精读",
                        "概括这篇文章", "概括这篇", "核心要点",
                        "说一下这篇", "讲讲这篇", "介绍这篇", "评价这篇", "怎么评价这篇",
                        "作者做了什么", "作者的研究思路", "讲了什么", "说了什么",
                        "review this paper", "summarize this paper", "explain this paper",
                        "pdf", ".pdf", "文献库", "文献库里"]
        if any(kw in lit_text for kw in paper_write_kw):
            lines.append("论文写作任务。调用 skill_view('academic-paper-writing')，"
                        "按 12-agent pipeline 生成论文。" if zh else
                        "Paper writing. Call skill_view('academic-paper-writing').")
        elif any(kw in lit_text for kw in paper_research_kw):
            lines.append("研究方案设计。调用 skill_view('research-plan')，"
                        "生成含 Mermaid 技术路线图的完整方案。" if zh else
                        "Research plan. Call skill_view('research-plan').")
        elif any(kw in lit_text for kw in paper_read_kw):
            # 2026-08-24 修复(memomics-aa368e59): 单篇文献总结/解读 → 轻量精读，禁止调研/出方案。
            # 用户只让"从专业编辑解读这篇文章、作者的研究思路做了什么"——不触发
            # skill_view('academic-research') / search_knowledge / search_papers 调研组合。
            # 2026-08-24 用户指定: 读文献优先 nature-reader（全文中英对照精读器，RED 必触发）。
            lines += [
                "📄 单篇文献总结/解读任务（用户提供或已导入 PDF）——轻量精读，不做文献调研、不出研究方案！",
                "1. 若该 PDF 尚未导入文献库：先 literature_import 导入；已在库则跳过",
                "2. 【优先】skill_view('nature-reader') 加载精读器 → 按其对 PDF/DOI/HTML/文本做全文中英对照精读",
                "   （图表/公式感知、源锚定、术语表，绝不降级为摘要）；精读产出后再以专业编辑口吻解读",
                "3. 备选快速路径：用户只要摘要/要点 → summarize_paper(文件或标题) 提取结构化摘要即可，不必全文对照",
                "4. 以专业编辑口吻直接解读：研究思路、作者做了什么、核心结论、学术价值——只解读用户问的这一篇",
                "⛔ 禁止：skill_view('academic-research') / search_knowledge / search_papers / memomics_pipeline",
                "⛔ 禁止：输出文献调研表格、PMID/DOI 清单、生成研究方案或待办——用户没要这些",
                "",
            ]
        else:
            lines.append("文献任务。调用 skill_search('文献') 或 skill_view('pubmed-search')。PDF保存到 work/papers/" if zh else
                         "Literature task. Use skill_search('literature') or skill_view('pubmed-search').")
    
    elif intent == "knowledge":
        lines.append("知识库查询。使用 search_knowledge_base 检索已有知识和经验。" if zh else
                     "Knowledge query. Use search_knowledge_base.")
    
    return explicit_prefix + pinned_prefix + red_prefix + "\n".join(lines)


# Progress text map (moved down from above)
_PROGRESS_TEXT = {
    "zh": {
        "thinking": "思考", "understanding": "正在理解您的需求",
        "complete": "完成", "reply_generated": "回复已生成",
        "stopped": "已停止", "user_stopped": "用户已停止运行",
        "waiting": "等待用户确认", "executing": "正在执行",
        "tool_started": "开始执行", "tool_completed": "执行完成",
        "tool_error": "执行出错", "installing_deps": "正在安装依赖",
        "scanning_data": "正在扫描数据", "analyzing": "正在分析",
        "generating_report": "正在生成报告", "debating": "正在辩论",
        "reviewing": "正在审查", "writing_code": "正在写代码",
        "completed": "已完成",
        "intro_reasoning": "用户询问系统身份，交给模型结合上下文作答。",
        "initializing_engine": "正在初始化分析引擎",
        "loading_skills": "加载 355 个生信技能模板...",
        "engine_ready": "引擎就绪，分析环境已就绪",
    },
    "en": {
        "thinking": "Thinking", "understanding": "Understanding your request",
        "complete": "Done", "reply_generated": "Reply generated",
        "stopped": "Stopped", "user_stopped": "Stopped by user",
        "waiting": "Waiting for user input", "executing": "Executing",
        "tool_started": "Started", "tool_completed": "Completed",
        "tool_error": "Error", "installing_deps": "Installing dependencies",
        "scanning_data": "Scanning data", "analyzing": "Analyzing",
        "generating_report": "Generating report", "debating": "Debating",
        "reviewing": "Reviewing", "writing_code": "Writing code",
        "completed": "Completed",
        "intro_reasoning": "User asked about system identity - answering from context via the model.",
        "initializing_engine": "Initializing analysis engine",
        "loading_skills": "Loading 355 bioinformatics skill templates...",
        "engine_ready": "Engine ready, analysis environment initialized",
    },
}

def _pt(session, key, default=None):
    """获取会话语言的进度文本"""
    lang = session.get("lang", "zh") if session else "zh"
    return _PROGRESS_TEXT.get(lang, _PROGRESS_TEXT["zh"]).get(key, default or key)


# === WebSocket 连接注册（多会话共享一个浏览器连接） ===
def _attach_ws(session, ws, loop):
    """把一个浏览器连接挂到会话上（不注销其他会话的连接）。

    多会话并发时，同一 ws 连接会同时挂到 A、B 两个会话；A 的 agent
    事件继续推给浏览器，前端 handleMessage 按 session_id 分流缓冲。
    """
    sid = session["id"]
    _ws_clients_by_session.setdefault(sid, set()).add((ws, loop))
    _ws_sessions_by_ws.setdefault(ws, set()).add(sid)
    # 兼容旧代码（微信桥接等直接读 ws_ref）
    session["ws_ref"] = ws
    session["loop_ref"] = loop
    session["ws_attached"] = True


def _detach_ws(ws):
    """ws 断开时从所有挂过的会话移除该连接（agent 不杀，继续后台跑）"""
    sids = _ws_sessions_by_ws.pop(ws, set())
    for sid in sids:
        clients = _ws_clients_by_session.get(sid)
        if not clients:
            continue
        clients = {c for c in clients if c[0] is not ws}
        if clients:
            _ws_clients_by_session[sid] = clients
        else:
            _ws_clients_by_session.pop(sid, None)
            s = _sessions.get(sid)
            if s is not None:
                s["ws_ref"] = None
                s["loop_ref"] = None
                s["ws_attached"] = False


# === 会话级消息发射器（支持 WS 断开后进度持久化） ===
def _session_emit(session, msg_dict):
    """存储消息到 progress_log 并通过 WS 发送（如果已连接）。

    解决的核心问题：WS 断开/切换会话时，agent 继续运行，
    进度事件存储在 session 内存中，切回时可重放。

    重要：自动注入 session_id — 前端 handleMessage 依赖此字段做会话分流，
    缺少 session_id 的消息不会被拦截，会串到当前会话的 UI。
    """
    # 自动注入 session_id（如果调用者没带）
    if "session_id" not in msg_dict:
        msg_dict["session_id"] = session.get("id", "")
    msg_type = msg_dict.get("type", "")
    # P1-1(2026-09-23): 待办事件的唯一回写收口。
    # 历史问题：四个推送点（debate 计划 / 心跳匹配 / 裁决同步 / 管线兜底）都只发 WS
    # 事件、不回写 session["todos"]，于是刷新或切回会话时 /api/todos 拿到的还是
    # 会话初始化时的 []。放在 emit 收口处统一回写（+落 state.db），未来新增推送点
    # 也自动生效，不必每处再记得补一行。
    if msg_type in ("todos", "todos_update"):
        try:
            _sync_session_todos(session, msg_dict.get("todos"))
        except Exception as _e_todo_sync:
            logger.warning(f"[todos] 回写会话失败: {_e_todo_sync}")
    # 记录最后事件时间（stall watchdog 用：5 分钟无事件 = LLM 卡死）
    session["_last_event_ts"] = time.time()
    # reasoning 流式文本：按 turn 合并持久化（刷新/重连后恢复 💭 思考过程）
    if msg_type == "reasoning":
        rlog = session.setdefault("reasoning_log", [])
        if rlog and rlog[-1].get("_open"):
            rlog[-1]["content"] += msg_dict.get("content", "")
        else:
            rlog.append({"content": msg_dict.get("content", ""), "_open": True})
        # 上限 10 个 turn，超出删最早的
        if len(rlog) > 10:
            del rlog[:len(rlog) - 10]
    # 2026-08-17: delta 流式文本按会话累积 —— 刷新/重连后 switch_session
    # 的 progress_replay 携带 partial_text 重放半截输出，前端继续接流不丢内容
    if msg_type == "delta":
        session["_partial_text"] = session.get("_partial_text", "") + msg_dict.get("content", "")
    # delta/reasoning/tool_gen 是流式文本，不存（太大）；其他都存
    if msg_type not in ("delta", "reasoning", "tool_gen", "heartbeat"):
        progress_log = session.setdefault("progress_log", [])
        progress_log.append(msg_dict)
        # 上限 500 条，超出删最早的
        if len(progress_log) > 500:
            del progress_log[:len(progress_log) - 500]
    # 结束型事件关闭 reasoning 累积段（下一个 turn 自动新开一段）
    if msg_type in ("complete", "cancelled", "error"):
        rlog = session.get("reasoning_log")
        if rlog and rlog[-1].get("_open"):
            rlog[-1]["_open"] = False
        # 2026-08-17: 回合结束清空半截文本累积（下个 turn 重新开始）
        session.pop("_partial_text", None)
    # 通过连接注册表广播到该会话的全部浏览器连接（多会话并发互不覆盖）
    recipients = list(_ws_clients_by_session.get(session.get("id", ""), set()))
    if recipients:
        for _w, _l in recipients:
            try:
                asyncio.run_coroutine_threadsafe(
                    _w.send_text(json.dumps(msg_dict, ensure_ascii=False)), _l)
            except Exception:
                pass
    else:
        # 兼容尚未接入注册表的入口（微信桥接等直接写 ws_ref）
        ws_ref = session.get("ws_ref")
        loop_ref = session.get("loop_ref")
        if ws_ref and loop_ref:
            try:
                asyncio.run_coroutine_threadsafe(
                    ws_ref.send_text(json.dumps(msg_dict, ensure_ascii=False)), loop_ref)
            except Exception:
                pass


def _create_session(title="新会话"):
    sid = f"memomics-{str(uuid.uuid4())[:8]}"
    db = _get_session_db()
    if db:
        db.ensure_session(sid, source="memomics", model=_current_model.get("model", ""))
        if title and title != "新会话":
            db.set_session_title(sid, title)
    session = {
        "id": sid,
        "title": title,
        "title_source": "auto",  # auto=自动总结可覆盖 / manual=用户手动改名，永不自动覆盖
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "messages": [],
        "model_config": dict(_current_model),
        "model_locked": False,  # 未做会话级切换 → 跟随全局模型
        "results_dir": os.path.join(RESULTS_DIR, sid),
        "todos": [],
        "bg_running": False,
        "running_agent": None,
        "running_task": None,
        "lang": "zh",  # 问题9: 会话语言，首条用户消息后更新
        "progress_log": [],   # 进度事件持久化（切换会话后可重放）
        "reasoning_log": [],  # 思考文本按 turn 持久化（刷新/重连后可恢复）
        "_last_event_ts": time.time(),  # stall watchdog 用
        "ws_attached": True,  # 当前是否有 WebSocket 连接监听此会话
        # 新会话本就为空，视为消息已加载（避免惰性加载误查 DB）
        "_messages_loaded": True,
        "_msg_count": 0,
        "_first_msg": "",
        "_last_msg": "",
    }
    # 结果目录延迟创建：仅在首次分析（scan_data/update_results_dir）时创建
    # 避免每次开新会话（即使只是聊天）都产生空目录
    _sessions[sid] = session
    return session


def _get_or_create_session(session_id=None):
    if session_id and session_id in _sessions:
        return _sessions[session_id]
    # 尝试从 state.db 加载会话（服务器重启后 _sessions 可能为空）
    if session_id:
        restored = _restore_single_session(session_id)
        if restored:
            return restored
    return _create_session()


def _cleanup_session_agent(session, kill_agent=False):
    """清理 session 关联的资源。

    kill_agent=False（默认）: 只断开 WS 引用，agent 继续在后台运行。
    kill_agent=True: 中断并清理 agent（仅在用户显式删除会话时使用）。
    """
    if not session:
        return
    # 断开 WS 引用（agent 的回调会通过 _session_emit 静默失败）
    session["ws_ref"] = None
    session["loop_ref"] = None
    session["ws_attached"] = False

    if kill_agent:
        agent_ref = session.get("running_agent")
        if agent_ref:
            try:
                if hasattr(agent_ref, "interrupt"):
                    agent_ref.interrupt()
            except Exception:
                pass
            try:
                if hasattr(agent_ref, "close"):
                    agent_ref.close()
            except Exception:
                pass
            session["running_agent"] = None
            session["running_task"] = None
            session["bg_running"] = False
            session["agent"] = None


def _scan_results_dir_for_session(sid, fallback_dir):
    """扫描 RESULTS_DIR，找到与 sid 关联的分析结果目录。
    目录名包含 sid 短ID（rename 时会在目录名末尾加短ID）。
    如果找不到，返回 fallback_dir。"""
    if not os.path.isdir(RESULTS_DIR):
        return fallback_dir
    short_id = sid.split("-")[-1] if "-" in sid else sid[:8]
    for d in sorted(os.listdir(RESULTS_DIR), reverse=True):
        if d.endswith('_' + short_id) and os.path.isdir(os.path.join(RESULTS_DIR, d)):
            return os.path.join(RESULTS_DIR, d)
    return fallback_dir


def _restore_single_session(sid):
    """从 state.db 恢复单个会话到内存（用于 HTTP API 按需加载）"""
    db = _get_session_db()
    if not db:
        return None
    try:
        sessions = db.list_sessions_rich(limit=1000)  # limit=0 returns all (hermes default=20)
        for s in sessions:
            s_id = s.get("session_id") or s.get("id")
            if s_id != sid:
                continue
            if not sid.startswith("memomics-"):
                continue
            msgs = []
            # 惰性恢复：按需恢复单会话时也只取元数据，完整消息在 get_messages 时加载
            messages = []
            _msg_count = int(s.get("message_count") or 0)
            _first_msg = str(s.get("preview") or "")
            persisted_cwd = ""
            try:
                row = db._conn.execute("SELECT cwd FROM sessions WHERE id = ?", (sid,)).fetchone()
                if row and row[0]:
                    persisted_cwd = row[0]
            except Exception:
                pass
            if persisted_cwd and os.path.isdir(persisted_cwd):
                # 安全验证：cwd 必须在 results/ 下（防止被外部路径污染）
                _results_base = os.path.abspath(RESULTS_DIR).rstrip(os.sep)
                cwd_abs = os.path.abspath(persisted_cwd.replace("/", os.sep))
                if cwd_abs.startswith(_results_base + os.sep) or cwd_abs == _results_base:
                    results_dir = persisted_cwd.replace("/", os.sep)
                else:
                    results_dir = os.path.join(RESULTS_DIR, sid)
            else:
                default_dir = os.path.join(RESULTS_DIR, sid)
                if os.path.isdir(default_dir):
                    results_dir = default_dir
                else:
                    results_dir = _scan_results_dir_for_session(sid, default_dir)
            ts_started = s.get("started_at")
            ts_active = s.get("last_active")
            try:
                created_str = datetime.fromtimestamp(ts_started).strftime("%Y-%m-%d %H:%M:%S") if ts_started else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                created_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                active_str = datetime.fromtimestamp(ts_active).strftime("%Y-%m-%d %H:%M:%S") if ts_active else created_str
            except Exception:
                active_str = created_str
            _mc, _mc_locked = _restore_session_model_config(sid, _current_model)
            session = {
                "id": sid,
                "title": s.get("title") or (_first_msg[:30] if _first_msg else sid[:20]),
                "title_source": _load_title_source(sid),
                "created": created_str,
                "last_active": active_str,
                "messages": messages,
                "model_config": _mc,
                "results_dir": results_dir,
                "todos": [],
                "bg_running": False,
                "running_agent": None,
                "running_task": None,
                "restored": True,
                "last_active": active_str,
                "source": "",
                "progress_log": [],
                "reasoning_log": [],
                "ws_attached": False,
                "ws_ref": None,
                "loop_ref": None,
                # 惰性加载标记：完整消息尚未载入内存
                "_messages_loaded": False,
                "_msg_count": _msg_count,
                "_first_msg": _first_msg,
                "_last_msg": "",
            }
            _sessions[sid] = session
            if _mc_locked:
                session["model_locked"] = True  # 重启后保持会话级锁定，全局切换不覆盖
            print(f"[MemOmics] 按需恢复会话: {sid}", flush=True)
            return session
    except Exception as e:
        print(f"[MemOmics] 单会话恢复失败 ({sid}): {e}", flush=True)
    return None


def _restore_one_persisted_session(db, s):
    """恢复单个会话到内存（从 _load_persisted_sessions 抽出，单条失败不影响整体）。"""
    sid = s.get("session_id") or s.get("id")
    if not sid or sid in _sessions:
        return False
    # 只加载 memomics 开头的会话
    if not sid.startswith("memomics-"):
        return False
    # 惰性恢复：启动时只取元数据（message_count/preview），不加载全部消息。
    # 完整消息在用户打开/继续会话时按需加载（见 _load_session_messages）。
    _msg_count = int(s.get("message_count") or 0)
    _first_msg = str(s.get("preview") or "")
    messages = []
    # 空会话也恢复（用户可能创建了但还没发消息）
    # 恢复 results_dir：优先从 state.db 的 cwd 字段读，没有就用 sid
    persisted_cwd = s.get("cwd") or ""
    # list_sessions_rich 不返回 cwd 字段，需要单独查询
    if not persisted_cwd:
        try:
            row = db._conn.execute("SELECT cwd FROM sessions WHERE id = ?", (sid,)).fetchone()
            if row and row[0]:
                persisted_cwd = row[0]
        except Exception:
            pass
    if persisted_cwd and os.path.isdir(persisted_cwd):
        # 安全验证：cwd 必须在 results/ 下（防止被外部路径污染）
        _results_base = os.path.abspath(RESULTS_DIR).rstrip(os.sep)
        cwd_abs = os.path.abspath(persisted_cwd.replace("/", os.sep))
        if cwd_abs.startswith(_results_base + os.sep) or cwd_abs == _results_base:
            results_dir = persisted_cwd.replace("/", os.sep)
        else:
            results_dir = os.path.join(RESULTS_DIR, sid)
    else:
        # 尝试 RESULTS_DIR/sid
        default_dir = os.path.join(RESULTS_DIR, sid)
        if os.path.isdir(default_dir):
            contents = os.listdir(default_dir)
            if contents == ["log"] or contents == []:
                # 空壳目录 — 扫描找到实际分析结果目录
                results_dir = _scan_results_dir_for_session(sid, default_dir)
            else:
                results_dir = default_dir
        else:
            results_dir = _scan_results_dir_for_session(sid, default_dir)
    ts_started = s.get("started_at")
    ts_active = s.get("last_active")
    try:
        created_str = datetime.fromtimestamp(ts_started).strftime("%Y-%m-%d %H:%M:%S") if ts_started else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        created_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        active_str = datetime.fromtimestamp(ts_active).strftime("%Y-%m-%d %H:%M:%S") if ts_active else created_str
    except Exception:
        active_str = created_str
    _mc, _mc_locked = _restore_session_model_config(sid, _current_model)
    session = {
        "id": sid,
        "title": s.get("title") or (_first_msg[:30] if _first_msg else sid[:20]),
        "created": created_str,
        "last_active": active_str,
        "messages": messages,
        "model_config": _mc,
        "results_dir": results_dir,
        "todos": [],
        "bg_running": False,
        "running_agent": None,
        "running_task": None,
        "restored": True,
        "progress_log": [],
        "reasoning_log": [],
        "ws_attached": False,
        "ws_ref": None,
        "loop_ref": None,
        # 惰性加载标记：完整消息尚未载入内存
        "_messages_loaded": False,
        "_msg_count": _msg_count,
        "_first_msg": _first_msg,
        "_last_msg": "",
    }
    _sessions[sid] = session
    if _mc_locked:
        session["model_locked"] = True  # 重启后保持会话级锁定，全局切换不覆盖
    return True


def _load_persisted_sessions():
    """启动时从 Hermes state.db 恢复历史会话"""
    db = _get_session_db()
    if not db:
        print("[MemOmics] SessionDB 不可用，跳过会话恢复", flush=True)
        return
    try:
        # 自愈（2026-08-08）：清理 sessions.model_config 里的空串/坏 JSON。
        # 空串 '' 不是合法 JSON，Hermes 的 list_sessions_rich 内部对
        # model_config 做 json_extract 时抛 "malformed JSON" → 整个会话恢复
        # 中断（内存 0 会话）→ 前端所有会话级操作（切模型等）404 静默失败。
        # 坏数据的来源：任何把 model_config 写成 '' 而非 NULL 的路径。
        try:
            if db._conn:
                db._conn.execute(
                    "UPDATE sessions SET model_config = NULL "
                    "WHERE model_config IS NOT NULL AND json_valid(model_config) = 0"
                )
                db._conn.commit()
        except Exception:
            pass
        sessions = db.list_sessions_rich(limit=1000)  # limit=0 returns all (hermes default=20)
        count = 0
        for s in sessions:
            try:
                _loaded = _restore_one_persisted_session(db, s)
                if _loaded:
                    count += 1
            except Exception as e:
                # 单条会话恢复失败不影响其他会话（原来整个 for 循环被一个
                # except 包住，一条坏数据 → 全部恢复失败 → 内存 0 会话）
                print(f"[MemOmics] 会话 {s.get('session_id') or s.get('id')} 恢复失败: {e}", flush=True)
                continue
        if count:
            print(f"[MemOmics] 从 state.db 恢复了 {count} 个历史会话", flush=True)
            # 恢复微信会话映射
            _rebuild_weixin_session_map()
        # M2: 重启后重新授权——所有恢复的非退役任务 disarm，自动唤醒必须用户消息恢复
        # （DSH armed 语义：机器不会自己恢复自主权，必须人显式"继续"）
        try:
            from webui.runtime.run_gate import disarm as _disarm_gate
            from webui.runtime.run_gate import is_retired as _is_retired_gate
            from webui.runtime.run_gate import is_armed as _is_armed_gate
            _disarmed = 0
            for _sid2, _sess2 in list(_sessions.items()):
                _rd2 = _sess2.get("results_dir", "") or ""
                if _rd2 and not _is_retired_gate(_rd2) and _is_armed_gate(_rd2):
                    _disarm_gate(_rd2, "server restart (re-authorization required)")
                    _disarmed += 1
            if _disarmed:
                print(f"[MemOmics] M2: {_disarmed} 个任务的自动唤醒已暂停（重启后需用户消息重新授权）", flush=True)
        except Exception:
            pass
        # M4: 启动一致性对账（run_gate 与 task_plan 漂移检测 + 自动修复确定性漂移）
        try:
            from webui.runtime.run_gate import reconcile as _reconcile_gate
            _recon_notes = []
            for _sid2, _sess2 in list(_sessions.items()):
                _rd2 = _sess2.get("results_dir", "") or ""
                if _rd2:
                    for _w in _reconcile_gate(_rd2):
                        _recon_notes.append(f"{_sid2[:12]}: {_w}")
            for _n in _recon_notes:
                print(f"[MemOmics] [Reconcile] {_n}", flush=True)
            if _recon_notes:
                print(f"[MemOmics] 启动对账完成：{len(_recon_notes)} 条漂移告警/修复", flush=True)
        except Exception:
            pass
    except Exception as e:
        print(f"[MemOmics] 会话恢复失败: {e}", flush=True)


def _persist_session_message(session, role, content):
    """把消息持久化到 Hermes state.db"""
    db = _get_session_db()
    if not db:
        return
    try:
        db.append_message(session["id"], role=role, content=content)
    except Exception:
        pass


def _conv_messages_to_memomics(msgs):
    """把 get_messages_as_conversation 的输出转成 MemOmics 显示格式。"""
    out = []
    for m in msgs or []:
        role = m.get("role", "")
        content = m.get("content", "")
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": str(content), "time": ""})
    return out


def _load_session_messages(sid, limit=None):
    """从 state.db 惰性加载会话消息。

    limit=None 加载全部；limit>0 只加载最近 limit 条（插入顺序）。
    失败返回 []，绝不抛异常。"""
    db = _get_session_db()
    if not db:
        return []
    try:
        return _conv_messages_to_memomics(db.get_messages_as_conversation(sid, limit=limit))
    except Exception:
        return []


def _ensure_session_messages_loaded(session):
    """确保会话的完整消息已在内存（供继续对话时的上下文构建/追加使用）。

    只在尚未完整加载时从 state.db 加载一次；新会话（本就空）直接视为已加载。"""
    if session.get("_messages_loaded"):
        return session.get("messages", [])
    sid = session.get("id", "")
    session["messages"] = _load_session_messages(sid, limit=None)
    session["_messages_loaded"] = True
    return session["messages"]


def _fmt_tool_args(tool_name, args):
    """格式化工具调用的参数为简短描述"""
    if not args:
        return ""
    try:
        if isinstance(args, str):
            return args[:100]
        if isinstance(args, dict):
            if "command" in args:
                return str(args["command"])[:100]
            if "path" in args:
                return str(args["path"])[:100]
            if "query" in args:
                return str(args["query"])[:100]
            if "code" in args:
                return "代码执行"
            if "file" in args:
                return str(args["file"])[:100]
            return str(args)[:100]
    except Exception:
        pass
    return ""


def _fmt_tool_result(tool_name, result):
    """格式化工具调用结果为简短描述"""
    if not result:
        return "完成"
    try:
        r = str(result)
        first_line = r.strip().split("\n")[0]
        return first_line[:120] if first_line else "完成"
    except Exception:
        return "完成"


# === Planning prompt: agent 收到任务后必须先创建待办清单 ===
# 2026-08-25: 执行策略（DSH 执行策略迁移——用户优先，决策交给 LLM，不硬编码）
# 用户消息 = 最高优先级；插话两不误；自动轮才自主修错续跑；报错停止后由用户决定；
# 不确定就问（ask_user）。注入 ephemeral_system_prompt（agent 级，所有回合可见）。
_EXECUTION_POLICY = """
## 执行策略（用户优先 · 决策由你判断）

### 1. 用户消息是最高优先级
用户让你做什么就做什么：用户只问就只答，用户要调查就只调查，用户要求执行才执行。
不要因为"有未完成任务"而覆盖用户当前的请求。

### 2. 任务进行中用户插话（回答与执行两不误）
- 先完整响应用户当前消息（问答/调查/修改指示）
- **用户中途问的问题 ≠ 打断**：纯问题（"为什么慢/参数是什么/结果怎样"）→ 先回答，
  任务本身继续，不用停
- 只有用户明确说"停止/停一下/先别跑/换个方向/重做"才停或改任务
- 判断用户意图：纯问答 → 只回答；要求修改任务 → 按新指示更新任务；
  没有明确说"继续/接着跑"→ 不擅自扩大执行
- 任务推进由系统自动接管：用户回合结束后系统会调度后台自检继续任务

### 3. 自动续跑轮（无人插手）可以自主工作
系统唤醒的自检回合（用户不在场）：检查进度 → 报错分析原因 → 修复 → 继续，
这是允许的自主行为，直接执行。

### 4. 报错停止后，是否继续由用户决定
用户回合中任务报错停止：只报告原因和可选方案，不要擅自修改后继续执行，等用户指示。
只有自动轮（用户不在场）才自主修复重试。

### 5. 开工前先问清楚（不确定就问，铁律 · 意图确认弹窗）
**高代价任务**——真实分析跑流程、集群投递（remote_cluster run/submit）、
结果入库（save_knowledge/knowledge_write/conclusion_save）、出报告
（generate_report/write_report）——**开工前必须先调 ask_user 弹出确认表单**，
把不清楚的一次问明白：数据在哪、物种/组织/条件、期望交付形式、关键参数与阈值、
是否继续旧任务。**不要靠猜、不要靠意图推断、不要先跑再说。**
用法：options 传可勾选项（对象可带 desc 说明/recommended 推荐），
多件事一起确认时 multi_select=true，kind="intent"。
**硬约束**：表单没答复前，执行类/产物类工具会被系统直接拦下（白跑一趟），
所以问完就结束本回合，等用户勾选或回复；用户答复会自动成为你的下一条消息。
**不要问的**：纯问答、只读查询、状态播报、用户已明确给全参数的任务——直接做。
原则：一次问清比十次返工便宜；但已有明确答案的事不要重复问。

### 6. 一切以用户为主
问清目的 → 规划 → 执行 → 报错就解决，循环；用户打断才停，用户回答后继续。
拿不准用户要什么时，回到第 5 条：问。
"""

_PLANNING_PROMPT = """

## Task Execution Protocol

### Phase 1: Plan

When the user asks you to perform an analysis task, you MUST:

1. **Load the relevant skill first.** Use `skill_view('skill-name')` to read the complete instructions, scripts, and review criteria for the analysis type. The skill contains:
   - What scripts to run and in what order
   - Parameter recommendations (cell counts, resolution, etc.)
   - Review criteria (what to check after each step)
   - Expected output files

2. **Create a todo checklist.** Break the skill's pipeline into concrete steps. Each step = one script execution + its review.
   - Use the `todo` tool (action='create')
   - Set `estimated_minutes` for each step (your best guess based on data size)
   - Order steps as defined in the skill

### Phase 2: Execute (one step per turn)

For EACH step in order:

**A. Short steps (estimated ≤ 2 minutes, no review needed):**
   - Run foreground: `terminal("Rscript script.R")` or `terminal("python script.py")`
   - No timeout limit — the system will wait
   - After completion: check output, mark `completed`, move to next step

**B. Normal steps (estimated 2-30 minutes):**
   - Run: `terminal("python script.py")` (foreground, no timeout)
   - After completion: 
     1. Check output quality (file sizes, expected columns)
     2. Run `rail_review(phase='post')` to validate
     3. If step is critical: run `debate_analysis()` 
     4. Mark `completed` → move to next step

**C. Very long steps (>30 minutes, e.g. CellBender, large clustering):**
   - Start: `terminal("python long_script.py", background=True, notify_on_complete=True)`
   - Mark as `in_progress` with `estimated_minutes`
   - End your turn. The system will auto-wakeup to check progress
   - When the system wakes you up:
     1. `process(action='poll')` to check status
     2. If done → check output → `rail_review(post)` → mark `completed`
     3. If still running → report progress → end turn (system will wakeup again)

**D. Steps needing debate/review (any duration):**
   - After computation completes, mark as `waiting_review`
   - Run `debate_analysis()` to critically evaluate results
   - Run `rail_review(phase='post')` to validate against skill criteria
   - Only after BOTH pass → mark `completed`

### Phase 3: Per-step review protocol

After EVERY analysis step completes (regardless of duration), you MUST:

1. **Check output files**: `search_files` or `read_file` to verify expected outputs exist and have reasonable sizes
2. **Rail review**: `rail_review(phase='post', skill_name='the-skill-you-loaded')` — validates against skill criteria
3. **Debate (for critical steps)**: `debate_analysis()` — critically evaluates results, flags issues
4. **Record**: update task_plan.md with completion status

### Special: CellBender / single long command

For tasks that are ONE long command (not a pipeline of steps):
- Create ONE todo: "Run CellBender" with `estimated_minutes` (typically 360-600)
- Start: `terminal("cellbender ...", background=True, notify_on_complete=True)`
- End your turn. System wakes up every 15 minutes to check.
- When complete: check output → rail_review → completed

### Task states summary

| State | Meaning | When to use |
|-------|---------|-------------|
| `pending` | Not started | Initial state |
| `in_progress` | Running now | Set `estimated_minutes` for the system |
| `waiting_review` | Done computing, needs debate | After terminal completes, before rail_review |
| `completed` | Done and verified | After rail_review + debate pass |
| `cancelled` | Failed | Note error in task_plan.md |

IMPORTANT: 
- Do NOT skip review steps. The SOUL.md iron rules REQUIRE rail_review after every analysis action.
- Do NOT combine multiple steps into one turn. One step = one script = one review cycle.
- The system will NOT time out your analysis steps. Only research_plan has a time limit.
- Use the `todo` tool to update status in real-time — the user sees progress on the WebUI.
"""


_FACT_RECALL_STOP = {
    "的", "了", "和", "是", "在", "我", "你", "要", "与", "或", "一个", "这个", "那个",
    "我们", "请", "帮", "怎么", "什么", "为什么", "如何", "这个", "进行", "一下",
    "the", "a", "an", "of", "to", "in", "for", "and", "or", "is", "are", "on",
}


def _recall_facts(text, limit=6, max_chars=450):
    """每轮自动召回相关历史记忆（memory_store.db facts，TencentDB L1-recall 的 MemOmics 版）。

    关键字 LIKE 匹配 + trust_score/retrieval_count 排序；预算 ≤450 字符。失败静默返回空串。
    """
    try:
        if not text:
            return ""
        import re as _re
        _kws = [w for w in _re.findall(r"[\u4e00-\u9fffA-Za-z0-9_.-]{2,}", text)
                if w.lower() not in _FACT_RECALL_STOP][:8]
        if not _kws:
            return ""
        _db = os.path.join(HERMES_HOME_DIR, "memory_store.db")
        if not os.path.isfile(_db):
            return ""
        import sqlite3 as _sq
        _conds = " OR ".join(["f.content LIKE ?" for _ in _kws])
        conn = _sq.connect(f"file:{_db}?mode=ro", uri=True, timeout=10)
        try:
            _rows = conn.execute(
                f"SELECT f.content, f.trust_score FROM facts f WHERE ({_conds}) AND f.trust_score >= 0.5 "
                "ORDER BY f.trust_score DESC, f.retrieval_count DESC LIMIT ?",
                tuple(f"%{k}%" for k in _kws) + (limit,)).fetchall()
        finally:
            conn.close()
        if not _rows:
            return ""
        _lines = ["[相关历史记忆 · 若与当前问题无关请忽略]"]
        _used = 0
        for _c, _t in _rows:
            _line = f"- {str(_c)[:110]}"
            if _used + len(_line) > max_chars:
                break
            _lines.append(_line)
            _used += len(_line)
        return "\n".join(_lines) if len(_lines) > 1 else ""
    except Exception:
        return ""


def _build_memory_digest(session, text):
    """构建"历史记忆召回 + 会话锚点摘要"脚手架（不含用户文本）。
    (b) 改造(2026-08-21)：每轮只注入最新一条；上限收紧(6 条/420 字)，
    避免窗口被每轮重复的锚点/记忆脚手架占满(实测 220K 上下文 94% 是缓存命中的重复系统段)。"""
    _parts = []
    # (#2 记忆不丢) 持久的用户要求/文件路径必须固定带上——不依赖当前问题关键词命中
    try:
        _reqs = _read_requirements(session, limit=6)
        if _reqs:
            # (用户要求要核实) 标注其中已不存在的路径，模型据此提示用户确认/纠错
            _warns = _verify_requirements(session, _reqs)
            _req_block = ("[会话要求 · 用户明确给过且仍未撤销的要求/路径/环境(持久)]\n"
                          "执行策略：优先按用户说明执行；带 (已确认)/(已验证) 标记的路径、环境、"
                          "包与结论**直接复用，不要再重复探测/验证**（每轮重复 check_env/探测 "
                          "浪费 token 且已确认过）；仅当条目缺失或与现状冲突时才核实并向用户确认。\n" +
                          "\n".join(f"- {_fmt_req_line(r)}" for r in _reqs))
            if _warns:
                _req_block += "\n⚠️ 以下要求中的路径不存在，请向用户核实是否已更新/作废：" + \
                              "；".join(f"{k[:40]}({','.join(v)})" for k, v in _warns.items())[:400]
            _parts.append(_req_block)
    except Exception:
        pass
    try:
        # (P3) 记忆召回切到 memory_store FTS5（失败回退 LIKE）
        # 2026-08-31 P0-6 接线：检索 query 用内容实体优先（"继续跑"→entity"热图"），
        # 让意图/话题切换旁路沉淀的 entity 真正驱动召回，而不是裸原文。
        _q_ent = ""
        try:
            from webui import session_state as _ss2
        except ImportError:
            import session_state as _ss2
        _q_ent = _ss2.extract_entity(text or "") or ""
        _recall_query = _q_ent or (text or "")
        _facts = context_arch.fts_recall(_recall_query) or _recall_facts(_recall_query)
        if _facts:
            _parts.append(_facts)
    except Exception:
        try:
            _facts = _recall_facts(text or "")
            if _facts:
                _parts.append(_facts)
        except Exception:
            pass
    try:
        from memomics.bio_tools import session_memory as _sm
        _block = _sm.build_digest(session.get("id", ""), max_items=6, max_chars=420)
        if _block:
            _parts.append(_block)
    except Exception:
        pass
    # (#3 脚本复用) scripts/ 已有脚本清单
    try:
        _sdig = _build_scripts_digest(session)
        if _sdig:
            _parts.append(_sdig)
    except Exception:
        pass
    # (2026-08-25) 产出资产清单：输入/输出/脚本/图片在哪——复用与汇报的依据
    try:
        _adig = _build_output_assets_digest(session)
        if _adig:
            _parts.append(_adig)
    except Exception:
        pass
    if not _parts:
        return ""
    return "\n\n".join(_parts)


def _inject_anchors(session, text):
    """每轮注入 历史记忆召回 + 会话锚点摘要（跨压缩持久，2026-08-14）。
    保留给自检唤醒路径(1761)使用；主用户回合改由 _build_memory_digest + run_agent 单条注入。"""
    _digest = _build_memory_digest(session, text)
    if not _digest:
        return text or ""
    return _digest + "\n\n" + (text or "")


def _est_message_tokens(m):
    """粗略 token 估算（CJK 密集文本约 2 字/token）：用于触发上下文折叠预算。"""
    c = m.get("content") if isinstance(m, dict) else ""
    if not isinstance(c, str) or not c:
        return 4
    return max(4, len(c) // 2) + 4


def _strip_scaffold_text(text):
    """剥离历史里服务器注入的 [相关历史记忆]/[会话锚点] 前缀脚手架，返回真实用户文本；
    纯脚手架返回 None。(b) 上下文卫生。唤醒/系统通知类消息本身即脚手架，不剥离直接丢弃。"""
    if not isinstance(text, str):
        return None
    cur = text.strip()
    if not cur:
        return None
    if cur.startswith(("[会话要求", "[系统唤醒", "📊 LoopX 状态", "[System:", "[数据读取配方")):
        return None
    for _ in range(4):
        if cur.startswith(("[相关历史记忆", "[会话锚点")):
            idx = cur.rfind("\n\n")
            if idx == -1:
                return None
            nxt = cur[idx + 2:].strip()
            if not nxt or nxt.startswith(("[相关历史记忆", "[会话锚点")):
                cur = nxt or cur
                if not nxt:
                    return None
                continue
            return nxt
        return cur
    return None


# 2026-08-26: 服务端系统注入脚手架前缀（写历史时常以 role=user 形式喂给模型，
# 显示层按 role 过滤不到 → 刷新后刷屏实测复现）。命中即视为注入消息，不进前端对话流。
_INJECT_PREFIXES = ("[会话要求", "[相关历史记忆", "[会话锚点", "[系统唤醒",
                    "📊 LoopX 状态", "[System:", "[数据读取配方", "[wakeup-progress-check]")


# 2026-08-27: task_plan 文本"整体完成"判定（纯函数，供唤醒注入最后防线 + 测试直测）。
# 只用整体级信号——Phase 级会出现"Phase 1 已完成"、"**Status:** complete"（每个
# Phase 都有），不能代表任务整体完成；"已完成"单词同样太弱（实测 Phase 级高频出现）。
def _plan_is_complete_text(plan_text: str) -> bool:
    if not plan_text or not isinstance(plan_text, str):
        return False
    _pl = plan_text.lower()
    return any(m in _pl for m in (
        "全部完成", "已全部完成", "无长任务", "确认无长任务", "标记完成",
        "任务结束", "任务已完成", "任务全部完成", "no active task",
        "all tasks complete", "all complete", "**task status:** complete"))


# 2026-08-27: ask_user 否定/结束回答判定（纯函数）：命中则保持任务退役状态，
# 不得复活 done 任务（实测："不用了" 回答曾把已完成任务复活 → 唤醒链 → 重复输出）。
_NEG_END_WORDS = ("不用", "不需要", "不用了", "不做了", "算了", "先这样",
                  "就到这", "没有任务", "没任务", "不跑", "不用继续",
                  "暂停", "先不", "不要了", "不用做")

def _is_negation_end_answer(user_text: str) -> bool:
    if not user_text or not isinstance(user_text, str):
        return False
    _t = user_text.lower()
    return any(w in _t for w in _NEG_END_WORDS)


_READ_KEYWORDS = ("readRDS", "read.csv", "read.table", "read_tsv", "read.delim",
                  "fread", "read_parquet", "read_excel", "readxl", "Load10X",
                  "Read10X", "scanpy.read", "pd.read_", "readr::", "readLines",
                  "readline", "vroom", "read.delim2", "read.delim(", "readxl::")
_FAIL_MARKERS = ("error", "exception", "traceback", "cannot open", "no such file",
                 "not found", "failed", "错误", "失败", "不存在", "无法读取")


def _extract_read_recipes(rows, limit=5, max_chars=1200):
    """从 tool_calls_log 行提取"此前成功读取方式"配方（确定性，不依赖 LLM writer）。

    筛选：args 含读取类关键词 且 result 不含失败标志 → 视为成功读取配方。
    解决长会话根因：上下文折叠/唤醒精简后模型"忘了怎么读文件"——
    把成功示例（含路径与参数）原样带回上下文，模型直接复用而不是重新发明。
    """
    recipes = []
    for _t, _a, _r, _ts in rows:
        _args = str(_a or "")
        _res = str(_r or "")
        if not any(k in _args for k in _READ_KEYWORDS):
            continue
        if any(m in _res.lower() for m in _FAIL_MARKERS):
            continue
        recipes.append(f"- [{_ts}] {_t}({_args[:260]})")
        if len(recipes) >= limit:
            break
    if not recipes:
        return ""
    out = "[数据读取配方 · 此前成功读取文件的命令（含路径/参数），直接复用，不要重新摸索]\n" + "\n".join(recipes)
    return out[:max_chars]


def _build_read_recipes(session, db_path=None, limit_rows=40):
    """查 state.db tool_calls_log，提取本会话的成功读取配方（最新优先）。"""
    try:
        sid = session.get("id", "") or ""
        if not sid:
            return ""
        _dbp = db_path or os.path.join(HERMES_HOME_DIR, "state.db")
        if not os.path.isfile(_dbp):
            return ""
        import sqlite3 as _sq
        _conn = _sq.connect(f"file:{_dbp}?mode=ro", uri=True, timeout=8)
        try:
            _rows = _conn.execute(
                "SELECT tool_name, args_json, result_text, "
                "datetime(timestamp,'unixepoch','localtime') FROM tool_calls_log "
                "WHERE session_id=? ORDER BY rowid DESC LIMIT ?",
                (sid, limit_rows)).fetchall()
        finally:
            _conn.close()
        return _extract_read_recipes(_rows)
    except Exception:
        return ""


def _resolve_message_id(session_id: str, content_hint: str) -> int:
    """按 content 片段在 state.db 查该会话的 message_id（elision marker 用）。

    返回 id 或 0（查不到时 fail-open，不阻断压缩）。"""
    if not session_id or not content_hint:
        return 0
    try:
        import sqlite3 as _sq
        _dbp = os.path.join(HERMES_HOME_DIR, "state.db")
        if not os.path.isfile(_dbp):
            return 0
        _conn = _sq.connect(f"file:{_dbp}?mode=ro", uri=True, timeout=8)
        try:
            _hint = content_hint.strip()[:60]
            if not _hint:
                return 0
            _row = _conn.execute(
                "SELECT id FROM messages WHERE session_id=? AND content LIKE ? "
                "ORDER BY id DESC LIMIT 1",
                (session_id, f"%{_hint[:40]}%")).fetchone()
            return int(_row[0]) if _row else 0
        finally:
            _conn.close()
    except Exception:
        return 0


def _build_rollup_checkpoint(session, head):
    """(c) 步进式结构化 checkpoint：把被折叠的历史头部压缩为结构化摘要。

    确定性构建（task_plan + 会话锚点 + 最近工具调用 + 起始诉求），零 LLM 成本、可离线测试。
    只折叠发给模型的这一份；state.db 全量轨迹不动，压缩永不丢证据。
    2026-08-22: 追加 elision marker —— 折叠边界 message_id 指针，模型可
    session_search(session_id, around_message_id=<id>, window=5) 逐字捞回早期细节。"""
    _lines = ["[会话检查点 · 跨压缩持久 · 早期历史已折叠为结构化摘要]",
              "## 会话", f"- id: {session.get('id', '')}"]
    rd = session.get("results_dir") or ""
    if rd:
        _lines.append(f"- results_dir: {rd}")
    # elision marker：折叠边界（head 最后一条）的 message_id —— 细节召回的直接指针
    try:
        _sid = session.get("id", "") or ""
        _last = None
        for _m in reversed(head or []):
            if isinstance(_m, dict) and isinstance(_m.get("content"), str) and _m["content"].strip():
                _last = _m["content"].strip()
                break
        if _sid and _last:
            _mid = _resolve_message_id(_sid, _last[-40:])
            if _mid:
                _lines.append(f"- 折叠边界 message_id: {_mid}（早期 N 条已折叠；"
                              f"需要细节 → session_search(session_id='{_sid}', "
                              f"around_message_id={_mid}, window=5) 逐字捞回）")
    except Exception:
        pass
    # (#2 记忆不丢) 持久要求随 checkpoint 带过滚动 —— 折叠后依然记得用户要求/路径
    try:
        _reqs = _read_requirements(session, limit=10)
        if _reqs:
            _lines += ["## 持久用户要求/路径(REQUIREMENTS)", "\n".join(f"- {r[:150]}" for r in _reqs)]
    except Exception:
        pass
    try:
        _plan = ""
        _p = os.path.join(rd, "task_plan.md") if rd else ""
        if _p and os.path.isfile(_p):
            with open(_p, encoding="utf-8", errors="replace") as _f:
                _plan = _f.read()[:1500]
        if _plan:
            _lines += ["## 目标/任务(task_plan 摘要)", _plan.strip()]
    except Exception:
        pass
    try:
        from memomics.bio_tools import session_memory as _sm
        _dig = _sm.build_digest(session.get("id", ""), max_items=6, max_chars=420)
        if _dig:
            _lines += ["## 关键文件/路径(会话锚点)", _dig]
    except Exception:
        pass
    try:
        import sqlite3 as _sq
        _dbp = os.path.join(HERMES_HOME_DIR, "state.db")
        _rows = []
        try:
            _conn = _sq.connect(f"file:{_dbp}?mode=ro", uri=True, timeout=8)
            try:
                _rows = _conn.execute(
                    "SELECT tool_name, substr(args_json,1,120), substr(result_text,1,60), "
                    "datetime(timestamp,'unixepoch','localtime') FROM tool_calls_log "
                    "WHERE session_id=? ORDER BY rowid DESC LIMIT 10", (session.get("id", ""),)).fetchall()
            finally:
                _conn.close()
        except Exception:
            _rows = []  # DB 不可用（新装/测试环境无 state.db）→ 不阻塞 checkpoint，配方段照跑
        if _rows:
            _lines += ["## 已执行工作(最近工具调用)"]
            for _t, _a, _r, _ts in reversed(_rows):
                _lines.append(f"- [{_ts}] {_t} args={_a} result={str(_r)[:60]}")
        # 2026-08: 数据读取配方 —— 折叠后"怎么读文件"不失忆（确定性提取，
        # 不依赖 LLM writer 是否记得保留读取命令）
        # 2026-08-26: 配方提取独立于 DB 查询 —— DB 缺失时也执行（否则新装/测试
        # 环境 checkpoint 永久丢配方段，实测 Linux 无 state.db 时整段被跳过）
        try:
            _recipes = _extract_read_recipes(_rows, limit=5)
            if _recipes:
                _lines += ["## 数据读取配方(此前成功)", _recipes]
        except Exception:
            pass
    except Exception:
        pass
    for _m in head:
        if isinstance(_m, dict) and _m.get("role") in ("user", "human") \
                and isinstance(_m.get("content"), str) and _m["content"].strip():
            _lines += ["## 起始诉求", _m["content"].strip()[:300]]
            break
    _lines += ["## 提示",
               "以上为早期对话的结构化摘要（保留了关键决策/路径/任务状态）。紧接其后的若干条消息是最近的真实对话，请基于它们继续，不必复述摘要。",
               "如需早期对话的细节（具体数字/原话/中间结果），用 session_search 全文召回：先 session_search(query=关键词) 找到带 message_id 的匹配，再 session_search(session_id=..., around_message_id=<id>, window=5) 拉逐字上下文——禁止凭摘要编造细节。"]
    return "\n".join(_lines)


def _build_recent_turns_digest(session, max_turns=8):
    """2026-08-31: 最近 N 轮对话速览（L2 层确定性注入）。

    用户痛点：上一轮解决过的错误/得出的关键结论，下一轮又忘了 → 重新报错、重新跑。
    这里从 state.db 直接取最近 user/assistant 问答，按轮生成 concise digest，
    每轮注入模型上下文。历史再怎么压缩，最近 8 轮的“问了什么→答了什么”始终可见。
    """
    try:
        import sqlite3 as _sq
        sid = session.get("id", "")
        if not sid:
            return ""
        _dbp = os.path.join(HERMES_HOME_DIR, "state.db")
        if not os.path.exists(_dbp):
            return ""
        _conn = _sq.connect(f"file:{_dbp}?mode=ro", uri=True, timeout=8)
        try:
            _rows = _conn.execute(
                "SELECT role, content FROM messages WHERE session_id=? AND role IN ('user','assistant') AND content IS NOT NULL AND length(content)>0 ORDER BY id DESC LIMIT ?",
                (sid, max_turns * 2 + 2),
            ).fetchall()
        finally:
            _conn.close()
        if not _rows:
            return ""
        _chrono = list(reversed(_rows))
        _entries = []
        _pending_user = None
        for _role, _content in _chrono:
            _c = str(_content or "").strip().replace("\n", " ")[:160]
            if not _c:
                continue
            if _role == "user":
                _pending_user = _c[:90]
            elif _role == "assistant" and _pending_user is not None:
                _entries.append(
                    f"- 问：{_pending_user}\n  答：{_c}"
                )
                _pending_user = None
        if _pending_user is not None:
            _entries.append(f"- 问：{_pending_user[:90]}（本轮用户消息，尚未回答）")
        if not _entries:
            return ""
        _tail = "\n".join(_entries[-max_turns:])
        return (
            "## 最近几轮对话速览（L2，供背景，不是你本轮要回答的内容）\n"
            f"{_tail}\n"
            "【重要】以上是你之前已经问过/答过的内容。已被解决的错误不要再次提起；"
            "已完成的步骤/已给出的结论请直接复用，禁止重新运行或重复回答。"
        )
    except Exception:
        return ""


def _build_pending_question_context(session, user_text):
    """2026-08-31: 待确认问题追踪 — 防止“需要”回答错题/遗忘自己问过的承诺。

    实证：memomics-cd677556 中 agent 问“需要我把这套解释整理进专利结论表吗？”，
    用户答“1.需要。2.为什么你在电脑上做不了？”，agent 却只去验证 bigWig，
    把已确认的任务（整理进专利结论表）丢了 —— 因为上下文没有“上一轮问过什么”的确定性记录。
    原理与 DSH dsh-client-ui-user-questions（PendingQuestion/QuestionComposer）一致：
    问话与答复必须绑定，不靠模型对“需要”的模糊指代。
    """
    try:
        import sqlite3 as _sq
        sid = session.get("id", "")
        if not sid or not (user_text or "").strip():
            return ""
        _dbp = os.path.join(HERMES_HOME_DIR, "state.db")
        if not os.path.exists(_dbp):
            return ""
        _conn = _sq.connect(f"file:{_dbp}?mode=ro", uri=True, timeout=8)
        try:
            _rows = _conn.execute(
                "SELECT content FROM messages WHERE session_id=? AND role='assistant' AND content IS NOT NULL AND length(content)>50 ORDER BY id DESC LIMIT 1",
                (sid,),
            ).fetchall()
        finally:
            _conn.close()
        if not _rows:
            return ""
        _last_assistant = (_rows[0][0] or "").strip()
        # 提取最后一句；以问句结尾且含征询词 → 视为待确认问题
        _parts = re.split(r"(?<=[。！？!?])", _last_assistant)
        _q = ""
        for _p in reversed(_parts):
            _p = _p.strip()
            if _p and (_p.endswith("？") or _p.endswith("?")):
                _q = _p
                break
        if not _q or not re.search(r"(需要|要不要|是否|可以吗|好吗|同意吗|吗)", _q):
            return ""
        if re.search(r"(不要|不用|不需要|不用了|算了|先不)", user_text or ""):
            return ""
        if not re.search(r"(需要|要|是|好|同意|可以|行|当然|好的|嗯)", user_text or ""):
            return ""
        return (
            "【待确认任务提醒 — 你上一轮问过，用户已确认】\n"
            f"你上一轮问：{_q[:300]}\n"
            "用户本轮已回复确认（需要/要/是/好/同意…）。本次必须完成该请求（执行/整理/生成），"
            "不要只复述或延后；若用户同时提出了新问题，请一并回答，两者都要完成。"
        )
    except Exception:
        return ""


def _build_ask_form_context(session, user_text):
    """P3(2026-09-22): 把"确认弹窗的勾选结果"变成确定性上下文（只注入一次）。

    为什么需要：弹窗答复经 chat 通道作为普通用户消息发出，模型可能把它当闲聊；
    这里按 form_id 取回结构化答复（勾选项 + 其他补充），明确告诉模型"这就是答案，
    按此执行、不要再问一遍"，与 DSH 的 PendingQuestion→QuestionComposer 绑定同理。
    """
    try:
        _ans = session.get("_ask_form_answers") or []
        if not _ans:
            return ""
        # 只看最近 10 分钟、还没注入过的答复
        _now = time.time()
        _pick = None
        for _it in reversed(_ans):
            if _it.get("injected"):
                continue
            _ts = _it.get("_ts") or 0
            if _ts and (_now - _ts) > 600:
                continue
            _pick = _it
            break
        if _pick is None:
            return ""
        _pick["injected"] = True
        _sel = _pick.get("selected") or []
        _other = (_pick.get("other") or "").strip()
        _lines = [
            "【用户已在确认弹窗中答复 — 这是确定性答案，不是猜测】",
            f"问题：{(_pick.get('question') or '')[:300]}",
        ]
        if _sel:
            _lines.append("用户勾选：" + "；".join(str(x) for x in _sel))
        if _other:
            _lines.append("用户补充：" + _other[:300])
        _lines.append(
            "要求：按用户勾选的方案直接执行（该确认已满足\"开工前先问清楚\"的门禁），"
            "不要再重复询问同一问题；若用户勾选了多个互斥项，按最先勾选的执行并在结尾说明。"
        )
        return "\n".join(_lines)
    except Exception:
        return ""


def _maybe_rollup_history(session, history):
    """(c) 步进式结构化 checkpoint：重放历史估算超预算时，把头部折叠为结构化摘要 + 保留最近尾窗逐字。

    预算/尾窗可用 MEMOMICS_ROLLUP_BUDGET / MEMOMICS_ROLLUP_TAIL 环境变量调整（便于测试）。
    摘要未变小则不折叠。"""
    if not history or len(history) < 12:
        return history
    try:
        _budget = int(os.environ.get("MEMOMICS_ROLLUP_BUDGET", "60000"))
        _tail = int(os.environ.get("MEMOMICS_ROLLUP_TAIL", "40"))
    except Exception:
        _budget, _tail = 60000, 40
    if _tail <= 0 or len(history) <= _tail + 4:
        return history
    _est = sum(_est_message_tokens(m) for m in history)
    if _est <= _budget:
        return history
    _tail_msgs = history[-_tail:]
    _checkpoint = _build_rollup_checkpoint(session, history[:-_tail])
    if not _checkpoint:
        return history
    if _est_message_tokens({"content": _checkpoint}) >= _est:
        return history
    return [{"role": "system", "content": _checkpoint}] + _tail_msgs


_REQUIREMENTS_MARKERS = ("必须", "不要", "别忘", "以后", "每次", "记住", "记得",
                         "保持不变", "统一", "都要", "都给我", "始终", "一律",
                         "我要求", "我需要", "务必", "请务必", "只能", "只许", "优先")
_REQUIREMENTS_MEM_WORDS = ("记住", "记得", "以后", "每次", "永远", "后续都", "我要求")
# (2026-08-22 用户强调) 特别指定词：用户特别强调/指定的要求 → 标记 (特别指定) +
# 强制进跨会话记忆(trust 0.95) + digest 置顶 —— 最高优先级
_REQUIREMENTS_SPECIAL_WORDS = ("特别记住", "特别指定", "特别重要", "非常重要", "特别强调",
                               "务必记住", "一定记住", "一定要记住", "必须记住", "一定要",
                               "重中之重", "重点记住", "千万记住", "千万别忘", "很重要")
# (2026-08-21) 过滤"发给助手本人的指令"（带'不要调用工具/只用一句话回复'等），
# 避免把对助手的指令误当成用户对项目的持久要求写入 REQUIREMENTS.md
_REQUIREMENTS_SKIP_ASSISTANT = (
    "不要调用任何工具", "不要调用工具", "不用调用工具", "只用一句话回复", "请只回复", "只回复",
    "请简短确认", "请简短回复", "请简短", "请确认", "不要做多余", "请勿", "你别",
    "只做一件事", "不要跑完整", "不要跑分析", "只回答数字", "只回答文件名", "先不要执行",
    "先别执行", "不要执行", "先看下", "看一下就行", "不用跑",
    # (2026-08-22) 元指令尾巴：指代上文的空要求（上面那句已入库，这句是废话）
    # 注意：不用"别忘/别忘了"子串——"路径 X 别忘了"是实义要求，不能误伤
    "记住这一点", "记住这个", "记住这点", "记住这些", "记住那条", "记住这条",
    "记住吧", "别忘了这个", "别忘了那条",
)
# (2026-08-21) 一次性任务指令词：含路径+动作词且无"记住/必须/以后"等 marker →
# 是"这次的任务"不是"持久要求"，不入库、不覆盖已有确认行
_REQUIREMENTS_TASK_WORDS = ("画一张", "画图", "绘图", "帮我分析", "分析一下", "统计一下", "跑一",
                            "读取", "数一下", "报告", "生成", "计算", "做个", "做一张", "画个")
# (2026-08-25) 输出位置词：句子含这些词说明用户指定了持久输出位置 →
# 即使含任务词也必须入库（提取"输出目标子句"），否则下一轮模型忘记文件放哪、重复跑
_OUTPUT_LOCATION_WORDS = ("输出到", "保存到", "放到", "写入", "存到", "生成到", "写到",
                          "输出至", "存放", "拷贝到", "复制到", "导出到")


def _extract_output_clause(s: str) -> str:
    """从"任务词+输出位置词"并存句提取输出目标子句（含路径的部分）。

    "帮我分析 E:/data 并把结果输出到 E:/my_output" → "把结果输出到 E:/my_output"
    "用 E:/data 画一张图，图保存到 E:/figures"      → "图保存到 E:/figures"
    "把最终报告输出到 E:/reports/final"            → "输出到 E:/reports/final"
    提取失败（无路径/子句过短）返回原句——调用方按原句处理。
    """
    try:
        for w in _OUTPUT_LOCATION_WORDS:
            idx = s.find(w)
            if idx < 0:
                continue
            start = idx
            for sep in ("，", ",", "；", ";", "并", "然后", "再"):
                j = s.rfind(sep, 0, idx)
                if j >= 0:
                    start = j + len(sep)
                    break
            clause = s[start:].strip()
            if 4 <= len(clause) <= 200 and (":" in clause or "/" in clause or "\\" in clause):
                return clause
    except Exception:
        pass
    return s
# (2026-08-21 用户强调) 环境/服务器情况信号：版本号/工具+路径/环境词 → 记入环境节
_REQUIREMENTS_ENV_SIGNALS = ("服务器", "本机", "这台机器", "系统环境", "环境", "R 版本", "python 版本",
                             "conda", "库目录", "libPath", "R-libs", "数据目录", "工作目录",
                             "根目录", "路径是", "装在", "安装位置", "数据库地址", "接口地址")
# (2026-08-21 用户强调) 确认词：用户确认某条 → 标"已确认"，下次以用户说明为主
_REQUIREMENTS_CONFIRM_WORDS = ("就用", "就是这个", "就用这个", "就用它", "确认", "没问题",
                               "按这个来", "按这个", "就这么定", "就用这条", "对，就")
# (2026-08-21 用户强调) 已验证词：环境/路径/包已验证存在 → 标 [已验证] (已确认)，
# 下一轮直接复用不再重复验证（省 token）
_REQUIREMENTS_VERIFIED_WORDS = ("已验证", "验证通过", "确认存在", "确认可用", "测试通过",
                                "能跑通", "跑通了", "已存在", "包已装", "装好了", "已装好",
                                "验证过", "没问题了", "可以用了", "检查过了", "测过了")


def _is_env_sentence(s):
    """环境/服务器情况句：含环境信号词，或 版本号+（R/python/conda/环境/库）组合。"""
    if any(w in s for w in _REQUIREMENTS_ENV_SIGNALS):
        return True
    return bool(re.search(r"\d+\.\d+(\.\d+)?", s)) and any(
        w in s for w in ("R ", "R-", "python", "conda", "环境", "版本", "库", "服务器"))


def _apply_confirm(existing, text):
    """用户确认已有条目（'就用/就是这个/确认…'）→ 在该条目尾标 (已确认)。

    返回 (列表, 是否变更)。用户已说明 → 标记为以用户为主。"""
    try:
        if not any(w in text for w in _REQUIREMENTS_CONFIRM_WORDS):
            return list(existing), False
        out, changed = [], False
        for ln in existing:
            if "(已确认)" in ln:
                out.append(ln)
                continue
            if _requirements_overlap(ln, text):
                out.append(ln + " (已确认)")
                changed = True
            else:
                out.append(ln)
        return out, changed
    except Exception:
        return list(existing), False


def _read_requirements(session, limit=8):
    """读会话持久要求文件 results/<sid>/REQUIREMENTS.md（路径优先、最新在前、去重）。"""
    rd = session.get("results_dir") or ""
    if not rd:
        return []
    _p = os.path.join(rd, "REQUIREMENTS.md")
    try:
        if not os.path.isfile(_p):
            return []
        with open(_p, encoding="utf-8", errors="replace") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
    except Exception:
        return []
    if not lines:
        return []
    # (2026-08-22) 特别指定优先置顶（最高优先级），再路径优先、最新在前
    special = [ln for ln in lines if "(特别指定)" in ln]
    rest = [ln for ln in lines if "(特别指定)" not in ln]
    paths = [ln for ln in rest if re.search(r"[A-Za-z]:[/\\]", ln)]
    others = [ln for ln in rest if ln not in paths]
    seen, out = set(), []
    for ln in (special[-limit:] + paths[-limit:] + others[-limit:]):
        if ln not in seen:
            seen.add(ln)
            out.append(ln)
    return out[-limit:]


def _requirement_anchor(text):
    """提取一条要求的锚点：优先绝对路径，否则取最长 ≤12 字中文短语（用于匹配/覆盖旧条目）。"""
    m = re.search(r"[A-Za-z]:[/\\][^\s，。！？!?;；、]+", text or "")
    if m:
        return m.group(0)
    m2 = re.search(r"[\u4e00-\u9fff]{4,12}", text or "")
    if m2:
        return m2.group(0)
    return ""


def _fmt_req_line(r, cap=110):
    """digest 展示行：截断到 cap，但保留 (已确认)/(特别指定) 标记不被截掉。"""
    s = (r or "")[:cap]
    if len(r or "") > cap:
        s = s.rstrip() + "…"
    if "(已确认)" in (r or "") and "(已确认)" not in s:
        s = s[: max(0, cap - 8)].rstrip() + "… (已确认)"
    if "(特别指定)" in (r or "") and "(特别指定)" not in s:
        s = s[: max(0, cap - 8)].rstrip() + "… (特别指定)"
    return s


_REQUIREMENTS_OVERLAP_STOP2 = {"以后", "必须", "都要", "每次", "记住", "这个", "就是", "就用",
                               "现在", "然后", "已经", "都是", "不要", "还是", "可以", "需要",
                               "要求", "按照", "直接", "输出", "生成", "绘制", "画图", "进行",
                               "出来", "完成", "没有", "一个", "那些", "下面"}


def _requirements_overlap(line, text):
    """旧要求行与新文本是否同一主题：绝对路径、共享 ≥1 个 4 字中文片段、
    共享字母数字 token(如 P 值/FDR/4.5.3)、或共享显著 2-gram。"""
    if not line or not text:
        return False
    for m in re.finditer(r"[A-Za-z]:[/\\][^\s，。！？!?;；、]+", line):
        if m.group(0) in text:
            return True
    a4, b4 = set(), set()
    for r in re.findall(r"[\u4e00-\u9fff]+", line):
        for i in range(len(r) - 3):
            a4.add(r[i:i + 4])
    for r in re.findall(r"[\u4e00-\u9fff]+", text):
        for i in range(len(r) - 3):
            b4.add(r[i:i + 4])
    if a4 & b4:
        return True
    # 字母数字 token（P 值 / FDR / 4.5.3 …）—— 更新/作废常靠这些对齐主题
    at = set(re.findall(r"[A-Za-z0-9][A-Za-z0-9._\-]*", line))
    bt = set(re.findall(r"[A-Za-z0-9][A-Za-z0-9._\-]*", text))
    if at & bt:
        return True
    a2 = {line[i:i + 2] for i in range(len(line) - 1) if line[i:i + 2] not in _REQUIREMENTS_OVERLAP_STOP2}
    b2 = {text[i:i + 2] for i in range(len(text) - 1) if text[i:i + 2] not in _REQUIREMENTS_OVERLAP_STOP2}
    return bool(a2 & b2)


def _apply_requirements_change(existing, text):
    """处理用户对已有要求的 移除/更新（用户说错了→能改掉，而不是只 append）。

    - 更新词(改成/改为/换成/其实是/更改为/更正/更新/其实)：移除与新文本同主题的旧条目, 写入新表述
    - 作废词(取消/不要了/不需要/不算/去掉/删掉/删除/不用记/收回/不成立)：移除同主题旧条目
    - 主题匹配：绝对路径精确, 或共享 ≥1 个 4 字中文片段(如"以后出图")
    返回 (处理后的列表, 是否发生动作)。"""
    try:
        is_update = any(w in text for w in ("改成", "改为", "换成", "改用", "更改为", "更正", "更新", "其实是", "其实"))
        is_drop = any(w in text for w in ("取消", "不要了", "不需要", "不算", "去掉", "删掉", "删除", "不用记", "收回", "不成立"))
        if not (is_update or is_drop):
            return list(existing), False
        keep = [ln for ln in existing if not _requirements_overlap(ln, text)]
        changed = len(keep) != len(existing) or is_update
        if is_update:
            # 提取"主语 = 新值"（'出图统计量改成 FDR' → '出图统计量 = FDR'），避免整句塞入
            m = re.search(r"([\u4e00-\u9fffA-Za-z0-9_\-]{2,14}?)(?:改成|改为|换成|改用|更改为)[为是:：]?\s*([^，。！？!?；;、]+)", text)
            if m:
                new_line = f"{m.group(1).strip()} = {m.group(2).strip()}"
            else:
                new_line = re.sub(r"^(其实|改成|改为|换成|改用|更改为|更新|更正)[为是:：]?\s*", "", text.strip()[:160])
            if new_line:
                keep.append(new_line)
        return keep[-40:], changed
    except Exception:
        return list(existing), False


def _verify_requirements(session, lines):
    """核实 REQUIREMENTS 行里的路径是否存在（用户要记住的内容要核实）。

    返回 warning 集合 {存在问题的行: 提示}。相对路径(含 data/ 等)按 results_dir 解析。"""
    rd = session.get("results_dir") or ""
    warns = {}
    for ln in lines or []:
        abs_spans = [(m.start(), m.end()) for m in re.finditer(r"[A-Za-z]:[/\\][^\s，。！？!?;；、]+", ln)]
        for m in re.finditer(r"[A-Za-z]:[/\\][^\s，。！？!?;；、]+", ln):
            p = m.group(0).rstrip("/\\")
            if not os.path.exists(p):
                tag = "（用户已确认但路径不存在，请立即向用户核实！）" if "(已确认)" in ln else " 不存在"
                warns.setdefault(ln.strip()[:140], []).append(f"{p}{tag}")
        # 相对路径校验：跳过落在绝对路径匹配区间内的片段(避免把 C:\…\data\real.csv 重复当相对路径误报)
        for m in re.finditer(r"(?:data|results|output|figures?|scripts?)[/\\][^\s，。！？!?;；、]+", ln):
            if any(m.start() >= a and m.end() <= b for a, b in abs_spans):
                continue
            p = re.sub(r"^\.?[/\\]+", "", m.group(0))
            full = os.path.join(rd, p)
            if rd and not os.path.exists(full):
                warns.setdefault(ln.strip()[:140], []).append(f"{p} 不存在(相对会话目录)")
    return warns


def _extract_and_store_requirements(session, text):
    """把用户明确给的要求/约束/文件路径沉淀为会话级 REQUIREMENTS.md + memory facts。

    (#2 记忆不丢 + 可纠错)：
      1) 结构化写 results/<sid>/REQUIREMENTS.md（文件在就一直在，digest/rollup 都带）
      2) 含明确记忆词(记住/以后/每次…)的要求另写 memory_store facts(user_pref)
      3) 用户说"改成/其实是/取消这条/不要了…" → 移除/更新旧条目(不再盲目 append)
      4) 同一锚点(路径/核心短语)重复陈述 → 覆盖旧条目，避免"旧对 + 新对"并存
      digest 每轮固定带上，并核实其中路径是否存在(不存在则标注 ⚠️ 待核实)。
    """
    try:
        rd = session.get("results_dir") or ""
        if not rd or not os.path.isdir(rd):
            return
        # 2026-08-31 极端评测修复 1/2：注入脚手架元循环——
        # digest 注入文本（"[会话要求 · …]"开头）会被自身规则当成"用户要求"
        # 再次写回 REQUIREMENTS.md（实测生产文件里同一条脚手架重复 8 行）。
        # 注入文本的原始用户消息在末尾，剥掉脚手架前缀后再提取。
        _t = (text or "").strip()
        _INJ = ("[会话要求", "[相关历史记忆", "[会话锚点", "[系统唤醒", "[System:", "[数据读取配方")
        while _t.startswith(_INJ):
            _idx = _t.rfind("\n\n")
            if _idx == -1:
                _t = ""  # 纯脚手架，无用户原文 → 不提取
                break
            _t = _t[_idx + 2:].strip()
        if not _t:
            return
        text = _t
        _p = os.path.join(rd, "REQUIREMENTS.md")
        existing = []
        if os.path.isfile(_p):
            with open(_p, encoding="utf-8", errors="replace") as f:
                existing = [ln.rstrip("\n") for ln in f]

        # 0) 移除/更新语义（用户纠正/否定 → 改掉旧条目）+ 确认标记（用户说"就用/就是这个"→已确认）
        existing, changed = _apply_requirements_change(existing, text or "")
        existing, changed_c = _apply_confirm(existing, text or "")
        changed = changed or changed_c

        _sents = [s.strip() for s in re.split(r"[。！？!?\n;；]", text or "") if s and s.strip()]
        _META_WORDS = ("取消", "不要了", "不需要", "不算", "去掉", "删掉", "删除", "不用记", "收回", "不成立",
                       "改成", "改为", "换成", "改用", "更改为", "更正", "更新", "其实是", "其实")
        added = []
        for _s in _sents:
            if not (4 <= len(_s) <= 200):
                continue
            if _s.startswith(("[会话要求", "[相关历史记忆", "[会话锚点", "[系统唤醒", "[System:", "[数据读取配方", "📊")):
                continue  # 句子级注入前缀残留（2026-08-31 实测元循环残留 1 条）
            if any(_k in _s for _k in _REQUIREMENTS_SKIP_ASSISTANT):
                continue  # 发给助手的指令，不是用户对项目的持久要求
            if re.search(r"[吗呢么吧]？?\s*$", _s) or _s.endswith("?") or re.search(r"(没有|了没|了吗|过没|过吗)$", _s):
                continue  # (压测发现) 问句(如'你记得…吗?'/'验证过没有?')不是要求，不得入库
            if "要不要" in _s or "能不能" in _s:
                continue  # 征询句（"你要不要看看…"）不是持久要求（2026-08-31 实测误报）
            if len(_s) < 16 and ("=" in _s or "==" in _s):
                continue  # 截断的映射片段（"帮我替 = 对应的亚群名"）不是完整要求
            if any(_m in _s for _m in _META_WORDS):
                continue  # (用户纠错) 含"取消/改成/不用记"等元指令的句子是操作不是新要求
            # 2026-08-31 极端评测修复：系统命令输出/服务器命令回显不是要求
            # （实测 "df -h /hwfssz3/… Filesystem Size Used Avail Use%" 被入库）。
            # 注意：命令必须"命令+参数"组合（df -/du /ls /cat …），
            # 裸"conda 环境在 E:/envs"是环境陈述必须放行（回归教训）。
            if re.search(r"^\s*(df\s+-|du\s+\S|ls\s+-|cat\s+\S|head\s+-|tail\s+-|free\s+-|nvidia-smi\b|pip\s+install)", _s) \
                    or ("Filesystem " in _s and "Use%" in _s) \
                    or re.search(r"^\s*[\w-]+@[\w.-]+[:$]\s*$", _s):
                continue
            _has_path = bool(re.search(r"[A-Za-z]:[/\\]\S+", _s))
            _has_marker = any(m in _s for m in _REQUIREMENTS_MARKERS)
            _is_env = _is_env_sentence(_s)
            _is_verified = any(w in _s for w in _REQUIREMENTS_VERIFIED_WORDS)
            # (2026-08-22) 用户特别指定/强调 → (特别指定) 标记 + 强制进跨会话记忆
            _is_special = any(w in _s for w in _REQUIREMENTS_SPECIAL_WORDS)
            # 2026-08-25: 路径类默认全录（向 DSH"全量留痕"哲学靠拢）——
            # 含绝对路径的用户句默认入库（digest 每轮必达），不再因"任务词"整句丢弃。
            # "读取 E:/data 分析"（输入路径）与"输出到 E:/out"（输出位置）都记；
            # 有输出位置时提取输出子句（干净），否则整句入录（保守记住比丢好——
            # 提取规则丢了的后果是模型找不到，见接缝实证）。
            # 豁免仅保留：纠错（META_WORDS）/问句/助手指令/无路径无标志（均在上面过滤）。
            _has_out = any(w in _s for w in _OUTPUT_LOCATION_WORDS)
            _has_task_word = any(w in _s for w in _REQUIREMENTS_TASK_WORDS)
            if _has_out and _has_task_word and _has_path and not _has_marker:
                # 任务词+输出位置并存：提取"输出目标子句"入库（任务动作部分不入库）
                _out_clause = _extract_output_clause(_s)
                if _out_clause and _out_clause != _s:
                    _s = _out_clause
            if not (_has_path or _has_marker or _is_env or _is_verified or _is_special):
                continue
            if any(w in _s for w in _REQUIREMENTS_MEM_WORDS) or _is_special:
                try:
                    from memomics.bio_tools.memory_bridge import store_user_pref
                    # 特别指定 → trust 0.95（召回时优先）；普通记忆要求 → 0.8
                    store_user_pref(f"[用户要求] {_s[:160]}", tags="requirement",
                                    trust_score=0.95 if _is_special else 0.8)
                except Exception:
                    pass
            # (用户强调) 环境/服务器情况 → 加 [环境] 前缀；确认句(就用/就是这个) → 标 (已确认)
            # (2026-08-21) 已验证句(已验证/确认存在/包已装…) → 加 [已验证] 前缀 + (已确认)，
            # 下一轮 digest 携带后模型直接复用，不再重复探测（省 token）
            # (2026-08-22) 特别指定句 → 加 (特别指定) 标记（最高优先级）
            _entry = _s
            if _is_verified and not _has_marker:
                _entry = f"[已验证] {_s}"
            elif _is_env and not _has_marker:
                _entry = f"[环境] {_s}"
            if _is_special:
                _entry = _entry + " (特别指定)"
            if _is_verified:
                _entry = _entry + " (已确认)"
            elif any(w in _s for w in _REQUIREMENTS_CONFIRM_WORDS) and (_has_path or _has_marker or _is_env):
                _entry = _entry + " (已确认)"
            # 2026-08-31 极端评测修复 2/2：去重键规范化——
            # "(已确认)/(特别指定)/[环境]/[已验证]" 是状态标记不是内容，
            # 否则同一句要求因标记变化反复入库（实测"一定要有依据"重复 4 行）
            def _norm_key(x: str) -> str:
                k = x
                for tag in (" (已确认)", " (特别指定)", "[环境] ", "[已验证] "):
                    k = k.replace(tag, "")
                return k.strip()
            if any(_norm_key(_entry) == _norm_key(x) for x in (existing + added)):
                continue
            # 同锚点覆盖(仅路径锚点)：用户对同一完整路径重复陈述 → 替换旧行。
            # 注意用"完整路径相等"而非子串包含——避免 E:/R-libs 误删 E:/R-libs/R-4.5.3
            # (2026-08-21) 旧行带 (已确认) → 新行继承标记（确认过的事实不因换措辞丢失）
            _anc = _requirement_anchor(_s)
            if _anc and _has_path:
                _anc_n = os.path.normpath(_anc)
                _had_confirm = False
                _kept = []
                for ln in existing:
                    if any(os.path.normpath(pp) == _anc_n
                           for pp in re.findall(r"[A-Za-z]:[/\\][^\s，。！？!?;；、]+", ln or "")):
                        if "(已确认)" in ln:
                            _had_confirm = True
                        continue
                    _kept.append(ln)
                existing = _kept
                if _had_confirm and "(已确认)" not in _entry:
                    _entry = _entry + " (已确认)"
            added.append(_entry)
        if not added and not changed:
            return
        existing = (existing + added)[-40:]
        with open(_p, "w", encoding="utf-8") as f:
            f.write("\n".join(existing) + ("\n" if existing else ""))
    except Exception:
        pass


def _build_scripts_digest(session, limit=5):
    """返回会话 scripts/ 目录最近文件清单提示（重复跑图先到这里找），无则空串。"""
    try:
        rd = session.get("results_dir") or ""
        _sdir = os.path.join(rd, "scripts") if rd else ""
        if not _sdir or not os.path.isdir(_sdir):
            return ""
        _fs = sorted([p.name for p in os.scandir(_sdir) if p.is_file()])[-limit:]
        if not _fs:
            return ""
        return f"[会话脚本目录 · scripts/ 已有脚本：{'、'.join(_fs)}，重复跑图/统计先到这里 search_files 找已有脚本复用]"
    except Exception:
        return ""


# ── 产出资产清单（2026-08-25）：输入/输出/脚本/图片的结构化索引 + digest 复用 ──
_ASSET_CATEGORIES = {
    "figure": (".png", ".jpg", ".jpeg", ".pdf", ".svg", ".tiff", ".bmp", ".webp"),
    "table": (".csv", ".tsv", ".xlsx", ".xls", ".txt"),
    "data": (".rds", ".rdata", ".rda", ".h5ad", ".mtx", ".h5", ".parquet", ".loom"),
    "report": (".html", ".md", ".docx", ".pptx"),
    "script": (".r", ".py", ".sh", ".pl"),
    "log": (".log", ".err", ".out"),
}
_ASSET_SKIP = ("task_plan.md", "task_plan.done.md", "REQUIREMENTS.md",
               ".task_state.json", "token_usage.jsonl", "prisma.json",
               "evidence.jsonl", "evidence.csv", "assets.json",
               ".loopx", "__pycache__", "checkpoints", ".git")


def _scan_output_assets(results_dir: str, max_files: int = 200) -> list:
    """扫描会话产出资产（子目录 + 根目录），分类、按时间最新在前。

    返回 [{cat, name, rel, path, mtime, size}]；排除运行账本文件与中间产物。
    """
    assets = []
    if not results_dir or not os.path.isdir(results_dir):
        return assets
    try:
        for root, dirs, files in os.walk(results_dir):
            dirs[:] = [d for d in dirs if d not in _ASSET_SKIP]
            if any(seg in _ASSET_SKIP for seg in root.replace("\\", "/").split("/")):
                continue
            for f in files:
                if f in _ASSET_SKIP or f.endswith((".tmp", ".pyc")):
                    continue
                if len(assets) >= max_files:
                    return assets
                p = os.path.join(root, f)
                try:
                    st = os.stat(p)
                    if st.st_size == 0:
                        continue
                except Exception:
                    continue
                try:
                    rel = os.path.relpath(p, results_dir).replace("\\", "/")
                except Exception:
                    rel = f
                ext = os.path.splitext(f)[1].lower()
                cat = "other"
                for _c, _exts in _ASSET_CATEGORIES.items():
                    if ext in _exts:
                        cat = _c
                        break
                assets.append({"cat": cat, "name": f, "rel": rel,
                               "path": p.replace("\\", "/"),
                               "mtime": st.st_mtime, "size": st.st_size})
        assets.sort(key=lambda a: -a["mtime"])
    except Exception:
        pass
    return assets


def _save_assets_index(session) -> None:
    """刷新产出资产索引 results/<sid>/review/assets.json（回合结束调用）。

    结构：{updated_at, inputs:[读取过的输入路径], assets:[产出文件分类清单]}
    输入路径供"按输入反查产出"（如 E:/data 分析产出了哪些文件）。
    """
    try:
        rd = session.get("results_dir") or ""
        if not rd or not os.path.isdir(rd):
            return
        assets = _scan_output_assets(rd)
        inputs = _extract_input_paths(session, limit=15)
        _rev = os.path.join(rd, "review")
        os.makedirs(_rev, exist_ok=True)
        _tmp = os.path.join(_rev, "assets.json.tmp")
        with open(_tmp, "w", encoding="utf-8") as f:
            json.dump({"updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "inputs": inputs, "assets": assets}, f, ensure_ascii=False)
        os.replace(_tmp, os.path.join(_rev, "assets.json"))
    except Exception:
        pass


def _extract_input_paths(session, limit=10, db_path=None) -> list:
    """从 tool_calls_log 提取本会话读取过的输入路径（数据从哪来）。

    供 assets.json 的 inputs 段使用——后面可按输入反查产出：
    "E:/data/matrix.mtx 分析产出了哪些文件？"（同一 results_dir 下、时间在读取之后）。
    db_path 可注入（单测用临时库）。
    """
    try:
        sid = session.get("id", "") or ""
        if not sid:
            return []
        _dbp = db_path or os.path.join(HERMES_HOME_DIR, "state.db")
        if not os.path.isfile(_dbp):
            return []
        import sqlite3 as _sq
        _conn = _sq.connect(f"file:{_dbp}?mode=ro", uri=True, timeout=8)
        try:
            _rows = _conn.execute(
                "SELECT tool_name, args_json, datetime(timestamp,'unixepoch','localtime') "
                "FROM tool_calls_log WHERE session_id=? "
                "AND (args_json LIKE '%readRDS%' OR args_json LIKE '%read.csv%' "
                "OR args_json LIKE '%read.table%' OR args_json LIKE '%read_parquet%' "
                "OR args_json LIKE '%read_excel%' OR args_json LIKE '%Load10X%' "
                "OR args_json LIKE '%pd.read_%' OR args_json LIKE '%scanpy.read%' "
                "OR args_json LIKE '%fread%' OR args_json LIKE '%read.delim%') "
                "ORDER BY rowid DESC LIMIT ?", (sid, limit * 4)).fetchall()
        finally:
            _conn.close()
        out = []
        seen = set()
        for _tool, _args, _ts in _rows:
            for _m in re.finditer(r"[A-Za-z]:[/\\][^\s'\"\),;]+", str(_args or "")):
                _p = _m.group(0).rstrip("/\\")
                if _p in seen:
                    continue
                seen.add(_p)
                out.append({"path": _p.replace("\\", "/"), "tool": _tool, "ts": _ts or ""})
                if len(out) >= limit:
                    return out
        return out
    except Exception:
        return []


def _build_output_assets_digest(session, limit=8) -> str:
    """产出资产摘要（digest 块）：输入路径 + 产出文件清单。

    优先读 assets.json（快），缺失则现扫。让模型跨轮知道"输入从哪来、
    输出在哪"——复用、汇报、避免重跑、可按输入反查产出。
    """
    try:
        rd = session.get("results_dir") or ""
        if not rd:
            return ""
        _idx = os.path.join(rd, "review", "assets.json")
        assets = None
        inputs = []
        if os.path.isfile(_idx):
            try:
                with open(_idx, encoding="utf-8") as f:
                    _data = json.load(f)
                assets = _data.get("assets") or []
                inputs = _data.get("inputs") or []
            except Exception:
                assets = None
        if assets is None:
            assets = _scan_output_assets(rd)
        if not assets and not inputs:
            return ""
        _tags = {"figure": "📊图", "table": "📋表", "script": "📜脚本",
                 "data": "💾数据", "report": "📄报告", "log": "📝日志"}
        lines = []
        if inputs:
            _in = "、".join(i.get("path", "") for i in inputs[:3])
            lines.append(f"[会话输入路径 · 读取过的数据（{len(inputs)} 个，前 3：{_in}；"
                         f"完整清单与产出对应关系见 review/assets.json）]")
        if assets:
            lines.append(f"[会话产出资产 · 已生成 {len(assets)} 个文件（最新在前；复用/汇报用这些路径，不要重复跑）]")
            for a in assets[:limit]:
                lines.append(f"- {_tags.get(a.get('cat'), '📁')} {a.get('rel', a.get('name', ''))}")
        return "\n".join(lines)
    except Exception:
        return ""


def _session_may_have_result(session):
    """该会话是否可能已有任务结果/产出（用于低置信度 chat 时决定要不要 LLM 兜底路由）。"""
    try:
        rd = session.get("results_dir") or ""
        if rd and os.path.isdir(rd) and any(next(os.scandir(rd), None)):
            return True
    except Exception:
        pass
    return len(session.get("messages") or []) >= 2


def _llm_route_intent(text, session):
    """低置信度 chat 的 LLM 兜底路由（规则分类器兜不住的短句/省略上下文场景）。

    让大模型判断：结果查询 / 进度查询 / 新分析 / 闲聊。失败静默返回 None（维持 chat）。
    仅由 ws chat 处理在 {chat 且置信度低且会话有产出} 的窄带上调用，成本可控。
    """
    _CANDIDATES = ["chat", "result_check", "progress_check", "knowledge_ask",
                   "analysis", "direct_exec", "cancel_task"]
    try:
        import urllib.request as _ur
        import json as _json
        cfg = _current_model or {}
        base = (cfg.get("base_url") or "").rstrip("/")
        key = cfg.get("api_key") or ""
        if not base or not key:
            return None
        prompt = (
            "你是科研助手 MemOmics 的意图路由器。用户消息可能很短且省略上下文。根据当前会话状态判意图，只输出一个词。\n"
            "候选词与含义：\n"
            "result_check=用户问之前任务的结果/产出在哪、出图了吗、还没结果\n"
            "progress_check=用户问任务是否还在跑/进度\n"
            "chat=闲聊或无法判断\n"
            "knowledge_ask=问专业知识\n"
            "analysis=要开始新的分析\n"
            "direct_exec=明确让我直接执行\n"
            "cancel_task=要停止/取消任务\n"
            f"当前会话有结果目录: {session.get('results_dir', '') or '无'}。\n"
            f"用户消息：{str(text)[:200]}\n"
            "只输出一个候选词。"
        )
        body = _json.dumps({
            "model": cfg.get("model", "deepseek-v4-flash"),
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 8,
            "temperature": 0,
        }).encode("utf-8")
        req = _ur.Request(base + "/chat/completions", data=body, headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + (key or ""),
        })
        with _ur.urlopen(req, timeout=15) as r:
            d = _json.loads(r.read().decode("utf-8", "replace"))
        ans = (((d.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip().lower()
        for c in _CANDIDATES:
            if c in ans:
                return c if c != "chat" else None
    except Exception:
        pass
    return None


def _checkpoint_writer_llm(prompt, cfg=None):
    """(P2) writer 的 LLM 后端：一次 OpenAI-compat 调用，输出 §1-§11 checkpoint 文本。失败抛错由调用方兜底。"""
    import urllib.request as _ur
    import json as _json
    cfg = cfg or _current_model or {}
    base = (cfg.get("base_url") or "").rstrip("/")
    key = cfg.get("api_key") or ""
    if not base or not key:
        raise RuntimeError("no model config for checkpoint writer")

    def _one_call(p):
        body = _json.dumps({
            "model": cfg.get("model", "deepseek-v4-flash"),
            "messages": [{"role": "user", "content": p}],
            "max_tokens": 8192,  # 2026-08-22 加固: 4096 易截断(实测只到 §6)，提到 8192
            "temperature": 0.2,
        }).encode("utf-8")
        req = _ur.Request(base + "/chat/completions", data=body, headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + (key or ""),
        })
        with _ur.urlopen(req, timeout=180) as r:
            return _json.loads(r.read().decode("utf-8", "replace"))

    d = _one_call(prompt)
    m = ((d.get("choices") or [{}])[0].get("message") or {})
    txt = (m.get("content") or "").strip()
    # deepseek-v4-flash 等推理模型可能只回 reasoning_content → 兜底取它
    if not txt:
        txt = (m.get("reasoning_content") or "").strip()
    if txt:
        # 2026-08-22 加固: 校验是否覆盖 9+ 个 § 段；不足 → 追加补全请求
        _sec_count = sum(1 for _s in ("§1", "§2", "§3", "§4", "§5", "§6", "§7", "§8", "§9", "§10", "§11")
                         if f"## {_s}" in txt)
        if _sec_count < 9:
            _fill = ("你上一条输出不完整（只覆盖了部分 § 段）。请只补全缺失的段，"
                     "保持原有内容不变，追加输出缺失的 § 段（Markdown，含 § 标题）：\n" + txt[:4000])
            try:
                _d2 = _one_call(_fill)
                _m2 = ((_d2.get("choices") or [{}])[0].get("message") or {})
                _txt2 = (_m2.get("content") or _m2.get("reasoning_content") or "").strip()
                if _txt2:
                    txt = txt.rstrip() + "\n\n" + _txt2
            except Exception:
                pass  # 补全失败不阻塞——run_writer 的 _merge_sections 还会兜底
        return txt
    # 空返回 → 换更短提示重试一次
    short = ("把下面对话压缩为结构化 checkpoint（Markdown，含 §1 Active intent / §2 Next action / "
             "§3 Directives / §5 Current work / §6 Files / §7 Discovered knowledge / §8 Errors / "
             "§10 Decisions / §11 Open notes）。保留路径与用户要求原文：\n" + prompt[:12000])
    d2 = _one_call(short)
    m2 = ((d2.get("choices") or [{}])[0].get("message") or {})
    return (m2.get("content") or m2.get("reasoning_content") or "").strip()


def _auto_anchor_turn(session, user_text="", tool_name="", args=None):
    """系统级自动锚定：用户消息中的路径 + 本轮新产物文件（2026-08-14）。"""
    try:
        from memomics.bio_tools import session_memory as _sm
        _sid = session.get("id", "")
        if user_text:
            _sm.auto_anchor_user_mentions(_sid, user_text)
        if tool_name in ("terminal", "execute_r", "execute_python", "write_file", "scan_data"):
            _rd = session.get("results_dir", "") or ""
            _since = session.get("_turn_start_ts") or (time.time() - 120)
            if _rd:
                # 只读观察命令不扫产物（避免每 30s 的监控命令空转扫盘）
                if tool_name == "terminal":
                    _cmd = str((args or {}).get("command", "")) if isinstance(args, dict) else ""
                    try:
                        from webui import enforcement as _enfx
                        if _cmd and _enfx._is_readonly_terminal(_cmd):
                            return
                    except Exception:
                        pass
                _sm.auto_anchor_recent_files(_sid, _rd, _since, max_files=6)
    except Exception:
        pass


def _env_digest_block() -> str:
    """环境卡片（env_inventory 缓存）—— 追加在 ephemeral_system_prompt 后面。

    只读缓存、绝不探测：本机首扫要 10~40 秒（R 全量探测最慢）、集群还要 SSH，
    放这里会拖慢每次建 agent，也会让系统提示词前缀缓存失效（同样的教训见 KB 预取）。
    缓存为空就返回空串，agent 自己按需调 env_inventory 工具。
    """
    try:
        from memomics.bio_tools import env_inventory as _env
        digest = _env.agent_digest()
        return "\n\n" + digest if digest else ""
    except Exception:
        return ""


def _create_agent(model_config=None, session_id=None, session=None):
    """创建新的 AIAgent 实例 (每次会话独立)
    
    链接 Hermes 原生能力：
    - checkpoints_enabled: 会话快照与回滚
    - session_id: 关联 Hermes 会话状态目录
    - context_compressor: 自动启用（agent_init 内置）
    - background_review: 自动启用（conversation_loop 内置）
    """
    from run_agent import AIAgent
    from webui import enforcement as _enf
    # 挂自动标题总结钩子：rail_review(post) 完成（分析里程碑）时回调 server 侧调度
    try:
        _enf._title_summary_hook = _schedule_title_summary
    except Exception:
        pass
    cfg = model_config or (session or {}).get("model_config") or _current_model
    # 2026-08-08：provider 名按 base_url 智能映射。MemOmics 统一存 provider='openai'，
    # 但 Hermes 的 provider 级配置（请求超时等）按 provider 名读取——opencode.ai 的
    # TLS 间歇性挂起需要短超时（60s）让外层 loop 重试，不能吃 openai 的 900s。
    _provider = cfg.get("provider", "openai")
    try:
        from utils import base_url_host_matches as _host_matches
        if _host_matches(cfg.get("base_url", ""), "opencode.ai"):
            _provider = "opencode-go"
    except Exception:
        pass
    skills_index = _read_skills_index()
    agent = AIAgent(
        base_url=cfg["base_url"],
        api_key=cfg["api_key"],
        provider=_provider,
        model=cfg["model"],
        max_iterations=300,
        max_tokens=8192,  # 2026-08-24 修复(memomics-aa368e59): 默认 None→服务端可能低至 4096，
                          # 长输出(大 dsh-ui JSON/mermaid) 会被 max_tokens 截断成半截 JSON。
                          # 显式 8192，与 checkpoint writer 2026-08-22 加固经验一致。
        enabled_toolsets=["terminal", "file", "code_execution", "memomics", "todo", "memory", "skills", "web", "computer_use", "cronjob", "delegation", "image_gen", "session_search", "browser"],
        ephemeral_system_prompt=skills_index + _PLANNING_PROMPT + "\n\n" + _EXECUTION_POLICY + _env_digest_block(),
        quiet_mode=True,
        tool_progress_mode="all",
        session_id=session_id or f"memomics-{uuid.uuid4().hex[:8]}",
        session_db=_get_session_db(),
        checkpoints_enabled=True,
        checkpoint_max_snapshots=10,
        checkpoint_max_total_size_mb=200,
        checkpoint_max_file_size_mb=10,
    )
    # 注入代码级强制执行回调
    if session:
        cbs = _enf.create_enforcement_callbacks(session, _session_emit, agent_ref=[agent])
        agent.tool_start_callback = cbs["tool_start_callback"]
        agent.tool_complete_callback = cbs["tool_complete_callback"]
        if not agent.tool_progress_callback:
            agent.tool_progress_callback = cbs.get("tool_progress_callback")
    # 注：不注入 CPU/内存 Job 限制（方案 A，2026-08-13）：
    # windows_job.py 的 Job Object 限制因 task_id 断链从未生效，且用户要求
    # “不管 CPU”——单细胞多核任务（plan(multisession)）需要整机算力自由。
    return agent

@app.get("/api/sessions")
async def list_sessions():
    """列出所有会话（按 last_active 降序 — 切换模型会更新 last_active，
    让最近操作的会话排最前，刷新后 autoSelectLatestSession 选中的是它）"""
    ordered = sorted(_sessions.values(),
                     key=lambda s: (s.get("last_active", s["created"]), s.get("created", "")),
                     reverse=True)
    result = []
    for s in ordered:
        msgs = s.get("messages") or []
        if s.get("_messages_loaded", True):
            _count = len(msgs)
            _first = (msgs[0].get("content") or msgs[0].get("text", ""))[:60] if msgs else ""
            _last = (msgs[-1].get("content") or msgs[-1].get("text", ""))[:80] if msgs else ""
        else:
            # 惰性会话：用启动时已取的元数据（不触发全量消息加载）
            _count = int(s.get("_msg_count") or 0)
            _first = (s.get("_first_msg") or "")[:60]
            _last = (s.get("_last_msg") or "")[:80]
        result.append({
            "id": s["id"], "title": s["title"], "created": s["created"],
            "bg_running": s.get("bg_running", False),
            "is_running": bool(s.get("running_agent") or s.get("running_task")),
            "restored": s.get("restored", False),
            "msg_count": _count,
            "model": (s.get("model_config") or {}).get("model", ""),
            "last_active": s.get("last_active", s["created"]),
            "source": s.get("source", "weixin" if s.get("wx_sender_id") else ""),
            "first_message": _first,
            "last_message": _last,
        })
    return {"sessions": result}


@app.post("/api/sessions/new")
async def new_session(title: str = "新会话"):
    """新建会话"""
    s = _create_session(title)
    return {"id": s["id"], "title": s["title"]}


def _sanitize_dir_name(s: str) -> str:
    """清理目录名：只保留字母数字中文下划线连字符，其余替换为_"""
    import re
    s = re.sub(r'[^\w\u4e00-\u9fff_-]', '_', s.strip().lower())
    s = re.sub(r'_+', '_', s).strip('_')
    return s or 'unknown'


@app.get("/")
async def index():
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    with open(html_path, encoding="utf-8") as f:
        return HTMLResponse(f.read(), headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.post("/api/sessions/{sid}/rename-results")
async def rename_results_dir(sid: str, body: dict = None):
    """scan_data 后用 物种_组织_方向_日期 重命名结果目录
    
    body: {species, tissue, direction}
    自动生成: species_tissue_direction_YYYYMMDD/
    如目录已存在则加短ID后缀。
    """
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    
    body = body or {}
    species = _sanitize_dir_name(body.get("species", ""))
    tissue = _sanitize_dir_name(body.get("tissue", ""))
    direction = _sanitize_dir_name(body.get("direction", ""))
    date_str = datetime.now().strftime("%Y%m%d")
    
    parts = [p for p in [species, tissue, direction, date_str] if p]
    if len(parts) < 2:
        return {"ok": False, "error": "Need at least species and tissue"}
    
    # 始终追加短ID，确保目录名可追溯到会话（zip部署/换电脑等场景必备）
    short_id = sid.split("-")[-1] if "-" in sid else sid[:6]
    new_name = "_".join(parts) + "_" + short_id
    old_dir = _sessions[sid]["results_dir"]
    new_dir = os.path.join(RESULTS_DIR, new_name)
    # Persist results_dir to state.db
    try:
        db = _get_session_db()
        if db and hasattr(db, '_conn'):
            db._conn.execute("UPDATE sessions SET cwd = ? WHERE id = ?", (new_dir, sid))
            db._conn.commit()
    except Exception:
        pass
    
    # 问题3: 用户可指定 output_root（桌面等），同时 results/ 下保留备份
    output_root = body.get("output_root", "")  # 用户指定路径
    user_dir = None
    if output_root and os.path.isdir(os.path.dirname(output_root)):
        user_dir = os.path.join(output_root, new_name)

    # P2-4：这一处会真的写（results/ 下的主目录）也真的删（用户目录里的同名目录），两类动作都过门。
    # 观察模式只记账；强制 fs.write/fs.delete 后，越出应用数据根的用户目录会被拦下——
    # 老逻辑是"父目录存在就照删照拷"，用户传个路径就能删掉那底下同名目录，太宽了。
    _app_roots = [RESULTS_DIR, WORK_DIR, MEMOMICS_DIR]
    _denied = _sandbox_precheck("fs.write", new_dir, _app_roots, "sessions.rename_results")
    if not _denied and user_dir:
        _denied = _sandbox_precheck("fs.delete" if os.path.exists(user_dir) else "fs.write",
                                    user_dir, _app_roots, "sessions.rename_results.user_root")
    if _denied:
        return JSONResponse({"ok": False, "error": "sandbox denied: %s" % _denied},
                            status_code=403)

    # 重命名目录 (results/ 下的主目录)
    if os.path.abspath(old_dir) != os.path.abspath(new_dir):
        if os.path.isdir(old_dir):
            os.rename(old_dir, new_dir)
        else:
            os.makedirs(new_dir, exist_ok=True)
        _sessions[sid]["results_dir"] = new_dir

    # 问题3: 如果用户指定了 output_root，复制一份到用户路径（备份仍在 results/）
    if user_dir:
        try:
            import shutil as _shutil
            if os.path.exists(user_dir):
                _shutil.rmtree(user_dir)
            _shutil.copytree(new_dir, user_dir)
        except Exception:
            pass  # 备份失败不阻断主流程
    
    # 同步更新会话标题 + 持久化 results_dir 到 state.db 的 cwd 字段
    title_parts = [body.get(k, "") for k in ["species", "tissue", "direction"] if body.get(k)]
    if title_parts:
        new_title = " ".join(title_parts)
        _sessions[sid]["title"] = new_title
        db = _get_session_db()
        if db:
            try:
                db.set_session_title(sid, new_title)
                # 把 results_dir 存到 cwd 字段，重启后可恢复
                db.update_session_cwd(sid, new_dir.replace("\\", "/"))
            except Exception:
                pass
    
    # 创建完整子目录结构（需求1d：分析log+辩证记录+运行记录强制保留）
    for sub in ["figures", "results", "scripts", "data", "log"]:
        os.makedirs(os.path.join(new_dir, sub), exist_ok=True)
    log_dir = os.path.join(new_dir, "log")
    
    # 设置线程级会话上下文（纯线程隔离，避免多会话竞态）
    from memomics.bio_tools.debate_analysis import set_session_context
    _set_debate_session_context(_sessions.get(sid) or {}, results_dir=new_dir.replace("\\", "/"))
    # 注意：不再写 os.environ，多会话并发时 os.environ 会串会话
    
    return {
        "ok": True, 
        "results_dir": new_dir.replace("\\", "/"),
        "results_name": new_name,
        "log_dir": log_dir.replace("\\", "/"),
        "title": _sessions[sid]["title"]
    }


def _sync_meta_display_name(session, title):
    """改名投影同步：results_dir 下 session.meta.json 存在才写 display_name。

    目录名永不变（改名只写 meta，避免 os.rename 运行中目录的句柄/引用断链），
    state.db 的 title 是 canonical，meta 只是投影——失败不阻断改名。
    """
    try:
        rdir = (session or {}).get("results_dir") or ""
        if not rdir:
            return
        meta_path = os.path.join(rdir, "session.meta.json")
        if not os.path.isfile(meta_path):
            return
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        meta["display_name"] = title
        meta["renamed_at"] = datetime.now().isoformat(timespec="seconds")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # 投影失败不阻断（DB 是权威）


def _append_rename_event(sid, old_title, new_title, source="manual"):
    """改名审计：只追加 JSONL（学 OpenAI4S Action Ledger），可追溯可回滚。"""
    try:
        events_dir = os.path.join(HERMES_HOME_DIR, "sessions")
        os.makedirs(events_dir, exist_ok=True)
        with open(os.path.join(events_dir, "rename_events.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "session_id": sid,
                "old_title": old_title,
                "new_title": new_title,
                "source": source,  # manual=用户改名 / auto=自动总结
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass


# 正在运行的自动标题总结线程（防重入：同一会话同时只跑一个）
_title_summary_locks = set()


def _persist_title_source(sid, source):
    """持久化标题来源标记（auto/manual）到 state.db kv 表。"""
    try:
        db = _get_session_db()
        if db and hasattr(db, "_conn"):
            db._conn.execute(
                "INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)",
                (f"title_source:{sid}", source),
            )
            db._conn.commit()
    except Exception:
        pass


def _load_title_source(sid):
    """从 state.db 恢复标题来源标记；缺省 auto（未标记的历史会话允许自动总结）。"""
    try:
        db = _get_session_db()
        if db and hasattr(db, "_conn"):
            row = db._conn.execute(
                "SELECT value FROM kv WHERE key = ?", (f"title_source:{sid}",)
            ).fetchone()
            if row and row[0] in ("auto", "manual"):
                return row[0]
    except Exception:
        pass
    return "auto"


def _schedule_title_summary(sid):
    """自动标题总结调度（幂等）：手动改名的会话跳过；防抖；防重入。

    触发点：① WS chat 每 5 条用户消息 ② rail_review(post) 完成（分析里程碑）。
    实际总结在后台线程执行，不阻塞消息响应。
    """
    try:
        s = _sessions.get(sid)
        if not s:
            return
        if s.get("title_source") == "manual":
            return  # 用户手动改过名 → 尊重用户，永不自动覆盖
        if sid in _title_summary_locks:
            return  # 已有总结线程在跑
        # 防抖：距上次总结至少新增 4 条用户消息
        user_msgs = [m for m in s.get("messages", []) if m.get("role") in ("user", "human")]
        if len(user_msgs) - int(s.get("_title_summary_at_msg", 0)) < 4:
            return
        _title_summary_locks.add(sid)
        _threading.Thread(target=_auto_summarize_title, args=(sid,), daemon=True).start()
    except Exception:
        pass


def _auto_summarize_title(sid):
    """后台线程：用 LLM 总结会话主要内容 → 生成 ≤20 字标题。

    材料 = 最近用户消息（最多 20 条）；一次轻量 chat completion（httpx 直连）；
    失败/超时/输出无效 → 静默保留旧名（总结是增强，不能成为故障点）。
    写回：state.db（撞名自动续号）+ 内存 + kv 来源标记 + meta 投影 + 审计 + WS 推送。
    """
    try:
        import httpx
        s = _sessions.get(sid)
        if not s or s.get("title_source") == "manual":
            return
        # 收集用户消息（最多 20 条，每条截 120 字）
        msgs = [
            (m.get("content") or m.get("text") or "").replace("\n", " ").strip()
            for m in s.get("messages", [])
            if m.get("role") in ("user", "human") and (m.get("content") or m.get("text") or "").strip()
        ][-20:]
        if len(msgs) < 4:
            return  # 消息太少，总结没有意义
        # 模型配置：会话级优先，全局兜底
        cfg = s.get("model_config") or _current_model
        base_url = str(cfg.get("base_url", "")).rstrip("/")
        if not base_url or not cfg.get("api_key") or not cfg.get("model"):
            return
        url = base_url + "/chat/completions" if not base_url.endswith("/chat/completions") else base_url
        digest = "\n".join("- " + m[:120] for m in msgs)
        prompt = (
            "你是一个会话命名助手。根据以下对话要点，用不超过 20 个汉字概括本会话的核心主题。\n"
            "要求：具体（如'hdWGCNA 网络构建参数选择'），不要空泛（如'生信分析'）。\n"
            "只输出标题本身，不要引号、不要解释、不要编号。\n\n对话要点：\n" + digest
        )
        _hdrs = {"Authorization": f"Bearer {cfg['api_key']}"}
        # 2026-09-13: 合并 config custom_providers[].extra_headers（opencode.ai
        # 网关必需 x-opencode-session，缺则 400 MissingSessionID）
        _hdrs.update(_provider_extra_headers_for(base_url))
        resp = httpx.post(
            url,
            headers=_hdrs,
            json={
                "model": cfg["model"],
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 60,
                "temperature": 0.3,
            },
            timeout=45,
        )
        resp.raise_for_status()
        title = ((resp.json().get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()
        # 清理：去引号/破折号/换行/编号，截断 30 字
        title = title.split("\n")[0].strip(' \"\'“”\u300c\u300d')
        title = re.sub(r"^[-–—:*\d.、\s]+\s*", "", title).strip()
        title = (title or "")[:30].strip()
        if len(title) < 2:
            return  # 输出无效，静默放弃
        if title == s.get("title"):
            return  # 与现名相同，不写
        # 写回 state.db（title 唯一约束：撞名 → 自动续号 "xxx #2"）
        new_title = title
        db = _get_session_db()
        if db:
            try:
                db.set_session_title(sid, title)
            except ValueError:
                try:
                    new_title = db.get_next_title_in_lineage(title)
                    db.set_session_title(sid, new_title)
                except Exception:
                    return
            except Exception:
                return
        old_title = s.get("title")
        s["title"] = new_title
        s["title_source"] = "auto"
        s["_title_summary_at_msg"] = len(
            [m for m in s.get("messages", []) if m.get("role") in ("user", "human")]
        )
        _sync_meta_display_name(s, new_title)
        _append_rename_event(sid, old_title, new_title, source="auto")
        _session_emit(s, {"type": "session_title", "title": new_title, "session_id": sid})
        logger.info(f"Session {sid}: auto title '{old_title}' -> '{new_title}'")
    except Exception as e:
        logger.debug(f"Session {sid}: auto title summary skipped: {e}")
    finally:
        _title_summary_locks.discard(sid)


@app.post("/api/sessions/{sid}/rename")
async def rename_session(sid: str, body: dict = None):
    """用户改名：只写 title 字段（内存 + state.db + meta.json + 审计）。

    六条链路（会话恢复 / 结果目录 / 模型绑定 / 心跳 / 后台任务 / WebSocket 分流）
    全部按 sid 寻址，与 title 无关——改名天然不断链。
    铁律：目录名永不变；state.db 是 canonical；改名可审计。
    """
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    body = body or {}
    raw = (body.get("title") or "").strip()
    if not raw:
        return {"ok": False, "error": "名称不能为空"}
    db = _get_session_db()
    try:
        new_title = db.sanitize_title(raw) if db else raw
        if not new_title:
            return {"ok": False, "error": "名称无效（含非法字符）"}
        if db:
            # title 在 sessions 表有唯一约束，同名抛 ValueError
            db.set_session_title(sid, new_title)
    except ValueError:
        return {"ok": False, "error": "该名称已被其他会话使用，请换一个"}
    except Exception as e:
        return {"ok": False, "error": f"写入失败: {e}"}
    old_title = _sessions[sid].get("title")
    _sessions[sid]["title"] = new_title
    _sessions[sid]["title_source"] = "manual"  # 用户手动改名 → 自动总结永不覆盖
    _persist_title_source(sid, "manual")
    _sync_meta_display_name(_sessions[sid], new_title)
    _append_rename_event(sid, old_title, new_title, source="manual")
    return {"ok": True, "title": new_title, "session_id": sid}


def _session_display_stats(sid, start_ua=0):
    """会话展示统计（只读，失败静默）：token 用量 + 消息时间窗元数据。
    返回 (stats, meta)：meta[k] = 第 (start_ua+k) 个 user/assistant 消息的
    {elapsed, tool_count, tool_names}——页脚显示用。"""
    import sqlite3 as _sq
    _dbp = os.path.join(HERMES_HOME_DIR, "state.db")
    try:
        _conn = _sq.connect(_dbp, timeout=5)
        _usage = _conn.execute(
            "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0),"
            " COALESCE(SUM(api_call_count),0), COALESCE(SUM(estimated_cost_usd),0)"
            " FROM session_model_usage WHERE session_id=?", (sid,)).fetchone()
        _rows = _conn.execute(
            "SELECT timestamp, role FROM messages WHERE session_id=? ORDER BY id", (sid,)).fetchall()
        _tools = _conn.execute(
            "SELECT timestamp, tool_name FROM tool_calls_log WHERE session_id=? ORDER BY timestamp", (sid,)).fetchall()
        _conn.close()
    except Exception:
        return {}, {}
    _ua = [r for r in _rows if r[1] in ("user", "assistant")]
    _meta = {}
    for i in range(start_ua, len(_ua)):
        _ts, _role = _ua[i]
        _nxt = _ua[i + 1][0] if i + 1 < len(_ua) else None
        _wnd = [t[1] for t in _tools if t[0] >= _ts and (_nxt is None or t[0] < _nxt)]
        _meta[i - start_ua] = {
            "elapsed": round(_nxt - _ts, 1) if _nxt else None,
            "tool_count": len(_wnd),
            "tool_names": _wnd[:8],
        }
    _stats = {}
    if _usage:
        _stats = {
            "input_tokens": int(_usage[0] or 0),
            "output_tokens": int(_usage[1] or 0),
            "api_calls": int(_usage[2] or 0),
            "estimated_cost_usd": round(float(_usage[3] or 0), 4),
        }
    return _stats, _meta


def _last_tool_of(sid):
    """会话最近一次工具调用（刷新后运行状态条显示 agent 在干什么）。"""
    import sqlite3 as _sq
    _dbp = os.path.join(HERMES_HOME_DIR, "state.db")
    try:
        _conn = _sq.connect(_dbp, timeout=5)
        _row = _conn.execute(
            "SELECT tool_name FROM tool_calls_log WHERE session_id=? ORDER BY id DESC LIMIT 1", (sid,)).fetchone()
        _conn.close()
        return _row[0] if _row else ""
    except Exception:
        return ""


@app.get("/api/sessions/{sid}/messages")
async def get_messages(sid: str, limit: int = 100):
    """获取会话历史消息 — 默认只返回最近100条，防止大会话卡顿。

    惰性加载：会话完整消息不在内存时，按需从 state.db 加载。
    limit>0 只加载一个窗口（最近 ~2*limit 条），limit<=0 加载全部。"""
    if sid not in _sessions:
        _restore_single_session(sid)
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    session = _sessions[sid]
    if limit and limit > 0:
        # 窗口加载：只取最近窗口，避免大会话全量解码
        if not session.get("_messages_loaded"):
            _win = max(int(limit), 200)
            if len(session.get("messages") or []) < _win:
                session["messages"] = _load_session_messages(sid, limit=_win)
        msgs = (session.get("messages") or [])[-limit:]
        # 2026-08-17: total 给可靠下限——旧会话 _msg_count 可能为 0，
        # 至少不小于已加载窗口长度，前端据此显示"加载更早"入口
        total = len(session["messages"]) if session.get("_messages_loaded") else max(int(session.get("_msg_count") or 0), len(session["messages"] or []))
    else:
        # 显示全部：加载完整历史
        _ensure_session_messages_loaded(session)
        msgs = session.get("messages") or []
        total = len(msgs)
    normalized = []
    for m in msgs:
        # 2026-08-23: 系统注入（唤醒/强制工具调用）与工具消息不进前端对话流
        # 2026-08-26: 注入脚手架常以 role=user 写入历史（喂模型）——按前缀内容级过滤，
        # 否则刷新后 [会话要求]/[相关历史记忆]/[会话锚点]/[系统唤醒] 全部刷屏（实测）
        if m.get("role") in ("system", "tool"):
            continue
        if (m.get("content") or "").lstrip().startswith(_INJECT_PREFIXES):
            continue
        nm = dict(m)
        if "content" not in nm and "text" in nm:
            nm["content"] = nm["text"]
        normalized.append(nm)
    # 2026-08-23: 消息页脚元数据（耗时/工具数）+ 会话统计（token/成本）
    _stats, _meta = {}, {}
    try:
        _ua_before = 0
        _all = session.get("messages") or []
        _win_start = max(0, len(_all) - (limit if (limit and limit > 0) else len(_all)))
        for _m in _all[:_win_start]:
            if _m.get("role") in ("user", "assistant"):
                _ua_before += 1
        _stats, _meta = _session_display_stats(sid, start_ua=_ua_before)
    except Exception:
        pass
    _mi = 0
    _turn = 0
    # P1-4: 每条消息带上轮次号（一条用户提问 = 一轮，它之后的回答都归这一轮），
    # 前端据此把右侧目录项和对话气泡对上号；还没有提问时的开场白记为第 0 轮。
    for m in normalized:
        if m.get("role") == "user":
            _turn += 1
        m["turn"] = _turn
        if m.get("role") in ("user", "assistant"):
            if _mi in _meta:
                m["elapsed"] = _meta[_mi].get("elapsed")
                m["tool_count"] = _meta[_mi].get("tool_count", 0)
                m["tool_names"] = _meta[_mi].get("tool_names", [])
            _mi += 1
    # 2026-09-18: 给前端一个「窗口起点在整段对话里的绝对序号」，
    # 辩论时间线据此把每场辩论插回它真正发生的位置（shown_total = 对话流消息总数）
    try:
        _shown_total = _debate_display_count(sid)
    except Exception:
        _shown_total = -1
    _shown_offset = max(0, _shown_total - len(normalized)) if _shown_total >= 0 else 0
    return {"messages": normalized, "total": total, "stats": _stats,
            "shown_offset": _shown_offset, "shown_total": _shown_total}


# ============ 会话删除 = 数据删除：结果目录连带清理 ============
# 用户要求：会话删除后，该会话在 results/ 下的目录连同里面的数据一并删除，不再保留。
# 三条安全边界：
#   1) 只删 results/ 之内的目录 —— 用户 output_root（桌面/自定义路径）镜像一律不动；
#   2) 目录必须可追溯到本会话（== sid 或含 sid 短 ID），绝不误伤别的会话；
#   3) results/ 根目录自身永不被删（防呆：base 严格子路径判定）。

def _owned_results_dir(sid: str, path) -> bool:
    """归属校验：path 必须真实位于 results/ 之内，且目录名可追溯到 sid。"""
    if not path:
        return False
    try:
        base = os.path.abspath(RESULTS_DIR)
        real_base = os.path.realpath(base)
        abs_path = os.path.abspath(str(path).replace("/", os.sep))
        real_path = os.path.realpath(abs_path)
    except Exception:
        return False
    # 严格位于 results/ 之下（== results/ 自身直接拒绝）；realpath 也必须在里面，
    # 否则符号链接可以指向 results/ 之外 → 拒绝（不跟随链接删除）。
    if not (os.path.normcase(abs_path).startswith(os.path.normcase(base) + os.sep)
            and os.path.normcase(real_path).startswith(os.path.normcase(real_base) + os.sep)):
        return False
    name = os.path.basename(abs_path.rstrip("\\/"))
    if not name or name in (".", ".."):
        return False
    if name == sid:
        return True
    short_id = sid.split("-")[-1] if "-" in sid else ""
    return bool(short_id) and short_id in name


def _owned_results_dirs(sid: str) -> list:
    """收集 results/ 下属于 sid 的目录（含 rename 后的 物种_组织_方向_日期_短ID 型）。"""
    owned = []
    base = os.path.abspath(RESULTS_DIR)
    if not os.path.isdir(base):
        return owned
    try:
        names = os.listdir(base)
    except Exception:
        return owned
    for name in names:
        cand = os.path.join(base, name)
        if _owned_results_dir(sid, cand):
            owned.append(cand)
    return owned


def _force_rmtree(path: str) -> None:
    """物理删除目录（清只读位；Windows 占用由调用方重试兜底）。"""
    if os.path.islink(path):
        os.remove(path)
        return
    if not os.path.lexists(path):
        return
    if not os.path.isdir(path):
        os.remove(path)
        return
    # agent 产物常带只读位 → 先统一放开权限再删
    for root, dirs, files in os.walk(path):
        for n in files:
            p = os.path.join(root, n)
            if not os.path.islink(p):
                try:
                    os.chmod(p, 0o600)
                except Exception:
                    pass
        for n in dirs:
            p = os.path.join(root, n)
            if not os.path.islink(p):
                try:
                    os.chmod(p, 0o700)
                except Exception:
                    pass
    shutil.rmtree(path)


async def _purge_session_results(sid: str, extra_paths=None) -> dict:
    """删除会话在 results/ 下的全部数据目录。

    返回 {deleted: [路径], failed: [{path, error}], external: [未删的外部路径]}。
    外部路径（用户 output_root / 桌面镜像）只报告不删除。
    """
    targets, seen, external = [], set(), []
    for p in list(extra_paths or []):
        if p and not _owned_results_dir(sid, p):
            external.append(str(p).replace("\\", "/"))
    candidates = _owned_results_dirs(sid) + [os.path.join(RESULTS_DIR, sid)] + list(extra_paths or [])
    for p in candidates:
        if not p:
            continue
        try:
            ap = os.path.abspath(str(p).replace("/", os.sep))
        except Exception:
            continue
        if ap in seen or not _owned_results_dir(sid, ap):
            continue
        seen.add(ap)
        if os.path.lexists(ap):
            targets.append(ap)

    deleted, failed = [], []
    loop = asyncio.get_running_loop()
    for ap in targets:
        err = ""
        ok = False
        # P2-4：删动作过门（目标本来就必须是会话自己的 results 目录；强制 fs.delete 后越界即拦，
        # 并且在批量删除里如实报成 failed，而不是整个接口 500）
        _denied = _sandbox_precheck("fs.delete", ap, [RESULTS_DIR], "sessions.purge_results")
        if _denied:
            failed.append({"path": ap.replace("\\", "/"),
                           "error": "sandbox denied: %s" % _denied})
            continue
        for attempt in range(3):
            try:
                await loop.run_in_executor(None, _force_rmtree, ap)
            except Exception as e:  # Windows 文件占用 / 权限
                err = str(e)
            if not os.path.lexists(ap):
                ok = True
                break
            await asyncio.sleep(0.3 * (attempt + 1))  # 等后台脚本释放句柄后重试
        if ok:
            deleted.append(ap.replace("\\", "/"))
        else:
            failed.append({"path": ap.replace("\\", "/"), "error": err or "目录在重试后仍存在"})
    return {"deleted": deleted, "failed": failed, "external": external}


@app.delete("/api/sessions/{sid}")
async def delete_session(sid: str):
    # sid 校验（防路径穿越：只接受 memomics-xxxxxxx 格式）
    if not re.fullmatch(r"memomics-[0-9a-f]{8}", sid or ""):
        return {"ok": False, "error": "invalid sid"}
    try:
        from tools.terminal_tool import clear_task_env_overrides
        clear_task_env_overrides(sid)
    except Exception:
        pass
    # 取消活动任务（TaskSupervisor 触发 task.cancel，租约随 done_callback 释放）
    try:
        _task_supervisor.cancel(sid)
    except Exception:
        pass
    """删除会话：内存 + state.db + agent 资源（真正杀死 agent）+ 结果目录数据"""
    session = _sessions.get(sid)
    _hint_dirs = []
    if session:
        # 结果目录 / 外部镜像先留作线索：内存记录删掉后，磁盘数据仍要按会话清干净
        _hint_dirs = [session.get("results_dir", ""), session.get("output_root", "")]
        # 清理 agent 资源（真正杀死 agent）
        _cleanup_session_agent(session, kill_agent=True)
        del _sessions[sid]
    # 从连接注册表移除该会话（浏览器连接保留，其他会话继续服务）
    clients = _ws_clients_by_session.pop(sid, set())
    for _w, _l in clients:
        sids = _ws_sessions_by_ws.get(_w)
        if sids:
            sids.discard(sid)
    # 从 state.db 删除
    db = _get_session_db()
    if db:
        try:
            db.delete_session(sid)
        except Exception:
            pass
    # 会话删除 = 数据删除（用户要求 2026-09-13）：results/ 下该会话的目录连同全部
    # 分析产物（figures/results/scripts/data/log、token_usage.jsonl 等）物理删除。
    # 放在 agent 清理之后，避免「边写边删」把目录复活。
    purge = await _purge_session_results(sid, extra_paths=_hint_dirs)
    if purge["deleted"]:
        logger.info(f"[MemOmics] 会话 {sid} 结果目录已删除: {purge['deleted']}")
    if purge["failed"]:
        logger.warning(f"[MemOmics] 会话 {sid} 结果目录删除失败: {purge['failed']}")
    if purge["external"]:
        logger.info(f"[MemOmics] 会话 {sid} 外部目录保留（非 results/ 内，未删）: {purge['external']}")
    # 删除 Hermes 会话转录文件（hermes_home/sessions/ 下的 request_dump_*）
    try:
        import glob as _glob
        for _f in _glob.glob(os.path.join(HERMES_HOME_DIR, "sessions", f"*{sid}*")):
            try:
                os.remove(_f)
            except Exception:
                pass
    except Exception:
        pass
    return {
        "ok": True,
        "results_dirs_deleted": purge["deleted"],
        "results_dirs_failed": purge["failed"],
        "external_dirs_kept": purge["external"],
    }


# --- 模型切换 ---

# --- Skill 个性化管理 ---

SKILLS_BIO_DIR = os.path.join(HERMES_HOME_DIR, "skills", "bioinformatics")

def _load_skills_config() -> dict:
    """读取 config.yaml 的 skills 部分"""
    import yaml as _yaml
    cfg_path = os.path.join(HERMES_HOME_DIR, "config.yaml")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = _yaml.safe_load(f) or {}
        return cfg.get("skills", {}) or {}
    except Exception:
        return {}

def _save_skills_disabled(disabled_list: list):
    """保存 disabled skill 列表到 config.yaml"""
    import yaml as _yaml
    cfg_path = os.path.join(HERMES_HOME_DIR, "config.yaml")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = _yaml.safe_load(f) or {}
        cfg["skills"] = cfg.get("skills") or {}
        cfg["skills"]["disabled"] = sorted(set(disabled_list))
        with open(cfg_path, "w", encoding="utf-8") as f:
            _yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
    except Exception as e:
        logger.warning(f"save skills config failed: {e}")

@app.post("/api/skills/register")
async def register_skill(request: Request):
    """手动注册 skill：生成 skill.json + 添加到 SKILLS_INDEX"""
    try:
        from webui import auto_register
        data = await request.json()
        skill_name = data.get("skill", "")
        trigger_kw = data.get("trigger_keywords", None)
        register_soul = data.get("register_soul", False)
        auto_register.init(
            os.path.join(HERMES_HOME_DIR, "skills", "bioinformatics"),
            os.path.join(HERMES_HOME_DIR, "SKILLS_INDEX.md"),
            os.path.join(HERMES_HOME_DIR, "SOUL.md"),
        )
        result = auto_register.register_skill(skill_name, trigger_kw, register_soul)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/skills/manage")
async def get_skills_manage():
    """返回所有 skill 列表 + disabled 状态"""
    skills_cfg = _load_skills_config()
    disabled = set(skills_cfg.get("disabled") or [])
    all_skills = []
    if os.path.isdir(SKILLS_BIO_DIR):
        for d in sorted(os.listdir(SKILLS_BIO_DIR)):
            sj = os.path.join(SKILLS_BIO_DIR, d, "skill.json")
            if not os.path.isfile(sj):
                continue
            try:
                import json as _json
                data = _json.load(open(sj, "r", encoding="utf-8"))
                all_skills.append({
                    "name": d,
                    "display_name": data.get("name", d),
                    "category": data.get("category", ""),
                    "description": data.get("description", ""),
                    "disabled": d in disabled,
                })
            except Exception:
                all_skills.append({"name": d, "display_name": d, "category": "", "description": "", "disabled": d in disabled})
    return {"skills": all_skills, "disabled_count": len(disabled), "total": len(all_skills)}

@app.put("/api/skills/manage")
async def put_skills_manage(request: Request):
    """更新 disabled skill 列表"""
    body = await request.json()
    disabled_list = body.get("disabled", [])
    _save_skills_disabled(disabled_list)
    return {"ok": True, "disabled_count": len(disabled_list)}

def _public_model_config() -> dict:
    """对浏览器脱敏的模型配置：不含 api_key 明文，只带 has_key 状态"""
    cfg = dict(_current_model)
    cfg["has_key"] = _is_valid_api_key(cfg.get("api_key"))
    cfg.pop("api_key", None)
    return cfg


@app.get("/api/models")
async def list_models(session_id: str = ""):
    """列出预设模型 + 当前模型

    - 带 session_id：current 返回该会话的 model_config（会话级切换后前端显示真实当前模型）。
    - 不带 session_id：返回全局 _current_model（兼容旧行为）。
    """
    cur = dict(_current_model)
    if session_id:
        s = _sessions.get(session_id)
        if s and s.get("model_config"):
            cur = dict(s["model_config"])
    return {"presets": _preset_models, "current": cur}


@app.post("/api/models/switch")
async def switch_model(payload: dict):
    """切换模型

    - 带 session_id：会话级切换 — 只影响该会话（独立 model_config + 重建该会话 agent），
      持久化到 Hermes state.db（update_session_model / update_session_billing_route），
      重启/重连后自动恢复；不影响其他会话和全局 _current_model。
    - 不带 session_id：全局切换（兼容旧行为）— 广播所有会话 + 写 model_config.json。
    """
    global _current_model
    sid = payload.get("session_id") or ""
    model = payload.get("model", "")
    base_url = payload.get("base_url", "")
    api_key = payload.get("api_key", "")
    provider = payload.get("provider", "")

    # ── 自动补全（2026-08-08 重新设计）：前端只需传 model id（+可选 provider_id）。
    # 原来要求前端把 base_url/api_key 都传全，旧页面/简化调用方缺字段时切换
    # 静默失败或串 key。现在后端按 model id 在已配置的 provider 里查补。
    if model and not base_url:
        _prov_hint = payload.get("provider_id") or ""
        _found = False
        for _pid, _saved in _provider_keys.items():
            if not (_saved or {}).get("api_key") and not (_saved or {}).get("local"):
                continue
            _p = _PROVIDERS_INDEX.get(_pid)
            if not _p:
                continue
            if _prov_hint and _pid != _prov_hint:
                continue
            for _m in _p.get("models", []):
                if _m["id"] == model:
                    base_url = _p["api"]
                    api_key = _saved["api_key"]
                    provider = provider or "openai"
                    _found = True
                    break
            if _found:
                break
        if not _found:
            return JSONResponse(
                {"error": f"模型 '{model}' 未配置 API Key，请先到设置页选择 Provider 并保存 Key"},
                status_code=400,
            )

    if sid:
        # ── 会话级切换 ──
        s = _sessions.get(sid)
        if s is None:
            return JSONResponse({"error": f"Session '{sid}' 不存在"}, status_code=404)
        new_cfg = dict(s.get("model_config") or _current_model)
        if model:
            new_cfg["model"] = model
        if base_url:
            new_cfg["base_url"] = base_url
        if api_key:
            new_cfg["api_key"] = api_key
        if provider:
            new_cfg["provider"] = provider
        s["model_config"] = new_cfg
        # 2026-08-08：切换模型 = 用户活跃操作 → 更新 last_active，
        # 让该会话在 /api/sessions 列表排到最前（刷新后 autoSelectLatestSession
        # 选中的是它，而不是某个空配置的自检/新会话 → 下拉框显示切过的模型）。
        s["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 清除该会话缓存的 agent — 下次发消息时用新模型重建
        if s.get("agent"):
            try:
                s["agent"].close()
            except Exception:
                pass
            s["agent"] = None
        # 持久化到 Hermes state.db（重启后自动恢复会话级模型）
        # 会话级锁定：此后全局模型切换不再覆盖本会话（互不影响）
        s["model_locked"] = True
        try:
            db = _get_session_db()
            if db:
                import json as _json
                db.update_session_meta(sid, _json.dumps(new_cfg, ensure_ascii=False), model or new_cfg.get("model"))
                if provider or base_url:
                    db.update_session_billing_route(
                        sid,
                        provider=provider or new_cfg.get("provider", "openai"),
                        base_url=base_url or new_cfg.get("base_url", ""),
                    )
        except Exception as e:
            print(f"[MemOmics] 会话模型持久化失败: {e}", flush=True)
        return {"ok": True, "session_id": sid, "current": dict(new_cfg)}

    # ── 全局切换（原行为） ──
    _current_model["model"] = payload.get("model", _current_model["model"])
    _current_model["api_key"] = payload.get("api_key", _current_model["api_key"])
    _current_model["base_url"] = payload.get("base_url", _current_model["base_url"])
    _current_model["provider"] = payload.get("provider", _current_model["provider"])
    # 同步到所有跟随全局的 session（修复: 旧 session 用旧配置的 bug）
    # 做过会话级切换（model_locked）的会话保持自己的模型，互不影响
    for s in _sessions.values():
        if s.get("model_locked"):
            continue
        s["model_config"] = dict(_current_model)
        # 清除缓存的 agent — 下次发消息时用新模型重建
        if s.get("agent"):
            try:
                s["agent"].close()
            except Exception:
                pass
            s["agent"] = None
    # 持久化到文件 (重启后自动恢复)
    _save_model_config()
    # 2026-09-13: 全局换模型后同步刷新辩论 env（无会话上下文的调用走这条兜底通道）
    try:
        _sync_debate_env()
    except Exception:
        pass
    return {"ok": True, "current": _public_model_config()}


# --- Provider 列表 (国内 + 国际热门) ---

@app.get("/api/providers")
async def list_providers():
    """列出所有可用 provider — 国内热门 + 国际大厂"""
    items = []
    for p in _CHINA_PROVIDERS:
        saved = _provider_keys.get(p["id"], {})
        items.append({
            "id": p["id"],
            "name": p["name"],
            "api": p["api"],
            "env_var": p.get("env_var", ""),
            "group": p.get("group", "其他"),
            "model_count": len(p.get("models", [])),
            "has_key": _is_valid_api_key(saved.get("api_key")),
            "is_custom": p["id"] == "dcs-cloud",
        })
    # 2026-08-27: 用户自定义 provider（custom-*）并入列表
    for pid, cp in _custom_providers.items():
        saved = _provider_keys.get(pid, {})
        items.append({
            "id": pid,
            "name": cp.get("name", pid),
            "api": cp.get("api", ""),
            "env_var": "",
            "group": "⭐ 自定义",
            "model_count": len(cp.get("models", [])),
            "has_key": _is_valid_api_key(saved.get("api_key")),
            "is_custom": True,
        })
    groups = {}
    for it in items:
        g = it["group"]
        groups[g] = groups.get(g, 0) + 1
    return {"providers": items, "total": len(items), "groups": groups}


def _mask_key(k):
    """API key 脱敏显示：只露首尾 4 位"""
    if not k:
        return ""
    if len(k) <= 10:
        return "****"
    return k[:4] + "…" + k[-4:]


@app.get("/api/imagegen/config")
async def get_imagegen_config():
    """读取图像生成配置（key 脱敏）"""
    cfg = {"provider": _image_gen_config.get("provider", "openai-compatible")}
    for section in ("openai_compatible", "dashscope"):
        sub = _image_gen_config.get(section, {}) or {}
        shown = dict(sub)
        if shown.get("api_key"):
            shown["api_key"] = _mask_key(shown["api_key"])
            shown["has_key"] = True
        else:
            shown["has_key"] = False
        cfg[section] = shown
    p = cfg["provider"]
    section_key = {"openai-compatible": "openai_compatible"}.get(p, p)
    sub = _image_gen_config.get(section_key, {}) or {}
    ready = False
    if sub.get("api_key"):
        if p == "dashscope":
            ready = bool(sub.get("model"))
        else:
            ready = bool(sub.get("base_url") and sub.get("model"))
    cfg["ready"] = ready
    return cfg


@app.post("/api/imagegen/config")
async def save_imagegen_config(body: dict):
    """保存图像生成配置（provider 下拉 + 各 section 字段）"""
    try:
        payload = body or {}
        if not isinstance(payload, dict):
            return JSONResponse({"error": "请求体必须是 JSON 对象"}, status_code=400)
        if "provider" in payload and payload["provider"] in ("openai-compatible", "dashscope"):
            _image_gen_config["provider"] = payload["provider"]
        for section in ("openai_compatible", "dashscope"):
            if section in payload and isinstance(payload[section], dict):
                sub = _image_gen_config.setdefault(section, {})
                for k, v in payload[section].items():
                    if v is None:
                        continue
                    if k == "api_key" and isinstance(v, str) and (v == "****" or "…" in v):
                        continue  # 脱敏值不回写
                    sub[k] = v
        _save_image_gen_config()
        _sync_imagegen_provider_to_hermes()  # image_generate 工具可见性依赖 config.yaml 的 image_gen.provider
        return {"ok": True, "provider": _image_gen_config.get("provider")}
    except Exception as exc:
        return JSONResponse({"error": f"保存图像生成配置失败: {exc}"}, status_code=400)


@app.get("/api/providers/{pid}/models")
async def get_provider_models(pid: str):
    """返回指定 provider 的模型列表"""
    p = _PROVIDERS_INDEX.get(pid)
    if not p:
        return JSONResponse({"error": f"Provider '{pid}' not found"}, status_code=404)
    models = []
    for m in p.get("models", []):
        models.append({
            "id": m["id"], "name": m["name"],
            "reasoning": m.get("reasoning", False),
            "tool_call": m.get("tool_call", False),
        })
    return {"provider": pid, "models": models, "base_url": p["api"]}


_OPENCODE_SESSION_HOST = "opencode.ai"


def _provider_extra_headers_for(base_url):
    """按 base_url 匹配 config.yaml custom_providers[].extra_headers（2026-09-13）。

    opencode.ai zen 网关要求每个请求带 x-opencode-session，缺则一律 400
    MissingSessionID。Hermes 底座走 openai SDK 时由
    get_custom_provider_extra_headers 注入，但 MemOmics 侧自建 httpx 调用
    （会话自动命名等）绕过底座，必须自行合并。匹配不到返回 {}。
    """
    if not base_url:
        return {}
    try:
        from hermes_cli.config import read_raw_config
        target = str(base_url).rstrip("/").lower()
        if target.endswith("/chat/completions"):
            target = target[: -len("/chat/completions")]
        cfg = read_raw_config() or {}
        for c in cfg.get("custom_providers") or []:
            if not isinstance(c, dict):
                continue
            for field in ("base_url", "api_base"):
                cand = str(c.get(field) or "").rstrip("/").lower()
                if cand and cand == target:
                    extra = c.get("extra_headers")
                    if isinstance(extra, dict) and extra:
                        return {str(k): str(v) for k, v in extra.items()}
                    return {}
    except Exception as e:
        print(f"[WARN] 读取 provider extra_headers 失败({base_url}): {e}")
    return {}


def _build_hermes_provider_entry(pid, name, api_base, api_key, models, prev=None):
    """构造写入 Hermes config.yaml 的 custom_providers 条目（2026-09-10 修复）。

    1) 同时写 `base_url`：Hermes 的 ProviderProfile / per-provider `extra_headers`
       匹配只认 `base_url`（hermes_cli/config.py:get_custom_provider_extra_headers），
       此前只写 `api_base` → 该类配置永远匹配不上，静默失效。
    2) 保留原有附加字段（extra_headers / api_mode / ssl_* / context_length…）：
       原实现每次保存 key 都从零重建条目，会抹掉用户或底座写入的附加设置。
    3) opencode.ai 网关自动补 `x-opencode-session`：该网关缺此请求头会直接
       400 MissingSessionID（"cannot be routed efficiently"）——这是 opencode-go
       提供商在 MemOmics 里"能列模型但一发消息就失败"的根因。会话 id 用于上游
       路由/缓存亲和，生成一次后随 config 持久化、稳定复用。
    """
    entry = dict(prev) if isinstance(prev, dict) else {}
    entry.update({
        "id": pid,
        "name": name,
        "api_base": api_base,     # MemOmics 自身读取的字段
        "base_url": api_base,     # Hermes 底座/匹配器读取的字段
        "api_key": api_key if _is_valid_api_key(api_key) else "",
        "models": models,
    })
    try:
        import urllib.parse as _up_mod
        host = (_up_mod.urlparse(api_base).hostname or "").lower()
    except Exception:
        host = ""
    headers = entry.get("extra_headers")
    headers = dict(headers) if isinstance(headers, dict) else {}
    if _OPENCODE_SESSION_HOST in host and not headers.get("x-opencode-session"):
        headers["x-opencode-session"] = str(uuid.uuid4())
        print("[MemOmics] 已为 opencode.ai 网关补充 x-opencode-session 请求头")
    if headers:
        entry["extra_headers"] = headers
    return entry


def _sync_custom_providers_to_hermes(pid=None):
    """把「有 key 的 provider」同步为 Hermes config.yaml 的 custom_providers。

    修复 2026-08-08：provider key 原来只存 MemOmics 的 provider_keys.json，
    Hermes 底座（config.yaml）看不到 → 底座侧模型路由/校验对不上。现每个
    保存/删除 key 的操作都同步一份到 config.yaml，与底座本地配置一致。
    """
    try:
        from hermes_cli.config import read_raw_config, atomic_config_write, get_config_path
        cfg = read_raw_config() or {}
        existing = {}
        for c in cfg.get("custom_providers") or []:
            if isinstance(c, dict) and c.get("id"):
                existing[c["id"]] = c
        if pid is None:
            # 2026-08-27: 遍历所有有 key 的 provider（内置 + 用户自定义 custom-*），
            # 原实现只遍历 _CHINA_PROVIDERS → 自定义 provider 的 key 不进 Hermes 底座
            for _pid in list(_provider_keys.keys()):
                saved = _provider_keys.get(_pid)
                if not (saved and saved.get("api_key")):
                    continue
                p = _PROVIDERS_INDEX.get(_pid) or {}
                _api = saved.get("base_url") or p.get("api", "")
                existing[_pid] = _build_hermes_provider_entry(
                    _pid, p.get("name", _pid), _api, saved["api_key"],
                    p.get("models", []), existing.get(_pid))
        elif pid in _provider_keys and _provider_keys[pid].get("api_key"):
            p = _PROVIDERS_INDEX.get(pid) or {}
            saved = _provider_keys[pid]
            _api = saved.get("base_url") or p.get("api", "")
            existing[pid] = _build_hermes_provider_entry(
                pid, p.get("name", pid), _api, saved["api_key"],
                p.get("models", []), existing.get(pid))
        else:
            existing.pop(pid, None)
        cfg["custom_providers"] = list(existing.values())
        atomic_config_write(get_config_path(), cfg)
        return True
    except Exception as e:
        print(f"[WARN] 同步 custom_providers 到 config.yaml 失败: {e}")
        return False


@app.post("/api/providers/{pid}/key")
async def save_provider_key(pid: str, payload: dict):
    """保存指定 provider 的 API Key（同时同步 Hermes config.yaml custom_providers）"""
    if pid not in _PROVIDERS_INDEX:
        return JSONResponse({"error": f"Provider '{pid}' not found"}, status_code=404)
    key = (payload.get("api_key") or "").strip()
    if not key:
        return JSONResponse({"error": "api_key is required"}, status_code=400)
    _provider_keys[pid] = {"api_key": key, "base_url": _PROVIDERS_INDEX[pid]["api"]}
    _save_provider_keys()
    _sync_custom_providers_to_hermes(pid)
    # 联动：全局模型正在用这个 provider 时，同步新 key——
    # 否则"设置页存 key + 设全局模型"的顺序反了就会用旧 key（微信/新会话都会中招）
    if _current_model.get("provider") == pid or _current_model.get("base_url") == _PROVIDERS_INDEX[pid]["api"]:
        _current_model["api_key"] = key
        _save_model_config()
        for s in _sessions.values():
            if s.get("model_locked"):
                continue  # 会话级锁定的配置不联动
            if s.get("model_config") and s["model_config"].get("base_url") == _PROVIDERS_INDEX[pid]["api"]:
                s["model_config"]["api_key"] = key
        print(f"[MemOmics] provider {pid} 的 key 已同步到全局模型配置", flush=True)
    return {"ok": True, "provider": pid, "has_key": True}


@app.delete("/api/providers/{pid}/key")
async def delete_provider_key(pid: str):
    """删除指定 provider 的 API Key（同步移除 Hermes config.yaml custom_providers 条目）"""
    if pid in _provider_keys:
        del _provider_keys[pid]
        _save_provider_keys()
        _sync_custom_providers_to_hermes(pid)
    return {"ok": True}


@app.post("/api/provider/local")
async def add_local_provider(payload: dict):
    """保存本地 OpenAI 兼容模型为免 key provider（P2，仅 loopback）"""
    model = payload.get("model") or ""
    base_url = payload.get("base_url") or ""
    server_name = payload.get("server") or "local"
    if not model or not base_url:
        return JSONResponse({"error": "model and base_url required"}, status_code=400)
    import urllib.parse as _up
    host = _up.urlparse(base_url).hostname or ""
    if host not in ("127.0.0.1", "localhost", "::1"):
        return JSONResponse({"error": "仅允许本地 loopback 地址"}, status_code=400)
    pid = f"local-{_sanitize_dir_name(server_name)}"
    if pid not in _PROVIDERS_INDEX:
        _PROVIDERS_INDEX[pid] = {"id": pid, "name": f"本地 {server_name}",
                                 "api": base_url, "models": []}
    _p = _PROVIDERS_INDEX[pid]
    if not any(m.get("id") == model for m in _p.get("models", [])):
        _p.setdefault("models", []).append({"id": model, "name": model})
    _provider_keys[pid] = {"api_key": "", "local": True, "base_url": base_url}
    _save_provider_keys()
    try:
        _sync_custom_providers_to_hermes()
    except Exception:
        pass
    return {"ok": True, "provider_id": pid, "model": model}


@app.get("/api/models/local")
async def detect_local_models():
    """扫描本地 OpenAI 兼容推理服务器（P2）：Ollama / LM Studio / vLLM / llama.cpp

    只读探测 loopback 常见端口，不修改任何配置；前端可展示/一键添加。
    """
    import json as _json
    import urllib.request
    candidates = [
        ("ollama", "http://127.0.0.1:11434/v1/models"),
        ("lm-studio", "http://127.0.0.1:1234/v1/models"),
        ("vllm", "http://127.0.0.1:8000/v1/models"),
        ("llama.cpp", "http://127.0.0.1:8080/v1/models"),
    ]
    found = []
    for name, url in candidates:
        try:
            if _net_guard is not None:
                # net.local：本机服务发现只认环回、默认放行（不该要授权，强制模式下也要能用）
                with _net_guard.urlopen(url, timeout=2.0,
                                        headers={"Accept": "application/json"},
                                        action="net.local",
                                        source="api.models.local") as r:
                    d = _json.loads(r.read().decode("utf-8"))
            else:
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=2) as r:
                    d = _json.loads(r.read().decode("utf-8"))
            for m in d.get("data", []):
                mid = m.get("id") or m.get("model") or ""
                if not mid:
                    continue
                found.append({
                    "id": mid, "name": mid, "provider": "local",
                    "server": name, "base_url": url.rsplit("/v1", 1)[0] + "/v1",
                })
        except Exception:
            continue
    return {"models": found, "count": len(found)}


# === 自定义 Provider API（2026-08-27：任意 OpenAI 兼容提供商 + 自定义模型）===

@app.get("/api/providers/custom")
async def list_custom_providers():
    """列出用户自定义 provider（key 脱敏）"""
    items = []
    for pid, p in _custom_providers.items():
        saved = _provider_keys.get(pid) or {}
        items.append({
            "id": pid,
            "name": p.get("name", pid),
            "base_url": p.get("api", ""),
            "models": p.get("models", []),
            "has_key": _is_valid_api_key(saved.get("api_key")),
            "key_masked": _mask_key(saved.get("api_key", "")),
            "local": bool(saved.get("local")),
        })
    return {"providers": items, "total": len(items)}


def _normalize_custom_models(models_raw):
    """模型归一化：["m1","m2"] 或 [{"id":"m1","name":"..."}] → [{"id","name",...}]"""
    models = []
    for m in models_raw or []:
        if isinstance(m, dict):
            _mid = str(m.get("id") or "").strip()
            if not _mid:
                continue
            models.append({"id": _mid, "name": str(m.get("name") or _mid).strip(),
                           "reasoning": bool(m.get("reasoning")),
                           "tool_call": bool(m.get("tool_call"))})
        elif isinstance(m, str) and m.strip():
            models.append({"id": m.strip(), "name": m.strip()})
    return models


def _normalize_base_url(raw):
    """URL 规整：完整 chat/completions 端点 → base_url。
    支持：https://host/v1/chat/completions → https://host/v1
          https://host/v1 → 原样
          https://host → 原样（/models 探测会自动补 /v1 变体）"""
    url = (raw or "").strip()
    for tail in ("/chat/completions", "/completions"):
        if url.endswith(tail):
            url = url[: -len(tail)]
    return url.rstrip("/")


def _safe_str(v):
    """2026-08-28: 请求字段类型防御——误传 list/数字等取首元素或空，不 500。"""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (list, tuple)) and v:
        return str(v[0]).strip()
    if v is None:
        return ""
    return str(v).strip()


@app.post("/api/providers/custom/discover")
async def discover_custom_models(payload: dict):
    """输入 URL（支持完整 chat/completions 端点）+ API Key → 自动拉取该端点所有模型。

    走 OpenAI 兼容 /models 列表接口；带代理 fallback 直连（与 _http_get_json 同策略）。
    """
    raw = _safe_str(payload.get("url") or payload.get("base_url"))
    api_key = _safe_str(payload.get("api_key"))
    base = _normalize_base_url(raw)
    if not base.startswith(("http://", "https://")):
        return JSONResponse({"error": "URL 需以 http(s):// 开头"}, status_code=400)
    import urllib.request as _ur
    import urllib.error as _uerr
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    # /models 端点变体：base + /v1 兜底
    candidates = [base + "/models"]
    if not base.endswith("/v1"):
        candidates.append(base + "/v1/models")
    last_err = ""
    for _url in candidates:
        for proxy in (_PROXY, None):
            try:
                req = _ur.Request(_url, headers=headers)
                # 2026-09-23: 统一走 _url_opener（certifi 信任库 + 代理/直连）
                with _url_opener(proxy).open(req, timeout=20) as r:
                    data = json.loads(r.read().decode("utf-8", "replace"))
                # OpenAI 兼容三种形态：data[] / models[] / object=list 的 data
                raw_models = data.get("data") or data.get("models") or []
                if not isinstance(raw_models, list):
                    raise ValueError("模型列表格式不识别")
                models = []
                for m in raw_models:
                    if isinstance(m, str):
                        models.append({"id": m, "name": m})
                        continue
                    if not isinstance(m, dict):
                        continue
                    mid = m.get("id") or m.get("model") or ""
                    if not mid:
                        continue
                    models.append({"id": str(mid), "name": str(m.get("name") or m.get("display_name") or mid)})
                if models:
                    return {"ok": True, "base_url": base, "url_used": _url,
                            "models": models, "count": len(models)}
                last_err = "端点返回空模型列表"
            except _uerr.HTTPError as e:
                last_err = f"HTTP {e.code}: {e.reason}"
                if e.code in (401, 403):
                    return JSONResponse({"error": f"{_url} 返回 {e.code} —— API Key 无效或无权访问"}, status_code=400)
                if e.code == 404:
                    continue  # 试下一个端点变体
            except Exception as e:
                last_err = str(e)[:150]
    return JSONResponse({"error": f"模型发现失败（{base}/models）：{last_err or '无法连接'}。请确认 URL 正确、Key 有效、端点支持 OpenAI 兼容 /models。"}, status_code=400)


@app.post("/api/providers/custom")
async def add_custom_provider(payload: dict):
    """添加自定义 OpenAI 兼容 provider：名称 + base_url + api_key + 模型列表"""
    name = (payload.get("name") or "").strip()
    base_url = (payload.get("base_url") or "").strip().rstrip("/")
    api_key = (payload.get("api_key") or "").strip()
    models = _normalize_custom_models(payload.get("models"))
    if not name or not base_url:
        return JSONResponse({"error": "name 和 base_url 必填"}, status_code=400)
    if not models:
        return JSONResponse({"error": "models 必填（至少一个模型名）"}, status_code=400)
    if not base_url.startswith(("http://", "https://")):
        return JSONResponse({"error": "base_url 需以 http(s):// 开头"}, status_code=400)
    pid = "custom-" + _sanitize_dir_name(name)
    if pid in _PROVIDERS_INDEX and pid not in _custom_providers:
        return JSONResponse({"error": f"provider id 冲突: {pid}"}, status_code=409)
    _custom_providers[pid] = {"id": pid, "name": name, "api": base_url, "models": models}
    _PROVIDERS_INDEX[pid] = _custom_providers[pid]
    _save_custom_providers()
    if api_key:
        _provider_keys[pid] = {"api_key": api_key, "base_url": base_url}
        _save_provider_keys()
    try:
        _sync_custom_providers_to_hermes(pid)
    except Exception:
        pass
    return {"ok": True, "provider_id": pid}


@app.put("/api/providers/custom/{pid}")
async def update_custom_provider(pid: str, payload: dict):
    """更新自定义 provider（base_url / 模型 / key）"""
    if pid not in _custom_providers:
        return JSONResponse({"error": f"自定义 provider '{pid}' 不存在"}, status_code=404)
    _def = _custom_providers[pid]
    if payload.get("name"):
        _def["name"] = str(payload["name"]).strip()
    if payload.get("base_url"):
        _b = str(payload["base_url"]).strip().rstrip("/")
        if _b.startswith(("http://", "https://")):
            _def["api"] = _b
    _models = _normalize_custom_models(payload.get("models"))
    if _models:
        _def["models"] = _models
    _PROVIDERS_INDEX[pid] = _def
    _save_custom_providers()
    _key = (payload.get("api_key") or "").strip()
    if _key and "…" not in _key and _key != "****":
        _provider_keys[pid] = {"api_key": _key, "base_url": _def["api"]}
        _save_provider_keys()
    try:
        _sync_custom_providers_to_hermes(pid)
    except Exception:
        pass
    return {"ok": True, "provider_id": pid}


@app.delete("/api/providers/custom/{pid}")
async def delete_custom_provider(pid: str):
    """删除自定义 provider（定义 + key + Hermes 同步）"""
    if pid not in _custom_providers:
        return JSONResponse({"error": f"自定义 provider '{pid}' 不存在"}, status_code=404)
    del _custom_providers[pid]
    _PROVIDERS_INDEX.pop(pid, None)
    _provider_keys.pop(pid, None)
    _save_custom_providers()
    _save_provider_keys()
    try:
        _sync_custom_providers_to_hermes(pid)
    except Exception:
        pass
    return {"ok": True}


@app.get("/api/models/available")
async def list_available_models(session_id: str = ""):
    """列出所有已配置 key 的 provider 的模型 — 用于交互框快速切换

    2026-08-08 修复：is_current 优先按会话级模型判定（带 session_id 且该会话
    做过会话级切换时），否则退回全局 _current_model。原来只认全局 → 用户会话
    实际用 kimi/GLM，设置页"已连接的模型"却把 ●当前 标在全局默认 Flash 上。
    """
    # 会话级当前模型（用于 is_current 判定）
    sess_cfg = None
    if session_id:
        s = _sessions.get(session_id)
        if s and s.get("model_config"):
            sess_cfg = s["model_config"]
    cur_cfg = sess_cfg or _current_model
    models = []
    for pid, saved in _provider_keys.items():
        if not saved.get("api_key") and not saved.get("local"):
            continue
        p = _PROVIDERS_INDEX.get(pid)
        if not p:
            continue
        is_current = (cur_cfg.get("api_key") == saved.get("api_key") and
                      cur_cfg.get("base_url") == p["api"])
        for m in p.get("models", []):
            models.append({
                "id": m["id"], "name": m["name"],
                "provider_id": pid, "provider_name": p["name"].split("(")[0].strip(),
                "base_url": p["api"], "api_key": saved["api_key"],
                "reasoning": m.get("reasoning", False),
                "tool_call": m.get("tool_call", False),
                "is_current": is_current and cur_cfg.get("model") == m["id"],
            })
    return {"models": models, "total": len(models)}


# --- 微信 iLink 连接 ---

_weixin_state = {
    "connected": False,
    "account_id": "",
    "token": "",
    "chat_id": "",
    "base_url": "https://ilinkai.weixin.qq.com",
    "qrcode_url": "",
    "qrcode_token": "",
    "qr_login_in_progress": False,
    "last_error": "",
    "context_token": "",
}

# 从磁盘恢复已保存的微信凭据
def _load_weixin_persist():
    try:
        persist_path = os.path.join(HERMES_HOME_DIR, "weixin_account.json")
        if os.path.exists(persist_path):
            with open(persist_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            _weixin_state["account_id"] = saved.get("account_id", "")
            _weixin_state["token"] = saved.get("token", "")
            _weixin_state["base_url"] = saved.get("base_url", _weixin_state["base_url"])
            _weixin_state["chat_id"] = saved.get("chat_id", _weixin_state.get("chat_id", ""))
            _weixin_state["context_token"] = saved.get("context_token", "")
            _weixin_state["connected"] = bool(_weixin_state["token"])
            return True
    except Exception as e:
        print(f"[MemOmics] 加载微信持久化状态失败: {e}", flush=True)
    return False

def _save_weixin_persist():
    try:
        os.makedirs(HERMES_HOME_DIR, exist_ok=True)
        persist_path = os.path.join(HERMES_HOME_DIR, "weixin_account.json")
        with open(persist_path, "w", encoding="utf-8") as f:
            json.dump({
                "account_id": _weixin_state["account_id"],
                "token": _weixin_state["token"],
                "chat_id": _weixin_state.get("chat_id", ""),
                "base_url": _weixin_state["base_url"],
                "context_token": _weixin_state.get("context_token", ""),
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[MemOmics] 保存微信持久化状态失败: {e}", flush=True)

_load_weixin_persist()


@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    """上传图片 — 支持粘贴/拖拽/文件选择的截图和图片"""
    import uuid, time
    # 限制文件类型
    ext = os.path.splitext(file.filename or "image.png")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"):
        return JSONResponse({"error": f"不支持的图片格式: {ext}"}, status_code=400)
    # 限制文件大小 (20MB)
    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        return JSONResponse({"error": "图片大小超过 20MB 限制"}, status_code=400)
    # 生成唯一文件名
    ts = int(time.time() * 1000)
    uid = str(uuid.uuid4())[:8]
    fname = f"{ts}_{uid}{ext}"
    fpath = os.path.join(_uploads_dir, fname)
    # P2-4：写盘前过沙箱门（观察模式不拦；强制 fs.write 且越界/无授权 -> 403，一个字节都不落盘）
    _denied = _sandbox_precheck("fs.write", fpath, [_uploads_dir], "upload.image")
    if _denied:
        return JSONResponse({"error": "sandbox denied: %s" % _denied}, status_code=403)
    with open(fpath, "wb") as f:
        f.write(contents)
    url = f"/uploads/{fname}"
    return {"url": url, "name": fname, "size": len(contents)}

@app.get("/api/runtime")
async def runtime_status():
    """任务账本快照：活动任务 + 内存历史 + 持久历史（重启后遗留任务为 interrupted）"""
    return _task_supervisor.snapshot()


@app.get("/api/resources")
async def resource_status():
    """资源准入快照：容量 / 已用 / 可用 / 活动租约 / 排队"""
    return _resource_scheduler.snapshot()


# ---------------------------------------------------------------------------
# 后台任务查看（T2/4，2026-09-24）：读的是任务自己写的契约，服务端只读不猜
# 契约文件：hermes_home/runtime/tasks/<task_id>.json（memomics/bio_tools/task_run.py 原子写）
# ---------------------------------------------------------------------------

def _task_run():
    """task_run 模块（导入失败也不能让面板 500）。"""
    try:
        from memomics.bio_tools import task_run
        return task_run
    except Exception as e:      # pragma: no cover - 正常安装不会走到
        logger.warning("task_run import failed: %s", e)
        return None


def _task_eta():
    """阶段历史推 ETA 模块（导入失败就退回"不给数"，面板照常能用）。"""
    try:
        from memomics.bio_tools import task_eta
        return task_eta
    except Exception as e:      # pragma: no cover - 正常安装不会走到
        logger.warning("task_eta import failed: %s", e)
        return None


def _task_history(items) -> dict:
    """把「已跑完任务的阶段耗时」汇成历史，供 ETA 使用（一次汇总，全列表共用）。"""
    mod = _task_eta()
    if mod is None:
        return {}
    try:
        return mod.collect_history(items or [])
    except Exception as e:      # pragma: no cover - 纯计算，出错就退化成不给数
        logger.warning("task_eta collect failed: %s", e)
        return {}


def _live_states() -> tuple:
    """task_run 认为"还活着"的状态集合（拿不到就退回保守默认）。"""
    tr = _task_run()
    return tuple(getattr(tr, "LIVE_STATES", None) or ("queued", "running", "cancelling", "paused"))


def _retry_root(d: dict) -> str:
    """重试链的根 —— A 失败重试出 B、B 再失败重试出 C，三者的根始终是 A 的 task_id。"""
    params = d.get("params") or {}
    return str(params.get("重试根") or params.get("重试来源") or d.get("task_id") or "")


def _retry_index(items, pending=None) -> dict:
    """{根 id: {"used": 已重试次数, "live": 还在跑（或已排定）的那次重试 id}}。

    一次汇总全列表共用（和 ETA 的历史汇总同一个套路）：列表里每张卡片都要知道
    "这个任务还能不能再重试"，不能每张卡片各扫一遍目录。
    `pending` 是"已经排定、还没落地的重试根"——退避要等几秒，那几秒里契约还不存在，
    不把它算进去的话连点两下就会排出两个一模一样的一次重试。
    """
    live_states = _live_states()
    index = {}
    for d in items or []:
        root = _retry_root(d)
        if not root or root == str(d.get("task_id") or ""):
            continue            # 只统计"重试出来的任务"，根本身不算一次重试
        slot = index.setdefault(root, {"used": 0, "live": ""})
        try:
            nth = int((d.get("params") or {}).get("第几次重试") or 0)
        except Exception:
            nth = 0
        slot["used"] = max(slot["used"], nth)
        if (d.get("status") or "") in live_states and not slot["live"]:
            slot["live"] = str(d.get("task_id") or "")
    for root in (pending or ()):
        slot = index.setdefault(str(root), {"used": 0, "live": ""})
        if not slot["live"]:
            slot["live"] = "已排定（等退避）"
    return index


# 失败到"可以重试"的终态：failed（真失败）/ interrupted（进程没了或服务重启留下的残局）。
# cancelled 是用户自己按停的，面板不给重试按钮 —— 想重跑直接说一声就行。
_RETRY_STATES = ("failed", "interrupted")
try:
    from webui.runtime.retry_backoff import RetryBackoff
except ImportError:      # pragma: no cover - 兼容把 webui/ 当根目录的启动方式
    from runtime.retry_backoff import RetryBackoff

_retry_backoff = RetryBackoff()     # 2s / 5s / 15s / 45s，连续 3 次后不再硬重试
# 已经排定退避、还没拉起来的那次重试：重试根 -> 排定时间。见 _retry_index 的 pending。
_RETRY_INFLIGHT = {}


def _retry_plan(d: dict, index: dict = None) -> dict:
    """能不能重试、算第几次、隔多久 —— 退避策略全部由 RetryBackoff 说了算，不另发明一套。

    返回字段：allowed / reason / root / used / attempt / delay_sec / max_retries。
    """
    task_id = str(d.get("task_id") or "")
    status = str(d.get("status") or "")
    root = _retry_root(d) or task_id
    slot = (index if index is not None else {}).get(root) or {}
    used = int(slot.get("used") or 0)
    attempt = used + 1
    plan = {"root": root, "used": used, "attempt": attempt,
            "delay_sec": _retry_backoff.next_delay(attempt),
            "max_retries": _retry_backoff.max_failures,
            "allowed": True, "reason": ""}
    # T15：退出码 0 但还有阶段没跑到的任务，也算"该重跑"—— 它没干完活。
    left = [stg.get("name") for stg in (d.get("stages") or []) if stg.get("status") == "pending"]
    unwound = bool(d.get("incomplete")) or bool(status == "done" and left)
    if unwound and status == "done":
        plan["note"] = ("任务退出码 0，但还有 %d 段没跑到（%s），可以重跑"
                        % (len(left), "、".join([str(x) for x in left[:3]]) or "见阶段时间线"))
    if status not in _RETRY_STATES and not unwound:
        plan.update(allowed=False, reason="任务没失败（%s），不用重试" % (status or "未知"))
    elif not (d.get("cmd") or ""):
        plan.update(allowed=False, reason="这份契约没记下实际命令，重跑会变成瞎猜")
    elif slot.get("live"):
        plan.update(allowed=False, reason="上一次重试还在跑（%s），等它结束" % slot["live"])
    elif _retry_backoff.exhausted(used):
        plan.update(allowed=False, reason="已经连着重试 %d 次（上限 %d 次），先看日志再动手"
                    % (used, _retry_backoff.max_failures))
    return plan


def _split_cmd(cmd):
    """把契约里的命令还原成参数列表。

    契约里 cmd 是**给人看的字符串**（为了面板显示拼过），重跑要拆回 token。
    只认双引号包裹（Windows 上 "C:\\Program Files\\..." 这种），不解释 shell 语法 ——
    管道/重定向/变量展开一律当普通字符，宁可跑出来报错，也不偷偷换个意思执行。
    """
    if isinstance(cmd, (list, tuple)):
        return [str(x) for x in cmd if str(x)]
    text = str(cmd or "").strip()
    if not text:
        return []
    try:
        import shlex
        parts = shlex.split(text, posix=False)
    except Exception:
        parts = text.split()
    out = []
    for p in parts:
        p = str(p)
        if len(p) >= 2 and p[0] == '"' and p[-1] == '"':
            p = p[1:-1]
        if p:
            out.append(p)
    return out


def _spawn_retry(d: dict, plan: dict) -> tuple:
    """真起一个 wrapper 重跑原命令；返回 (结果字典, 错误串)，二者必有一个为空。

    只搬契约里已有的东西（cmd/type/title/stages/script/params/session），
    外加三个溯源参数：重试来源 / 重试根 / 第几次重试 —— 面板据此画重试链。
    """
    import subprocess as _sp
    tr = _task_run()
    if tr is None:
        return None, "task_run 模块不可用"
    argv_cmd = _split_cmd(d.get("cmd"))
    if not argv_cmd:
        return None, "没有可重跑的命令"
    wrapper = getattr(tr, "__file__", "") or os.path.join(MEMOMICS_DIR, "memomics", "bio_tools", "task_run.py")
    python = sys.executable or "python"
    title = str(d.get("title") or d.get("task_id") or "任务")
    argv = [python, wrapper, "--type", str(d.get("type") or "other"),
            "--title", "%s（重试 %d/%d）" % (title, plan["attempt"], plan["max_retries"])]
    stages = [str(stg.get("name") or "") for stg in (d.get("stages") or []) if stg.get("name")]
    if stages:
        argv += ["--stages", ",".join(stages)]
    if d.get("script"):
        argv += ["--script", str(d["script"])]
    if d.get("session_dir"):
        argv += ["--session-dir", str(d["session_dir"])]
    if d.get("session_id"):
        argv += ["--session-id", str(d["session_id"])]
    if d.get("demo"):
        argv += ["--demo"]
    for k, v in (d.get("params") or {}).items():
        argv += ["--param", "%s=%s" % (k, v)]
    # 溯源参数放最后：dict 里同名键会被它们覆盖，重试的重试也只会指向直接上一级。
    argv += ["--param", "重试来源=%s" % str(d.get("task_id") or ""),
             "--param", "重试根=%s" % plan["root"],
             "--param", "第几次重试=%d" % plan["attempt"]]
    argv += ["--"] + argv_cmd
    env = dict(os.environ)
    # wrapper 按 env 找任务目录：必须显式钉到服务端正在读的那个 HERMES_HOME，
    # 否则测试/多实例下会写去另一个目录，面板永远看不到这次重试。
    env["MEMOMICS_TASKS_DIR"] = _tasks_dir()
    env["MEMOMICS_RUNTIME_DIR"] = os.path.dirname(_tasks_dir())
    cwd = str(d.get("cwd") or "")
    if not (cwd and os.path.isdir(cwd)):
        cwd = str(d.get("session_dir") or "")
    if not (cwd and os.path.isdir(cwd)):
        cwd = MEMOMICS_DIR
    log_dir = os.path.join(HERMES_HOME_DIR, "runtime", "logs")
    result = {"argv": argv, "cwd": cwd, "pid": None, "log": ""}
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        log_dir = ""
    flags = getattr(_sp, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    log_path = os.path.join(log_dir, "retry-%s.log" % time.strftime("%Y%m%d-%H%M%S")) if log_dir else ""
    try:
        if log_path:
            with open(log_path, "a", encoding="utf-8") as fh:
                proc = _sp.Popen(argv, cwd=cwd, env=env, stdout=fh, stderr=fh,
                                 stdin=_sp.DEVNULL, creationflags=flags)
        else:
            proc = _sp.Popen(argv, cwd=cwd, env=env, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
                             stdin=_sp.DEVNULL, creationflags=flags)
    except Exception as e:
        return None, "拉起重试进程失败：%s" % e
    result["pid"] = proc.pid
    result["log"] = log_path
    return result, ""


async def _retry_later(d: dict, plan: dict, delay: float) -> None:
    """退避等待后再拉起重试（等待期间服务端该干嘛干嘛，不阻塞请求）。"""
    try:
        await asyncio.sleep(max(0.0, float(delay or 0)))
    except asyncio.CancelledError:      # pragma: no cover - 进程退出时取消
        _RETRY_INFLIGHT.pop(str(plan.get("root") or ""), None)
        return
    # T16：这条任务可能已经被删了（人工清理 / 到点自动过期）—— 删了就别再把它复活。
    tid = os.path.basename(str(d.get("task_id") or ""))
    if tid and not os.path.isfile(os.path.join(_tasks_dir(), tid + ".json")):
        _RETRY_INFLIGHT.pop(str(plan.get("root") or ""), None)
        return
    try:
        _spawn_retry(d, plan)
    except Exception as e:              # pragma: no cover - 兜底，别让后台任务炸日志
        logger.warning("retry spawn failed: %s", e)
    finally:
        # 拉起来（或失败）之后就把名额放开：契约已经落地，_retry_index 看得到它了。
        _RETRY_INFLIGHT.pop(str(plan.get("root") or ""), None)


def _tasks_dir() -> str:
    """每次现算：HERMES_HOME_DIR 可被测试/多实例改写，不能固化成模块常量。"""
    return os.path.join(HERMES_HOME_DIR, "runtime", "tasks")


def _task_api_token() -> str:
    """后台任务写 API 的轻量鉴权 token（同源本地 token，沿用记忆写 API 那套机制）。"""
    return _memory_api_token()


# ---------------------------------------------------------------------------
# T16(2026-09-24)：任务清理 —— 人工删一条 / 批量清已结束 / 到点自动过期。
# 三条硬规矩：
#   ① 活着的一律不删（queued/running/paused/cancelling）—— 要删先取消；
#   ② 只删契约 .json 和它自己的 <task_id>.log；产出文件（results/ 里的数据）一律不动；
#   ③ 过期时间可调：MEMOMICS_TASK_TTL_HOURS（小时，默认 12；设 0 = 关掉自动清理）。
# 人工批量清理**不看 TTL**（用户点了就清已结束的）；TTL 只管"到点没人管自动清"。
# ---------------------------------------------------------------------------
_TASK_TTL_ENV = "MEMOMICS_TASK_TTL_HOURS"
_TASK_TTL_HOURS_DEFAULT = 12.0
_TASK_SWEEP_MIN_GAP = 60.0
_TASK_SWEEP_AT = [0.0]


def _task_ttl_hours(override=None) -> float:
    """保留多少小时（0 = 不自动清）。override > 环境变量 > 默认 12h。"""
    raw = override
    if raw is None or raw == "":
        raw = os.environ.get(_TASK_TTL_ENV, "")
    if raw is None or raw == "":
        return _TASK_TTL_HOURS_DEFAULT
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return _TASK_TTL_HOURS_DEFAULT


def _task_live_states(tr) -> tuple:
    return tuple(getattr(tr, "LIVE_STATES", ("queued", "running", "paused", "cancelling")))


def _task_terminal_states(tr) -> tuple:
    return tuple(getattr(tr, "TERMINAL_STATES", ("done", "failed", "cancelled", "interrupted")))


def _task_ended_ts(d: dict, path: str = "") -> float:
    """任务什么时候结束的（epoch 秒）：finished_at → started_at+耗时 → 契约文件 mtime。

    时间戳解析不了就退回 mtime —— 过期判定宁可晚一点，也不能因为格式怪就误删。
    """
    from datetime import datetime as _dt, timezone as _tz

    def _parse(text):
        try:
            got = _dt.fromisoformat(str(text).strip())
        except (TypeError, ValueError):
            return None
        if got.tzinfo is None:
            got = got.replace(tzinfo=_tz.utc)
        return got.timestamp()

    fin = _parse(d.get("finished_at"))
    if fin:
        return float(fin)
    started = _parse(d.get("started_at"))
    if started:
        try:
            return float(started) + float(d.get("duration_sec") or 0.0)
        except (TypeError, ValueError):
            return float(started)
    try:
        return os.path.getmtime(path) if path and os.path.isfile(path) else 0.0
    except OSError:
        return 0.0


def _task_log_candidates(tr, d: dict) -> list:
    """这条任务的日志可能在哪几个地方 —— 只认"正好叫 <task_id>.log"的文件名。

    契约里记的 log 最准；但老契约/单元夹具可能没记（或记的是别处），所以再按
    task_run 的默认规则补几个候选：会话目录/log/、任务目录/、任务目录兄弟 logs/。
    文件名不等于是这条任务的日志的一律不要 —— 契约被改坏也删不到别人的文件。
    """
    tid = os.path.basename(str(d.get("task_id") or ""))
    if not tid:
        return []
    want = tid + ".log"
    cands = [str(d.get("log") or "")]
    sess = str(d.get("session_dir") or "")
    if sess:
        try:
            cands.append(tr._default_log_path(sess, tid))
        except Exception:
            cands.append(os.path.join(sess, "log", want))
    cands.append(os.path.join(_tasks_dir(), want))
    cands.append(os.path.join(os.path.dirname(_tasks_dir()), "logs", want))
    out = []
    for p in cands:
        if p and os.path.basename(p) == want and p not in out:
            out.append(p)
    return out


def _task_delete_files(tr, d: dict) -> list:
    """删一条任务的记录：契约 .json + 它自己的日志（产出文件一律不动）。"""
    tid = os.path.basename(str(d.get("task_id") or ""))
    if not tid:
        return []
    targets = [os.path.join(_tasks_dir(), tid + ".json")] + _task_log_candidates(tr, d)
    gone = []
    for p in targets:
        try:
            if os.path.isfile(p):
                os.remove(p)
                gone.append(p)
        except OSError as e:      # pragma: no cover - 文件被占用/权限不够就记一笔
            logger.warning("任务清理：删不掉 %s（%s）", p, e)
    _RETRY_INFLIGHT.pop(tid, None)      # 排定但还没启动的重试不再复活（_retry_later 还会再核一次）
    return gone


def _task_delete_one(tr, task_id: str) -> dict:
    """删一条已结束的任务。在跑/排队的一律拒绝（409），让用户先取消 —— 不偷偷杀进程。"""
    t = tr.load_task(task_id)
    if t is None:
        return {"task_id": task_id, "ok": False, "code": 404, "reason": "任务不存在：%s" % task_id}
    d = tr.reconcile(t.data) or t.data
    status = str(d.get("status") or "")
    if status in _task_live_states(tr):
        return {"task_id": task_id, "ok": False, "code": 409, "status": status,
                "reason": "任务还在跑（%s），先取消再删" % status}
    gone = _task_delete_files(tr, d)
    return {"task_id": task_id, "ok": True, "status": status, "removed": gone,
            "title": d.get("title") or "", "incomplete": bool(d.get("incomplete"))}


def _tasks_cleanup(states=None, session_id: str = "", ttl_hours=None, dry_run: bool = False) -> dict:
    """批量清理 —— 面板上的「🧹 清理已结束」和到点自动过期走的是同一段代码。

    ttl_hours=None：不看时间，把所有已结束的清掉（人工操作）；
    ttl_hours>0   ：只清结束超过这么久的老任务（自动过期）。
    """
    tr = _task_run()
    if tr is None:
        return {"ok": False, "error": "task_run 模块不可用", "deleted": [], "deleted_count": 0}
    _bind_task_run(tr)
    want = tuple(states or _task_terminal_states(tr))
    live = _task_live_states(tr)
    ttl = _task_ttl_hours(ttl_hours) if ttl_hours is not None else 0.0
    now = time.time()
    try:
        items = tr.list_tasks(session_id=session_id or "", limit=500, refresh=1)
    except Exception as e:
        return {"ok": False, "error": "读取任务失败：%s" % e, "deleted": [], "deleted_count": 0}
    deleted, kept, notdue = [], [], []
    for d in items:
        tid = str(d.get("task_id") or "")
        status = str(d.get("status") or "")
        if not tid or status not in want:
            continue
        if status in live:                      # 双保险：过滤器写错也删不到活任务
            kept.append({"task_id": tid, "reason": "还在跑（%s）" % status})
            continue
        if ttl > 0:
            ended = _task_ended_ts(d, os.path.join(_tasks_dir(), tid + ".json"))
            age = (now - ended) if ended else 0.0
            if ended and age < ttl * 3600.0:
                notdue.append({"task_id": tid, "left_sec": round(ttl * 3600.0 - age, 1)})
                continue
        entry = {"task_id": tid, "title": d.get("title") or "", "status": status}
        if dry_run:
            deleted.append(entry)
            continue
        one = _task_delete_one(tr, tid)
        if one.get("ok"):
            entry["removed"] = one.get("removed")
            deleted.append(entry)
        else:
            kept.append({"task_id": tid, "reason": one.get("reason") or "删不掉"})
    return {"ok": True, "deleted": deleted, "deleted_count": len(deleted),
            "kept": kept[:50], "kept_count": len(kept),
            "notdue": notdue[:50], "notdue_count": len(notdue),
            "ttl_hours": ttl, "dry_run": bool(dry_run),
            "states": list(want), "session_id": session_id or ""}


def _task_auto_sweep() -> dict:
    """到点自动过期（列表接口顺带跑，60s 最多一次）。返回给面板看的策略说明。"""
    ttl = _task_ttl_hours()
    info = {"ttl_hours": ttl, "auto": ttl > 0, "swept": None, "env": _TASK_TTL_ENV}
    if ttl <= 0:
        return info
    now = time.time()
    if now - _TASK_SWEEP_AT[0] < _TASK_SWEEP_MIN_GAP:
        return info
    _TASK_SWEEP_AT[0] = now
    try:
        res = _tasks_cleanup(ttl_hours=ttl)
        info["swept"] = int(res.get("deleted_count") or 0)
    except Exception as e:      # pragma: no cover - 清理失败绝不能拖垮列表
        logger.warning("任务自动过期失败：%s", e)
        info["error"] = str(e)
    return info


def _bind_task_run(tr):
    """让 task_run 指向当前 hermes_home（面板与 wrapper 必须看同一个目录）。"""
    tr.TASKS_DIR = _tasks_dir()
    tr.FALLBACK_LOG_DIR = os.path.join(HERMES_HOME_DIR, "runtime", "logs")
    return tr


def _env_line(env: dict) -> str:
    """环境一句话（面板列表用）：R 4.5.3 / Python 3.12.10 / conda:xxx。"""
    env = env or {}
    if env.get("r"):
        r = env["r"]
        pk = (" + %s 包" % r.get("pkg_count")) if r.get("pkg_count") else ""
        return "R %s%s" % (r.get("version", "?"), pk)
    if env.get("conda"):
        return "conda %s" % env["conda"]
    if env.get("python_version"):
        return "Python %s" % env["python_version"]
    return env.get("kind", "未知环境")


# T13(2026-09-24)：任务要标清楚"属于哪个会话"——只给一串 memomics-xxxx 等于没标。
# 会话名走 state.db（索引查询，很便宜），30 秒缓存一次：一次列表 100 条任务不该查 100 次库。
_SESSION_TITLE_MEMO = {}


def _session_title(sid: str) -> str:
    """会话显示名：标题优先，没标题就退回最近一句用户话，都没有就空（面板显示 id）。"""
    sid = (sid or "").strip()
    if not sid:
        return ""
    now = time.time()
    hit = _SESSION_TITLE_MEMO.get(sid)
    if hit and now - hit[0] < 30:
        return hit[1]
    title = ""
    try:
        db = _get_session_db()
        if db is not None:
            if hasattr(db, "get_session_title"):
                title = str(db.get_session_title(sid) or "").strip()
            if (not title or title in ("新会话", "New Chat")) and hasattr(db, "get_session"):
                sess = db.get_session(sid) or {}
                title = _queue_label(sess) or title
    except Exception:  # pragma: no cover - 库里查不到就当没名字，不能拖垮列表
        title = ""
    title = " ".join(str(title).split())[:60]
    _SESSION_TITLE_MEMO[sid] = (now, title)
    return title


def _task_card(d: dict, history: dict = None, retries: dict = None) -> dict:
    """列表项：只留面板要显示的字段（契约文件本身可能很大）。

    history（可选）：阶段耗时历史 —— 给了就算「还要多久」（T10），
    没历史 / 任务已结束 / 信息不足时 eta_sec 为 None，面板就不显示这一行。
    retries（可选）：重试链索引（T12）—— 给了就算「还能不能再重试 / 第几次」，
    面板据此决定重试按钮是亮的还是灰的（后端算，面板不自己猜）。
    """
    from datetime import datetime as _dt, timezone as _tz
    proc = d.get("proc") or {}
    prog = d.get("progress") or {}
    val = prog.get("value")
    started = d.get("started_at") or ""
    elapsed = None
    if d.get("status") in ("queued", "running", "cancelling", "paused"):
        try:
            t0 = _dt.fromisoformat(started)
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=_tz.utc)
            elapsed = round((_dt.now(_tz.utc) - t0).total_seconds(), 1)
        except Exception:
            elapsed = None
    else:
        elapsed = d.get("duration_sec")
    eta = {}
    mod = _task_eta()
    if mod is not None:
        try:
            eta = mod.estimate(d, history or {})
        except Exception as e:  # pragma: no cover - 估算失败不该拖垮列表
            logger.warning("task_eta estimate failed: %s", e)
            eta = {}
    try:
        rp = _retry_plan(d, retries or {})
    except Exception as e:      # pragma: no cover - 纯计算，算不出来就不给按钮
        logger.warning("retry plan failed: %s", e)
        rp = {"allowed": False, "reason": "", "root": "", "used": 0, "attempt": 1,
              "delay_sec": 0.0, "max_retries": 0}
    return {
        "retry_allowed": bool(rp.get("allowed")),
        # T15：允许重试但理由值得说的时候给一句（例如"退出码 0 但还有 3 段没跑到"）
        "retry_note": rp.get("note") or "",
        "retry_reason": rp.get("reason") or "",
        "retry_root": rp.get("root") or "",
        "retry_used": rp.get("used") or 0,
        "retry_attempt": rp.get("attempt") or 0,
        "retry_delay_sec": rp.get("delay_sec") or 0,
        "retry_max": rp.get("max_retries") or 0,
        "eta_sec": eta.get("sec"),
        "eta_text": eta.get("text") or "",
        "eta_basis": eta.get("basis") or "",
        "eta_source": eta.get("source") or "",
        "eta_confidence": eta.get("confidence") or "",
        "task_id": d.get("task_id"),
        "title": d.get("title") or "未命名任务",
        "type": d.get("type") or "other",
        "status": d.get("status") or "unknown",
        "session_id": d.get("session_id") or "",
        "session_title": _session_title(d.get("session_id") or ""),
        "session_dir": d.get("session_dir") or "",
        "demo": bool(d.get("demo")),
        "source": d.get("source") or "",
        "progress_pct": (round(100.0 * val) if isinstance(val, (int, float)) else None),
        "progress_text": prog.get("text") or "",
        "stage_index": d.get("stage_index") or 0,
        "stage_total": d.get("stage_total") or len(d.get("stages") or []),
        # T15：阶段没跑完就不许说「完成」。老契约没这两个字段，这里按 stages 现场算；
        # 于是面板不用改判断逻辑，incomplete 就是"退出码 0 但还有阶段是 pending"。
        "stage_pending": len(d.get("stage_unfinished") or [
            stg.get("name") for stg in (d.get("stages") or []) if stg.get("status") == "pending"]),
        "stage_unfinished": (d.get("stage_unfinished") or [
            stg.get("name") for stg in (d.get("stages") or []) if stg.get("status") == "pending"])[:8],
        "incomplete": bool(d.get("incomplete")) or bool(
            d.get("status") in ("done", "cancelled")
            and [stg for stg in (d.get("stages") or []) if stg.get("status") == "pending"]),
        # 当前阶段名。面板一直读的是 stage，而契约里只有 stages[]/stage_index，
        # 于是列表永远显示「阶段 1/4：」（冒号后面空着）—— 真机实测发现，补上。
        "stage": next((stg.get("name") or "" for stg in (d.get("stages") or [])
                       if stg.get("status") == "running"), ""),
        # 循环变量别叫 s/sess/state：那是会话状态漂移门禁的扫描口径（test_p2_2_thread_state.py），
        # 阶段字典会被误判成会话键，门禁直接红。
        "stages": [{"name": stg.get("name"), "status": stg.get("status"), "sec": stg.get("sec")}
                   for stg in (d.get("stages") or [])],
        "pid": proc.get("pid") or d.get("pid"),
        "pname": proc.get("pname") or "",
        "cpu_pct": proc.get("cpu_pct"),
        "rss_gb": proc.get("rss_gb"),
        "alive": bool(d.get("alive")),
        "stalled": bool(d.get("stalled")),
        "heartbeat_age_sec": d.get("heartbeat_age_sec"),
        "started_at": started,
        "updated_at": d.get("updated_at") or "",
        "elapsed_sec": elapsed,
        "duration_sec": d.get("duration_sec"),
        "exit_code": d.get("exit_code"),
        "error": (d.get("error") or "")[:300],
        "cmd": (d.get("cmd") or "")[:400],
        "script": d.get("script") or "",
        "params": d.get("params") or {},
        "output_count": len(d.get("outputs") or []),
        "summary": d.get("summary") or "",
        "log": d.get("log") or "",
        "env_line": _env_line(d.get("env") or {}),
        "env_kind": (d.get("env") or {}).get("kind", ""),
    }


def _confine_path(path: str, session_dir: str) -> str:
    """只允许读会话目录 / 仓库内的脚本（面板要能看脚本，但不能变成任意文件读取）。"""
    if not path:
        return ""
    p = path if os.path.isabs(path) else os.path.join(session_dir or MEMOMICS_DIR, path)
    p = os.path.abspath(p)
    for root in (session_dir or "", MEMOMICS_DIR):
        if root and (p == os.path.abspath(root)
                     or p.startswith(os.path.abspath(root) + os.sep)):
            return p
    return ""


def _resolve_output(raw: str, session_dir: str, cwd: str = "") -> str:
    """产物路径解析：绝对路径照用；相对路径依次在 会话目录 → 会话/results → 任务 cwd → 仓库 下找。

    2026-09-24 真机踩到：脚本按约定打 `#TASK:OUTPUT t5_qc_box.png`（相对路径），
    产物落在 <会话>/results/ 下，而旧代码只按会话目录拼一次，于是文件明明在、
    面板却显示"不存在"。产物真假是面板的核心承诺，不能糊。
    """
    if not raw:
        return ""
    cands = []
    if os.path.isabs(raw):
        cands.append(raw)
    else:
        for base in (session_dir or "", os.path.join(session_dir or "", "results"),
                     cwd or "", MEMOMICS_DIR):
            if base:
                cands.append(os.path.join(base, raw))
    for c in cands:
        try:
            if os.path.isfile(c):
                return os.path.abspath(c)
        except OSError:
            continue
    return os.path.abspath(cands[0]) if cands else ""


# === 后台任务面板的实时推送（WS）==========================================
# 面板进视图发 task_subscribe、切走发 task_unsubscribe；订阅期间服务端每 1.5s 比一次
# 「任务目录指纹」，变了才推整份列表 —— 客户端不用高频轮询，多开几个标签也只扫一份。
_TASK_WS_CLIENTS: set = set()
_TASK_WATCH_TASK = None
_TASK_WATCH_SIG = None


def _tasks_fingerprint():
    """契约目录指纹：条数 + 最新 mtime + 总字节（任务每次 flush 都会变）。"""
    root = _tasks_dir()
    try:
        names = os.listdir(root)
    except OSError:
        return (0, 0.0, 0)
    count, latest, total = 0, 0.0, 0
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            info = os.stat(os.path.join(root, name))
        except OSError:
            continue
        count += 1
        latest = max(latest, info.st_mtime)
        total += info.st_size
    return (count, round(latest, 3), total)


# 真机实测（2026-09-24）：debate_analysis 一跑就是 4-7 分钟（3 正 + 3 反 + 评委），
# 长 R 脚本十几分钟也正常 —— 统一按 180 秒判"卡住"会把正常干活的会话全标成告警。
# 按工具给一个"合理的沉默时长"，超过才提示可能卡住。
_TOOL_EXPECT_SEC = {"debate_analysis": 900, "execute_r": 1800, "execute_python": 1800,
                    "terminal": 1800, "cellbender": 3600}


def _live_session_cards(limit: int = 20) -> list:
    """正在跑的会话（只读快照）。

    现场：用户点开「后台任务」看到空的 —— 因为后台任务契约只记录显式用
    task_run 包装的活儿，而用户真正在等的是"哪个会话正在跑分析"。
    这里把活着的会话也列出来（不伪造状态，字段全部来自运行时）：
      在干什么（最近一次工具）、跑了多久、有没有卡住（工具 3 分钟没动静）、
      计划做到第几步（session["todos"]）、占了多少内存。
    """
    out = []
    try:
        sessions = list(_sessions.values())
    except Exception:
        return out
    now = time.time()
    for s in sessions:
        try:
            if not (s.get("running_agent") or s.get("running_task") or s.get("bg_running")
                    or s.get("_user_turn_active")):
                continue
            msgs = s.get("messages") or []
            if msgs:
                ask = (msgs[0].get("content") or msgs[0].get("text") or "")
            else:
                ask = s.get("_first_msg") or ""
            todos = [t for t in (s.get("todos") or []) if isinstance(t, dict)]
            doing = [t for t in todos if t.get("status") == "in_progress"]
            pending = [t for t in todos if t.get("status") == "pending"]
            live_tool = s.get("_live_tool") or ""
            tool_ts = s.get("_live_tool_ts") or 0
            proc = {}
            try:
                hist = s.get("_proc_hist") or []
                if hist and hist[-1][1]:
                    _pid, _cpu, _io, _rss = hist[-1][1][0]
                    proc = {"pid": _pid, "cpu_s": round(_cpu, 1), "rss_mb": round(_rss / 1048576.0, 0)}
            except Exception:
                proc = {}
            start = s.get("_turn_start_ts") or 0
            out.append({
                "sid": s.get("id") or "",
                "title": s.get("title") or "",
                "ask": (ask or "").replace("\n", " ")[:110],
                "msg_count": len(msgs) if s.get("_messages_loaded", True) else int(s.get("_msg_count") or 0),
                "last_active": s.get("last_active") or s.get("created") or "",
                "elapsed_sec": int(now - start) if start else None,
                "last_tool": live_tool,
                "tool_age_sec": int(now - tool_ts) if tool_ts else None,
                "tool_expect_sec": _TOOL_EXPECT_SEC.get(live_tool, 180),
                "stalled": bool(live_tool) and bool(tool_ts)
                           and (now - tool_ts) > _TOOL_EXPECT_SEC.get(live_tool, 180),
                "todos_total": len(todos),
                "todos_done": sum(1 for t in todos if t.get("status") == "completed"),
                "doing": (doing[0].get("title") or "")[:110] if doing else "",
                "next": (pending[0].get("title") or "")[:110] if pending else "",
                "bg_running": bool(s.get("bg_running")),
                "proc": proc or None,
            })
        except Exception:
            continue
    out.sort(key=lambda x: (x.get("last_active") or ""), reverse=True)
    return out[:limit]


# === 活会话详情（2026-09-24 用户反馈：点了后台任务看不到参数、主要环境） ===
# 面板原来点活会话只是"切过去看对话"，可用户要的是"这活到底拿什么参数、在什么环境下跑的"。
# 这里把运行时可查的事实全部摊开：最近的工具调用（含入参原文）、跑分析用的 R/Python 环境、
# 已经落盘的产物、辩论记录、日志路径；拿不到的一律留空，不编。
_LIVE_ARTIFACT_DIRS = ("results", "figures", "scripts", "conclusions")


def _live_artifacts(sid: str, limit: int = 40) -> list:
    """会话落盘产物（结果表/图/脚本/结论），按修改时间倒序。"""
    base = os.path.join(RESULTS_DIR, sid)
    out = []
    for sub in _LIVE_ARTIFACT_DIRS:
        d = os.path.join(base, sub)
        if not os.path.isdir(d):
            continue
        try:
            names = os.listdir(d)
        except Exception:
            continue
        for fn in names:
            p = os.path.join(d, fn)
            try:
                st = os.stat(p)
            except Exception:
                continue
            if not os.path.isfile(p):
                continue
            out.append({"rel": sub + "/" + fn, "size": st.st_size, "mtime": st.st_mtime})
    out.sort(key=lambda x: -(x.get("mtime") or 0))
    return out[:limit]


def _session_tool_trace(sid: str, limit: int = 12) -> list:
    """会话最近的工具调用（工具 + 入参 + 结果摘要）——"参数"最硬的一手证据。"""
    p = os.path.join(RESULTS_DIR, sid, "log", "system_log.jsonl")
    if not os.path.isfile(p):
        return []
    lines = []
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip():
                    lines.append(line)
    except Exception:
        return []
    out = []
    for line in lines[-max(1, limit):]:
        try:
            e = json.loads(line)
        except Exception:
            continue
        out.append({"ts": str(e.get("ts") or ""), "tool": str(e.get("tool") or ""),
                    "args": str(e.get("args") or "")[:900],
                    "result": str(e.get("result_preview") or "")[:400]})
    out.reverse()                     # 最新的排前面
    return out


def _session_stats(sid: str) -> dict:
    """"跑成什么样"的粗账：工具次数、用过哪些技能、审查/辩论几次。"""
    p = os.path.join(RESULTS_DIR, sid, "log", "system_log.jsonl")
    stats = {"tool_calls": 0, "tools": {}, "skills": [], "rail_pre": 0, "rail_post": 0,
             "debate_calls": 0, "files_written": 0}
    if not os.path.isfile(p):
        return stats
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                t = str(e.get("tool") or "")
                if not t:
                    continue
                stats["tool_calls"] += 1
                stats["tools"][t] = stats["tools"].get(t, 0) + 1
                args = str(e.get("args") or "")
                if t == "skill_view":
                    m = re.search(r"['\"]name['\"]\s*:\s*['\"]([^'\"]+)", args)
                    if m and m.group(1) not in stats["skills"]:
                        stats["skills"].append(m.group(1))
                elif t == "rail_review":
                    if "pre" in args:
                        stats["rail_pre"] += 1
                    if "post" in args:
                        stats["rail_post"] += 1
                elif t == "debate_analysis":
                    stats["debate_calls"] += 1
                elif t in ("write_file", "patch", "execute_r", "execute_python"):
                    if t in ("write_file", "patch"):
                        stats["files_written"] += 1
    except Exception:
        pass
    return stats


def _session_debates(sid: str, limit: int = 5) -> list:
    """本会话的辩论记录（题目/裁决/置信度/结论/下一步）——用户最想知道的"它到底怎么判的"。"""
    d = os.path.join(RESULTS_DIR, sid, "log")
    if not os.path.isdir(d):
        return []
    out = []
    try:
        names = sorted([n for n in os.listdir(d) if n.startswith("debate_") and n.endswith(".json")])
    except Exception:
        return []
    for fn in names[-limit:]:
        try:
            with open(os.path.join(d, fn), encoding="utf-8", errors="replace") as f:
                j = json.load(f)
        except Exception:
            continue
        na = j.get("next_actions")
        out.append({"file": fn,
                    "topic": str(j.get("topic") or "")[:300],
                    "verdict": str(j.get("verdict") or ""),
                    "confidence": str(j.get("confidence") or ""),
                    "decision": str(j.get("decision") or "")[:600],
                    "next_actions": len(na) if isinstance(na, list) else None,
                    "mtime": os.path.getmtime(os.path.join(d, fn))})
    out.reverse()
    return out


def _session_env_facts() -> dict:
    """跑分析用的主要环境：R/Python 可执行文件、库路径、GPU —— 用户问"主要环境"要的就是这些。"""
    facts = {"python": sys.executable or "", "cwd": os.getcwd(),
             "r_libs_user": os.environ.get("R_LIBS_USER") or ""}
    try:
        with open(os.path.join(MEMOMICS_DIR, "environment.json"), encoding="utf-8") as f:
            env = json.load(f)
        for ver, info in list(((env.get("paths") or {}).get("r") or {}).items())[:1]:
            facts["r_version"] = str(ver)
            facts["rscript"] = str((info or {}).get("bin") or "")
            facts["r_lib_user"] = str((info or {}).get("lib_user") or facts["r_libs_user"])
            facts["r_pkg_count"] = (info or {}).get("pkg_count")
            facts["r_key_pkgs"] = list((info or {}).get("key_pkgs") or [])[:8]
        py = ((env.get("paths") or {}).get("python") or {})
        if isinstance(py, dict) and py:
            k0 = list(py)[0]
            facts["python_declared"] = str((py.get(k0) or {}).get("bin") or k0) if isinstance(py.get(k0), dict) else str(py.get(k0))
        facts["platform"] = env.get("platform")
        facts["gpu"] = env.get("gpu")
        ki = env.get("known_issues")
        facts["known_issues"] = [str(x)[:200] for x in (ki or [])[:3]] if isinstance(ki, list) else []
        facts["env_updated"] = str(env.get("_last_updated") or "")
    except Exception as e:
        facts["env_error"] = str(e)
    facts["memomics_env"] = {k: v for k, v in os.environ.items() if k.startswith("MEMOMICS_")}
    return facts


def _live_session_detail(sid: str, tool_limit: int = 12) -> dict:
    """活会话详情：它是谁、在跑什么、拿什么参数、什么环境、出了什么产物、日志在哪。"""
    s = _sessions.get(sid)
    if s is None:
        try:
            _restore_single_session(sid)
        except Exception:
            pass
        s = _sessions.get(sid)
    cards = {}
    try:
        for c in _live_session_cards(limit=200):
            if c.get("sid") == sid:
                cards = c
                break
    except Exception:
        cards = {}
    ask = ""
    if s:
        msgs = s.get("messages") or []
        if msgs:
            ask = str(msgs[0].get("content") or msgs[0].get("text") or "")
        elif s.get("_first_msg"):
            ask = str(s.get("_first_msg") or "")
    if not ask:
        try:
            for m in _load_session_messages(sid, limit=6) or []:
                c0 = str(m.get("content") or m.get("text") or "")
                if (m.get("role") or "") == "user" and c0 and not c0.lstrip().startswith(_INJECT_PREFIXES):
                    ask = c0
                    break
        except Exception:
            pass
    task = None
    try:
        tr = _task_run()
        if tr is not None:
            _bind_task_run(tr)
            mine = tr.list_tasks(session_id=sid, limit=5, refresh=True)
            if mine:
                task = mine[0]
    except Exception:
        task = None
    detail = {
        "ok": True,
        "sid": sid,
        "title": (s or {}).get("title") or "",
        "ask": ask.strip(),
        "live": bool(cards),
        "is_running": bool(cards) or bool((s or {}).get("running_agent") or (s or {}).get("running_task")),
        "elapsed_sec": cards.get("elapsed_sec"),
        "last_active": (s or {}).get("last_active") or (s or {}).get("created") or "",
        "created": (s or {}).get("created") or "",
        "msg_count": cards.get("msg_count") if cards else (s or {}).get("_msg_count"),
        "current": cards or None,
        "todos": [t for t in ((s or {}).get("todos") or []) if isinstance(t, dict)][:20],
        "tools": _session_tool_trace(sid, limit=tool_limit),
        "stats": _session_stats(sid),
        "debates": _session_debates(sid),
        "artifacts": _live_artifacts(sid),
        "env": _session_env_facts(),
        "paths": {"session_dir": os.path.join(RESULTS_DIR, sid),
                  "system_log": os.path.join(RESULTS_DIR, sid, "log", "system_log.jsonl"),
                  "tasks_dir": _tasks_dir()},
        "task": task,
    }
    return detail


@app.get("/api/live_session/{sid}")
async def api_live_session(sid: str, tools: int = 12):
    """活会话详情（参数 / 环境 / 产物 / 日志）—— 后台任务面板点进去看的就是这个。"""
    try:
        return JSONResponse(_live_session_detail(sid, tool_limit=max(1, min(60, int(tools or 12)))))
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


def _tasks_payload(session_id: str = "", states: str = "", limit: int = 100,
                   refresh: int = 1) -> dict:
    """任务列表载荷 —— HTTP 路由与 WS 推送共用一份，免得两边漂移。"""
    tr = _task_run()
    if tr is None:
        return {"ok": False, "error": "task_run 模块不可用", "tasks": [], "counts": {}}
    _bind_task_run(tr)
    sweep = _task_auto_sweep()      # T16：到点自动过期（60s 最多一次），删完再列，免得刚删的又出现
    try:
        items = tr.list_tasks(session_id=session_id or "",
                              limit=max(1, min(500, int(limit or 100))), refresh=bool(refresh))
    except Exception as e:
        return {"ok": False, "error": "读取任务失败：%s" % e, "tasks": [], "counts": {}}
    # 历史要在「按状态过滤」之前汇总：过滤成只看 running 时，历史仍然得是全量的，
    # 否则面板一筛选，ETA 就集体变成"看不到"。
    history = _task_history(items)
    # 重试索引同样要在过滤前算：只看 failed 时，重试链上"还在跑的那次"也要算进去。
    retries = _retry_index(items, _RETRY_INFLIGHT)
    if states:
        want = {one.strip() for one in states.split(",") if one.strip()}
        items = [d for d in items if (d.get("status") or "") in want]
    counts = {}
    for d in items:
        st = d.get("status") or "unknown"
        counts[st] = counts.get(st, 0) + 1
    # 用户点开「后台任务」要看到的是"谁在跑" —— 契约任务之外，把活着的会话也带上。
    # 已经用自己的任务行显示过的会话不重复列（免得同一条会话出现两次）。
    busy_sids = {d.get("session_id") or "" for d in items
                 if (d.get("status") or "") in tuple(tr.LIVE_STATES)}
    live = [c for c in _live_session_cards() if c.get("sid") and c.get("sid") not in busy_sids]
    return {"ok": True, "tasks": [_task_card(d, history, retries) for d in items], "counts": counts,
            "live_sessions": live, "live_count": len(live),
            "active": counts.get("running", 0) + counts.get("cancelling", 0),
            "states": list(tr.LIVE_STATES), "types": list(tr.TASK_TYPES),
            "tasks_dir": _tasks_dir(), "api_token": _task_api_token(),
            "cleanup": sweep, "cleanup_states": list(_task_terminal_states(tr)),
            "sessions": sorted({d.get("session_id") or "" for d in items} - {""})}


async def _task_ws_broadcast(payload: dict) -> None:
    """把任务列表推给所有订阅者；推不动（连接没了）就地摘掉。"""
    dead = []
    text = json.dumps(payload, ensure_ascii=False)
    for sock in list(_TASK_WS_CLIENTS):
        try:
            await sock.send_text(text)
        except Exception:
            dead.append(sock)
    for sock in dead:
        _TASK_WS_CLIENTS.discard(sock)


async def _task_watch_loop() -> None:
    """订阅期间的后台扫描：指纹变了才推，没人订阅就自己退出。"""
    global _TASK_WATCH_SIG
    while _TASK_WS_CLIENTS:
        sig = _tasks_fingerprint()
        if sig != _TASK_WATCH_SIG:
            _TASK_WATCH_SIG = sig
            payload = _tasks_payload(limit=100, refresh=1)
            if payload.get("ok"):
                await _task_ws_broadcast(payload)
        await asyncio.sleep(1.5)
    _TASK_WATCH_SIG = None


def _ensure_task_watch() -> None:
    """有订阅者就把扫描任务拉起来（懒启动：没人看面板就不占 CPU）。"""
    global _TASK_WATCH_TASK
    if not _TASK_WS_CLIENTS:
        return
    if _TASK_WATCH_TASK is None or _TASK_WATCH_TASK.done():
        try:
            _TASK_WATCH_TASK = asyncio.get_running_loop().create_task(_task_watch_loop())
        except RuntimeError:
            _TASK_WATCH_TASK = None


@app.get("/api/tasks")
async def list_background_tasks(session_id: str = "", states: str = "", limit: int = 100,
                                refresh: int = 1):
    """后台任务列表（跨会话）。

    契约由任务自己写（wrapper / 脚本打点），服务端只读取 + 核对存活：
    refresh=1（默认）会用「PID + 进程创建时间」核对，进程没了的活任务收敛成 interrupted。
    """
    payload = _tasks_payload(session_id=session_id, states=states, limit=limit, refresh=refresh)
    if not payload.get("ok"):
        code = 503 if "不可用" in str(payload.get("error") or "") else 500
        return JSONResponse({"ok": False, "error": payload.get("error")}, status_code=code)
    return payload


@app.get("/api/tasks/{task_id}")
async def get_background_task(task_id: str, tail: int = 200, script: int = 1):
    """任务详情：契约全字段 + 日志尾部 + 产物（大小/是否存在）+ 脚本正文。"""
    tr = _task_run()
    if tr is None:
        return JSONResponse({"ok": False, "error": "task_run 模块不可用"}, status_code=503)
    _bind_task_run(tr)
    t = tr.load_task(task_id)
    if t is None:
        return JSONResponse({"ok": False, "error": "任务不存在：%s" % task_id}, status_code=404)
    d = tr.reconcile(t.data)
    try:
        _all = tr.list_tasks(limit=500, refresh=0)
    except Exception:  # pragma: no cover - 拿不到全量列表就退化成"只有自己"
        _all = [d]
    try:
        history = _task_history(_all)
    except Exception:  # pragma: no cover - 历史拿不到就不给 ETA
        history = {}
    card = _task_card(d, history, _retry_index(_all, _RETRY_INFLIGHT))
    card["params"] = d.get("params") or {}
    card["outputs"] = []
    for p in (d.get("outputs") or [])[:100]:
        full = _resolve_output(p, d.get("session_dir") or "", d.get("cwd") or "")
        try:
            exists = os.path.isfile(full)
            size = os.path.getsize(full) if exists else None
        except OSError:
            exists, size = False, None
        card["outputs"].append({"path": p, "exists": exists, "size": size, "abs": full})
    log_path = d.get("log") or ""
    card["log_tail"] = tr.tail_log(log_path, max(1, min(4000, int(tail))))
    try:
        card["log_size"] = os.path.getsize(log_path) if os.path.isfile(log_path) else 0
    except OSError:
        card["log_size"] = 0
    card["wrapper_pid"] = (d.get("wrapper") or {}).get("pid")
    # 详情抽屉要能显示"这活儿到底占多少 CPU/内存、什么时候起的" —— 列表卡片给了
    # 扁平字段，详情补齐原始 proc/wrapper 与取消意图（真机实测发现详情里读不到 proc）。
    card["proc"] = d.get("proc") or {}
    card["wrapper"] = d.get("wrapper") or {}
    card["cancel_requested"] = bool(d.get("cancel_requested"))
    card["cancel_by"] = d.get("cancel_by") or ""
    card["env"] = d.get("env") or {}
    src = _confine_path(d.get("script") or "", d.get("session_dir") or "")
    card["script_path"] = src
    card["script_text"] = ""
    # 面板要能看脚本 —— 但只读会话目录/仓库内的（防任意文件读取）。够不着就说清楚，
    # 不能让用户以为"这个任务压根没脚本"。
    card["script_note"] = ""
    if not src and (d.get("script") or ""):
        card["script_note"] = "脚本在会话目录/仓库之外，面板不读（安全策略）：%s" % d.get("script")
    if src and script and os.path.isfile(src):
        try:
            if os.path.getsize(src) <= 256 * 1024:
                with open(src, "r", encoding="utf-8", errors="replace") as f:
                    card["script_text"] = f.read()
            else:
                card["script_truncated"] = True
        except OSError:
            pass
    return {"ok": True, "task": card}


@app.get("/api/tasks/{task_id}/log")
async def get_background_task_log(task_id: str, tail: int = 200, grep: str = ""):
    """日志尾部（seek 读，不整读几百 MB 的 CellBender 日志）。grep 为不区分大小写的子串过滤。"""
    tr = _task_run()
    if tr is None:
        return JSONResponse({"ok": False, "error": "task_run 模块不可用"}, status_code=503)
    _bind_task_run(tr)
    t = tr.load_task(task_id)
    if t is None:
        return JSONResponse({"ok": False, "error": "任务不存在：%s" % task_id}, status_code=404)
    log_path = (t.data.get("log") or "")
    text = tr.tail_log(log_path, max(1, min(5000, int(tail))))
    if grep and text:
        needle = grep.lower()
        text = os.linesep.join([ln for ln in text.splitlines() if needle in ln.lower()])
    try:
        size = os.path.getsize(log_path) if os.path.isfile(log_path) else 0
    except OSError:
        size = 0
    return {"ok": True, "task_id": t.data.get("task_id"), "log": log_path,
            "exists": bool(log_path and os.path.isfile(log_path)), "size": size,
            "text": text}


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_background_task(task_id: str, payload: dict = None, request: Request = None):
    """取消任务：需要 X-Task-Token；先写取消意图，再按「pid + 创建时间」核对身份杀子树。

    三步，任何一步都不猜：
      1. 只写 cancel_requested（wrapper 退出路径读到 → 状态落成 cancelled，而不是 failed）
      2. 杀进程前核对 create_time，PID 被复用（不是原进程）就绝不杀
      3. 宽限 15s 让 wrapper 自己收尾；还没收尾就按 wrapper 身份升级强杀，并由服务端落终态
    """
    tr = _task_run()
    if tr is None:
        return JSONResponse({"ok": False, "error": "task_run 模块不可用"}, status_code=503)
    _bind_task_run(tr)
    payload = payload or {}
    token = (request.headers.get("x-task-token", "") if request else "") or str(payload.get("token", ""))
    if token != _task_api_token():
        return JSONResponse({"ok": False, "error": "Unauthorized: missing/invalid task API token"},
                            status_code=401)
    t = tr.load_task(task_id)
    if t is None:
        return JSONResponse({"ok": False, "error": "任务不存在：%s" % task_id}, status_code=404)
    if (t.data.get("status") or "") not in tr.LIVE_STATES:
        return JSONResponse({"ok": False, "error": "任务已结束（%s），无需取消" % t.data.get("status")},
                            status_code=409)
    denied = _sandbox_precheck("proc.exec", t.path, [HERMES_HOME_DIR], "tasks.cancel")
    if denied:
        return JSONResponse({"ok": False, "error": "sandbox denied: %s" % denied}, status_code=403)

    marks = tr.request_cancel(task_id, by="api")
    kill_proc = tr.kill_registered_process(t.data, key="proc")
    escalated = False
    waited = 0.0
    for _ in range(30):                     # 最多 15s 等 wrapper 自己收尾
        await asyncio.sleep(0.5)
        waited += 0.5
        cur = tr.load_task(task_id)
        if cur is None or (cur.data.get("status") or "") not in tr.LIVE_STATES:
            break
        # 管任务的进程（wrapper）自己都没了 —— 没人会来收尾，服务端立刻落终态，别干等 15s
        _w = (cur.data.get("wrapper") or {})
        if _w.get("pid"):
            if not tr.proc_alive(_w.get("pid"), _w.get("create_time")):
                break
        elif kill_proc.get("killed"):
            break
    cur = tr.load_task(task_id)
    if cur is not None and (cur.data.get("status") or "") in tr.LIVE_STATES:
        escalated = True
        kill_wrap = tr.kill_registered_process(cur.data, key="wrapper")
        cur.finish("cancelled", error="用户取消（服务端兜底收尾）")
    else:
        kill_wrap = {}
    cur = tr.load_task(task_id)
    return {"ok": True, "task_id": task_id, "status": (cur.data.get("status") if cur else "unknown"),
            "marks": marks, "killed": kill_proc, "escalated": escalated,
            "kill_wrapper": kill_wrap, "waited_sec": waited}


@app.post("/api/tasks/{task_id}/retry")
async def retry_background_task(task_id: str, payload: dict = None, request: Request = None):
    """失败任务一键重试：按 retry_backoff 的退避间隔重跑契约里记下的那条命令。

    三条硬规矩：
      1. 只重跑契约里**已经记下来的命令**（cmd + 脚本/阶段/参数/会话目录原样搬），不自己发挥；
      2. 隔多久、还能不能重试，全由 webui.runtime.retry_backoff 决定（2s/5s/15s，连续 3 次后停），
         服务端不另写一套退避；
      3. 重试出来的任务在契约里带 重试来源 / 重试根 / 第几次重试（面板画重试链、算上限）。
    需要和取消同一把 token；只对 failed / interrupted 生效（cancelled 是用户主动停的，不给按钮）。
    """
    tr = _task_run()
    if tr is None:
        return JSONResponse({"ok": False, "error": "task_run 模块不可用"}, status_code=503)
    _bind_task_run(tr)
    payload = payload or {}
    token = (request.headers.get("x-task-token", "") if request else "") or str(payload.get("token", ""))
    if token != _task_api_token():
        return JSONResponse({"ok": False, "error": "Unauthorized: missing/invalid task API token"},
                            status_code=401)
    t = tr.load_task(task_id)
    if t is None:
        return JSONResponse({"ok": False, "error": "任务不存在：%s" % task_id}, status_code=404)
    try:
        all_items = tr.list_tasks(limit=500, refresh=0)
    except Exception:      # pragma: no cover - 扫不到全量就只按本任务算
        all_items = [t.data]
    plan = _retry_plan(t.data, _retry_index(all_items, _RETRY_INFLIGHT))
    if not plan["allowed"]:
        return JSONResponse({"ok": False, "error": plan["reason"], "retry": plan}, status_code=409)
    denied = _sandbox_precheck("proc.exec", t.path, [HERMES_HOME_DIR], "tasks.retry")
    if denied:
        return JSONResponse({"ok": False, "error": "sandbox denied: %s" % denied}, status_code=403)
    # 退避 >0 时不在请求里干等（面板不用吊着），排个后台任务到点再拉起来。
    if plan["delay_sec"] > 0:
        _RETRY_INFLIGHT[plan["root"]] = time.time()
        try:
            asyncio.ensure_future(_retry_later(t.data, plan, plan["delay_sec"]))
        except Exception as e:          # pragma: no cover - 排不上就当场放开名额
            _RETRY_INFLIGHT.pop(plan["root"], None)
            return JSONResponse({"ok": False, "error": "排定重试失败：%s" % e, "retry": plan},
                                status_code=409)
        return {"ok": True, "scheduled": True, "task_id": task_id, "retry": plan,
                "attempt": plan["attempt"], "delay_sec": plan["delay_sec"],
                "cmd": str(t.data.get("cmd") or "")}
    spawned, err = _spawn_retry(t.data, plan)
    if err:
        return JSONResponse({"ok": False, "error": err, "retry": plan}, status_code=409)
    return {"ok": True, "scheduled": False, "task_id": task_id, "retry": plan,
            "attempt": plan["attempt"], "delay_sec": 0,
            "cmd": str(t.data.get("cmd") or ""), "spawned": spawned}


@app.delete("/api/tasks/{task_id}")
async def delete_background_task(task_id: str, payload: dict = None, request: Request = None):
    """删掉一条**已经结束**的任务记录（契约 .json + 它自己的日志）。

    三条硬规矩：
      1. 在跑 / 排队 / 暂停的一律不删（409，让用户先取消）—— 清理接口绝不偷偷杀进程；
      2. 只删任务记录，产出文件（results/ 里的数据）一个都不动；
      3. token 与取消/重试同一把（X-Task-Token），跨会话删除面板还会再问一次。
    """
    tr = _task_run()
    if tr is None:
        return JSONResponse({"ok": False, "error": "task_run 模块不可用"}, status_code=503)
    _bind_task_run(tr)
    payload = payload or {}
    token = (request.headers.get("x-task-token", "") if request else "") or str(payload.get("token", ""))
    if token != _task_api_token():
        return JSONResponse({"ok": False, "error": "Unauthorized: missing/invalid task API token"},
                            status_code=401)
    safe = os.path.basename(str(task_id or ""))
    denied = _sandbox_precheck("fs.delete", os.path.join(_tasks_dir(), safe + ".json"),
                               [HERMES_HOME_DIR, _tasks_dir()], "tasks.delete")
    if denied:
        return JSONResponse({"ok": False, "error": "sandbox denied: %s" % denied}, status_code=403)
    one = _task_delete_one(tr, task_id)
    if not one.get("ok"):
        return JSONResponse({"ok": False, "error": one.get("reason"), "task_id": task_id,
                             "status": one.get("status", "")},
                            status_code=int(one.get("code") or 409))
    return {"ok": True, "task_id": task_id, "status": one.get("status"),
            "title": one.get("title", ""), "removed": one.get("removed") or []}


@app.post("/api/tasks/cleanup")
async def cleanup_background_tasks(payload: dict = None, request: Request = None):
    """批量清理已结束的任务（默认 done/failed/cancelled/interrupted 全清）。

    payload 可选：
      states    只清这些状态（默认四类终态）；
      session_id 只清这个会话的（空 = 所有会话，跨会话可见就得跨会话可清）；
      ttl_hours 只清结束超过这么多小时的老任务（不传 = 不看时间，人工清就是立刻清）；
      dry_run   true 只报数不删（面板先让用户看清要删什么）。
    在跑/排队的一律不动，这条在 _tasks_cleanup 里是硬判断，不是靠调用方自觉。
    """
    tr = _task_run()
    if tr is None:
        return JSONResponse({"ok": False, "error": "task_run 模块不可用"}, status_code=503)
    _bind_task_run(tr)
    payload = payload or {}
    token = (request.headers.get("x-task-token", "") if request else "") or str(payload.get("token", ""))
    if token != _task_api_token():
        return JSONResponse({"ok": False, "error": "Unauthorized: missing/invalid task API token"},
                            status_code=401)
    states = payload.get("states") or None
    if isinstance(states, str):
        states = [s.strip() for s in states.split(",") if s.strip()]
    if states:
        bad = [s for s in states if s not in _task_terminal_states(tr)]
        if bad:
            return JSONResponse({"ok": False, "error": "不能清这些状态：%s（只允许 %s）"
                                 % ("/".join(bad), "/".join(_task_terminal_states(tr)))},
                                status_code=400)
    ttl = payload.get("ttl_hours")
    try:
        ttl = None if ttl in (None, "") else float(ttl)
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "ttl_hours 得是数字（小时）"}, status_code=400)
    denied = _sandbox_precheck("fs.delete", _tasks_dir(), [HERMES_HOME_DIR, _tasks_dir()],
                               "tasks.cleanup")
    if denied:
        return JSONResponse({"ok": False, "error": "sandbox denied: %s" % denied}, status_code=403)
    res = _tasks_cleanup(states=states, session_id=str(payload.get("session_id") or ""),
                         ttl_hours=ttl, dry_run=bool(payload.get("dry_run")))
    if not res.get("ok"):
        return JSONResponse(res, status_code=500)
    return res


@app.get("/api/version")
async def api_version():
    """前端版本标识：git commit + server 启动时间 + 修复包级别。

    修复包（fix_bundle）：打包分发的安装没有 .git（rev=unknown），
    用 hermes_home/.fix_bundle 标记当前修复级别；outdated=True 表示
    文件级修复已落后（旧安装/部分覆盖更新），WebUI 可据此提示升级。
    """
    import subprocess as _sp
    rev = "unknown"
    try:
        _r = _sp.run(["git", "rev-parse", "--short", "HEAD"], cwd=MEMOMICS_DIR,
                     capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3)
        if _r.returncode == 0:
            rev = _r.stdout.strip()
    except Exception:
        pass
    # 2026-08-16: 修复包级别（启动事件已自动应用文件级迁移，此处只报告）
    _level = "none"
    _outdated = False
    try:
        from memomics.fix_bundle import BUNDLE as _BUNDLE, fix_bundle_level as _level_fn
        _level = _level_fn(HERMES_HOME_DIR) or "none"
        _outdated = _level < _BUNDLE
        _bundle = _BUNDLE
    except Exception:
        _bundle = ""
    return {"version": rev, "started": _SERVER_STARTED_STR,
            "fix_bundle": _level, "fix_bundle_latest": _bundle, "outdated": _outdated}


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "MemOmics WebUI v2", "sessions": len(_sessions)}


# === 检查更新 / 在线更新（2026-08-23，迁移 MiMo-Code 更新架构：自动检查 + autoupdate 策略） ===

_GITHUB_REPO = "GGbond-bo/MemOmics-Agent"
_GITHUB_API = f"https://api.github.com/repos/{_GITHUB_REPO}"
_GITHUB_RAW = f"https://raw.githubusercontent.com/{_GITHUB_REPO}/main"
_PROXY = "http://127.0.0.1:6478"
#: 检查更新这条自带功能的固定外部依赖（强制模式下需要显式自授权，见下）
_UPDATE_HOST = "api.github.com"


def _sandbox_env_grants() -> None:
    """运维用环境变量显式声明的可写/可删目录（渐进强制下的逃生舱，幂等）。

    MEMOMICS_SANDBOX_GRANT_DIRS="D:/Desktop;E:/out"（分号或 os.pathsep 分隔）。
    为什么要有它：沙箱的 TTL 授权故意没有远程 API（线上临时开授权就是开后门），
    所以"我就是要往这个目录写"必须由启动环境显式声明，且理由进审计、随时可查。
    只在对应动作被强制时才打；观察模式下一律不动。
    """
    try:
        from webui import sandbox as _sb
        raw = os.environ.get("MEMOMICS_SANDBOX_GRANT_DIRS", "")
        if not raw.strip():
            return
        actions = [a for a in ("fs.write", "fs.delete") if _sb.enforce_action(a)]
        if not actions:
            return
        _sb.purge_expired()
        dirs = [d.strip() for d in re.split(r"[;%s]" % re.escape(os.pathsep), raw) if d.strip()]
        have = {(g.get("action"), os.path.normcase(g.get("resource") or ""))
                for g in _sb.grants() if (g.get("ttl_left") or 0) > 0}
        for d in dirs:
            ap = os.path.abspath(os.path.expanduser(d))
            for act in actions:
                if (act, os.path.normcase(ap)) in have:
                    continue
                _sb.grant(act, ap, ttl_s=7 * 86400.0,
                          reason="运维环境变量声明：MEMOMICS_SANDBOX_GRANT_DIRS", writable=True)
    except Exception as _e:
        print("[WARN] 可写目录授权失败: %s" % _e)


def _sandbox_precheck(action: str, path, roots, source: str = "server") -> str:
    """写/删类集成点的统一门：返回 "" 放行；非空 = 拒绝理由（调用方回 403）。

    与 security.resolve_within_roots 的区别很重要：这里**不做包含判定**——
    包含判定是老代码自己的规矩（roots 只当作策略提示交给沙箱）。
    观察模式（默认）下沙箱不拦人，老行为一个字节都不变；
    只有该动作被显式强制（MEMOMICS_SANDBOX_ENFORCE=fs.write 之类）才可能返回理由。
    沙箱自身的任何异常都被吞掉：安全组件宁可少拦，也绝不能把正常功能打挂。
    """
    try:
        import webui.sandbox as _sb
        _sandbox_env_grants()
        d = _sb.gate(action, str(path), roots=[str(r) for r in roots], source=source)
        if d.blocked:
            return "%s (%s)" % (d.code, d.reason)
    except Exception:
        return ""
    return ""


def _sandbox_ensure_app_grants() -> None:
    """强制模式下给自己人打窄授权：只授权固定主机、只授权 net.fetch、理由写清、全进审计。

    为什么需要它：api.github.com 是"检查更新"的固定依赖。一开强制、它又没授权，
    更新检查会立刻死掉——"安全了但功能废了"不是我们要的结果。所以把自依赖显式声明出来，
    而不是偷偷放行。授权是 TTL 的，本函数幂等：过期会被清掉并补打，调用方每次出网前调一次即可。
    观察模式（默认）下什么都不做。
    """
    try:
        from webui import sandbox as _sb
        if not _sb.enforce_action("net.fetch"):
            return
        _sb.purge_expired()
        have = {g.get("resource") for g in _sb.grants()
                if g.get("action") == "net.fetch" and (g.get("ttl_left") or 0) > 0}
        if _UPDATE_HOST not in have:
            _sb.grant("net.fetch", _UPDATE_HOST, ttl_s=3600.0,
                      reason="应用自更新检查（强制模式下的显式自依赖）", writable=False)
    except Exception as _e:
        print("[WARN] 应用自授权失败: %s" % _e)


_sandbox_ensure_app_grants()


def _get_update_config() -> dict:
    """读取更新策略配置（hermes_home/config.yaml 的 update 段）。

    对齐 MiMo-Code autoupdate 语义：
      notify — 仅通知用户有新版本（默认，更新由用户决定）
      false  — 完全关闭检查
      true   — 自动应用补丁（日期型 tag 无补丁概念，等价 notify）
    返回 {autoupdate: str, enabled: bool}
    """
    cfg = {"autoupdate": "notify", "enabled": True}
    try:
        import yaml as _yaml
        _p = os.path.join(HERMES_HOME_DIR, "config.yaml")
        if os.path.isfile(_p):
            with open(_p, encoding="utf-8") as _f:
                _d = _yaml.safe_load(_f) or {}
            _u = _d.get("update") or {}
            _v = str(_u.get("autoupdate", "notify")).lower()
            if _v == "false" or _v == "off" or _v == "0":
                cfg["autoupdate"] = "false"
                cfg["enabled"] = False
            elif _v == "true" or _v == "on":
                cfg["autoupdate"] = "true"
            else:
                cfg["autoupdate"] = "notify"
    except Exception:
        pass
    return cfg


def _set_update_config(autoupdate: str) -> dict:
    """写更新策略回 config.yaml（保留其他键）。"""
    import yaml as _yaml
    _p = os.path.join(HERMES_HOME_DIR, "config.yaml")
    try:
        with open(_p, encoding="utf-8") as _f:
            _d = _yaml.safe_load(_f) or {}
    except Exception:
        _d = {}
    _d.setdefault("update", {})
    _d["update"]["autoupdate"] = autoupdate
    try:
        with open(_p, "w", encoding="utf-8") as _f:
            _yaml.safe_dump(_d, _f, allow_unicode=True, sort_keys=False)
        return {"ok": True, "autoupdate": autoupdate}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# 启动时自动检查结果缓存（供前端 footer 状态点显示，避免每轮重复请求 GitHub）
_AUTO_CHECK = {"done": False, "status": "", "tag": "", "ts": 0.0, "error": ""}


def _background_update_check() -> None:
    """启动后台线程自动检查一次更新（对齐 MiMo-Code 启动即查；静默失败）。"""
    import threading as _th
    def _run():
        try:
            cfg = _get_update_config()
            if not cfg["enabled"]:
                _AUTO_CHECK.update(done=True, status="disabled", ts=__import__("time").time())
                return
            import asyncio as _aio
            # 用新事件循环执行 check（不依赖主 loop）
            _loop = _aio.new_event_loop()
            try:
                _r = _loop.run_until_complete(update_check())
            finally:
                _loop.close()
            _AUTO_CHECK.update(done=True, status=_r.get("status", ""),
                               tag=((_r.get("remote") or {}).get("tag", "")),
                               ts=__import__("time").time())
        except Exception as _e:
            _AUTO_CHECK.update(done=True, status="error", error=str(_e)[:150],
                               ts=__import__("time").time())
    _th.Thread(target=_run, daemon=True, name="memomics-auto-update-check").start()


# === 更新检查的 TLS 信任库（2026-09-23）===
# 用户报障：点"检查更新"偶发
#   <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
#    unable to get local issuer certificate (_ssl.c:1010)>
# 根因：urllib 走 Python 默认 SSL 上下文，在 Windows 上信任锚取自系统证书存储
# （ssl.enum_certificates 先 LocalMachine 后退 CurrentUser）。实测本机只载入 54 张，
# 而随包 certifi 有 119 张 —— 系统存储缺签发链时 GitHub 证书就验不过，检查直接失败。
# 修法：取 certifi ∪ 系统证书库（只取 certifi 会让装了 HTTPS 中间人安全软件的
# 用户从"偶尔失败"变成"稳定失败"—— 那类根证书只在系统库里）。绝不关闭证书校验。
_SSL_CTX_CACHE = None


def _ssl_context():
    """certifi ∪ 系统证书库 的 SSL 上下文（取并集，绝不关闭校验）。

    2026-09-23 用户报障后定位到：这条链路上"只取一边"会各坏一种用户。
      · 只信系统库（Python 默认）：安装包用户的系统库可能滞后/精简（实测随包
        运行时只读到 54 张），缺 GitHub 签发链 → "unable to get local issuer
        certificate"，也就是用户反馈的那个错；
      · 只信 certifi：公司/安全软件做 HTTPS 中间人时，其自签根证书只装在
        Windows 证收库里、certifi 没有（实测"仅系统库独有"的根有 21 张）
        → 这些用户会从"偶尔能连"变成"稳定连不上"，等于修一个坏一个。
    并集同时覆盖两种情形（实测随包运行时 150 + 54 → 172，⊇ 任一单独来源）。
    加载全部失败才退化为系统默认（依旧开着校验）。
    """
    global _SSL_CTX_CACHE
    if _SSL_CTX_CACHE is not None:
        return _SSL_CTX_CACHE
    import ssl as _ssl
    ctx = None
    try:
        import certifi
        ctx = _ssl.create_default_context(cafile=certifi.where())
    except Exception:
        try:
            ctx = _ssl.create_default_context()
        except Exception:
            return _ssl.create_default_context()
    try:
        ctx.load_default_certs()   # 并上系统库：补中间人根证书/本机专有 CA
    except Exception:
        pass
    _SSL_CTX_CACHE = ctx
    return ctx


def _url_opener(proxy):
    """构建带 TLS 上下文与可选代理的 opener。

    2026-09-23 两个真实缺陷（用户报障"检查更新偶发失败"的根因）：
    1. TLS 上下文用 Python 默认值 → Windows 取系统证书存储（本机仅 54 张信任锚），
       而随包 certifi 有 119 张；缺签发链时报
       "[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate"。
    2. 所谓"失败降级直连"其实没直连 —— build_opener() 会自动挂一个读系统代理的
       ProxyHandler，而本机注册表 ProxyEnable=1 指向 127.0.0.1:6478，于是两轮尝试
       走的是同一个代理、同一个失败原因，"双路兜底"形同虚设。
       现改为 proxy=None 时显式 ProxyHandler({})（空字典=禁用全部代理）才真正直连。
    """
    import urllib.request as _ur
    handlers = [_ur.HTTPSHandler(context=_ssl_context())]
    handlers.append(_ur.ProxyHandler({"http": proxy, "https": proxy}) if proxy
                    else _ur.ProxyHandler({}))   # 空字典 = 真直连，不读系统代理
    return _ur.build_opener(*handlers)


def _http_get_text(url: str, timeout: int = 20) -> str:
    """GET 纯文本（CDN 镜像源用：无 API 配额限制）。"""
    import urllib.request as _ur
    last_err = None
    for proxy in (_PROXY, None):
        try:
            req = _ur.Request(url, headers={"User-Agent": "MemOmics-Updater"})
            with _url_opener(proxy).open(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last_err = e
            continue
    raise last_err


def _asset_exists(tag: str, name: str, timeout: int = 15) -> bool:
    """探测 release 资产是否存在（HEAD/Range 探测，不下载正文）。

    API 配额用尽时的回退：tag 已知则资产 URL 可推导，但资产不一定都在，
    所以用 1 字节 Range 请求确认，避免给用户一个 404 的更新按钮。
    """
    import urllib.request as _ur
    url = f"https://github.com/{_GITHUB_REPO}/releases/download/{tag}/{name}"
    for proxy in (_PROXY, None):
        try:
            req = _ur.Request(url, headers={"User-Agent": "MemOmics-Updater", "Range": "bytes=0-0"})
            with _url_opener(proxy).open(req, timeout=timeout) as r:
                if r.status in (200, 206):
                    return True
        except Exception:
            continue
    return False


def _net_error_hint(err) -> str:
    """把网络异常翻译成可操作的中文提示（TLS 证书问题单独说明）。"""
    txt = str(err)
    low = txt.lower()
    if "certificate" in low and ("verify failed" in low or "local issuer" in low):
        return ("TLS 证书校验失败：本机信任库缺少 GitHub 证书的签发链。"
                "已改用 certifi 信任库并自动重试；若持续失败，请检查本机代理 "
                "127.0.0.1:6478 是否在改写 HTTPS 流量，或到 GitHub Releases 手动下载安装包覆盖更新。"
                "原始错误：" + txt[:160])
    if "rate limit" in low or "403" in txt:
        return ("GitHub API 访问受限（匿名调用每小时 60 次配额用尽）。"
                "已自动改用 CDN 镜像获取版本；你也可稍后重试或直接到 Release 页手动下载。"
                "原始错误：" + txt[:160])
    if "timed out" in low or "timeout" in low:
        return "连接 GitHub 超时（网络或代理不可用，可稍后重试）。原始错误：" + txt[:160]
    if "getaddrinfo" in low or "name or service not known" in low or "11001" in txt:
        return "DNS 解析失败（无网络或代理故障）。原始错误：" + txt[:160]
    return txt[:200]


def _http_get_json(url: str, timeout: int = 20, retries: int = 2) -> dict:
    """带代理的 GET JSON：certifi 信任库 + 代理/直连双路 + 瞬时失败重试。"""
    import urllib.request as _ur
    headers = {"User-Agent": "MemOmics-Updater", "Accept": "application/vnd.github+json"}
    last_err = None
    tries = max(1, int(retries))
    for attempt in range(tries):
        for proxy in (_PROXY, None):
            try:
                if _net_guard is not None:
                    _sandbox_ensure_app_grants()      # 强制模式下补齐自依赖授权（TTL 到期自动续）
                    with _net_guard.urlopen(url, timeout=timeout, headers=headers,
                                            proxy=proxy, action="net.fetch",
                                            source="update.check") as r:
                        return json.loads(r.read().decode("utf-8", "replace"))
                req = _ur.Request(url, headers=headers)
                with _url_opener(proxy).open(req, timeout=timeout) as r:
                    return json.loads(r.read().decode("utf-8", "replace"))
            except Exception as e:
                last_err = e
                continue
        if attempt + 1 < tries:
            time.sleep(1.5 * (attempt + 1))
    raise last_err


def _git_run(args: list, timeout: int = 60) -> str:
    """在 MemOmics 仓库执行 git（走代理环境变量），返回 stdout。"""
    import subprocess as _sp
    env = dict(os.environ)
    env["HTTPS_PROXY"] = _PROXY
    env["HTTP_PROXY"] = _PROXY
    r = _sp.run(["git"] + args, cwd=MEMOMICS_DIR, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def _local_version_info() -> dict:
    """本地版本：VERSION 文件 + git commit（若有）+ fix_bundle 级别。

    安装包用户无 .git → VERSION 是唯一版本标识；开发仓库另有 git commit。
    """
    # VERSION 文件（打包时写入，安装后根目录存在）
    ver = "unknown"
    try:
        _vp = os.path.join(MEMOMICS_DIR, "VERSION")
        if os.path.isfile(_vp):
            with open(_vp, encoding="utf-8", errors="replace") as f:
                ver = f.read().strip() or "unknown"
    except Exception:
        pass
    # git commit（开发仓库才有；安装包无 .git → unknown）
    rev = "unknown"
    date = ""
    try:
        rev = _git_run(["rev-parse", "--short", "HEAD"])
    except Exception:
        pass
    try:
        date = _git_run(["log", "-1", "--format=%cd", "--date=short"])
    except Exception:
        pass
    bundle = "none"
    try:
        from memomics.fix_bundle import BUNDLE
        bundle = BUNDLE
    except Exception:
        pass
    return {"version": ver, "rev": rev, "date": date, "fix_bundle": bundle,
            "has_git": rev != "unknown"}


# 平台 → GitHub release 资产名（2026-08-23；新增资产时在此登记）
def _platform_asset() -> str:
    """按当前平台返回 release 资产名（zip/tar.gz），未知平台返回空。"""
    import platform as _plt
    sysname = (_plt.system() or "").lower()
    machine = (_plt.machine() or "").lower()
    if sysname == "windows":
        return "MemOmics-Windows.zip"
    if sysname == "linux":
        return "MemOmics-Linux.tar.gz"
    if sysname == "darwin":
        return ("MemOmics-macOS-arm64.tar.gz" if "arm" in machine or "aarch64" in machine
                else "MemOmics-macOS-x86_64.tar.gz")
    return ""


# ── 差异覆盖的保留清单（对齐打包.bat 排除：用户数据/环境/密钥绝不覆盖）──
_KEEP_DIRS = (".venv", ".git", ".backups", "node_modules", "miniconda_env", "miniconda",
              "runtime", "hermes_home", "results", "uploads", "log", "ArchRLogs",
              "__pycache__", ".pytest_cache", ".idea", ".vscode")
_KEEP_FILES = (".env", ".install_path", "venv_deps_ok.txt", "venv_vision_ok.txt",
               "VERSION",  # 本地版本标识不被远端覆盖（覆盖会破坏比较）
               )
_KEEP_TOP_LEVEL = ("hermes_home", "results", "uploads", "log", ".venv", "runtime",
                   "node_modules", "miniconda_env", "miniconda", ".git", ".backups")


def _is_keep_path(rel: str, allow_skills: bool = True, allow_version: bool = True) -> bool:
    """判断 zip 内相对路径是否应保留（不覆盖）。

    检查路径的每一段：任何一段命中保留目录（node_modules/.venv/hermes_home 等）
    都保留——例如 hermes-agent/node_modules/xxx 命中 node_modules 段。

    2026-08-23 细化（轻量 update 包场景）：
    - hermes_home/ 整体保留（config/memories/sessions 是用户数据）
    - 但 hermes_home/skills/ 例外：技能库是发布内容，随版本更新
    - VERSION 例外：update 包携带发布版 VERSION，允许覆盖（更新后版本号变化）
    """
    rel = rel.replace("\\", "/").lstrip("/")
    if not rel:
        return True
    parts = [p for p in rel.split("/") if p and p != "."]  # 忽略空段和 ./ 段
    if not parts:
        return True
    top = parts[0]
    if top in _KEEP_TOP_LEVEL:
        # 例外 1: hermes_home/skills 技能库随版本更新
        if top == "hermes_home" and len(parts) > 1 and parts[1] == "skills":
            return False
        return True
    # 路径任何段命中保留目录 → 保留（覆盖 hermes-agent/node_modules、memomics/vendor 等）
    if any(seg in _KEEP_DIRS for seg in parts):
        return True
    # 例外 2: VERSION 允许被 update 包覆盖（携带发布版号）
    if parts[-1] == "VERSION":
        return False
    if parts[-1] in _KEEP_FILES:
        return True
    return False


# ── 更新任务状态（单任务锁 + 取消） ──
_UPDATE_TASK = {"running": False, "cancelled": False, "stage": "", "progress": 0.0,
                "total_bytes": 0, "done_bytes": 0, "error": "", "started": ""}


def _update_status_dict() -> dict:
    return dict(_UPDATE_TASK, progress_pct=round(
        _UPDATE_TASK["done_bytes"] / _UPDATE_TASK["total_bytes"] * 100, 1)
        if _UPDATE_TASK["total_bytes"] else 0.0)


@app.get("/api/update/status")
async def update_status():
    """更新任务状态（进度/阶段/可取消）。"""
    return _update_status_dict()


@app.get("/api/update/autocheck")
async def update_autocheck():
    """启动时自动检查的结果（供前端 footer 状态点显示，不重复请求 GitHub）。"""
    return dict(_AUTO_CHECK, config=_get_update_config())


@app.post("/api/update/config")
async def update_config(payload: dict):
    """修改更新策略（对齐 MiMo-Code autoupdate：notify/false/true）。"""
    mode = str(payload.get("autoupdate") or "").lower()
    if mode not in ("notify", "false", "true"):
        return JSONResponse({"error": "autoupdate 必须是 notify/false/true"}, status_code=400)
    return _set_update_config(mode)


@app.post("/api/update/cancel")
async def update_cancel():
    """取消进行中的下载/解压（覆盖阶段不中断：覆盖是原子短操作）。"""
    if _UPDATE_TASK["running"] and _UPDATE_TASK["stage"] in ("download", "extract"):
        _UPDATE_TASK["cancelled"] = True
        return {"ok": True, "message": "已请求取消"}
    if _UPDATE_TASK["stage"] == "apply":
        return {"ok": False, "message": "正在覆盖文件（短暂操作），无法取消，请稍候"}
    return {"ok": False, "message": "当前没有可取消的更新任务"}


def _download_file(url: str, dest: str, timeout: int = 1800) -> None:
    """流式下载到文件，支持取消与进度；失败清理。"""
    import urllib.request as _ur
    _UPDATE_TASK["stage"] = "download"
    _UPDATE_TASK["done_bytes"] = 0
    last_err = None
    for proxy in (_PROXY, None):
        if _UPDATE_TASK["cancelled"]:
            raise RuntimeError("已取消")
        try:
            req = _ur.Request(url, headers={"User-Agent": "MemOmics-Updater"})
            # 2026-09-23: 统一走 _url_opener（挂 certifi 信任库 + 代理/直连），
            # 下载大包时同样会撞上缺签发链的 CERTIFICATE_VERIFY_FAILED
            with _url_opener(proxy).open(req, timeout=timeout) as r, open(dest, "wb") as f:
                _UPDATE_TASK["total_bytes"] = int(r.headers.get("Content-Length") or 0)
                while True:
                    if _UPDATE_TASK["cancelled"]:
                        f.close()
                        try:
                            os.remove(dest)
                        except Exception:
                            pass
                        raise RuntimeError("已取消")
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    _UPDATE_TASK["done_bytes"] += len(chunk)
            return
        except Exception as e:
            last_err = e
            if isinstance(e, RuntimeError) and str(e) == "已取消":
                raise
            continue
    raise last_err


def _safe_extract(archive_path: str, dest_dir: str, is_tar: bool = False) -> list:
    """安全解压（防路径穿越），返回顶层目录名列表。"""
    import zipfile
    import tarfile
    _UPDATE_TASK["stage"] = "extract"
    os.makedirs(dest_dir, exist_ok=True)
    tops = set()
    if is_tar:
        with tarfile.open(archive_path, "r:gz") as tf:
            for m in tf.getmembers():
                name = m.name.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    raise RuntimeError(f"非法的归档路径: {name}")
                if m.isdir():
                    tops.add(name.rstrip("/").split("/")[0])
                    continue
                target = os.path.join(dest_dir, *name.split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                src = tf.extractfile(m)
                if src:
                    with open(target, "wb") as f:
                        while True:
                            if _UPDATE_TASK["cancelled"]:
                                raise RuntimeError("已取消")
                            chunk = src.read(1 << 20)
                            if not chunk:
                                break
                            f.write(chunk)
                tops.add(name.split("/")[0])
    else:
        with zipfile.ZipFile(archive_path) as zf:
            for m in zf.infolist():
                name = m.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    raise RuntimeError(f"非法的归档路径: {name}")
                if m.is_dir():
                    tops.add(name.rstrip("/").split("/")[0])
                    continue
                target = os.path.join(dest_dir, *name.split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(m) as src, open(target, "wb") as f:
                    while True:
                        if _UPDATE_TASK["cancelled"]:
                            raise RuntimeError("已取消")
                        chunk = src.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                tops.add(name.split("/")[0])
    return sorted(tops)


def _apply_overlay(extract_root: str, tops: list) -> int:
    """把解压出的内容按保留清单覆盖到安装目录，返回覆盖文件数。

    tops 是解压顶层名列表；若 extract_root 已定位到内容根（zip 内单层
    MemOmics-Windows/ 子目录），tops 传入该子目录名 → 直接覆盖其内容。
    """
    import shutil as _sh
    _UPDATE_TASK["stage"] = "apply"
    copied = 0
    # 若 extract_root 本身就是某个 top 的内容目录，直接覆盖根
    base_name = os.path.basename(extract_root.rstrip(os.sep))
    roots = []
    if base_name in tops and os.path.isdir(extract_root):
        roots.append(("", extract_root))  # 覆盖 extract_root 下所有内容到 MEMOMICS_DIR
    else:
        for top in tops:
            # 2026-08-23: hermes_home 顶层特殊处理——允许进入（skills 技能库随版本更新），
            # 内部子目录仍按 _is_keep_path 过滤（config/memories/sessions 保留）
            if top == "hermes_home":
                src_dir = os.path.join(extract_root, top)
                if os.path.isdir(src_dir):
                    roots.append((top, src_dir))
                continue
            if _is_keep_path(top):
                continue
            src_dir = os.path.join(extract_root, top)
            if os.path.isdir(src_dir):
                roots.append((top, src_dir))
    for prefix, src_dir in roots:
        dst_dir = MEMOMICS_DIR if not prefix else os.path.join(MEMOMICS_DIR, prefix)
        os.makedirs(dst_dir, exist_ok=True)
        for root, dirs, files in os.walk(src_dir):
            rel_sub = os.path.relpath(root, src_dir)
            keep_dirs = []
            for d in dirs:
                rel_d = os.path.join(prefix, rel_sub, d).replace("\\", "/")
                # 2026-08-23: hermes_home 必须进入 walk（内部 skills 更新），
                # 仅当整路径命中保留时才剪枝（如 hermes_home/memories）
                if rel_d.lstrip("./") == "hermes_home" or not _is_keep_path(rel_d):
                    keep_dirs.append(d)
            dirs[:] = keep_dirs
            for fn in files:
                rel = os.path.join(prefix, rel_sub, fn).replace("\\", "/")
                if _is_keep_path(rel):
                    continue
                s = os.path.join(root, fn)
                d = os.path.join(dst_dir, rel_sub, fn)
                try:
                    os.makedirs(os.path.dirname(d), exist_ok=True)
                    _sh.copy2(s, d)
                    copied += 1
                except Exception:
                    # 单个文件失败不阻断（运行中占用等），记录继续
                    pass
    return copied


@app.get("/api/update/check")
async def update_check():
    """检查更新：本地 VERSION vs GitHub 最新 release（含平台资产信息）。

    返回:
      local: {version, rev, date, fix_bundle, has_git}
      remote: {tag, tag_date, asset_name, asset_size_mb, asset_url, tag_url}
      status: "up_to_date" | "update_available" | "local_ahead" | "unable_to_check"
      update_mode: "zip_overlay"（有平台资产可自动覆盖）| "manual"（无资产/无 VERSION）
    """
    local = _local_version_info()
    result = {"local": local, "remote": None, "status": "unable_to_check", "update_mode": "manual",
              "install_type": "unknown", "local_ahead_commits": 0, "error": ""}
    # 安装方式检测（迁移 MiMo-Code method 概念）：git 仓库 / 安装包（无 git）
    try:
        if local.get("has_git"):
            result["install_type"] = "git"
        elif local.get("version") != "unknown":
            result["install_type"] = "portable"
        else:
            result["install_type"] = "unknown"
    except Exception:
        pass
    try:
        tag = tag_date = ""
        assets = []
        try:
            rel = _http_get_json(f"{_GITHUB_API}/releases/latest")
            tag = rel.get("tag_name", "")
            tag_date = (rel.get("published_at") or "")[:10]
            assets = rel.get("assets") or []
            result["source"] = "api"
        except Exception as api_err:
            # 2026-09-23: GitHub REST 匿名配额只有 60 次/小时，超了返回
            # "HTTP Error 403: rate limit exceeded"，此前会直接把整个检查判失败。
            # 退路：raw.githubusercontent 的 VERSION（CDN，无配额）+ 按约定拼资产名
            # （tag 已知则 asset URL 是可推导的，不需要 API 列举）。
            result["source"] = "cdn"
            result["api_error"] = _net_error_hint(api_err)
            ver_txt = _http_get_text(f"{_GITHUB_RAW}/VERSION").strip()
            m = re.search(r"v\d{4}-\d{2}-\d{2}", ver_txt)
            if not m:
                raise RuntimeError(
                    "GitHub API 受限（" + str(api_err)[:80] + "）且 CDN 回退未取到版本号")
            tag = m.group(0)
            result["remote_note"] = "GitHub API 配额用尽，已用 CDN 镜像获取版本；更新包地址按约定推导"
        if assets:
            # 更新包优先级 —— 轻量代码包 MemOmics-update.zip（跨平台）优先，
            # 老用户升级只下载代码；找不到才回退平台完整包（新装机用）。
            upd_asset = next((a for a in assets if a.get("name") == "MemOmics-update.zip"), None)
            asset_name = _platform_asset()
            full_asset = next((a for a in assets if a.get("name") == asset_name), None) if asset_name else None
            asset = upd_asset or full_asset
        elif tag:
            # CDN 回退：tag 已知 → release 资产 URL 可推导（下载前会先探测存在性）
            asset_name = _platform_asset()
            upd_name = "MemOmics-update.zip"
            if _asset_exists(tag, upd_name):
                asset = {"name": upd_name, "size": 0,
                         "browser_download_url": f"https://github.com/{_GITHUB_REPO}/releases/download/{tag}/{upd_name}"}
            elif asset_name and _asset_exists(tag, asset_name):
                asset = {"name": asset_name, "size": 0,
                         "browser_download_url": f"https://github.com/{_GITHUB_REPO}/releases/download/{tag}/{asset_name}"}
            else:
                asset = None
        else:
            asset = None
        _aname = (asset or {}).get("name", "")
        result["remote"] = {
            "tag": tag, "tag_date": tag_date,
            "asset_name": _aname,
            "asset_size_mb": round((asset.get("size") or 0) / 1048576, 1) if asset else 0,
            "asset_url": (asset or {}).get("browser_download_url", ""),
            "asset_kind": ("update" if _aname == "MemOmics-update.zip"
                           else ("full" if _aname else "")),
            "tag_url": f"https://github.com/{_GITHUB_REPO}/releases/latest",
        }
        local_ver = local.get("version") or "unknown"
        if local_ver == "unknown" or not tag:
            result["status"] = "unable_to_check"
            result["error"] = "无法获取本地 VERSION 或远端 release" if not tag else "本地缺少 VERSION 文件（旧安装），请手动更新"
            result["update_mode"] = "manual"
        else:
            # 比较：开发版（vdev-*）永远视为最新；否则按 tag 字符串比较
            if local_ver.startswith("vdev") or local_ver.startswith("dev"):
                result["status"] = "local_ahead"
                result["update_mode"] = "manual" if not asset else "zip_overlay"
            elif local_ver == tag:
                result["status"] = "up_to_date"
                result["update_mode"] = "zip_overlay" if asset else "manual"
            else:
                result["status"] = "update_available"
                result["update_mode"] = "zip_overlay" if asset else "manual"
    except Exception as e:
        result["error"] = _net_error_hint(e)
        result["status"] = "unable_to_check"
    return result


@app.post("/api/update/apply")
async def update_apply(payload: dict):
    """执行更新（用户已确认）：下载平台安装包 → 校验 → 差异覆盖代码（保留用户数据）→ fix_bundle。

    覆盖范围：zip 内除保留清单（hermes_home/results/.venv/runtime/node_modules 等）外的代码文件。
    完成后需用户重启服务生效。
    """
    confirmed = payload.get("confirmed")
    if not confirmed:
        return JSONResponse({"error": "需要 confirmed=true 确认"}, status_code=400)
    if _UPDATE_TASK["running"]:
        return JSONResponse({"error": "已有更新任务进行中"}, status_code=409)
    check = await update_check()
    if check["status"] != "update_available":
        return JSONResponse({"error": f"当前状态 {check['status']}，无需更新或无法更新"}, status_code=400)
    remote = check.get("remote") or {}
    asset_url = remote.get("asset_url") or ""
    asset_name = remote.get("asset_name") or ""
    if not asset_url or not asset_name:
        return JSONResponse({"error": "当前平台无可用更新包（没有匹配的 release 资产）"}, status_code=400)

    import tempfile as _tmp
    import shutil as _sh
    _UPDATE_TASK.update(running=True, cancelled=False, stage="download", progress=0.0,
                        total_bytes=0, done_bytes=0, error="",
                        started=datetime.now().strftime("%H:%M:%S"))
    tmpdir = ""
    try:
        tmpdir = _tmp.mkdtemp(prefix="memomics_update_")
        archive = os.path.join(tmpdir, asset_name)
        # 1. 下载
        _download_file(asset_url, archive)
        if _UPDATE_TASK["cancelled"]:
            raise RuntimeError("已取消")
        # 2. 解压
        is_tar = asset_name.endswith(".tar.gz")
        extract = os.path.join(tmpdir, "extract")
        tops = _safe_extract(archive, extract, is_tar=is_tar)
        if not tops:
            raise RuntimeError("安装包为空或解压失败")
        # 解压后内容可能在顶层子目录（如 MemOmics-Windows/）
        extract_root = extract
        for t in tops:
            cand = os.path.join(extract, t)
            if os.path.isdir(cand) and (os.path.isfile(os.path.join(cand, "start.bat")) or
                                        os.path.isfile(os.path.join(cand, "start.sh"))):
                extract_root = cand
                break
        # 3. 差异覆盖（保留用户数据）
        copied = _apply_overlay(extract_root, tops)
        # 4. 应用文件级迁移
        fix_log = ""
        try:
            import subprocess as _sp
            r = _sp.run([sys.executable, os.path.join(MEMOMICS_DIR, "scripts", "apply_fix_bundle.py")],
                        cwd=MEMOMICS_DIR, capture_output=True, text=True, encoding="utf-8",
                        errors="replace", timeout=60)
            fix_log = (r.stdout or "")[-200:]
        except Exception as e:
            fix_log = f"fix_bundle 跳过: {e}"
        if _UPDATE_TASK["cancelled"]:
            raise RuntimeError("已取消")
        new_local = _local_version_info()
        _UPDATE_TASK["running"] = False
        _UPDATE_TASK["stage"] = "done"
        return {"ok": True, "message": f"已覆盖 {copied} 个代码文件", "fix_log": fix_log,
                "new_version": new_local.get("version"), "restart_required": True,
                "asset_size_mb": remote.get("asset_size_mb")}
    except RuntimeError as e:
        _UPDATE_TASK["running"] = False
        _UPDATE_TASK["error"] = str(e)
        return JSONResponse({"error": str(e)}, status_code=400 if str(e) == "已取消" else 500)
    except Exception as e:
        _UPDATE_TASK["running"] = False
        _UPDATE_TASK["error"] = str(e)[:300]
        return JSONResponse({"error": f"更新失败: {str(e)[:300]}"}, status_code=500)
    finally:
        if tmpdir:
            try:
                _sh.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass


# === 首次启动 / 环境检测 ===

@app.get("/api/setup/status")
async def setup_status():
    """检查是否需要首次配置"""
    _has_valid_key = _is_valid_api_key(_current_model.get("api_key"))
    needs_config = (not _has_valid_key
                    or not _current_model.get("base_url")
                    or not _current_model.get("model"))
    return {
        "needs_config": needs_config,
        "current": {
            "provider": _current_model.get("provider", "openai"),
            "base_url": _current_model.get("base_url", ""),
            "model": _current_model.get("model", ""),
            "has_key": _has_valid_key,
        }
    }


@app.post("/api/setup/config")
async def setup_config(req: Request):
    """首次配置：保存 API key + base_url + model"""
    data = await req.json()
    provider = data.get("provider", "openai")
    base_url = data.get("base_url", "").strip()
    api_key = data.get("api_key", "").strip()
    model = data.get("model", "").strip()
    if not api_key or not base_url or not model:
        return JSONResponse({"error": "api_key, base_url, model are required"}, status_code=400)
    _current_model["provider"] = provider
    _current_model["base_url"] = base_url
    _current_model["api_key"] = api_key
    _current_model["model"] = model
    _save_model_config()
    try:
        _cfg_path = os.path.join(HERMES_HOME_DIR, "config.yaml")
        _cfg_lines = [
            f"api_base: {base_url}",
            f"api_key: {api_key}",
            "max_turns: 200",
            f"model: {model}",
            f"provider: {provider}",
            "sessions:",
            "  write_json_snapshots: true",
            "skills:",
            "  disabled: []",
        ]
        with open(_cfg_path, "w", encoding="utf-8") as f:
            f.write("\n".join(_cfg_lines) + "\n")
    except Exception as e:
        print(f"[WARN] 写入 config.yaml 失败: {e}")
    return {"ok": True, "model": model, "base_url": base_url}


# === 环境管理（env_inventory，2026-09-22 新增）===
# 用户和 agent 都能看到：本机有什么环境（R/Python/生信 CLI/GPU/磁盘/已知坑）+
# 集群有什么（节点/核数/负载/调度器/目录/已装工具与版本）。
# 集群探测要 SSH（每节点最长 60 秒），绝不能卡在 HTTP 请求里：
#   GET 只读缓存并立刻返回；refresh=1 只负责"踢一脚"后台线程，前端轮询 state.status。
_ENV_INV_STATE = {"status": "idle", "scope": "", "started_at": 0, "finished_at": 0, "error": ""}
_ENV_INV_LOCK = _threading.Lock()


def _env_inv_module():
    from memomics.bio_tools import env_inventory as _mod
    return _mod


def _env_inv_scan(scope="all"):
    """后台线程里真探测。scope: all（本机+集群）/ local（只本机）/ cluster（只集群）。"""
    with _ENV_INV_LOCK:
        _ENV_INV_STATE.update({"status": "running", "scope": scope,
                               "started_at": time.time(), "error": ""})
    try:
        mod = _env_inv_module()
        if scope == "cluster":
            mod.scan_cluster(force=True)
        elif scope == "local":
            mod.scan_local(force=True)
        else:
            mod.build_report(force=True, cluster=True)
        with _ENV_INV_LOCK:
            _ENV_INV_STATE.update({"status": "ok", "finished_at": time.time()})
    except Exception as e:
        with _ENV_INV_LOCK:
            _ENV_INV_STATE.update({"status": "error", "error": f"{type(e).__name__}: {e}",
                                   "finished_at": time.time()})


def _env_inv_refresh(scope="all"):
    """踢一脚后台刷新；已经在跑就返回 False（不重复探测）。"""
    with _ENV_INV_LOCK:
        if _ENV_INV_STATE.get("status") == "running":
            return False
    _threading.Thread(target=_env_inv_scan, args=(scope,), daemon=True,
                      name="env-inventory-scan").start()
    return True


@app.get("/api/env/inventory")
async def env_inventory_api(refresh: int = 0, cluster: int = 1, scope: str = ""):
    """环境管理面板数据：本机 + 集群。

    refresh=1 触发后台重扫（不阻塞）：返回当前缓存 + state.status=running，前端轮询刷新。
    cluster=0 只清点本机（完全不碰 SSH）。任何情况下都先返回缓存，绝不空等。
    """
    mod = _env_inv_module()
    report = mod.build_report(cache_only=True, cluster=bool(cluster))
    local = report.get("local") or {}
    cluster_data = report.get("cluster") or {}
    pending = bool(local.get("pending")) or bool(cluster_data.get("pending"))
    # 2026-09-23：过期数据仍然返回（面板不再回退成"没扫过"），但必须照样踢后台刷新，
    # 否则 stale 的数据会一直卡着不更新 —— 这里把 needs_refresh 也算作要刷新。
    stale = bool(local.get("needs_refresh")) or bool(cluster_data.get("needs_refresh"))
    triggered = None
    if refresh or pending or stale:
        triggered = _env_inv_refresh(scope or ("all" if cluster else "local"))
    with _ENV_INV_LOCK:
        state = dict(_ENV_INV_STATE)
    if triggered is not None:
        state["triggered"] = triggered
    return {"ok": True, "state": state, "local": local, "cluster": cluster_data,
            "warnings": report.get("warnings") or [], "pending": pending,
            "stale": stale,
            "agent_digest": report.get("agent_digest") or "",
            "cache_path": mod._cache_path()}


@app.post("/api/env/verify")
async def env_verify_api():
    """便宜地"确认一遍"环境（毫秒级）：指纹没变就复用缓存，变了才重扫。

    2026-09-23：用户要的"下次遇到分析再确认一遍"落在这里 ——
    不陪 R 全量探测（10~45 秒），但装/卸包一定被指纹抓到。
    """
    mod = _env_inv_module()
    try:
        # verify 在"环境变了"时会真扫（本机 10~45 秒）→ 必须挪出事件循环，
        # 否则这几十秒里整个 WebUI 的 HTTP 都停摆（照仓库惯例用 to_thread）。
        result = await asyncio.to_thread(mod.verify)
    except Exception as e:
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    if result.get("rescanned"):
        with _ENV_INV_LOCK:
            _ENV_INV_STATE.update({"status": "ok", "finished_at": time.time()})
    return result


@app.get("/api/env/report.md")
async def env_report_md(download: int = 0):
    """人看的 markdown 环境报告（可下载存档 / 贴给同事）。只读缓存，秒回。"""
    mod = _env_inv_module()
    text = mod.render_markdown(cache_only=True)
    headers = ({"Content-Disposition": 'attachment; filename="memomics-environment.md"'}
               if download else {})
    return Response(text, media_type="text/markdown; charset=utf-8", headers=headers)


@app.on_event("startup")
async def _env_inventory_warmup():
    """启动后预热环境清单：后台线程，先等服务起来再扫，不拖慢启动。"""
    def _warm():
        time.sleep(8)
        try:
            _env_inv_module().build_report(force=False, cluster=True)
        except Exception as e:
            print(f"[WARN] 环境清单预热失败: {e}")
    _threading.Thread(target=_warm, daemon=True, name="env-inventory-warmup").start()


@app.get("/api/env/check")
async def env_check():
    """环境自检：Python/R/GPU/磁盘/内存/关键包"""
    import shutil, platform, subprocess as _sp
    result = {"python": {}, "r": {}, "gpu": {}, "system": {}, "packages": {}}
    result["python"]["version"] = sys.version.split()[0]
    result["python"]["ok"] = True
    r_path = shutil.which("Rscript")
    if r_path:
        try:
            rv = _sp.run(["Rscript", "-e", "cat(R.version$major, R.version$minor, sep='.')"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
            result["r"]["version"] = rv.stdout.strip()
            result["r"]["ok"] = True
        except Exception:
            result["r"]["ok"] = False
    else:
        result["r"]["ok"] = False
    try:
        gpu = shutil.which("nvidia-smi")
        if gpu:
            gv = _sp.run([gpu, "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
            result["gpu"]["name"] = gv.stdout.strip()
            result["gpu"]["ok"] = True
        else:
            result["gpu"]["ok"] = False
    except Exception:
        result["gpu"]["ok"] = False
    result["system"]["platform"] = platform.platform()
    try:
        import psutil
        result["system"]["memory_gb"] = round(psutil.virtual_memory().total / (1024**3), 1)
        result["system"]["disk_free_gb"] = round(psutil.disk_usage(".").free / (1024**3), 1)
    except Exception:
        pass
    return result


@app.get("/api/enforcement/{sid}")
async def enforcement_status(sid: str):
    """查询会话的强制执行状态"""
    from webui import enforcement as _enf
    return _enf.get_enforcement_report(sid)


@app.get("/api/weixin/status")
async def weixin_status():
    """获取微信连接状态"""
    result = {
        "connected": _weixin_state["connected"],
        "account_id": _weixin_state["account_id"][:16] + "..." if _weixin_state["account_id"] else "",
        "qr_login_in_progress": _weixin_state["qr_login_in_progress"],
        "last_error": _weixin_state["last_error"],
        "agent_enabled": _weixin_agent_enabled,
        "adapter_alive": _weixin_adapter is not None and getattr(_weixin_adapter, '_poll_task', None) is not None and not getattr(_weixin_adapter._poll_task, 'done', lambda: True)(),
        "msg_count": len(_weixin_msg_store),
    }
    return result


@app.post("/api/weixin/qr-login")
async def weixin_qr_login():
    """发起微信 iLink QR 码登录"""
    global _weixin_state
    if _weixin_state["qr_login_in_progress"]:
        # 如果上一次 QR 登录已超时，强制重置
        _weixin_state["qr_login_in_progress"] = False
        _weixin_state["qrcode_token"] = ""
    
    try:
        import aiohttp
        _weixin_state["qr_login_in_progress"] = True
        _weixin_state["last_error"] = ""
        
        base_url = _weixin_state["base_url"]
        async with aiohttp.ClientSession() as session:
            async def _qr_get():
                async with session.get(
                    f"{base_url}/ilink/bot/get_bot_qrcode?bot_type=3",
                    headers={"iLink-App-Id": "bot", "iLink-App-ClientVersion": "131584"},
                ) as resp:
                    return await resp.text()
            raw = await asyncio.wait_for(_qr_get(), timeout=35)
            data = json.loads(raw)
            if data.get("ret") != 0:
                _weixin_state["qr_login_in_progress"] = False
                _weixin_state["last_error"] = f"获取二维码失败: {data.get('msg', '未知错误')} (ret={data.get('ret')})"
                return {"ok": False, "error": _weixin_state["last_error"]}
                
            qrcode_token = data.get("qrcode", "")
            qrcode_url_raw = data.get("qrcode_img_content", "")
            _weixin_state["qrcode_token"] = qrcode_token
            _weixin_state["qrcode_url"] = qrcode_url_raw
                
            # 生成 QR 码图片 (base64 PNG) — 兼容 qrcode v7 和 v8
            qrcode_img_b64 = ""
            try:
                import qrcode as _qr, io as _io, base64 as _b64
                if hasattr(_qr, 'make'):
                    # qrcode v8+ API
                    img = _qr.make(qrcode_url_raw)
                else:
                    # qrcode v7 API
                    qr = _qr.QRCode(box_size=6, border=2)
                    qr.add_data(qrcode_url_raw)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                buf = _io.BytesIO()
                img.save(buf, format="PNG")
                qrcode_img_b64 = "data:image/png;base64," + _b64.b64encode(buf.getvalue()).decode()
            except Exception:
                pass
                
            return {"ok": True, "qrcode_url": qrcode_img_b64, "qrcode_token": qrcode_token, "raw_url": qrcode_url_raw}
    except Exception as e:
        _weixin_state["qr_login_in_progress"] = False
        _weixin_state["last_error"] = str(e)
        return {"ok": False, "error": str(e)}


@app.get("/api/weixin/qr-poll")
async def weixin_qr_poll():
    """轮询 QR 码扫描状态"""
    if not _weixin_state["qrcode_token"]:
        return {"status": "idle", "message": "未发起登录"}
    
    try:
        import aiohttp
        qrcode = _weixin_state["qrcode_token"]
        base_url = _weixin_state["base_url"]
        async with aiohttp.ClientSession() as session:
            async def _poll_get():
                async with session.get(
                    f"{base_url}/ilink/bot/get_qrcode_status?qrcode={qrcode}",
                    headers={"iLink-App-Id": "bot", "iLink-App-ClientVersion": "131584"},
                ) as resp:
                    return await resp.text()
            raw = await asyncio.wait_for(_poll_get(), timeout=35)
            data = json.loads(raw)
            print(f"[MemOmics] qr-poll: status={data.get('status')}, ret={data.get('ret')}, keys={list(data.keys())[:8]}", flush=True)
            status = data.get("status", "unknown")
            ret_code = data.get("ret")
            if ret_code is not None and ret_code != 0:
                return {"status": "error", "message": data.get("msg", "API error")}
                
            if status == "wait":
                return {"status": "waiting", "message": "等待扫码..."}
            elif status == "scaned":
                return {"status": "scanned", "message": "已扫码，请在微信里确认登录"}
            elif status == "scaned_but_redirect":
                redirect_host = data.get("redirect_host", "") or data.get("redirecthost", "")
                if redirect_host:
                    _weixin_state["base_url"] = f"https://{redirect_host.rstrip('/')}"
                    _save_weixin_persist()
                return {"status": "scanned", "message": "已扫码，正在重定向..."}
            elif status == "confirmed":
                token = data.get("bot_token", "")
                account_id = data.get("ilink_bot_id", "")
                user_id = data.get("ilink_user_id", "")
                _weixin_state["token"] = token
                _weixin_state["account_id"] = account_id
                _weixin_state["connected"] = True
                _weixin_state["qr_login_in_progress"] = False
                _weixin_state["qrcode_token"] = ""
                _weixin_state["chat_id"] = (user_id + "@im.wechat") if user_id and "@" not in user_id else (user_id or account_id)  # 优先用用户微信ID
                base_url_new = data.get("baseurl", "")
                if base_url_new:
                    _weixin_state["base_url"] = base_url_new.rstrip("/")
                print(f"[MemOmics] QR confirmed: account={account_id[:20] if account_id else 'empty'}, user={user_id[:20] if user_id else 'empty'}", flush=True)
                _save_weixin_persist()
                try:
                    _start_weixin_poll()  # 启动 Hermes WeixinAdapter
                except Exception as e:
                    print(f"[MemOmics] 启动微信适配器异常: {e}", flush=True)
                return {"status": "connected", "message": f"已连接! 账号: {account_id[:12]}...", "account_id": account_id}
            elif status == "expired":
                _weixin_state["qr_login_in_progress"] = False
                _weixin_state["qrcode_token"] = ""
                return {"status": "expired", "message": "二维码已过期，请重新获取"}
            else:
                    return {"status": "unknown", "message": f"未知状态: {status}"}
    except asyncio.TimeoutError:
        return {"status": "waiting", "message": "等待扫码..."}
    except Exception as e:
        print(f"[MemOmics] qr-poll 异常: {e}", flush=True)
        return {"status": "error", "message": str(e) or repr(e)}


@app.post("/api/weixin/test")
async def weixin_test():
    """测试微信消息推送"""
    if not _weixin_state["connected"]:
        return {"ok": False, "error": "微信未连接"}
    ok = await _send_weixin_progress("🎉 MemOmics 微信推送测试成功! 时间: " + datetime.now().strftime("%H:%M:%S"))
    return {"ok": ok, "error": "" if ok else "发送失败"}

@app.post("/api/weixin/disconnect")
async def weixin_disconnect():
    """断开微信连接 — 清除内存状态并持久化到磁盘，重启后不再自动重连"""
    global _weixin_state
    _stop_weixin_poll()  # 先停止轮询，再清空状态
    _weixin_state["connected"] = False
    _weixin_state["token"] = ""
    _weixin_state["account_id"] = ""
    _weixin_state["chat_id"] = ""
    _weixin_state["context_token"] = ""
    _weixin_state["qr_login_in_progress"] = False
    _weixin_state["qrcode_token"] = ""
    _weixin_state["last_error"] = ""
    _save_weixin_persist()  # 持久化空状态，确保重启后不会自动重连
    return {"ok": True}


async def _send_weixin_progress(message: str) -> bool:
    """向微信发送进度消息 — 使用 Hermes 原生 WeixinAdapter.send()（带节流+熔断）"""
    if _weixin_adapter is None:
        return False
    if not _gate_weixin_send(message, min_interval=2.0):
        _WEIXIN_SEND_GATE["dropped"] += 1
        return False
    try:
        chat_id = _weixin_state.get("chat_id") or _weixin_last_user_id or _weixin_state["account_id"]
        # Ensure @im.wechat suffix for user IDs
        if chat_id and "@" not in chat_id:
            chat_id = chat_id + "@im.wechat"
        result = await _weixin_adapter.send(chat_id, message)
        err = getattr(result, 'error', '') or ''
        if hasattr(result, 'error') and result.error and 'session' in str(result.error).lower():
            _weixin_state["connected"] = False
            _weixin_state["last_error"] = "微信会话已过期，请重新扫码"
            print(f"[MemOmics] 微信会话过期: {result.error}", flush=True)
            _wx_fail_backoff(str(err), time.monotonic())
            return False
        ok = result.success if hasattr(result, 'success') else bool(result)
        if ok:
            _WEIXIN_SEND_GATE["last_ok_ts"] = time.monotonic()
            _WEIXIN_SEND_GATE["last_text"] = message
        else:
            _wx_fail_backoff(str(err), time.monotonic())
        return ok
    except Exception as e:
        _wx_fail_backoff(str(e), time.monotonic())
        return False


async def _send_weixin_image(image_path: str, caption: str = "") -> bool:
    """向微信发送本地图片 — 使用 Hermes 原生 WeixinAdapter.send_image_file()"""
    if _weixin_adapter is None:
        return False
    if not os.path.isfile(image_path):
        print(f"[MemOmics] 微信图片不存在: {image_path}", flush=True)
        return False
    if not _gate_weixin_send(image_path, min_interval=5.0, dedup_window=60.0):
        return False
    try:
        chat_id = _weixin_state.get("chat_id") or _weixin_last_user_id or _weixin_state["account_id"]
        if chat_id and "@" not in chat_id:
            chat_id = chat_id + "@im.wechat"
        result = await _weixin_adapter.send_image_file(chat_id, image_path, caption=caption)
        err = getattr(result, 'error', '') or ''
        ok = result.success if hasattr(result, 'success') else bool(result)
        if ok:
            _WEIXIN_SEND_GATE["last_ok_ts"] = time.monotonic()
            _WEIXIN_SEND_GATE["last_text"] = image_path
        else:
            _wx_fail_backoff(str(err), time.monotonic())
        return ok
    except Exception as e:
        _wx_fail_backoff(str(e), time.monotonic())
        return False


async def _send_weixin_document(file_path: str, caption: str = "") -> bool:
    """向微信发送文件 — 使用 Hermes 原生 WeixinAdapter.send_document()"""
    if _weixin_adapter is None:
        return False
    if not os.path.isfile(file_path):
        print(f"[MemOmics] 微信文件不存在: {file_path}", flush=True)
        return False
    if not _gate_weixin_send(file_path, min_interval=5.0, dedup_window=60.0):
        return False
    try:
        chat_id = _weixin_state.get("chat_id") or _weixin_last_user_id or _weixin_state["account_id"]
        if chat_id and "@" not in chat_id:
            chat_id = chat_id + "@im.wechat"
        result = await _weixin_adapter.send_document(chat_id, file_path, caption=caption)
        err = getattr(result, 'error', '') or ''
        ok = result.success if hasattr(result, 'success') else bool(result)
        if ok:
            _WEIXIN_SEND_GATE["last_ok_ts"] = time.monotonic()
            _WEIXIN_SEND_GATE["last_text"] = file_path
        else:
            _wx_fail_backoff(str(err), time.monotonic())
        return ok
    except Exception as e:
        _wx_fail_backoff(str(e), time.monotonic())
        return False


async def _send_weixin_important(message: str, chat_id_override: str = None, max_wait: float = 120.0) -> bool:
    """重要消息（最终回复/错误通知/手动发送）：不被节流丢弃。
    若处于 iLink 熔断期，等待冷却结束后再发送（最多 max_wait 秒）。"""
    if _weixin_adapter is None:
        return False
    deadline = time.monotonic() + max_wait
    while True:
        now = time.monotonic()
        if now >= _WEIXIN_SEND_GATE["cooldown_until"]:
            break
        if now >= deadline:
            print(f"[MemOmics] 微信重要消息等待熔断超时，放弃发送", flush=True)
            return False
        await asyncio.sleep(min(5.0, _WEIXIN_SEND_GATE["cooldown_until"] - now))
    try:
        chat_id = chat_id_override or _weixin_state.get("chat_id") or _weixin_last_user_id or _weixin_state["account_id"]
        if chat_id and "@" not in chat_id:
            chat_id = chat_id + "@im.wechat"
        result = await _weixin_adapter.send(chat_id, message)
        err = getattr(result, 'error', '') or ''
        ok = result.success if hasattr(result, 'success') else bool(result)
        if ok:
            _WEIXIN_SEND_GATE["last_ok_ts"] = time.monotonic()
            _WEIXIN_SEND_GATE["last_text"] = message
        else:
            _wx_fail_backoff(str(err), time.monotonic())
        return ok
    except Exception as e:
        _wx_fail_backoff(str(e), time.monotonic())
        return False


def _weixin_push_image(image_path: str, caption: str = "", loop=None):
    """线程安全地向微信推送图片"""
    if not _weixin_state.get("connected") or not _weixin_state.get("token"):
        return
    try:
        if loop is not None:
            asyncio.run_coroutine_threadsafe(_send_weixin_image(image_path, caption), loop)
        else:
            try:
                l = asyncio.get_running_loop()
                asyncio.run_coroutine_threadsafe(_send_weixin_image(image_path, caption), l)
            except RuntimeError:
                pass
    except Exception:
        pass


def _weixin_push_document(file_path: str, caption: str = "", loop=None):
    """线程安全地向微信推送文件"""
    if not _weixin_state.get("connected") or not _weixin_state.get("token"):
        return
    try:
        if loop is not None:
            asyncio.run_coroutine_threadsafe(_send_weixin_document(file_path, caption), loop)
        else:
            try:
                l = asyncio.get_running_loop()
                asyncio.run_coroutine_threadsafe(_send_weixin_document(file_path, caption), l)
            except RuntimeError:
                pass
    except Exception:
        pass


# --- 微信双向消息轮询 ---

_weixin_msg_store = []       # 最近消息列表（供前端拉取和 WS 推送）
_weixin_seen_ids = set()     # 已处理消息 ID 去重
_weixin_sync_buf = ""        # iLink 增量轮询 sync_buf
_weixin_poll_task = None     # 后台轮询 asyncio.Task
_weixin_adapter = None
_weixin_last_user_id = ""     # Last user who sent a message      # Hermes 原生 WeixinAdapter 实例
_MAX_WEIXIN_MSGS = 200
_WEIXIN_MSGS_FILE = os.path.join(HERMES_HOME_DIR, "runtime", "weixin_messages.json")

# 2026-08-14: 跨入口共享去重 — server 轮询(_weixin_poll_loop)与 Hermes 适配器回调
# (_hermes_weixin_message_handler) 各自拉同一条消息时，只处理一次，防双会话/双回复。
_WEIXIN_SHARED_SEEN = set()
_WEIXIN_SHARED_SEEN_MAX = 5000


def _weixin_mark_seen(msg_id) -> bool:
    """跨入口去重：未处理过返回 True 并登记；已处理返回 False。无 ID 不去重。"""
    global _WEIXIN_SHARED_SEEN
    if not msg_id:
        return True
    key = str(msg_id)
    if key in _WEIXIN_SHARED_SEEN:
        return False
    _WEIXIN_SHARED_SEEN.add(key)
    if len(_WEIXIN_SHARED_SEEN) > _WEIXIN_SHARED_SEEN_MAX:
        _WEIXIN_SHARED_SEEN = set(list(_WEIXIN_SHARED_SEEN)[-_WEIXIN_SHARED_SEEN_MAX // 2:])
    return True


def _normalize_weixin_sender(sender_id: str) -> str:
    """统一 sender_id 格式（补齐 @im.wechat 后缀），防双入口格式差异建出双会话。"""
    sid = (sender_id or "").strip()
    if sid and "@" not in sid:
        sid = sid + "@im.wechat"
    return sid


def _append_weixin_msg(wx_msg: dict):
    """追加微信消息到 store 并持久化（2026-08-14：防重启丢历史，前端刷新可见）。"""
    _weixin_msg_store.append(wx_msg)
    if len(_weixin_msg_store) > _MAX_WEIXIN_MSGS:
        _weixin_msg_store[:] = _weixin_msg_store[-_MAX_WEIXIN_MSGS:]
    try:
        os.makedirs(os.path.dirname(_WEIXIN_MSGS_FILE), exist_ok=True)
        with open(_WEIXIN_MSGS_FILE, "w", encoding="utf-8") as f:
            json.dump(_weixin_msg_store[-_MAX_WEIXIN_MSGS:], f, ensure_ascii=False)
    except Exception:
        pass  # 持久化失败不影响实时推送


def _load_weixin_msg_store():
    """启动时恢复微信消息历史。"""
    global _weixin_msg_store
    try:
        if os.path.isfile(_WEIXIN_MSGS_FILE):
            with open(_WEIXIN_MSGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                _weixin_msg_store = data
    except Exception:
        _weixin_msg_store = []


_load_weixin_msg_store()

# === Agent 循环检测器（2026-08-14 修复终端监控死循环）===
# 场景：agent 在长任务（如 git 依赖安装）中陷入
# "继续监控 → tail 日志 → 仍在进行 → 继续监控" 的无限循环，
# 上下文不断膨胀、注意力崩溃，stall watchdog 因 agent "一直在动" 无法触发。
# 检测两类循环，命中后通过 Hermes 原生 _pending_steer 通道注入强制收尾提示：
#   A. 工具调用循环：最近 8 次调用中 ≥6 对是同工具 + 相似命令
#   B. 重复表述循环：最近 8 个回合文本片段中 ≥6 对高度相似
from difflib import SequenceMatcher as _SeqMatcher
import threading as _threading_mod

_LOOP_SIG_TOOLS = {"terminal", "execute_code", "execute_python", "execute_r", "bash", "shell"}

# 2026-08-24: 循环检测豁免——以下工具连续调用是正常业务（连续读文献/查知识/出图），
# 不是失控死循环。尤其无参数调用（skill_view/summarize_paper/search_*）签名相似度高，
# 连续两篇文献就会被误报"工具调用循环"。这些工具不参与相似度累计。
_LOOP_EXEMPT_TOOLS = {
    "skill_view", "skill_search", "skill_list_by_domain",
    "summarize_paper", "literature_import", "kb_extract_from_paper", "extract_paper_knowledge",
    "search_knowledge", "search_knowledge_base", "search_papers", "search_papers_by_context",
    "web_search", "literature_search", "pubmed_search",
    "rail_review", "debate_analysis", "record_run", "check_env",
}


def _loop_tool_sig(tool_name: str, args) -> str:
    """提取工具调用的命令特征签名（用于相似度比较）。"""
    try:
        if tool_name in _LOOP_SIG_TOOLS and isinstance(args, dict):
            cmd = str(args.get("command", args.get("code", args.get("script", ""))))
            return re.sub(r"\s+", " ", cmd)[:150]
        if isinstance(args, dict):
            for _k in ("path", "file", "name", "query", "target", "url"):
                _v = args.get(_k)
                if isinstance(_v, str) and _v:
                    return re.sub(r"\s+", " ", _v)[:120]
    except Exception:
        pass
    return ""


# 写文件类调用（出图/导出）的输出目标文件名 — 用于"逐张出图"豁免：
# 两次调用命令相似但输出文件不同 = 正常批量出图，不算循环。
_OUT_TARGET_RE = re.compile(r"""["']([^"']+\.(?:png|jpe?g|pdf|svg|tiff|bmp|csv|tsv|rds|RData|html))["']""")


def _loop_out_target(sig: str) -> str:
    """提取签名里的输出文件名（无则空串）。"""
    if not sig:
        return ""
    try:
        _m = _OUT_TARGET_RE.search(sig)
        return _m.group(1) if _m else ""
    except Exception:
        return ""


def _sig_has_progress(sg1: str, sg2: str) -> bool:
    """签名间的数字在单调推进（step0→step1→step2）→ 正常批处理，不算循环。"""
    try:
        _n1 = [int(x) for x in re.findall(r"\d+", sg1)]
        _n2 = [int(x) for x in re.findall(r"\d+", sg2)]
        if not _n1 or not _n2:
            return False
        # 所有相同位置数字严格递增，或首个数字递增
        if len(_n1) == len(_n2) and all(b > a for a, b in zip(_n1, _n2)):
            return True
        return _n2[0] > _n1[0]
    except Exception:
        return False


def _loop_check(session, agent, event: str, tool_name: str = None, args=None, delta: str = None) -> bool:
    """循环检测主入口。event: 'delta' | 'tool_start' | 'turn_end'。返回 True=刚注入干预。"""
    try:
        if session is None:
            return False
        g = session.setdefault("_loop_guard", {
            "lock": _threading_mod.Lock(),
            "tool_hist": [],       # [(tool, sig, ts)]
            "text_buf": "",        # 当前回合累积文本
            "turn_texts": [],      # 最近 8 个回合文本片段
            "last_inject_ts": 0.0,
            "inject_count": 0,
        })
        with g["lock"]:
            now = time.time()
            triggered = None  # (reason, detail)

            if event == "delta" and delta:
                g["text_buf"] = (g["text_buf"] + str(delta))[-4000:]

            elif event == "tool_start":
                # 回合分段：上一段累积文本压栈
                if len(g["text_buf"]) >= 25:
                    g["turn_texts"].append(g["text_buf"][:800])
                    g["turn_texts"] = g["turn_texts"][-8:]
                g["text_buf"] = ""
                if tool_name in _LOOP_EXEMPT_TOOLS:
                    # 豁免工具不累计（但保留文本分段语义，text_buf 已清空）
                    return False
                _sig = _loop_tool_sig(tool_name, args)
                g["tool_hist"].append((tool_name or "", _sig, now))
                g["tool_hist"] = g["tool_hist"][-10:]
                _hist = g["tool_hist"][-8:]
                if len(_hist) >= 4:
                    _pairs = 0
                    for _i in range(len(_hist)):
                        for _j in range(_i + 1, len(_hist)):
                            _tn1, _sg1, _ = _hist[_i]
                            _tn2, _sg2, _ = _hist[_j]
                            if not _tn1 or _tn1 != _tn2:
                                continue
                            if not _sg1 and not _sg2:
                                _pairs += 1  # 同名无参数工具 = 重复
                            elif _sg1 and _sg2 and not _sig_has_progress(_sg1, _sg2) \
                                    and _SeqMatcher(None, _sg1, _sg2).ratio() > 0.72:
                                # 2026-08-14 出图/导出豁免：输出文件名不同 = 正常批量出图
                                _t1, _t2 = _loop_out_target(_sg1), _loop_out_target(_sg2)
                                if _t1 and _t2 and _t1 != _t2:
                                    continue
                                _pairs += 1
                    if _pairs >= 4:
                        triggered = ("工具调用循环", "连续执行相同/相似的监控命令")

            elif event == "turn_end":
                if len(g["text_buf"]) >= 25:
                    g["turn_texts"].append(g["text_buf"][:800])
                    g["turn_texts"] = g["turn_texts"][-8:]
                g["text_buf"] = ""
                _texts = [t for t in g["turn_texts"] if len(t) >= 30]
                if len(_texts) >= 4:
                    _pairs = 0
                    for _i in range(len(_texts)):
                        for _j in range(_i + 1, len(_texts)):
                            if _SeqMatcher(None, _texts[_i], _texts[_j]).ratio() > 0.6:
                                _pairs += 1
                    if _pairs >= 4:
                        triggered = ("重复表述循环", "连续多轮输出几乎相同的监控话术")

            if not triggered:
                return False
            _reason, _detail = triggered
            # 防抖：180s 内最多 1 次；单个用户回合累计 ≤3 次
            if g["inject_count"] >= 4:
                return False
            if now - g["last_inject_ts"] < 90:
                return False
            g["last_inject_ts"] = now
            g["inject_count"] += 1
            if _loop_inject_steer(session, agent, _reason, _detail):
                try:
                    _session_emit(session, {"type": "info",
                        "content": f"🔁 循环检测：{_reason}（{_detail}）。已注入强制收尾提示。",
                        "session_id": session["id"]})
                except Exception:
                    pass
                return True
            return False
    except Exception:
        return False


def _loop_inject_steer(session, agent, reason: str, detail: str) -> bool:
    """通过 Hermes 原生 _pending_steer 通道注入强制收尾提示（下一轮 LLM 调用前生效）。"""
    try:
        if agent is None and session is not None:
            agent = session.get("running_agent")
        if agent is None:
            return False
        _steer = (
            "【系统循环检测·强制干预】检测到你已连续多轮重复几乎相同的操作和表述（" + reason + "：" + detail + "）。"
            "判定为循环失控，请立即停止重复：\n"
            "1. 停止再执行重复的监控/查看动作；\n"
            "2. 若任务产物已生成（图/文件已保存、命令返回成功），直接视为完成，禁止再做任何验证/检查动作；"
            "仅当确实不知道结果时才做一次状态确认；\n"
            "3. 用 2-3 句话给用户明确结论：任务已完成 / 已失败 / 已卡死（附原因与产物路径）；\n"
            "4. 结束本轮回复，禁止再次执行重复动作。"
        )
        _lock = getattr(agent, "_pending_steer_lock", None)
        if _lock is not None:
            with _lock:
                agent._pending_steer = (agent._pending_steer + "\n" + _steer) if agent._pending_steer else _steer
        else:
            _cur = getattr(agent, "_pending_steer", "") or ""
            agent._pending_steer = (_cur + "\n" + _steer) if _cur else _steer
        return True
    except Exception:
        return False


# === 微信发送门控（2026-08-14 修复限流死循环）===
# 根因：agent 工具进度事件高频触发 _send_weixin_progress，iLink 限流后
# adapter 电路断路器反复开合，日志三行一组无限刷屏且消息永远发不出去。
# 修复：发送侧统一节流 + 去重 + 失败熔断（比 adapter 电路更长的静默期）。
_WEIXIN_SEND_GATE = {
    "cooldown_until": 0.0,     # 发送失败后的熔断截止（单调时钟）
    "last_ok_ts": 0.0,         # 上次成功发送时间
    "last_text": "",           # 上次发送文本（去重用）
    "last_fail_log_ts": 0.0,   # 上次失败日志时间（日志降噪）
    "dropped": 0,              # 节流丢弃计数（诊断）
}

def _gate_weixin_send(text: str = "", min_interval: float = 2.0, dedup_window: float = 5.0, reserve: bool = True) -> bool:
    """同步预检：是否允许本次微信发送。在 create_task 之前调用，避免海量任务堆积。
    - 熔断期内一律拒绝（静默）
    - 距上次发送不足 min_interval 秒拒绝
    - 相同文本在 dedup_window 秒内重复出现拒绝
    reserve=True 时通过即预占时间槽（供真正的发送函数在内部调用，
    保证并发 task 只有一个能实际发送）；外部快速预检用 reserve=False。
    """
    now = time.monotonic()
    g = _WEIXIN_SEND_GATE
    if now < g["cooldown_until"]:
        return False
    if now - g["last_ok_ts"] < min_interval:
        return False
    if text and text == g["last_text"] and now - g["last_ok_ts"] < dedup_window:
        return False
    if reserve:
        g["last_ok_ts"] = now  # 预占时间槽
    return True

def _wx_fail_backoff(err_text: str, now: float) -> None:
    """发送失败后的熔断：iLink 限流时静默更长时间（120s），
    日志 60s 内最多打一次，避免刷屏。"""
    g = _WEIXIN_SEND_GATE
    if "rate limited" in err_text or "cooldown active" in err_text or "限流" in err_text:
        g["cooldown_until"] = now + 120.0
        if now - g["last_fail_log_ts"] > 60.0:
            g["last_fail_log_ts"] = now
            print(f"[MemOmics] 微信被 iLink 限流，熔断 120s（期间静默丢弃进度推送）", flush=True)
    elif now - g["last_fail_log_ts"] > 60.0:
        g["last_fail_log_ts"] = now
        print(f"[MemOmics] 微信发送失败: {err_text[:150]}", flush=True)

_WEIXIN_WS_CLIENTS: set = set()  # 已订阅微信消息的 WebSocket 连接
_weixin_agent_enabled = True     # Agent 自动回复开关
_weixin_session_map: dict = {}    # {wx_user_id: {"session_id": ..., "last_ts": ...}}
_WEIXIN_SESSION_TTL = 43200       # 12 小时无消息自动新建会话


def _extract_text_from_weixin_msg(msg: dict) -> str:
    """从 iLink 消息格式中提取纯文本"""
    text_parts = []
    item_list = msg.get("item_list", [])
    if not item_list and msg.get("msg_text"):
        return str(msg["msg_text"])
    for item in item_list:
        if item.get("type") == 1:  # ITEM_TEXT
            text_item = item.get("text_item", {})
            text = text_item.get("text", "")
            if text:
                text_parts.append(text)
    return "".join(text_parts)




def _get_or_create_weixin_session(sender_id: str, sender_name: str) -> dict:
    """获取或创建微信用户关联的 MemOmics 会话（12h 超时自动新建）"""
    global _weixin_session_map
    sender_id = _normalize_weixin_sender(sender_id)
    now = time.time()
    entry = _weixin_session_map.get(sender_id)

    if entry:
        elapsed = now - entry.get("last_ts", 0)
        sid = entry["session_id"]
        if sid in _sessions and elapsed < _WEIXIN_SESSION_TTL:
            _weixin_session_map[sender_id]["last_ts"] = now
            _save_weixin_session_map()
            return _sessions[sid]

    date_str = datetime.now().strftime("%m-%d")
    title = f"📱 {date_str} {sender_name or sender_id[:12]}"
    session = _create_session(title)
    _weixin_session_map[sender_id] = {"session_id": session["id"], "last_ts": now}
    session["wx_sender_id"] = sender_id
    session["source"] = "weixin"
    _save_weixin_session_map()
    print(f"[MemOmics] 微信新会话: {sender_name} → {session['id']}", flush=True)
    return session


def _save_weixin_session_map():
    """持久化微信会话映射到 state.db"""
    try:
        db = _get_session_db()
        if db and hasattr(db, "_conn"):
            import json as _json
            db._conn.execute(
                "INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)",
                ("weixin_session_map", _json.dumps(_weixin_session_map, ensure_ascii=False))
            )
            db._conn.commit()
    except Exception:
        pass


def _rebuild_weixin_session_map():
    """启动时从 state.db 恢复微信会话映射"""
    global _weixin_session_map
    try:
        db = _get_session_db()
        if db and hasattr(db, "_conn"):
            import json as _json
            row = db._conn.execute(
                "SELECT value FROM kv WHERE key = ?", ("weixin_session_map",)
            ).fetchone()
            if row:
                stored = _json.loads(row[0])
                cleaned = {}
                for uid, entry in stored.items():
                    sid = entry.get("session_id", "")
                    if sid in _sessions:
                        cleaned[_normalize_weixin_sender(uid)] = entry
                    else:
                        print(f"[MemOmics] 微信映射清理: {uid} → {sid} 会话不存在", flush=True)
                _weixin_session_map = cleaned
                # Mark weixin sessions with source tag
                for uid, entry in cleaned.items():
                    sid = entry.get("session_id", "")
                    if sid in _sessions:
                        _sessions[sid]["source"] = "weixin"
                        _sessions[sid]["wx_sender_id"] = uid
                print(f"[MemOmics] 微信会话映射已恢复 ({len(cleaned)} 个)", flush=True)
    except Exception as e:
        print(f"[MemOmics] 恢复微信会话映射失败: {e}", flush=True)
        _weixin_session_map = {}


async def _process_weixin_agent_reply(sender_id: str, sender_name: str, text: str, context_token: str = ""):
    """用 MemOmics Agent 处理微信消息并自动回复（关联 MemOmics 会话，12h 超时自动新建）
    
    双通道展示：
    - 中间交互框：完整思考/分析过程（等同手动输入）
    - 右侧微信面板：简短阶段性汇报
    - 不限时，支持长任务
    - 离线继续跑（WebSocket断开不影响Agent执行）
    """
    global _weixin_msg_store, _WEIXIN_WS_CLIENTS

    # 获取或创建关联的 MemOmics 会话
    session = _get_or_create_weixin_session(sender_id, sender_name)
    sid = session["id"]

    # 把用户消息追加到会话
    session.setdefault("messages", []).append({"role": "user", "content": text, "time": datetime.now().strftime("%H:%M:%S"), "source": "weixin"})
    if len(session["messages"]) > 200:
        session["messages"] = session["messages"][-200:]
    session["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # state.db 由 Hermes 框架 _persist_session 自动写（双写修复：2026-08-13）

    # 更新会话标题（首次消息）
    phone_icon = "\U0001f4f1"
    if session.get("title", "").startswith(phone_icon) and len(session["messages"]) <= 2:
        short_text = text[:30].replace("\n", " ").strip()
        session["title"] = f"{phone_icon} {datetime.now().strftime('%m-%d')} {sender_name}: {short_text}"
        try:
            db = _get_session_db()
            if db and hasattr(db, "set_session_title"):
                db.set_session_title(sid, session["title"])
        except Exception:
            pass

    # 标记会话为运行状态
    session["running_agent"] = True
    session["running_task"] = "weixin_agent"

    # === 关键：把当前 WebSocket 连接绑到微信会话 ===
    # 让中间交互框能接收所有 thinking/progress/delta/tool 事件
    loop = asyncio.get_event_loop()
    if _WEIXIN_WS_CLIENTS:
        ws_ref = max(_WEIXIN_WS_CLIENTS, key=lambda ws: id(ws))
        session["ws_ref"] = ws_ref
        session["loop_ref"] = loop
        session["ws_attached"] = True

    # 发送初始事件（等同WebUI手动输入的体验）
    _session_emit(session, {"type": "thinking", "content": "正在理解您的问题...", "session_id": sid})
    _session_emit(session, {"type": "progress", "step": "thinking", "status": "pending", "detail": "正在理解您的问题", "ts": datetime.now().strftime("%H:%M:%S"), "session_id": sid})
    _session_emit(session, {"type": "agent_running", "session_id": sid})
    # 广播 session_update 让前端刷新列表（显示运行状态）
    session_update_msg = json.dumps({"type": "session_update", "session_id": sid, "is_running": True, "last_active": session["last_active"]}, ensure_ascii=False)
    for ws_cli in list(_WEIXIN_WS_CLIENTS):
        try:
            await ws_cli.send_text(session_update_msg)
        except Exception:
            pass


    try:
        # 分析级别检测
        from webui import enforcement as _enf3
        _level = _enf3.detect_analysis_level(text)
        _es = _enf3.get_enforcement(sid)
        _es.analysis_level = _level
        _es.results_dir = session.get("results_dir", "")
        
        # 用 WebUI 同款的 _create_agent 工厂函数
        agent = _create_agent(session_id=sid, session=session)

        # === 注册完整回调：中间框显示全过程 ===
        def _wx_tool_progress_cb(event_type, **kwargs):
            msg_text = kwargs.get("message", kwargs.get("text", ""))
            tool_name = kwargs.get("tool", "")
            percent = kwargs.get("percent", 0)
            _session_emit(session, {"type": "tool_progress", "tool": tool_name, "content": msg_text[:500] if msg_text else "", "percent": percent, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": sid})
            if msg_text and _weixin_adapter:
                try:
                    short_msg = "\u26a1 {}{}".format(f"{tool_name}: " if tool_name else "", msg_text[:80])
                    # 同步预检：熔断期/节流期直接丢弃，不再堆积 create_task（不预占时间槽）
                    if _gate_weixin_send(short_msg, min_interval=2.0, reserve=False):
                        asyncio.get_event_loop().create_task(_send_weixin_progress(short_msg))
                except Exception:
                    pass

        def _wx_tool_start_cb(tool_name, args=None):
            _session_emit(session, {"type": "tool_start", "tool": tool_name, "args": args or {}, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": sid})
            # P1-2(2026-09-23): 改动复核 —— 微信通道同样抓「改前」快照
            try:
                _snapshot_before_change(session, tool_name, args)
            except Exception:
                pass

        def _wx_tool_complete_cb(tool_name, result_str=""):
            _ev_wx = {"type": "tool_complete", "tool": tool_name, "result": result_str[:500], "ts": datetime.now().strftime("%H:%M:%S"), "session_id": sid}
            if tool_name == "debate_analysis":  # 2026-09-18: 附完整辩论归档，前端渲染过程表格
                try:
                    _deb_wx = _load_latest_debate(sid)
                    if _deb_wx.get("ok"):
                        _ev_wx["debate"] = _deb_wx
                    else:
                        _ev_wx["debate_error"] = _deb_wx.get("error", "")
                except Exception:
                    pass
            _session_emit(session, _ev_wx)
            # P1-2(2026-09-23): 改动复核 —— 微信通道（complete 回调没有 args）→ 结算该工具留下的全部待结算项
            try:
                _finalize_file_change(session, tool_name)
            except Exception:
                pass
            # 扫描新生成的图片 → 推送 new_figure 事件
            try:
                base = session.get("results_dir", "")
                if base and os.path.isdir(base):
                    for p in sorted(Path(base).rglob("*"), key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True):
                        if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.svg'}:
                            key = str(p)
                            if key not in getattr(_wx_tool_complete_cb, '_known', set()):
                                _wx_tool_complete_cb._known = getattr(_wx_tool_complete_cb, '_known', set()) | {key}
                                rel = str(p.relative_to(base)).replace(chr(92), "/")
                                fig = {"name": p.name, "rel_path": rel, "url": f"/api/results/{sid}/figure?path={rel}", "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%H:%M:%S")}
                                _session_emit(session, {"type": "new_figure", "figure": fig, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": sid})
                                # 📱 微信路径：新图片直接发微信
                                try:
                                    if _gate_weixin_send(str(p), min_interval=5.0, dedup_window=60.0, reserve=False):
                                        asyncio.get_event_loop().create_task(_send_weixin_image(str(p), f"🖼️ {p.name}"))
                                except Exception:
                                    pass
            except Exception:
                pass
            if _weixin_adapter:
                try:
                    # 同步预检：熔断期/节流期直接丢弃（不预占时间槽）
                    if _gate_weixin_send("\u2705 {} 完成".format(tool_name), min_interval=3.0, reserve=False):
                        asyncio.get_event_loop().create_task(_send_weixin_progress("\u2705 {} 完成".format(tool_name)))
                except Exception:
                    pass

        def _wx_delta_cb(delta_text):
            _session_emit(session, {"type": "delta", "content": str(delta_text), "session_id": sid})

        def _wx_reasoning_cb(reasoning_text):
            _session_emit(session, {"type": "reasoning", "content": str(reasoning_text), "session_id": sid})

        # 合并 enforcement + WeChat 回调（先保存 enforcement 回调）
        # 2026-08-17: 幂等合并（同上，防回调链无限叠加）
        if not getattr(agent, "_memomics_wx_cbs_merged", False):
            _enf_tool_start = agent.tool_start_callback
            _enf_tool_complete = agent.tool_complete_callback
            _enf_progress = agent.tool_progress_callback
            
            def _merged_tool_start(tool_call_id, tool_name, args):
                # P0-1(2026-08-13): 透传 enforcement 硬阻断返回值
                _block = None
                if _enf_tool_start:
                    try:
                        _block = _enf_tool_start(tool_call_id, tool_name, args)
                    except Exception:
                        pass
                _wx_tool_start_cb(tool_name, args)
                return _block
            
            def _merged_tool_complete(tool_call_id, tool_name, args, result):
                if _enf_tool_complete:
                    _enf_tool_complete(tool_call_id, tool_name, args, result)
                _wx_tool_complete_cb(tool_name, str(result)[:500] if result else "")
            
            def _merged_progress(event_type, **kwargs):
                if _enf_progress:
                    try: _enf_progress(event_type, **kwargs)
                    except Exception: pass
                try: _wx_tool_progress_cb(event_type, **kwargs)
                except Exception: pass
            
            agent.tool_start_callback = _merged_tool_start
            agent.tool_complete_callback = _merged_tool_complete
            agent.tool_progress_callback = _merged_progress
            agent._memomics_wx_cbs_merged = True
        agent.stream_delta_callback = _wx_delta_cb
        agent.reasoning_callback = _wx_reasoning_cb

        # 构建对话历史（最近 20 条）
        history = []
        for m in session.get("messages", [])[-20:]:
            if m.get("role") in ("user", "assistant"):
                history.append({"role": m["role"], "content": m.get("content", m.get("text", ""))})

        # === 不限时运行 ===（支持长任务，关机后Agent还在跑）
        def _do_run():
            # P1-13(2026-08-13): 微信 executor 线程内设置会话上下文（kernel 会话隔离）
            try:
                from memomics.bio_tools.debate_analysis import set_session_context
                _set_debate_session_context(session)
            except Exception:
                pass
            result = agent.run_conversation(text, conversation_history=history if history else None, task_id=session["id"])
            return result.get("final_response") or "" if isinstance(result, dict) else str(result)

        result_text = await loop.run_in_executor(None, _do_run)

        if result_text and result_text.strip():
            session["messages"].append({"role": "assistant", "content": result_text.strip(), "time": datetime.now().strftime("%H:%M:%S"), "source": "weixin-agent"})
            if len(session["messages"]) > 200:
                session["messages"] = session["messages"][-200:]
            session["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # state.db 由 Hermes 框架 _persist_session 自动写（双写修复：2026-08-13）

            _session_emit(session, {"type": "complete", "session_id": sid})
            _session_emit(session, {"type": "progress", "step": "complete", "status": "done", "detail": "回复已生成", "ts": datetime.now().strftime("%H:%M:%S"), "session_id": sid})

            wx_msg = {"id": str(int(time.time() * 1000)), "sender_id": _weixin_state["account_id"], "sender_name": "Agent", "text": result_text.strip(), "context_token": "", "ts": int(time.time()), "direction": "out"}
            _append_weixin_msg(wx_msg)
            # 2026-08-14: 先推前端（回复即时可见），微信发送/熔断等待不再阻塞 UI
            for ws_client in list(_WEIXIN_WS_CLIENTS):
                try:
                    await ws_client.send_text(json.dumps({"type": "weixin_message", "message": wx_msg}, ensure_ascii=False))
                except Exception:
                    pass

            if _weixin_adapter:
                try:
                    send_result = await _send_weixin_important(result_text.strip(), chat_id_override=sender_id)
                    print(f"[MemOmics] 微信Agent回复: success={send_result}", flush=True)
                except Exception as e:
                    print(f"[MemOmics] 微信Agent回复发送失败: {e}", flush=True)

            # 注意：不再发送 type=chat 消息 — delta 已实时流式渲染全部文本
            # state.db 中已持久化，重连后通过消息历史加载
            print(f"[MemOmics] 微信Agent回复 sent to={sender_name}: {result_text[:80]}...", flush=True)

    except Exception as e:
        print(f"[MemOmics] 微信Agent异常: {e}", flush=True)
        import traceback
        traceback.print_exc()
        _session_emit(session, {"type": "error", "session_id": sid, "message": str(e)})
        if _weixin_adapter:
            try:
                await _send_weixin_important(f"处理出错: {str(e)[:200]}", chat_id_override=sender_id, max_wait=60.0)
            except Exception:
                pass

    finally:
        session["running_agent"] = None
        session["running_task"] = None
        session["ws_attached"] = False
        session["ws_ref"] = None
        session["loop_ref"] = None
        session_update_msg = json.dumps({"type": "session_update", "session_id": sid, "is_running": False, "last_active": session["last_active"]}, ensure_ascii=False)
        for ws_cli in list(_WEIXIN_WS_CLIENTS):
            try:
                await ws_cli.send_text(session_update_msg)
            except Exception:
                pass


async def _weixin_poll_loop():
    """后台轮询微信消息，推送到 WebSocket 前端"""
    global _weixin_sync_buf
    import aiohttp
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', 'hermes-agent'))
    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', 'hermes-agent', 'gateway'))
    from platforms.weixin import _get_updates, _send_message
    poll_interval = 3
    if _weixin_state["qr_login_in_progress"]:
        poll_interval = 1  # QR 登录期间加速轮询

    while _weixin_state["connected"] or _weixin_state["qr_login_in_progress"]:
        try:
            # 如果有活跃的 QR 登录，先处理它
            if _weixin_state["qr_login_in_progress"] and _weixin_state["qrcode_token"]:
                # QR 登录期间只轮询状态，不获取消息
                await asyncio.sleep(poll_interval)
                continue

            if not _weixin_state["connected"] or not _weixin_state["token"]:
                await asyncio.sleep(poll_interval)
                continue

            token = _weixin_state["token"]
            base_url = _weixin_state["base_url"]
            account_id = _weixin_state["account_id"]

            try:
                async with aiohttp.ClientSession() as session:
                    result = await _get_updates(
                        session,
                        base_url=base_url,
                        token=token,
                        sync_buf=_weixin_sync_buf,
                        timeout_ms=15000,
                    )
            except Exception as e:
                if "Token验证失败" in str(e) or "token" in str(e).lower():
                    _weixin_state["connected"] = False
                    _weixin_state["token"] = ""
                    _save_weixin_persist()
                    print(f"[MemOmics] 微信 token 失效，已断开", flush=True)
                else:
                    print(f"[MemOmics] 微信轮询错误: {e}", flush=True)
                await asyncio.sleep(poll_interval)
                continue

            if result.get("ret") == 0:
                new_sync_buf = result.get("get_updates_buf", "")
                if new_sync_buf:
                    _weixin_sync_buf = new_sync_buf
                msgs = result.get("msgs") or []
                for msg in msgs:
                    msg_id = msg.get("message_id") or msg.get("msg_id") or ""
                    if msg_id and not _weixin_mark_seen(msg_id):
                        continue

                    sender_id = msg.get("from_user_id") or msg.get("from") or ""

                    sender_id = msg.get("from_user_id") or msg.get("from") or ""
                    sender_name = msg.get("from_user_name") or msg.get("sender_name") or sender_id
                    text = _extract_text_from_weixin_msg(msg)
                    context_token = msg.get("context_token") or ""
                    if not text and not msg.get("item_list"):
                        continue  # 跳过空消息（如图片、系统通知等）

                    ts = msg.get("create_time") or msg.get("msg_create_time") or int(time.time())
                    wx_msg = {
                        "id": msg_id or str(int(time.time() * 1000)),
                        "sender_id": sender_id,
                        "sender_name": sender_name[:60] if sender_name else "",
                        "text": text,
                        "context_token": context_token,
                        "ts": int(ts) if isinstance(ts, (int, float)) else int(time.time()),
                        "direction": "in",
                    }
                    _append_weixin_msg(wx_msg)

                    # 推送到已订阅 WebSocket 客户端
                    ws_event = json.dumps({"type": "weixin_message", "message": wx_msg})
                    dead = set()
                    for ws in list(_WEIXIN_WS_CLIENTS):
                        try:
                            await ws.send_text(ws_event)
                        except Exception:
                            dead.add(ws)
                    _WEIXIN_WS_CLIENTS -= dead

                    # 同步推送到 MemOmics 会话聊天面板
                    session = _get_or_create_weixin_session(sender_id, sender_name)
                    if session:
                        _session_emit(session, {
                            "type": "chat",
                            "session_id": session["id"],
                            "message": {"role": "user", "content": text, "source": "weixin"}
                        })
                    print(f"[MemOmics] 微信消息 from={sender_name}: {text[:80]}", flush=True)

                    # Agent 自动回复
                    if _weixin_agent_enabled and text.strip():
                        asyncio.create_task(_process_weixin_agent_reply(
                            sender_id, sender_name, text, context_token
                        ))

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[MemOmics] 微信轮询异常: {e}", flush=True)

        await asyncio.sleep(poll_interval)

    print("[MemOmics] 微信轮询已停止", flush=True)


def _start_weixin_poll():
    """启动 Hermes 原生 WeixinAdapter"""
    global _weixin_adapter
    if _weixin_adapter is not None:
        return
    asyncio.create_task(_connect_hermes_weixin_adapter())
    print("[MemOmics] Hermes 微信适配器启动中...", flush=True)


def _stop_weixin_poll():
    """停止 Hermes 原生 WeixinAdapter"""
    global _weixin_adapter
    if _weixin_adapter is not None:
        asyncio.create_task(_disconnect_hermes_weixin_adapter())

# ================================================================
# Hermes 原生 WeixinAdapter 集成
# ================================================================

def _build_weixin_platform_config():
    """用当前 _weixin_state 构建 Hermes PlatformConfig"""
    import sys as _sys
    _hermes_root = os.path.join(os.path.dirname(__file__), "..", "hermes-agent")
    _sys.path.insert(0, _hermes_root)
    from gateway.config import Platform, PlatformConfig
    return PlatformConfig(
        enabled=True,
        token=_weixin_state["token"],
        extra={
            "account_id": _weixin_state["account_id"],
            "base_url": _weixin_state.get("base_url", "https://ilinkai.weixin.qq.com"),
            "dm_policy": "pairing",
            "group_policy": "disabled",
            "send_chunk_delay_seconds": "1.5",
            "send_chunk_retries": "4",
        }
    )


async def _hermes_weixin_message_handler(event):
    """Hermes 消息回调 — 存储、推送、自动回复"""
    global _weixin_msg_store, _WEIXIN_WS_CLIENTS
    try:
        msg_id = event.message_id or str(int(time.time() * 1000))
        # 2026-08-14: 共享去重 — 轮询路径已处理过则跳过（防双会话/双回复）
        if not _weixin_mark_seen(msg_id):
            return
        sender_id = event.source.user_id or ""
        _weixin_last_user_id = sender_id
        sender_name = event.source.user_name or sender_id
        text = event.text or ""
        ctx_token = ""
        if event.raw_message and isinstance(event.raw_message, dict):
            ctx_token = event.raw_message.get("context_token", "")
        if ctx_token:
            _weixin_state["context_token"] = ctx_token
        if event.source.chat_id:
            _weixin_state["chat_id"] = event.source.chat_id
            _weixin_last_user_id = event.source.chat_id

        if not text and not (event.raw_message and isinstance(event.raw_message, dict) and event.raw_message.get("item_list")):
            return

        ts = int(time.time())
        wx_msg = {
            "id": msg_id,
            "sender_id": sender_id,
            "sender_name": sender_name[:60] if sender_name else "",
            "text": text,
            "context_token": ctx_token,
            "ts": ts,
            "direction": "in",
        }
        _append_weixin_msg(wx_msg)

        ws_event = json.dumps({"type": "weixin_message", "message": wx_msg})
        dead = set()
        for ws in list(_WEIXIN_WS_CLIENTS):
            try:
                await ws.send_text(ws_event)
            except Exception:
                dead.add(ws)
        _WEIXIN_WS_CLIENTS -= dead

        # 同步推送到 MemOmics 会话聊天面板
        session = _get_or_create_weixin_session(sender_id, sender_name)
        if session:
            # 重新绑定 ws_ref（每次消息都需要，因为上次 finally 清除过）
            if _WEIXIN_WS_CLIENTS:
                session["ws_ref"] = max(_WEIXIN_WS_CLIENTS, key=lambda ws: id(ws))
                session["loop_ref"] = asyncio.get_event_loop()
                session["ws_attached"] = True
            # 1) 通过 session 的 ws_ref 推送
            _session_emit(session, {
                "type": "chat",
                "session_id": session["id"],
                "message": {"role": "user", "content": text, "source": "weixin"}
            })
            # 2) 通过微信 WS 广播 session_update（让前端刷新会话列表）
            session_update = json.dumps({
                "type": "session_update",
                "session_id": session["id"],
                "title": session.get("title", ""),
                "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source": "weixin",
                "msg_count": len(session.get("messages", [])),
            }, ensure_ascii=False)
            dead = set()
            for ws_cli in list(_WEIXIN_WS_CLIENTS):
                try:
                    await ws_cli.send_text(session_update)
                except Exception:
                    dead.add(ws_cli)
            _WEIXIN_WS_CLIENTS -= dead
            # 更新 last_active
            session["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # state.db 由 Hermes 框架 _persist_session 自动写（双写修复：2026-08-13）

        print(f"[MemOmics] 微信消息 from={sender_name}: {text[:80]}", flush=True)

        if _weixin_agent_enabled and text.strip():
            asyncio.create_task(_process_weixin_agent_reply(
                sender_id, sender_name, text, ctx_token
            ))
    except Exception:
        import traceback
        traceback.print_exc()
    return None


async def _auto_reconnect_weixin():
    """服务启动时自动重连微信 — 使用已保存的 token"""
    global _weixin_adapter
    try:
        token = _weixin_state.get("token", "")
        account_id = _weixin_state.get("account_id", "")
        if not token:
            logger.info("[MemOmics] 微信自动重连: 无已保存 token，跳过")
            return
        
        logger.info(f"[MemOmics] 微信自动重连: 尝试恢复账号 {account_id[:16] if account_id else 'unknown'}...")
        
        # 等待 uvicorn 完全启动 (让事件循环就绪)
        await asyncio.sleep(2)
        
        # 调用 Hermes WeixinAdapter 连接
        await _connect_hermes_weixin_adapter()
        
        if _weixin_adapter and _weixin_state.get("connected"):
            logger.info("[MemOmics] 微信自动重连成功!")
        else:
            logger.warning("[MemOmics] 微信自动重连失败，token 可能已过期，请手动扫码")
            _weixin_state["connected"] = False
            _weixin_state["token"] = ""
            _save_weixin_persist()
    except Exception as e:
        logger.warning(f"[MemOmics] 微信自动重连异常: {e}")

async def _connect_hermes_weixin_adapter():
    """连接 Hermes 原生 WeixinAdapter"""
    global _weixin_adapter
    try:
        import sys as _sys
        _hermes_root = os.path.join(os.path.dirname(__file__), "..", "hermes-agent")
        _sys.path.insert(0, _hermes_root)
        from gateway.platforms.weixin import WeixinAdapter, check_weixin_requirements
        if not check_weixin_requirements():
            print("[MemOmics] 微信依赖缺失 (aiohttp/cryptography)", flush=True)
            return
        config = _build_weixin_platform_config()
        print(f"[MemOmics] adapter config: token={'YES' if config.token else 'NO'}, account={_weixin_state.get('account_id','')[:20]}", flush=True)
        _weixin_adapter = WeixinAdapter(config)
        _weixin_adapter.set_message_handler(_hermes_weixin_message_handler)
        ok = await _weixin_adapter.connect()
        print(f"[MemOmics] adapter connect result: {ok}", flush=True)
        if ok:
            print("[MemOmics] Hermes 微信适配器已连接", flush=True)
            _weixin_state["connected"] = True
            _save_weixin_persist()
        else:
            print("[MemOmics] Hermes 微信适配器连接失败", flush=True)
            _weixin_state["last_error"] = "Hermes 适配器连接失败"
            _weixin_adapter = None
    except Exception as e:
        print(f"[MemOmics] Hermes 微信适配器异常: {e}", flush=True)
        import traceback
        traceback.print_exc()
        _weixin_state["last_error"] = str(e)
        _weixin_adapter = None


async def _disconnect_hermes_weixin_adapter():
    """断开 Hermes 原生 WeixinAdapter"""
    global _weixin_adapter
    if _weixin_adapter is not None:
        try:
            await _weixin_adapter.disconnect()
        except Exception:
            pass
        _weixin_adapter = None
    _weixin_state["connected"] = False

    print("[MemOmics] Hermes 微信适配器已停止", flush=True)





@app.get("/api/weixin/messages")
async def weixin_messages(since: str = ""):
    """获取微信消息列表"""
    if since:
        # 返回 after 指定 ID 的新消息（按 ts 排序保证顺序）
        found = False
        result = []
        for m in _weixin_msg_store:
            if found:
                result.append(m)
            if m["id"] == since:
                found = True
        result.sort(key=lambda m: m.get("ts", 0))
        return {"messages": result}
    _recent = sorted(_weixin_msg_store[-50:], key=lambda m: m.get("ts", 0))
    return {"messages": _recent}  # 最近 50 条（按 ts 排序）


@app.post("/api/weixin/send")
async def weixin_send(body: dict = None):
    """向微信用户发送/回复消息 — 使用 Hermes 原生 WeixinAdapter"""
    global _weixin_msg_store
    if not body:
        return JSONResponse({"ok": False, "error": "请求体为空"}, status_code=400)
    if _weixin_adapter is None:
        return {"ok": False, "error": "微信未连接"}

    to_user = body.get("to", "") or body.get("sender_id", "") or _weixin_state.get("chat_id") or _weixin_state["account_id"]
    text = body.get("text", "").strip()
    if not text:
        return {"ok": False, "error": "消息不能为空"}

    try:
        result = await _send_weixin_important(text, chat_id_override=to_user)
        ok = bool(result)
        if ok:
            wx_msg = {
                "id": str(int(time.time() * 1000)),
                "sender_id": _weixin_state["account_id"],
                "sender_name": "我",
                "text": text,
                "context_token": _weixin_state.get("context_token", ""),
                "ts": int(time.time()),
                "direction": "out",
            }
            _append_weixin_msg(wx_msg)
            # 2026-08-14: 手动回复成功后实时推前端（之前要手动刷新才可见）
            ws_event = json.dumps({"type": "weixin_message", "message": wx_msg}, ensure_ascii=False)
            dead = set()
            for ws_cli in list(_WEIXIN_WS_CLIENTS):
                try:
                    await ws_cli.send_text(ws_event)
                except Exception:
                    dead.add(ws_cli)
            _WEIXIN_WS_CLIENTS -= dead
            return {"ok": True}
        else:
            return {"ok": False, "error": "发送失败"}
    except Exception as e:
        return {"ok": False, "error": str(e)}



@app.post("/api/weixin/send_image")
async def weixin_send_image(body: dict = None):
    """发送本地图片到微信（给 scripts/desktop_shot.py 这类本机工具用）。

    背景（2026-09-25）：/api/weixin/send 只能发文本，图片发送只存在于进程内
    （_send_weixin_image），于是「computer_use 截图 → 发微信」在纯聊天会话里没有出口：
    聊天会话不创建 results 目录，_scan_new_figures 也就扫不到图。这里补一个显式出口。

    安全：只允许已存在的图片文件（扩展名白名单），复用 _gate_weixin_send 的
    5 秒间隔 / 60 秒去重限流，发送目标沿用 _weixin_state 的会话（与文本一致）。
    """
    global _weixin_msg_store
    body = body or {}
    path = str(body.get("path", "") or "").strip()
    caption = str(body.get("caption", "") or "").strip()
    if not path:
        return JSONResponse({"ok": False, "error": "缺少 path"}, status_code=400)
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        return JSONResponse({"ok": False, "error": "只允许图片文件（png/jpg/jpeg/webp/gif），收到: %s" % (ext or "无扩展名")},
                            status_code=400)
    if not os.path.isfile(path):
        return JSONResponse({"ok": False, "error": "文件不存在: %s" % path}, status_code=404)
    if _weixin_adapter is None:
        return {"ok": False, "error": "微信未连接"}
    try:
        size = os.path.getsize(path)
    except OSError:
        size = -1
    print(f"[MemOmics] 微信发图: {path} ({size} 字节)", flush=True)
    ok = await _send_weixin_image(path, caption)
    if not ok:
        return {"ok": False, "error": "发送失败或被限流（5 秒间隔 / 60 秒去重）", "path": path}
    try:
        _append_weixin_msg({
            "id": str(int(time.time() * 1000)),
            "sender_id": _weixin_state["account_id"],
            "sender_name": "我",
            "text": "[图片] " + os.path.basename(path) + ((" — " + caption) if caption else ""),
            "context_token": _weixin_state.get("context_token", ""),
            "ts": int(time.time()),
            "direction": "out",
        })
    except Exception:
        pass
    return {"ok": True, "path": path, "bytes": size}


@app.get("/api/files")
async def list_files(path: str = ""):
    """列出目录文件 — 限制在 work/ 和 results/ 内"""
    if not path:
        # 展示根目录列表
        return {
            "path": "MemOmics 工作目录",
            "items": [
                {"name": "work", "path": WORK_DIR.replace("\\", "/"), "is_dir": True, "size": 0, "ext": "", "desc": "文献下载、用户文件"},
                {"name": "results", "path": RESULTS_DIR.replace("\\", "/"), "is_dir": True, "size": 0, "ext": "", "desc": "会话分析结果"},
            ]
        }
    # 安全检查: 只允许在 work/ 和 results/ 内浏览
    real_path = os.path.realpath(path)
    allowed = False
    for root in _BROWSE_ROOTS.values():
        if real_path.startswith(os.path.realpath(root)):
            allowed = True
            break
    if not allowed:
        return JSONResponse({"error": "只能浏览 work/ 和 results/ 目录"}, status_code=403)
    try:
        items = []
        for p in sorted(Path(path).iterdir(), key=lambda x: (not x.is_dir(), -x.stat().st_mtime)):
            if p.name.startswith(".") or p.name == "__pycache__":
                continue
            items.append({
                "name": p.name,
                "path": str(p).replace("\\", "/"),
                "is_dir": p.is_dir(),
                "size": p.stat().st_size if p.is_file() else 0,
                "ext": p.suffix.lower() if p.is_file() else "",
            })
        return {"path": str(path).replace("\\", "/"), "items": items}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# ============ 2026-09-17 文献导入提速：目录 PDF 计数缓存 ============
# 现象：点导入 → 选目录，每打开一层就要等几秒到几十秒。根因是列表接口每次都对该目录
# 做一次递归 os.walk 数 PDF（实测：扫整个磁盘分区单次 32.7s，扫项目目录 0.8s）。
# 现在改为：内存缓存 + 命中即返回；未命中时后台线程预热并立刻返回 pdf_count=null，
# 前端先渲染列表、再轮询 /api/lit/pdf_count 把数字补上（不阻塞浏览）。
_LIT_PDF_COUNT_CACHE = {}
_LIT_PDF_COUNT_TTL = 600.0        # 10 分钟内直接复用
_LIT_PDF_COUNT_BUDGET = 2.5       # 单次扫描时间预算（秒），超预算按已扫到的计数并标 partial
_LIT_PDF_COUNT_CAP = 5000
_LIT_PDF_COUNT_BUDGET_DEEP = 25.0   # 用户主动查数字时（/api/lit/pdf_count）给足预算，尽量精确
_LIT_PDF_COUNT_LOCK = _threading.Lock()
_LIT_PDF_COUNT_PENDING = set()


def _scan_pdf_count(root: str, budget: float = None) -> tuple:
    """迭代式扫描目录树数 PDF（os.scandir，比 os.walk 快）；受时间预算与上限约束。

    返回 (count, partial)：partial=True 表示没扫完（预算/上限触发），count 是下界。
    """
    budget = _LIT_PDF_COUNT_BUDGET if budget is None else float(budget)
    n, t0, partial = 0, time.time(), False
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for ent in it:
                    if ent.name.startswith("."):
                        continue
                    try:
                        if ent.is_dir(follow_symlinks=False):
                            stack.append(ent.path)
                        elif ent.name.lower().endswith(".pdf"):
                            n += 1
                            if n >= _LIT_PDF_COUNT_CAP:
                                return n, True
                    except Exception:
                        continue
        except Exception:
            continue
        if time.time() - t0 > budget:
            partial = True
            break
    return n, partial


def _lit_pdf_count_cached(path: str, wait: bool = False, budget: float = None):
    """取目录 PDF 数：缓存优先；未命中则（wait=False 时）后台预热并返回 None。

    wait=True 时同步扫描并按 budget 计时（默认浅预算 2.5s；用户主动查数字时用深预算）。
    partial（没扫完）的结果只短缓存 60s，等下次深扫覆盖。
    """
    key = os.path.realpath(path or MEMOMICS_DIR)
    now = time.time()
    with _LIT_PDF_COUNT_LOCK:
        hit = _LIT_PDF_COUNT_CACHE.get(key)
        if hit:
            _ttl = 60.0 if hit[2] else _LIT_PDF_COUNT_TTL
            if now - hit[1] < _ttl:
                return {"pdf_count": hit[0], "pdf_count_partial": bool(hit[2])}
        if not wait and key in _LIT_PDF_COUNT_PENDING:
            return {"pdf_count": None, "pdf_count_partial": False}
        _LIT_PDF_COUNT_PENDING.add(key)

    if wait:
        try:
            n, partial = _scan_pdf_count(key, budget)
        except Exception:
            n, partial = 0, False
        with _LIT_PDF_COUNT_LOCK:
            _LIT_PDF_COUNT_CACHE[key] = (n, time.time(), partial)
            _LIT_PDF_COUNT_PENDING.discard(key)
        return {"pdf_count": n, "pdf_count_partial": partial}

    def _warm():
        try:
            n, partial = _scan_pdf_count(key)
            with _LIT_PDF_COUNT_LOCK:
                _LIT_PDF_COUNT_CACHE[key] = (n, time.time(), partial)
        except Exception:
            pass
        finally:
            with _LIT_PDF_COUNT_LOCK:
                _LIT_PDF_COUNT_PENDING.discard(key)

    _threading.Thread(target=_warm, daemon=True).start()
    return {"pdf_count": None, "pdf_count_partial": False}


@app.get("/api/lit/pdf_count")
async def lit_pdf_count(path: str = ""):
    """文献导入：只取"本目录 PDF 数量"（缓存优先，未命中最多扫 2.5s）。

    前端在浏览列表渲染后轮询它补数字，避免浏览被递归扫描阻塞。
    """
    real = os.path.realpath(path or MEMOMICS_DIR)
    if not os.path.isdir(real):
        return {"count": 0, "partial": False, "path": real.replace("\\", "/")}
    # 用户主动要这个数字时给足预算（浏览列表早已渲染完成，不阻塞任何交互）
    r = await asyncio.to_thread(_lit_pdf_count_cached, real, True, _LIT_PDF_COUNT_BUDGET_DEEP)
    return {"count": r.get("pdf_count") or 0, "partial": bool(r.get("pdf_count_partial")),
            "path": real.replace("\\", "/")}


@app.get("/api/lit/browse")
async def lit_browse(path: str = ""):
    """文献导入的目录浏览（批H 2026-08-16，跨平台）。

    - 空 path → 默认打开 MemOmics 安装目录（MEMOMICS_DIR），首项为系统根虚拟项
      （Windows:「💻 此电脑」→ __drives__ 盘符列表；Linux:「💻 根目录 /」→ /）
    - path == "__drives__"（仅 Windows）→ 盘符列表
    - 其他 → 该目录下的子目录 + PDF 文件
    - parent 由服务端按平台计算（Windows 盘符根/ Linux / 之上无 parent），
      前端直接用 d.parent 做「返回上一级」，不做任何平台路径字符串拼装。
    仅本机回环服务使用（文献导入需要访问用户任意位置的 PDF）。
    """
    is_win = os.name == "nt"

    # 系统根虚拟项
    root_virtual = ({"name": "💻 此电脑", "path": "__drives__", "is_dir": True, "virtual": True}
                    if is_win else
                    {"name": "💻 根目录 /", "path": "/", "is_dir": True, "virtual": True})
    if not path:
        root_dir = MEMOMICS_DIR
        try:
            items = [root_virtual]
            for p in sorted(Path(root_dir).iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if p.name.startswith(".") or p.name == "__pycache__":
                    continue
                try:
                    is_dir = p.is_dir()
                except Exception:
                    continue
                if not is_dir and p.suffix.lower() != ".pdf":
                    continue
                items.append({
                    "name": p.name,
                    "path": str(p).replace("\\", "/"),
                    "is_dir": is_dir,
                    "size": p.stat().st_size if not is_dir else 0,
                    "ext": p.suffix.lower() if not is_dir else "",
                })
            return {"path": root_dir.replace("\\", "/") + "  (MemOmics 安装目录)",
                    "items": items, "is_root": True, "parent": None, "platform": os.name,
                    **_lit_pdf_count_cached(root_dir)}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)
    if path == "__drives__" and is_win:
        drives = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            root = f"{letter}:\\"
            if os.path.exists(root):
                drives.append({"name": f"{letter}:\\", "path": f"{letter}:/", "is_dir": True})
        return {"path": "💻 此电脑 — 选择盘符", "items": drives, "is_root": True,
                "parent": "", "platform": os.name}
    real = os.path.realpath(path)
    if not os.path.isdir(real):
        return JSONResponse({"error": f"目录不存在: {path}"}, status_code=400)
    # 服务端计算上一级（跨平台）
    if is_win:
        norm = os.path.normpath(real).replace("\\", "/")
        if norm.endswith("/"):
            norm = norm.rstrip("/")
        drive_root = bool(re.fullmatch(r"[A-Za-z]:", norm))
        parent = "" if drive_root else (os.path.dirname(real).replace("\\", "/") or "")
    else:
        parent = "" if os.path.realpath(path) == "/" else (os.path.dirname(os.path.realpath(path)) or "/")
    try:
        items = [root_virtual]
        # 2026-09-17: Path.iterdir()+stat 改为 os.scandir（每个条目省一次 stat 系统调用，
        # 大目录/慢盘差异明显）；排序语义保持不变（目录在前，然后按名字小写）。
        _rows = []
        with os.scandir(real) as _it:
            for _e in _it:
                if _e.name.startswith(".") or _e.name in ("$RECYCLE.BIN", "System Volume Information", "__pycache__"):
                    continue
                try:
                    _is_dir = _e.is_dir()
                except Exception:
                    continue
                _suf = os.path.splitext(_e.name)[1].lower()
                if not _is_dir and _suf != ".pdf":
                    continue
                try:
                    _size = 0 if _is_dir else _e.stat().st_size
                except Exception:
                    _size = 0
                _rows.append((not _is_dir, _e.name.lower(), {
                    "name": _e.name,
                    "path": os.path.join(real, _e.name).replace("\\", "/"),
                    "is_dir": _is_dir,
                    "size": _size,
                    "ext": "" if _is_dir else _suf,
                }))
        _rows.sort(key=lambda r: (r[0], r[1]))
        items.extend([r[2] for r in _rows])
        return {"path": real.replace("\\", "/"), "items": items, "is_root": False,
                "parent": parent, "platform": os.name, **_lit_pdf_count_cached(real)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/file/read")
async def file_read(path: str = ""):
    """读取文件内容（限制在 work/results/项目内，防任意文件读取）"""
    try:
        from webui.security import resolve_within_roots, UnsafePathError
        _p = resolve_within_roots(path, [WORK_DIR, RESULTS_DIR, MEMOMICS_DIR])
        path = str(_p)
        size = os.path.getsize(path)
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read(200000)  # 最多 200KB
        return {"path": path, "content": content, "size": size, "truncated": size > 200000}
    except UnsafePathError as e:
        return JSONResponse({"error": str(e)}, status_code=403)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/file/download")
async def download_file(path: str):
    """下载文件（限制在 work/results/项目内，防任意文件下载）"""
    try:
        from webui.security import resolve_within_roots, UnsafePathError
        path = str(resolve_within_roots(path, [WORK_DIR, RESULTS_DIR, MEMOMICS_DIR]))
    except UnsafePathError as e:
        return JSONResponse({"error": str(e)}, status_code=403)
    if not os.path.isfile(path):
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(path, filename=os.path.basename(path))


# ============ P5 结果文件直读（2026-09-22）：预览 / 原始字节 / 系统打开 ============
# 用户需求：分析结果里的文件要能直接点开看（txt/md/csv/excel/word/pdf/图片…），
# 并且按时间倒序、最新的排最上面。转换全部在服务端做（webui/preview_convert.py），
# 不引前端 CDN、不依赖随包环境缺的库。
_PREVIEW_ROOTS = [WORK_DIR, RESULTS_DIR, MEMOMICS_DIR]


def _p5_lang_of(lang) -> str:
    """P5.1：请求语言（zh 默认 / en）。只影响预览与打开接口里的固定文案。"""
    return "en" if str(lang or "").strip().lower().startswith("en") else "zh"


# P6-2：界面语言（前端点中/英切换时会 POST /api/ui/lang 告知一次）。
# 用来让**后端自己生成、直接显示在界面上**的文案也跟着切（如 P4 的确定性弹窗、ask_user 弹窗提示）。
# 默认 zh：没告知过就维持原样，不会影响任何既有行为。
_UI_LANG_STATE = {"lang": "zh"}


def _ui_lang() -> str:
    """当前界面语言（zh / en）。"""
    return "en" if str(_UI_LANG_STATE.get("lang") or "zh").strip().lower().startswith("en") else "zh"


def _p5_t(lang, zh, en, *args) -> str:
    s = en if _p5_lang_of(lang) == "en" else zh
    if args:
        try:
            return s % args
        except Exception:
            return s
    return s


# ---- 「已查看」标记（P5.1）------------------------------------------------
# 存 <结果目录>/.viewed.json：点开头，list_results 扫描时自动忽略，不污染结果目录。
# key = 结果目录内的相对路径（正斜杠），value = 首次标记时间戳。
_VIEWED_FILE = ".viewed.json"


def _viewed_load(base: str) -> dict:
    try:
        with open(os.path.join(base, _VIEWED_FILE), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _viewed_save(base: str, data: dict) -> None:
    p = os.path.join(base, _VIEWED_FILE)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, p)
_SYSOPEN_ENABLED = (os.environ.get("MEMOMICS_SYSOPEN", "1").strip().lower()
                    not in ("0", "false", "no", "off"))

_FILE_MIME = {
    ".md": "text/markdown; charset=utf-8", ".markdown": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8", ".log": "text/plain; charset=utf-8",
    ".csv": "text/csv; charset=utf-8", ".tsv": "text/tab-separated-values; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".jsonl": "application/x-ndjson; charset=utf-8",
    ".yaml": "text/yaml; charset=utf-8", ".yml": "text/yaml; charset=utf-8",
    ".pdf": "application/pdf", ".svg": "image/svg+xml", ".png": "image/png",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
    ".bmp": "image/bmp", ".ico": "image/x-icon", ".tif": "image/tiff", ".tiff": "image/tiff",
    ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".ipynb": "application/x-ipynb+json",
}


def _guess_media(path: str) -> str:
    import mimetypes
    ext = os.path.splitext(path)[1].lower()
    if ext in _FILE_MIME:
        return _FILE_MIME[ext]
    mt, _ = mimetypes.guess_type(path)
    if not mt:
        return "application/octet-stream"
    if mt.startswith("text/") and "charset" not in mt:
        return mt + "; charset=utf-8"
    return mt


def _preview_resolve(path: str, lang: str = "zh"):
    """校验路径（限制在 work/results/项目根内，防任意文件读取）。返回 (full, err_response)"""
    from webui.security import resolve_within_roots, UnsafePathError
    if not path:
        return "", JSONResponse({"error": _p5_t(lang, "缺少 path 参数", "Missing path parameter")}, status_code=400)
    try:
        full = str(resolve_within_roots(path, _PREVIEW_ROOTS))
    except UnsafePathError as e:
        return "", JSONResponse({"error": str(e)}, status_code=403)
    except Exception as e:
        return "", JSONResponse({"error": str(e)}, status_code=400)
    if not os.path.exists(full):
        return "", JSONResponse({"error": _p5_t(lang, "文件不存在：%s", "File not found: %s",
                                               os.path.basename(full))}, status_code=404)
    return full, None


@app.get("/api/file/preview")
async def file_preview(path: str = "", sheet: str = "", max_rows: int = 0, max_cols: int = 0,
                       lang: str = "zh"):
    """把任意结果文件转成 WebUI 能直接显示的结构（只读）。

    返回 kind：text / code / markdown / table / excel / word / notebook / pdf / image /
    html / binary / missing，附 meta、download_url、raw_url。
    """
    import functools
    from urllib.parse import quote
    full, err = _preview_resolve(path, lang)
    if err is not None:
        return err
    try:
        from webui import preview_convert as _pc
    except Exception as e:
        return JSONResponse({"error": _p5_t(lang, "预览模块不可用：%s", "Preview module unavailable: %s", e)},
                            status_code=500)
    if os.path.isdir(full):
        return JSONResponse({"kind": "missing", "meta": _pc.file_meta(full),
                             "error": _p5_t(lang, "这是一个目录，不能预览", "This is a directory and cannot be previewed")},
                status_code=200)
    kw = {"lang": _p5_lang_of(lang)}
    if sheet:
        kw["sheet"] = sheet
    if max_rows and int(max_rows) > 0:
        kw["max_rows"] = min(int(max_rows), 5000)
    if max_cols and int(max_cols) > 0:
        kw["max_cols"] = min(int(max_cols), 200)
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, functools.partial(_pc.preview, full, **kw))
    except Exception as e:
        data = {"kind": "binary", "meta": _pc.file_meta(full),
                "error": _p5_t(lang, "预览失败：%s: %s", "Preview failed: %s: %s", type(e).__name__, e)}
    data["path"] = full.replace(os.sep, "/")
    data["download_url"] = "/api/file/download?path=" + quote(full)
    data["raw_url"] = "/api/file/raw?path=" + quote(full)
    return JSONResponse(data, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@app.get("/api/file/raw")
async def file_raw(path: str, dl: int = 0):
    """原样返回文件字节：图片/PDF/HTML 用来内嵌渲染（dl=1 强制下载）。"""
    from urllib.parse import quote
    full, err = _preview_resolve(path)
    if err is not None:
        return err
    if not os.path.isfile(full):
        return JSONResponse({"error": "File not found"}, status_code=404)
    fname = os.path.basename(full)
    disp = "attachment" if dl else "inline"
    return FileResponse(full, media_type=_guess_media(full), headers={
        "Content-Disposition": "%s; filename=\"%s\"; filename*=UTF-8''%s" % (disp, quote(fname), quote(fname)),
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "X-Content-Type-Options": "nosniff",
    })


class FileOpenRequest(BaseModel):
    path: str = ""
    action: str = "system"   # system（默认程序打开）| folder（在文件管理器里定位）
    lang: str = "zh"         # P5.1：固定文案语言（zh / en）


@app.post("/api/file/open")
async def file_open(req: FileOpenRequest):
    """用系统默认程序打开 / 在文件管理器里定位（P5，仅桌面端有意义）。

    保守设计：只允许 work/results/项目根内的已存在文件；MEMOMICS_SYSOPEN=0 一键关闭。
    """
    import subprocess
    if not _SYSOPEN_ENABLED:
        return JSONResponse({"ok": False, "error": _p5_t(req.lang, "「系统打开」已被禁用（MEMOMICS_SYSOPEN=0）",
                                                        "\"Open with system app\" is disabled (MEMOMICS_SYSOPEN=0)")},
                            status_code=403)
    full, err = _preview_resolve(req.path, req.lang)
    if err is not None:
        return err
    action = (req.action or "system").strip().lower()
    if action not in ("system", "folder"):
        return JSONResponse({"ok": False, "error": _p5_t(req.lang, "action 只支持 system / folder",
                                                        "action must be system or folder")}, status_code=400)
    try:
        if os.name == "nt":
            if action == "folder":
                subprocess.Popen(["explorer", "/select,", os.path.normpath(full)])
            else:
                os.startfile(full)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open"] + (["-R"] if action == "folder" else []) + [full])
        else:
            target = os.path.dirname(full) if action == "folder" else full
            subprocess.Popen(["xdg-open", target])
    except Exception as e:
        return JSONResponse({"ok": False, "error": _p5_t(req.lang, "打开失败：%s: %s",
                                                        "Failed to open: %s: %s", type(e).__name__, e)},
                            status_code=500)
    return {"ok": True, "action": action, "path": full.replace(os.sep, "/"),
            "message": _p5_t(req.lang,
                             "已交给系统默认程序打开" if action == "system" else "已在文件管理器中定位",
                             "Handed to the system default application" if action == "system"
                             else "Revealed in the file manager")}


@app.get("/api/papers")
async def serve_papers(path: str = ""):
    """文献原文/产物只读服务（批N1 2026-08-16）：仅限 hermes_home/papers/ 内。

    - path 为相对路径（如 xxx.pdf / markdown/xxx.md / translations/xxx.zh.md）
    - PDF → application/pdf（浏览器 iframe 原生阅读器）；md → text/markdown
    """
    papers_root = os.path.join(HERMES_HOME_DIR, "papers")
    try:
        from webui.security import resolve_within_roots, UnsafePathError
        # 相对路径拼到 papers 根后再校验（防 ../ 穿越）
        full = str(resolve_within_roots(os.path.join(papers_root, path or ""), [papers_root]))
    except UnsafePathError as e:
        return JSONResponse({"error": str(e)}, status_code=403)
    if not os.path.isfile(full):
        return JSONResponse({"error": "File not found"}, status_code=404)
    media = ("application/pdf" if full.lower().endswith(".pdf")
             else "text/markdown; charset=utf-8" if full.lower().endswith((".md", ".markdown"))
             else None)
    if media is None:
        return JSONResponse({"error": "仅支持 PDF / Markdown"}, status_code=400)
    return FileResponse(full, media_type=media)


@app.get("/api/papers/page")
async def serve_paper_page(path: str = "", page: int = 0, dpi: int = 150):
    """文献 PDF 单页渲染为 PNG（批O4 2026-08-16：对照视图左侧"真原文"，含原图）。

    - path: 相对 papers 根的 .pdf 文件名
    - page: 0-based 页码；dpi: 80-300（默认 150，含图清晰可读）
    - PyMuPDF get_pixmap 整页渲染（含全部图/表）；Cache-Control 供浏览器缓存
    """
    papers_root = os.path.join(HERMES_HOME_DIR, "papers")
    try:
        from webui.security import resolve_within_roots, UnsafePathError
        full = str(resolve_within_roots(os.path.join(papers_root, path or ""), [papers_root]))
    except UnsafePathError as e:
        return JSONResponse({"error": str(e)}, status_code=403)
    if not full.lower().endswith(".pdf") or not os.path.isfile(full):
        return JSONResponse({"error": "PDF not found"}, status_code=404)
    dpi = max(80, min(300, int(dpi or 150)))
    page = max(0, int(page or 0))
    try:
        import pymupdf as fitz
        import io as _io
        doc = fitz.open(full)
        if page >= doc.page_count:
            doc.close()
            return JSONResponse({"error": "page out of range"}, status_code=400)
        pix = doc[page].get_pixmap(dpi=dpi)
        doc.close()
        png = pix.tobytes("png")
        return Response(content=png, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})
    except Exception as e:
        return JSONResponse({"error": f"page render failed: {str(e)[:200]}"}, status_code=500)


# --- 知识库 ---

@app.get("/api/kb")
async def list_kb(path: str = ""):
    """浏览知识库"""
    if not path:
        path = KB_DIR
    if not os.path.isdir(path):
        return JSONResponse({"error": "KB dir not found"}, status_code=404)
    items = []
    try:
        for p in sorted(Path(path).iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name.startswith("."):
                continue
            items.append({
                "name": p.name,
                "path": str(p).replace("\\", "/"),
                "is_dir": p.is_dir(),
                "size": p.stat().st_size if p.is_file() else 0,
                "ext": p.suffix.lower() if p.is_file() else "",
            })
        return {"path": str(path).replace("\\", "/"), "items": items, "kb_root": KB_DIR.replace("\\", "/"),
                "total_files": sum(1 for _ in Path(KB_DIR).rglob("*") if _.is_file())}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# ── 知识库图谱 / 搜索 / 文件（2026-08-08 从旧副本恢复：生产版丢失了图谱功能） ──

@app.get("/api/kb/file")
async def kb_file_api(path: str = ""):
    """读取知识库文件 + YAML 结构化解析（只读，防路径穿越）"""
    if not path:
        return JSONResponse({"error": "path required"}, status_code=400)
    full = os.path.normpath(path if os.path.isabs(path) else os.path.join(KB_DIR, path))
    kb_root = os.path.normpath(KB_DIR)
    if not (full == kb_root or full.startswith(kb_root + os.sep)):
        return JSONResponse({"error": "path outside KB"}, status_code=403)
    if not os.path.isfile(full):
        return JSONResponse({"error": "File not found"}, status_code=404)
    try:
        size = os.path.getsize(full)
        with open(full, encoding="utf-8", errors="replace") as f:
            content = f.read(200000)
        parsed = None
        parse_error = None
        if full.lower().endswith((".yaml", ".yml")):
            try:
                import yaml
                parsed = yaml.safe_load(content)
            except Exception as e:
                parse_error = str(e)
        return {"path": full.replace("\\", "/"), "content": content, "size": size,
                "truncated": size > 200000, "parsed": parsed, "parse_error": parse_error}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/kb/search")
async def kb_search_api(q: str = "", path: str = ""):
    """知识库全文搜索（线性扫 YAML/MD，毫秒级；CSV 只读头部）"""
    if not q or not q.strip():
        return {"query": q, "results": [], "total": 0}
    root = path if path and os.path.isdir(path) else KB_DIR
    q_lower = q.strip().lower()
    results = []
    try:
        for p in sorted(Path(root).rglob("*")):
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".yaml", ".yml", ".md", ".csv"):
                continue
            limit = 4096 if p.suffix.lower() == ".csv" else 200000
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    lines = f.read(limit).splitlines()
            except Exception:
                continue
            hits = []
            for i, line in enumerate(lines):
                if q_lower in line.lower():
                    start = max(0, i - 1)
                    end = min(len(lines), i + 2)
                    hits.append({"line": i + 1, "snippet": "\n".join(lines[start:end])})
            if hits:
                results.append({"path": str(p).replace("\\", "/"),
                                "hits": hits[:5], "hit_count": len(hits)})
        results.sort(key=lambda r: -r["hit_count"])
        return {"query": q, "results": results[:30], "total": len(results)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/kb/coverage")
async def kb_coverage_api():
    """知识库覆盖矩阵（2026-08-14）：物种×组织×方向×类别/assay 条目数 + 陈旧度。"""
    try:
        import yaml as _yaml
    except Exception:
        _yaml = None
    rows = []
    _now = time.time()
    _stale_days = 90
    try:
        for _sp in sorted(Path(KB_DIR).iterdir()):
            if not _sp.is_dir() or _sp.name.startswith("."):
                continue
            for _ti in sorted(_sp.iterdir()):
                if not _ti.is_dir():
                    continue
                for _dr in sorted(_ti.iterdir()):
                    if not _dr.is_dir():
                        continue
                    _cats = {"01_生物学知识": 0, "02_质控参数": 0, "03_测序方法": 0, "other": 0}
                    _assays = {}
                    _stale = 0
                    _files = 0
                    for _p in _dr.rglob("*.yaml"):
                        _files += 1
                        _lu = ""
                        if _yaml is not None:
                            try:
                                with open(_p, encoding="utf-8", errors="replace") as _pf:
                                    _d = _yaml.safe_load(_pf.read(200000))
                                if isinstance(_d, dict):
                                    _lu = str(_d.get("last_updated") or "")
                            except Exception:
                                pass
                        if _lu:
                            try:
                                _dt = datetime.strptime(_lu[:10], "%Y-%m-%d")
                                if (_now - _dt.timestamp()) > _stale_days * 86400:
                                    _stale += 1
                            except Exception:
                                pass
                        _rel = _p.relative_to(_dr).parts
                        _rel0 = _rel[0] if _rel else ""
                        if _rel0 in _cats:
                            _cats[_rel0] += 1
                        elif _rel0 and not _rel0.isdigit():
                            _cats["other"] += 1
                        if _rel0 == "03_测序方法" and len(_rel) >= 2:
                            _assays[_rel[1]] = _assays.get(_rel[1], 0) + 1
                    rows.append({
                        "species": _sp.name, "tissue": _ti.name, "direction": _dr.name,
                        "cats": _cats, "assays": _assays, "files": _files, "stale": _stale,
                    })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"rows": rows, "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "stale_days": _stale_days, "total_files": sum(r["files"] for r in rows)}


@app.get("/api/kb/graph")
async def kb_graph_api():
    """知识库图谱：路径层级节点（物种/组织/方向/分类/文件）+ auto_trigger 内容关联边（只读）"""
    try:
        import yaml
    except Exception:
        yaml = None
    nodes, node_ids, edges = [], {}, {}
    def add_node(nid, label, ntype, path):
        if nid not in node_ids:
            node_ids[nid] = len(nodes)
            nodes.append({"id": nid, "label": label, "type": ntype, "path": path})
        return node_ids[nid]
    def add_edge(src, dst, etype):
        key = (src, dst, etype)
        if key not in edges:
            edges[key] = len(edges)
        return edges[key]
    try:
        root = Path(KB_DIR)
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix.lower() not in (".yaml", ".yml", ".md"):
                continue
            rel = p.relative_to(root)
            parts = list(rel.parts)
            parent_id = None
            for depth, part in enumerate(parts):
                is_file = depth == len(parts) - 1 and p.is_file()
                ntype = "file" if is_file else "dir"
                label = p.stem if is_file else part
                nid = "/".join(parts[: depth + 1])
                add_node(nid, label, ntype, str(p).replace("\\", "/") if is_file else "")
                if parent_id is not None:
                    add_edge(parent_id, nid, "hierarchy")
                parent_id = nid
        if yaml is not None:
            kw_map = {}
            for n in nodes:
                if n["type"] != "file":
                    continue
                try:
                    with open(n["path"], encoding="utf-8", errors="replace") as f:
                        data = yaml.safe_load(f.read(200000))
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                # 2026-08-14: quality/verified 挂到节点（递归查找嵌套字段，前端着色: 绿=verified+high, 橙=unverified）
                def _find_meta(_obj, _key, _out):
                    if isinstance(_obj, dict):
                        for _k2, _v2 in _obj.items():
                            if _k2 == _key and isinstance(_v2, (str, bool)):
                                _out.append(_v2)
                            else:
                                _find_meta(_v2, _key, _out)
                    elif isinstance(_obj, list):
                        for _v2 in _obj:
                            _find_meta(_v2, _key, _out)
                _qs, _vs = [], []
                _find_meta(data, "quality", _qs)
                _find_meta(data, "verified", _vs)
                n["quality"] = str(_qs[0]) if _qs else ""
                n["verified"] = "verified" if (any(v is True for v in _vs) or any(str(v).lower() == "verified" for v in _vs)) else ""
                # auto_trigger / method / package 可能嵌套在任意层级，递归提取共享关键词
                def _collect_triggers(obj, out):
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if k in ("auto_trigger", "method", "package") and isinstance(v, (str, list)):
                                if isinstance(v, str):
                                    out.append(v)
                                else:
                                    out.extend(x for x in v if isinstance(x, str))
                            else:
                                _collect_triggers(v, out)
                    elif isinstance(obj, list):
                        for v in obj:
                            _collect_triggers(v, out)
                triggers = []
                _collect_triggers(data, triggers)
                seen = set()
                for kw in triggers:
                    kw = kw.strip().split("—")[0].strip()[:30]
                    if not kw or kw in seen:
                        continue
                    seen.add(kw)
                    kw_map.setdefault(kw, []).append(n["id"])
            for kw, ids in kw_map.items():
                if len(ids) >= 2:
                    for i in range(len(ids) - 1):
                        add_edge(ids[i], ids[i + 1], "related")
        # 2026-08-14: error_memory 节点（错误经验入库图谱，红色标识）
        _em_root = add_node("error_memory", "错误记忆", "dir", "")
        try:
            _em_path = root / "error_memory" / "errors.jsonl"
            if _em_path.is_file():
                _em_seen = set()
                for _line in _em_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    _line = _line.strip()
                    if not _line.startswith("{"):
                        continue
                    try:
                        _e = json.loads(_line)
                    except Exception:
                        continue
                    _et = str(_e.get("error_type") or "unknown")[:40]
                    if _et in _em_seen:
                        continue
                    _em_seen.add(_et)
                    _eid = "error_memory/" + _et
                    _ei = add_node(_eid, _et, "error", "")
                    nodes[_ei]["detail"] = str(_e.get("symptom") or "")[:100]
                    add_edge("error_memory", _eid, "hierarchy")
        except Exception:
            pass

        edge_list = [{"source": s, "target": t, "type": et} for (s, t, et) in edges]
        return {"nodes": nodes, "edges": edge_list,
                "counts": {"nodes": len(nodes), "edges": len(edges),
                           "related": sum(1 for e in edge_list if e["type"] == "related")}}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# --- Skill 浏览 ---

@app.get("/api/skills")
async def list_skills():
    """列出所有 skill, 按类型分类"""
    # category 字段值 -> 显示分类名 的映射
    JSON_CATEGORY_MAP = {
        "scrna": "scRNA", "scRNA": "scRNA",
        "scatac": "scATAC", "scATAC": "scATAC",
        "Spatial": "Spatial", "spatial": "Spatial",
        "Bulk RNA": "Bulk RNA", "bulk rna": "Bulk RNA",
        "Proteomics": "Proteomics", "proteomics": "Proteomics",
        "Drug Discovery": "Drug Discovery", "drug discovery": "Drug Discovery",
        "Microbiome": "Microbiome", "microbiome": "Microbiome",
        "Multi-omics": "Multi-omics", "multi-omics": "Multi-omics",
        "Clinical": "Clinical", "clinical": "Clinical",
        "GWAS/Genetics": "GWAS/Genetics", "gwas/genetics": "GWAS/Genetics",
        "Data Query": "Data Query", "data query": "Data Query",
        "Literature": "Literature", "literature": "Literature",
        "Visualization": "Visualization", "visualization": "Visualization",
        "user-skill": "用户技能", "user-plotting": "用户画图",
        "General Utility": "General Utility", "general utility": "General Utility",
        "Immunology": "Immunology", "immunology": "Immunology",
        "Mol Bio": "Mol Bio", "mol bio": "Mol Bio",
        "Assay/Wet Lab": "Assay/Wet Lab", "assay/wet lab": "Assay/Wet Lab",
        "Imaging": "Imaging", "imaging": "Imaging",
        "Structural Biology": "Structural Biology", "structural biology": "Structural Biology",
        "Histology/Pathology": "Histology/Pathology", "histology/pathology": "Histology/Pathology",
        "Bioimaging": "Bioimaging", "bioimaging": "Bioimaging",
    }
    # 扩展关键词 — 覆盖 description 内容匹配
    NAME_RULES = [
        ("scATAC-seq", ["atac", "archr", "signac", "chromvar", "chromatin", "peak-call", "motif", "footprint"]),
        ("空间转录组", ["spatial", "visium", "stereo", "slide-seq", "cell2location", "stlearn", "squidpy"]),
        ("表观/甲基化", ["methylation", "bisulfite", "chipseq", "chip-seq", "chip-atlas", "cuttag", "cut&tag", "epigenome", "epigenetic"]),
        ("多组学整合", ["integration", "multiome", "rgcca", "mofa", "wgcna", "coexpression-network", "hdwgcna"]),
        ("Bulk RNA-seq", ["bulk", "deseq2", "edger", "limma", "rnaseq", "counts-to-de"]),
        ("蛋白/代谢", ["proteomics", "metabolomics", "lipidomics"]),
        ("药物/临床", ["drug", "admet", "docking", "fda", "clinical", "survival", "disease", "therapeutic", "pharmac", "target", "disease-progression", "check_drug", "find_alternative_drugs", "get_fda", "drug-label"]),
        ("微生物/基因组", ["microbial", "phylo", "sgrna", "crispr", "plasmid", "primer", "restriction", "bacterial", "phage", "amr", "cas9_mutation", "knockout_sgrna"]),
        ("报告/工具", ["html", "report", "monitor", "layout", "design", "code-writer", "docx", "pptx", "ppt-", "data-viz", "pdf-report", "summarize", "find-skill", "computer-use", "self-improving", "deep-research", "web-research", "search_google"]),
        ("文献/检索", ["paper", "pubmed", "arxiv", "scholar", "literature", "pdf-translate", "pdf_reader", "extract_pdf", "fetch_supplementary"]),
        ("数据库查询", ["query_", "query-", "open-targets", "cbioportal", "chembl", "pubchem", "uniprot", "pdb", "ensembl", "encode", "kegg", "reactome", "jaspar", "gnomad", "dbsnp", "stringdb", "genomic_region", "genomic-region", "sequence-align", "alphafold", "chatnt"]),
        ("scRNA-seq", ["scrna", "seurat", "sctransform", "clustering", "cellchat", "scenic", "trajectory", "deg", "annotation", "doublet", "cellbender", "soupx", "infercnv", "cell-cycle", "senescence", "sasp", "cell-type"]),
    ]

    # description 内容关键词匹配 — 当名字匹配不到时使用
    DESC_RULES = [
        ("scATAC-seq", ["atac-seq", "atac seq", "chromatin accessibility", "peak call", "motif enrichment", "footprint", "archr", "signac", "tf binding"]),
        ("空间转录组", ["spatial transcriptom", "visium", "squidpy", "spatial rna", "spatial gene"]),
        ("表观/甲基化", ["methylation", "bisulfite", "chip-seq", "chip seq", "chip atlas", "cut&tag", "epigenome", "epigenetic", "histone modification", "macs2"]),
        ("scRNA-seq", ["single-cell", "scrna", "seurat", "scanpy", "cell type", "cellchat", "scenic", "doublet", "cellbender", "soupx", "infercnv", "cnv", "harmony", "scvi", "umap", "leiden", "sctransform", "transcriptom", "gene expression", "differential expression"]),
        ("Bulk RNA-seq", ["bulk rna", "deseq2", "edger", "limma", "counts", "rna-seq align", "rnaseq count"]),
        ("微生物/基因组", ["bacterial", "crispr", "sgrna", "plasmid", "phylogen", "phage", "microbial", "antimicrobial", "cas9", "primer design", "pcr"]),
        ("药物/临床", ["drug", "fda", "clinical trial", "survival analysis", "disease", "therapeutic", "pharmac", "admet", "docking", "prescription"]),
        ("文献/检索", ["paper", "pubmed", "literature", "pdf", "arxiv", "scholar"]),
        ("数据库查询", ["query", "database", "api", "ensembl", "uniprot", "pdb", "chembl", "pubchem", "kegg", "reactome", "encode", "jaspar", "cbioportal", "gnomad", "clinvar"]),
        ("报告/工具", ["report", "html", "powerpoint", "docx", "visualization", "summarize"]),
    ]

    def _categorize(name, skill_json_data, skill_md_content="", desc=""):
        nl = name.lower()
        # 0. SKILL.md category 字段优先 (对齐 SOUL.md 18 类系统)
        if skill_md_content:
            cat_match = _re_mod.search(r'category:\s*"?([^"\n]+)"?', skill_md_content)
            if cat_match:
                cat_val = cat_match.group(1).strip()
                if cat_val in JSON_CATEGORY_MAP:
                    return JSON_CATEGORY_MAP[cat_val]
                if cat_val.lower() in JSON_CATEGORY_MAP:
                    return JSON_CATEGORY_MAP[cat_val.lower()]
        combined = (nl + " " + desc.lower())
        # 1. 名字关键词匹配
        if any(kw in nl for kw in ["scrna", "seurat", "scanpy", "sctransform", "cellchat", "scenic", "monocle", "cellranger"]):
            return "scRNA-seq"
        # 0b. 名字明确包含 atac, 直接分到 scATAC-seq
        if any(kw in nl for kw in ["atac", "archr", "signac", "chromvar"]):
            return "scATAC-seq"
        # 0c. 名字明确包含 spatial/visium
        if any(kw in nl for kw in ["spatial", "visium", "stereo", "squidpy"]):
            return "空间转录组"
        # 0d. CellBender/SoupX/inferCNV 等 scRNA 去污染/工具
        if any(kw in nl for kw in ["cellbender", "soupx", "infercnv", "doubletfinder"]):
            return "scRNA-seq"
        # 0e. cell-cell-communication -> scRNA-seq
        if "cell-cell" in nl or "cell_cell" in nl:
            return "scRNA-seq"
        # 0f. senescence/sasp -> scRNA-seq (或衰老相关)
        if any(kw in nl for kw in ["sasp", "senescence"]):
            return "scRNA-seq"
        # 0g. annotate_celltype -> scRNA-seq
        if "annotate_celltype" in nl or "annotate_cell" in nl:
            return "scRNA-seq"
        # 0h. trajectory/deg/functional-enrichment-from-degs -> scRNA-seq
        if any(kw in nl for kw in ["trajectory", "deg-analysis", "functional-enrichment-from"]):
            return "scRNA-seq"
        # 0i. create_harmony/scvi/uce embeddings -> scRNA-seq
        if any(kw in nl for kw in ["harmony_embeddings", "scvi_embeddings", "uce_embeddings", "ima_interpret"]):
            return "scRNA-seq"
        # 0j. immune-deconvolution -> 不是 scRNA-seq, 放数据库/工具
        # 0k. coexpression-network -> 多组学整合
        if "coexpression" in nl:
            return "多组学整合"
        # 0l. functional-enrichment / gene_set_enrichment -> scRNA-seq 下游分析
        if any(kw in nl for kw in ["functional-enrichment", "gene_set_enrichment", "pathway-enrichment"]):
            return "scRNA-seq"
        # 1. 读 SKILL.md frontmatter 里的 metadata.hermes.tags / metadata.hermes.category
        if skill_md_content:
            import re
            # 提取 tags
            tag_match = re.search(r'tags:\s*\[(.+?)\]', skill_md_content)
            if tag_match:
                tags_str = tag_match.group(1).lower()
                if any(kw in tags_str for kw in ["atac", "archr", "scatac"]):
                    return "scATAC-seq"
                if any(kw in tags_str for kw in ["spatial", "visium"]):
                    return "空间转录组"
                if any(kw in tags_str for kw in ["methylation", "chipseq", "epigenome"]):
                    return "表观/甲基化"
                if any(kw in tags_str for kw in ["scrna", "seurat", "scenic", "cellchat"]):
                    return "scRNA-seq"
                if any(kw in tags_str for kw in ["bulk", "deseq2"]):
                    return "Bulk RNA-seq"
                if any(kw in tags_str for kw in ["proteomics", "metabolomics"]):
                    return "蛋白/代谢"
                if any(kw in tags_str for kw in ["microbial", "crispr"]):
                    return "微生物/基因组"
                if any(kw in tags_str for kw in ["integration", "multiome"]):
                    return "多组学整合"
                if any(kw in tags_str for kw in ["report", "html"]):
                    return "报告/工具"
            # 提取 category (跳过宽泛的 genomics/tool/other)
            cat_match = _re_mod.search(r'category:\s*(\S+)', skill_md_content)
            if cat_match:
                cat_val = cat_match.group(1).lower().strip('"').strip("'")
                if cat_val not in ("genomics", "tool", "other") and cat_val in JSON_CATEGORY_MAP:
                    return JSON_CATEGORY_MAP[cat_val]
        # 2. 读 skill.json 的 category
        # 注意: "genomics" 太宽泛, 不直接返回, 继续检查 description
        if skill_json_data:
            cat = skill_json_data.get("category", "").lower().strip()
            if cat and cat not in ("genomics", "tool", "other"):
                if cat in JSON_CATEGORY_MAP:
                    return JSON_CATEGORY_MAP[cat]
                for jcat, display in JSON_CATEGORY_MAP.items():
                    if jcat in cat or cat in jcat:
                        return display
        # 4. description 内容匹配 (当名字和 metadata 都匹配不到时)
        desc_lower = desc.lower()
        for display_cat, keywords in DESC_RULES:
            for kw in keywords:
                if kw in desc_lower:
                    return display_cat
        # 5. 名字关键词匹配 (按优先级排序)
        # 注意: 如果名字里包含多个类型的关键词, 按以下优先级排序
        for display_cat, keywords in NAME_RULES:
            for kw in keywords:
                if kw in nl:
                    # 额外检查: 如果是通用动词开头的 (analyze_/get_/perform_/find_), 不用名字分类
                    # 而是依赖 description (已经在第4步处理)
                    if any(nl.startswith(p) for p in ['analyze_', 'get_', 'perform_', 'find_', 'generate_', 'detect_', 'fit_', 'simulate_', 'bayesian_', 'identify_', 'liftover_', 'interspecies_']):
                        continue  # 跳过名字匹配, 交给后面的默认分类
                    return display_cat
        # 6. 如果是 analyze_/get_/perform_ 等通用技能, 默认归内置
        return "内置"

    # Read disabled skills from config.yaml
    disabled_skills = _read_disabled_skills()

    # Scan both SKILLS_DIR (project root skills/) and hermes_home/skills/bioinformatics/
    scan_dirs = [Path(SKILLS_DIR)]
    bio_dir = Path(HERMES_HOME_DIR) / "skills" / "bioinformatics"
    if bio_dir.exists() and bio_dir not in scan_dirs:
        scan_dirs.append(bio_dir)
    # 用户专属 skill 库（画图等用户提供脚本沉淀，category: user-skill）
    # 未来新增 user-skill-<类别> 分类目录时在此登记
    user_plot_dir = Path(HERMES_HOME_DIR) / "skills" / "plotting"
    if user_plot_dir.exists() and user_plot_dir not in scan_dirs:
        scan_dirs.append(user_plot_dir)

    items = []
    seen_names = set()
    for scan_dir in scan_dirs:
        if not scan_dir.is_dir():
            continue
        for p in sorted(scan_dir.iterdir(), key=lambda x: x.name.lower()):
            if not p.is_dir() or p.name.startswith("."):
                continue
            if p.name in seen_names:
                continue  # deduplicate
            seen_names.add(p.name)
            skill_md = p / "SKILL.md"
            skill_json = p / "skill.json"
            desc = ""
            scripts_count = 0
            sj_data = None
            md_content = ""
            if skill_md.exists():
                with open(skill_md, encoding="utf-8", errors="replace") as f:
                    md_content = f.read(2000)
                    for line in md_content.split("\n"):
                        if line.strip().startswith("description:"):
                            desc = line.split(":", 1)[1].strip().strip('"').strip("'")
                            break
            if skill_json.exists():
                try:
                    with open(skill_json, encoding="utf-8", errors="replace") as f:
                        sj_data = json.load(f)
                except:
                    pass
            scripts_dir = p / "scripts"
            if scripts_dir.exists():
                scripts_count = len([f for f in scripts_dir.iterdir() if f.is_file() and not f.name.startswith(".")])
            category = _categorize(p.name, sj_data, md_content, desc)
            items.append({
                "name": p.name,
                "path": str(p).replace("\\", "/"),
                "description": desc[:120],
                "scripts_count": scripts_count,
                "has_skill_md": skill_md.exists(),
                "category": category,
                "disabled": p.name in disabled_skills,
            })
    # 按分类分组统计
    cat_counts = {}
    for item in items:
        c = item["category"]
        cat_counts[c] = cat_counts.get(c, 0) + 1
    enabled_count = sum(1 for i in items if not i["disabled"])
    return {"skills": items, "total": len(items), "categories": cat_counts, "enabled_count": enabled_count, "disabled_count": len(disabled_skills)}


# ── Skill management: enable/disable via config.yaml ──

def _read_disabled_skills() -> set:
    """Read skills.disabled from hermes_home/config.yaml."""
    import yaml
    cfg_path = os.path.join(HERMES_HOME_DIR, "config.yaml")
    if not os.path.exists(cfg_path):
        return set()
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        if not cfg:
            return set()
        skills_cfg = cfg.get("skills")
        if not isinstance(skills_cfg, dict):
            return set()
        return set(skills_cfg.get("disabled") or [])
    except Exception:
        return set()


def _write_disabled_skills(disabled: set):
    """Write skills.disabled to hermes_home/config.yaml (preserving other keys)."""
    import yaml
    cfg_path = os.path.join(HERMES_HOME_DIR, "config.yaml")
    cfg = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception:
            cfg = {}
    if "skills" not in cfg or not isinstance(cfg.get("skills"), dict):
        cfg["skills"] = {}
    cfg["skills"]["disabled"] = sorted(disabled)
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


@app.post("/api/skills/{name}/toggle")
async def toggle_skill(name: str):
    """Toggle a skill on/off (enable <-> disable)."""
    disabled = _read_disabled_skills()
    # Check both SKILLS_DIR and hermes_home/skills/bioinformatics
    skill_dir = os.path.join(SKILLS_DIR, name)
    if not os.path.isdir(skill_dir):
        skill_dir = os.path.join(HERMES_HOME_DIR, "skills", "bioinformatics", name)
    if not os.path.isdir(skill_dir):
        return {"error": f"Skill '{name}' not found"}
    if name in disabled:
        disabled.discard(name)
        action = "enabled"
    else:
        disabled.add(name)
        action = "disabled"
    _write_disabled_skills(disabled)
    return {"ok": True, "skill": name, "action": action, "disabled_count": len(disabled)}


@app.post("/api/skills/bulk-toggle")
async def bulk_toggle_skills(request: Request):
    """Bulk enable/disable skills by category or list of names.
    Body: {"action": "enable"|"disable", "names": [...], "category": "..."}
    """
    body = await request.json()
    action = body.get("action", "disable")
    names = body.get("names", [])
    category_filter = body.get("category", "")
    disabled = _read_disabled_skills()
    if category_filter:
        # Get all skills in this category
        skills_data = await list_skills()
        names = [s["name"] for s in skills_data["skills"] if s["category"] == category_filter]
    if action == "disable":
        disabled.update(names)
    else:
        disabled.difference_update(names)
    _write_disabled_skills(disabled)
    return {"ok": True, "action": action, "affected": len(names), "disabled_count": len(disabled)}


@app.get("/api/skills/enabled/list")
async def list_enabled_skills():
    """List only enabled skills (for system prompt reference)."""
    disabled = _read_disabled_skills()
    items = []
    if os.path.isdir(SKILLS_DIR):
        for p in sorted(Path(SKILLS_DIR).iterdir(), key=lambda x: x.name.lower()):
            if not p.is_dir() or p.name.startswith("."):
                continue
            if p.name in disabled:
                continue
            items.append(p.name)
    return {"enabled_skills": items, "count": len(items)}


@app.get("/api/skills/catalog")
async def skills_catalog(q: str = "", category: str = "", limit: int = 0):
    """P8: 置顶选择器用的 skill 清单（含触发等级/触发词/适用场景/禁用状态）"""
    try:
        base = await list_skills()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    disabled = _read_disabled_skills()
    kw = (q or "").strip().lower()
    items = []
    for it in (base.get("skills") or []):
        name = it.get("name") or ""
        if not name:
            continue
        if category and it.get("category") != category:
            continue
        meta = _skill_meta(name)
        row = {
            "name": name,
            "display": (meta.get("display") or name),
            "description": (meta.get("description") or it.get("description") or "")[:300],
            "when_to_use": (meta.get("when_to_use") or "")[:400],
            "trigger_keywords": (meta.get("trigger_keywords") or [])[:20],
            "aliases": (meta.get("aliases") or [])[:10],
            "trigger_level": meta.get("trigger_level") or "",
            "category": it.get("category") or "",
            "scripts_count": it.get("scripts_count") or 0,
            "has_skill_md": bool(it.get("has_skill_md")),
            "disabled": name in disabled,
            "dir": meta.get("dir") or it.get("path") or "",
        }
        if kw:
            hay = " ".join([name, row["display"], row["description"], row["when_to_use"],
                            " ".join(row["trigger_keywords"]), row["category"]]).lower()
            if kw not in hay:
                continue
        items.append(row)
    items.sort(key=lambda x: (x["disabled"], x["trigger_level"] != "RED", x["name"].lower()))
    if limit and limit > 0:
        items = items[:limit]
    return {"skills": items, "total": len(items), "pinned_max": _PINNED_MAX}


@app.get("/api/skills/resolve")
async def resolve_skill(q: str = ""):
    """P0-3: 解析 /skill-name（前端斜杠补全 + 歧义/未知/相近建议）。

    注意：必须注册在 /api/skills/{name} 之前，否则 /resolve 会被当成技能名吞掉。
    """
    inv = _parse_skill_invocations(q or "")
    first = inv["resolved"][0]["name"] if inv["resolved"] else ""
    return {
        "query": q or "",
        "raw": inv["raw"],
        "resolved": inv["resolved"],
        "unknown": inv["unknown"],
        "ambiguous": inv["ambiguous"],
        "overflow": inv["overflow"],
        "suggestions": [s for t in inv["unknown"] for s in _suggest_skills(t)][:8],
        "skill": _pinned_item(first) if first else {},
    }


@app.get("/api/skills/{name}")
async def get_skill_detail(name: str):
    """获取 skill 详情 (SKILL.md + 脚本列表)"""
    # 同时检查 SKILLS_DIR 和 SKILLS_BIO_DIR
    skill_dir = os.path.join(SKILLS_DIR, name)
    if not os.path.isdir(skill_dir):
        skill_dir = os.path.join(SKILLS_BIO_DIR, name)
    if not os.path.isdir(skill_dir):
        return JSONResponse({"error": "Skill not found"}, status_code=404)
    result = {"name": name, "path": skill_dir}
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if os.path.exists(skill_md):
        with open(skill_md, encoding="utf-8", errors="replace") as f:
            result["skill_md"] = f.read()
    skill_json = os.path.join(skill_dir, "skill.json")
    if os.path.exists(skill_json):
        with open(skill_json, encoding="utf-8", errors="replace") as f:
            result["skill_json"] = json.load(f)
    scripts_dir = os.path.join(skill_dir, "scripts")
    if os.path.isdir(scripts_dir):
        result["scripts"] = []
        for f in sorted(Path(scripts_dir).iterdir()):
            if f.is_file() and not f.name.startswith("."):
                result["scripts"].append({"name": f.name, "size": f.stat().st_size})
    refs_dir = os.path.join(skill_dir, "references")
    if os.path.isdir(refs_dir):
        result["references"] = []
        for f in sorted(Path(refs_dir).iterdir()):
            if f.is_file():
                result["references"].append({"name": f.name, "size": f.stat().st_size})
    return result


@app.get("/api/skills/{name}/files")
async def skill_files(name: str):
    """P8: skill 目录完整文件树（WebUI 里浏览该 skill 的全部文件与脚本）"""
    data = _skill_files_tree(name)
    if not data:
        return JSONResponse({"error": "Skill not found"}, status_code=404)
    return data


class PinnedSkillsRequest(BaseModel):
    skills: list = []


@app.get("/api/sessions/{sid}/skills")
async def get_session_pinned_skills(sid: str):
    """P8: 会话置顶 skill + 本会话实际加载记录（前端 chip / 徽标 / 审计数据源）"""
    pinned = _pinned_skills_get(sid)
    used = _skill_usage_get(sid)
    return {
        "session_id": sid,
        "pinned": [_pinned_item(n) for n in pinned],
        "used": used,
        "used_names": sorted(used.keys()),
        "pinned_max": _PINNED_MAX,
    }


@app.post("/api/sessions/{sid}/skills")
async def set_session_pinned_skills(sid: str, req: PinnedSkillsRequest):
    """P8: 设置本会话置顶 skill（优先而非独占；与全局启用/禁用互不影响）"""
    clean = _pinned_skills_set(sid, req.skills or [])
    used = _skill_usage_get(sid)
    return {"ok": True, "session_id": sid, "pinned": [_pinned_item(n) for n in clean], "used": used}


# --- 动态创建技能 ---

class CreateSkillRequest(BaseModel):
    name: str
    description: str = ""
    trigger_scenario: str = ""
    language: str = "R"
    scripts: dict = {}       # {filename: content}
    skill_md_content: str = ""
    category: str = "custom"


@app.post("/api/skills/create")
async def create_skill(req: CreateSkillRequest):
    """动态创建新技能 (Biomni 风格: SKILL.md + scripts/ + skill.json)"""
    import re
    # 安全: skill name 只允许字母数字下划线短横
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', req.name.strip().lower())
    if not safe_name:
        return JSONResponse({"error": "Invalid skill name"}, status_code=400)

    skill_dir = os.path.join(SKILLS_DIR, safe_name)
    if os.path.exists(skill_dir):
        return JSONResponse({"error": f"Skill '{safe_name}' already exists"}, status_code=409)

    os.makedirs(os.path.join(skill_dir, "scripts"), exist_ok=True)

    # 生成 SKILL.md
    now = datetime.now().strftime("%Y-%m-%d")
    if req.skill_md_content:
        skill_md = req.skill_md_content
    else:
        skill_md = f"""---
name: {safe_name}
description: "{req.description}"
version: 1.0.0
author: MemOmics (auto-created)
created: {now}
category: {req.category}
language: {req.language}
---

## 触发场景

{req.trigger_scenario or '当用户需要相关分析时触发。'}

## 使用方法

1. source 脚本
2. 调用对应函数

## 脚本列表

"""
        for fname in req.scripts:
            skill_md += f"- `scripts/{fname}`\n"

    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(skill_md)

    # 写脚本
    for fname, content in req.scripts.items():
        safe_fname = os.path.basename(fname)
        with open(os.path.join(skill_dir, "scripts", safe_fname), "w", encoding="utf-8") as f:
            f.write(content)

    # skill.json
    skill_json = {
        "id": safe_name,
        "name": req.name,
        "description": req.description,
        "category": req.category,
        "language": req.language,
        "trigger_scenario": req.trigger_scenario,
        "version": "1.0.0",
        "created": now,
        "scripts": list(req.scripts.keys()),
        "auto_created": True,
    }
    with open(os.path.join(skill_dir, "skill.json"), "w", encoding="utf-8") as f:
        json.dump(skill_json, f, indent=2, ensure_ascii=False)

    # 同步到 hermes_home/skills/bioinformatics/
    import shutil
    dest = os.path.join(HERMES_HOME_DIR, "skills", "bioinformatics", safe_name)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(skill_dir, dest)

    # P5: 自动重建技能索引（新 skill 创建后立即生效）
    # 2026-08-21: hermes-agent/tools/build_skill_index.py 已不在仓库内 → 改用
    # webui/auto_register（启动 scan 同一套机制），保证 create 后索引立即生效。
    try:
        from webui import auto_register as _ar
        _ar.init(
            os.path.join(HERMES_HOME_DIR, "skills", "bioinformatics"),
            os.path.join(HERMES_HOME_DIR, "SKILLS_INDEX.md"),
            os.path.join(HERMES_HOME_DIR, "SOUL.md"),
        )
        _r = _ar.scan_and_register_all()
        print(f"[MemOmics] Auto-rebuilt skill index after creating {safe_name}: {_r}", flush=True)
    except Exception as e:
        print(f"[MemOmics] Auto-rebuild index failed (non-fatal): {e}", flush=True)

    return {"ok": True, "name": safe_name, "path": skill_dir, "scripts": list(req.scripts.keys())}


# --- 分析结果 ---

@app.get("/api/results/{sid}")
@app.get("/api/results/{sid}")
async def list_results(sid: str, path: str = "", sort: str = "time_desc", lang: str = "zh"):
    """列出会话分析结果目录（每次实时扫描磁盘，不用缓存）

    sort（P5 2026-09-22 / P5.1 修订）：
      - time_desc（默认）：**目录全部在最上面（按名称 A→Z）**，文件排在目录下面、按修改时间倒序
        —— 用户要求「最新出的文件排最上面，不要把目录和文件混了」
      - name：目录在前 + 名称升序（旧行为，目录同样永远在最上面）

    每项带 viewed（P5.1）：是否已被用户打开看过，见 <结果目录>/.viewed.json。
    """
    # 每次都扫描磁盘，不依赖内存中的 results_dir
    base = _find_best_results_dir(sid)
    if not base and sid in _sessions:
        base = _sessions[sid]["results_dir"]
    if not base:
        base = os.path.join(RESULTS_DIR, sid)
    if not os.path.isdir(base) or not any(Path(base).iterdir()):
        return {"items": [], "path": base,
                "note": _p5_t(lang, "该会话尚未产生分析结果。开始分析后，结果将自动存储到此处。",
                              "This session has no analysis results yet. They will appear here once analysis starts."),
                "base": base.replace("\\", "/")}
    # 同步更新内存
    if sid in _sessions and os.path.abspath(_sessions[sid].get("results_dir","")) != os.path.abspath(base):
        _sessions[sid]["results_dir"] = base
    target = os.path.join(base, path) if path else base
    if not os.path.isdir(target):
        return {"items": [], "path": target,
                "note": _p5_t(lang, "该会话尚未产生分析结果。开始分析后，结果将自动存储到此处。",
                              "This session has no analysis results yet. They will appear here once analysis starts."),
                "base": base.replace("\\", "/")}
    items = []
    _viewed = _viewed_load(base)
    _sort_mode = (sort or "time_desc").strip().lower()
    if _sort_mode in ("name", "name_asc"):
        def _iter_key(x):
            return (0 if x.is_dir() else 1, x.name.lower())
    else:
        # 目录永远在最上面，且目录之间按名称 A→Z；文件按 mtime 倒序（最新在最上面）
        def _iter_key(x):
            if x.is_dir():
                return (0, x.name.lower(), 0)
            try:
                return (1, "", -x.stat().st_mtime)
            except OSError:
                return (1, "", 0)
    try:
        for p in sorted(Path(target).iterdir(), key=_iter_key):
            if p.name.startswith("."):
                continue
            try:
                _st = p.stat()
            except OSError:
                continue
            _rel = str(p.relative_to(base)).replace("\\", "/")
            items.append({
                "name": p.name,
                "path": str(p).replace("\\", "/"),
                "is_dir": p.is_dir(),
                # 看过了 & 看完之后文件没再被改写 才算「已查看」（重新分析覆盖同名文件会重新变回未查看）
                "viewed": (bool(_viewed.get(_rel)) and _st.st_mtime <= float(_viewed.get(_rel) or 0))
                          if p.is_file() else False,
                "size": _st.st_size if p.is_file() else 0,
                "ext": p.suffix.lower() if p.is_file() else "",
                "rel_path": _rel,
                "mtime": _st.st_mtime,
                "mtime_str": datetime.fromtimestamp(_st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })
        _unread = sum(1 for it in items if not it["is_dir"] and not it.get("viewed"))
        return JSONResponse({"items": items, "path": target.replace("\\", "/"), "base": base.replace("\\", "/"), "session_id": sid, "sort": _sort_mode, "results_name": os.path.basename(base),
                "unread": _unread,
                "viewed_count": sum(1 for it in items if it["viewed"]),
                "manifest": _load_result_manifest(base), "manifest_versions": _list_manifest_versions(base)},
                headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


class ResultViewedRequest(BaseModel):
    path: str = ""            # 绝对路径或结果目录内的相对路径
    viewed: bool = True       # false = 取消「已查看」标记


class UILangRequest(BaseModel):
    lang: str = "zh"


@app.post("/api/ui/lang")
async def set_ui_lang(req: UILangRequest):
    """P6-2：前端切换中/英时告知一次，让后端生成的界面文案（P4 弹窗等）跟着切。

    单机单用户工具：这是一个进程级的界面偏好，不参与会话隔离。
    """
    _l = (req.lang or "").strip().lower()
    if _l not in ("zh", "en"):
        return JSONResponse({"error": "lang must be zh or en"}, status_code=400)
    _UI_LANG_STATE["lang"] = _l
    return {"ok": True, "lang": _l}


@app.get("/api/ui/lang")
async def get_ui_lang():
    """P6-2：当前界面语言（只读，用于自检/验证）。"""
    return {"lang": _ui_lang()}


@app.post("/api/results/{sid}/viewed")
async def mark_result_viewed(sid: str, req: ResultViewedRequest):
    """把结果文件标成「已查看」（P5.1，提醒用户还有哪些文件没看）。

    - 前端在右侧面板打开文件后调用；viewed=false 可撤销
    - 只写 <结果目录>/.viewed.json（点开头，列表扫描自动忽略，不污染结果目录）
    - 越界路径 403，结果目录不存在 404；不接受目录
    """
    base = _find_best_results_dir(sid)
    if not base and sid in _sessions:
        base = _sessions[sid]["results_dir"]
    if not base:
        base = os.path.join(RESULTS_DIR, sid)
    if not os.path.isdir(base):
        return JSONResponse({"error": "No results directory for this session"}, status_code=404)
    raw = (req.path or "").strip()
    if not raw:
        return JSONResponse({"error": "path is required"}, status_code=400)
    root = os.path.abspath(base)
    full = os.path.abspath(raw if os.path.isabs(raw) else os.path.join(root, raw))
    if full != root and not full.startswith(root + os.sep):
        return JSONResponse({"error": "Path is outside the session results directory"}, status_code=403)
    key = os.path.relpath(full, root).replace(os.sep, "/")
    if key in ("", ".") or key.startswith(".."):
        return JSONResponse({"error": "Invalid path"}, status_code=400)
    if os.path.isdir(full):
        return JSONResponse({"error": "Directories cannot be marked as viewed"}, status_code=400)
    if not os.path.exists(full):
        return JSONResponse({"error": "File not found"}, status_code=404)
    data = _viewed_load(root)
    if req.viewed:
        data.setdefault(key, time.time())
    else:
        data.pop(key, None)
    try:
        _viewed_save(root, data)
    except Exception as e:
        return JSONResponse({"error": "Cannot write viewed state: %s" % e}, status_code=500)
    return {"ok": True, "path": full.replace(os.sep, "/"), "rel": key,
            "viewed": bool(req.viewed), "viewed_count": len(data)}


# ============ 结果完成契约（P0-2）：analysis_manifest 协议 ============
MANIFEST_SCHEMA = "memomics.analysis_manifest.v1"


def _list_manifest_versions(results_dir: str) -> list:
    """列出结果目录中已保存的 manifest 版本号（升序）"""
    versions = []
    if not results_dir or not os.path.isdir(results_dir):
        return versions
    try:
        for fn in os.listdir(results_dir):
            m = re.match(r"^analysis_manifest\.v(\d+)\.json$", fn)
            if m:
                versions.append(int(m.group(1)))
    except Exception:
        pass
    return sorted(versions)


def _load_result_manifest(results_dir: str, version: int = 0):
    """读取最新（version=0）或指定版本的 manifest；无则返回 None"""
    if not results_dir:
        return None
    p = os.path.join(results_dir, f"analysis_manifest.v{version}.json") if version else os.path.join(results_dir, "analysis_manifest.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_result_manifest(results_dir: str, manifest: dict) -> int:
    """保存 manifest：版本递增，写 .v{n} + 更新最新文件。返回版本号。"""
    if not results_dir:
        raise ValueError("results_dir is empty")
    os.makedirs(results_dir, exist_ok=True)
    versions = _list_manifest_versions(results_dir)
    ver = (versions[-1] + 1) if versions else 1
    manifest["schema"] = MANIFEST_SCHEMA
    manifest["version"] = ver
    if not manifest.get("created_at"):
        manifest["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if "model" not in manifest:
        manifest["model"] = {"provider": _current_model.get("provider", ""), "model": _current_model.get("model", "")}
    prov = manifest.setdefault("provenance", {})
    if "git" not in prov:
        try:
            import subprocess as _sp
            # 2026-08-20: GBK 崩溃修复——git status 输出含中文文件名(UTF-8), 默认按
            # cp936 解码会抛 UnicodeDecodeError 并崩溃子进程 reader 线程
            _r = _sp.run(["git", "rev-parse", "--short", "HEAD"], cwd=MEMOMICS_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3)
            _d = _sp.run(["git", "status", "--porcelain"], cwd=MEMOMICS_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3)
            prov["git"] = {"commit": _r.stdout.strip() or "unknown", "dirty": bool(_d.stdout.strip())}
        except Exception:
            prov["git"] = {"commit": "unknown", "dirty": False}
    if "env" not in prov:
        # P1-5：环境指纹自动补全（当前 conda 环境的包版本清单，供复现）
        try:
            from tools.env_manager import fingerprint
            _cur = os.environ.get("CONDA_DEFAULT_ENV", "")
            prov["env"] = fingerprint(_cur) if _cur else {"conda_env": "", "packages": {}, "note": "未检测到 conda 环境"}
        except Exception:
            prov["env"] = {"conda_env": "", "packages": {}}
    body = json.dumps(manifest, ensure_ascii=False, indent=2)
    with open(os.path.join(results_dir, f"analysis_manifest.v{ver}.json"), "w", encoding="utf-8") as f:
        f.write(body)
    with open(os.path.join(results_dir, "analysis_manifest.json"), "w", encoding="utf-8") as f:
        f.write(body)
    return ver


@app.post("/api/results/manifest")
async def submit_result_manifest(payload: dict):
    """结果完成契约：保存 analysis_manifest（版本化 + 溯源自动补全）"""
    sid = payload.get("session_id") or ""
    if not sid:
        return JSONResponse({"error": "session_id required"}, status_code=400)
    manifest = payload.get("manifest")
    if not isinstance(manifest, dict):
        return JSONResponse({"error": "manifest must be an object"}, status_code=400)
    base = _find_best_results_dir(sid)
    if not base or not os.path.isdir(base):
        base = os.path.join(RESULTS_DIR, sid)
        os.makedirs(base, exist_ok=True)
    try:
        ver = _save_result_manifest(base, manifest)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return {"ok": True, "version": ver, "path": base.replace("\\", "/")}


@app.get("/api/science/search")
async def science_search(q: str = "", source: str = "arxiv", limit: int = 5):
    """科学文献检索（P1-6，带溯源）：arxiv / openalex

    每条记录携带 {source, query, fetched_at} 溯源元数据，
    入库/引用时保留 provenance（知识库验证铁轨配套）。
    """
    if not q or not q.strip():
        return JSONResponse({"error": "q required"}, status_code=400)
    try:
        from tools.science_connectors import arxiv_search, openalex_search
    except Exception:
        return JSONResponse({"error": "science_connectors 不可用"}, status_code=500)
    if source == "openalex":
        return openalex_search(q.strip(), limit=limit)
    return arxiv_search(q.strip(), limit=limit)


# 文献导入异步任务账本（批I 2026-08-16：导入在后台线程跑，前端轮询进度）
_lit_jobs = {}


def _run_lit_import(job_id: str, paths: list, imported_by: str = ""):
    import json as _json
    from memomics.bio_tools.literature_library import import_pdfs
    try:
        def _cb(phase, done, total, detail):
            _lit_jobs[job_id].update({
                "status": "running", "phase": phase,
                "done": done, "total": total, "current": str(detail)[:120],
            })
        _result = _json.loads(import_pdfs(paths, progress_cb=_cb, imported_by=imported_by))
        _lit_jobs[job_id].update({"status": "done", "result": _result,
                                  "current": f"完成：导入 {_result.get('imported', 0)} 篇"})
    except Exception as e:
        _lit_jobs[job_id].update({"status": "error", "error": str(e)[:300]})


@app.post("/api/literature/import")
async def literature_import(payload: dict):
    """导入本地 PDF 到全局文献库（批F；批I 起异步化：立即返回 job_id，GET 轮询进度）。"""
    paths = payload.get("paths") or []
    if not paths:
        return JSONResponse({"error": "paths required"}, status_code=400)
    import uuid
    job_id = uuid.uuid4().hex[:8]
    _lit_jobs[job_id] = {"job_id": job_id, "status": "running", "phase": "collect",
                         "done": 0, "total": 0, "current": "任务已创建"}
    _imported_by = str(payload.get("session_id") or "")[:64]
    asyncio.create_task(asyncio.to_thread(_run_lit_import, job_id, paths, _imported_by))
    return {"job_id": job_id, "status": "running"}


@app.get("/api/literature/import/{job_id}")
async def literature_import_status(job_id: str):
    """导入进度查询：{status: running/done/error, phase, done, total, current, result}"""
    return _lit_jobs.get(job_id, {"status": "unknown", "error": "job not found"})


def _run_lit_extract(job_id: str, file_or_title: str, extract_all: bool = False):
    import json as _json
    from memomics.bio_tools.literature_library import kb_extract_from_paper, extract_all_papers
    try:
        def _cb(phase, done, total, detail):
            _lit_jobs[job_id].update({
                "status": "running", "phase": phase,
                "done": int(done), "total": int(total), "current": str(detail)[:150],
            })
        if extract_all:
            _result = _json.loads(extract_all_papers(progress_cb=_cb))
        else:
            _result = _json.loads(kb_extract_from_paper(file_or_title, progress_cb=_cb))
        if _result.get("ok"):
            _msg = f"提炼完成：写入 {_result.get('written_total', len(_result.get('written') or []))} 条"
        else:
            _msg = f"提炼失败：{_result.get('error', '未知错误')[:120]}"
        _lit_jobs[job_id].update({"status": "done", "result": _result, "current": _msg})
    except Exception as e:
        _lit_jobs[job_id].update({"status": "error", "error": str(e)[:300]})


@app.post("/api/literature/extract")
async def literature_extract(payload: dict):
    """提炼单篇文献进知识库（批I：异步任务化，立即返回 job_id）。"""
    file_or_title = (payload.get("file_or_title") or "").strip()
    if not file_or_title:
        return JSONResponse({"error": "file_or_title required"}, status_code=400)
    import uuid
    job_id = uuid.uuid4().hex[:8]
    _lit_jobs[job_id] = {"job_id": job_id, "status": "running", "phase": "read",
                         "done": 0, "total": 1, "current": "任务已创建"}
    asyncio.create_task(asyncio.to_thread(_run_lit_extract, job_id, file_or_title, False))
    return {"job_id": job_id, "status": "running"}


@app.post("/api/literature/extract-all")
async def literature_extract_all():
    """一键提炼全部文献进知识库（批I：异步任务化）。"""
    import uuid
    job_id = uuid.uuid4().hex[:8]
    _lit_jobs[job_id] = {"job_id": job_id, "status": "running", "phase": "paper",
                         "done": 0, "total": 0, "current": "任务已创建"}
    asyncio.create_task(asyncio.to_thread(_run_lit_extract, job_id, "", True))
    return {"job_id": job_id, "status": "running"}


def _run_lit_summarize(job_id: str, file_or_title: str, do_all: bool = False, force: bool = False):
    import json as _json
    from memomics.bio_tools.literature_library import summarize_paper, summarize_all_papers
    try:
        def _cb(phase, done, total, detail):
            _lit_jobs[job_id].update({
                "status": "running", "phase": phase,
                "done": int(done), "total": int(total), "current": str(detail)[:150],
            })
        if do_all:
            _result = _json.loads(summarize_all_papers(progress_cb=_cb))
        else:
            _result = _json.loads(summarize_paper(file_or_title, progress_cb=_cb, force=force))
        if _result.get("ok"):
            _msg = (f"全文提炼完成：{_result.get('succeeded', 1)} 篇成功" if do_all
                    else "全文提炼完成（9 项摘要已落盘）")
        else:
            _msg = f"全文提炼失败：{_result.get('error', '未知错误')[:120]}"
        _lit_jobs[job_id].update({"status": "done", "result": _result, "current": _msg})
    except Exception as e:
        _lit_jobs[job_id].update({"status": "error", "error": str(e)[:300]})


@app.post("/api/literature/summarize")
async def literature_summarize(payload: dict):
    """全文思路提炼（方向1，给人看，批J）：9 项摘要，异步任务化。force=true 重新提炼。"""
    file_or_title = (payload.get("file_or_title") or "").strip()
    if not file_or_title:
        return JSONResponse({"error": "file_or_title required"}, status_code=400)
    import uuid
    job_id = uuid.uuid4().hex[:8]
    _lit_jobs[job_id] = {"job_id": job_id, "status": "running", "phase": "read",
                         "done": 0, "total": 1, "current": "任务已创建"}
    _force = bool(payload.get("force"))
    asyncio.create_task(asyncio.to_thread(_run_lit_summarize, job_id, file_or_title, False, _force))
    return {"job_id": job_id, "status": "running"}


@app.post("/api/literature/summarize-all")
async def literature_summarize_all():
    """一键全文提炼：只处理未提炼（summary_done=false）的文章（批J）。"""
    import uuid
    job_id = uuid.uuid4().hex[:8]
    _lit_jobs[job_id] = {"job_id": job_id, "status": "running", "phase": "paper",
                         "done": 0, "total": 0, "current": "任务已创建"}
    asyncio.create_task(asyncio.to_thread(_run_lit_summarize, job_id, "", True))
    return {"job_id": job_id, "status": "running"}


def _run_lit_translate(job_id: str, file_or_title: str, force: bool = False):
    import json as _json
    from memomics.bio_tools.literature_library import translate_paper
    try:
        def _cb(phase, done, total, detail):
            _lit_jobs[job_id].update({
                "status": "running", "phase": phase,
                "done": int(done), "total": int(total), "current": str(detail)[:150],
            })
        _result = _json.loads(translate_paper(file_or_title, progress_cb=_cb, force=force))
        if _result.get("ok"):
            _msg = ("翻译完成（学术中文，段落级对齐，已落盘 translations/）" if not _result.get("skipped")
                    else "该文献已翻译过（幂等跳过）")
        else:
            _msg = f"翻译失败：{_result.get('error', '未知错误')[:120]}"
        _lit_jobs[job_id].update({"status": "done", "result": _result, "current": _msg})
    except Exception as e:
        _lit_jobs[job_id].update({"status": "error", "error": str(e)[:300]})


@app.post("/api/literature/translate")
async def literature_translate(payload: dict):
    """学术中文翻译（批N2 2026-08-16；批O2 2026-08-16 段落级编号直译，保证中英对照 1:1）。
    force=true 重新翻译。"""
    file_or_title = (payload.get("file_or_title") or "").strip()
    if not file_or_title:
        return JSONResponse({"error": "file_or_title required"}, status_code=400)
    import uuid
    job_id = uuid.uuid4().hex[:8]
    _lit_jobs[job_id] = {"job_id": job_id, "status": "running", "phase": "convert",
                         "done": 0, "total": 0, "current": "任务已创建"}
    _force = bool(payload.get("force"))
    asyncio.create_task(asyncio.to_thread(_run_lit_translate, job_id, file_or_title, _force))
    return {"job_id": job_id, "status": "running"}


@app.get("/api/literature/summary")
async def literature_summary(file_or_title: str = ""):
    """查看某篇文献的完整详情（批O 2026-08-16：含 9 项摘要/知识/全套引文）。"""
    if not file_or_title.strip():
        return JSONResponse({"error": "file_or_title required"}, status_code=400)
    try:
        from memomics.bio_tools.literature_library import get_summary
        import json as _json
        return _json.loads(get_summary(file_or_title.strip()))
    except Exception as e:
        return JSONResponse({"error": str(e)[:300]}, status_code=500)


# ── 批O(2026-08-16)：结构化知识提取 / 元数据补全 / 整库引用导出 ──

def _run_lit_knowledge(job_id: str, file_or_title: str, do_all: bool = False, force: bool = False):
    import json as _json
    from memomics.bio_tools.literature_library import extract_paper_knowledge, extract_all_knowledge
    try:
        def _cb(phase, done, total, detail):
            _lit_jobs[job_id].update({
                "status": "running", "phase": phase,
                "done": int(done), "total": int(total), "current": str(detail)[:150],
            })
        if do_all:
            _result = _json.loads(extract_all_knowledge(progress_cb=_cb))
        else:
            _result = _json.loads(extract_paper_knowledge(file_or_title, progress_cb=_cb, force=force))
        if _result.get("ok"):
            _msg = (f"知识提取完成：{_result.get('succeeded', 1)} 篇成功" if do_all
                    else f"知识提取完成：写入 {len(_result.get('written') or [])} 条知识库条目")
        else:
            _msg = f"知识提取失败：{_result.get('error', '未知错误')[:120]}"
        _lit_jobs[job_id].update({"status": "done", "result": _result, "current": _msg})
    except Exception as e:
        _lit_jobs[job_id].update({"status": "error", "error": str(e)[:300]})


@app.post("/api/literature/knowledge")
async def literature_knowledge(payload: dict):
    """单篇结构化知识提取（生物学+生信），异步任务化（批O）。force=true 重新提取。"""
    file_or_title = (payload.get("file_or_title") or "").strip()
    if not file_or_title:
        return JSONResponse({"error": "file_or_title required"}, status_code=400)
    import uuid
    job_id = uuid.uuid4().hex[:8]
    _lit_jobs[job_id] = {"job_id": job_id, "status": "running", "phase": "convert",
                         "done": 0, "total": 1, "current": "任务已创建"}
    _force = bool(payload.get("force"))
    asyncio.create_task(asyncio.to_thread(_run_lit_knowledge, job_id, file_or_title, False, _force))
    return {"job_id": job_id, "status": "running"}


@app.post("/api/literature/knowledge-all")
async def literature_knowledge_all():
    """一键知识提取：只处理未提取（knowledge_done≠true）的文章（批O）。"""
    import uuid
    job_id = uuid.uuid4().hex[:8]
    _lit_jobs[job_id] = {"job_id": job_id, "status": "running", "phase": "paper",
                         "done": 0, "total": 0, "current": "任务已创建"}
    asyncio.create_task(asyncio.to_thread(_run_lit_knowledge, job_id, "", True))
    return {"job_id": job_id, "status": "running"}


def _run_lit_enrich(job_id: str, file_or_title: str, do_all: bool = False):
    import json as _json
    from memomics.bio_tools.literature_library import enrich_paper_metadata, enrich_all_metadata
    try:
        def _cb(phase, done, total, detail):
            _lit_jobs[job_id].update({
                "status": "running", "phase": phase,
                "done": int(done), "total": int(total), "current": str(detail)[:150],
            })
        if do_all:
            _result = _json.loads(enrich_all_metadata(progress_cb=_cb))
        else:
            _result = _json.loads(enrich_paper_metadata(file_or_title, progress_cb=_cb))
        if _result.get("ok"):
            _msg = (f"元数据补全完成：{_result.get('succeeded', 1)} 篇" if do_all
                    else f"元数据补全完成：修正字段 {_result.get('changed') or []}")
        else:
            _msg = f"元数据补全失败：{_result.get('error', '未知错误')[:120]}"
        _lit_jobs[job_id].update({"status": "done", "result": _result, "current": _msg})
    except Exception as e:
        _lit_jobs[job_id].update({"status": "error", "error": str(e)[:300]})


@app.post("/api/literature/enrich")
async def literature_enrich(payload: dict):
    """单篇元数据补全（Crossref：卷/期/页码/PMID/修正乱码与脏 DOI），异步（批O）。"""
    file_or_title = (payload.get("file_or_title") or "").strip()
    if not file_or_title:
        return JSONResponse({"error": "file_or_title required"}, status_code=400)
    import uuid
    job_id = uuid.uuid4().hex[:8]
    _lit_jobs[job_id] = {"job_id": job_id, "status": "running", "phase": "read",
                         "done": 0, "total": 1, "current": "任务已创建"}
    asyncio.create_task(asyncio.to_thread(_run_lit_enrich, job_id, file_or_title, False))
    return {"job_id": job_id, "status": "running"}


@app.post("/api/literature/enrich-all")
async def literature_enrich_all():
    """一键补全全部疑似缺失元数据（卷/期/页/乱码作者/脏 DOI），异步（批O）。"""
    import uuid
    job_id = uuid.uuid4().hex[:8]
    _lit_jobs[job_id] = {"job_id": job_id, "status": "running", "phase": "paper",
                         "done": 0, "total": 0, "current": "任务已创建"}
    asyncio.create_task(asyncio.to_thread(_run_lit_enrich, job_id, "", True))
    return {"job_id": job_id, "status": "running"}


@app.get("/api/literature/export")
async def literature_export():
    """整库引文导出：BibTeX / RIS / GB/T 7714 全量文本（批O 2026-08-16）。"""
    try:
        from memomics.bio_tools.literature_library import export_citations
        import json as _json
        return _json.loads(export_citations())
    except Exception as e:
        return JSONResponse({"error": str(e)[:300]}, status_code=500)


@app.get("/api/literature/bilingual")
async def literature_bilingual(file_or_title: str = ""):
    """双语对照文档（批O4 2026-08-16）：模块(书签/标题)→页码→段落→矩形 映射。

    前端 ⇄对照 视图用：左侧真 PDF（/api/papers/page 渲染，含原图），
    右侧按模块组织的译文；点模块/段落定位原文页并高亮区域。
    """
    if not file_or_title.strip():
        return JSONResponse({"error": "file_or_title required"}, status_code=400)
    try:
        from memomics.bio_tools.literature_library import build_bilingual
        import json as _json
        return _json.loads(build_bilingual(file_or_title.strip()))
    except Exception as e:
        return JSONResponse({"error": str(e)[:300]}, status_code=500)


@app.get("/api/literature/binding")
async def literature_binding(session_id: str = ""):
    """文献库会话绑定：未绑定或 12 小时过期时自动绑定到当前会话（批J）。"""
    try:
        from memomics.bio_tools.literature_library import get_binding, bind_session
        cur = get_binding()
        if session_id and (cur.get("expired") or not cur.get("session_id")):
            cur = bind_session(session_id, force=False)
        return {"ok": True, "auto_bind": cur.get("auto", False), **cur,
                "ttl_hours": 12,
                "note": "绑定 12 小时有效；过期后新会话打开文献库时自动换绑"}
    except Exception as e:
        return JSONResponse({"error": str(e)[:300]}, status_code=500)


@app.post("/api/literature/binding")
async def literature_binding_force(payload: dict):
    """手动绑定文献库到指定会话（force 换绑）。"""
    try:
        from memomics.bio_tools.literature_library import bind_session
        return bind_session(payload.get("session_id", ""), force=True)
    except Exception as e:
        return JSONResponse({"error": str(e)[:300]}, status_code=500)


@app.get("/api/literature/library")
async def literature_library_list():
    """列出全部文献（用户导入 + agent 下载），带期刊/文章名/下载日期标识。"""
    try:
        from memomics.bio_tools.literature_library import list_library
        import json as _json
        return _json.loads(list_library())
    except Exception as e:
        return JSONResponse({"error": str(e)[:300]}, status_code=500)


def _find_best_results_dir(sid: str) -> str:
    """每次实时扫描 results/，找到当前会话的确定分析结果目录。
    
    核心不变式：返回路径必须属于当前会话（通过短ID验证），且必须在 results/ 下。
    这防止了：① 新会话匹配旧会话目录 ② agent 改到桌面等外部路径后污染后续会话。
    
    策略（按优先级）：
    1) state.db cwd — 最权威（rename_results_dir 持久化），需短ID验证
    2) 内存 results_dir — 需在 results/ 下 + 短ID验证
    3) 扫描 results/ 精确匹配
    4) 回退到 results/{sid}（即使不存在，由调用方处理）"""
    short_id = sid.split("-")[-1] if "-" in sid else ""
    _results_base = os.path.abspath(RESULTS_DIR).rstrip(os.sep)
    
    def _is_session_dir(dpath: str) -> bool:
        """验证目录路径确实属于当前会话"""
        if not os.path.isdir(dpath):
            return False
        abs_path = os.path.abspath(dpath)
        # 必须在 results/ 下
        if not (abs_path.startswith(_results_base + os.sep) or abs_path == _results_base):
            return False
        # 目录名必须可追溯到当前会话：含短ID 或 等于 sid
        dirname = os.path.basename(abs_path.rstrip(os.sep))
        if short_id and short_id in dirname:
            return True
        if dirname == sid:
            return True
        return False
    
    # 1. state.db cwd — 最权威来源（rename 时写入，含短ID）
    try:
        db = _get_session_db()
        if db and hasattr(db, '_conn'):
            row = db._conn.execute("SELECT cwd FROM sessions WHERE id = ?", (sid,)).fetchone()
            if row and row[0]:
                cwd = row[0].replace("/", os.sep)
                if _is_session_dir(cwd):
                    return cwd
    except Exception:
        pass
    
    # 2. 内存 results_dir — 需验证属于当前会话
    if sid in _sessions:
        cached = _sessions[sid].get("results_dir", "")
        if cached and _is_session_dir(cached):
            return cached
    
    # 3. 扫描 results/ 目录，精确匹配
    if os.path.isdir(RESULTS_DIR):
        for d in os.listdir(RESULTS_DIR):
            dpath = os.path.join(RESULTS_DIR, d)
            if _is_session_dir(dpath):
                # 同步到内存
                if sid in _sessions:
                    _sessions[sid]["results_dir"] = dpath
                return dpath
    
    # 4. 无匹配 — 回退到 results/{sid}（不信任内存缓存，前面所有验证已失败）
    return os.path.join(RESULTS_DIR, sid)

@app.get("/api/results")
async def list_all_results():
    """列出所有有分析结果目录的会话（包括不在内存中的旧会话）"""
    sessions_with_results = []
    seen_sids = set()
    # 1. 内存中的会话 — 每次实时扫描磁盘
    for sid, s in _sessions.items():
        seen_sids.add(sid)
        rdir = _find_best_results_dir(sid) or s["results_dir"]
        if os.path.isdir(rdir) and any(Path(rdir).iterdir()):
            file_count = sum(1 for _ in Path(rdir).rglob("*") if _.is_file())
            sessions_with_results.append({
                "session_id": sid,
                "title": s["title"],
                "created": s["created"],
                "results_dir": rdir.replace("\\", "/"),
                "file_count": file_count,
                "has_manifest": bool(_load_result_manifest(rdir)),
                "manifest_versions": _list_manifest_versions(rdir),
            })
    # 2. 磁盘上有但内存中没有的旧会话目录
    if os.path.isdir(RESULTS_DIR):
        for p in Path(RESULTS_DIR).iterdir():
            if not p.is_dir() or p.name.startswith("."):
                continue
            sid = p.name
            if sid in seen_sids:
                continue
            try:
                has_content = any(p.iterdir())
            except Exception:
                has_content = False
            if not has_content:
                continue
            file_count = sum(1 for _ in p.rglob("*") if _.is_file())
            mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            sessions_with_results.append({
                "session_id": sid,
                "title": sid,
                "created": mtime,
                "results_dir": str(p).replace("\\", "/"),
                "file_count": file_count,
                "has_manifest": bool(_load_result_manifest(str(p))),
                "manifest_versions": _list_manifest_versions(str(p)),
            })
    # 按修改时间倒序排列（最新在最上面）
    sessions_with_results.sort(key=lambda x: x.get("results_dir", ""), reverse=True)
    # 也可以通过文件数量辅助排序：让有更多文件的目录优先
    sessions_with_results.sort(key=lambda x: (os.path.getmtime(x["results_dir"]) if os.path.isdir(x["results_dir"]) else 0), reverse=True)
    return {"sessions": sessions_with_results, "debug_results_dir": RESULTS_DIR}


@app.get("/api/results/{sid}/tree")
async def results_tree(sid: str):
    """返回会话结果目录的树形结构"""
    base = _find_best_results_dir(sid)
    if not base and sid in _sessions:
        base = _sessions[sid].get("results_dir", "")
    if not base:
        base = os.path.join(RESULTS_DIR, sid)
    if not os.path.isdir(base) or not any(Path(base).iterdir()):
        return {"tree": None, "results_name": "", "total_files": 0, "total_dirs": 0, "note": "No results yet"}

    def _bt(dp):
        ch = []
        tf = 0
        td = 0
        try:
            for p in sorted(Path(dp).iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if p.name.startswith("."):
                    continue
                rel = str(p.relative_to(base)).replace(chr(92), "/")
                if p.is_dir():
                    td += 1
                    sub = _bt(str(p))
                    ch.append({"name": p.name, "path": rel, "is_dir": True, "children": sub["ch"], "mtime": p.stat().st_mtime})
                    tf += sub["tf"]
                    td += sub["td"]
                else:
                    tf += 1
                    ch.append({"name": p.name, "path": rel, "is_dir": False, "size": p.stat().st_size, "mtime": p.stat().st_mtime, "ext": p.suffix.lower()})
        except Exception:
            pass
        return {"ch": ch, "tf": tf, "td": td}

    tree = _bt(base)
    rn = os.path.basename(base)
    return {"tree": {"name": rn, "path": "", "is_dir": True, "children": tree["ch"], "total_files": tree["tf"], "total_dirs": tree["td"]}, "results_name": rn, "total_files": tree["tf"], "total_dirs": tree["td"], "base": base.replace(chr(92), "/"), "session_id": sid}


def _extract_json_obj(s):
    """best-effort：从字符串里抠出第一个 JSON 对象（容忍 ```json 围栏、前后缀说明文字、被截断的尾巴）。"""
    if not isinstance(s, str):
        return None
    t = s.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    try:
        obj = json.loads(t)
        if isinstance(obj, (dict, list)):
            return obj
    except Exception:
        pass
    i = t.find("{")
    while i != -1:
        try:
            obj, _end = json.JSONDecoder().raw_decode(t[i:])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        i = t.find("{", i + 1)
    return None


def _load_latest_debate(sid: str):
    """读取会话 results 目录下最新一场辩论的完整归档（2026-09-18，供 WebUI 渲染辩论过程表格）。

    兼容历史上出现过的 4 种结构：
      v3 多角色 —— pro_arguments/con_arguments = {biology:{argument:...}, ...}
      L1 轻量采样 —— samples = [{pro:..., con:...}]
      v2 —— pro_args/con_args = [{role, argument}]
      失败记录 —— error=true + failed_roles
    外层若被 result_summary 包一层（会话级归档），自动剥掉。
    只读，绝不抛异常给调用方。
    """
    base = ""
    try:
        base = _find_best_results_dir(sid) or ""
    except Exception:
        base = ""
    if not base and sid in _sessions:
        base = (_sessions.get(sid) or {}).get("results_dir") or ""
    if not base:
        base = os.path.join(RESULTS_DIR, sid)
    if not base or not os.path.isdir(base):
        return {"ok": False, "error": "未找到该会话的结果目录", "base": str(base)}
    try:
        files = [p for p in Path(base).rglob("debate_*.json") if p.is_file()]
    except Exception as e:
        return {"ok": False, "error": f"扫描辩论记录失败: {e}", "base": str(base)}
    if not files:
        return {"ok": False, "error": "该会话还没有辩论记录文件", "base": str(base).replace("\\", "/")}

    def _mtime(x):
        try:
            return x.stat().st_mtime
        except Exception:
            return 0.0

    def _usable(x):
        """这份归档能不能渲染出「辩论过程」表。"""
        if not isinstance(x, dict):
            return False
        if x.get("pro_arguments") or x.get("con_arguments") or x.get("samples") \
                or x.get("pro_args") or x.get("con_args"):
            return True
        if x.get("error") or x.get("failed_role_ids"):
            return True   # 失败场也要展示（能看到失败角色/原因）
        return bool(x.get("judge_verdict") and (x.get("level") or x.get("verdict")))

    def _read_debate(p):
        try:
            x = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return None
        if isinstance(x, dict) and "result_summary" in x and "pro_arguments" not in x:
            inner = _extract_json_obj(x.get("result_summary"))
            if isinstance(inner, dict):
                x = inner
        return x

    files.sort(key=_mtime, reverse=True)
    files = files[:60]
    newest = files[0]
    # 会话级结论归档（conclusions/debate_*.json）常是 result_summary 被截断的副本，会排在最新 ——
    # 因此不能只取最新一份，要往下找最近一份「能渲染」的（24h 窗口内，避免翻出陈年旧辩论）。
    newest_mt = _mtime(newest)
    picked, picked_data = None, None
    for _p in files:
        _mt = _mtime(_p)
        if newest_mt - _mt > 6 * 3600:
            break   # 只在这「同一场辩论」的归档批次里回退，避免翻出很久以前的旧辩论
        _x = _read_debate(_p)
        if _usable(_x):
            picked, picked_data = _p, _x
            break
    if picked is None:
        return {"ok": False, "path": str(newest), "candidate_count": len(files),
                "error": "最近这场辩论没有可展示的编辑论点（可能失败了，或归档被截断成摘要）",
                "base": str(base).replace("\\", "/")}
    st = None
    try:
        st = picked.stat()
    except Exception:
        pass
    skipped = []
    for _p in files:
        if _p == picked:
            break
        skipped.append(str(_p))
    return {
        "ok": True,
        "path": str(picked),
        "rel_path": str(picked.relative_to(base)).replace("\\", "/") if base else picked.name,
        "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S") if st else "",
        "mtime_epoch": st.st_mtime if st else 0,
        "skipped_newer": skipped,
        "debate": picked_data,
    }


# ============ 辩论时间线（2026-09-18 v2：多场辩论各自回到它发生的位置）============
# 用户诉求：一次分析里跑了好几场辩论时，卡片不能全堆在对话末尾 —— 每场要落在它真正
# 发生的那一刻（前后就是当时的对话内容），点开才看细节。
# 因此给每场辩论算一个 after_index：该场辩论开始前，对话流里已经有多少条
# user/assistant 消息（与 /messages 完全同一套过滤规则），前端据此把卡片插回原位。
_DEBATE_KEY_RE = re.compile(r"debate_(\d{8}_\d{6})")

_DEBATE_VERDICT_MAP = {
    "ok": ("方案成立，可以照此执行", "ok"),
    "support": ("支持正方主张", "ok"),
    "support_pro": ("支持正方主张", "ok"),
    "pro": ("支持正方主张", "ok"),
    "pro_wins": ("支持正方主张", "ok"),
    "modify": ("方案要改，改完再用", "warn"),
    "modify_first": ("方案要改，改完再用", "warn"),
    "need_more_info": ("证据不足，先补数据再下结论", "warn"),
    "insufficient_evidence": ("证据不足，先补数据再下结论", "warn"),
    "reject": ("否决该方案", "con"),
    "support_con": ("支持反方主张", "con"),
    "con": ("支持反方主张", "con"),
    "con_wins": ("支持反方主张", "con"),
}


def _debate_base_of(sid: str) -> str:
    """会话的结果根目录（失败返回空串，绝不抛异常）。"""
    base = ""
    try:
        base = _find_best_results_dir(sid) or ""
    except Exception:
        base = ""
    if not base and sid in _sessions:
        base = (_sessions.get(sid) or {}).get("results_dir") or ""
    if not base:
        base = os.path.join(RESULTS_DIR, sid)
    return base if (base and os.path.isdir(base)) else ""


def _read_debate_file(p):
    """读一份辩论归档；外层被 result_summary 包一层时自动剥掉。读不了返回 None。"""
    try:
        x = json.loads(Path(p).read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    if isinstance(x, dict) and "result_summary" in x and "pro_arguments" not in x:
        inner = _extract_json_obj(x.get("result_summary"))
        if isinstance(inner, dict):
            x = inner
    return x


def _debate_richness(x) -> int:
    """归档的信息量打分：同一场辩论常同时落 log/ 与 conclusions/ 两份，
    取信息量大的那份（conclusions 副本常被截断）。"""
    if not isinstance(x, dict):
        return -1
    n = 0
    if x.get("pro_arguments") or x.get("pro_args") or x.get("samples"):
        n += 40
    if x.get("con_arguments") or x.get("con_args"):
        n += 20
    if x.get("judge_verdict"):
        n += 15
    if isinstance(x.get("judge_digest"), dict) and x.get("judge_digest"):
        n += 25
    if x.get("neutral_reviews"):
        n += 8
    if x.get("error"):
        n -= 30
    try:
        n += min(len(json.dumps(x, ensure_ascii=False)) // 2000, 20)
    except Exception:
        pass
    return n


def _debate_display_count(sid: str, ts_epoch: float = 0.0) -> int:
    """对话流（user/assistant，非注入）里的消息条数。

    ts_epoch>0 时只数 timestamp <= ts_epoch 的（= 这场辩论开始前已经说完的话）。
    失败返回 -1，前端会退化成「追加到末尾」。"""
    try:
        import sqlite3 as _sq
        _dbp = os.path.join(HERMES_HOME_DIR, "state.db")
        if not os.path.exists(_dbp):
            return -1
        _conn = _sq.connect(f"file:{_dbp}?mode=ro", uri=True, timeout=8)
        try:
            _rows = _conn.execute(
                "SELECT content, timestamp FROM messages WHERE session_id=? AND role IN ('user','assistant') "
                "AND content IS NOT NULL AND length(content)>0 ORDER BY id",
                (sid,),
            ).fetchall()
        finally:
            _conn.close()
        n = 0
        for _c, _ts in _rows:
            if str(_c or "").lstrip().startswith(_INJECT_PREFIXES):
                continue
            if ts_epoch and not (_ts and float(_ts) <= float(ts_epoch)):
                continue
            n += 1
        return n
    except Exception:
        return -1


def _debate_verdict_bits(x: dict):
    """(结论文字, tone, 置信度原文, 置信度中文)"""
    v = str(x.get("verdict") or "").strip()
    conf = str(x.get("confidence") or "").strip()
    jv = x.get("judge_verdict")
    if isinstance(jv, dict):
        if not v:
            v = str(jv.get("verdict") or "").strip()
        if not conf:
            conf = str(jv.get("confidence") or "").strip()
    label, tone = _DEBATE_VERDICT_MAP.get(v.lower(), ("", "none"))
    if not label:
        label = ("本次没有给出裁决" if not v else ("裁决：" + v))
        tone = "none"
    conf_cn = {"high": "高", "medium": "中", "low": "低"}.get(conf.lower(), conf)
    return label, tone, conf, conf_cn


def _debate_one_line(x: dict, limit: int = 300) -> str:
    """一句话依据：先说整理稿总结，其次裁判正文首句；都没有就给空串。"""
    cands = []
    d = x.get("judge_digest")
    if isinstance(d, dict):
        for k in ("summary", "overview", "note"):
            if d.get(k):
                cands.append(str(d.get(k)))
    jv = x.get("judge_verdict")
    if isinstance(jv, dict):
        for k in ("reasoning", "summary", "conclusion", "text"):
            if jv.get(k):
                cands.append(str(jv.get(k)))
    elif isinstance(jv, str) and jv.strip():
        s = jv.strip()
        if s.startswith("{"):
            try:
                o = json.loads(s)
                if isinstance(o, dict):
                    for k in ("reasoning", "summary", "conclusion", "text", "verdict_reason"):
                        if o.get(k):
                            cands.append(str(o.get(k)))
            except Exception:
                pass
        else:
            cands.append(s)
    for k in ("reasoning", "summary"):
        if x.get(k):
            cands.append(str(x.get(k)))
    for c in cands:
        c = " ".join(str(c).split())
        if not c:
            continue
        if c.startswith("{") or c.startswith("[reasoning"):
            continue          # 裁判原始 JSON / 未精炼的 reasoning 草稿都不作一句话依据
        if len(c) > limit:
            cut = -1
            for sep in ("。", "；", ". ", "! ", "? "):
                i = c.find(sep, 40, limit)
                if i > 0 and (cut < 0 or i < cut):
                    cut = i + len(sep)
            c = c[:cut] if cut > 0 else (c[:limit] + "…")
        return c
    return ""


def _debate_topic_of(x: dict) -> str:
    """辩题：优先 topic；老归档没记时退回 debate_config.topic / note 首行。"""
    cands = [x.get("topic")]
    cfg = x.get("debate_config")
    if isinstance(cfg, dict):
        cands.append(cfg.get("topic"))
    note = x.get("note")
    if isinstance(note, str) and note.strip():
        cands.append(note.strip().splitlines()[0])
    for c in cands:
        c = " ".join(str(c or "").split())
        if c:
            return c
    return ""


def _debate_roles_of(x: dict):
    """(正反角色名列表, 模型名列表)"""
    names, models = [], []

    def _addm(v):
        s = str(v or "").strip()
        if s and s not in models:
            models.append(s)

    for k in ("pro_arguments", "con_arguments"):
        v = x.get(k)
        if isinstance(v, dict):
            for kk, vv in v.items():
                names.append(str(kk))
                if isinstance(vv, dict):
                    _addm(vv.get("model") or vv.get("_model") or vv.get("llm"))
        elif isinstance(v, list):
            for e in v:
                if isinstance(e, dict):
                    names.append(str(e.get("role") or e.get("name") or e.get("seat") or "?"))
                    _addm(e.get("model"))
    if isinstance(x.get("samples"), list):
        for i, e in enumerate(x["samples"]):
            names.append("sample%d" % (i + 1))
            if isinstance(e, dict):
                _addm(e.get("pro_model") or e.get("model"))
    _addm(x.get("judge_model"))
    _addm(x.get("judge_digest_model"))
    for e in (x.get("neutral_reviews") or []):
        if isinstance(e, dict):
            _addm(e.get("model"))
    return names, models


def _debate_index_entry(sid: str, base: str, rel: str, abspath: str, x: dict, key: str, mt: float):
    label, tone, conf, conf_cn = _debate_verdict_bits(x)
    names, models = _debate_roles_of(x)
    d = x.get("judge_digest") if isinstance(x.get("judge_digest"), dict) else {}
    # 2026-09-18 v4：赛前场景预判（辩论前先判「这是哪类问题」→ 席位身份与裁判 rubric 按场景生成）
    sc = x.get("scenario") if isinstance(x.get("scenario"), dict) else {}
    return {
        "key": key,
        "rel_path": rel,
        "path": abspath,
        "mtime": datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M:%S") if mt else "",
        "mtime_epoch": mt,
        "after_index": _debate_display_count(sid, mt),
        "topic": _debate_topic_of(x),
        "verdict": str(x.get("verdict") or "").strip(),
        "confidence": conf,
        "confidence_cn": conf_cn,
        "conclusion": label,
        "tone": tone,
        "why": _debate_one_line(x),
        "level": str(x.get("level") or "").strip(),
        "format": str(x.get("debate_format") or "").strip(),
        "roles": len(names),
        "drafts": len(x.get("draft_only_roles") or []),
        "has_digest": bool(d),
        "failed": bool(x.get("error")),
        # 场景预判：折叠卡片不加载全文也能显示「这场按什么场景/谁的尺子判的」
        "scenario": str(sc.get("scenario") or "").strip(),
        "scenario_label": str(sc.get("scenario_label") or "").strip(),
        "scenario_why": str(sc.get("why") or "").strip(),
        "scenario_judge": str(sc.get("judge_persona") or "").strip(),
        "scenario_rubrics": [str((r or {}).get("key") or "").strip()
                             for r in (sc.get("rubrics") or []) if isinstance(r, dict)][:8],
        "scenario_error": str(x.get("scenario_error") or "").strip()[:200],
        "has_scenario": bool(sc),
        "models": models[:8],
    }


def _load_debate_index(sid: str):
    """该会话全部辩论场次（时间正序）。

    同一场辩论会落多份归档（log/ 全量 + conclusions/ 摘要副本），按文件名里的
    时间戳 debate_YYYYMMDD_HHMMSS 归组，每组取信息量最大的那份。"""
    base = _debate_base_of(sid)
    if not base:
        return {"ok": False, "error": "未找到该会话的结果目录", "base": str(base), "debates": []}
    try:
        files = [p for p in Path(base).rglob("debate_*.json") if p.is_file()]
    except Exception as e:
        return {"ok": False, "error": f"扫描辩论记录失败: {e}", "base": str(base).replace("\\", "/"), "debates": []}
    if not files:
        return {"ok": True, "count": 0, "base": str(base).replace("\\", "/"), "debates": []}
    groups = {}
    for p in files:
        try:
            st = p.stat()
        except Exception:
            continue
        m = _DEBATE_KEY_RE.search(p.name)
        key = m.group(1) if m else ("t%d" % int(st.st_mtime))
        g = groups.setdefault(key, {"mt": st.st_mtime, "files": []})
        g["mt"] = max(g["mt"], st.st_mtime)
        g["files"].append((st.st_mtime, str(p)))
    # 每个文件名时间戳先各自挑出信息量最大的那份
    picked = []
    for key in sorted(groups, key=lambda k: groups[k]["mt"]):
        best = None
        for _mt, ps in sorted(groups[key]["files"], key=lambda t: -t[0]):
            x = _read_debate_file(ps)
            if not isinstance(x, dict):
                continue
            sc = _debate_richness(x)
            if best is None or sc > best[0]:
                best = (sc, ps, x, _mt)
        if best is None:
            continue
        picked.append({"key": key, "score": best[0], "path": best[1], "data": best[2], "mt": best[3]})

    # 再合并「同一场辩论的重复归档」：时间相差很近、且辩题相同或一方没记辩题。
    # 实测 conclusions/ 摘要副本的文件名时间戳会比 log/ 全量版晚 1 秒，必须合掉。
    merged = []
    for it in picked:
        t_new = _debate_topic_of(it["data"])
        if merged:
            prev = merged[-1]
            t_old = _debate_topic_of(prev["data"])
            if (it["mt"] - prev["mt"]) <= 300 and (not t_new or not t_old or t_new == t_old):
                if it["score"] > prev["score"]:
                    merged[-1] = it
                else:
                    merged[-1]["mt"] = max(prev["mt"], it["mt"])
                continue
        merged.append(it)

    out = []
    for it in merged:
        ps, x = it["path"], it["data"]
        try:
            rel = str(Path(ps).relative_to(base)).replace("\\", "/")
        except Exception:
            rel = Path(ps).name
        out.append(_debate_index_entry(sid, base, rel, ps, x, it["key"], it["mt"]))
    return {"ok": True, "count": len(out), "base": str(base).replace("\\", "/"), "debates": out}


@app.get("/api/results/{sid}/debates")
async def list_debates(sid: str):
    """该会话全部辩论场次（时间正序，含 after_index = 插回对话流的位置）。"""
    return JSONResponse(_load_debate_index(sid),
                        headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@app.get("/api/results/{sid}/debate/one")
async def one_debate(sid: str, rel: str = ""):
    """按 rel_path 取某一整场辩论的完整归档（前端展开卡片时才拉取）。"""
    base = _debate_base_of(sid)
    if not base or not rel:
        return JSONResponse({"ok": False, "error": "缺少 path 或会话结果目录不存在"},
                            headers={"Cache-Control": "no-store"})
    try:
        p = Path(base) / rel
        rp, rb = os.path.realpath(str(p)), os.path.realpath(base)
        if not rp.startswith(rb) or not Path(rp).name.startswith("debate_") or not rp.endswith(".json") or not os.path.isfile(rp):
            return JSONResponse({"ok": False, "error": "路径不在本会话的辩论归档里"},
                                headers={"Cache-Control": "no-store"})
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"路径解析失败: {e}"}, headers={"Cache-Control": "no-store"})
    x = _read_debate_file(rp)
    if not isinstance(x, dict):
        return JSONResponse({"ok": False, "error": "辩论归档读不出来（可能正在写或已损坏）"},
                            headers={"Cache-Control": "no-store"})
    try:
        st = os.stat(rp)
        mt, mts = st.st_mtime, datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        mt, mts = 0.0, ""
    return JSONResponse({
        "ok": True, "path": rp, "rel_path": str(Path(rp).relative_to(base)).replace("\\", "/"),
        "mtime": mts, "mtime_epoch": mt, "debate": x,
        "after_index": _debate_display_count(sid, mt),
    }, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@app.get("/api/results/{sid}/debate/latest")
async def latest_debate(sid: str):
    """最新一场辩论的完整记录（WebUI「辩论过程」表格数据源）。"""
    return JSONResponse(_load_latest_debate(sid),
                        headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@app.get("/api/results/{sid}/figures")
async def list_figures(sid: str, sort: str = "time_desc"):
    """列出会话所有 figures（递归扫描 png/jpg/svg/pdf）

    sort（P5 2026-09-22）：time_desc（默认，最新出的图排最上面）/ time_asc（旧行为）/ name
    """
    # 每次实时扫描
    base = _find_best_results_dir(sid)
    if not base and sid in _sessions:
        base = _sessions[sid]["results_dir"]
    if not base:
        base = os.path.join(RESULTS_DIR, sid)
    if not os.path.isdir(base):
        return {"figures": [], "base": base.replace("\\", "/")}
    figures = []
    img_exts = {'.png', '.jpg', '.jpeg', '.svg', '.pdf'}
    try:
        def _fig_mtime(x):
            try:
                return x.stat().st_mtime
            except OSError:
                return 0
        _sort_mode = (sort or "time_desc").strip().lower()
        if _sort_mode == "name":
            _fig_key = lambda x: x.name.lower()
        elif _sort_mode == "time_asc":
            _fig_key = _fig_mtime
        else:
            _fig_key = lambda x: -_fig_mtime(x)
        for p in sorted(Path(base).rglob("*"), key=_fig_key):
            if p.is_file() and p.suffix.lower() in img_exts:
                rel = str(p.relative_to(base)).replace("\\", "/")
                parts = rel.split("/")
                category = parts[0] if len(parts) > 1 else "root"
                _st = p.stat()
                figures.append({
                    "name": p.name,
                    "rel_path": rel,
                    "category": category,
                    "url": f"/api/results/{sid}/figure?path={rel}",
                    "size": _st.st_size,
                    "mtime": datetime.fromtimestamp(_st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "mtime_epoch": _st.st_mtime,
                    "ext": p.suffix.lower(),
                })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"figures": figures, "base": base.replace("\\", "/"), "session_id": sid, "sort": _sort_mode},
                        headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@app.get("/api/results/{sid}/figure")
async def get_figure(sid: str, path: str = ""):
    """返回会话下的图片文件 — 每次实时扫描磁盘"""
    base = _find_best_results_dir(sid)
    if not base and sid in _sessions:
        base = _sessions[sid]["results_dir"]
    if not base:
        base = os.path.join(RESULTS_DIR, sid)
    file_path = os.path.join(base, path) if path else base
    if not os.path.isfile(file_path):
        return JSONResponse({"error": "File not found"}, status_code=404)
    # 防止路径遍历
    if not os.path.abspath(file_path).startswith(os.path.abspath(base)):
        return JSONResponse({"error": "Access denied"}, status_code=403)
    return FileResponse(file_path, headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})


# --- P3(2026-09-22): 意图确认弹窗答复 ---

class AskFormAnswerRequest(BaseModel):
    session_id: str
    form_id: str = ""
    selected: list = []      # 勾选的选项文字
    other: str = ""          # "其他"自由填写
    question: str = ""       # 原问题（前端回传，用于审计兜底）


@app.post("/api/ask_form/answer")
async def ask_form_answer(req: AskFormAnswerRequest):
    """接收确认弹窗的勾选结果：记录 → 解除执行门禁 → 前端再把它作为用户消息发出。

    为什么这么设计：弹窗答复本身就是用户消息（沿用既有 chat 通道，零新轨道），
    这里负责把它结构化留档（审计/复盘）+ 解除 enforcement 的执行门禁。
    """
    sid = (req.session_id or "").strip()
    if sid not in _sessions:
        _restore_single_session(sid)
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    sess = _sessions[sid]
    sel = [str(s).strip() for s in (req.selected or []) if str(s).strip()]
    other = (req.other or "").strip()
    if not sel and not other:
        return JSONResponse({"error": "需要至少勾选一项或填写其他内容"}, status_code=400)
    # 找到对应的待确认问题（按 form_id；没有则取最后一条未答复的）
    _pend = sess.get("_pending_questions") or []
    _hit = None
    for _pq in reversed(_pend):
        if req.form_id and _pq.get("form_id") == req.form_id:
            _hit = _pq
            break
    if _hit is None:
        for _pq in reversed(_pend):
            if not _pq.get("answered"):
                _hit = _pq
                break
    _q_text = (_hit or {}).get("question") or req.question or ""
    if _hit is not None:
        _hit["answered"] = True
        _hit["answer"] = {"selected": sel, "other": other,
                          "answered_at": datetime.now().strftime("%H:%M:%S")}
    # 组装给模型看的人话（前端也用它作为用户消息）
    _parts = []
    if sel:
        _parts.append("选中：" + "；".join(sel))
    if other:
        _parts.append("补充说明：" + other)
    _answer_text = ("【用户对「" + _q_text[:120] + "」的确认答复】" + "；".join(_parts)) if _q_text \
        else ("【用户确认答复】" + "；".join(_parts))
    # P4(2026-09-22): 前端提交弹窗后自己拼消息再发（措辞与 _answer_text 不同）→
    # 打一个 30 秒有效的一次性标记，让下一轮能可靠认出"这是弹窗答复，不是新需求"
    sess["_form_ans_marker"] = time.time()
    sess.setdefault("_ask_form_answers", []).append({
        "form_id": req.form_id or (_hit or {}).get("form_id", ""),
        "question": _q_text, "selected": sel, "other": other,
        "answer_text": _answer_text,
        "_ts": time.time(),
        "injected": False,
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    del sess["_ask_form_answers"][:-20]
    # 用户答复了确认表单 = 意图已确认（本会话不再重复问）
    sess["_intent_confirmed"] = True
    # 解除执行门禁（P3：意图确认后才允许执行）
    _gate_cleared = False
    try:
        from webui import enforcement as _enf_f
        _es_f = _enf_f.get_enforcement(sid)
        _gate_cleared = _enf_f.clear_awaiting_form(_es_f, req.form_id or "",
                                                   {"selected": sel, "other": other,
                                                    "question": _q_text})
    except Exception as _e_f:
        logger.warning(f"[ask_form] 解除门禁失败: {_e_f}")
    # P4(2026-09-22): 代码修改模式的答复语义 —— 与 P3 不同："答复"不默认解锁。
    #   选"只给我改好的代码，先别跑" → 锁继续（这正是他的本意）
    #   选"用这些数据跑一遍验证"   → 解锁并允许执行
    _ce_state = ""
    try:
        from webui import enforcement as _enf_cea
        _es_cea = _enf_cea.get_enforcement(sid)
        if getattr(_es_cea, "code_edit", False) or _enf_cea.code_edit_pending(_es_cea):
            _ans_all = (" ".join(sel) + " " + other).strip()
            _ans_low = _ans_all.lower()
            # 英文按钮可能首字母大写（"Run a verification…"），英文关键词一律大小写无关
            _want_run = (any(w in _ans_all for w in ("验证", "跑", "测试", "执行", "试一下", "试下"))
                         or any(w in _ans_low for w in ("run", "test", "verify", "execute")))
            # 中英都要认：英文按钮 "Code only, do not run" 里带 run，若不认这些否定词会被误判成「要跑」
            _want_no = (any(w in _ans_all for w in
                            ("先别", "不要跑", "别跑", "不跑", "只给", "只看", "不执行", "先给"))
                        or any(w in _ans_low for w in
                               ("code only", "only the code", "only code", "just the code",
                                "just give me the code", "do not run", "don't run", "dont run",
                                "not run", "no run", "without running", "do not execute",
                                "don't execute", "no execution", "not execute")))
            if _want_run and not _want_no:
                _enf_cea.clear_code_edit(_es_cea, grant_exec=True)
                _gate_cleared = True
                _ce_state = "verify_ok"
            else:
                _enf_cea.arm_code_edit(
                    _es_cea, "用户选择：只给代码、不要执行（答复：%s）" % _ans_all[:80],
                    data=getattr(_es_cea, "code_edit_data", []) or [])
                _ce_state = "edit_only"
            logger.info(f"[code_edit] sid={sid} 答复={_ans_all[:60]!r} → {_ce_state}")
    except Exception as _e_cea:
        logger.warning(f"[code_edit] 答复处理失败: {_e_cea}")
    try:
        _session_emit(sess, {"type": "ask_form_answered", "form_id": req.form_id,
                             "question": _q_text, "selected": sel, "other": other,
                             "gate_cleared": _gate_cleared,
                             "code_edit": _ce_state,
                             "ts": datetime.now().strftime("%H:%M:%S"), "session_id": sid})
    except Exception:
        pass
    logger.info(f"[ask_form] sid={sid} form={req.form_id} selected={sel} other={other[:60]!r} gate_cleared={_gate_cleared}")
    return {"ok": True, "question": _q_text, "selected": sel, "other": other,
            "answer_text": _answer_text, "gate_cleared": _gate_cleared,
            "code_edit": _ce_state}


# --- P1-1 (2026-09-23): 会话目标条（goal）+ 待办持久化 ---
#
# 借鉴 deer-flow 的两条语义（backend/.../agents/thread_state.py:120-137 的 merge_todos/merge_goal）：
#   · None = 本次没动它 → 保留旧值（别把「没传」当成「清空」）
#   · []   = 显式清空
# 数据形状参考 agents/goal_state.py:22-31（objective/status/created_at/updated_at）。
# 不抄 deer-flow 的「自动续跑 + LLM 评估器」——MemOmics 这一层只做「目标 + 进度上屏」。

_GOAL_MAX_LEN = 4000
_GOAL_STATUSES = ("active", "done", "blocked", "cancelled")


def _kv_get(key, default=None):
    """读 Hermes state.db 的 kv 表（与微信会话映射同一张表，见 _get_session_db）。"""
    try:
        db = _get_session_db()
        if not db or not getattr(db, "_conn", None):
            return default
        row = db._conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        if row and row[0] not in (None, ""):
            return row[0]
    except Exception:
        pass
    return default


def _kv_set(key, value):
    try:
        db = _get_session_db()
        if not db or not getattr(db, "_conn", None):
            return False
        db._conn.execute(
            "INSERT INTO kv (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
        db._conn.commit()
        return True
    except Exception as e:
        logger.warning(f"[kv] 写入失败 key={key}: {e}")
        return False


def _todos_public(todos):
    """把任意来源的待办归一成前端认识的四项 {id,title,status,module}。"""
    out = []
    if not isinstance(todos, list):
        return out
    for t in todos:
        if not isinstance(t, dict):
            continue
        out.append({
            "id": str(t.get("id", "") or ""),
            "title": str(t.get("title") or t.get("content") or t.get("name") or ""),
            "status": str(t.get("status") or "pending"),
            "module": str(t.get("module", "") or ""),
        })
    return out


def _kv_ns(kind, sid):
    return f"memomics_{kind}:{sid}"


def _sync_session_todos(session, todos, persist=True):
    """把待办写回会话（None = 保留旧值，[] = 显式清空），内容变了才落库。

    返回归一化后的列表。revision 供前端做乐观更新对账（抄 deer-flow
    use-active-goal.ts:15-68 的「服务器一回报就丢弃本地覆盖」）。
    """
    if todos is None:
        return _todos_public(session.get("todos"))
    pub = _todos_public(todos)
    sid = session.get("id", "")
    try:
        blob = json.dumps(pub, ensure_ascii=False, sort_keys=True)
    except Exception:
        blob = ""
    if session.get("_todos_blob") != blob:
        session["todos"] = pub
        session["_todos_blob"] = blob
        session["todos_revision"] = int(session.get("todos_revision", 0) or 0) + 1
        if persist and sid:
            _kv_set(_kv_ns("todos", sid), blob)
    return pub


def _session_todos(session):
    """读会话待办：内存优先，其次 state.db（服务重启后仍在）。"""
    todos = session.get("todos")
    if todos:
        return _todos_public(todos)
    sid = session.get("id", "")
    if sid:
        raw = _kv_get(_kv_ns("todos", sid))
        if raw:
            try:
                cached = json.loads(raw)
            except Exception:
                cached = None
            if isinstance(cached, list) and cached:
                session["todos"] = _todos_public(cached)
                session["_todos_blob"] = raw
                return session["todos"]
    return _todos_public(todos)


def _goal_get(session):
    """读会话目标：内存优先，其次 state.db。"""
    goal = session.get("goal")
    if isinstance(goal, dict) and goal.get("objective"):
        return goal
    sid = session.get("id", "")
    if sid:
        raw = _kv_get(_kv_ns("goal", sid))
        if raw:
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = None
            if isinstance(parsed, dict) and parsed.get("objective"):
                session["goal"] = parsed
                return parsed
    return None


def _goal_set(session, objective, status="active", source="manual"):
    objective = (objective or "").strip()
    if not objective:
        return None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    old = _goal_get(session) or {}
    goal = {
        "objective": objective[:_GOAL_MAX_LEN],
        "status": status if status in _GOAL_STATUSES else "active",
        "source": source if source in ("manual", "auto") else "manual",
        "created_at": old.get("created_at") or now,
        "updated_at": now,
        "revision": int(old.get("revision", 0) or 0) + 1,
    }
    session["goal"] = goal
    sid = session.get("id", "")
    if sid:
        _kv_set(_kv_ns("goal", sid), json.dumps(goal, ensure_ascii=False))
    return goal


def _goal_clear(session):
    session["goal"] = None
    sid = session.get("id", "")
    if sid:
        _kv_set(_kv_ns("goal", sid), "")


def _goal_payload(session):
    """给前端的统一目标条载荷（progress / goal 两个端点共用一份形状）。"""
    return {
        "goal": _goal_get(session),
        "todos": _session_todos(session),
        "todos_revision": int(session.get("todos_revision", 0) or 0),
    }


class GoalRequest(BaseModel):
    objective: str = ""
    status: str = "active"
    source: str = "manual"


@app.get("/api/sessions/{sid}/goal")
async def get_session_goal(sid: str):
    """P1-1: 会话目标（目标条数据源）"""
    if sid not in _sessions:
        _restore_single_session(sid)
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    session = _sessions[sid]
    return _goal_payload(session)


@app.put("/api/sessions/{sid}/goal")
async def put_session_goal(sid: str, req: GoalRequest):
    """P1-1: 设置会话目标（objective 为空 = 无效；要清空请用 DELETE）"""
    if sid not in _sessions:
        _restore_single_session(sid)
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    objective = (req.objective or "").strip()
    if not objective:
        return JSONResponse({"error": "objective 不能为空"}, status_code=400)
    if len(objective) > _GOAL_MAX_LEN:
        return JSONResponse({"error": f"objective 过长（>{_GOAL_MAX_LEN}）"}, status_code=400)
    if req.status not in _GOAL_STATUSES:
        return JSONResponse({"error": f"status 必须是 {list(_GOAL_STATUSES)}"}, status_code=400)
    session = _sessions[sid]
    goal = _goal_set(session, objective, status=req.status, source=req.source)
    payload = _goal_payload(session)
    _session_emit(session, {"type": "goal_update", **payload,
                            "ts": datetime.now().strftime("%H:%M:%S")})
    return {"ok": True, **payload}


@app.delete("/api/sessions/{sid}/goal")
async def delete_session_goal(sid: str):
    """P1-1: 清空会话目标"""
    if sid not in _sessions:
        _restore_single_session(sid)
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    session = _sessions[sid]
    _goal_clear(session)
    payload = _goal_payload(session)
    _session_emit(session, {"type": "goal_update", **payload,
                            "ts": datetime.now().strftime("%H:%M:%S")})
    return {"ok": True, **payload}


@app.delete("/api/sessions/{sid}/todos")
async def delete_session_todos(sid: str):
    """P1-1(2026-09-24): 清空会话待办 —— 目标条上「清空」按钮的落点。

    只清展示副本（session["todos"] + state.db 的 kv），**不动** agent 的
    _todo_store：那本书是 agent 自己的执行状态，下次它推新待办时这里照样会出现。
    语义同 goal：[] = 显式清空（_sync_session_todos 会涨 revision 并广播）。
    """
    if sid not in _sessions:
        _restore_single_session(sid)
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    session = _sessions[sid]
    _sync_session_todos(session, [], persist=True)
    payload = {"todos": [], "revision": int(session.get("todos_revision", 0) or 0)}
    _session_emit(session, {"type": "todos_update", "todos": [],
                            "ts": datetime.now().strftime("%H:%M:%S"),
                            "session_id": session["id"]})
    return {"ok": True, **payload}


# --- P1-2 (2026-09-23): 改动复核（跑前跑后快照 + diff + 单文件回滚） ---
#
# 借鉴 deer-flow 的部分（workspace_changes/types.py:63-116 的 WorkspaceFileChange 形状、
# :18-26 的体积上限、api.py:18-48 的「轻量列表 / 完整内容两次取」）：
#   path / change_type / lines_added / lines_removed / sha 前后值 / 轻量列表带预览。
# deer-flow 没有的部分（这里是自己设计的，别处抄不到）：
#   · 单文件回滚（POST .../revert）：写回改前内容，且要求当前内容仍等于改动后的 sha，
#     否则 409 拒绝——防止把用户/别的程序后来的修改一起覆盖掉。
#   · 跳过的改动也要能看见（超大/二进制文件不记 diff，但列表里给出原因）。

_WRITER_TOOLS = {"write_file", "patch", "edit_file", "str_replace", "apply_patch", "create_file"}
_CHANGE_MAX_FILE_BYTES = 262144     # 单文件快照上限 256KB（超过只记"跳过+原因"）
_CHANGE_MAX_KEEP = 200              # 每会话保留最近 200 条
_CHANGE_MAX_DIFF_LINES = 400        # 单条 diff 最多存 400 行
_CHANGE_MAX_STORE_BYTES = 262144    # 落 state.db 的总量上限 256KB（超了从最旧的丢）
_CHANGE_MAX_SKIPPED = 50
_CHANGE_PREVIEW_LINES = 12
_CHANGE_SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules",
                     ".ipynb_checkpoints", ".mypy_cache", ".pytest_cache", ".idea"}

_SERVER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _change_path_from_args(args):
    """从工具参数里取目标路径（write_file/patch 用 path，别的工具可能用 file_path/file）。"""
    if not isinstance(args, dict):
        return ""
    for k in ("path", "file_path", "file", "filename", "target"):
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().strip('"').strip("'")
    return ""


def _change_skip_reason(abs_path):
    parts = set(re.split(r"[\\/]+", abs_path))
    if parts & _CHANGE_SKIP_DIRS:
        return "缓存/依赖目录"
    return ""


def _change_skip_reason_text(kind):
    return {"binary": "二进制/目录", "toolarge": f"超过 {_CHANGE_MAX_FILE_BYTES // 1024}KB",
            "error": "读取失败"}.get(kind, "不可读")


def _read_text_for_change(abs_path):
    """读文件做快照。返回 (kind, text)：kind ∈ exists|missing|binary|toolarge|error"""
    try:
        if not os.path.exists(abs_path):
            return "missing", None
        if os.path.isdir(abs_path):
            return "binary", None
        size = os.path.getsize(abs_path)
        if size > _CHANGE_MAX_FILE_BYTES:
            return "toolarge", None
        with open(abs_path, "rb") as f:
            raw = f.read()
        if b"\x00" in raw[:8192]:
            return "binary", None
        try:
            return "exists", raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return "exists", raw.decode("utf-8", errors="replace")
            except Exception:
                return "binary", None
    except Exception:
        return "error", None


def _sha12(text):
    if text is None:
        return ""
    try:
        return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:12]
    except Exception:
        return ""


def _unified_diff_text(path, before, after):
    """生成 unified diff；返回 (diff_text, added, removed, truncated)"""
    import difflib as _dl
    b = (before or "").splitlines(keepends=True)
    a = (after or "").splitlines(keepends=True)
    name = os.path.basename(path) or path
    lines = list(_dl.unified_diff(b, a, fromfile=f"改前/{name}", tofile=f"改后/{name}", n=3))
    added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    truncated = False
    if len(lines) > _CHANGE_MAX_DIFF_LINES:
        lines = lines[:_CHANGE_MAX_DIFF_LINES]
        truncated = True
    return "".join(lines), added, removed, truncated


def _change_note_skipped(session, path, reason):
    lst = session.setdefault("_changes_skipped", [])
    lst.append({"path": path, "reason": reason, "ts": datetime.now().strftime("%H:%M:%S")})
    if len(lst) > _CHANGE_MAX_SKIPPED:
        del lst[:len(lst) - _CHANGE_MAX_SKIPPED]


def _snapshot_before_change(session, tool_name, args):
    """工具执行前：把「改前」内容抓下来（此时文件还没被改）。"""
    if tool_name not in _WRITER_TOOLS:
        return None
    path = _change_path_from_args(args)
    if not path:
        return None
    try:
        abs_path = os.path.abspath(path)
    except Exception:
        return None
    reason = _change_skip_reason(abs_path)
    if reason:
        _change_note_skipped(session, abs_path, reason)
        return None
    kind, text = _read_text_for_change(abs_path)
    if kind in ("binary", "toolarge", "error"):
        _change_note_skipped(session, abs_path, _change_skip_reason_text(kind))
        return None
    pending = session.setdefault("_changes_pending", {})
    pending[abs_path] = {"tool": tool_name, "before": text, "before_exists": kind == "exists",
                         "ts": time.time()}
    # 上限保护：pending 不该堆积（正常一次工具调用一进一出）
    if len(pending) > 20:
        for k in list(pending)[:-10]:
            pending.pop(k, None)
    return abs_path


def _finalize_file_change(session, tool_name, args=None, result=None):
    """工具执行后：对比「改后」内容，产出 diff 记录并推给前端。

    args 给定时按它的 path 结算；args 为 None（微信通道的 complete 回调不带 args）
    时，结算本会话里该工具留下的全部待结算项。
    """
    if tool_name not in _WRITER_TOOLS:
        return None
    pending = session.get("_changes_pending") or {}
    if args is None or not _change_path_from_args(args):
        targets = [p for p, s in pending.items() if s.get("tool") == tool_name]
        rec = None
        for p in targets:
            rec = _finalize_one_change(session, tool_name, p) or rec
        return rec
    try:
        abs_path = os.path.abspath(_change_path_from_args(args))
    except Exception:
        return None
    return _finalize_one_change(session, tool_name, abs_path)


def _finalize_one_change(session, tool_name, abs_path):
    """结算单个路径：读改后内容 → diff → 记一条 → 推送。"""
    pending = session.get("_changes_pending") or {}
    snap = pending.pop(abs_path, None)
    if snap is None:
        return None          # 执行前没抓到（跳过或非本工具写的）→ 不记
    kind, after_text = _read_text_for_change(abs_path)
    if kind == "missing":
        after_text, status = "", "deleted"
    elif kind in ("binary", "toolarge", "error"):
        _change_note_skipped(session, abs_path, _change_skip_reason_text(kind))
        return None
    else:
        status = "added" if not snap.get("before_exists") else "modified"
    before_text = snap.get("before")
    if (before_text or "") == (after_text or "") and status != "deleted":
        return None          # 内容没变（工具重写了同样内容）→ 不污染列表
    diff_text, added, removed, truncated = _unified_diff_text(abs_path, before_text, after_text)
    rec = {
        "id": "chg_" + uuid.uuid4().hex[:10],
        "path": abs_path,
        "rel_path": _change_rel_path(session, abs_path),
        "tool": tool_name,
        "status": status,
        "ts": datetime.now().strftime("%H:%M:%S"),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "added": added,
        "removed": removed,
        "truncated": truncated,
        "sha_before": _sha12(before_text),
        "sha_after": _sha12(after_text),
        "diff": diff_text,
        "preview": diff_text.splitlines()[:_CHANGE_PREVIEW_LINES],
        "revertible": True,
        # 回滚用的改前内容只放内存（不落库：体积大且含数据路径），重启后只能看不能回滚
        "_before_text": before_text,
        "_before_exists": bool(snap.get("before_exists")),
    }
    changes = session.setdefault("changes", [])
    changes.append(rec)
    if len(changes) > _CHANGE_MAX_KEEP:
        del changes[:len(changes) - _CHANGE_MAX_KEEP]
    _persist_changes(session)
    _session_emit(session, {"type": "changes_update", **_changes_payload(session, light=True)})
    return rec


def _change_rel_path(session, abs_path):
    for base in (session.get("results_dir") or "", _SERVER_ROOT):
        if base:
            try:
                rel = os.path.relpath(abs_path, base)
                if not rel.startswith(".."):
                    return rel.replace("\\", "/")
            except Exception:
                pass
    return abs_path


def _changes_persist_blob(session):
    """落库内容：只存元数据 + diff（不存改前全文），并按总量上限从最旧的丢。"""
    keep = []
    total = 0
    for rec in reversed(session.get("changes", [])):
        item = {k: v for k, v in rec.items() if not k.startswith("_")}
        try:
            size = len(json.dumps(item, ensure_ascii=False))
        except Exception:
            continue
        if total + size > _CHANGE_MAX_STORE_BYTES:
            break
        total += size
        keep.append(item)
    keep.reverse()
    return json.dumps({"schema": "memomics.changes/1", "changes": keep}, ensure_ascii=False)


def _persist_changes(session):
    sid = session.get("id", "")
    if sid:
        _kv_set(_kv_ns("changes", sid), _changes_persist_blob(session))


def _restore_changes(session):
    """进程重启后从 state.db 读回改动列表（只读不复写；revertible=False）。"""
    if session.get("changes"):
        return session["changes"]
    sid = session.get("id", "")
    if not sid:
        return []
    raw = _kv_get(_kv_ns("changes", sid))
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    items = parsed.get("changes") if isinstance(parsed, dict) else None
    out = []
    for it in (items or []):
        if not isinstance(it, dict) or not it.get("path"):
            continue
        it = dict(it)
        it["revertible"] = False      # 重启后没有改前全文 → 只能复核，不能回滚
        it["restored"] = True
        out.append(it)
    session["changes"] = out
    return out


def _changes_payload(session, light=True, change_id=None):
    _restore_changes(session)
    changes = session.get("changes", [])
    skipped = session.get("_changes_skipped", [])
    def _public(rec):
        return {k: v for k, v in rec.items() if not k.startswith("_")}

    if change_id:
        for rec in changes:
            if rec.get("id") == change_id:
                return _public(rec)
        return None
    if not light:
        return {"changes": [_public(c) for c in changes], "skipped": list(skipped)}
    light_list = []
    for rec in changes:
        light_list.append({k: v for k, v in rec.items() if k not in ("diff",) and not k.startswith("_")})
    files = len({c.get("path") for c in changes})
    return {
        "summary": {
            "changes": len(changes),
            "files": files,
            "added": sum(int(c.get("added") or 0) for c in changes),
            "removed": sum(int(c.get("removed") or 0) for c in changes),
            "skipped": len(skipped),
            "revertible": sum(1 for c in changes if c.get("revertible")),
        },
        "changes": light_list,
        "skipped": list(skipped),
    }


def _change_revert_allowed(path):
    """回滚白名单：只允许写回会话 results_dir 或仓库根目录内的文件。"""
    try:
        abs_path = os.path.abspath(path)
    except Exception:
        return False
    roots = [_SERVER_ROOT]
    for base in roots:
        try:
            if os.path.commonpath([abs_path, base]) == os.path.abspath(base):
                return True
        except Exception:
            continue
    return False


def _revert_file_change(session, change_id):
    """回滚单条改动：把改前内容写回去。

    安全闸（自己设计的部分）：当前文件内容必须仍等于该条改动后的 sha，
    否则说明之后又有人改过它 → 409，绝不覆盖别人的修改。
    """
    _restore_changes(session)
    rec = None
    for c in session.get("changes", []):
        if c.get("id") == change_id:
            rec = c
            break
    if rec is None:
        return 404, {"error": "改动记录不存在"}
    if not rec.get("revertible") or "_before_text" not in rec:
        return 409, {"error": "这条改动是重启前记录的，只有 diff 没有改前全文，无法回滚"}
    path = rec.get("path") or ""
    if not _change_revert_allowed(path):
        return 403, {"error": f"路径不在允许回滚的范围内：{path}"}
    kind, current = _read_text_for_change(path)
    if kind in ("binary", "toolarge", "error"):
        return 409, {"error": f"当前文件不可读（{kind}），拒绝回滚"}
    cur_sha = _sha12("" if kind == "missing" else current)
    if cur_sha != (rec.get("sha_after") or ""):
        return 409, {"error": "文件在本次改动之后又被修改过，拒绝覆盖（请先人工确认）"}
    # P2-4：回滚既是"写回去"也可能是"删掉它"，按真实动作分别过门
    # （观察模式不拦；强制 fs.write/fs.delete 后越界或无授权 -> 403，绝不半途写坏文件）
    _act = "fs.write" if rec.get("_before_exists") else "fs.delete"
    _denied = _sandbox_precheck(_act, path, [_SERVER_ROOT], "changes.revert")
    if _denied:
        return 403, {"error": "sandbox denied: %s" % _denied}
    try:
        if not rec.get("_before_exists"):
            # 改动前文件不存在 → 回滚 = 删除它
            if os.path.exists(path):
                os.remove(path)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(rec.get("_before_text") or "")
    except Exception as e:
        return 500, {"error": f"写回失败：{e}"}
    rec["status"] = "reverted"
    rec["revertible"] = False
    rec["_before_text"] = None
    _persist_changes(session)
    _session_emit(session, {"type": "changes_update", **_changes_payload(session, light=True)})
    return 200, {"ok": True, "path": path, "restored": bool(rec.get("_before_exists")),
                 **_changes_payload(session, light=True)}


@app.get("/api/sessions/{sid}/changes")
async def get_session_changes(sid: str, full: int = 0):
    """P1-2: 会话改动复核（默认轻量列表；full=1 时连 diff 一起给）"""
    if sid not in _sessions:
        _restore_single_session(sid)
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    session = _sessions[sid]
    payload = _changes_payload(session, light=(not full))
    payload["session_id"] = sid
    return payload


@app.get("/api/sessions/{sid}/changes/{change_id}")
async def get_session_change_detail(sid: str, change_id: str):
    """P1-2: 单条改动的完整 diff（列表接口刻意不下发 diff，避免大文件刷屏）"""
    if sid not in _sessions:
        _restore_single_session(sid)
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    rec = _changes_payload(_sessions[sid], change_id=change_id)
    if rec is None:
        return JSONResponse({"error": "改动记录不存在"}, status_code=404)
    return {"change": rec, "session_id": sid}


@app.post("/api/sessions/{sid}/changes/{change_id}/revert")
async def revert_session_change(sid: str, change_id: str):
    """P1-2: 回滚单条改动（带 sha 一致性闸门，拒绝覆盖后续修改）"""
    if sid not in _sessions:
        _restore_single_session(sid)
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    code, body = _revert_file_change(_sessions[sid], change_id)
    body["session_id"] = sid
    return JSONResponse(body, status_code=code)


# --- P1-3 可点击引用 --------------------------------------------------------
# 回答里原本只是「看着像标签、点不动」的文字（[KB源:x] / [数据:y] / [DOI:z] / [PMID:n] / [URL:u]），
# 现在解析成一个可核对的目标：知识库/数据文件给出原文摘录（含命中行号），
# DOI/PMID/URL 给出外链，解析不到就明说「找不到」并给原因。
# 只读、不联网：摘录一律来自本机文件，且只能读知识库/数据目录内的内容。

_CITE_MAX_TEXT = 20000          # 单次解析的文本上限（防超长回答拖垮解析）
_CITE_MAX_ITEMS = 40            # 单条消息最多解析多少个锚点
_CITE_EXCERPT_LINES = 24        # 摘录行数
_CITE_EXCERPT_CHARS = 4000      # 摘录字符上限
_CITE_MAX_MATCHES = 8           # 同名候选文件上限
_CITE_MAX_VALUE = 300           # 单个锚点值的字符上限（和前端正则保持一致）

_CITE_RE = re.compile(
    r"\[\s*(DOI|PMID|PMIDs|KB源|KB|数据|DATA|资料|URL|链接|来源)\s*[:：]?\s*([^\]]*)\]",
    re.IGNORECASE,
)
_CITE_NOTE_RE = re.compile(
    r"\[\s*(找不到论据|找不到证据|未找到证据|无证据|仅是推理|推理|无外部证据|推断)\s*\]"
)
_CITE_KB_KINDS = ("kb源", "kb", "来源", "资料")
_CITE_DATA_KINDS = ("数据", "data")
_CITE_URL_KINDS = ("url", "链接")


def _cite_kind(raw_kind: str) -> str:
    """把方括号里的中文/英文标签归一到 5 类。"""
    kl = (raw_kind or "").strip().lower()
    if kl == "doi":
        return "doi"
    if kl in ("pmid", "pmids"):
        return "pmid"
    if kl in _CITE_KB_KINDS:
        return "kb"
    if kl in _CITE_DATA_KINDS:
        return "data"
    if kl in _CITE_URL_KINDS:
        return "url"
    return "other"


def _cite_extract(text, limit: int = _CITE_MAX_ITEMS):
    """抽出证据锚点：保序、按 (类别,值) 去重、限量。"""
    found = []
    if not text:
        return found
    s = text[:_CITE_MAX_TEXT]
    for m in _CITE_RE.finditer(s):
        found.append((m.start(), "anchor", _cite_kind(m.group(1)), m.group(1).strip(), (m.group(2) or "").strip(), m.group(0)))
    for m in _CITE_NOTE_RE.finditer(s):
        found.append((m.start(), "note", "note", m.group(1).strip(), m.group(1).strip(), m.group(0)))
    found.sort(key=lambda x: x[0])
    out, seen = [], set()
    for _pos, _t, kind, label, value, raw in found:
        value = value[:_CITE_MAX_VALUE]      # 超长值没有可核对的可能，直接截断（别把响应撑爆）
        raw = raw[:_CITE_MAX_VALUE + 8]
        key = (kind, value.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({"kind": kind, "label": label, "value": value, "raw": raw})
        if len(out) >= limit:
            break
    return out


def _cite_external_url(kind: str, value: str) -> str:
    """DOI/PMID → 权威外链；URL → 只放行 http(s)（挡住 javascript:/file: 之类）。"""
    v = (value or "").strip().strip("<>").strip()
    if not v:
        return ""
    if kind == "doi":
        v = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", v, flags=re.IGNORECASE).strip()
        if not re.match(r"^10\.\d{4,9}/\S+$", v):
            return ""
        return "https://doi.org/" + v
    if kind == "pmid":
        m = re.search(r"\d{4,9}", v)
        return ("https://pubmed.ncbi.nlm.nih.gov/%s/" % m.group(0)) if m else ""
    if re.match(r"^https?://", v, re.IGNORECASE):
        # 带空白/尖括号/引号的“网址”不是合法 URL，放行只会把脏串带到前端
        if re.search(r"""[\s<>"'{}|\\^\u0060]""", v):
            return ""
        return v[:500]
    return ""


def _cite_safe_roots(session=None):
    """允许读取的根目录：知识库 + 数据目录（+ 本会话结果目录）。"""
    roots = [os.path.abspath(KB_DIR), os.path.abspath(DATA_DIR)]
    if session:
        rd = (session.get("results_dir") or "").strip()
        if rd:
            try:
                roots.append(os.path.abspath(rd))
            except Exception:
                pass
    uniq = []
    for r in roots:
        if r not in uniq:
            uniq.append(r)
    return uniq


def _cite_inside(abs_path: str, roots) -> bool:
    p = os.path.abspath(abs_path)
    for r in roots:
        if p == r or p.startswith(r + os.sep):
            return True
    return False


def _cite_rel(abs_path: str) -> str:
    """给前端一个可读的相对标识（知识库/数据根下）。"""
    pairs = (("knowledge_base", KB_DIR), ("data", DATA_DIR))
    for name, root in pairs:
        try:
            r = os.path.abspath(root)
            if abs_path == r or abs_path.startswith(r + os.sep):
                return name + "/" + os.path.relpath(abs_path, r).replace("\\", "/")
        except Exception:
            continue
    return os.path.basename(abs_path)


def _cite_find_files(value: str, roots, limit: int = _CITE_MAX_MATCHES):
    """找候选文件 → [(绝对路径, 是否精确命中)]。

    优先级：直给路径（相对/绝对）→ 同名或同词干 → 文件名子串（词干≥4 才算，
    免得 "win.ini" 这种短片断匹配到无关文件）。所有候选必须落在允许的根内，
    含 .. 的相对路径、盘符路径一律拒绝。
    """
    v = (value or "").strip().strip('"').strip("'").strip().replace("\\", "/")
    if not v:
        return []
    parts = [p for p in v.split("/") if p not in ("", ".")]
    if ".." in parts or v.startswith("/") or re.match(r"^[a-zA-Z]:", v):
        return []
    out, seen = [], set()

    def _add(p, exact):
        try:
            ap = os.path.abspath(p)
        except Exception:
            return
        if ap in seen or not os.path.isfile(ap) or not _cite_inside(ap, roots):
            return
        seen.add(ap)
        out.append((ap, exact))

    for r in roots:
        _add(os.path.join(r, v), True)
    if out:
        return out[:limit]
    base = os.path.basename(v)
    if len(base) < 3:
        return []
    stem = os.path.splitext(base)[0].lower()
    bl = base.lower()
    for r in roots:
        if not os.path.isdir(r):
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(r):
                dirnames[:] = [d for d in dirnames if d not in _CHANGE_SKIP_DIRS]
                for fn in filenames:
                    fl = fn.lower()
                    exact = fl == bl or os.path.splitext(fl)[0] == stem
                    fuzzy = (not exact) and len(stem) >= 4 and bl in fl
                    if exact or fuzzy:
                        _add(os.path.join(dirpath, fn), exact)
                        if len(out) >= limit:
                            return out
        except Exception:
            continue
    return out


def _cite_excerpt(abs_path: str, needle: str = ""):
    """读一段摘录（复用 P1-2 的只读读法：二进制/超大/缺失都有明确原因）。"""
    kind, text = _read_text_for_change(abs_path)
    if kind != "exists" or text is None:
        return None, _change_skip_reason_text(kind)
    lines = text.splitlines()
    start, hit = 0, 0
    nl = (needle or "").lower()
    if nl and len(nl) >= 3:
        for i, ln in enumerate(lines):
            if nl in ln.lower():
                hit = i + 1
                start = max(0, i - 2)
                break
    chunk = lines[start:start + _CITE_EXCERPT_LINES]
    body = "\n".join(chunk)
    more = (start + _CITE_EXCERPT_LINES) < len(lines)
    return {
        "lines": [{"n": start + i + 1, "text": t[:400]} for i, t in enumerate(chunk)],
        "start_line": start + 1,
        "total_lines": len(lines),
        "hit_line": hit,
        "text": body[:_CITE_EXCERPT_CHARS],
        "truncated": bool(more or len(body) > _CITE_EXCERPT_CHARS),
    }, ""


def _cite_resolve_item(item, session=None):
    """解析单个锚点 → 可展示的结果（resolved/external/missing/note 四种状态）。"""
    kind = item.get("kind") or "other"
    value = (item.get("value") or "").strip()
    rec = {"kind": kind, "label": item.get("label") or "", "value": value, "raw": item.get("raw") or "",
           "status": "missing", "reason": "", "title": "", "url": "", "path": "", "rel": "",
           "lines": [], "start_line": 0, "total_lines": 0, "hit_line": 0, "text": "",
           "truncated": False, "alternatives": [], "approx": False}
    if kind == "note":
        rec["status"] = "note"
        rec["reason"] = "原文写明这条结论只是推理" if ("推理" in value or "推断" in value) else "原文写明找不到论据"
        return rec
    if kind in ("doi", "pmid", "url"):
        url = _cite_external_url(kind, value)
        if url:
            rec.update(status="external", url=url, title=value or url)
        else:
            rec["reason"] = "不是有效的 DOI / PMID / 网址"
        return rec
    if not value:
        rec["reason"] = "锚点没写具体目标"
        return rec
    roots = _cite_safe_roots(session)
    files = _cite_find_files(value, roots)
    if not files:
        rec["reason"] = "知识库/数据目录里找不到「%s」" % value[:80]
        return rec
    abs_path, exact = files[0]
    if not _cite_inside(abs_path, roots):
        rec["reason"] = "目标不在允许读取的目录内"
        return rec
    rec["approx"] = not exact          # 靠文件名模糊匹配到的 → 前端要标明
    exc, why = _cite_excerpt(abs_path, value if kind == "data" else "")
    rec["path"] = abs_path.replace("\\", "/")
    rec["rel"] = _cite_rel(abs_path)
    rec["title"] = os.path.basename(abs_path)
    rec["alternatives"] = [_cite_rel(p) for p, _e in files[1:]]
    if exc is None:
        rec["reason"] = why or "这个文件读不了"
        return rec
    rec.update(exc)
    rec["status"] = "resolved"
    return rec


def _cite_resolve(text: str, session=None):
    """把一段文本里的所有证据锚点解析出来。"""
    items = [_cite_resolve_item(it, session) for it in _cite_extract(text or "")]
    summary = {"total": len(items), "resolved": 0, "external": 0, "missing": 0, "note": 0,
               "truncated_text": max(0, len(text or "") - _CITE_MAX_TEXT)}
    for it in items:
        summary[it["status"]] = summary.get(it["status"], 0) + 1
    return {"summary": summary, "items": items}


def _cite_last_assistant_index(msgs):
    for i in range(len(msgs) - 1, -1, -1):
        if (msgs[i].get("role") or "") == "assistant":
            return i
    return None


class CiteResolveReq(BaseModel):
    text: str = ""
    session_id: Optional[str] = None


@app.post("/api/citations/resolve")
async def citations_resolve(req: CiteResolveReq):
    """把一段文本里的证据锚点解析成可核对的目标（只读、不联网）。"""
    text = req.text or ""
    if len(text) > _CITE_MAX_TEXT * 5:
        return JSONResponse({"error": "文本过长（上限 %d 字符）" % (_CITE_MAX_TEXT * 5)}, status_code=413)
    sess = None
    if req.session_id:
        sess = _sessions.get(req.session_id)
        if sess is None:
            _restore_single_session(req.session_id)
            sess = _sessions.get(req.session_id)
    out = _cite_resolve(text, sess)
    out["ok"] = True
    if req.session_id:
        out["session_id"] = req.session_id
    return out


@app.get("/api/sessions/{sid}/citations")
async def session_citations(sid: str, msg: int = -1):
    """解析某条消息里的证据锚点（msg=-1 = 最后一条助手消息）。"""
    if sid not in _sessions:
        _restore_single_session(sid)
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    msgs = _sessions[sid].get("messages") or []
    if not msgs:
        return JSONResponse({"error": "该会话还没有消息"}, status_code=404)
    idx = msg if msg >= 0 else _cite_last_assistant_index(msgs)
    if idx is None or idx < 0 or idx >= len(msgs):
        return JSONResponse({"error": "消息下标越界", "total_messages": len(msgs)}, status_code=404)
    m = msgs[idx]
    if (m.get("role") or "") != "assistant":
        return JSONResponse({"error": "只有助手消息才有证据锚点", "role": m.get("role"),
                             "total_messages": len(msgs)}, status_code=400)
    out = _cite_resolve(m.get("content") or "", _sessions[sid])
    out.update({"ok": True, "session_id": sid, "msg_index": idx, "total_messages": len(msgs)})
    return out


# --- P1-4 会话大纲 ---
# 会话一长就翻不动：每一轮（一条提问 + 它之后的回答）生成一条目录项，前端点一下就跳过去。
# 过滤规则与 /api/sessions/{sid}/messages 完全一致（系统注入、工具消息不进目录）；
# 只读、不联网、不写盘；轮数、摘要长度、扫描条数都封顶，免得大会话把面板拖垮。

_OUTLINE_MAX_TURNS = 200      # 目录最多返回多少轮（超出只留最近这些轮）
_OUTLINE_SCAN_MSGS = 4000     # 最多扫描多少条消息
_OUTLINE_TITLE_CHARS = 60     # 提问摘要长度
_OUTLINE_HEAD_CHARS = 100     # 回答摘要长度


def _outline_title(text, limit: int = _OUTLINE_TITLE_CHARS):
    """取第一条像样的行当摘要：剥掉 markdown 噪声、压空白、截断；全空返回空串。"""
    s = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    for line in s.split("\n"):
        ln = line.strip().lstrip("#>*+-•· \t").strip()
        if not ln:
            continue
        ln = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", ln)        # 图片 → 去掉
        ln = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", ln)  # 链接 → 留文字
        ln = re.sub(r"`+", "", ln)                             # 行内代码反引号
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln:
            return ln[:limit]
    return ""


def _outline_visible_msgs(session, limit=None):
    """筛出会出现在对话流里的消息（与 /messages 同一套过滤）。

    limit 默认取模块级 _OUTLINE_SCAN_MSGS（调用时读，方便测试收紧窗口）。
    """
    if limit is None:
        limit = _OUTLINE_SCAN_MSGS
    msgs = session.get("messages") or []
    if limit and limit > 0 and len(msgs) > limit:
        msgs = msgs[-limit:]
    out = []
    for m in msgs:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content")
        if content is None:
            content = m.get("text")
        if not isinstance(content, str):
            content = "" if content is None else str(content)
        if content.lstrip().startswith(_INJECT_PREFIXES):
            continue
        item = {"role": role, "content": content, "time": m.get("time") or ""}
        try:
            item["tool_count"] = int(m.get("tool_count") or 0)
        except Exception:
            item["tool_count"] = 0
        out.append(item)
    return out


def _session_outline(session):
    """把会话切成一轮一轮，给前端做目录。

    一轮 = 一条用户提问 + 它之后、下一条提问之前的全部回答。
    提问还没被回答也建轮（正在跑的那一轮在目录里能看见）。
    """
    turns = []
    leading = 0
    for m in _outline_visible_msgs(session):
        if m["role"] == "user":
            turns.append({
                "turn": len(turns) + 1,
                "question": _outline_title(m["content"]),
                "time": m["time"],
                "answers": 0,
                "answer_head": "",
                "chars": 0,
                "tools": 0,
                "anchors": 0,
            })
            continue
        if not turns:
            leading += 1          # 开场白：还没有用户提问
            continue
        t = turns[-1]
        t["answers"] += 1
        t["chars"] += len(m["content"])
        if not t["answer_head"]:
            t["answer_head"] = _outline_title(m["content"], _OUTLINE_HEAD_CHARS)
        try:
            t["tools"] += int(m.get("tool_count") or 0)
        except Exception:
            pass
        try:
            t["anchors"] += len(_cite_extract(m["content"]))
        except Exception:
            pass
    total_turns = len(turns)
    hidden = 0
    if total_turns > _OUTLINE_MAX_TURNS:
        hidden = total_turns - _OUTLINE_MAX_TURNS
        turns = turns[-_OUTLINE_MAX_TURNS:]
    return {"turns": turns, "total_turns": total_turns, "leading": leading,
            "hidden_turns": hidden, "truncated": hidden > 0}


@app.get("/api/sessions/{sid}/outline")
async def session_outline(sid: str):
    """会话大纲：每条提问一轮，带回答摘要和角标，供右侧面板做可点目录。"""
    if sid not in _sessions:
        _restore_single_session(sid)
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    session = _sessions[sid]
    # 只加载一个窗口（和 /messages 一样），大会话不为了目录把整段历史解进内存
    if not session.get("_messages_loaded"):
        try:
            _win = max(int(_OUTLINE_SCAN_MSGS), 200)
            if len(session.get("messages") or []) < _win:
                session["messages"] = _load_session_messages(sid, limit=_win)
        except Exception:
            pass
    data = _session_outline(session)
    data.update({"ok": True, "session_id": sid, "title": session.get("title") or ""})
    return data


# --- 待办 ---

@app.get("/api/todos/{sid}")
async def get_todos(sid: str):
    """获取会话待办（P1-1 起：内存 + state.db 双读，刷新/重启不丢）"""
    if sid not in _sessions:
        _restore_single_session(sid)
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    session = _sessions[sid]
    return {"todos": _session_todos(session),
            "revision": int(session.get("todos_revision", 0) or 0)}

@app.get("/api/sessions/{sid}/progress")
async def get_progress(sid: str):
    """获取会话的进度日志（用于切换会话后重放）"""
    if sid not in _sessions:
        _restore_single_session(sid)
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    session = _sessions[sid]
    return {
        "progress_log": session.get("progress_log", []),
        "reasoning_log": [r.get("content", "") for r in session.get("reasoning_log", []) if r.get("content")],
        # 2026-08-17: 半截流式文本（刷新/重连时恢复进行中的回复，HTTP 兜底同款）
        "partial_text": session.get("_partial_text", ""),
        "is_running": bool(session.get("running_agent") or session.get("running_task")),
        # 2026-08-23: 最近一次工具调用（刷新后状态条显示 agent 在干什么）
        "last_tool": _last_tool_of(sid),
        # P1-1(2026-09-23): 目标条数据随进度接口一起下发 —— 前端刷新/切会话时
        # 本来就要拉这个接口，零新增请求即可恢复目标 + 待办。
        **_goal_payload(session),
        "session_id": sid,
    }


@app.post("/api/sessions/{sid}/wakeup")
async def wakeup_session(sid: str):
    """外部唤醒端点 — cron agent / 心跳进程完成后调用，激活 MemOmics Agent。
    
    请求体可选：{"reason": "completion|error|progress", "msg": "..."}
    """
    if sid not in _sessions:
        _restore_single_session(sid)
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found", "wakeup": False}, status_code=404)
    session = _sessions[sid]
    # 2026-08-16: 退役任务（done/cancelled）的自动唤醒一律拦截——此前外部唤醒
    # 置 urgent 会绕过 RunGate，让已完成任务白跑一轮
    try:
        from webui.runtime.run_gate import check_gate
        _rd = session.get("results_dir", "") or ""
        if _rd:
            _verdict, _reason = check_gate(_rd, is_auto_wake=True)
            if _verdict == "stop":
                logger.info(f"[Wakeup] session {sid[:12]}: RunGate 拦截外部唤醒 ({_reason})")
                return {"wakeup": False, "session_id": sid, "msg": f"Wakeup rejected: {_reason}"}
    except Exception:
        pass
    session["_urgent_wakeup"] = True
    logger.info(f"[Wakeup] session {sid[:12]}: external wakeup triggered")
    return {"wakeup": True, "session_id": sid, "msg": "Wakeup signal received. Agent will be activated on next tick."}


# --- 外置记忆 (跨会话) ---

def _memory_api_token() -> str:
    """P1-10(2026-08-13): 记忆写 API 轻量鉴权 token。

    服务首次启动时生成随机 token 持久化到 hermes_home/memory_api_token。
    同源 WebUI 通过 GET /api/memory 拿到 token 后随写请求携带。
    """
    _tok_path = os.path.join(HERMES_HOME_DIR, "memory_api_token")
    try:
        if os.path.exists(_tok_path):
            with open(_tok_path, encoding="utf-8") as f:
                _tok = f.read().strip()
            if len(_tok) >= 16:
                return _tok
    except OSError:
        pass
    _tok = uuid.uuid4().hex + uuid.uuid4().hex[:8]  # 40 hex chars
    try:
        with open(_tok_path, "w", encoding="utf-8") as f:
            f.write(_tok)
    except OSError:
        pass
    return _tok

# 记忆文件限额：真相源是 hermes_home/config.yaml 的 memory_char_limit / user_char_limit
# （Hermes MemoryStore 用的就是这两个数）。
# 2026-09-23 修：原来硬编码 10000，而 config.yaml 写的是 30000 —— 于是记忆栏的
# 「追加/覆盖」在这台机器上 100% 被 413 挡死（MEMORY.md 早已 29530 字符），
# 用户看到的就是"添加完全没用"。注释当时声称"与 config 保持一致"，其实从来没读过 config。
_MEMORY_LIMIT_KEYS = {"USER.md": "user_char_limit", "MEMORY.md": "memory_char_limit"}
_MEMORY_DEFAULT_LIMIT = 30000


def _memory_char_limit(filename: str) -> int:
    """取记忆文件限额：config.yaml 优先，读不到就退回默认值（绝不再硬编码一个小数）。"""
    _name = os.path.basename(str(filename or "MEMORY.md"))
    _key = _MEMORY_LIMIT_KEYS.get(_name, "memory_char_limit")
    try:
        _cfg, _raw = _hermes_config_read()
        _mem = (_cfg or {}).get("memory") or {}
        _val = _mem.get(_key) or _mem.get("memory_char_limit") or _MEMORY_DEFAULT_LIMIT
        _val = int(_val)
        return _val if _val > 0 else _MEMORY_DEFAULT_LIMIT
    except Exception:
        return _MEMORY_DEFAULT_LIMIT


def _memory_usage():
    """记忆文件占用/限额（面板占用条 + 治理体检共用；限额真相源=config.yaml）。"""
    mem_dir = os.path.join(HERMES_HOME_DIR, "memories")
    out = {}
    for name in ("MEMORY.md", "USER.md"):
        path = os.path.join(mem_dir, name)
        chars = 0
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    chars = len(f.read())
            except Exception:
                chars = 0
        limit = _memory_char_limit(name)
        out[name] = {"chars": chars, "limit": limit,
                     "pct": round(100.0 * chars / limit, 1) if limit else None,
                     "headroom": max(0, limit - chars)}
    return out


@app.post("/api/memory/govern")
async def memory_govern(payload: dict = None, request: Request = None):
    """记忆治理（2026-09-24 重做 —— 原实现只重算索引，点了等于没点）。

    mode="dry"（默认，只读）：占用/余量、分层、分数分布、可归档候选、预计释放字符。
    mode="apply"：把"自己标了低价值"（条目开头 [imp:x] ≤ threshold）的条目归档到
        memories/archive/YYYY-MM.md，原位置留一行索引；动前整档备份到
        memories/.backup/<ts>/；内容永不删除。apply 需要 X-Memory-Token。
    旧前端不带 body 调用 → 走 dry，纯只读，向后兼容。
    """
    payload = payload or {}
    mode = str(payload.get("mode", "dry")).lower()
    try:
        threshold = float(payload.get("threshold", 0.7))
    except Exception:
        threshold = 0.7
    limits = {k: v["limit"] for k, v in _memory_usage().items()}
    try:
        from memomics.memory_governance import governor
        if mode in ("apply", "run"):
            _token = (request.headers.get("x-memory-token", "") if request else "") \
                or str(payload.get("token", ""))
            if _token != _memory_api_token():
                return JSONResponse({"error": "Unauthorized: missing/invalid memory API token"},
                                    status_code=401)
            _target = os.path.join(HERMES_HOME_DIR, "memories", "MEMORY.md")
            _denied = _sandbox_precheck("fs.write", _target, [MEMOMICS_DIR], "memory.govern")
            if _denied:
                return JSONResponse({"error": "sandbox denied: %s" % _denied}, status_code=403)
            rep = governor.archive_low_value(threshold=threshold, dry_run=False,
                                             limits=limits, force=bool(payload.get("force")))
            rep["mode"] = "apply"
        else:
            rep = governor.archive_low_value(threshold=threshold, dry_run=True,
                                             limits=limits)
            rep["mode"] = "dry"
        rep["usage"] = _memory_usage()
        if not rep.get("ok", True):
            return JSONResponse(rep, status_code=409)
        return rep
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/memory")
async def get_memory():
    """读取外置记忆内容（响应携带写 API token，供同源页面使用）"""
    mem_dir = os.path.join(HERMES_HOME_DIR, "memories")
    result = {"entries": [], "api_token": _memory_api_token(),
              "usage": _memory_usage()}
    try:
        from memomics.memory_governance import governor
        result["parsed"] = governor.list_entries()
    except Exception as e:
        result["parsed"] = {}
        result["parsed_error"] = str(e)
    # MEMORY.md — agent 自己的记忆
    memory_md = os.path.join(mem_dir, "MEMORY.md")
    if os.path.exists(memory_md):
        with open(memory_md, encoding="utf-8", errors="replace") as f:
            result["memory"] = f.read()
    # USER.md — 用户偏好
    user_md = os.path.join(mem_dir, "USER.md")
    if os.path.exists(user_md):
        with open(user_md, encoding="utf-8", errors="replace") as f:
            result["user"] = f.read()
    # 列出所有 .md 文件
    if os.path.isdir(mem_dir):
        for p in sorted(Path(mem_dir).glob("*.md")):
            result["entries"].append({"name": p.name, "size": p.stat().st_size, "path": str(p).replace("\\", "/")})
    return result


@app.post("/api/memory/write")
async def write_memory(payload: dict, request: Request):
    """写入外置记忆 — P1-10(2026-08-13): token 鉴权 + 限额检查"""
    # 鉴权：写操作必须携带 token（读操作不受限，页面需展示）
    _token = request.headers.get("x-memory-token", "") or str(payload.get("token", ""))
    if _token != _memory_api_token():
        return JSONResponse({"error": "Unauthorized: missing/invalid memory API token"}, status_code=401)
    mem_dir = os.path.join(HERMES_HOME_DIR, "memories")
    os.makedirs(mem_dir, exist_ok=True)
    target = payload.get("target", "MEMORY.md")  # MEMORY.md or USER.md
    content = payload.get("content", "")
    mode = payload.get("mode", "append")  # append or overwrite
    # 安全: 只允许 .md 文件
    if not target.endswith(".md"):
        return JSONResponse({"error": "Only .md files allowed"}, status_code=400)
    file_path = os.path.join(mem_dir, os.path.basename(target))
    # 限额检查（防记忆无限膨胀；数值与 Hermes MemoryStore 同源：config.yaml）
    _limit = _memory_char_limit(target)
    _existing = ""
    if mode != "overwrite" and os.path.exists(file_path):
        with open(file_path, encoding="utf-8", errors="replace") as f:
            _existing = f.read()
    _new_total = len((_existing + "\n\n" + content) if _existing else content)
    if _new_total > _limit:
        return JSONResponse({
            "error": (f"超出记忆限额：{_new_total}/{_limit} 字符"
                      f"（限额取自 hermes_home/config.yaml 的 memory_char_limit / user_char_limit）。"
                      f"请先删除或压缩旧条目，或用「🧹 治理」归档低价值条目再写入。"),
            "current": len(_existing), "limit": _limit,
        }, status_code=413)
    # P2-4：写动作过沙箱门（观察模式不拦；强制 fs.write 后越界/无授权 -> 403 且不落盘）
    _denied = _sandbox_precheck("fs.write", file_path, [MEMOMICS_DIR], "memory.write")
    if _denied:
        return JSONResponse({"error": "sandbox denied: %s" % _denied}, status_code=403)
    if mode == "overwrite":
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
    else:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write("\n\n" + content)
    return {"ok": True, "path": file_path.replace("\\", "/"), "size": os.path.getsize(file_path)}


@app.delete("/api/memory/entry")
async def memory_delete_entry(payload: dict = None, request: Request = None):
    """删除单条记忆（面板逐条 🗑）—— 2026-09-24 用户要求"记忆支持删除"。

    与"治理归档"不同，这是真删，所以：token 鉴权 + 服务端先整档备份 + 未知文件/越界
    一律不动字节。路由必须注册在 /api/memory/{filename} 之前，否则 "entry" 会被当成文件名。
    """
    payload = payload or {}
    _token = (request.headers.get("x-memory-token", "") if request else "") \
        or str(payload.get("token", ""))
    if _token != _memory_api_token():
        return JSONResponse({"error": "Unauthorized: missing/invalid memory API token"},
                            status_code=401)
    target = os.path.basename(str(payload.get("target", "MEMORY.md")))
    if target not in ("MEMORY.md", "USER.md"):
        return JSONResponse({"error": "只允许 MEMORY.md / USER.md"}, status_code=400)
    file_path = os.path.join(HERMES_HOME_DIR, "memories", target)
    _denied = _sandbox_precheck("fs.write", file_path, [MEMOMICS_DIR], "memory.entry_delete")
    if _denied:
        return JSONResponse({"error": "sandbox denied: %s" % _denied}, status_code=403)
    try:
        from memomics.memory_governance import governor
        rep = governor.delete_entry(target, payload.get("index"))
        rep["usage"] = _memory_usage()
        if not rep.get("ok"):
            _err = str(rep.get("error", ""))
            _code = 404 if ("越界" in _err or "未知" in _err or "不存在" in _err) else 400
            return JSONResponse(rep, status_code=_code)
        return rep
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.delete("/api/memory/{filename}")
async def delete_memory(filename: str, request: Request):
    """删除记忆文件 — P1-10: token 鉴权"""
    _token = request.headers.get("x-memory-token", "")
    if _token != _memory_api_token():
        return JSONResponse({"error": "Unauthorized: missing/invalid memory API token"}, status_code=401)
    if not filename.endswith(".md"):
        return JSONResponse({"error": "Only .md files"}, status_code=400)
    mem_dir = os.path.join(HERMES_HOME_DIR, "memories")
    file_path = os.path.join(mem_dir, os.path.basename(filename))
    if os.path.exists(file_path):
        # P2-4：删动作过沙箱门（观察模式不拦；强制 fs.delete 后越界/无授权 -> 403）
        _denied = _sandbox_precheck("fs.delete", file_path, [MEMOMICS_DIR], "memory.delete")
        if _denied:
            return JSONResponse({"error": "sandbox denied: %s" % _denied}, status_code=403)
        os.remove(file_path)
        return {"ok": True}
    return JSONResponse({"error": "Not found"}, status_code=404)


# === 系统级自动日志（确保 LLM 即使跳过 skill_evolution 也有审计记录） ===


def _weixin_push_progress(session, tool_name, result_str, loop=None):
    """微信进度推送：关键工具完成时向微信发送进度
    在 thread-pool callback 中调用时需传入主 event loop。
    """
    if not _weixin_state.get("connected") or not _weixin_state.get("token"):
        return
    KEY_TOOLS = {"scan_data", "execute_r", "execute_python", "terminal",
                  "rail_review", "debate_analysis", "skill_evolution", "generate_report"}
    if tool_name not in KEY_TOOLS:
        return
    try:
        step_name = session.get("step_name", "")
        ts = datetime.now().strftime("%H:%M:%S")
        msg = "🔬 MemOmics: {} 完成 ({})".format(step_name or tool_name, ts)
        if loop is not None:
            asyncio.run_coroutine_threadsafe(_send_weixin_progress(msg), loop)
        else:
            try:
                l = asyncio.get_running_loop()
                asyncio.run_coroutine_threadsafe(_send_weixin_progress(msg), l)
            except RuntimeError:
                pass
        # 📎 generate_report 完成后，自动发送 HTML 报告到微信
        if tool_name == "generate_report":
            _results_dir = session.get("results_dir", "")
            if _results_dir and os.path.isdir(_results_dir):
                try:
                    for p in sorted(Path(_results_dir).rglob("*.html"), key=lambda x: x.stat().st_mtime, reverse=True):
                        if p.stat().st_mtime > time.time() - 120:  # 2分钟内的新报告
                            if loop is not None:
                                asyncio.run_coroutine_threadsafe(
                                    _send_weixin_document(str(p), f"📄 {p.name}"), loop)
                            else:
                                try:
                                    l = asyncio.get_running_loop()
                                    asyncio.run_coroutine_threadsafe(
                                        _send_weixin_document(str(p), f"📄 {p.name}"), l)
                                except RuntimeError:
                                    pass
                            break  # 只发最新的一个
                except Exception:
                    pass
    except Exception:
        pass

def _ensure_results_dir(session):
    """确保 session 的 results_dir 物理目录存在。
    仅在目录不存在时创建，避免纯聊天产生空目录。
    由工具执行钩子触发（首个分析工具调用时自动创建）。
    安全规则：只创建 results/ 下的目录，拒绝外部路径。"""
    try:
        results_dir = session.get("results_dir", "")
        if not results_dir:
            return
        # 安全验证：只允许在 results/ 下创建目录
        _results_base = os.path.abspath(RESULTS_DIR).rstrip(os.sep)
        if not (os.path.abspath(results_dir).startswith(_results_base + os.sep) or \
                os.path.abspath(results_dir) == _results_base):
            return
        if not os.path.isdir(results_dir):
            os.makedirs(results_dir, exist_ok=True)
        # (3) 会话目录子结构：分析产出子目录 + scripts/(脚本落盘约定) + REQUIREMENTS.md 目录
        for _sub in ("figures", "results", "data", "scripts", "log"):
            try:
                os.makedirs(os.path.join(results_dir, _sub), exist_ok=True)
            except Exception:
                pass
        # (4) 2026-08-22: notes.md 草稿本（MiMo-Code 模式）——模型临时想法/疑问/引语的唯一合法 scratchpad
        try:
            _notes = os.path.join(results_dir, "notes.md")
            if not os.path.isfile(_notes):
                with open(_notes, "w", encoding="utf-8") as _f:
                    _f.write("# 会话草稿本 (notes.md)\n\n"
                             "临时观察/未决疑问/引语/跨项目观察。\n"
                             "格式：## [turn N · 时间]\n自由正文。\n")
        except Exception:
            pass
    except Exception:
        pass


def _auto_system_log(session, tool_name, args, result_str, tool_id=""):
    """在每个关键工具调用完成后，自动写入 results/<sid>/log/system_log.jsonl
    仅当 results_dir 已存在（即有实际分析产出）时才写入，不主动创建目录。

    2026-08-17 去重（memomics-0228a136 案例）：tool_complete 回调经多层合并链
    被同一工具事件反复触发（实测单个事件写 984 条相同日志，35h 会话日志
    膨胀到 166MB、UI 卡顿），按 tool_id 在 1.5s 窗口内去重。
    """
    try:
        _dedup = session.setdefault("_syslog_dedup", {})
        _key = str(tool_id or tool_name or "")
        _now = time.time()
        if _key and _now - _dedup.get(_key, 0) < 1.5:
            return
        _dedup[_key] = _now
        if len(_dedup) > 500:  # 有界化
            _dedup.clear()
        results_dir = session.get("results_dir", "")
        if not results_dir or not os.path.isdir(results_dir):
            return  # 纯聊天会话不创建目录
        log_dir = os.path.join(results_dir, "log")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "system_log.jsonl")
        entry = {
            "ts": datetime.now().isoformat(),
            "tool": tool_name,
            "args": args if isinstance(args, dict) else str(args or ""),
            "result_preview": result_str[:300] if result_str else "",
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# === WebSocket ===

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    """WebSocket 端点 — 支持多会话 + 后台任务"""
    await ws.accept()
    current_sid = None
    loop = asyncio.get_event_loop()

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            # --- 消息类型 ---
            msg_type = msg.get("type", "chat")

            # 微信订阅/列表不涉及 MemOmics 会话
            if msg_type == "weixin_subscribe":
                _WEIXIN_WS_CLIENTS.add(ws)
                await ws.send_text(json.dumps({
                    "type": "weixin_status",
                    "connected": _weixin_state["connected"],
                    "account_id": _weixin_state["account_id"][:16] + "..." if _weixin_state["account_id"] else "",
                }, ensure_ascii=False))
                continue
            if msg_type == "weixin_unsubscribe":
                _WEIXIN_WS_CLIENTS.discard(ws)
                continue
            if msg_type == "weixin_agent_toggle":
                global _weixin_agent_enabled
                _weixin_agent_enabled = msg.get("enabled", False)
                print(f"[MemOmics] 微信Agent自动回复: {'开启' if _weixin_agent_enabled else '关闭'}", flush=True)
                continue
            if msg_type == "weixin_list":
                await ws.send_text(json.dumps({
                    "type": "weixin_list",
                    "messages": _weixin_msg_store[-50:],
                }, ensure_ascii=False))
                continue

            # 后台任务面板订阅/退订：订阅当场回一份快照，之后由扫描循环按变化推
            if msg_type == "task_subscribe":
                _TASK_WS_CLIENTS.add(ws)
                _ensure_task_watch()
                snapshot = _tasks_payload(limit=100, refresh=1)
                snapshot["type"] = "tasks"
                await ws.send_text(json.dumps(snapshot, ensure_ascii=False))
                continue
            if msg_type == "task_unsubscribe":
                _TASK_WS_CLIENTS.discard(ws)
                continue

            sid = msg.get("session_id")
            prev_sid = current_sid  # 保存上一轮的 sid（switch_session 需要）
            session = _get_or_create_session(sid)
            current_sid = session["id"]

            if msg_type == "switch_session":
                # 前端切换会话 - 不中断旧会话的 agent，也不注销旧会话的 WS。
                # 同一浏览器连接同时服务多个会话：切走会话的事件继续推送，
                # 前端按 session_id 分流缓冲（快照系统切回时重放）。
                _attach_ws(session, ws, loop)
                current_sid = session["id"]
                # 发送进度日志重放
                progress_log = session.get("progress_log", [])
                # 运行状态用 task.done() 判定：已完成但引用未清的任务不算运行中
                # （修复：run_agent 闭包 finally 可能因循环变量指向错会话而漏清理，
                #   导致会话显示"Agent 运行中"且输入被当 steer）
                _rt = session.get("running_task")
                if isinstance(_rt, str):
                    _task_alive = bool(_rt)
                elif _rt is None:
                    _task_alive = False
                else:
                    try:
                        _task_alive = not _rt.done()
                    except Exception:
                        _task_alive = False
                is_running = bool(session.get("running_agent")) and _task_alive
                await ws.send_text(json.dumps({
                    "type": "progress_replay",
                    "progress_log": progress_log,
                    "reasoning_log": [r.get("content", "") for r in session.get("reasoning_log", []) if r.get("content")],
                    # 2026-08-17: 半截流式文本（刷新/重连时恢复进行中的回复）
                    "partial_text": session.get("_partial_text", ""),
                    "is_running": is_running,
                    "session_id": session["id"],
                }, ensure_ascii=False))
                if is_running:
                    await ws.send_text(json.dumps({
                        "type": "agent_running",
                        "session_id": session["id"],
                    }, ensure_ascii=False))
                continue

            elif msg_type == "chat":
                user_text = msg.get("message", msg.get("content", "")).strip()
                image_urls = msg.get("images", []) or []
                # P3(2026-09-22): 用户直接回消息 = 对确认弹窗的答复 → 立即解除执行门禁
                # （弹窗提交走 /api/ask_form/answer 后也把答复当消息发回，会命中这里）
                try:
                    _pf_sid = msg.get("session_id") or session.get("id", "")
                    from webui import enforcement as _enf_c
                    _es_c = _enf_c.get_enforcement(_pf_sid)
                    if _enf_c.clear_awaiting_form(_es_c, "", {"selected": [], "other": user_text[:200],
                                                              "question": getattr(_es_c, "awaiting_form_question", "")}):
                        _pq_list = session.get("_pending_questions") or []
                        for _pq in reversed(_pq_list):
                            if not _pq.get("answered"):
                                _pq["answered"] = True
                                _pq["answer"] = {"selected": [], "other": user_text[:200],
                                                 "via": "chat"}
                                break
                    # 预置门禁（高代价任务还没弹表单）：用户这一轮消息本身就是对
                    # "要做什么"的补充 → 解除，避免同一件事反复追问。
                    if _enf_c.clear_intent_confirm(_es_c):
                        session["_intent_confirmed"] = True
                except Exception:
                    pass
                # 允许仅图片无文字
                if not user_text and not image_urls:
                    continue
                # 新一轮用户指令：重置循环守卫的检测窗口（保留注入计数）
                try:
                    _lg = session.get("_loop_guard")
                    if _lg:
                        with _lg["lock"]:
                            _lg["tool_hist"] = []
                            _lg["turn_texts"] = []
                            _lg["text_buf"] = ""
                            _lg["inject_count"] = 0
                except Exception:
                    pass
                # 2026-08-14: 同步重置"说而不做"唤醒计数（每回合最多 2 次）
                session.pop("_saying_wakeup_n", None)
                # 2026-08-14: 运行状态基线（UI 心跳实时可见）
                session["_turn_start_ts"] = time.time()
                session["_api_calls"] = 0
                session["_partial_text"] = ""  # 2026-08-17: 新回合重置半截文本累积
                session["_real_exec_this_turn"] = False  # 本回合是否有代码真实执行(被护栏跳过的调用不算)
                session["_tool_dedup"] = {}  # 每轮用户消息重置重复执行拦截:用户反复重跑相同代码是合法的
                session["_live_tool"] = ""
                session["_live_tool_ts"] = time.time()
                session["_proc_hist"] = []  # 2026-08-16: 进程采样历史（回合级窗口）
                session["_stall_notice_last"] = 0
                session["_turn_activity_ts"] = time.time()
                # 2026-08-24 修复: 循环检测状态按用户回合重置——之前的 tool_hist/turn_texts
                # 跨回合累计，用户连续几轮做相似的正事（连读两篇文献都调 summarize_paper /
                # nature-reader / skill_view）会被误报"工具调用循环"并注入强制收尾提示。
                # 循环检测只应判断"同一回合内"的重复动作。
                sg = session.get("_loop_guard")
                if sg is not None:
                    with sg.get("lock", _threading_mod.Lock()):
                        sg["tool_hist"] = []
                        sg["turn_texts"] = []
                        sg["text_buf"] = ""
                        sg["inject_count"] = 0
                # 如果有图片，将图片 URL 作为上下文附加到用户消息中
                if image_urls:
                    img_context = "\n\n[用户上传的图片]\n" + "\n".join(f"![]({url})" for url in image_urls)
                    user_text = (user_text or "查看图片") + img_context

                # 问题9: 检测用户语言并更新会话语言
                # 2026-08-17: 显式指定（用英文/answer in english）→ 强制并粘滞；
                # 英文提问且近期上下文无中文 → 英文；上下文有中文 → 保持中文
                detected_lang = _detect_lang(user_text)
                _explicit_lang = _user_lang_instruction(user_text)
                if _explicit_lang:
                    detected_lang = _explicit_lang
                    session["lang_locked"] = _explicit_lang
                elif session.get("lang_locked"):
                    detected_lang = session["lang_locked"]
                elif detected_lang == "en":
                    _recent_msgs = [m for m in (session.get("messages") or [])[-8:]
                                    if m.get("role") == "user" and m.get("content")]
                    if any(_detect_lang(m.get("content", "")) == "zh" for m in _recent_msgs):
                        detected_lang = session.get("lang", "zh")
                session["lang"] = detected_lang

                # 分析级别检测 (闲聊 vs 分析)
                from webui import enforcement as _enf2
                _level = _enf2.detect_analysis_level(user_text)
                _es = _enf2.get_enforcement(session["id"])
                _es.analysis_level = _level
                _es.results_dir = session.get("results_dir", "")
                # 2026-08-16: 用户新消息 = 新指令 → 解除审查硬阻断残留（12G Seurat 案例：
                # rail_review(post) 未通过残留使 execute_r/terminal 一直被拦，死锁）
                if _enf2.clear_hard_block(session["id"]):
                    logger.info(f"[Enforcement] session {session['id'][:12]}: 新用户消息解除审查硬阻断")
                # 2026-08-14: 会话锚点 — 用户点名的路径自动标记 + 注入锚点摘要
                _auto_anchor_turn(session, user_text=user_text)
                # 2026-08-14: 会话轮数计数（长会话可见性：第 N 轮）
                session["_turn_count"] = int(session.get("_turn_count", 0)) + 1
                _run_text = user_text  # (b) 不再把记忆/锚点脚手架拼进用户消息本体（防历史污染），
                # 脚手架由 run_agent 以单条 system 消息注入（见下文 (b) 上下文卫生块）

                # 惰性加载：继续旧会话前，先把完整历史载入内存（保证上下文构建/追加正确）
                _ensure_session_messages_loaded(session)

                # 记录用户消息到 session + state.db
                session["messages"].append({"role": "user", "content": user_text, "time": datetime.now().strftime("%H:%M:%S")})
                session["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # 并发护栏(2026-08-20 memomics-2274ab75 只说不做): 用户消息一进来就置位,
                # 自检唤醒/心跳在该标记为真期间不得启动并发 agent 回合——否则两个回合在
                # 同一 agent 上交错流, single-writer 护栏砍掉在飞流导致工具参数被截断为空。
                # 在 self_intro/agent创建失败/run_agent finally 三处清除。
                session["_user_turn_active"] = True
                # P2-2：显式回合记账（默认只记账，不改行为；同一会话第二个回合起飞时计 conflicts）。
                # P2-2 补丁：MEMOMICS_THREAD_SERIALIZE=1 时先过串行化门——等同会话上一个回合收尾
                # 再开新回合，conflicts 归零；默认关 = 立刻返回、零开销、行为与以前完全一致。
                if _thread_state is not None:
                    if await _thread_state.begin_turn_serialized(session["id"], source="user") is None:
                        logger.warning("[ThreadState] session %s: 串行化门等待超时，按原行为继续",
                                       session["id"][:12])
                # state.db 持久化由 Hermes 框架 _persist_session 自动完成（agent 带 session_db），
                # 手动写入会双写（2026-08-13 实测同秒重复 2 份 → 刷新后回复重复显示）

                # RunGate（P1-A 接线，2026-08-12）：用户主动发消息 = 新指令 →
                # 退役任务（done/cancelled）重置为 pending（命中"继续"词表由 check_gate 内部处理；
                # 未命中返回 ask_user → 用户发消息本身即新指令，保守重置为新任务）
                # 2026-08-27 修复：ask_user 的**否定回答**（"不用了/不需要继续"）不得复活
                # done 任务——实测：模型 ask_user 问"还要继续吗？"→ 用户答"不用"→ 无条件
                # 重置 pending+armed → 已完成任务被唤醒链复活 → 模型被反复叫醒重复输出
                try:
                    from webui.runtime.run_gate import check_gate, save_state, arm, reset_rounds
                    _rd_g = session.get("results_dir", "") or ""
                    if _rd_g:
                        _verdict, _reason = check_gate(_rd_g, is_auto_wake=False, user_message=user_text)
                        if _verdict == "ask_user":
                            if _is_negation_end_answer(user_text):
                                # 用户确认结束/否定 → 保持退役状态（休息），不重置 pending
                                logger.info(f"[RunGate] session {session['id'][:12]}: ask_user 否定回答（{user_text[:30]}）→ 保持任务退役，不复活")
                            else:
                                save_state(_rd_g, "pending", "user message (ask_user -> new task)")
                        # M2/M3（DSH resume 语义的交互式版）：用户在场 = 重新授权 + 预算刷新
                        arm(_rd_g, by="user_message")
                        reset_rounds(_rd_g)
                except Exception:
                    pass

                # 注册 WebSocket 引用 + 立即发送 thinking（在意图分类之前，消除初始空白）
                loop = asyncio.get_event_loop()
                _attach_ws(session, ws, loop)
                # 直接用 await ws.send_text() 而非 _session_emit——确保立刻发送到前端，
                # 不受事件循环排队影响（_session_emit 用 run_coroutine_threadsafe 排队）
                await ws.send_text(json.dumps({"type": "thinking", "content": _pt(session, "understanding") + "...", "session_id": session["id"]}, ensure_ascii=False))
                await ws.send_text(json.dumps({"type": "progress", "step": _pt(session, "thinking"), "status": "pending", "detail": _pt(session, "understanding"), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False))

                # 如果是第一条消息, 更新标题（自动命名：同名自动续号 "xxx #2"，
                # 避免 set_session_title 唯一约束抛 ValueError 被吞导致仍叫"新会话"）
                if len(session["messages"]) == 1:
                    base_title = user_text[:30]
                    db = _get_session_db()
                    if db:
                        try:
                            next_title = db.get_next_title_in_lineage(base_title)
                            db.set_session_title(session["id"], next_title)
                            session["title"] = next_title
                        except Exception:
                            pass
                    else:
                        session["title"] = base_title
                
                # 自动标题总结：每 5 条用户消息触发一次（内容感知，后台异步，不阻塞）
                _user_msg_count = sum(1 for m in session["messages"] if m.get("role") in ("user", "human"))
                if _user_msg_count >= 5 and _user_msg_count % 5 == 0:
                    _schedule_title_summary(session["id"])

                # 图路由：每条消息检测领域 + 意图（不仅是第一条消息，随时切换）
                domain = _detect_domain_from_text(user_text)
                if domain:
                    session["domain"] = domain
                
                # 意图分类 + 构建技能注入上下文
                _intent, _intent_conf, _intent_meta = _classify_intent(user_text)
                # (a2) 低置信度 chat + 会话可能有任务结果 → LLM 兜底路由（规则兜不住时让模型判，
                # 避免"怎么没有结果呢"这类省略上下文短句被当 chat 后只聊不查状态）
                if _intent == "chat" and float(_intent_conf or 0) <= 0.75 and _session_may_have_result(session):
                    _routed = await loop.run_in_executor(None, _llm_route_intent, user_text, session)
                    if _routed:
                        _intent, _intent_conf = _routed, 0.55
                        _intent_meta = {"reason": "llm_router_fallback"}
                        logger.info(f"Session {session['id']}: intent llm-router {_routed} (rules said chat)")
                session["intent"] = _intent
                session["intent_conf"] = _intent_conf
                session["intent_meta"] = _intent_meta

                # 2026-08-14 同会话多任务隔离：新数据路径（非继续）→ 切新任务子目录，
                # 防新任务覆盖旧任务的 task_plan.md/产出；RunGate 重置 pending。
                _maybe_switch_task_dir(session, user_text, _intent)

                # === 会话级状态捕获（诉求 + 资产候选，故障静默不阻塞主流程）===
                try:
                    try:
                        from webui import session_state as _ss
                    except ImportError:
                        import session_state as _ss
                    _ss.capture_user_request(session["id"], user_text, intent=_intent or "chat")
                    # 2026-08-31 P3 接线：project = 结果目录名（资产项目隔离）；
                    # intent 每轮写入 task_json → holographic prefetch 按意图调检索策略
                    _proj = os.path.basename((session.get("results_dir") or "").rstrip("\\/"))
                    _ss.extract_assets(session["id"], user_text, project=_proj or "")
                    _ss.update_task_state(session["id"], intent=_intent or "chat")
                    _extract_and_store_requirements(session, user_text)  # (#2) 要求/路径持久化

                    # === 话题切换检测旁路（P1-4）：analysis 意图且实体变化 → 更新任务状态块 ===
                    try:
                        _ent = _ss.extract_entity(user_text)
                        if _ent and _intent in ("analysis", "research_plan", "direct_exec"):
                            _st = _ss.get_store().get_session_state(session["id"])
                            _task = json.loads(_st.get("task_json") or "{}")
                            _old = _task.get("entity") or ""
                            _sw = _old if (_old and _old != _ent) else ""
                            if _old != _ent:
                                _ss.update_task_state(
                                    session["id"],
                                    entity=_ent,
                                    switched_from=_sw,
                                    last_topic_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                                )
                    except Exception as _sw_err:
                        logger.debug("topic-switch detection failed: %s", _sw_err)
                except Exception as _ss_err:
                    logger.warning("session_state capture failed: %s", _ss_err)

                # RED 必触发预检在 _build_skill_injection 内部完成：
                # chat/self_intro 意图也调用（命中 RED 触发词 → 返回强约束注入；
                # 未命中 → chat 返回空字符串，self_intro 返回「按语境作答 + 事实参考」）
                # P0-3: 显式 /skill-name 调用 —— 用户点名的技能优先级最高（高于置顶与 RED）
                _explicit_inv = _parse_skill_invocations(user_text)
                # 2026-09-26: self_intro 不再走"写好的介绍"快速回复，和别的意图一样交给
                # agent LLM 回答。这里统一构建注入：self_intro 分支现在给的是
                # "按语境作答 + 事实参考"，不是逐字文案。
                _inj_intent = _intent
                _skill_ctx = _build_skill_injection(_inj_intent, domain or session.get("domain", ""), session.get("lang", "zh"), user_text,
                                                  pinned=_pinned_skills_get(session["id"]),
                                                  explicit=_explicit_inv)
                _pinned_expect_emit(session, user_text)  # P8: 置顶技能触发词命中 → 前端标记「本轮应加载」
                _red_hit_emit(session, user_text)        # P0-3: RED 命中原因 → 前端 chip 显示「为什么」
                _skill_invoke_emit(session, _explicit_inv)  # P0-3: 显式点名结果（命中/未知/歧义）→ 前端回显
                logger.info(f"Session {session['id']}: intent={_intent} conf={_intent_conf:.2f} domain={domain or session.get('domain','')}")


                # 发送 session_id（thinking 已在消息到达时即时发送）
                _session_emit(session, {"type": "session", "session_id": session["id"], "title": session["title"]})

                # session 级 agent 复用：如果已有 agent 则复用，否则创建
                agent = session.get("agent")
                if agent is None:
                    # 发送引擎初始化进度（首次加载较大，让用户感知系统在工作）
                    _ei = _pt(session, "initializing_engine")
                    _session_emit(session, {"type": "progress", "step": _ei, "status": "pending",
                        "detail": _pt(session, "loading_skills"), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                    try:
                        agent = _create_agent(session["model_config"], session_id=session["id"], session=session)
                        session["agent"] = agent  # 缓存到 session
                        _session_emit(session, {"type": "progress", "step": _ei, "status": "done",
                            "detail": _pt(session, "engine_ready"), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                    except Exception as e:
                        _session_emit(session, {"type": "error", "content": f"Agent 创建失败: {e}"})
                        session["_user_turn_active"] = False  # 并发护栏: 失败路径也需清除
                        if _thread_state is not None:
                            _thread_state.mark_turn_end(session["id"])
                        continue

                # 清除可能残留的中断标志（上一个 turn 完成后未正确重置会导致新 turn 立即退出）
                if getattr(agent, "_interrupt_requested", False):
                    agent.clear_interrupt()
                # 2026-08-14: 清空上回合残留的循环干预 steer——上一回合注入、
                # 本回合首个 tool batch 后才送达的"停止重复"提示会干扰正常新任务，
                # 造成"图已出完还在跑"。新回合开始即作废旧干预。
                try:
                    _st_lock = getattr(agent, "_pending_steer_lock", None)
                    if _st_lock is not None:
                        with _st_lock:
                            agent._pending_steer = ""
                    else:
                        agent._pending_steer = ""
                except Exception:
                    pass
                session["restored"] = False
                # 问题2: 不再用环境变量传 sid（进程级变量会串会话），改用 agent 实例属性
                agent.memomics_sid = session["id"]
                agent.memomics_session = session

                # 设置线程级会话上下文（纯线程隔离，避免多会话竞态）
                from memomics.bio_tools.debate_analysis import set_session_context
                _set_debate_session_context(session)
                # 注意：不再写 os.environ，多会话并发时 os.environ 会串会话

                # 注入 results_dir 到 Agent 系统提示词，确保输出文件写到正确位置
                rd = session.get("results_dir", "")
                # 🔧 按意图裁剪 system prompt：
                #   无数据路径 → SOUL.md only (~15KB) 轻量响应
                #   有数据路径 + 分析执行 → SOUL.md + detail + skills_index + PLANNING
                import re as _re_path
                _has_data_path = bool(_re_path.search(r'[A-Za-z]:[/\\]\S+', user_text)) if user_text else False
                # 轻量意图：永远不注入 SOUL-detail + skills_index（省 40%+ 上下文）
                _LIGHT_INTENTS = ("chat", "self_intro", "knowledge_ask", "progress_check", "result_check", "analysis_plan", "cancel_task")
                # 重量意图：仅 explicit execution 或 analysis + 数据路径 + 执行关键词
                _has_exec_kw = any(kw in user_text for kw in
                    ("跑", "执行", "开始", "启动", "运行", "run", "start", "execute", "analyze")) if user_text else False
                _is_explicit_exec = _intent in ("analysis_exec", "direct_exec")
                _is_heavy = _is_explicit_exec or (
                    _intent not in _LIGHT_INTENTS
                    and _has_data_path
                    and _has_exec_kw
                )
                # 2026-08-21 缓存优化：light/heavy 若用不同结构系统提示，同一会话
                # 交替回合（分析↔闲聊）会让 DeepSeek 前缀缓存整体失效（实测回合首
                # 调用 miss 140K+）。统一为基础段（soul+skills+PLANNING+目录+语言），
                # light 只是不再注入 KB/领域尾部；heavy 的 KB 注入已走 _kb_tail。
                _soul_detail = ""
                try:
                    _detail_path = os.path.join(HERMES_HOME_DIR, "SOUL-detail.md")
                    if os.path.isfile(_detail_path):
                        with open(_detail_path, encoding="utf-8") as _f:
                            _soul_detail = _f.read()
                except Exception:
                    pass
                _skills = _read_skills_index()
                agent.ephemeral_system_prompt = (_soul_detail + "\n\n" + _skills + _PLANNING_PROMPT
                                                 + "\n\n" + _EXECUTION_POLICY)
                if rd:
                    agent.ephemeral_system_prompt += f"\n\n## 当前会话输出目录\n所有 R/Python/终端脚本的输出文件（图片、表格、报告）请保存到：\n`{rd.replace(chr(92), '/')}`\n请使用绝对路径或在脚本开头 `setwd()` / `os.chdir()` 到此目录。\n**脚本落盘约定**：分析/绘图脚本(.py/.r/.sh)统一保存到 `{rd}/scripts/`(用描述性文件名)；重复跑图/统计时，先 `search_files` 查看 `{rd}/scripts/` 已有脚本再复用，不要每次重写。\n"
                    agent.ephemeral_system_prompt += (
                        f"**输出归位铁律（2026-08-25）**：产出文件必须写入 `{rd.replace(chr(92), '/')}` 的对应子目录：\n"
                        f"- 图 → `{rd.replace(chr(92), '/')}/figures/`\n"
                        f"- 表/结果 → `{rd.replace(chr(92), '/')}/results/`\n"
                        f"- 脚本 → `{rd.replace(chr(92), '/')}/scripts/`\n"
                        f"- 数据 → `{rd.replace(chr(92), '/')}/data/`\n"
                        f"- 日志 → `{rd.replace(chr(92), '/')}/log/`\n"
                        f"禁止把产出直接写到 `{rd.replace(chr(92), '/')}` 根目录（子目录已由系统创建）。\n"
                        "回合结束时，向用户汇报**本次回合新增**的产出（类别 + 相对路径，"
                        "如 `figures/umap.png`、`results/cluster_stats.csv`），不要只说'已生成图'不给出位置。"
                        "历史产出较多时只给总数总览（如'另有历史产出 87 个文件，完整清单见 review/assets.json'），"
                        "**不要逐条罗列全部历史文件**——避免长清单拖慢回合、膨胀历史。")

                    # 🔧 分析任务自动预查知识库 + 方法路线引导
                    # 2026-08-21 缓存优化：KB 预查询/领域引导内容随用户消息变化，
                    # 注入 system prompt(=请求前缀头部) 会破坏 DeepSeek 前缀缓存
                    # （实测连续回合命中率仅 12-22%）。已改为尾部 system 消息注入
                    # （见 conversation_history 构建处 _kb_tail），前缀保持稳定
                    # （soul+skills+PLANNING），命中率可回 90%+。

                # 2026-08-17: 回答语言策略 — 把会话语言显式注入 Agent 系统提示
                # （英文提问+无中文上下文 / 用户显式指定英文 → 全程英文回复；否则中文）
                _resp_lang = session.get("lang", "zh")
                if _resp_lang == "en":
                    agent.ephemeral_system_prompt += (
                        "\n\n## 回答语言（最高优先）\n"
                        "用户当前使用英文交流。请用**英文**完成本回合及后续所有回复："
                        "包括分析结论、图表标题与图注、报告正文与文件名，不要混用中文。"
                    )
                else:
                    agent.ephemeral_system_prompt += (
                        "\n\n## 回答语言（最高优先）\n"
                        "请使用**中文**回复用户（包括图表标题与图注、报告正文）。"
                    )

                # 进度发送辅助函数
                def _send_progress(step, status, detail="", _s=session):
                    """发送进度时间线条目 - 同时存储到 progress_log"""
                    _session_emit(_s, {"type": "progress", "step": step, "status": status, "detail": detail, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _s["id"]})

                # 回调
                has_delta = False  # 追踪是否已通过流式发送过文本

                def stream_cb(delta, _s=session):
                    nonlocal has_delta
                    try:
                        if delta is None: return
                        has_delta = True
                        _s["_turn_activity_ts"] = time.time()
                        _loop_check(_s, None, "delta", delta=delta)
                        _session_emit(_s, {"type": "delta", "content": str(delta), "session_id": _s["id"]})
                    except Exception:
                        pass

                def reasoning_cb(text, _s=session):
                    try:
                        if text is None: return
                        _s["_turn_activity_ts"] = time.time()
                        _session_emit(_s, {"type": "reasoning", "content": str(text), "session_id": _s["id"]})
                    except Exception:
                        pass

                _tool_call_log = []
                
                def tool_start_cb(tool_id, tool_name, args=None, _s=session):
                    try:
                        # 循环检测：连续重复工具调用（如反复 tail 日志监控安装）
                        _loop_check(_s, None, "tool_start", tool_name=tool_name, args=args)
                        # 2026-08-16 任务类型：terminal background=True = 长任务运行时证据
                        if tool_name == "terminal" and isinstance(args, dict) and args.get("background") is True:
                            _mark_task_long_running(_s)
                        _s["_turn_activity_ts"] = time.time()
                        # 批M(2026-08-16) 工具调用爆炸护栏：
                        # 事故 memomics-2274ab75 05:47:52 —— 模型一次响应并发发射 984 次
                        # 相同的 execute_code（每个都在里面再跑一遍 python 出图脚本），
                        # 机器被拖垮、用户被迫手动停止。两重保护：
                        #   (1) 昂贵工具（execute_code/execute_python/execute_r）相同参数
                        #       在同一轮内只执行第一次，其余重复调用跳过并返回失败
                        #   (2) 单回合工具调用总数上限 100 —— 超过后所有昂贵工具一律跳过
                        # 2026-08-16 修订(memomics-2274ab75 用户反馈):
                        #   - 拦截范围限定"单轮"：每轮新用户消息都会清零 _tool_dedup ——
                        #     用户合法地反复重跑相同代码（改图改很多遍）不受任何限制
                        #   - 记录带 tid：hermes 对同一调用会触发两次回调(预检+执行worker)，
                        #     同一调用的第二次触发不算重复，只有"别的调用"提交相同代码才拦截
                        #   - 跳过的调用以非零退出码结束(status=error)，模型不会再误报"已生成"
                        _dedup = _s.setdefault("_tool_dedup", {})
                        _now_d = time.time()
                        if len(_dedup) > 300:
                            _dedup = {k: v for k, v in _dedup.items()
                                      if _now_d - v.get("ts", 0) < 90}
                            _s["_tool_dedup"] = _dedup
                        _expensive = tool_name in ("execute_code", "execute_python", "execute_r")
                        if _expensive and isinstance(args, dict):
                            try:
                                import hashlib as _hl
                                _key = tool_name + ":" + _hl.sha1(
                                    json.dumps(args, sort_keys=True, default=str).encode("utf-8")).hexdigest()
                            except Exception:
                                _key = ""
                            _rec = _dedup.get(_key) if _key else None
                            # 同一调用的第二次回调(执行worker)不算重复 —— 它才是真正执行的那次
                            _fresh = bool(_rec and _now_d - _rec.get("ts", 0) < 90
                                          and _rec.get("tid") != tool_id)
                            _over_cap = int(_s.get("_api_calls", 0)) >= 100
                            if _fresh or _over_cap:
                                _n = (_rec.get("n", 0) + 1) if _rec else 1
                                if _fresh:
                                    _skip_msg = (
                                        "本次调用未执行任何代码，磁盘文件没有任何变化。"
                                        "本回合内已执行过完全相同的代码（以那次执行的真实结果为准），本次重复调用被跳过。"
                                        "如需重新生成：请先修改代码内容再调用；或直接发新一轮用户消息后再跑（每轮开始会重置此限制）。"
                                        "不要宣称“已生成/已修改”。")
                                else:
                                    _skip_msg = (
                                        "回合保护：本回合工具调用已超 100 次，本次未执行任何代码。"
                                        "请先总结已完成的步骤并交付结果，不要宣称“已生成/已修改”。")
                                if _n >= 3:
                                    _skip_msg += f"（已连续 {_n} 次提交完全相同的代码且全部被跳过，请立即停止重试）"
                                # 关键修复(2026-08-16 memomics-2274ab75):用非零退出码结束,
                                # 工具结果会是 status=error —— 模型会明确知道"没有执行成功",
                                # 而不是像旧实现那样收到 status=ok 后误报"✅ 已重新生成"
                                if tool_name == "execute_r":
                                    args["code"] = (
                                        "cat('[⛔ 执行保护] " + _skip_msg + "')\n"
                                        "stop('[⛔ 执行保护] skipped')\n")
                                else:
                                    args["code"] = (
                                        "import sys\n"
                                        "print('[⛔ 执行保护] " + _skip_msg + "', file=sys.stderr)\n"
                                        "raise SystemExit(3)\n")
                                # 跳过后不刷新 ts:窗口从第一次真实执行起算,风暴停止后自然过期
                                if _rec:
                                    _rec["n"] = _n
                                logger.warning(f"[MemOmics] 工具调用护栏: {tool_name} {_skip_msg} (n={_n})")
                                _session_emit(_s, {"type": "warning",
                                    "content": f"⛔ {_skip_msg}（{tool_name}）",
                                    "session_id": _s["id"]})
                            else:
                                _dedup[_key] = {"ts": _now_d, "n": 1, "tid": tool_id}
                        # 强制保护：禁止自杀命令 + 禁止删除数据
                        if tool_name in ("terminal", "execute_code", "execute_python") and isinstance(args, dict):
                            _cmd = str(args.get("command", args.get("code", "")))
                            if _cmd:
                                if _is_suicide_command(_cmd):
                                    logger.warning(f"[MemOmics] 拦截自杀命令: {_cmd[:100]}")
                                    args["command"] = "echo '⛔ 此命令已被拦截——它会杀死 MemOmics 自己。请用 taskkill /F /PID <具体PID>'"
                                    args["code"] = "print('⛔ 此代码已被拦截——它会杀死 MemOmics 自己')"
                                    _session_emit(_s, {"type": "error",
                                        "content": "⛔ 自杀命令已拦截！请用 taskkill /F /PID <具体PID> 指定精确进程",
                                        "session_id": _s["id"]})
                                if _is_data_destroy_command(_cmd) or _is_code_destroy(_cmd):
                                    logger.warning(f"[MemOmics] 拦截删除操作: {_cmd[:100]}")
                                    # 不直接阻断，改为引导 Agent 向用户展示删除内容并请求确认
                                    _safe_cmd = _cmd[:300].replace("'", "'\"'\"'")
                                    args["command"] = (
                                        f"echo '[⚠️ 操作需确认] 你刚才尝试执行删除操作。'\n"
                                        f"echo ' '\n"
                                        f"echo '📋 要执行的命令:'\n"
                                        f"echo '  {_safe_cmd}'\n"
                                        f"echo ' '\n"
                                        f"echo '⛔ 此操作未被直接执行。请先向用户展示:\n"
                                        f"echo '  1. 列出要删除的具体文件和目录\n"
                                        f"echo '  2. 说明为什么需要删除\n"
                                        f"echo '  3. 等待用户明确回复\"确认删除\"后再执行'\n"
                                        f"echo ' '\n"
                                        f"echo '💡 用户确认后，请使用确认后的命令重新执行。'"
                                    )
                                    args["code"] = (
                                        "print('[⚠️ 操作需确认] 你刚才尝试执行删除操作。')\n"
                                        "print()\n"
                                        "print('⛔ 此操作未被直接执行。请先向用户展示要删除的具体文件和原因，等待用户确认后再执行。')"
                                    )
                                    _session_emit(_s, {"type": "warning",
                                        "content": f"⚠️ Agent 尝试删除文件：{_cmd[:200]}\n\n操作已暂停。请 Agent 先向用户列出要删除的内容并等待确认。",
                                        "session_id": _s["id"]})
                        # 文件产出型工具 — 首次调用时按需创建 results_dir
                        _PRODUCING_TOOLS = {
                            "scan_data", "execute_r", "execute_python", "terminal",
                            "execute_code", "update_results_dir", "add_figure",
                            "generate_report", "debate_analysis", "run_command",
                        }
                        if tool_name in _PRODUCING_TOOLS and not _s.get("_dir_created"):
                            _ensure_results_dir(_s)
                            _s["_dir_created"] = True
                        # (3) 脚本落盘约定(非阻断提醒)：写 .py/.r/.sh 且不在会话 scripts/ 下 → 提示复用
                        if tool_name == "write_file" and isinstance(args, dict):
                            try:
                                _fp = str(args.get("path", ""))
                                if _fp.lower().endswith((".py", ".r", ".sh", ".m", ".rmd")):
                                    _rdir = _s.get("results_dir") or ""
                                    _sdir = os.path.join(_rdir, "scripts") or ""
                                    if _rdir and not _fp.replace("\\", "/").startswith(_sdir.replace("\\", "/")):
                                        _session_emit(_s, {"type": "warning",
                                            "content": f"⏳ 脚本落盘提醒（不阻断）：分析脚本建议保存到 `{_sdir}`（会话目录 scripts/）。当前路径：`{_fp}`。下次重复跑图请先到 scripts/ search_files 找已有脚本。",
                                            "session_id": _s["id"]})
                            except Exception:
                                pass
                        # 记录本回合是否有真实执行(被执行保护替换成占位打印的调用不算)
                        if tool_name in _PRODUCING_TOOLS and isinstance(args, dict):
                            if "[⛔ 执行保护]" not in str(args.get("command", args.get("code", ""))):
                                _s["_real_exec_this_turn"] = True
                        _tool_call_log.append({"tool": tool_name, "id": tool_id})
                        _s["_api_calls"] = int(_s.get("_api_calls", 0)) + 1
                        _s["_live_tool"] = tool_name
                        _s["_live_tool_ts"] = time.time()
                        _s.pop("_live_tool_warned", None)  # 每个工具各自一次 30min 长工具提醒
                        _session_emit(_s, {"type": "tool_start", "tool": tool_name, "args": args or {}, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _s["id"]})
                        # P1-2(2026-09-23): 改动复核 —— 执行前抓「改前」快照（此时文件尚未被改）
                        try:
                            _snapshot_before_change(_s, tool_name, args)
                        except Exception as _e_snap:
                            logger.warning(f"[changes] 快照失败: {_e_snap}")
                        # P8: 记录本会话实际加载过的 skill（前端徽标 + 每轮审计数据源）
                        try:
                            if tool_name == "skill_view" and isinstance(args, dict) and args.get("name"):
                                _skill_usage_note(_s["id"], str(args["name"]), _s)
                        except Exception:
                            pass

                        # 问题4: 激活进度时间线 — 工具开始时推送进度
                        _send_progress(_pt(_s, "executing") + ": " + tool_name, "pending", tool_name)
                    except Exception:
                        pass

                # 跟踪已知的图片文件，用于检测新图
                _known_figures = set()

                def _scan_new_figures(_s=session):
                    """扫描 results_dir 下的新图片，返回新增列表"""
                    new_figs = []
                    base = _s.get("results_dir", "")
                    if not base or not os.path.isdir(base):
                        return new_figs
                    img_exts = {'.png', '.jpg', '.jpeg', '.svg'}
                    try:
                        for p in Path(base).rglob("*"):
                            if p.is_file() and p.suffix.lower() in img_exts:
                                key = str(p)
                                if key not in _known_figures:
                                    _known_figures.add(key)
                                    new_figs.append({
                                        "name": p.name,
                                        "rel_path": str(p.relative_to(base)).replace("\\", "/"),
                                        "url": f"/api/results/{_s['id']}/figure?path={str(p.relative_to(base)).replace(chr(92), '/')}",
                                        "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%H:%M:%S"),
                                    })
                    except Exception:
                        pass
                    return new_figs

                _main_loop = asyncio.get_running_loop()  # for thread-safe async scheduling

                def tool_complete_cb(tool_id, tool_name, args=None, result=None, _s=session, _agent=agent):
                    try:
                        result_str = str(result or "")
                        # 2026-08-16: 长工具完成后刷新活动时间 + 清除工具在飞标记——
                        # 否则 watchdog 会在长工具结束后立即把"模型思考间隙"误判成挂起，
                        # 且工具豁免会泄漏到工具结束之后。
                        _s["_turn_activity_ts"] = time.time()
                        _s["_live_tool"] = ""
                        _s["_live_tool_ts"] = time.time()
                        _ev_complete = {"type": "tool_complete", "tool": tool_name, "result": result_str[:500], "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _s["id"]}
                        # 2026-09-18: 辩论完成 → 事件里带上完整辩论归档，前端据此渲染「辩论过程」表格
                        # （tool_complete 的 result 只有 500 字，装不下 7 位编辑的完整论点）
                        if tool_name == "debate_analysis":
                            try:
                                _deb = _load_latest_debate(_s["id"])
                                if _deb.get("ok"):
                                    _ev_complete["debate"] = _deb
                                else:
                                    _ev_complete["debate_error"] = _deb.get("error", "")
                            except Exception:
                                pass
                        _session_emit(_s, _ev_complete)
                        # P1-2(2026-09-23): 改动复核 —— 工具跑完结算 before/after，产出 diff 并推送
                        try:
                            _finalize_file_change(_s, tool_name, args)
                        except Exception as _e_chg:
                            logger.warning(f"[changes] 结算失败: {_e_chg}")
                        # P2(2026-09-22): 裁决 → 会话待办（辩论结果必须进入下一步进程）
                        if tool_name == "debate_analysis":
                            try:
                                from webui import enforcement as _enf_plan
                                _es_plan = _enf_plan.get_enforcement(_s["id"])
                                _dt = list(getattr(_es_plan, "debate_todos", []) or [])
                                _plan = dict(getattr(_es_plan, "debate_plan", {}) or {})
                                if _dt:
                                    # 注意：Hermes TodoStore 只有 {id, content, status} 三字段，
                                    # 且没有 add()（只有 write(merge=True)）——写错会静默丢失待办。
                                    if hasattr(_agent, "_todo_store") and _agent._todo_store is not None:
                                        _agent._todo_store.write(
                                            [{"id": t.get("id", ""), "content": t.get("title", ""),
                                              "status": "pending"} for t in _dt], merge=True)
                                        _cur = [t for t in _agent._todo_store.read() if isinstance(t, dict)]
                                        _todos_pub = [{"id": t.get("id", ""),
                                                       "title": t.get("title", t.get("content", "")),
                                                       "status": t.get("status", "pending"),
                                                       "module": t.get("module", "")} for t in _cur]
                                    else:
                                        _todos_pub = [{"id": t.get("id", ""), "title": t.get("title", ""),
                                                       "status": t.get("status", "pending"), "module": "debate"} for t in _dt]
                                    _session_emit(_s, {"type": "todos_update", "todos": _todos_pub,
                                                       "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _s["id"]})
                                    logger.info(f"[DEBATE-PLAN] {len(_dt)} 条裁决待办已进入会话待办 decision={( _plan.get('decision') or '')[:60]}")
                            except Exception as _e_plan:
                                logger.warning(f"[DEBATE-PLAN] 待办同步失败: {_e_plan}")
                        # 问题4: 激活进度时间线 — 工具完成时推送进度
                        _send_progress(_pt(_s, "tool_completed") + ": " + tool_name, "done", tool_name)
                        # 2026-08-16 任务类型：管线启动命令 = 长任务运行时证据
                        _is_launch = tool_name in ("terminal", "execute_code", "execute_python") and _is_launch_command(str(args))
                        if _is_launch:
                            _mark_task_long_running(_s)
                        # 强制验证：仅 CellBender 类启动做 GPU/进程二次确认（画图/普通脚本不触发）
                        if _is_launch and "cellbender" in str(args).lower():
                            _session_emit(_s, {"type": "progress", "step": "verify_launch", "status": "pending",
                                "detail": "验证启动状态...", "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _s["id"]})
                            try:
                                import time as _t
                                _t.sleep(3)  # 等进程启动
                                # P1-16(2026-08-13): 平台守卫 — Windows 用 tasklist；
                                # POSIX 用 ps -ef（nvidia-smi 缺失时静默跳过 GPU 检查）
                                if os.name == "nt":
                                    _check = subprocess.run("nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader",
                                        shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
                                    _gpu = _check.stdout.strip()
                                    _check2 = subprocess.run("tasklist | findstr cellbender",
                                        shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
                                    _proc = _check2.stdout.strip()
                                    _failed = ("0 %" in _gpu and not _proc)
                                else:
                                    _gpu = ""
                                    _check = subprocess.run("nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader",
                                        shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
                                    if _check.returncode == 0:
                                        _gpu = _check.stdout.strip()
                                    _check2 = subprocess.run("ps -ef | grep -E 'cellbender|rscript|python' | grep -v grep",
                                        shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
                                    _proc = _check2.stdout.strip()
                                    _failed = ("0 %" in _gpu and not _proc) if _gpu else False
                                if _failed:
                                    _session_emit(_s, {"type": "error",
                                        "content": "⚠️ 启动命令已执行但 GPU 0%、无 CellBender 进程——可能启动失败！请检查命令和日志。",
                                        "session_id": _s["id"]})
                                    logger.warning(f"[MemOmics] Launch verify FAILED: GPU={_gpu}, proc={_proc}")
                                else:
                                    _session_emit(_s, {"type": "progress", "step": "verify_launch", "status": "done",
                                        "detail": f"GPU {_gpu or 'n/a'} — 进程已启动", "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _s["id"]})
                            except Exception:
                                pass
                        # 2026-08-16 任务类型：cron 心跳部署 = 长任务运行时证据
                        if tool_name == "cronjob" and "heartbeat" in str(args).lower():
                            _mark_task_long_running(_s)
                        # 持久化工具调用到 state.db 的 tool_calls_log 表
                        try:
                            import json as _tcl_json
                            import time as _tcl_time
                            import os as _tcl_os  # 2026-08-20: 局部别名, 规避闭包作用域 os 未绑定
                            _db_path = _tcl_os.path.join(HERMES_HOME_DIR, "state.db")
                            _args_json = _tcl_json.dumps(args, ensure_ascii=False, default=str) if args else ""
                            _result_trunc = result_str[:2000]  # 截断长结果
                            import sqlite3 as _tcl_sqlite
                            _conn = _tcl_sqlite.connect(_db_path, timeout=10)
                            _conn.execute("PRAGMA journal_mode=WAL")
                            _conn.execute("PRAGMA busy_timeout=5000")
                            _conn.execute(
                                "INSERT INTO tool_calls_log (session_id, tool_name, tool_id, args_json, result_text, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                                (_s["id"], tool_name, str(tool_id or ""), _args_json, _result_trunc, _tcl_time.time())
                            )
                            _conn.commit()
                            _conn.close()
                        except Exception as _tcl_err:
                            # 2026-08-17: 此前 except:pass 静默吞错，表 35 小时零行；记录原因
                            logger.warning(f"[tool_log] tool_calls_log 写入失败: {_tcl_err}")
                        # 检测 skill_evolution 自进化事件
                        if tool_name == "skill_evolution":
                            try:
                                import json as _json
                                # result 可能是 JSON string
                                result_obj = _json.loads(result_str) if isinstance(result_str, str) else result_str
                                if isinstance(result_obj, dict) and result_obj.get("_evolution_event"):
                                    evt = result_obj["_evolution_event"]
                                    _session_emit(_s, {"type": "evolution", "event": evt, "skill": result_obj.get("skill", ""), "script": result_obj.get("script", ""), "tag": result_obj.get("tag", ""), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _s["id"]})
                            except Exception:
                                pass
                        # todo/todo_manage/memomics_pipeline 完成后同步待办到前端
                        if tool_name in ("todo", "todo_manage", "memomics_todo_manage", "memomics_pipeline"):
                            try:
                                # memomics_pipeline 返回的 todos 写入 store
                                if tool_name == "memomics_pipeline" and hasattr(_agent, "_todo_store"):
                                    try:
                                        result_obj = json.loads(result_str) if isinstance(result_str, str) else result_str
                                        if isinstance(result_obj, dict):
                                            # 缓存 pipeline 结果供后续合并
                                            _s["_pipeline_todos"] = result_obj.get("todos", result_obj.get("modules", []))
                                            # 如果有 todos，写入 store
                                            if result_obj.get("todos"):
                                                for td in result_obj["todos"]:
                                                    _agent._todo_store.add({
                                                        "title": td.get("title", td.get("name", "")),
                                                        "module": td.get("module", td.get("id", "")),
                                                        "skill": td.get("skill", ""),
                                                        "status": "pending",
                                                        "description": td.get("description", td.get("desc", ""))
                                                    })
                                    except Exception:
                                        pass
                                # ⚡ 桥接: todo_manage → _agent._todo_store
                                if tool_name == "todo_manage" and hasattr(_agent, "_todo_store"):
                                    try:
                                        result_obj = json.loads(result_str) if isinstance(result_str, str) else result_str
                                        if isinstance(result_obj, dict) and result_obj.get("action") in ("create",) and result_obj.get("todos"):
                                            hermes_todos = []
                                            for i, td in enumerate(result_obj["todos"]):
                                                hermes_todos.append({
                                                    "id": td.get("id", f"todo_{i}"),
                                                    "content": f"[{td.get('module_id','')}] {td.get('substep_name','')}",
                                                    "status": td.get("status", "pending"),
                                                })
                                            _agent._todo_store.write(hermes_todos)
                                            # 同时缓存为 pipeline_todos 供 skill 映射
                                            _s["_pipeline_todos"] = result_obj["todos"]
                                        # 兜底: todo_manage 未传 modules → 0个todo → 自动生成默认待办
                                        elif isinstance(result_obj, dict) and result_obj.get("action") in ("create",) and not result_obj.get("todos"):
                                            if not _agent._todo_store.has_items():
                                                try:
                                                    import sys, os
                                                    from memomics.memomics_pipeline import modules_to_todos
                                                    default_ids = ["01","02","03","04","05"]
                                                    pipe_todos = modules_to_todos(default_ids)
                                                    hermes_todos = []
                                                    for i, td in enumerate(pipe_todos):
                                                        hermes_todos.append({
                                                            "id": td.get("id", f"todo_{i}"),
                                                            "content": td.get("title", td.get("name", f"Module {td.get('module','')}-{td.get('substep','')}")),
                                                            "status": "pending",
                                                        })
                                                    _agent._todo_store.write(hermes_todos)
                                                    session["_pipeline_todos"] = pipe_todos
                                                    logger.info(f"[TODO-FALLBACK] 自动生成 {len(pipe_todos)} 个默认待办")
                                                except Exception:
                                                    pass
                                    except Exception:
                                        pass
                                # 规范化 store_todos: 字符串→字典；模糊匹配补充 skill
                                store_todos_raw = list(_agent._todo_store.read()) if hasattr(_agent, "_todo_store") and _agent._todo_store else []
                                store_todos = []
                                for t in store_todos_raw:
                                    if isinstance(t, str):
                                        store_todos.append({"title": t, "status": "pending", "skill": "", "module": ""})
                                    elif isinstance(t, dict):
                                        # Hermes TodoStore 格式: {id, content, status} → {title, status, skill, module}
                                        if "content" in t and "title" not in t:
                                            store_todos.append({
                                                "title": t.get("content", ""),
                                                "status": t.get("status", "pending"),
                                                "skill": t.get("skill", ""),
                                                "module": t.get("module", t.get("module_id", "")),
                                                "id": t.get("id", ""),
                                            })
                                        else:
                                            store_todos.append(t)
                                pipeline_todos = session.get("_pipeline_todos", [])
                                if not store_todos and pipeline_todos:
                                    todos = pipeline_todos
                                else:
                                    todos = store_todos
                                    if pipeline_todos:
                                        skill_map = {}
                                        for pt in pipeline_todos:
                                            if isinstance(pt, dict) and pt.get("skill"):
                                                ttl = pt.get("title", pt.get("name", ""))
                                                skill_map[ttl] = pt
                                                for kw in re.split(r"[\s\-–—]+", ttl.lower()):
                                                    if len(kw) >= 3:
                                                        skill_map[kw] = pt
                                        for st in todos:
                                            if not st.get("skill"):
                                                ttl = st.get("title", "")
                                                if ttl in skill_map:
                                                    st["skill"] = skill_map[ttl].get("skill", "")
                                                    st["module"] = skill_map[ttl].get("module", "")
                                                else:
                                                    best, best_score = None, 0
                                                    for kw, pt in skill_map.items():
                                                        if len(kw) >= 4 and kw in ttl.lower():
                                                            if len(kw) > best_score:
                                                                best_score = len(kw)
                                                                best = pt
                                                    if best:
                                                        st["skill"] = best.get("skill", "")
                                                        st["module"] = best.get("module", "")
                                if todos and len(todos) > 0:
                                    # P2(2026-09-22): 裁决待办完成状态回写（blocks 硬约束据此解除）
                                    try:
                                        from webui import enforcement as _enf_sync
                                        _n_sync = _enf_sync.sync_debate_todos(
                                            _enf_sync.get_enforcement(session["id"]), todos)
                                        if _n_sync:
                                            logger.info(f"[DEBATE-PLAN] 裁决待办状态同步 {_n_sync} 条")
                                    except Exception:
                                        pass
                                    _session_emit(session, {"type": "todos_update", "todos": todos, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                            except Exception:
                                pass
                        # P5: 文献结果缓存 (去重, 24h 有效)
                        if tool_name in ("literature_search", "search_papers", "search_papers_by_context", "search_knowledge", "search_knowledge_base"):
                            try:
                                import hashlib as _hl
                                query_key = _hl.md5(str(args).encode()).hexdigest()[:16]
                                _lit_cache[query_key] = (time.time(), result_str[:10000], session["id"])
                                now2 = time.time()
                                _lit_cache.update({k: v for k, v in list(_lit_cache.items()) if now2 - v[0] < 86400})
                            except Exception: pass
                        # terminal 执行后检测新图片
                        if tool_name in ("terminal", "run_command", "execute_code"):
                            new_figs = _scan_new_figures()
                            for fig in new_figs:
                                _session_emit(session, {"type": "new_figure", "figure": fig, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]})
                                # 📱 新图片自动推送微信
                                img_path = os.path.join(session.get("results_dir", ""), fig["rel_path"])
                                _weixin_push_image(img_path, f"🖼️ {fig['name']}", loop=_main_loop)
                        # 🔧 系统级自动日志：每个关键工具调用都写入 log/ 目录
                        # 先确保 results_dir 物理目录存在（纯聊天不创建，首次分析自动创建）
                        _ensure_results_dir(session)
                        _auto_system_log(session, tool_name, args, result_str, tool_id=tool_id)
                        # 📱 微信进度推送：关键步骤完成时推送到微信
                        _weixin_push_progress(session, tool_name, result_str, loop=_main_loop)
                        # 🔧 update_results_dir 后同步更新 session 的 results_dir
                        # 安全规则：results_dir 必须在 results/ 下，外部路径改为 output_root 镜像
                        if tool_name == "update_results_dir":
                            try:
                                resp = json.loads(result_str)
                                if resp.get("ok") and resp.get("results_dir"):
                                    new_dir = resp["results_dir"].replace("/", os.sep)
                                    _results_base = os.path.abspath(RESULTS_DIR).rstrip(os.sep)
                                    if os.path.abspath(new_dir).startswith(_results_base + os.sep) or \
                                       os.path.abspath(new_dir) == _results_base:
                                        # 合法：在 results/ 下，直接更新
                                        session["results_dir"] = new_dir
                                        db = _get_session_db()
                                        if db:
                                            db.update_session_cwd(session["id"], new_dir.replace("\\", "/"))
                                    else:
                                        # 外部路径（如桌面）：不覆盖 results_dir，记录为 output_root
                                        session["output_root"] = new_dir
                                        logger.info(f"[MemOmics] update_results_dir 外部路径记录为 output_root: {new_dir}")
                            except Exception:
                                pass
                    except Exception:
                        pass

                def status_cb(category, message, _s=session):
                    try:
                        _session_emit(_s, {"type": "status", "category": category, "content": message, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _s["id"]})
                    except Exception:
                        pass

                def notice_cb(notice, _s=session):
                    try:
                        # 提取 notice 的关键字段（AgentNotice 对象）
                        notice_text = getattr(notice, 'text', None) or str(notice)
                        notice_key = getattr(notice, 'key', None) or ''
                        notice_level = getattr(notice, 'level', None) or 'info'
                        _session_emit(_s, {"type": "notice", "content": notice_text[:500], "key": notice_key, "level": notice_level, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _s["id"]})
                    except Exception:
                        pass

                def notice_clear_cb(key, _s=session):
                    """Hermes notice_clear_callback: 清除前端对应的通知"""
                    try:
                        _session_emit(_s, {"type": "notice_clear", "key": str(key), "session_id": _s["id"]})
                    except Exception:
                        pass

                def tool_gen_cb(tool_name, partial_args="", _s=session):
                    """Hermes tool_gen_callback: 工具参数生成中实时回调"""
                    try:
                        _session_emit(_s, {"type": "tool_gen", "tool": tool_name, "partial": str(partial_args)[:300], "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _s["id"]})
                    except Exception:
                        pass

                def tool_progress_cb(tool_name, progress_msg, percent=None, _s=session):
                    try:
                        _s["_turn_activity_ts"] = time.time()
                    except Exception:
                        pass
                    """Hermes tool_progress_callback: 工具执行进度更新"""
                    try:
                        # 问题9: 翻译英文事件名为会话语言
                        msg_str = str(progress_msg)
                        if msg_str == "tool.started":
                            msg_str = _pt(_s, "tool_started")
                        elif msg_str == "tool.completed":
                            msg_str = _pt(_s, "tool_completed")
                        _session_emit(_s, {"type": "tool_progress", "tool": tool_name, "content": msg_str[:500], "percent": percent, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _s["id"]})
                        # 问题4: 同步推送到进度时间线
                        _send_progress(_pt(_s, "executing") + ": " + tool_name, "pending", msg_str[:200])
                    except Exception:
                        pass

                agent.stream_delta_callback = stream_cb
                agent.reasoning_callback = reasoning_cb
                # P0-1(2026-08-13): 合并 enforcement 回调（_create_agent 已注册）——
                # 之前本地回调直接覆盖，导致审查硬阻断（es.blocked / 自杀命令 / record_run 门禁）在主聊天路径失效。
                # enforcement 回调返回 {"blocked": True, "message": ...} 时透传给 tool_executor 硬拦截。
                # 2026-08-17: 幂等合并——此前每次进入都再包一层，链长随触发次数增长
                # （实测单事件被触发 984 次 → system_log 写放大 984x、UI 卡顿）
                if not getattr(agent, "_memomics_ws_cbs_merged", False):
                    _enf_tool_start = getattr(agent, "tool_start_callback", None)
                    _enf_tool_complete = getattr(agent, "tool_complete_callback", None)
                    def _merged_tool_start(tool_id, tool_name, args=None, _s=session):
                        _block = None
                        if _enf_tool_start:
                            try:
                                _block = _enf_tool_start(tool_id, tool_name, args)
                            except Exception:
                                pass
                        tool_start_cb(tool_id, tool_name, args)
                        return _block
                    def _merged_tool_complete(tool_id, tool_name, args=None, result=None, _s=session):
                        if _enf_tool_complete:
                            try:
                                _enf_tool_complete(tool_id, tool_name, args, result)
                            except Exception:
                                pass
                        tool_complete_cb(tool_id, tool_name, args, result)
                        # 2026-08-14: 自动锚定本轮新产物文件（会话锚点）
                        _auto_anchor_turn(_s, tool_name=tool_name, args=args)
                    agent.tool_start_callback = _merged_tool_start
                    agent.tool_complete_callback = _merged_tool_complete
                    agent._memomics_ws_cbs_merged = True
                agent.status_callback = status_cb
                agent.notice_callback = notice_cb
                agent.notice_clear_callback = notice_clear_cb
                agent.tool_gen_callback = tool_gen_cb
                agent.tool_progress_callback = tool_progress_cb

                # 问题4: 接通 clarify_callback — agent 提问时不中断进度，改为 waiting 状态
                def clarify_cb(question=None, _s=session, **kwargs):
                    try:
                        q_text = str(question) if question else "Please confirm"
                        # 进度不停，只改为 waiting 状态
                        _send_progress(_pt(_s, "waiting"), "waiting", q_text[:200])
                        _session_emit(_s, {"type": "clarify", "content": q_text[:500], "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _s["id"]})
                    except Exception:
                        pass
                agent.clarify_callback = clarify_cb

                # 问题4: 长任务心跳监控 — 每 30s 检查磁盘进度并汇报
                _heartbeat_active = {"on": True}
                _heartbeat_last_report = {"ts": 0}

                async def _heartbeat_loop(_s=session, _agent=agent):
                    while _heartbeat_active["on"]:
                        await asyncio.sleep(30)
                        try:
                            # 2026-08-14: 运行状态心跳 — 用户实时可见"还在跑/跑了多久/在干什么"
                            _turn_start = _s.get("_turn_start_ts") or time.time()
                            _live_tool = _s.get("_live_tool", "") or ""
                            _live_since = _s.get("_live_tool_ts") or 0
                            _stalled = bool(_live_tool) and (time.time() - _live_since) > 180
                            # 2026-08-16: 任务进程 CPU/内存监控（内核 worker/后台进程最新采样）
                            _proc = {}
                            try:
                                _h = _s.get("_proc_hist", [])
                                if _h and _h[-1][1]:
                                    _pid0, _cpu0, _io0, _rss0 = _h[-1][1][0]
                                    _proc = {"pid": _pid0, "cpu_s": round(_cpu0, 1),
                                             "rss_mb": round(_rss0 / 1048576.0, 0)}
                            except Exception:
                                pass
                            _session_emit(_s, {"type": "heartbeat",
                                "elapsed": int(time.time() - _turn_start),
                                "api_calls": int(_s.get("_api_calls", 0) or 0),
                                "turns": int(_s.get("_turn_count", 0) or 0),
                                "tool": _live_tool,
                                "stalled": _stalled,
                                "proc": _proc or None,
                                "ts": datetime.now().strftime("%H:%M:%S"),
                                "session_id": _s["id"]})
                            _results_dir = _s.get("results_dir", "")
                            _report_parts = []

                            # 1. 读取 task_plan.md 提取当前 Phase 状态
                            if _results_dir:
                                _plan_path = os.path.join(_results_dir, "task_plan.md")
                                if os.path.isfile(_plan_path):
                                    try:
                                        with open(_plan_path, "r", encoding="utf-8") as f:
                                            _plan_text = f.read()
                                        # 提取 Current Phase + 状态
                                        import re
                                        _phase_match = re.search(r"## Current Phase\n(.+?)(?:\n|$)", _plan_text)
                                        if _phase_match:
                                            _report_parts.append(f"📍 {_phase_match.group(1).strip()}")
                                        # 找 in_progress 的 Phase
                                        for _m in re.finditer(r"### (Phase \d+: .+?)\n(.*?)(?=\n###|\n##|\Z)", _plan_text, re.DOTALL):
                                            if "**Status:** in_progress" in _m.group(2):
                                                _checklist = [l.strip("- [ ] ").strip() for l in _m.group(2).split("\n") if l.strip().startswith("- [ ]")]
                                                _report_parts.append(f"⏳ {_m.group(1).strip()}")
                                                if _checklist:
                                                    _report_parts.append(f"   待完成: {', '.join(_checklist[:3])}")
                                                break
                                    except Exception:
                                        pass

                                # 2. 检查真正的分析产出目录
                                try:
                                    _recent_files = []
                                    _scan_dirs = []
                                    # 用户指定的分析目录（如 F:/CellBender_v2）
                                    _analysis_dir = _s.get("analysis_dir", "")
                                    if _analysis_dir and os.path.isdir(_analysis_dir):
                                        _scan_dirs.append(_analysis_dir)
                                        for _sub in ["cellbender_output", "output", "figures"]:
                                            _sd = os.path.join(_analysis_dir, _sub)
                                            if os.path.isdir(_sd):
                                                _scan_dirs.append(_sd)
                                    # MemOmics results 目录
                                    _res_sub = os.path.join(_results_dir, "results")
                                    if os.path.isdir(_res_sub):
                                        _scan_dirs.append(_res_sub)
                                    _scan_dirs = list(dict.fromkeys(_scan_dirs))
                                    for _scan_root in _scan_dirs:
                                        if not os.path.isdir(_scan_root):
                                            continue
                                        try:
                                            for _entry in os.listdir(_scan_root):
                                                _fp = os.path.join(_scan_root, _entry)
                                                if os.path.isfile(_fp):
                                                    _mtime = os.path.getmtime(_fp)
                                                    if _mtime > _heartbeat_last_report["ts"]:
                                                        _recent_files.append((_mtime, _entry))
                                        except Exception:
                                            pass
                                    _recent_files.sort(reverse=True)
                                    if _recent_files:
                                        _newest = _recent_files[:3]
                                        _report_parts.append(f"📄 新产出: {', '.join(f[1] for f in _newest)}")
                                        
                                        # 🔧 Layer3: 文件产出自动匹配待办
                                        if hasattr(_agent, "_todo_store"):
                                            try:
                                                _todos = list(_agent._todo_store.read())
                                                for _tf in _recent_files[:5]:
                                                    _fname = _tf[1].lower()
                                                    for _i, _td in enumerate(_todos):
                                                        _title = (_td.get("title") or _td.get("content") or "").lower()
                                                        # 模糊匹配：文件名关键词出现在待办标题中
                                                        _keywords = _fname.replace("_", " ").replace(".", " ").split()
                                                        if any(kw in _title for kw in _keywords if len(kw) > 2):
                                                            if _td.get("status") not in ("completed", "cancelled"):
                                                                _td["status"] = "completed"
                                                                _agent._todo_store._items[_i] = _td
                                                                logger.info(f"[Heartbeat] todo matched: {_td.get('title','')[:40]} -> completed (file: {_tf[1]})")
                                                                break
                                                # 推送更新
                                                _updated = [{"title": t.get("title", t.get("content", "")), "status": t.get("status", "pending")} 
                                                           for t in _agent._todo_store.read() if isinstance(t, dict)]
                                                _session_emit(_s, {"type": "todos_update", "todos": _updated, 
                                                    "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _s["id"]})
                                            except Exception:
                                                pass
                                except Exception:
                                    pass

                                # 🔧 Layer2.5: 读取 cron _agent 写入的 PROGRESS.md + alerts.json + .heartbeat_stop
                                # 路径优先级：analysis_dir > results_dir
                                try:
                                    _scan_dirs_for_progress = []
                                    _ad = _s.get("analysis_dir", "")
                                    _rd = _s.get("results_dir", "")
                                    if _ad and os.path.isdir(_ad):
                                        _scan_dirs_for_progress.append(_ad)
                                    if _rd and os.path.isdir(_rd) and _rd not in _scan_dirs_for_progress:
                                        _scan_dirs_for_progress.append(_rd)
                                    for _scan_dir in _scan_dirs_for_progress:
                                        # 检测 .heartbeat_stop 标记（cron _agent 自检完成）
                                        _stop_path = os.path.join(_scan_dir, ".heartbeat_stop")
                                        if os.path.isfile(_stop_path) and _marker_belongs_to_session(_stop_path, _s):
                                            _report_parts.append("🏁 cron: 任务完成，心跳已停止")
                                            _s["_urgent_wakeup"] = True
                                            # 一次性标记：处理完即删，防止每轮心跳重复唤醒
                                            try:
                                                os.remove(_stop_path)
                                            except Exception:
                                                pass
                                            break
                                        # 读 PROGRESS.md（cron _agent 写入的进度摘要）
                                        _progress_path = os.path.join(_scan_dir, "PROGRESS.md")
                                        if os.path.isfile(_progress_path) and _marker_belongs_to_session(_progress_path, _s):
                                            _pmtime = os.path.getmtime(_progress_path)
                                            if _pmtime > _heartbeat_last_report.get("progress_ts", 0):
                                                _heartbeat_last_report["progress_ts"] = _pmtime
                                                with open(_progress_path, "r", encoding="utf-8") as _pf:
                                                    _plines = _pf.read().strip().split("\n")
                                                _last_entry = ""
                                                for _l in reversed(_plines):
                                                    if _l.startswith("## "):
                                                        _last_entry = _l.strip("## ")
                                                        break
                                                if _last_entry:
                                                    _report_parts.append(f"📊 cron: {_last_entry}")
                                        # 读 alerts.json（cron _agent 写入的警报）
                                        _alerts_path = os.path.join(_scan_dir, "alerts.json")
                                        if os.path.isfile(_alerts_path) and _marker_belongs_to_session(_alerts_path, _s):
                                            _amtime = os.path.getmtime(_alerts_path)
                                            if _amtime > _heartbeat_last_report.get("alerts_ts", 0):
                                                _heartbeat_last_report["alerts_ts"] = _amtime
                                                import json as _json_alerts
                                                with open(_alerts_path, "r", encoding="utf-8") as _af:
                                                    _alerts_data = _json_alerts.load(_af)
                                                _unhandled_high = [a for a in _alerts_data if not a.get("handled") and a.get("urgency") == "HIGH"]
                                                if _unhandled_high:
                                                    _a = _unhandled_high[0]
                                                    _report_parts.append(f"🚨 cron告警: {_a.get('type','?')} — {_a.get('msg','?')[:80]}")
                                                    _s["_urgent_wakeup"] = True
                                                    break  # 找到 HIGH alert 就停，优先唤醒
                                except Exception:
                                    pass

                                # 🔧 紧急唤醒：检测错误/完成标记
                                try:
                                    _urgent = False
                                    for _entry in os.listdir(_results_dir) if _results_dir else []:
                                        _el = _entry.lower()
                                        # 错误标记：R错误、Python traceback、非零退出
                                        if any(kw in _el for kw in ["error", "fail", "traceback", "crash", ".err"]):
                                            _mtime = os.path.getmtime(os.path.join(_results_dir, _entry))
                                            if _mtime > time.time() - 120:  # 2分钟内的新错误
                                                _urgent = True
                                                _report_parts.append(f"🚨 检测到错误: {_entry}")
                                                break
                                    # 完成标记：大文件产出（聚类结果/报告等）
                                    if not _urgent:
                                        _todos = list(_agent._todo_store.read()) if hasattr(_agent, "_todo_store") else []
                                        _has_waiting = any(t.get("status") == "waiting_review" for t in _todos)
                                        if _has_waiting and _recent_files:
                                            _urgent = True
                                            _report_parts.append("🔔 待审阅任务，触发立即唤醒")
                                    if _urgent:
                                        _s["_urgent_wakeup"] = True
                                        _session_emit(_s, {"type": "notice", 
                                            "content": "🚨 检测到紧急事件，系统将立即唤醒 Agent 检查",
                                            "session_id": _s["id"]})
                                except Exception:
                                    pass

                            _heartbeat_last_report["ts"] = time.time()

                            if _report_parts:
                                _detail = " | ".join(_report_parts)
                                _send_progress(_pt(_s, "monitoring"), "pending",
                                               f"🕐 {datetime.now().strftime('%H:%M')} {_detail}")
                            else:
                                _send_progress(_pt(_s, "thinking"), "pending", _pt(_s, "running_task"))
                        except Exception:
                            pass
                _heartbeat_task = asyncio.ensure_future(_heartbeat_loop())

                # 统一事件流：Hermes event_callback 转发所有结构化事件到 WebSocket
                def event_cb(event_type, data, _s=session):
                    """Hermes event_callback(event_type, data) — 统一事件流"""
                    try:
                        _session_emit(_s, {"type": "event", "event_type": event_type, "data": data, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _s["id"]})
                    except Exception:
                        pass
                agent.event_callback = event_cb

                # 问题1: 环境检测关键词路由 — 用户说"检查环境/GPU/服务器"时自动注入真实检测结果
                _env_keywords = ["检查环境", "环境配置", "环境检测", "检测环境", "check env", "gpu", "显卡", "服务器配置", "系统配置", "电脑配置"]
                _env_ctx = None
                if any(kw in user_text.lower() for kw in _env_keywords):
                    try:
                        _env_result = await env_check()
                        import json as _json2
                        _env_summary = []
                        _lang = session.get("lang", "zh")
                        if _lang == "zh":
                            _env_summary.append(f"【环境检测结果】")
                            _env_summary.append(f"Python: {_env_result.get('python',{}).get('version','?')} ✓")
                            _r = _env_result.get("r", {})
                            _env_summary.append(f"R: {_r.get('version','未安装')} {'✓' if _r.get('ok') else '✗'}")
                            _gpu = _env_result.get("gpu", {})
                            if _gpu.get("ok"):
                                _env_summary.append(f"GPU: {_gpu.get('name','?')} ({_gpu.get('vram_mb',0)}MB) ✓")
                            else:
                                _env_summary.append(f"GPU: 未检测到 ✗ (debug: {_gpu.get('debug',{})})")
                            _sys = _env_result.get("system", {})
                            _env_summary.append(f"CPU核心: {_sys.get('cpu_cores','?')}, 内存: {_sys.get('memory_gb','?')}GB, 可用: {_sys.get('memory_available_gb','?')}GB")
                            _env_summary.append(f"磁盘可用: {_sys.get('disk_free_gb','?')}GB")
                            _env_summary.append(f"平台: {_sys.get('platform','?')}")
                        else:
                            _env_summary.append("[Environment Check]")
                            _env_summary.append(f"Python: {_env_result.get('python',{}).get('version','?')} OK")
                            _r = _env_result.get("r", {})
                            _env_summary.append(f"R: {_r.get('version','not installed')} {'OK' if _r.get('ok') else 'MISSING'}")
                            _gpu = _env_result.get("gpu", {})
                            if _gpu.get("ok"):
                                _env_summary.append(f"GPU: {_gpu.get('name','?')} ({_gpu.get('vram_mb',0)}MB) OK")
                            else:
                                _env_summary.append(f"GPU: NOT FOUND (debug: {_gpu.get('debug',{})})")
                            _sys = _env_result.get("system", {})
                            _env_summary.append(f"CPU cores: {_sys.get('cpu_cores','?')}, RAM: {_sys.get('memory_gb','?')}GB, available: {_sys.get('memory_available_gb','?')}GB")
                            _env_summary.append(f"Disk free: {_sys.get('disk_free_gb','?')}GB")
                            _env_summary.append(f"Platform: {_sys.get('platform','?')}")
                        _env_ctx = "\n".join(_env_summary)
                        # 推送进度
                        _send_progress(_pt(session, "tool_completed") + ": env_check", "done", _env_ctx[:200])
                    except Exception as _e:
                        _env_ctx = None

                # 问题11: 用户说"html"/"报告"时，自动检测是否有分析结果，有则注入 skill_view 上下文
                _html_ctx = None
                _html_keywords = ["html", "报告", "report", "做报告", "生成报告", "分析报告", "总结报告", "生成html", "html报告"]
                _html_triggered = any(kw in user_text.lower() for kw in _html_keywords)
                if _html_triggered:
                    # 检查是否有分析结果：1) results_dir 已重命名 2) tool_calls_log 有分析工具调用
                    _has_analysis = False
                    _results_dir = session.get("results_dir", "")
                    # 检查1: results_dir 不是默认的 memomics-xxx 格式
                    _sid = session.get("id", "")
                    if _results_dir and not _results_dir.endswith(_sid):
                        _has_analysis = True
                    # 检查2: tool_calls_log 有分析工具
                    if not _has_analysis:
                        try:
                            db = _get_session_db()
                            if db and hasattr(db, "conn"):
                                _rows = db.conn.execute(
                                    "SELECT COUNT(*) FROM tool_calls_log WHERE session_id=? AND tool_name IN ('scan_data','execute_r','execute_python','terminal','add_figure','debate_analysis','generate_report','rail_review','skill_view','env_check','module_selector')",
                                    (_sid,)
                                ).fetchone()
                                if _rows and _rows[0] > 0:
                                    _has_analysis = True
                        except Exception:
                            pass
                    if _has_analysis:
                        _html_ctx = (
                            "【系统指令：报告生成】\n"
                            "用户要求生成 HTML 报告。当前会话已包含分析结果。\n"
                            "你必须使用 bioinformatics-html-report skill 来生成专业报告，不要用 generate_report 工具简单包装。\n"
                            "步骤：\n"
                            "1. 调用 skill_view('bioinformatics-html-report') 加载完整指令\n"
                            "2. 使用 html_report_builder.py 的 ReportBuilder + auto_fill_from_logs() 自动收集日志和图表\n"
                            "3. 报告保存到桌面，包含所有分析图表、辩论记录、参数来源、日志溯源\n"
                            "4. 报告使用的语言必须与用户交互语言一致\n"
                            "不要偷懒用 generate_report 工具传入手工 HTML——那样会丢失图表、辩论和日志溯源。"
                        )
                        _send_progress("📄 报告生成", "pending", "检测到分析结果，自动触发 HTML 报告生成...")

                # 是否后台运行
                is_bg = msg.get("background", False)

                async def run_agent(_intent=_intent, _skill_ctx=_skill_ctx, _env_ctx=_env_ctx, _html_ctx=_html_ctx, _session=session, _agent=agent):
                    """在 executor 中运行 _agent — 用 run_conversation + conversation_history"""
                    try:
                        # 惰性加载兜底：确保上下文构建器（task_plan/resume 等）能读到完整历史
                        _ensure_session_messages_loaded(_session)
                        # 从 state.db 加载 conversation_history（排除当前消息，run_conversation 会加）
                        conversation_history = []
                        db = _get_session_db()
                        if db:
                            try:
                                all_msgs = db.get_messages_as_conversation(_session["id"])
                                # 排除最后一条（当前用户消息，run_conversation 会自动加）
                                history = all_msgs[:-1] if all_msgs else []
                                # 只保留 user/assistant 消息，且 content 强制为 string
                                # （tool 消息的 content 可能是 dict/int，会导致 API 400）
                                for m in history:
                                    role = m.get("role", "")
                                    if role not in ("user", "assistant"):
                                        continue
                                    content = m.get("content", "")
                                    if not isinstance(content, str):
                                        if isinstance(content, (dict, list)):
                                            import json as _json
                                            content = _json.dumps(content, ensure_ascii=False)
                                        else:
                                            content = str(content)
                                    if not content.strip():
                                        continue
                                    conversation_history.append({"role": role, "content": content})
                            except Exception:
                                pass

                        # ── (b) 上下文卫生：历史里累积的"记忆/锚点/唤醒"脚手架去重折叠 ──
                        # 旧版把 _inject_anchors 拼进用户消息并被持久化，导致历史堆满重复的
                        # [相关历史记忆]/[会话锚点] 脚手架(实测 220K 上下文 94% 为缓存命中的
                        # 重复系统段)。这里：纯脚手架丢弃、带脚手架的旧用户消息剥离脚手架只留
                        # 真实文本、本轮记忆/锚点以有且仅一条 system 消息注入。
                        try:
                            _filtered = []
                            for _m in conversation_history:
                                _c = _m.get("content")
                                if not isinstance(_c, str):
                                    _filtered.append(_m)
                                    continue
                                if _c.lstrip().startswith(("[会话要求", "[相关历史记忆", "[会话锚点", "[系统唤醒", "📊 LoopX 状态", "[System:", "[数据读取配方")):
                                    _rest = _strip_scaffold_text(_c)
                                    if _rest is None:
                                        continue
                                    _m2 = dict(_m)
                                    _m2["content"] = _rest
                                    _filtered.append(_m2)
                                    continue
                                _filtered.append(_m)
                            conversation_history = _filtered
                            # ── (b2 2026-08-29) 历史去重：空 assistant 丢弃 + 相邻完全重复消息折叠 ──
                            # 实证：memomics-cd677556 3449 条 user/assistant 历史，含 99 条重复 user
                            # 消息、757 处同角色连排 → 模型被旧问答淹没，回答上一个问题/重复重跑。
                            _dedupe = []
                            _prev_key = None
                            for _m in conversation_history:
                                _c = _m.get("content") if isinstance(_m, dict) else None
                                if not isinstance(_c, str):
                                    _dedupe.append(_m)
                                    _prev_key = None
                                    continue
                                if not _c.strip() and _m.get("role") == "assistant":
                                    continue
                                _key = (_m.get("role"), _c.strip())
                                if _key == _prev_key:
                                    continue
                                _dedupe.append(_m)
                                _prev_key = _key
                            conversation_history = _dedupe
                            _mem_digest = _build_memory_digest(_session, user_text or "")
                            if _mem_digest:
                                conversation_history = [m for m in conversation_history
                                    if not (isinstance(m.get("content"), str)
                                            and m["content"].startswith(("[相关历史记忆", "[会话锚点")))]
                                conversation_history.append({"role": "system", "content": _mem_digest})
                        except Exception as _b_err:
                            logger.warning(f"[MemOmics] (b) 上下文卫生失败(不阻断): {_b_err}")

                        # ── (c0 2026-08-29) 超预算早折叠：把死代码 _maybe_rollup_history 接上 ──
                        # 之前 1M 窗口模型让 317K token 历史一直不折叠，老问答紧邻新问题 →
                        # “回答上一个问题”/忘记已跑结果。现在 >60K token 就折叠头部为结构化摘要。
                        try:
                            _pre_roll = conversation_history
                            conversation_history = _maybe_rollup_history(_session, conversation_history)
                            _rolled = conversation_history is not _pre_roll
                        except Exception as _c0_err:
                            _rolled = False
                            logger.warning(f"[MemOmics] (c0) 历史早折叠失败(不阻断): {_c0_err}")

                        # ── (c/P1-P5) MiMo-Code 上下文架构：单一边界 usable() + 后台 writer(§1-§11) +
                        #      四层记忆(FTS/REQUIREMENTS/MEMORY/History) + 分段重建预算 + 增量压缩 ──
                        # 2026-08-31 折叠分工：c0 已折叠 → skip_rebuild=True（防摘要套摘要）；
                        # c0 未折叠且触发（30K+/自检唤醒）→ 才走 P1-P5 重建。
                        try:
                            _wcfg = _session.get("model_config") or _current_model
                            conversation_history = context_arch.memomics_replay(
                                _session, conversation_history,
                                llm_fn=lambda p, _c=_wcfg: _checkpoint_writer_llm(p, cfg=_c),
                                skip_rebuild=_rolled)
                        except Exception as _c_err:
                            logger.warning(f"[MemOmics] (c) P1-P5 架构回放失败(不阻断): {_c_err}")

                        # 🔧 每轮开头：检查上一轮是否有未完成的后台进程
                        _bg_check = _build_background_process_check(_session, _agent)
                        if _bg_check:
                            conversation_history.insert(0, {"role": "system", "content": _bg_check})

                        # 问题1: 如果检测到环境关键词，把真实检测结果作为 system context 注入
                        if _env_ctx:
                            conversation_history.append({"role": "system", "content": _env_ctx})

                        # 问题11: HTML报告关键词自动触发 skill_view
                        if _html_ctx:
                            conversation_history.append({"role": "system", "content": _html_ctx})

                        # 图路由：根据意图+领域注入技能触发指令（P1+P2+P3）
                        if _skill_ctx:
                            conversation_history.append({"role": "system", "content": _skill_ctx})

                        # 🔧 KB 预查询/领域引导 → 尾部 system 消息（2026-08-21 缓存优化：
                        # 放前缀会破坏 DeepSeek 前缀缓存，放尾部只影响最新请求段）
                        try:
                            _kb_tail = _build_kb_tail_injection(user_text or "", _intent, _is_heavy)
                            if _kb_tail:
                                conversation_history.append({"role": "system", "content": _kb_tail})
                        except Exception:
                            pass

                        # P3(2026-09-22): 确认弹窗的结构化答复 → 确定性上下文（只注入一次）
                        try:
                            _form_ctx = _build_ask_form_context(_session, user_text or "")
                            if _form_ctx:
                                conversation_history.append({"role": "system", "content": _form_ctx})
                        except Exception:
                            pass

                        # 2026-08-25: 开工前澄清（grill）——执行意图 + 关键信息缺失 → 先问清楚
                        # P3(2026-09-22): grill 没触发时，高代价任务再补一层"意图确认"
                        # （数据有了但要做成什么没交代）——并预置门禁：用户勾选前不许执行。
                        # P4(2026-09-22): 代码修改模式优先 —— 用户给脚本让"改一下"时只改不跑；
                        # 记忆里正好有他的数据 → **服务器自己**弹窗问"要不要用数据验证"。
                        _ce_mode, _ce_data = "", []
                        try:
                            _ce_mode = _code_edit_mode(user_text or "")
                            _is_form_ans = _is_form_answer_text(user_text or "", _session)
                            from webui import enforcement as _enf_ce
                            _es_ce = _enf_ce.get_enforcement(_session.get("id", ""))
                            if _ce_mode == "edit":
                                _ce_data = _find_memory_data(_session, user_text or "")
                                _enf_ce.arm_code_edit(
                                    _es_ce, "用户要求改代码、没说要跑：%s" % (user_text or "")[:60],
                                    data=_ce_data)
                                if _ce_data and not _session.get("_code_edit_asked"):
                                    _fid_ce, _ok_ce = _emit_code_edit_form(_session, _ce_data)
                                    _session["_code_edit_asked"] = bool(_ok_ce)
                                    if _ok_ce:
                                        logger.info("[code_edit] session %s: 已弹窗问验证（%d 条数据）",
                                                    str(_session.get("id", ""))[:12], len(_ce_data))
                            elif _ce_mode != "verify" and not _is_form_ans \
                                    and _enf_ce.code_edit_pending(_es_ce):
                                # 锁还开着，但用户这轮说的是别的（不是弹窗答复）→ 语境变了，解锁
                                _enf_ce.clear_code_edit(_es_ce)
                                logger.info("[code_edit] 用户新消息 → 解锁代码修改模式")
                        except Exception as _e_ce0:
                            logger.warning("[code_edit] 预置失败: %s", _e_ce0)
                        if _ce_mode:
                            try:
                                conversation_history.append({
                                    "role": "system",
                                    "content": _build_code_edit_prompt(_session, user_text or "",
                                                                       _ce_mode, _ce_data)})
                                logger.info("[code_edit] session %s mode=%s data=%d asked=%s",
                                            str(_session.get("id", ""))[:12], _ce_mode, len(_ce_data),
                                            bool(_session.get("_code_edit_asked")))
                            except Exception as _e_ce1:
                                logger.warning("[code_edit] 指令注入失败: %s", _e_ce1)
                        else:
                            # P4: 上一轮锁着"只改代码"、这轮用户说了别的（非弹窗答复）→ 解锁
                            try:
                                from webui import enforcement as _enf_ce2
                                _es_ce2 = _enf_ce2.get_enforcement(_session.get("id", ""))
                                if _enf_ce2.code_edit_pending(_es_ce2) and not \
                                        _is_form_answer_text(user_text or "", _session):
                                    _enf_ce2.clear_code_edit(_es_ce2)
                                    logger.info("[code_edit] 用户新消息 → 解锁代码修改模式")
                            except Exception:
                                pass
                            try:
                                _grill = _build_grill_prompt(_session, user_text or "", _intent)
                                if _grill:
                                    conversation_history.append({"role": "system", "content": _grill})
                                else:
                                    _iconf = _build_intent_confirm_prompt(_session, user_text or "", _intent)
                                    if _iconf:
                                        conversation_history.append({"role": "system", "content": _iconf})
                                        try:
                                            from webui import enforcement as _enf_ic
                                            _es_ic = _enf_ic.get_enforcement(_session.get("id", ""))
                                            _enf_ic.arm_intent_confirm(
                                                _es_ic, "高代价任务（分析/投递/入库/报告）开工前意图未确认")
                                            logger.info("[intent_confirm] session %s: 已预置门禁，等用户勾选",
                                                        str(_session.get("id", ""))[:12])
                                        except Exception as _e_ic:
                                            logger.warning("[intent_confirm] arm failed: %s", _e_ic)
                            except Exception:
                                pass

                        # 2026-08-16 修复「问下一个问题被旧上下文占据」：
                        # 用户消息带新数据路径且不是"继续/接着"→ 视为新任务，
                        # 跳过 task_plan 恢复 + 主线续跑注入，先干净回答新问题。
                        _new_data_task = False
                        if user_text:
                            try:
                                _new_paths = re.findall(r'[A-Za-z]:[/\\]\S+', user_text)
                                _is_continue = any(w in user_text for w in
                                    ("继续", "接着", "下一步", "然后", "继续跑", "接着跑", "继续做", "接着做"))
                                _new_data_task = bool(_new_paths) and not _is_continue
                            except Exception:
                                _new_data_task = False

                        # 🔧 长任务记忆锚点 + 任务状态指令（合并为一条，避免被稀释）
                        # 2026-08-25: 从"强制推进"改为"状态通报"——用户请求优先（_EXECUTION_POLICY）
                        _plan_ctx = _build_task_plan_context(_session) if not _new_data_task else None
                        if _plan_ctx:
                            # 把所有关键指令合并成一条 system 消息
                            _merged = (
                                _plan_ctx + "\n\n"
                                "## 任务状态指令（用户请求优先）\n"
                                "你当前有 task_plan.md，存在进行中的分析任务。请遵守：\n"
                                "1. 用户当前消息是最高优先级：用户问什么就答什么，用户要调查就只调查。\n"
                                "2. 仅当用户明确要求执行/继续任务时，才按 task_plan 推进（工具调用优先）。\n"
                                "3. 用户是问答/调查/规划类请求时，不要擅自执行任务、不要擅自修复后重跑。\n"
                                "4. 用户没有说'继续'时，任务推进交给系统自动续跑，不在本回合推进。\n"
                                "5. 若用户明确要求执行且 Phase 描述模糊，可补充具体步骤执行；不确定时用 ask_user 确认。\n"
                                "6. 任何脚本/分析在重新执行前，必须先用 search_files/read_file 检查 results 目录下对应产物是否已存在且非空；已存在 → 直接复用并汇报，禁止重跑（铁律13）。\n"
                                "7. 需要用户确认（是否/要不要/需要吗/可以吗）时，必须调用 ask_user 工具（带选项）提问，禁止在正文结尾用问句——正文问句的答复无法与问题绑定，用户答‘需要’会丢失所指。"
                            )
                            conversation_history.append({"role": "system", "content": _merged})

                        # P0-1: Agent 启动协议 — 每轮自动读 alerts.json
                        _alerts_ctx = _build_alerts_context(_session)
                        if _alerts_ctx:
                            conversation_history.append({"role": "system", "content": _alerts_ctx})

                        # 🔧 主线任务恢复：回答完用户问题后必须继续主线
                        _resume_ctx = _build_task_resume_prompt(_session) if not _new_data_task else None
                        if _resume_ctx:
                            conversation_history.append({"role": "system", "content": _resume_ctx})

                        # plan_refine 模式：临时屏蔽 todo/todo_manage 工具，强制走 memomics_pipeline
                        _saved_tools = None
                        if _intent == "plan_refine" and _agent.tools:
                            _saved_tools = _agent.tools
                                                        # DEBUG: 打印所有可用工具
                            all_tool_names = sorted([t.get('function',{}).get('name','') for t in _agent.tools]) if _agent.tools else []
                            logger.info(f"[ALL-TOOLS] ({len(all_tool_names)}): {all_tool_names}")
                            # 白名单：plan_refine 只允许规划+文献+方案工具
                            
                            PLAN_ONLY = ("memomics_pipeline", "skill_view", "skill_search", "search_knowledge", "search_papers", "search_papers_by_context", "web_search", "web_extract")
                            _agent.tools = [t for t in _agent.tools if t.get("function", {}).get("name", "") in PLAN_ONLY]
                            before = sorted([t.get('function',{}).get('name','') for t in _agent.tools]) if _agent.tools else []
                            logger.info(f"[DEBUG-ALL-TOOLS] ({len(before)}): {before}")

                        # ── 2026-08-31 L0/L1 结论注册表注入（关键结论/修复/决策，勿重跑） ──
                        try:
                            from conclusion_store import build_memory_budget_context
                            _l1_ctx = build_memory_budget_context(_session, user_text or "", limit=20, max_chars=4000)
                            if _l1_ctx:
                                conversation_history.append({"role": "system", "content": _l1_ctx})
                        except Exception:
                            pass

                        # ── 2026-08-31 待确认问题追踪：用户“需要”必须绑定上一轮问话 ──
                        try:
                            _pend_ctx = _build_pending_question_context(_session, user_text or "")
                            if _pend_ctx:
                                conversation_history.append({"role": "system", "content": _pend_ctx})
                        except Exception:
                            pass

                        # ── 2026-08-31 最近 N 轮速览注入（L2）：结论/已解决问题不再忘 ──
                        try:
                            _recent_digest = _build_recent_turns_digest(_session, max_turns=8)
                            if _recent_digest:
                                conversation_history.append({"role": "system", "content": _recent_digest})
                        except Exception:
                            pass

                        # ── 2026-08-29 注意力聚焦：最新用户消息前放“本轮唯一任务”转向标记 ──
                        # 实证：历史里紧邻的旧问答会把模型注意力吸走 → 回答上一个问题。
                        # 把用户本轮消息摘抄到 system 尾部，明确“只回答这一条、以本轮为准”。
                        try:
                            _focus_text = (user_text or "").strip()
                            if _focus_text:
                                _turn_focus = (
                                    "【本轮唯一任务 — 最高优先级】下面是用户刚刚发送的消息，"
                                    "请只回答这一条，不要延续或重复你上一轮的输出；"
                                    "历史对话仅供背景，若与历史相似，以本轮用户消息为准。\n"
                                    f"用户本轮消息：{_focus_text[:800]}"
                                )
                                conversation_history.append({"role": "system", "content": _turn_focus})
                        except Exception:
                            pass

                        # 2026-08-14: 本轮回合运行基线（心跳计时起点）
                        _session["_turn_start_ts"] = time.time()
                        _session["_live_tool"] = ""
                        _session["_live_tool_ts"] = time.time()
                        
                        def _do_run():
                            # P1-13(2026-08-13): executor 线程内设置会话上下文 —
                            # threading.local 不跨线程，须在工具执行线程内设定，
                            # execute_r/execute_python 才能识别会话并隔离 kernel。
                            try:
                                from memomics.bio_tools.debate_analysis import set_session_context
                                _set_debate_session_context(_session)
                            except Exception:
                                pass
                            result = _agent.run_conversation(
                                _run_text,
                                conversation_history=conversation_history if conversation_history else None,
                                task_id=_session["id"],
                            )
                            return result.get("final_response") or "" if isinstance(result, dict) else str(result)

                        # research_plan 模式超时保护（CNS级方案 8 分钟）
                        if _intent == "research_plan":
                            try:
                                result = await asyncio.wait_for(
                                    loop.run_in_executor(None, _do_run),
                                    timeout=480
                                )
                            except asyncio.TimeoutError:
                                result = _agent.checkpoint.read_partial() if hasattr(_agent, "checkpoint") else ""
                                if not result:
                                    result = "研究方案生成超时。CNS 级方案涉及大量文献调研，请回复 **继续** 让我完成。"
                                _session_emit(_session, {"type": "timeout", "content": "research_plan超时(8分钟)", "session_id": _session["id"]})
                        else:
                            # 2026-08-27 用户要求：去除 15 分钟绝对超时保护（长任务会被误杀）。
                            # 不再设置 turn 级绝对上限；服务端仍保留 5 分钟无输出 stall watchdog 兜底。
                            result = await loop.run_in_executor(None, _do_run)

                        # ── 2026-08-31 L0 结论注册表：本轮结论/修复/失败/决策自动沉淀 + L3 归档索引 ──
                        try:
                            from conclusion_store import extract_turn_conclusions, append_conclusions, archive_turn, link_archive
                            _l0 = extract_turn_conclusions(user_text or "", str(result or ""))
                            if _l0:
                                _ids = append_conclusions(_session, _l0)
                                if _ids:
                                    _arc = archive_turn(_session, user_text or "", str(result or ""))
                                    if _arc:
                                        link_archive(_session, _ids, _arc)
                                    logger.info(f"[MemOmics] L0 conclusions +{len(_ids)} ids={_ids} (session {_session['id'][:12]})")
                        except Exception as _l0_err:
                            logger.warning(f"[MemOmics] L0 conclusions store failed(不阻断): {_l0_err}")

                        # ⚡ Bug 3: 工具调用事后验证 — intent需要工具但agent没调则追加警告
                        if _intent in ("research_plan", "plan_refine") and result and len(result.strip()) > 50:
                            # 检查是否调过核心工具
                            _tool_list = _tool_call_log
                            _all_tool_names = [t.get("tool", "") for t in _tool_list]
                            _core_tools = {"memomics_pipeline", "skill_search", "search_knowledge", "search_papers", "literature_search"}
                            _called_core = _core_tools & set(_all_tool_names)
                            if not _called_core:
                                _warning = (
                                    "\n\n【⚠️ 系统检测：以上回复未调用任何搜索/方案工具】\n"
                                    "本回复可能缺乏真实文献和数据支持。\n"
                                    "请回复 **'请用文献搜索工具重新生成方案，附 PMID/DOI'** 触发完整流程。"
                                )
                                result += _warning
                                logger.warning(f"[TOOL-VALIDATION] {_intent}: 0 core tools called, warning appended")

                        # B5: post-hoc quality validation (internal — NOT shown to user)
                        if _intent in ("research_plan", "plan_refine") and result:
                            quality_warnings = []
                            has_pmid = "PMID" in result or "DOI:" in result or "doi:" in result.lower()
                            if not has_pmid:
                                quality_warnings.append("[LIT] literature refs missing (no PMID/DOI)")
                            has_conc = any(k in result.lower() for k in ["conclusion", "validation", "experiment", "follow-up"])
                            if not has_conc:
                                quality_warnings.append("[INTERP] no conclusion or validation section")
                            unique_tools = set(t.get("tool", "") for t in _tool_call_log)
                            if len(unique_tools) < 2 and _intent not in ("chat", "self_intro"):
                                quality_warnings.append("[TOOLS] only " + str(len(unique_tools)) + " tool types called")
                            if quality_warnings:
                                logger.warning(f"[QUALITY] {_intent}: {len(quality_warnings)} warnings: {quality_warnings}")
                                # 只记日志，不附加到用户可见输出

                        # 恢复原始工具列表
                        if _saved_tools is not None:
                            _agent.tools = _saved_tools
                        # 兜底：plan_refine 结束后若未调用 memomics_pipeline，自动触发生成待办
# 兜底：plan_refine 结束后若未调用 memomics_pipeline，直接调用 Python 函数生成待办
                        if _intent == "plan_refine":
                            did_call = any(t for t in _tool_call_log if t.get("tool") == "memomics_pipeline")
                            if not did_call:
                                try:
                                    import sys
                                    from memomics.memomics_pipeline import modules_to_todos
                                    default_ids = ["02", "03", "04"]
                                    pipe_todos = modules_to_todos(default_ids)
                                    if pipe_todos:
                                        for td in pipe_todos:
                                            _agent._todo_store.add({"title": td.get("title", td.get("name", "")), "module": td.get("module", ""), "skill": td.get("skill", ""), "status": "pending", "description": td.get("description", "")})
                                        _session_emit(_session, {"type": "todos_update", "todos": pipe_todos, "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _session["id"]})
                                        _session_emit(_session, {"type": "progress", "step": "auto_todos", "status": "done", "detail": f"自动生成{len(pipe_todos)}个待办", "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _session["id"]})
                                except Exception as e:
                                    logger.warning(f"auto-todos failed: {e}")
                        # Hermes 中断是优雅的：run_conversation() 正常返回
                        if getattr(_agent, "_interrupt_requested", False):
                            _agent.clear_interrupt()
                            _session_emit(_session, {"type": "progress", "step": _pt(_session, "stopped"), "status": "done", "detail": _pt(_session, "user_stopped"), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _session["id"]})
                            _session_emit(_session, {"type": "cancelled", "session_id": _session["id"]})
                            return
                        # 记录助手回复到 _session（state.db 由 Hermes 框架 _persist_session 自动写）
                        _session["messages"].append({"role": "assistant", "content": result, "time": datetime.now().strftime("%H:%M:%S")})
                        _session["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        # 尝试提取 todo
                        # P1-1 修正：原代码调 _agent.get_todos()，该方法在 Hermes 全仓 grep
                        # 0 命中（根本不存在）→ 这个分支恒为 []，等于每轮结束什么都没同步。
                        # 真源是 _todo_store.read()；四个推送点的回写统一走 _session_emit
                        # 收口，这里只在 store 非空时补齐一次（store 空时不清空已有待办）。
                        try:
                            _tstore = getattr(_agent, "_todo_store", None)
                            _cur_todos = [t for t in _tstore.read() if isinstance(t, dict)] if _tstore is not None else []
                            if _cur_todos:
                                _sync_session_todos(_session, _cur_todos)
                        except Exception:
                            pass
                        # 回合结束：循环检测（重复表述）
                        _loop_check(_session, None, "turn_end")

                        # 发送进度完成
                        _session_emit(_session, {"type": "progress", "step": _pt(_session, "complete"), "status": "done", "detail": _pt(_session, "reply_generated"), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _session["id"]})
                        # 聊天框内容：有文本回复就用文本，纯工具调用时生成操作摘要
                        if has_delta:
                            _chat_content = ""  # 已通过 delta 流式发送，不重复
                        elif result and result.strip():
                            _chat_content = result
                        elif _tool_call_log:
                            _tools_done = [t["tool"] for t in _tool_call_log]
                            _unique = list(dict.fromkeys(_tools_done))
                            _chat_content = "✅ 已完成: " + " → ".join(_unique[:6])
                        else:
                            _chat_content = ""
                        _session_emit(_session, {"type": "complete", "content": _chat_content, "session_id": _session["id"]})

                        # 代码级反"说而不做"：检测到行动承诺但未执行 → 自动补发执行指令
                        # 2026-08-14 v3 三重 AND 判定 → 2026-08-16 v4 提取为 _detect_action_promise
                        # （扩充词表 + Tier B 编号计划承诺，修复 memomics-2274ab75 "先并行扫描"漏检）
                        _has_action_promise = _detect_action_promise(result, _tool_call_log)
                        _has_plan = bool(_session.get("plan_path") or
                                         os.path.isfile(os.path.join(_session.get("results_dir", ""), "task_plan.md")))
                        # 每用户回合最多紧急唤醒 2 次，防"做完了又不停"
                        _wake_n = _session.get("_saying_wakeup_n", 0)
                        if _has_action_promise and _wake_n < 2:
                            _session["_saying_wakeup_n"] = _wake_n + 1
                            logger.info(f"[MemOmics] 检测到说而不做: action_promise=True → 立即触发自唤醒 (#{_wake_n + 1}/2)")
                            _session_emit(_session, {"type": "info",
                                "content": "⚠️ 检测到说而不做——系统将立即触发新一轮检查，强制调用工具",
                                "session_id": _session["id"]})
                            _session["_urgent_wakeup"] = True
                            _session["_force_tool_check"] = True
                        # 2026-08-16 修复 memomics-2274ab75:模型宣称"已生成/已修改",
                        # 但本回合所有执行调用都被执行保护拦截、磁盘文件无变化 →
                        # 强制自检纠正,杜绝"看着旧文件假装跑完"
                        _claim_done_words = ("已生成", "已重新生成", "已修改", "已保存",
                                             "已更新", "已重跑", "已出图", "已执行")
                        if any(_w in (result or "") for _w in _claim_done_words) \
                                and not _session.get("_real_exec_this_turn") \
                                and not _results_dir_changed_since(_session, _session.get("_turn_start_ts") or 0):
                            _wake_n2 = _session.get("_saying_wakeup_n", 0)
                            if _wake_n2 < 2:
                                _session["_saying_wakeup_n"] = _wake_n2 + 1
                                _session["_urgent_wakeup"] = True
                                _session["_force_tool_check"] = True
                                _session.setdefault("messages", []).append(
                                    {"role": "system",
                                     "content": "⚠️ 你刚才回复称已生成/已修改文件，但系统检查发现本回合没有任何代码真正执行、磁盘文件也没有任何变化。请立即调用工具实际重新执行，并核对文件修改时间后再回复，不要谎报完成。",
                                     "time": datetime.now().strftime("%H:%M:%S"),
                                     "source": "fake_done_check"})
                                _session_emit(_session, {"type": "info",
                                    "content": "⚠️ 检测到虚假完成声明（本回合无真实执行、文件未变化）——系统将强制重新执行",
                                    "session_id": _session["id"]})
                                logger.info("[MemOmics] 检测到虚假完成声明 → 强制自检重跑")
                        # 2026-08-22 产物终检（一次性，回合末）：本回合有真实执行 + 模型声称完成 →
                        # 检查结果目录是否有新产物且非空（存在+大小>0），不满足则提醒模型核实交付。
                        # 设计：不每次执行都查（省 token），只在回合交付前查一次；内容对错靠执行时
                        # rail_review 保证，这里只兜底"声称完成但产物缺失/空文件"。
                        _claim_prod_words = ("完成", "已生成", "已保存", "已复制", "已写入",
                                             "已交付", "已导出", "已输出", "已合并", "已创建",
                                             "已写好", "已出", "产物", "结果如下", "文件已")
                        _real_exec_this_turn = _session.get("_real_exec_this_turn") or bool(_tool_call_log)
                        if _real_exec_this_turn and any(_w in (result or "") for _w in _claim_prod_words):
                            try:
                                # 用户目标路径产物可能不在 results_dir，一并检查
                                _extra_dirs = []
                                for _p in re.findall(r'[A-Za-z]:[\\/][^\s"\'，。；：、]*', _run_text or ""):
                                    _dir_c = _p if os.path.isdir(_p) else os.path.dirname(_p)
                                    if _dir_c and os.path.isdir(_dir_c):
                                        _extra_dirs.append(_dir_c)
                                _prod_ok = _results_dir_changed_since(_session, _session.get("_turn_start_ts") or 0,
                                                                      extra_dirs=_extra_dirs)
                            except Exception:
                                _prod_ok = True
                            if not _prod_ok:
                                _wake_n3 = _session.get("_saying_wakeup_n", 0)
                                if _wake_n3 < 2:
                                    _session["_saying_wakeup_n"] = _wake_n3 + 1
                                    _session["_urgent_wakeup"] = True
                                    _session["_force_tool_check"] = True
                                    _session.setdefault("messages", []).append(
                                        {"role": "system",
                                         "content": "⚠️ 你回复称已完成，但系统检查发现本回合执行后结果目录没有任何新产物（文件不存在或为空）。请先核实目标产物是否真的写出：检查文件存在、大小非空、内容正确；缺失则重新执行并验证后再交付。",
                                         "time": datetime.now().strftime("%H:%M:%S"),
                                         "source": "prod_check"})
                                    _session_emit(_session, {"type": "info",
                                        "content": "⚠️ 回合终检：声称完成但结果目录无新产物——已提醒模型核实",
                                        "session_id": _session["id"]})
                                    logger.info("[MemOmics] 产物终检未过（声称完成但无新产物）→ 提醒核实")
                        # 🔧 空响应检测：只有模型真正返回空（无任何文本且无工具调用）才重试。
                        # 注意：短回复（如用户要求"只回复两个字"）是合法回复，不能按空处理
                        if not _tool_call_log and (not result or not result.strip()):
                            logger.info(f"[MemOmics] 检测到空响应(len={len(result.strip()) if result else 0}) → 触发自唤醒重试")
                            _session_emit(_session, {"type": "info",
                                "content": "⚠️ 模型返回空响应，系统将在3秒后自动重试",
                                "session_id": _session["id"]})
                            _session["_urgent_wakeup"] = True
                    except asyncio.CancelledError:
                        if not getattr(_agent, "_interrupt_requested", False):
                            _agent.interrupt()
                        _session_emit(_session, {"type": "progress", "step": _pt(_session, "stopped"), "status": "done", "detail": _pt(_session, "user_stopped"), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _session["id"]})
                        _session_emit(_session, {"type": "cancelled", "session_id": _session["id"]})
                    except Exception as e:
                        import traceback
                        _session_emit(_session, {"type": "error", "content": f"Agent 执行出错: {e}\n{traceback.format_exc()[-500:]}", "session_id": _session["id"]})
                    finally:
                        _session["running_agent"] = None
                        _session["running_task"] = None
                        _session["_user_turn_active"] = False  # 并发护栏: 用户回合结束清除
                        if _thread_state is not None:
                            _thread_state.mark_turn_end(_session["id"])
                        # 技能索引自愈（2026-09-24）：agent 会话中途用 write 直接造出来的技能目录不在
                        # 启动 scan 范围内，不补就永远不进 SKILLS_INDEX.md（模型唯一能看到的技能清单）。
                        # 廉价判定（列目录 + 读索引），真缺行才整表重建；失败绝不影响回合收尾。
                        try:
                            _sync_info = auto_register.sync_new_skills()
                            if _sync_info.get("rebuilt") or _sync_info.get("json_generated"):
                                logger.info(
                                    "[MemOmics] 技能索引自愈：补 %d 行 / 补 %d 个 skill.json"\
                                    % (len(_sync_info.get("missing") or []), len(_sync_info.get("json_generated") or [])))
                        except Exception as _e_sync:
                            logger.info(f"[MemOmics] skill index sync skipped: {_e_sync}")
                        # LoopX 执行层：用户回合交付记录（cadence 数据源）
                        try:
                            from memomics.loopx_bridge import LoopXBridge
                            _rd3 = _session.get("results_dir", "") or ""
                            if _rd3:
                                _final3 = locals().get("result", "") or ""
                                LoopXBridge(_session["id"], _rd3, user_online=True).record_turn_delivery(
                                    outcome="primary_goal_outcome" if _final3 and "完成" in str(_final3) else "outcome_progress",
                                    summary=str(_final3)[:150],
                                    model=(_session.get("model_config") or {}).get("model", ""),
                                )
                        except Exception:
                            pass
                        # ── token 消耗持久化（2026-08-07）：用户回合追加写入 token_usage.jsonl ──
                        try:
                            _persist_token_usage(_session, turn_kind="user")
                        except Exception:
                            pass
                        # 停止本轮心跳
                        _heartbeat_active["on"] = False
                        if '_heartbeat_task' in dir() and _heartbeat_task and not _heartbeat_task.done():
                            _heartbeat_task.cancel()
                        # 🔧 自唤醒：如果有未完成的主线任务，延迟5分钟后自动触发下一轮
                        _schedule_self_check(_session, _agent, loop, trigger="turn_end")
                        # 2026-08-25: 用户回合结束刷新产出资产索引（供 digest 跨轮复用）
                        try:
                            _save_assets_index(_session)
                        except Exception:
                            pass
                        # state.db 已在运行中实时持久化，无需额外快照

                # 前台/后台均不阻塞 WebSocket 循环，以便接收 cancel 消息
                # 任务账本 + 资源租约 + Job Object 硬限制（借鉴重构版）
                if _task_supervisor.is_running(session["id"]):
                    _session_emit(session, {"type": "info", "content": "该会话已有任务在运行，请先发送取消后再试", "session_id": session["id"]})
                else:
                    session["running_agent"] = agent
                    _res_req = _session_resource_request(session)
                    try:
                        _lease = await asyncio.wait_for(
                            _resource_scheduler.acquire(session["id"], _res_req,
                                                        label=_queue_label(session)),
                            timeout=60)
                    except Exception:
                        # 排队超时/容量不足 → 无租约降级运行（不阻塞聊天）
                        _lease = None
                        logger.warning(f"[MemOmics] resource acquire failed for session {session['id'][:12]}, running without lease")
                    # 注：不再 _register_job_limits（方案 A，2026-08-13）——Job Object
                    # CPU/内存硬限制因 task_id 断链从未生效，用户要求多核自由。
                    task = asyncio.ensure_future(run_agent())
                    session["running_task"] = task
                    task.add_done_callback(lambda _t, _sid=session["id"], _ls=_lease: (_release_lease(_sid, _ls), _clear_session_running(_sid)))
                    try:
                        _task_supervisor.register(session["id"], task, label="agent_conversation")
                    except RuntimeError:
                        # 极端竞态：已有活动任务 → 取消本次并释放
                        task.cancel()
                        _release_lease(session["id"], _lease)


            elif msg_type == "get_context_usage":
                # 返回当前会话的上下文窗口使用情况
                agent = session.get("agent")
                if agent is None:
                    # agent 未初始化（重启/重连后还没发消息）：仍返回 DB 持久化的累计 token，
                    # 让上下文窗口不因 agent 未创建而丢失历史统计
                    _ss = _build_session_stats(session["id"])
                    _ss["last_turn"] = _last_turn_stats(session.get("results_dir") or "")
                    _cumulative = (_ss.get("input_tokens", 0) or 0) + (_ss.get("output_tokens", 0) or 0)
                    _session_emit(session, {"type": "context_usage", "data": {
                        "categories": [],
                        "context_max": 0,
                        "context_used": 0,
                        "context_percent": 0,
                        "cumulative_tokens": _cumulative,
                        "model": (session.get("model_config") or {}).get("model", ""),
                        "session_stats": _ss,
                        "headroom_stats": _get_headroom_stats(),
                    }, "session_id": session["id"]})
                else:
                    try:
                        from agent.context_breakdown import compute_session_context_breakdown
                        msgs = session.get("messages", [])
                        conv_msgs = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in msgs]
                        breakdown = compute_session_context_breakdown(agent, messages=conv_msgs)
                        # 累计 session 统计（优先内存，回退 DB 聚合）
                        breakdown["session_stats"] = _build_session_stats(session["id"], agent)
                        breakdown["session_stats"]["last_turn"] = _last_turn_stats(session.get("results_dir") or "")
                        # headroom 压缩统计
                        breakdown["headroom_stats"] = _get_headroom_stats()
                        # 累计 token 用于圆圈展示（全部输入+输出）
                        _ss = breakdown["session_stats"]
                        _cumulative = (_ss.get("input_tokens", 0) or 0) + (_ss.get("output_tokens", 0) or 0)
                        breakdown["cumulative_tokens"] = _cumulative
                        _session_emit(session, {"type": "context_usage", "data": breakdown, "session_id": session["id"]})
                    except Exception as e:
                        # 降级：直接从 compressor 获取基础数据
                        try:
                            compressor = getattr(agent, "context_compressor", None)
                            ctx_max = int(getattr(compressor, "context_length", 0) or 0)
                            ctx_used = int(getattr(compressor, "last_prompt_tokens", 0) or 0)
                            ctx_pct = round(ctx_used / ctx_max * 100, 1) if ctx_max > 0 else 0
                            _ss = _build_session_stats(session["id"], agent)
                            _ss["last_turn"] = _last_turn_stats(session.get("results_dir") or "")
                            _cumulative = (_ss.get("input_tokens", 0) or 0) + (_ss.get("output_tokens", 0) or 0)
                            _session_emit(session, {"type": "context_usage", "data": {
                                "categories": [],
                                "context_max": ctx_max,
                                "context_used": ctx_used,
                                "context_percent": ctx_pct,
                                "cumulative_tokens": _cumulative,
                                "model": getattr(agent, "model", "") or "",
                                "session_stats": _ss,
                                "headroom_stats": _get_headroom_stats(),
                            }, "session_id": session["id"]})
                        except Exception as e2:
                            _session_emit(session, {"type": "context_usage", "error": str(e2), "session_id": session["id"]})

            elif msg_type == "cancel":
                # 强制停止当前运行的 agent
                session["bg_running"] = False
                try:
                    _task_supervisor.cancel(session["id"])
                except Exception:
                    pass
                agent_ref = session.get("running_agent")
                task_ref = session.get("running_task")
                if agent_ref and hasattr(agent_ref, "interrupt"):
                    try:
                        agent_ref.interrupt()
                    except Exception:
                        pass
                if task_ref and hasattr(task_ref, "done") and not task_ref.done():
                    task_ref.cancel()
                # 2026-08-16 修复「中断后还在后台运行」：
                # interrupt() 只设 _interrupt_requested flag，不杀子进程；executor 线程
                # 也取消不掉。这里显式清理本会话的 terminal 后台进程 + R/Python kernel
                # worker（task_id 已接线为 session["id"]，见 run_conversation 调用点）。
                try:
                    from tools.process_registry import process_registry
                    # 2026-08-16: terminal 后台进程的 task_id 被 _resolve_container_task_id
                    # 折叠为 "default"，但 session_key 保留了 session id。按 session_key 杀，
                    # 否则 kill_all(task_id=session id) 永远匹配不到（进程 task_id 全是 default）。
                    _killed = 0
                    for _p in process_registry.list_sessions(session_key=session["id"]):
                        if _p.get("status") != "running":
                            continue
                        try:
                            process_registry.kill_process(_p["session_id"], source="cancel", consume_output=True)
                            _killed += 1
                        except Exception:
                            pass
                    if _killed:
                        logger.info("[cancel] killed %d background processes (session_key=%s)", _killed, session["id"][:12])
                except Exception as e:
                    logger.warning("[cancel] process_registry kill failed: %s", e)
                try:
                    from tools.persistent_kernel import KERNEL_POOL
                    KERNEL_POOL.restart(task_id=session["id"])
                except Exception as e:
                    logger.warning("[cancel] kernel restart failed: %s", e)
                # 2026-08-16 修复「任务结束了还一直输出」：手动停止 → 落盘 mark_cancelled，
                # RunGate 会拦截后续自检自动唤醒（check_gate is_auto_wake=True → stop），
                # 否则 task_plan 还带 in_progress 时 _schedule_self_check 会继续唤醒。
                try:
                    from webui.runtime.run_gate import mark_cancelled
                    _rd_c = session.get("results_dir", "") or ""
                    if _rd_c:
                        mark_cancelled(_rd_c, "user cancelled (stop button)")
                except Exception as e:
                    logger.warning("[cancel] mark_cancelled failed: %s", e)
                # 不在此发 cancelled 消息 — 由 run_agent 的 except/finally 统一发送
                # 如果 agent 引用为空（没有运行中的任务），直接回 cancelled
                if not agent_ref:
                    _session_emit(session, {"type": "cancelled", "session_id": session["id"]})

            elif msg_type == "steer":
                # 中途引导：agent 运行时注入消息，不中断当前工具
                steer_text = msg.get("content", "").strip()
                agent_ref = session.get("running_agent")
                if agent_ref and hasattr(agent_ref, "steer") and steer_text:
                    try:
                        ok = agent_ref.steer(steer_text)
                        _session_emit(session, {"type": "steer_sent", "content": steer_text, "success": bool(ok), "session_id": session["id"]})
                    except Exception as e:
                        _session_emit(session, {"type": "error", "content": f"引导失败: {e}", "session_id": session["id"]})
                else:
                    # Agent 未运行 → 提示改用普通消息，同时自动发起新 turn
                    if steer_text:
                        _session_emit(session, {"type": "info", "content": "Agent 空闲，已自动转为新消息", "session_id": session["id"]})
                        # 复用现有 chat 处理：通过消息队列自己触发
                        loop.call_soon_threadsafe(
                            lambda: asyncio.ensure_future(
                                ws.send_text(json.dumps({"type": "_internal_chat", "message": steer_text, "session_id": session["id"]}, ensure_ascii=False))
                            )
                        )
                    continue

    except WebSocketDisconnect:
        # WS 断开 - 只断开 WS 引用，不杀 agent（agent 继续在后台运行）
        _detach_ws(ws)
        _TASK_WS_CLIENTS.discard(ws)  # 任务面板订阅也要摘掉，免得往死连接推
        if current_sid and current_sid in _sessions:
            _cleanup_session_agent(_sessions[current_sid], kill_agent=False)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f'WS EXCEPTION: {type(e).__name__}: {e}', flush=True)
        try:
            await ws.send_text(json.dumps({"type": "error", "content": f"WebSocket 错误: {e}"}, ensure_ascii=False))
        except Exception:
            pass
        _detach_ws(ws)
        if current_sid and current_sid in _sessions:
            _cleanup_session_agent(_sessions[current_sid], kill_agent=False)


# === 远端集群控制台（2026-09-19）===
# 让用户直接在 WebUI 里敲 SSH 命令 / 交作业，不必先跟模型说话。三点取舍：
#  1. 复用 remote_cluster 的 handler —— UI 与 agent 走同一条代码路径，行为不漂移；
#  2. UI 里敲的命令是用户自己的操作，不过 rail_review / 辩论门禁（那是给模型看的闸）；
#  3. 配置写回用「文本块替换」而不是 _hermes_config_write —— 后者整文件 yaml.dump，
#     会把 config.yaml 的注释全抹掉（本机已被抹过一次，注释模板就是这么没的）。
_CLUSTER_FIELDS = (
    "enabled", "host", "user", "port", "key", "workdir", "scheduler",
    "partition", "queue", "local_root", "remote_root", "timeout", "job_dir",
    "extra_ssh_options", "default_node", "node_policy",
)
# 单个命名节点里允许覆盖的字段（前端节点编辑器渲染的就是这些；其余字段走共享配置）
_CLUSTER_NODE_FIELDS = (
    "name", "host", "port", "user", "key", "workdir", "note", "role",
    "proxy_jump", "scheduler", "partition", "queue",
)
_CLUSTER_NODE_LIST_FIELDS = ("extra_ssh_options",)
_CLUSTER_ACTIONS = ("locate", "nodes", "check", "run", "push", "pull", "submit", "status", "logs", "cancel", "jobs")
_CLUSTER_NODE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")


def _cluster_mod():
    from memomics.bio_tools import remote_cluster as _rc
    return _rc


def _cluster_view() -> dict:
    """配置视图：只回显当前生效值，不建连接（连通性自检是单独的 action=check）。"""
    rc = _cluster_mod()
    cfg = rc._load_remote_config(force=True)
    out = {k: cfg.get(k) for k in _CLUSTER_FIELDS}
    out["enabled"] = bool(cfg.get("enabled"))
    key = str(cfg.get("key") or "")
    out["key_exists"] = bool(key) and os.path.exists(os.path.expanduser(key))
    out["config_path"] = str(rc._get_config_path())
    out["tool_visible"] = bool(rc.remote_cluster_enabled())
    out["job_dir_effective"] = cfg.get("job_dir")
    # 命名节点：既回显「用户显式写了什么」（spec），也回显「实际会连什么」（effective）。
    # effective 由 remote_cluster._node_table 算出来，和真正连的时候用的是同一份逻辑。
    table = rc._node_table(cfg)
    nodes = []
    for name, entry in (cfg.get("nodes") or {}).items():
        eff = table.get(name) or {}
        spec = {"name": name}
        for k in _CLUSTER_NODE_FIELDS:
            if k == "name":
                continue
            val = entry.get(k)
            if val not in (None, "", [], {}):
                spec[k] = val
        nodes.append({
            "name": name,
            "spec": spec,
            "effective": {
                "host": eff.get("host"), "user": eff.get("user"), "port": eff.get("port"),
                "key": eff.get("key"), "workdir": eff.get("workdir"),
                "job_dir": eff.get("job_dir"), "scheduler": eff.get("scheduler"),
                "proxy_jump": str(entry.get("proxy_jump") or ""),
                "note": eff.get("_note") or "",
            },
            "is_default": name == str(cfg.get("default_node") or ""),
            "reachable_note": "",
        })
    out["nodes"] = nodes
    out["nodes_effective_count"] = len(table)
    out["node_policy"] = cfg.get("node_policy") or "ask"
    return out


def _cluster_yaml_scalar(value) -> str:
    """单引号 YAML 标量：Windows 路径里的反斜杠在单引号里是字面量，不会被转义吃掉。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _cluster_node_lines(nodes) -> list:
    """生成 remote.nodes: 段（两级缩进）。名字非法/重复直接报错，不静默丢配置。"""
    if isinstance(nodes, dict):
        items = []
        for name, spec in nodes.items():
            if isinstance(spec, dict):
                item = dict(spec)
            elif spec in (None, ""):
                item = {}
            else:
                item = {"host": spec}
            item["name"] = name
            items.append(item)
    elif isinstance(nodes, (list, tuple)):
        items = [dict(x) for x in nodes if isinstance(x, dict)]
    else:
        raise ValueError("nodes 必须是列表或字典")
    seen = set()
    lines = ["  nodes:"]
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        if not _CLUSTER_NODE_NAME_RE.match(name):
            raise ValueError(
                "节点名 %r 不合法：只允许字母/数字/点/下划线/短横线，且不超过 48 字符"
                "（中文请写在 note 里，节点名会进入远端作业名和日志文件名）" % name)
        low = name.lower()
        if low in seen:
            raise ValueError("节点名 %r 重复了（节点名用来选机器，不能重名）" % name)
        seen.add(low)
        spec = {}
        for k in _CLUSTER_NODE_FIELDS:
            if k == "name":
                continue
            val = item.get(k)
            if val is None:
                continue
            if isinstance(val, str) and not val.strip():
                continue
            if k == "port":
                try:
                    val = int(str(val).strip())
                except Exception:
                    raise ValueError("节点 %r 的 port 不是数字：%r" % (name, item.get(k)))
            spec[k] = val
        extra = item.get("extra_ssh_options")
        if extra:
            spec["extra_ssh_options"] = extra if isinstance(extra, (list, tuple)) else [str(extra)]
        if not spec:
            lines.append("    %s: {}" % name)
            continue
        lines.append("    %s:" % name)
        for k, v in spec.items():
            if isinstance(v, (list, tuple)):
                lines.append("      %s: [%s]" % (k, ", ".join(_cluster_yaml_scalar(x) for x in v)))
            else:
                lines.append("      %s: %s" % (k, _cluster_yaml_scalar(v)))
    if len(lines) == 1:
        return []
    return lines


def _cluster_write_config(values: dict) -> dict:
    rc = _cluster_mod()
    cfg = rc._load_remote_config(force=True)  # 合并的底：当前生效值
    path = rc._get_config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
    # 合并而不是替换：从当前生效配置起底，只覆盖前端提交的字段。
    # 这样手写在 config.yaml 里、表单没有的字段（extra_ssh_options 等）不会被抹掉。
    merged = {}
    for key in _CLUSTER_FIELDS:
        cur = cfg.get(key)
        if key == "enabled":
            merged[key] = bool(cur)
        elif cur is not None and cur != "" and cur != [] and cur != {}:
            merged[key] = cur
    nodes_in = values.pop("nodes", None) if "nodes" in values else None
    for key, val in values.items():
        if key not in _CLUSTER_FIELDS:
            continue
        if key == "enabled":
            merged[key] = bool(val) if not isinstance(val, str) else val.strip().lower() in ("1", "true", "yes", "on")
            continue
        if val is None or (isinstance(val, str) and not val.strip()):
            merged.pop(key, None)  # 明确的空值 = 移除该字段，回落默认
            continue
        merged[key] = val
    if nodes_in is not None:
        old_nodes = cfg.get("nodes") or {}
        if isinstance(nodes_in, dict):
            seq = []
            for name, spec in nodes_in.items():
                item = dict(spec) if isinstance(spec, dict) else ({"host": spec} if spec else {})
                item["name"] = name
                seq.append(item)
        else:
            seq = list(nodes_in or [])
        # 逐个节点并回原来的显式覆盖：前端没渲染的字段（extra_ssh_options/job_dir/timeout）
        # 保留；前端显式给了空串的字段 = 用户清掉了这个覆盖，回落共享配置。
        for item in seq:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            old = old_nodes.get(name) or {}
            if not isinstance(old, dict):
                old = {}
            for k, v in list(item.items()):
                if k == "name":
                    continue
                if isinstance(v, str) and not v.strip():
                    item.pop(k)
                    old.pop(k, None)
            for k, v in old.items():
                item.setdefault(k, v)
        values["nodes"] = seq
    lines = ["remote:"]
    for key in _CLUSTER_FIELDS:
        if key not in merged:
            continue
        val = merged[key]
        if isinstance(val, (list, tuple)):
            lines.append("  %s: [%s]" % (key, ", ".join(_cluster_yaml_scalar(x) for x in val)))
        else:
            lines.append("  %s: %s" % (key, _cluster_yaml_scalar(val)))
    if "nodes" in values:
        lines += _cluster_node_lines(values["nodes"])
    block = "\n".join(lines) + "\n"
    # 顶层 remote: 块（后续行必须缩进；注释行以 # 开头，不会被误吞）
    pat = re.compile(r"(?m)^remote:[ \t]*\n(?:[ \t]+[^\n]*\n)*")
    m = pat.search(text)
    if m:
        new_text = text[:m.start()] + block + text[m.end():]
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        new_text = text + block
    # 落盘前先校验：新文件必须能解析出 remote 段，宁可写不进去也不写坏 config.yaml
    import yaml as _yaml
    parsed = _yaml.safe_load(new_text) or {}
    if not isinstance(parsed, dict) or not isinstance(parsed.get("remote"), dict):
        raise ValueError("生成的 remote 段无法被 YAML 解析，已放弃写入（config.yaml 未改动）")
    tmp = str(path) + ".cluster.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(new_text)
    os.replace(tmp, path)
    rc._load_remote_config(force=True)  # 清 mtime 缓存，下一个动作就用新配置
    try:
        from tools.registry import invalidate_check_fn_cache
        invalidate_check_fn_cache()  # 让模型侧立刻看到工具出现/消失，不用重启
    except Exception:
        pass
    return _cluster_view()


@app.get("/api/cluster/status")
async def api_cluster_status():
    try:
        return {"ok": True, "config": _cluster_view(), "actions": list(_CLUSTER_ACTIONS)}
    except Exception as exc:
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}


@app.post("/api/cluster/config")
async def api_cluster_config(request: Request):
    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "error": "请求体不是合法 JSON"}
    if not isinstance(body, dict):
        return {"ok": False, "error": "请求体必须是 JSON 对象"}
    values = {k: v for k, v in body.items() if k in _CLUSTER_FIELDS or k == "nodes"}
    if not values:
        return {"ok": False, "error": "没有可写入的字段（可选：%s, nodes）" % ", ".join(_CLUSTER_FIELDS)}
    try:
        return {"ok": True, "config": _cluster_write_config(values)}
    except Exception as exc:
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}


@app.post("/api/cluster/exec")
async def api_cluster_exec(request: Request):
    """把 WebUI 的输入原样转给 remote_cluster（与 agent 同一个 handler）。"""
    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "error": "请求体不是合法 JSON"}
    if not isinstance(body, dict):
        return {"ok": False, "error": "请求体必须是 JSON 对象"}
    action = str(body.get("action") or "").strip().lower()
    if action not in _CLUSTER_ACTIONS:
        return {"ok": False, "error": "未知 action: %r（可选：%s）" % (action, ", ".join(_CLUSTER_ACTIONS))}
    args = {k: v for k, v in body.items() if v is not None and v != ""}
    args["action"] = action
    try:
        raw = _cluster_mod().remote_cluster_handler(args)
    except Exception as exc:
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
    try:
        return {"ok": True, "result": json.loads(raw)}
    except Exception:
        return {"ok": True, "result": {"note": "工具未返回 JSON", "raw": raw}}


if __name__ == "__main__":
    import uvicorn
    import time as _time
    import socket as _sock
    port = int(os.environ.get("MEMOMICS_PORT", "8899"))
    _load_persisted_sessions()

    # 2026-08-08：端口已被占用 = 已有实例在运行。
    # 直接退出（不开第二个 server、不开新浏览器标签）——用户已打开的
    # WebUI 页面继续使用（WS 自动重连），避免每次点 start.bat 都多一个标签页。
    try:
        with _sock.create_connection(("127.0.0.1", port), 1):
            print(f"[MemOmics] 端口 {port} 已被占用 — 已有实例在运行。", flush=True)
            print(f"[MemOmics] 请直接使用已打开的 http://127.0.0.1:{port} 页面", flush=True)
            print(f"[MemOmics] （如需重启：先关闭原 MemOmics 窗口，再重新启动）", flush=True)
            raise SystemExit(0)
    except OSError:
        pass  # 端口空闲，正常启动

    # 启动通用长任务守护（独立进程，不随 server 崩溃）
    # P1-14(2026-08-13): 走 platform_runtime 单入口薄层（平台差异收敛一处）
    try:
        _guardian_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "task_guardian.py")
        if os.path.exists(_guardian_path):
            from memomics.platform_runtime import spawn_detached
            spawn_detached([sys.executable, _guardian_path])
            print(f"[MemOmics] Task guardian started")
    except Exception:
        pass
    
    # 2026-08-25: 非 Windows 首启环境探测 —— 打包模板 environment.json 的
    # paths.python/paths.r 为空，validate_env.py 会把探测结果回填（Linux/macOS）。
    # Windows 本机 environment.json 已含完整路径，跳过以免误改本机配置。
    try:
        if os.name != "nt":
            _env_script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "..", "scripts", "validate_env.py")
            if os.path.exists(_env_script):
                import subprocess as _sp
                _pr = _sp.run([sys.executable, _env_script],
                              capture_output=True, text=True, timeout=180)
                _last = ((_pr.stdout or "").strip().splitlines() or [""])[-1]
                print(f"[MemOmics] environment discovery exit={_pr.returncode} | {_last}", flush=True)
    except Exception:
        pass  # 探测失败不阻塞启动；worker 运行时另有 .libPaths() 探测兜底

    print(f"MemOmics WebUI v2 starting on http://127.0.0.1:{port}")
    # 2026-08-08：不再自动打开浏览器（用户要求手动输入地址，
    # 避免每次启动/重启都新开标签页）。请在浏览器手动访问：
    print(f"[MemOmics] 请在浏览器手动打开: http://127.0.0.1:{port}")
    # 自动重启：DeepSeek API 空响应等非致命错误不应杀死整个服务
    _crash_count = 0
    while True:
        try:
            uvicorn.run(app, host=os.environ.get("MEMOMICS_HOST", "127.0.0.1"), port=port)
        except Exception as e:
            _crash_count += 1
            if _crash_count > 20:
                print(f"[FATAL] Server crashed {_crash_count} times, giving up: {e}")
                break
            print(f"[WARN] Server crashed (#{_crash_count}), restarting in 3s: {e}")
            # 批O3c(2026-08-16)：崩溃原因留痕——uvicorn 异常时写完整 traceback 到
            # log/server_crash.log（此前重启原因只打印在控制台，窗口一关就无从追查）
            try:
                import traceback as _tb
                _log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "log")
                os.makedirs(_log_dir, exist_ok=True)
                with open(os.path.join(_log_dir, "server_crash.log"), "a", encoding="utf-8") as _f:
                    _f.write("\n===== %s  crash #%d =====\n" % (
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), _crash_count))
                    _tb.print_exc(file=_f)
            except Exception:
                pass
            _time.sleep(3)
