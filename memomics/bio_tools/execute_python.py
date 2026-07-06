"""execute_python — Python 代码执行工具，带 conda 环境检测 + 超时 kill。

从 MemOmics 老版迁移核心逻辑，适配 hermes registry 格式。
"""
import os
import re
import subprocess
import tempfile
import logging

logger = logging.getLogger(__name__)

SCHEMA = {
    "name": "execute_python",
    "description": (
        "Execute Python code with conda env support and timeout kill. "
        "Use for scanpy/anndata/scvi-tools/cellrank analysis. "
        "Returns stdout + stderr (truncated to 10000 chars)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute"
            },
            "working_dir": {
                "type": "string",
                "description": "Working directory (optional)",
                "default": ""
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (10-600, default 300)",
                "default": 300
            },
            "conda_env": {
                "type": "string",
                "description": "Conda environment name (optional)",
                "default": ""
            }
        },
        "required": ["code"]
    }
}


def _ensure_win_env(env: dict) -> dict:
    """Fix Windows subprocess env."""
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
    return env


def _kill_process_group(proc):
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


def execute_python(code: str, working_dir: str = "", timeout: int = 300,
                   conda_env: str = "") -> str:
    """Execute Python code with process-group kill on timeout."""
    timeout = min(max(int(timeout), 10), 600)
    proc = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w",
                                         delete=False, encoding="utf-8") as f:
            f.write(code)
            script_path = f.name
        if conda_env:
            cmd = ["conda", "run", "-n", conda_env, "python", script_path]
        else:
            cmd = ["python", script_path]

        kwargs = dict(
            args=cmd,
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
            return f"Error: Python execution timed out after {timeout}s. Process killed."

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
            output += chr(10) + f"[Exit code: {proc.returncode}]"
        return output[:10000] or "(no output)"
    except Exception as e:
        if proc:
            _kill_process_group(proc)
        return f"Error executing Python: {e}"


def _register():
    from tools.registry import registry
    registry.register(
        name="execute_python",
        toolset="memomics",
        schema=SCHEMA,
        handler=lambda args, **kw: execute_python(
            args.get("code", ""),
            args.get("working_dir", ""),
            args.get("timeout", 300),
            args.get("conda_env", ""),
        ),
        emoji="🐍",
        max_result_size_chars=50_000,
    )

_register()
