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


def _apply_sct_rail(code: str) -> str:
    """SCTransform 铁轨: 强制 workers=1 + sequential + conserve.memory."""
    code = re.sub(r'plan\s*\(\s*"multisession"[^)]*\)', 'plan("sequential")', code)
    code = re.sub(r'plan\s*\(\s*"multicore"[^)]*\)', 'plan("sequential")', code)
    if 'SCTransform' in code:
        if 'glmGamPoi' not in code and 'method' not in code:
            code = code.replace('SCTransform(',
                                'SCTransform(method="glmGamPoi", conserve.memory=TRUE, ', 1)
        elif 'conserve.memory' not in code:
            code = code.replace('SCTransform(',
                                'SCTransform(conserve.memory=TRUE, ', 1)
    code = re.sub(r'workers\s*=\s*\d+', 'workers=1', code)
    return code


def execute_r(code: str, working_dir: str = "", timeout: int = 600, task_id: str = "") -> str:
    """Execute R code with OOM detection and auto-retry.

    P0-1 持久 kernel 优先：跨调用保留变量/已加载包（热调用免解释器启动
    + 包加载，Seurat/ArchR 类 2000x+）；持久不可用/报错时回退
    每次 Rscript 新进程（保留 OOM 检测 + 自动重试 + SCTransform 特判）。
    """
    timeout = min(max(int(timeout), 30), 900)

    if 'SCTransform' in code:
        code = _apply_sct_rail(code)

    # ── 沙箱 fail-closed：degraded 模式写白名单外路径直接拒绝 ──
    try:
        from tools.sandbox_probe import probe_sandbox_capability, is_write_path_allowed
        import re as _re
        _write_re = _re.compile(
            r"""(?:write\.csv|write\.table|write\.rds|write\.tsv|saveRDS|ggsave|pdf|png|jpeg|tiff|bmp|writeLines|save)\s*\([^)]*?["']([^"']+)["']""")
        if probe_sandbox_capability().get("degraded"):
            _violations = []
            for _m in _write_re.finditer(code):
                _p = _m.group(1).strip()
                if _p and not is_write_path_allowed(_p):
                    _violations.append(_p)
            if _violations:
                return (f"Error: 沙箱 degraded 模式：写入白名单外路径被拒绝: {_violations[:3]}. "
                        "配置 MEMOMICS_ALLOWED_WRITE_ROOTS 可放行特定目录。")
    except Exception:
        pass

    # ── P0-1 持久 kernel 优先（状态保持 + 免包加载） ──
    try:
        from tools.persistent_kernel import KERNEL_POOL
        _res = KERNEL_POOL.execute(
            code,
            task_id or os.environ.get("MEMOMICS_SESSION_ID") or "default",
            timeout=min(timeout, 600), language="r")
        if _res.get("status") == "ok":
            return (_res.get("output", "") or "(no output)")[:15000]
        if _res.get("status") == "timeout":
            return f"Error: R execution timed out after {timeout}s. Kernel killed; next call starts fresh."
        # status == error → 回退旧路径（OOM 检测 + 重试）
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
                return f"Error: R execution timed out after {timeout}s (attempt {attempt}/{max_attempts}). Process killed."

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
                    code = _apply_sct_rail(code)
                    continue
                output += chr(10) + f"[Exit code: {proc.returncode}]"
                if is_oom:
                    output += chr(10) + "[建议] 内存不足: 使用plan('sequential') + method='glmGamPoi' + conserve.memory=TRUE"

            return output[:15000] or "(no output)"

        except FileNotFoundError:
            return "Error: R is not installed or not in PATH"
        except Exception as e:
            if proc:
                _kill_process_group(proc)
            return f"Error executing R: {e}"

    return "Error: R execution failed after retries"


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
