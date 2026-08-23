"""execute_python — Python 代码执行工具，带 conda 环境检测 + 超时 kill。

从 MemOmics 老版迁移核心逻辑，适配 hermes registry 格式。
"""
import os
import re
import json
import subprocess
import tempfile
import logging

logger = logging.getLogger(__name__)

SCHEMA = {
    "name": "execute_python",
    "description": (
        "Execute Python code with conda env support and timeout kill. "
        "Use for scanpy/anndata analysis (scvi-tools/cellrank 未装，需先 pip 安装到 .venv). "
        "Returns stdout + stderr (truncated to 10000 chars). "
        "PERSISTENT KERNEL: 同一会话（同一 task_id）内复用同一 Python worker，"
        "之前定义的变量（如 adata）和 import 的包在后续调用里仍可用。"
        "同一会话后续步骤直接复用 adata，不要每步重新 read_h5ad / 写中间副本。"
        "仅当变量丢失（kernel 超时/重启）时才重新加载。"
        "【运行脚本文件（matplotlib 出图脚本等）也用本工具】exec(open('路径', encoding='utf-8').read())"
        "——持久内核重跑秒级返回；禁止用 terminal 执行 python xx.py 冷启动。"
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
                "description": "Timeout in seconds (10-7200, default 1800). 大矩阵/长计算请显式传大 timeout（如 3600），不要靠默认值。",
                "default": 1800
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


def execute_python(code: str, working_dir: str = "", timeout: int = 1800,
                   conda_env: str = "", task_id: str = "") -> str:
    """Execute Python code with process-group kill on timeout.

    P2-14(2026-08-10): 持久 kernel 优先 — 与 execute_r 对齐。
    之前每次新建子进程，第二次交互变量全丢（画图/加载的包不保留）。
    现在优先走 KERNEL_POOL（按 {lang}:{task_id} 缓存，空闲 30 分钟惰性关闭，
    同会话跨调用保留变量/已加载包）；持久不可用/报错时回退旧路径。
    """
    # 2026-08-16: 上限 600→7200 —— 长计算曾被默认超时误杀
    timeout = min(max(int(timeout), 10), 7200)

    # ── P2-14: 持久 kernel 优先（状态保持 + 免包加载） ──
    try:
        from tools.persistent_kernel import KERNEL_POOL
        import os as _os
        # P1-13(2026-08-13): 会话识别 — 用 execute_r 同款隔离键（线程上下文 sid 优先）
        try:
            from memomics.bio_tools.execute_r import _session_task_id
            _task = _session_task_id(task_id)
        except Exception:
            _task = task_id or _os.environ.get("MEMOMICS_SESSION_ID") or "default"
        _res = KERNEL_POOL.execute(
            code, _task, timeout=min(timeout, 7200), language="python",
            cwd=working_dir or None)  # P1-5: working_dir 接线
        if _res.get("status") == "ok":
            return (_res.get("output", "") or "(no output)")[:15000]
        if _res.get("status") == "timeout":
            return f"Error: Python execution timed out after {timeout}s. Kernel killed; next call starts fresh."
        # status == error → 分类处理（P1-4，2026-08-13：防副作用双跑）
        _err = _res.get("error", "unknown kernel error")
        _infra_fail = ("worker died unexpectedly" in _err) or ("worker write failed" in _err)
        if _infra_fail:
            # 基础设施失败：代码大概率未送达 → 回退旧路径相对安全
            pass
        else:
            # 代码运行时错误：不回退，防整脚本重跑双写
            return json.dumps({"status": "error", "output": (_res.get("output", "") or "")[:15000],
                               "error": _err, "exit_code": 1,
                               "mode": "persistent_kernel"}, ensure_ascii=False)
    except Exception:
        pass

    proc = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w",
                                         delete=False, encoding="utf-8") as f:
            f.write(code)
            script_path = f.name
        if conda_env:
            # 2026-08-16 修复：conda 已损坏（zstandard 缺失 + conda-libmamba-solver 加载失败，
            # 且只有 base 无命名 env），conda run -n 会直接报错。这里先探测 conda 可用性，
            # 不可用则回退当前解释器（.venv），避免 execute_python 白报错。
            _use_conda = False
            try:
                import shutil as _shutil
                _ce = _shutil.which("conda")
                if _ce:
                    _p = subprocess.run(
                        [_ce, "env", "list"], capture_output=True, text=True, timeout=15,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                    )
                    _use_conda = _p.returncode == 0
            except Exception:
                _use_conda = False
            if _use_conda:
                cmd = ["conda", "run", "-n", conda_env, "python", script_path]
            else:
                import sys as _sys
                cmd = [_sys.executable, script_path]
        else:
            # 2026-08-16: 用当前进程解释器（.venv），不用 PATH 的 "python"
            # （机器上是 WindowsApps stub，缺 scanpy 生态）。
            import sys as _sys
            cmd = [_sys.executable, script_path]

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
            # 2026-08-14: 非零退出码 = 执行失败（不再伪装成功返回）
            return json.dumps({"status": "error", "output": output[:10000],
                               "error": f"Process exited with non-zero code {proc.returncode}",
                               "exit_code": proc.returncode, "mode": "subprocess"}, ensure_ascii=False)
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
            args.get("timeout", 1800),
            args.get("conda_env", ""),
            kw.get("task_id", ""),
        ),
        emoji="🐍",
        max_result_size_chars=50_000,
    )

_register()
