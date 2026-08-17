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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="MemOmics WebUI v2")

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
                # ── 无工具在飞 + 5 分钟无事件 = 模型网关挂起（原逻辑） ──
                try:
                    if hasattr(agent_ref, "interrupt"):
                        agent_ref.interrupt()
                except Exception:
                    pass
                try:
                    _session_emit(s, {"type": "error", "content": "Agent 长时间无响应（5 分钟无输出），已自动中断。可能是模型网关连接挂起，请重试或切换模型。", "session_id": sid})
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
    }
    db = _get_session_db()
    if db and hasattr(db, "_conn"):
        try:
            row = db._conn.execute(
                "SELECT input_tokens, output_tokens, cache_read_tokens, "
                "cache_write_tokens, reasoning_tokens FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row:
                stats["input_tokens"] = row[0] or 0
                stats["output_tokens"] = row[1] or 0
                stats["cache_read_tokens"] = row[2] or 0
                stats["cache_write_tokens"] = row[3] or 0
                stats["reasoning_tokens"] = row[4] or 0
        except Exception:
            pass
    stats["prompt_tokens"] = stats["input_tokens"]
    return stats


_TOKEN_USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens",
                       "cache_write_tokens", "reasoning_tokens")


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
                # 尝试提取用户指定的路径（如 PROJECT_DATA_DIR）
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


def _build_task_resume_prompt(session):
    """检测是否有未完成的主线任务（task_plan.md 或未完成待办）。
    如果是知识问答/进度查询 → 只给轻量提示。如果是正常对话 → 给完整提醒。"""
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
    
    # 检查当前意图：知识问答/进度查询/方案讨论 → 轻量提示
    _intent = session.get("intent", "")
    _is_light_question = _intent in ("knowledge_ask", "progress_check", "analysis_plan", "chat", "cancel_task")
    
    if _is_light_question:
        # 轻量：只提醒有任务在后台，不强制推进
        return (
            "💡 提示：你有未完成的分析任务在后台。"
            "先回答用户的问题，回答完后如果需要继续任务，"
            f"可以读取 {plan_path} 查看进度。"
            if has_plan else
            "💡 提示：你有未完成的待办事项。先回答用户的问题。"
        )
    
    # 正常对话 → 完整提醒
    parts = ["⛔ 你有未完成的主线任务！"]
    if has_plan:
        parts.append(f"- task_plan.md: {plan_path if results_dir else '存在'}")
    if has_todos:
        parts.append(f"- 待办: {len(incomplete)}/{len(todos)} 未完成: {', '.join(t.get('title','')[:30] for t in incomplete[:5])}")
    parts += [
        "",
        "⛔ 工具优先！你的下一句话必须是工具调用（terminal/read_file/search_files/process），不是文字！",
        "禁止：先说'马上查'然后输出文字。正确：直接调工具，完成后再汇报。",
        "",
        "你必须按以下优先级行动：",
        "1. 先简短回答用户的问题（如果用户问了问题）",
        "2. 然后立即检查主线任务进度：",
        "   - 读 task_plan.md 看当前 Phase",
        "   - 调 process(action='list') 检查后台进程",
        "   - 调 process(action='poll') 查具体进程状态",
        "   - 用 search_files 看 results_dir 最新产出文件",
        "3. 根据进度继续执行下一个未完成的待办/Phase",
        "4. 报错→分析原因→能修就修→修不了记录到 task_plan.md Errors 段→跳过继续",
        "禁止：回答完用户问题后直接结束 turn！必须检查并推进主线！",
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
                     "我去看", "我去跑", "我去把", "先把"]
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
    return False


def _results_dir_changed_since(session, ts: float) -> bool:
    """results_dir 下是否有真实产出文件在 ts 之后被修改（排除平台自写文件）。

    平台自写(不算产出): token_usage.jsonl / .task_state.json / task_plan.md / log/ / .loopx/
    扫描上限 200 个文件，避免大目录全量遍历。
    返回 True 表示"有变化"(或无法判断——此时不干预，避免误伤)。
    """
    _rd = session.get("results_dir", "") or ""
    if not _rd or not os.path.isdir(_rd) or not ts:
        return True
    _skip_names = {"token_usage.jsonl", ".task_state.json", "task_plan.md"}
    _targets = []
    for _sub in ("figures", "scripts", "results", "data", "datasets"):
        _p = os.path.join(_rd, _sub)
        if os.path.isdir(_p):
            try:
                _targets.extend(os.path.join(_p, f) for f in os.listdir(_p))
            except Exception:
                pass
    try:
        _targets.extend(os.path.join(_rd, f) for f in os.listdir(_rd))
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
            if os.path.isfile(_f) and os.path.getmtime(_f) >= ts:
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


def _schedule_self_check(session, agent, loop):
    """本轮结束后，如果有未完成的主线任务，延迟5分钟后自动触发下一轮自检。
    但如果 task_plan 被标记为 cancelled 或 paused，则跳过。"""
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
    
    async def _wakeup():
        await asyncio.sleep(delay)
        try:
            if sid not in _sessions: return
            s = _sessions[sid]
            if s.get("running_agent") or s.get("running_task"):
                # 2026-08-16: 冻结分支已直接武装诊断回合 → 本唤醒不重排（防双发）
                if s.get("_stall_wake_active"):
                    return
                # 2026-08-14 P0: 早退重排——被并发回合吞掉的唤醒重新调度（最多 3 次）
                _retry_n = s.setdefault("_wakeup_retry_n", 0)
                if _retry_n < 3:
                    s["_wakeup_retry_n"] = _retry_n + 1
                    s["_urgent_wakeup"] = True
                    logger.info(f"[SelfCheck] session {sid[:12]}: 唤醒遇运行中回合，重排 #{_retry_n + 1}/3")
                    _schedule_self_check(s, agent, loop)
                else:
                    s.pop("_wakeup_retry_n", None)
                return
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
    """自检唤醒精简上下文（2026-08-14 成本优化）。

    之前每次唤醒走 agent 内部全量对话历史（实测 67K input tokens/次，
    占全部 token 消耗 66%）。改为只带：
    1) task_plan.md 主线区摘要（含 Goal/Phase 状态）
    2) 最近一条用户消息（原始诉求）
    3) 最近一条助手回复（上次做到哪）
    用户回合仍走 run_agent 的全量历史路径，不受影响。
    """
    history = []
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
    _msgs = session.get("messages", [])
    for _m in reversed(_msgs[-10:]):
        if _m.get("role") == "user" and isinstance(_m.get("content"), str) and _m.get("content").strip():
            history.append({"role": "user", "content": _m["content"][:1000]})
            break
    for _m in reversed(_msgs[-10:]):
        if _m.get("role") == "assistant" and isinstance(_m.get("content"), str) and _m.get("content").strip():
            history.append({"role": "assistant", "content": _m["content"][:2000]})
            break
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
                set_session_context(sid=session["id"], results_dir=session.get("results_dir", ""))
            except Exception:
                pass
            # 2026-08-14 成本优化：唤醒用精简上下文（task_plan 摘要 + 最近用户/助手消息），
            # 不带全量历史（67K input/次 → ~4K）
            _wake_history = _build_self_check_wake_history(session)
            return agent.run_conversation(_inject_anchors(session, message), conversation_history=_wake_history or None, task_id=session["id"])
        # 2026-08-16: 去 wait_for —— 让长工具自然跑完；网关挂起由 stall watchdog 中断
        result = await loop.run_in_executor(None, _run)
        final = result.get("final_response", "") if isinstance(result, dict) else str(result)
        session.setdefault("messages", []).append(
            {"role": "assistant", "content": final, "time": datetime.now().strftime("%H:%M:%S"), "source": "self_check"})
        _session_emit(session, {"type": "complete", "content": final[:200], "session_id": session["id"]})
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
        _schedule_self_check(session, agent, asyncio.get_event_loop())


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
    _is_analysis = _intent not in ("", "chat", "self_intro", "knowledge_ask", "progress_check")
    _has_messages = len(session.get("messages", [])) >= 2

    if not os.path.isfile(plan_path):
        # 🔑 自动创建 task_plan.md 的严格条件：
        # ① 有数据路径 ② 有执行关键词 ③ 意图不是轻量类型
        _msgs = session.get("messages", [])
        _last_msg = _msgs[-1].get("content", "") if _msgs else ""
        _has_data_path = bool(re.search(r'[A-Za-z]:[/\\]\S+', _last_msg))
        _has_exec_kw = any(kw in _last_msg for kw in 
                          ("跑", "执行", "开始", "启动", "运行", "run", "start", "execute", "analyze",
                           "帮我做", "帮我跑", "做分析", "跑分析"))
        _is_exec = _intent in ("analysis_exec", "direct_exec")
        # 三个条件同时满足才创建：explicit exec intent OR (data+exec keywords), AND not light intent
        _LIGHT_FOR_PLAN = ("chat", "self_intro", "knowledge_ask", "progress_check", "analysis_plan")
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

