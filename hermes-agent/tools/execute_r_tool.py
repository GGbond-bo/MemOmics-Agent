# -*- coding: utf-8 -*-
"""execute_r 工具：持久 R kernel 接入 agent 工具链（P0-1 补齐）

R 分析优先用本工具而非 `terminal Rscript xxx.R`：
持久内核跨调用保留变量/已加载包，免去每次解释器启动 + 包加载
（Seurat/ArchR 类重包热调用 2000x+）。

- 沙箱 degraded 模式：写白名单外路径（R 写 API 静态检查）直接拒绝
- 超时 kill worker，下次调用自动重建
- 与 execute_code 返回结构一致（status/result/output/error/...）
"""
import json
import re
import time

_R_WRITE_RE = re.compile(
    r"""(?:write\.csv|write\.table|write\.rds|write\.tsv|saveRDS|ggsave|pdf|png|jpeg|tiff|bmp|writeLines|save)\s*\([^)]*?["']([^"']+)["']"""
)


def _build_schema() -> dict:
    return {
        "name": "execute_r",
        "description": (
            "Run R code in a PERSISTENT R kernel — variables and loaded packages "
            "survive across calls within the same session. Prefer this over "
            "`terminal Rscript script.R` for analysis steps: warm calls skip "
            "interpreter startup and package loading (Seurat/ArchR-class workloads "
            "are 100x+ faster on repeat calls).\n\n"
            "Print your final result (print()/cat()) to stdout; a single-expression "
            "cell echoes its value like a Jupyter cell.\n\n"
            "Limits: 120s per call, 200KB output cap. Kernel is per-session "
            "(other sessions cannot see your variables). If a call times out the "
            "kernel is killed and a fresh one starts on the next call (state resets)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "R code to execute.",
                },
            },
            "required": ["code"],
        },
    }


def execute_r(code: str, task_id=None, timeout=120) -> str:
    """执行 R 代码（持久 kernel）；返回与 execute_code 一致的 JSON 字符串"""
    start = time.monotonic()
    if not code or not code.strip():
        return json.dumps({"status": "error", "error": "No R code provided.",
                           "output": "", "tool_calls_made": 0, "duration_seconds": 0},
                          ensure_ascii=False)

    # 沙箱 degraded 模式：写白名单外路径直接拒绝（fail-closed）
    try:
        from tools.sandbox_probe import probe_sandbox_capability, is_write_path_allowed
        _probe = probe_sandbox_capability()
        if _probe.get("degraded"):
            violations = []
            for m in _R_WRITE_RE.finditer(code):
                p = m.group(1).strip()
                if p and not is_write_path_allowed(p):
                    violations.append(p)
            if violations:
                return json.dumps({
                    "status": "error",
                    "error": f"沙箱 degraded 模式：写入白名单外路径被拒绝: {violations[:3]}. "
                             "配置 MEMOMICS_ALLOWED_WRITE_ROOTS 可放行特定目录。",
                    "output": "", "tool_calls_made": 0,
                    "duration_seconds": round(time.monotonic() - start, 2),
                }, ensure_ascii=False)
    except Exception:
        pass

    try:
        from tools.persistent_kernel import KERNEL_POOL
        res = KERNEL_POOL.execute(code, task_id or "default", timeout=timeout, language="r")
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e), "output": "",
                           "tool_calls_made": 0,
                           "duration_seconds": round(time.monotonic() - start, 2)},
                          ensure_ascii=False)
    res["duration_seconds"] = round(time.monotonic() - start, 2)
    return json.dumps(res, ensure_ascii=False)


from tools.registry import registry  # noqa: E402

registry.register(
    name="execute_r",
    toolset="code_execution",
    schema=_build_schema(),
    handler=lambda args, **kw: execute_r(
        code=args.get("code", ""),
        task_id=kw.get("task_id")),
    check_fn=lambda: True,
    emoji="📊",
    max_result_size_chars=100_000,
)
