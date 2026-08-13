"""execute_r — R 代码执行工具，带 SCTransform 铁轨 + OOM 自动修复。

从 MemOmics 老版迁移核心逻辑，适配 hermes registry 格式。
"""
import json
import os
import re
import subprocess
import tempfile
import logging

logger = logging.getLogger(__name__)

SCHEMA = {
    "name": "execute_r",
    "description": (
        "Execute R code with SCTransform guardrails and OOM auto-retry. "
        "Automatically injects conserve.memory=TRUE, plan('sequential'), "
        "workers=1 for SCTransform calls. Detects OOM and retries with "
        "stricter memory settings. Use for Seurat/CellChat/monocle3/SCENIC "
        "analysis. Returns stdout + stderr (truncated to 15000 chars)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "R code to execute"
            },
            "working_dir": {
                "type": "string",
                "description": "Working directory (optional)",
                "default": ""
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (30-900, default 600)",
                "default": 600
            }
        },
        "required": ["code"]
    }
}


def _ensure_win_env(env: dict) -> dict:
    """Fix Windows subprocess env (STATUS_DLL_INIT_FAILED root cause)."""
    if os.name != 'nt':
        return env
    if not env.get('SystemRoot'):
        for c in (r'C:\WINDOWS', r'C:\Windows'):
            if os.path.isdir(c):
                env['SystemRoot'] = c
                break
    if not env.get('ComSpec'):
        for c in (r'C:\WINDOWS\system32\cmd.exe', r'C:\Windows\System32\cmd.exe'):
            if os.path.isfile(c):
                env['ComSpec'] = c
                break
    if not env.get('R_HOME'):
        import shutil
        rscript = shutil.which('Rscript')
        if rscript:
            r_home = os.path.dirname(os.path.dirname(rscript))
            if os.path.isdir(r_home):
                env['R_HOME'] = r_home
        if not env.get('R_HOME'):
            for c in (r'C:\Program Files\R', r'D:\R', r'C:\R'):
                if os.path.isdir(c):
                    # 找到最新版本
                    for sub in sorted(os.listdir(c), reverse=True):
                        if sub.startswith('R-'):
                            env['R_HOME'] = os.path.join(c, sub)
                            break
                if env.get('R_HOME'):
                    break
    return env


def _kill_process_group(proc):
    """Kill process and entire process tree."""
    try:
        if proc.poll() is not None:
            return
    except Exception:
        return
    try:
        if os.name == 'nt':
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, timeout=10)
        else:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        pass


def _apply_sct_rail(code: str):
    """SCTransform 铁轨: 强制 workers=1 + sequential + conserve.memory.

    P1-6(2026-08-13): 返回 (code, changes) — 改写不再静默，
    变更明细随执行结果返回给 agent（之前 agent 不知道自己代码被改）。
    """
    changes = []
    _new = re.sub(r'plan\s*\(\s*"multisession"[^)]*\)', 'plan("sequential")', code)
    if _new != code:
        changes.append('plan("multisession")→plan("sequential")')
        code = _new
    _new = re.sub(r'plan\s*\(\s*"multicore"[^)]*\)', 'plan("sequential")', code)
    if _new != code:
        changes.append('plan("multicore")→plan("sequential")')
        code = _new
    if 'SCTransform' in code:
        if 'glmGamPoi' not in code and 'method' not in code:
            code = code.replace('SCTransform(',
                                'SCTransform(method="glmGamPoi", conserve.memory=TRUE, ', 1)
            changes.append('SCTransform 注入 method="glmGamPoi" + conserve.memory=TRUE')
        elif 'conserve.memory' not in code:
            code = code.replace('SCTransform(',
                                'SCTransform(conserve.memory=TRUE, ', 1)
            changes.append('SCTransform 注入 conserve.memory=TRUE')
    _new = re.sub(r'workers\s*=\s*\d+', 'workers=1', code)
    if _new != code:
        changes.append('workers=N→workers=1')
        code = _new
    return code, changes