def _load_provider_keys():
    global _provider_keys
    try:
        if os.path.exists(_PROVIDER_KEYS_FILE):
            with open(_PROVIDER_KEYS_FILE, "r", encoding="utf-8") as f:
                _provider_keys = json.load(f)
    except Exception:
        _provider_keys = {}

_load_provider_keys()

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
        if ak and pid.lower() == "deepseek":
            os.environ["DEEPSEEK_API_KEY"] = ak
            if bu:
                os.environ["DEEPSEEK_BASE_URL"] = bu.rstrip("/")
            os.environ["DEEPSEEK_MODEL"] = _current_model.get("model", "deepseek-v4-flash")
            print(f"[INFO] Debate env injected from provider_keys (deepseek): URL={bu} MODEL={_current_model.get('model','?')}")
            return
    for pid, info in _provider_keys.items():
        ak = info.get("api_key", "")
        bu = info.get("base_url", "")
        if ak and ("dcs" in pid.lower() or "dcs" in bu.lower() or "deepseek" in pid.lower()):
            os.environ["DEEPSEEK_API_KEY"] = ak
            if bu:
                os.environ["DEEPSEEK_BASE_URL"] = bu.rstrip("/")
            os.environ["DEEPSEEK_MODEL"] = _current_model.get("model", "deepseek-v4-flash")
            print(f"[INFO] Debate env injected (fallback): URL={bu} MODEL={_current_model.get('model','?')}")
            return

# 启动同步：如果 _current_model 有 key 但 provider_keys 为空，
# 自动按 base_url 反查 provider 并同步 key，保证交互框下拉框能显示模型
if _current_model.get("api_key") and not _provider_keys:
    _cur_base = _current_model.get("base_url", "")
    for _p in _CHINA_PROVIDERS:
        if _p["api"] == _cur_base:
            _provider_keys[_p["id"]] = {"api_key": _current_model["api_key"], "base_url": _cur_base}
            _save_provider_keys()
            print(f"[INFO] 已自动同步 provider key: {_p['id']} (从 model_config.json)")
            break

# 为 debate_analysis 等需要独立 LLM 调用的模块注入环境变量
_sync_debate_env()

# 预设模型 (兼容旧 API, 从 _CHINA_PROVIDERS 生成)
_preset_models = []
for p in _CHINA_PROVIDERS:
    _pname = p["name"].split("(")[0].strip()
    for m in p.get("models", []):
        _preset_models.append({"id": m["id"], "name": m["name"] + " (" + _pname + ")", "provider": "openai", "provider_id": p["id"], "base_url": p["api"], "provider_name": _pname})

SKILLS_DIR = os.path.join(MEMOMICS_DIR, "skills")
KB_DIR = os.path.join(MEMOMICS_DIR, "memomics", "knowledge_base")
_lit_cache = {}  # P5: literature dedup cache { query_hash: (timestamp, results_json) }
WORK_DIR = os.path.join(MEMOMICS_DIR, "work")
RESULTS_DIR = os.path.join(MEMOMICS_DIR, "results")
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
_RED_TRIGGER_CACHE = None  # [(skill_name, [triggers...]), ...]


def _match_red_skill_triggers(user_text: str) -> list:
    """解析 SKILLS_INDEX.md 中 RED 必触发行的触发词，与用户消息做子串匹配。
    返回命中的 skill 名列表（按索引顺序）。空消息/无命中 → []。
    缓存随 SKILLS_INDEX mtime 失效（由 _read_skills_index 的重读隐式保证：
    这里每次直接重新解析，索引 50KB 解析开销 < 1ms，可忽略）。"""
    global _RED_TRIGGER_CACHE
    if not user_text:
        return []
    idx = _read_skills_index()
    if _RED_TRIGGER_CACHE is None:
        _RED_TRIGGER_CACHE = []
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
    hits = []
    for name, triggers in _RED_TRIGGER_CACHE:
        matched = False
        for kw in triggers:
            kw_l = kw.lower()
            if len(kw_l) >= 2:
                if kw_l in t:
                    matched = True
                    break
                # 英文触发词：词级交集（"review paper" 命中 "Can you review this manuscript?" 的 review）
                if " " in kw_l and t_words:
                    _STOP = {"this", "that", "the", "a", "an", "for", "to", "with",
                             "is", "are", "of", "and", "or", "in", "on", "my", "me",
                             "i", "you", "can", "do", "does", "be", "it", "its", "as"}
                    kw_words = set(w for w in kw_l.split() if w not in _STOP)
                    if kw_words and any(w in t_words for w in kw_words):
                        matched = True
                        break
        if matched:
            hits.append(name)
    # 批K(2026-08-16)：本地文献库操作豁免全局文献类 RED skills——
    # "总结文献库里…" 不应被 literature-review(触发词'总结') / paper-summary(触发词'paper')
    # 抢占 skill_view，本地文献库有专用工具（summarize_paper / kb_extract_from_paper / literature_import）。
    _LOCAL_LIT_RED_EXEMPT = {"literature-review", "paper-summary", "paper-download",
                             "paper-translate", "academic-paper-writing"}
    if hits and ("文献库" in user_text or "文献库里" in user_text or "/papers" in user_text
                 or ".pdf" in user_text.lower()):
        hits = [h for h in hits if h not in _LOCAL_LIT_RED_EXEMPT]
    return hits


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


