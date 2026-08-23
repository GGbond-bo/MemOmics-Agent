# -*- coding: utf-8 -*-
"""kernel_restart 工具：重启持久 kernel worker，一键释放全部内存。

内存密集管线（单细胞/空间组/ATAC）阶段切换时的释放手段：
- 阶段间对象级清理（rm + gc）是常规做法，但 R 的堆碎片/未回收内存
  仍然堆积时，重启 worker 是唯一 100% 释放的方式（OpenAI4S "换 kernel"
  等价物，进程退出 → OS 回收全部内存）。
- 重启后所有变量/加载的包清空：下一阶段必须 readRDS 重新加载最小输入。
"""
import json

SCHEMA = {
    "type": "object",
    "properties": {
        "language": {
            "type": "string",
            "enum": ["r", "python", ""],
            "description": "重启哪种语言的 worker。默认 'r'（单细胞分析主力）。空 = 全部语言",
        },
        "task_id": {
            "type": "string",
            "description": "只重启指定任务的 worker；留空 = 该语言全部 worker",
        },
    },
    "required": [],
}


def kernel_restart(language="r", task_id=""):
    try:
        from tools.persistent_kernel import KERNEL_POOL
        return KERNEL_POOL.restart(
            language=language or None,
            task_id=task_id or None,
        )
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


def _register():
    from tools.registry import registry
    registry.register(
        name="kernel_restart",
        toolset="memomics",
        schema=SCHEMA,
        handler=lambda args, **kw: kernel_restart(
            (args or {}).get("language", "r"),
            (args or {}).get("task_id", ""),
        ),
        emoji="🧹",
        max_result_size_chars=2_000,
    )


_register()