def _session_task_id(task_id: str) -> str:
    """P1-13(2026-08-13): kernel 隔离键 — 会话识别，防跨会话 kernel 污染。

    优先级：显式 task_id 参数 > 线程级会话上下文（set_session_context，由
    server.py 在 executor 线程入口设置）> MEMOMICS_SESSION_ID 环境变量 > "default"。
    每个会话拿到自己的 sid 作为 kernel 键 → 变量/已加载包互不串染，
    会话回访还能命中自己的热 worker（LRU 2 个/30min 空闲）。
    """
    if task_id:
        return str(task_id)
    try:
        from memomics.bio_tools.debate_analysis import get_session_sid
        _sid = get_session_sid()
        if _sid:
            return _sid
    except Exception:
        pass
    return os.environ.get("MEMOMICS_SESSION_ID") or "default"


def execute_r(code: str, working_dir: str = "", timeout: int = 600, task_id: str = "") -> str:
    """Execute R code with OOM detection and auto-retry.

    P0-1 持久 kernel 优先：跨调用保留变量/已加载包（热调用免解释器启动
    + 包加载，Seurat/ArchR 类 2000x+）；持久不可用/报错时回退
    每次 Rscript 新进程（保留 OOM 检测 + 自动重试 + SCTransform 特判）。

    P0-3(2026-08-13) 失败语义：返回结构化 JSON（对齐 code_execution_tool），
    status ∈ success/error/timeout，含 exit_code/error 字段；output 字段保留
    纯文本（含 [STDERR]/[Exit code] 标记）兼容既有文本消费方。
    """
    timeout = min(max(int(timeout), 30), 900)

    _sct_changes = []
    if 'SCTransform' in code:
        code, _sct_changes = _apply_sct_rail(code)
    _sct_note = ("" if not _sct_changes else
                 "[SCTransform铁轨] 代码已自动调整: " + "; ".join(_sct_changes) + chr(10))

    # ── 沙箱探测：degraded 模式写白名单外路径直接拒绝 ──
    # P1-7(2026-08-13): 探测异常时 fail-open 但显式告警（原注释误导称 fail-closed）
    try:
        from tools.sandbox_probe import probe_sandbox_capability, is_write_path_allowed
        import re as _re
        _write_re = _re.compile(
            r"""(?:write\.csv|write\.table|write\.rds|write\.tsv|saveRDS|ggsave|pdf|png|jpeg|tiff|bmp|writeLines|save)\s*\([^)]*?["']([^"']+)["']""")
        _probe = probe_sandbox_capability()
        if _probe.get("degraded"):
            _violations = []
            for _m in _write_re.finditer(code):
                _p = _m.group(1).strip()
                if _p and not is_write_path_allowed(_p):
                    _violations.append(_p)
            if _violations:
                _msg = (f"Error: 沙箱 degraded 模式：写入白名单外路径被拒绝: {_violations[:3]}. "
                        "配置 MEMOMICS_ALLOWED_WRITE_ROOTS 可放行特定目录。")
                return json.dumps({"status": "error", "output": _msg, "error": _msg,
                                   "exit_code": 1}, ensure_ascii=False)
    except Exception as _probe_err:
        logger.warning("sandbox probe failed, write restrictions NOT enforced (fail-open): %s", _probe_err)

    # ── P0-1 持久 kernel 优先（状态保持 + 免包加载） ──
    try:
        from tools.persistent_kernel import KERNEL_POOL
        _res = KERNEL_POOL.execute(
            code,
            _session_task_id(task_id),
            timeout=min(timeout, 600), language="r",
            cwd=working_dir or None)  # P1-5: working_dir 接线（不再被 kernel 丢弃）
        if _res.get("status") == "ok":
            _out = _sct_note + ((_res.get("output", "") or "(no output)")[:15000])
            return json.dumps({"status": "success", "output": _out, "exit_code": 0,
                               "mode": "persistent_kernel"}, ensure_ascii=False)
        if _res.get("status") == "timeout":
            _msg = f"Error: R execution timed out after {timeout}s. Kernel killed; next call starts fresh."
            return json.dumps({"status": "timeout", "output": _sct_note + _msg, "error": _msg,
                               "exit_code": None}, ensure_ascii=False)
        # status == error → 分类处理（P1-4 修复，2026-08-13：防副作用双跑）
        _err = _res.get("error", "unknown kernel error")
        _infra_fail = ("worker died unexpectedly" in _err) or ("worker write failed" in _err)
        if _infra_fail:
            # 基础设施失败（worker 启动即死/管道断裂）：代码大概率未送达 →
            # 回退 Rscript 重跑相对安全；记录原因避免静默失败。
            logger.warning("persistent kernel R infra failure, falling back to fresh Rscript: %s", _err)
        else:
            # 代码运行时错误：kernel 内已执行（可能有部分副作用）→ 不回退，
            # 直接返回 error，防止 Rscript 把整脚本再跑一遍造成双写/重复副作用。
            _out = (_res.get("output", "") or "")[:15000]
            _out += chr(10) + f"[Kernel error: {_err}]"
            return json.dumps({"status": "error", "output": _sct_note + _out, "error": _err,
                               "exit_code": 1, "mode": "persistent_kernel"}, ensure_ascii=False)
    except Exception:
        pass

    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        proc = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".R", mode="w",
                                             delete=False, encoding="utf-8") as f:
                f.write(code)
                script_path = f.name

            kwargs = dict(
                args=["Rscript", script_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=working_dir or None,
                env=_ensure_win_env(dict(os.environ)),
            )
            if os.name == 'nt':
                kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs['start_new_session'] = True
            proc = subprocess.Popen(**kwargs)

            try:
                stdout_data, stderr_data = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                _kill_process_group(proc)
                proc.wait(timeout=10)
                try:
                    os.unlink(script_path)
                except OSError:
                    pass
                _msg = f"Error: R execution timed out after {timeout}s (attempt {attempt}/{max_attempts}). Process killed."
                return json.dumps({"status": "timeout", "output": _sct_note + _msg, "error": _msg,
                                   "exit_code": None}, ensure_ascii=False)

            try:
                os.unlink(script_path)
            except OSError:
                pass

            output = ""
            if stdout_data:
                output += stdout_data.decode("utf-8", errors="replace")
            if stderr_data:
                output += chr(10) + "[STDERR]" + chr(10) + stderr_data.decode("utf-8", errors="replace")

            if proc.returncode != 0:
                is_oom = any(p in output.lower() for p in [
                    'cannot allocate', 'out of memory', 'bad_alloc', 'oom',
                    'memory exhausted', 'reached total allocation',
                    'reached memory limit', 'fatal error', 'killed'
                ])
                if is_oom and attempt < max_attempts:
                    output += chr(10) + f"[OOM检测] R进程内存不足(尝试{attempt}/{max_attempts})"
                    output += chr(10) + "[自动修复] 强制plan('sequential') + conserve.memory=TRUE"
                    code, _sct_changes = _apply_sct_rail(code)
                    continue
                output += chr(10) + f"[Exit code: {proc.returncode}]"
                if is_oom:
                    output += chr(10) + "[建议] 内存不足: 使用plan('sequential') + method='glmGamPoi' + conserve.memory=TRUE"
                # P0-3: 非零退出码 → 结构化 error（工具层不再视为成功）
                _err = f"R exited with code {proc.returncode}"
                if stderr_data:
                    _st = stderr_data.decode("utf-8", errors="replace").strip()
                    if _st:
                        _err = _st.splitlines()[-1] if _st.splitlines() else _err
                return json.dumps({"status": "error", "output": _sct_note + output[:15000],
                                   "error": _err, "exit_code": proc.returncode},
                                  ensure_ascii=False)

            return json.dumps({"status": "success", "output": _sct_note + (output[:15000] or "(no output)"),
                               "exit_code": 0}, ensure_ascii=False)

        except FileNotFoundError:
            _msg = "Error: R is not installed or not in PATH"
            return json.dumps({"status": "error", "output": _sct_note + _msg, "error": _msg,
                               "exit_code": None}, ensure_ascii=False)
        except Exception as e:
            if proc:
                _kill_process_group(proc)
            _msg = f"Error executing R: {e}"
            return json.dumps({"status": "error", "output": _sct_note + _msg, "error": _msg,
                               "exit_code": None}, ensure_ascii=False)

    _msg = "Error: R execution failed after retries"
    return json.dumps({"status": "error", "output": _sct_note + _msg, "error": _msg,
                       "exit_code": 1}, ensure_ascii=False)


def _register():
    from tools.registry import registry
    registry.register(
        name="execute_r",
        toolset="memomics",
        schema=SCHEMA,
        handler=lambda args, **kw: execute_r(
            args.get("code", ""),
            args.get("working_dir", ""),
            args.get("timeout", 600),
            kw.get("task_id", ""),
        ),
        emoji="📊",
        max_result_size_chars=50_000,
    )

_register()