# === 自我介绍文案（WebUI 与微信路径共用，绕过 LLM）===
_SELF_INTRO_ZH = (
    "我是 **MemOmics**，基于 Hermes 框架的自进化多组学生信分析平台。\n\n"
    "我不是聊天机器人，而是能帮你**跑完完整生信分析**的自主 Agent。给我数据，我自己扫描、分析、出报告，你不用写一行代码。\n\n"
    "## 核心能力\n\n"
    "**数据扫描**：自动识别 scRNA-seq / scATAC-seq / 空间转录组 / Bulk RNA-seq 等数据格式，检测物种、组织、细胞数、注释状态，推荐最佳分析路径。\n\n"
    "**完整分析流程**：QC（去污染→双胞过滤→归一化）→ 降维 → 聚类 → 细胞注释 → 差异表达 → 通路富集 → 细胞通讯 → 轨迹推断 → SCENIC 转录因子调控 → 生存分析 → 报告生成，全流程自动走完。\n\n"
    "**R + Python 双引擎**：根据数据规模智能推荐——大于 60 万细胞自动切换 Python/Scanpy，默认用 R/Seurat。缺包时自动安装（BiocManager/remotes/pip/conda），不用你操心环境。\n\n"
    "**内置 270+ 生信技能模板**：Seurat、Scanpy、CellChat、Monocle3、SCENIC、CellBender、Harmony、squidpy 等覆盖主流分析场景，分析时自动调用对应技能的参数和模板，不是从零写代码。\n\n"
    "**铁轨审查机制**：每个分析步骤前后自动审查——环境检查 → 缺失包安装 → 参数校验 → 结果质量评估 → 图表检查 → 代码审查。不通过则阻断纠正，不会带着错误继续往下跑。\n\n"
    "**知识库驱动**：内置生信知识库（物种/组织/方向三维索引），分析时自动检索相关生物学背景，结合文献先验知识做注释和解读。\n\n"
    "**结果管理**：分析结果按 `results/<模块>/<方法>/{figures,results,scripts,data}` 分目录存储，每次分析可追溯、可复现。\n\n"
    "有什么需要帮忙的，直接告诉我！"
)
_SELF_INTRO_EN = (
    "I'm **MemOmics**, a self-evolving multi-omics bioinformatics analysis platform powered by the Hermes framework.\n\n"
    "I'm not a chatbot — I'm an autonomous Agent that can run complete bioinformatics analyses for you. Give me your data, and I'll scan, analyze, and generate reports. You don't need to write a single line of code.\n\n"
    "## Core Capabilities\n\n"
    "**Data Scanning**: Automatically identifies scRNA-seq / scATAC-seq / Spatial Transcriptomics / Bulk RNA-seq formats, detecting species, tissue, cell count, and annotation status to recommend optimal analysis paths.\n\n"
    "**Complete Analysis Pipeline**: QC (decontamination → doublet filtering → normalization) → Dimensionality Reduction → Clustering → Cell Annotation → Differential Expression → Pathway Enrichment → Cell Communication → Trajectory Inference → SCENIC TF Regulation → Survival Analysis → Report Generation — fully automated.\n\n"
    "**R + Python Dual Engine**: Intelligently selects R/Seurat by default, auto-switches to Python/Scanpy for datasets >600K cells. Auto-installs missing packages (BiocManager/remotes/pip/conda).\n\n"
    "**270+ Built-in Bioinformatics Skill Templates**: Seurat, Scanpy, CellChat, Monocle3, SCENIC, CellBender, Harmony, squidpy covering mainstream analysis scenarios. Skills are called with proper parameters — never writing code from scratch.\n\n"
    "**Rail Review Mechanism**: Each analysis step undergoes pre/post review — environment check → missing package install → parameter validation → result quality assessment → figure inspection → code review. Blocked and corrected if anything fails.\n\n"
    "**Knowledge Base Driven**: Built-in bioinformatics knowledge base (species/tissue/direction 3D index) for automatic biological context retrieval, combining literature priors for annotation and interpretation.\n\n"
    "**Result Management**: Results stored under `results/<module>/<method>/{figures,results,scripts,data}` — traceable and reproducible for every analysis.\n\n"
    "What can I help you with? Just let me know!"
)

# === 图路由：意图分类 + 技能触发注入 ===
# 五级意图：self_intro > chat > research_plan > direct_exec > analysis
# SOUL.md 三级操作级别（轻量/统计/分析级）在 agent 内部独立判断，意图不覆盖
def _classify_intent(text: str):
    """五级意图识别。Returns: (intent, confidence, meta_dict)
    
    Intent flow:
      self_intro    — 自介快回，绕过LLM
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
    if "介绍一下" in t and any(x in t for x in ["你", "自己", "你们"]):
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
    if any(kw in t for kw in ["停止", "暂停", "取消", "不要", "别"]) and any(kw in t for kw in 
        ["任务", "分析", "cellbender", "训练", "计算", "进程", "job"]):
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
                   "状态", "nvidia-smi", "gpu", "显卡", "显存", "内存",
                   "后台", "后台任务", "后台进程", "卡住了", "停了",
                   "还要多久", "多久了", "跑了多久", "跑多久",
                   "check progress", "how long", "status", "still running"]
    if any(kw in t for kw in PROGRESS_KW):
        return ("progress_check", 0.85, {"reason": "progress_or_status_query"})

    # 1.5b: knowledge_ask（知识/错误/润色/参数问题 — 无数据路径）
    KNOWLEDGE_QUESTION_KW = ["什么意思", "是什么", "什么是", "参数", "怎么选",
                             "怎么设", "怎么调", "区别", "vs", "对比",
                             "推荐", "建议", "选哪个", "哪个好", "最佳",
                             "怎么用", "用途", "作用", "原理", "含义",
                             "解释", "说明", "介绍一下",
                             "哪些", "用什么方法", "怎么修", "怎么处理",
                             "润色", "怎么写", "如何选择", "如何设置",
                             "报错了", "不工作", "出错了", "失败了", "怎么解决"]
    _has_knowledge_q = any(kw in t for kw in KNOWLEDGE_QUESTION_KW)
    _is_planning_q = any(kw in t for kw in ["怎么设计", "如何设计", "方案", "路线",
                                             "研究框架", "分析框架", "实验设计"])
    # 错误/修复上下文：即使有"跑"也不当执行动作
    _is_error_context = any(kw in t for kw in ["报错", "出错", "错误", "不工作", "失败", "怎么修", "怎么解决"])
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


def _build_skill_injection(intent: str, domain: str, session_lang: str = "zh", user_text: str = "") -> str:
    """根据意图+领域构建系统指令（硬注入，LLM无法跳过）"""
    # === RED 必触发预检：用户消息命中 RED skill 触发词 → 前置强约束先 skill_view ===
    # 审稿/润色/拆解等文献类任务常被意图分类器分到弱约束分支（literature/chat），
    # agent 会跳过 skill_view 直接按固有知识处理。这里在意图注入之外兜底：
    # 命中 RED 触发词 → 注入最高优先级指令，强制先加载对应 skill。
    # 注意：不覆盖原意图注入，作为前置段拼接。
    red_prefix = ""
    red_hits = _match_red_skill_triggers(user_text)
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
        return red_prefix
    if intent == "self_intro":
        # 硬注入固定自我介绍，LLM 禁止自由发挥
        return (
            "【系统指令：自我介绍 — 必须逐字输出以下内容，禁止修改、禁止缩写、禁止自己编】\n\n"
            "请直接输出以下固定内容作为回复，不要改动任何字：\n\n"
            "> 我是 **MemOmics**，基于 Hermes 框架的自进化多组学生信分析平台。\n"
            "> \n"
            "> 我不是聊天机器人，而是能帮你**跑完完整生信分析**的自主 Agent。给我数据，我自己扫描、分析、出报告，你不用写一行代码。\n"
            "> \n"
            "> ## 核心能力\n"
            "> \n"
            "> **数据扫描**：自动识别 scRNA-seq / scATAC-seq / 空间转录组 / Bulk RNA-seq 等数据格式，检测物种、组织、细胞数、注释状态，推荐最佳分析路径。\n"
            "> \n"
            "> **完整分析流程**：QC（去污染→双胞过滤→归一化）→ 降维 → 聚类 → 细胞注释 → 差异表达 → 通路富集 → 细胞通讯 → 轨迹推断 → SCENIC 转录因子调控 → 生存分析 → 报告生成，全流程自动走完。\n"
            "> \n"
            "> **R + Python 双引擎**：根据数据规模智能推荐——大于 60 万细胞自动切换 Python/Scanpy，默认用 R/Seurat。缺包时自动安装（BiocManager/remotes/pip/conda），不用你操心环境。\n"
            "> \n"
            "> **内置 270+ 生信技能模板**：Seurat、Scanpy、CellChat、Monocle3、SCENIC、CellBender、Harmony、squidpy 等覆盖主流分析场景，分析时自动调用对应技能的参数和模板，不是从零写代码。\n"
            "> \n"
            "> **铁轨审查机制**：每个分析步骤前后自动审查——环境检查 → 缺失包安装 → 参数校验 → 结果质量评估 → 图表检查 → 代码审查。不通过则阻断纠正，不会带着错误继续往下跑。\n"
            "> \n"
            "> **知识库驱动**：内置生信知识库（物种/组织/方向三维索引），分析时自动检索相关生物学背景，结合文献先验知识做注释和解读。\n"
            "> \n"
            "> **结果管理**：分析结果按 `results/<模块>/<方法>/{figures,results,scripts,data}` 分目录存储，每次分析可追溯、可复现。\n"
            "> \n"
            "> 有什么需要帮忙的，直接告诉我！"
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
            return red_prefix + "\n".join(lines)
        # Detect paper-writing sub-intent
        lit_text = user_text if zh else user_text.lower()
        paper_write_kw = ["写论文", "写文章", "论文写作", "写一篇", "manuscript", "paper writing",
                         "write a paper", "draft a paper", "帮我写", "投稿", "学术论文"]
        paper_research_kw = ["研究方案", "实验设计", "方案设计", "设计实验", "研究计划",
                            "research plan", "research proposal", "技术路线"]
        if any(kw in lit_text for kw in paper_write_kw):
            lines.append("论文写作任务。调用 skill_view('academic-paper-writing')，"
                        "按 12-agent pipeline 生成论文。" if zh else
                        "Paper writing. Call skill_view('academic-paper-writing').")
        elif any(kw in lit_text for kw in paper_research_kw):
            lines.append("研究方案设计。调用 skill_view('research-plan')，"
                        "生成含 Mermaid 技术路线图的完整方案。" if zh else
                        "Research plan. Call skill_view('research-plan').")
        else:
            lines.append("文献任务。调用 skill_search('文献') 或 skill_view('pubmed-search')。PDF保存到 work/papers/" if zh else
                         "Literature task. Use skill_search('literature') or skill_view('pubmed-search').")
    
    elif intent == "knowledge":
        lines.append("知识库查询。使用 search_knowledge_base 检索已有知识和经验。" if zh else
                     "Knowledge query. Use search_knowledge_base.")
    
    return red_prefix + "\n".join(lines)


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
        "intro_reasoning": "用户询问系统身份，触发自我介绍快速回复模板，无需调用 LLM。",
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
        "intro_reasoning": "User asked about system identity. Self-introduction fast-reply template triggered, no LLM call needed.",
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


def _inject_anchors(session, text):
    """每轮注入 历史记忆召回 + 会话锚点摘要（跨压缩持久，2026-08-14）。"""
    _parts = []
    try:
        _facts = _recall_facts(text or "")
        if _facts:
            _parts.append(_facts)
    except Exception:
        pass
    try:
        from memomics.bio_tools import session_memory as _sm
        _block = _sm.build_digest(session.get("id", ""), max_items=12, max_chars=700)
        if _block:
            _parts.append(_block)
    except Exception:
        pass
    if not _parts:
        return text
    return "\n\n".join(_parts) + "\n\n" + (text or "")


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
        enabled_toolsets=["terminal", "file", "code_execution", "memomics", "todo", "memory", "skills", "web", "computer_use", "cronjob", "delegation", "image_gen", "session_search", "browser"],
        ephemeral_system_prompt=skills_index + _PLANNING_PROMPT,
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
    set_session_context(sid=sid, results_dir=new_dir.replace("\\", "/"))
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
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {cfg['api_key']}"},
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
        total = len(session["messages"]) if session.get("_messages_loaded") else int(session.get("_msg_count") or 0)
    else:
        # 显示全部：加载完整历史
        _ensure_session_messages_loaded(session)
        msgs = session.get("messages") or []
        total = len(msgs)
    normalized = []
    for m in msgs:
        nm = dict(m)
        if "content" not in nm and "text" in nm:
            nm["content"] = nm["text"]
        normalized.append(nm)
    return {"messages": normalized, "total": total}


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
    """删除会话：内存 + state.db + agent 资源（真正杀死 agent）"""
    session = _sessions.get(sid)
    if session:
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
    # 注：结果目录（results/{sid}/ 分析产出）按用户要求保留，不删除
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
    return {"ok": True}


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
    cfg["has_key"] = bool(cfg.get("api_key"))
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
            "has_key": bool(saved.get("api_key")),
            "is_custom": p["id"] == "dcs-cloud",
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
            for p in _CHINA_PROVIDERS:
                saved = _provider_keys.get(p["id"])
                if saved and saved.get("api_key"):
                    existing[p["id"]] = {
                        "id": p["id"], "name": p["name"],
                        "api_base": saved.get("base_url") or p["api"],
                        "api_key": saved["api_key"],
                        "models": p.get("models", []),
                    }
        elif pid in _provider_keys and _provider_keys[pid].get("api_key"):
            p = _PROVIDERS_INDEX.get(pid) or {}
            saved = _provider_keys[pid]
            existing[pid] = {
                "id": pid, "name": p.get("name", pid),
                "api_base": saved.get("base_url") or p.get("api", ""),
                "api_key": saved["api_key"],
                "models": p.get("models", []),
            }
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
                     capture_output=True, text=True, timeout=3)
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


# === 首次启动 / 环境检测 ===

@app.get("/api/setup/status")
async def setup_status():
    """检查是否需要首次配置"""
    needs_config = not _current_model.get("api_key") or not _current_model.get("base_url") or not _current_model.get("model")
    return {
        "needs_config": needs_config,
        "current": {
            "provider": _current_model.get("provider", "openai"),
            "base_url": _current_model.get("base_url", ""),
            "model": _current_model.get("model", ""),
            "has_key": bool(_current_model.get("api_key")),
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
            rv = _sp.run(["Rscript", "-e", "cat(R.version$major, R.version$minor, sep='.')"], capture_output=True, text=True, timeout=10)
            result["r"]["version"] = rv.stdout.strip()
            result["r"]["ok"] = True
        except Exception:
            result["r"]["ok"] = False
    else:
        result["r"]["ok"] = False
    try:
        gpu = shutil.which("nvidia-smi")
        if gpu:
            gv = _sp.run([gpu, "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True, timeout=10)
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
    print(f"[MemOmics] 微信新会话: {sender_name} → {session["id"]}", flush=True)
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

    # === 自我介绍快速回复（绕过 agent LLM，与 WebUI 路径对齐）===
    # 2026-08-14: 微信路径此前缺 self_intro 快回 → 模型限流时"你是谁"永远无回复
    try:
        _wx_intent, _wx_conf, _wx_extra = _classify_intent(text)
    except Exception:
        _wx_intent = "chat"
    if _wx_intent == "self_intro":
        _intro = _SELF_INTRO_EN if session.get("lang") == "en" else _SELF_INTRO_ZH
        session["messages"].append({"role": "assistant", "content": _intro, "time": datetime.now().strftime("%H:%M:%S"), "source": "weixin-agent"})
        if len(session["messages"]) > 200:
            session["messages"] = session["messages"][-200:]
        session["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session["running_agent"] = False
        session["running_task"] = None
        _persist_session_message(session, "assistant", _intro)
        _session_emit(session, {"type": "delta", "content": _intro, "session_id": sid})
        _session_emit(session, {"type": "complete", "content": _intro, "session_id": sid})
        _session_emit(session, {"type": "progress", "step": "complete", "status": "done", "detail": "回复已生成", "ts": datetime.now().strftime("%H:%M:%S"), "session_id": sid})
        wx_msg = {"id": str(int(time.time() * 1000)), "sender_id": _weixin_state["account_id"], "sender_name": "Agent", "text": _intro, "context_token": "", "ts": int(time.time()), "direction": "out"}
        _append_weixin_msg(wx_msg)
        for ws_client in list(_WEIXIN_WS_CLIENTS):
            try:
                await ws_client.send_text(json.dumps({"type": "weixin_message", "message": wx_msg}, ensure_ascii=False))
            except Exception:
                pass
        if _weixin_adapter:
            try:
                send_result = await _send_weixin_important(_intro, chat_id_override=sender_id)
                print(f"[MemOmics] 微信Agent回复(自介快回): success={send_result}", flush=True)
            except Exception as e:
                print(f"[MemOmics] 微信自介回复发送失败: {e}", flush=True)
        return

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

        def _wx_tool_complete_cb(tool_name, result_str=""):
            _session_emit(session, {"type": "tool_complete", "tool": tool_name, "result": result_str[:500], "ts": datetime.now().strftime("%H:%M:%S"), "session_id": sid})
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
                set_session_context(sid=session["id"], results_dir=session.get("results_dir", ""))
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

    def _pdf_count(d: str) -> int:
        """递归统计目录下 PDF 数量（上限 2000，防超深目录拖慢浏览）。"""
        n = 0
        try:
            for _root, _dirs, _files in os.walk(d):
                _dirs[:] = [x for x in _dirs if not x.startswith(".")]
                for _f in _files:
                    if _f.lower().endswith(".pdf"):
                        n += 1
                        if n >= 2000:
                            return n
        except Exception:
            pass
        return n

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
                    "pdf_count": _pdf_count(root_dir)}
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
        for p in sorted(Path(real).iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name.startswith(".") or p.name in ("$RECYCLE.BIN", "System Volume Information", "__pycache__"):
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
        return {"path": real.replace("\\", "/"), "items": items, "is_root": False,
                "parent": parent, "platform": os.name, "pdf_count": _pdf_count(real)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    """读取文件内容（限制在 work/results/项目内，防任意文件读取）"""
    try:
        from webui.security import resolve_within_roots, UnsafePathError
        _p = resolve_within_roots(path, [WORK_DIR, RESULTS_DIR, MEMOMICS_DIR])
        path = str(_p)
        size = os.path.getsize(path)
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read(200000)  # 最多 200KB
        return {"path": path, "content": content, "size": size, "truncated": size > 200000}
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
    try:
        import subprocess
        index_script = os.path.join(HERMES_DIR, "tools", "build_skill_index.py")
        if os.path.exists(index_script):
            subprocess.run([sys.executable, index_script], capture_output=True, timeout=30)
            print(f"[MemOmics] Auto-rebuilt skill index after creating {safe_name}", flush=True)
    except Exception as e:
        print(f"[MemOmics] Auto-rebuild index failed (non-fatal): {e}", flush=True)

    return {"ok": True, "name": safe_name, "path": skill_dir, "scripts": list(req.scripts.keys())}


# --- 分析结果 ---

@app.get("/api/results/{sid}")
@app.get("/api/results/{sid}")
async def list_results(sid: str, path: str = ""):
    """列出会话分析结果目录（每次实时扫描磁盘，不用缓存）"""
    # 每次都扫描磁盘，不依赖内存中的 results_dir
    base = _find_best_results_dir(sid)
    if not base and sid in _sessions:
        base = _sessions[sid]["results_dir"]
    if not base:
        base = os.path.join(RESULTS_DIR, sid)
    if not os.path.isdir(base) or not any(Path(base).iterdir()):
        return {"items": [], "path": base, "note": "该会话尚未产生分析结果。开始分析后，结果将自动存储到此处。", "base": base.replace("\\", "/")}
    # 同步更新内存
    if sid in _sessions and os.path.abspath(_sessions[sid].get("results_dir","")) != os.path.abspath(base):
        _sessions[sid]["results_dir"] = base
    target = os.path.join(base, path) if path else base
    if not os.path.isdir(target):
        return {"items": [], "path": target, "note": "该会话尚未产生分析结果。开始分析后，结果将自动存储到此处。", "base": base.replace("\\", "/")}
    items = []
    try:
        for p in sorted(Path(target).iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name.startswith("."):
                continue
            _st = p.stat()
            items.append({
                "name": p.name,
                "path": str(p).replace("\\", "/"),
                "is_dir": p.is_dir(),
                "size": _st.st_size if p.is_file() else 0,
                "ext": p.suffix.lower() if p.is_file() else "",
                "rel_path": str(p.relative_to(base)).replace("\\", "/"),
                "mtime": _st.st_mtime,
                "mtime_str": datetime.fromtimestamp(_st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })
        return JSONResponse({"items": items, "path": target.replace("\\", "/"), "base": base.replace("\\", "/"), "session_id": sid, "results_name": os.path.basename(base),
                "manifest": _load_result_manifest(base), "manifest_versions": _list_manifest_versions(base)},
                headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


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
            _r = _sp.run(["git", "rev-parse", "--short", "HEAD"], cwd=MEMOMICS_DIR, capture_output=True, text=True, timeout=3)
            _d = _sp.run(["git", "status", "--porcelain"], cwd=MEMOMICS_DIR, capture_output=True, text=True, timeout=3)
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


@app.get("/api/results/{sid}/figures")
async def list_figures(sid: str):
    """列出会话所有 figures（递归扫描 png/jpg/svg/pdf）"""
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
        for p in sorted(Path(base).rglob("*"), key=lambda x: x.stat().st_mtime if x.exists() else 0):
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
    return JSONResponse({"figures": figures, "base": base.replace("\\", "/"), "session_id": sid},
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


# --- 待办 ---

@app.get("/api/todos/{sid}")
async def get_todos(sid: str):
    """获取会话待办"""
    if sid not in _sessions:
        _restore_single_session(sid)
    if sid not in _sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return {"todos": _sessions[sid].get("todos", [])}

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
        "is_running": bool(session.get("running_agent") or session.get("running_task")),
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

# 记忆文件限额（与 hermes_home/config.yaml memory 段保持一致）
_MEMORY_CHAR_LIMITS = {"USER.md": 10000, "MEMORY.md": 10000}


@app.post("/api/memory/govern")
async def memory_govern():
    """记忆治理：重新扫描打分并生成索引（2026-08-14）。

    只读操作（不迁移条目）——L1/L2/L3 实际流转需显式 apply 才执行。"""
    try:
        from memomics.memory_governance import governor
        idx = governor.init_index(verbose=False)
        return {"ok": True, "stats": idx["stats"], "total": sum(idx["stats"].values())}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/memory")
async def get_memory():
    """读取外置记忆内容（响应携带写 API token，供同源页面使用）"""
    mem_dir = os.path.join(HERMES_HOME_DIR, "memories")
    result = {"entries": [], "api_token": _memory_api_token()}
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
    # 限额检查（防记忆无限膨胀，对齐 MemoryStore char limit）
    _limit = _MEMORY_CHAR_LIMITS.get(os.path.basename(target), 10000)
    _existing = ""
    if mode != "overwrite" and os.path.exists(file_path):
        with open(file_path, encoding="utf-8", errors="replace") as f:
            _existing = f.read()
    _new_total = len((_existing + "\n\n" + content) if _existing else content)
    if _new_total > _limit:
        return JSONResponse({
            "error": f"超出记忆限额：{_new_total}/{_limit} 字符。请先删除/压缩旧条目再写入。",
            "current": len(_existing), "limit": _limit,
        }, status_code=413)
    if mode == "overwrite":
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
    else:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write("\n\n" + content)
    return {"ok": True, "path": file_path.replace("\\", "/"), "size": os.path.getsize(file_path)}


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
                session["_real_exec_this_turn"] = False  # 本回合是否有代码真实执行(被护栏跳过的调用不算)
                session["_tool_dedup"] = {}  # 每轮用户消息重置重复执行拦截:用户反复重跑相同代码是合法的
                session["_live_tool"] = ""
                session["_live_tool_ts"] = time.time()
                session["_proc_hist"] = []  # 2026-08-16: 进程采样历史（回合级窗口）
                session["_stall_notice_last"] = 0
                session["_turn_activity_ts"] = time.time()
                # 如果有图片，将图片 URL 作为上下文附加到用户消息中
                if image_urls:
                    img_context = "\n\n[用户上传的图片]\n" + "\n".join(f"![]({url})" for url in image_urls)
                    user_text = (user_text or "查看图片") + img_context

                # 问题9: 检测用户语言并更新会话语言
                detected_lang = _detect_lang(user_text)
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
                _run_text = _inject_anchors(session, user_text)

                # 惰性加载：继续旧会话前，先把完整历史载入内存（保证上下文构建/追加正确）
                _ensure_session_messages_loaded(session)

                # 记录用户消息到 session + state.db
                session["messages"].append({"role": "user", "content": user_text, "time": datetime.now().strftime("%H:%M:%S")})
                session["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # state.db 持久化由 Hermes 框架 _persist_session 自动完成（agent 带 session_db），
                # 手动写入会双写（2026-08-13 实测同秒重复 2 份 → 刷新后回复重复显示）

                # RunGate（P1-A 接线，2026-08-12）：用户主动发消息 = 新指令 →
                # 退役任务（done/cancelled）重置为 pending（命中"继续"词表由 check_gate 内部处理；
                # 未命中返回 ask_user → 用户发消息本身即新指令，保守重置为新任务）
                try:
                    from webui.runtime.run_gate import check_gate, save_state
                    _rd_g = session.get("results_dir", "") or ""
                    if _rd_g:
                        _verdict, _reason = check_gate(_rd_g, is_auto_wake=False, user_message=user_text)
                        if _verdict == "ask_user":
                            save_state(_rd_g, "pending", "user message (ask_user -> new task)")
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
                    _ss.extract_assets(session["id"], user_text)

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
                # 未命中 → chat 返回空字符串，self_intro 由下方快速回复处理）
                if _intent == "self_intro":
                    _skill_ctx = None
                else:
                    _skill_ctx = _build_skill_injection(_intent, domain or session.get("domain", ""), session.get("lang", "zh"), user_text)
                logger.info(f"Session {session['id']}: intent={_intent} conf={_intent_conf:.2f} domain={domain or session.get('domain','')}")

                # === 自我介绍快速回复（绕过 agent LLM）===
                if _intent == "self_intro":
                    _intro_zh = (
                        "我是 **MemOmics**，基于 Hermes 框架的自进化多组学生信分析平台。\n\n"
                        "我不是聊天机器人，而是能帮你**跑完完整生信分析**的自主 Agent。给我数据，我自己扫描、分析、出报告，你不用写一行代码。\n\n"
                        "## 核心能力\n\n"
                        "**数据扫描**：自动识别 scRNA-seq / scATAC-seq / 空间转录组 / Bulk RNA-seq 等数据格式，检测物种、组织、细胞数、注释状态，推荐最佳分析路径。\n\n"
                        "**完整分析流程**：QC（去污染→双胞过滤→归一化）→ 降维 → 聚类 → 细胞注释 → 差异表达 → 通路富集 → 细胞通讯 → 轨迹推断 → SCENIC 转录因子调控 → 生存分析 → 报告生成，全流程自动走完。\n\n"
                        "**R + Python 双引擎**：根据数据规模智能推荐——大于 60 万细胞自动切换 Python/Scanpy，默认用 R/Seurat。缺包时自动安装（BiocManager/remotes/pip/conda），不用你操心环境。\n\n"
                        "**内置 270+ 生信技能模板**：Seurat、Scanpy、CellChat、Monocle3、SCENIC、CellBender、Harmony、squidpy 等覆盖主流分析场景，分析时自动调用对应技能的参数和模板，不是从零写代码。\n\n"
                        "**铁轨审查机制**：每个分析步骤前后自动审查——环境检查 → 缺失包安装 → 参数校验 → 结果质量评估 → 图表检查 → 代码审查。不通过则阻断纠正，不会带着错误继续往下跑。\n\n"
                        "**知识库驱动**：内置生信知识库（物种/组织/方向三维索引），分析时自动检索相关生物学背景，结合文献先验知识做注释和解读。\n\n"
                        "**结果管理**：分析结果按 `results/<模块>/<方法>/{figures,results,scripts,data}` 分目录存储，每次分析可追溯、可复现。\n\n"
                        "有什么需要帮忙的，直接告诉我！"
                    )
                    _intro_en = (
                        "I'm **MemOmics**, a self-evolving multi-omics bioinformatics analysis platform powered by the Hermes framework.\n\n"
                        "I'm not a chatbot — I'm an autonomous Agent that can run complete bioinformatics analyses for you. Give me your data, and I'll scan, analyze, and generate reports. You don't need to write a single line of code.\n\n"
                        "## Core Capabilities\n\n"
                        "**Data Scanning**: Automatically identifies scRNA-seq / scATAC-seq / Spatial Transcriptomics / Bulk RNA-seq formats, detecting species, tissue, cell count, and annotation status to recommend optimal analysis paths.\n\n"
                        "**Complete Analysis Pipeline**: QC (decontamination → doublet filtering → normalization) → Dimensionality Reduction → Clustering → Cell Annotation → Differential Expression → Pathway Enrichment → Cell Communication → Trajectory Inference → SCENIC TF Regulation → Survival Analysis → Report Generation — fully automated.\n\n"
                        "**R + Python Dual Engine**: Intelligently selects R/Seurat by default, auto-switches to Python/Scanpy for datasets >600K cells. Auto-installs missing packages (BiocManager/remotes/pip/conda).\n\n"
                        "**270+ Built-in Bioinformatics Skill Templates**: Seurat, Scanpy, CellChat, Monocle3, SCENIC, CellBender, Harmony, squidpy covering mainstream analysis scenarios. Skills are called with proper parameters — never writing code from scratch.\n\n"
                        "**Rail Review Mechanism**: Each analysis step undergoes pre/post review — environment check → missing package install → parameter validation → result quality assessment → figure inspection → code review. Blocked and corrected if anything fails.\n\n"
                        "**Knowledge Base Driven**: Built-in bioinformatics knowledge base (species/tissue/direction 3D index) for automatic biological context retrieval, combining literature priors for annotation and interpretation.\n\n"
                        "**Result Management**: Results stored under `results/<module>/<method>/{figures,results,scripts,data}` — traceable and reproducible for every analysis.\n\n"
                        "What can I help you with? Just let me know!"
                    )
                    _intro = _intro_en if session.get("lang") == "en" else _intro_zh
                    session["messages"].append({"role": "assistant", "content": _intro, "time": datetime.now().strftime("%H:%M:%S")})
                    session["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    _persist_session_message(session, "assistant", _intro)
                    await ws.send_text(json.dumps({"type": "session", "session_id": session["id"], "title": session["title"]}, ensure_ascii=False))
                    await ws.send_text(json.dumps({"type": "thinking", "content": _pt(session, "understanding") + "...", "session_id": session["id"]}, ensure_ascii=False))
                    await ws.send_text(json.dumps({"type": "progress", "step": _pt(session, "thinking"), "status": "pending", "detail": _pt(session, "understanding"), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False))
                    await asyncio.sleep(1.0)  # 让前端有时间渲染思考状态
                    await ws.send_text(json.dumps({"type": "progress", "step": _pt(session, "thinking"), "status": "done", "detail": _pt(session, "completed"), "ts": datetime.now().strftime("%H:%M:%S"), "session_id": session["id"]}, ensure_ascii=False))
                    await ws.send_text(json.dumps({"type": "reasoning", "content": _pt(session, "intro_reasoning"), "session_id": session["id"]}, ensure_ascii=False))
                    await ws.send_text(json.dumps({"type": "delta", "content": _intro, "session_id": session["id"]}, ensure_ascii=False))
                    await ws.send_text(json.dumps({"type": "complete", "content": _intro, "session_id": session["id"]}, ensure_ascii=False))
                    continue  # 跳过 agent 调用

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
                set_session_context(sid=session["id"], results_dir=session.get("results_dir", ""))
                # 注意：不再写 os.environ，多会话并发时 os.environ 会串会话

                # 注入 results_dir 到 Agent 系统提示词，确保输出文件写到正确位置
                rd = session.get("results_dir", "")
                # 🔧 按意图裁剪 system prompt：
                #   无数据路径 → SOUL.md only (~15KB) 轻量响应
                #   有数据路径 + 分析执行 → SOUL.md + detail + skills_index + PLANNING
                import re as _re_path
                _has_data_path = bool(_re_path.search(r'[A-Za-z]:[/\\]\S+', user_text)) if user_text else False
                # 轻量意图：永远不注入 SOUL-detail + skills_index（省 40%+ 上下文）
                _LIGHT_INTENTS = ("chat", "self_intro", "knowledge_ask", "progress_check", "analysis_plan", "cancel_task")
                # 重量意图：仅 explicit execution 或 analysis + 数据路径 + 执行关键词
                _has_exec_kw = any(kw in user_text for kw in
                    ("跑", "执行", "开始", "启动", "运行", "run", "start", "execute", "analyze")) if user_text else False
                _is_explicit_exec = _intent in ("analysis_exec", "direct_exec")
                _is_heavy = _is_explicit_exec or (
                    _intent not in _LIGHT_INTENTS
                    and _has_data_path
                    and _has_exec_kw
                )
                if not _is_heavy:
                    # 轻量：闲聊/知识/进度/无数据路径的分析讨论 → 不注入 skills 和 detail
                    agent.ephemeral_system_prompt = (
                        f"\n\n## 当前会话输出目录\n所有 R/Python/终端脚本的输出文件（图片、表格、报告）请保存到：\n`{rd.replace(chr(92), '/')}`\n请使用绝对路径或在脚本开头 `setwd()` / `os.chdir()` 到此目录。"
                        if rd else ""
                    )
                else:
                    # 重量：有数据路径 + 分析执行 → 注入全量
                    _soul_detail = ""
                    try:
                        _detail_path = os.path.join(HERMES_HOME_DIR, "SOUL-detail.md")
                        if os.path.isfile(_detail_path):
                            with open(_detail_path, encoding="utf-8") as _f:
                                _soul_detail = _f.read()
                    except Exception:
                        pass
                    _skills = _read_skills_index()
                    agent.ephemeral_system_prompt = _soul_detail + "\n\n" + _skills + _PLANNING_PROMPT
                    if rd:
                        agent.ephemeral_system_prompt += f"\n\n## 当前会话输出目录\n所有 R/Python/终端脚本的输出文件（图片、表格、报告）请保存到：\n`{rd.replace(chr(92), '/')}`\n请使用绝对路径或在脚本开头 `setwd()` / `os.chdir()` 到此目录。"

                    # 🔧 分析任务自动预查知识库 + 方法路线引导
                    _kb_result = _auto_search_knowledge(user_text)
                    if _kb_result and '"total": 0' not in _kb_result.split('\n')[0] if _kb_result else False:
                        # KB 有匹配 → 注入背景知识
                        agent.ephemeral_system_prompt += (
                            "\n\n## 📚 知识库预查询（线索，非文献来源）\n"
                            "以下是系统自动从知识库检索的内容，**仅作为分析线索和背景参考**。\n"
                            "⚠️ KB 中的文献引用可能缺少 PMID/DOI，**不可直接作为辩论引用来源**。\n\n"
                            "**铁律 5 强制要求**：\n"
                            "1. 辩论前必须先调 `search_papers()` 获取带 PMID/DOI 的真实文献\n"
                            "2. KB 内容作为 `knowledge_base_info` 传入辩论，提供生物学背景\n"
                            "3. 辩论中**只能引用 search_papers 返回的真实文献**\n\n"
                            + _kb_result
                        )
                    elif _intent in ("analysis", "research_plan", "analysis_plan"):
                        # KB 无匹配 → 引导使用 skill 体系构建分析路线
                        # 🔑 关键：限定领域，不让 RNA 问题搜到空间组
                        _detected_domain = _detect_domain_from_text(user_text)
                        _domain_hint = f"（系统推断领域: {_detected_domain}）" if _detected_domain else ""
                        _domain_list = f"skill_list_by_domain(domain=\"{_detected_domain}\")" if _detected_domain else "skill_list_by_domain(domain=<推断的领域>)"
                        agent.ephemeral_system_prompt += (
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
                        _session_emit(_s, {"type": "tool_complete", "tool": tool_name, "result": result_str[:500], "ts": datetime.now().strftime("%H:%M:%S"), "session_id": _s["id"]})
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
                                        shell=True, capture_output=True, text=True, timeout=10)
                                    _gpu = _check.stdout.strip()
                                    _check2 = subprocess.run("tasklist | findstr cellbender",
                                        shell=True, capture_output=True, text=True, timeout=5)
                                    _proc = _check2.stdout.strip()
                                    _failed = ("0 %" in _gpu and not _proc)
                                else:
                                    _gpu = ""
                                    _check = subprocess.run("nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader",
                                        shell=True, capture_output=True, text=True, timeout=5)
                                    if _check.returncode == 0:
                                        _gpu = _check.stdout.strip()
                                    _check2 = subprocess.run("ps -ef | grep -E 'cellbender|rscript|python' | grep -v grep",
                                        shell=True, capture_output=True, text=True, timeout=5)
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
                            _db_path = os.path.join(HERMES_HOME_DIR, "state.db")
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
                                    # 用户指定的分析目录（如 PROJECT_DATA_DIR）
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

                        # 🔧 长任务记忆锚点 + 强制执行指令（合并为一条，避免被稀释）
                        _plan_ctx = _build_task_plan_context(_session) if not _new_data_task else None
                        if _plan_ctx:
                            # 把所有关键指令合并成一条 system 消息
                            _merged = (
                                _plan_ctx + "\n\n"
                                "⛔⛔⛔ 最高优先级指令 ⛔⛔⛔\n"
                                "你当前有 task_plan.md，正在执行分析任务。请严格遵守：\n"
                                "1. 你的下一句话必须是一个工具调用（terminal/write_file/skill_view），不是文字。\n"
                                "2. 说'启动'→调 terminal。说'写脚本'→调 write_file。说'检查'→调 terminal 执行命令。\n"
                                "3. 禁止先输出大段文字再调工具。工具调用必须在文字之前。\n"
                                "4. CellBender/训练/长时间命令必须 terminal(background=True, notify_on_complete=True)。\n"
                                "5. 如果 task_plan 的 Phase 描述模糊，直接用你的判断补充具体步骤并执行。不要等用户确认。"
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
                                set_session_context(sid=_session["id"], results_dir=_session.get("results_dir", ""))
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
                            try:
                                # 绝对超时防护：Windows 上 ssl 握手被网关挂起时
                                # connect/read 超时可能失效，线程永久卡死。
                                # 15 分钟上限 → 超时中断 agent 并报错（daemon 线程
                                # 泄漏不阻塞进程，但避免任务永久挂起）。
                                result = await asyncio.wait_for(
                                    loop.run_in_executor(None, _do_run),
                                    timeout=900
                                )
                            except asyncio.TimeoutError:
                                try:
                                    if hasattr(_agent, "interrupt"):
                                        _agent.interrupt()
                                except Exception:
                                    pass
                                result = ""
                                _session_emit(_session, {"type": "error", "content": "AI 响应超时（15 分钟）。网关连接可能被挂起，请重试或切换模型。", "session_id": _session["id"]})

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
                        try:
                            todos = _agent.get_todos() if hasattr(_agent, "get_todos") else []
                            if todos:
                                _session["todos"] = todos if isinstance(todos, list) else []
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
                        _schedule_self_check(_session, _agent, loop)
                        # state.db 已在运行中实时持久化，无需额外快照

                # 前台/后台均不阻塞 WebSocket 循环，以便接收 cancel 消息
                # 任务账本 + 资源租约 + Job Object 硬限制（借鉴重构版）
                if _task_supervisor.is_running(session["id"]):
                    _session_emit(session, {"type": "info", "content": "该会话已有任务在运行，请先发送取消后再试", "session_id": session["id"]})
                else:
                    session["running_agent"] = agent
                    _res_req = _session_resource_request(session)
                    try:
                        _lease = await asyncio.wait_for(_resource_scheduler.acquire(session["id"], _res_req), timeout=60)
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
