"""☁️ DCS 云连接器（agent 工具薄壳）—— 把华大 DCS Cloud / GenPilot 接进 MemOmics。

工具本体只做三件事：声明 schema、提供可见性 check_fn、把调用转给
``memomics.connectors.dcs_cloud.dcs_cloud_handler``（与 WebUI「☁️ DCS 云」面板
共用同一个实现，避免两套逻辑漂移）。

背景与安全约定见 ``memomics/connectors/dcs_cloud.py`` 模块 docstring：
    * 凭据是 PAT（个人访问令牌，平台明确允许"AI Agent 调用"），**不碰用户密码**；
    * 绑定/解绑只能在 WebUI 面板或用户明确给 PAT 时进行；模型不许替用户生成/猜测 PAT；
    * 上传/投递等写操作会改动云端数据并计费 —— 执行前必须先向用户确认。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def dcs_cloud_enabled() -> bool:
    """check_fn：config.yaml 的 dcs_cloud.enabled=true 时，工具对模型可见。"""
    try:
        from memomics.connectors import dcs_cloud as _dcs
        return _dcs.dcs_cloud_enabled()
    except Exception as exc:
        logger.debug("dcs_cloud check_fn 失败: %s", exc)
        return False


SCHEMA = {
    "name": "dcs_cloud",
    "description": (
        "☁️ 华大 DCS Cloud（含 GenPilot）连接器 —— 操作用户**已有**的云平台项目："
        "看数据、上下传文件、在云容器里跑命令、查离线任务与日志。\n"
        "适用：用户说\"我 DCS 云上有项目/数据\"\"帮我把结果传到云上\"\"在云上跑\"\"查一下云上任务\"，"
        "或用户的数据/算力在 DCS Cloud（genpilot / dcs.cloud）上。\n"
        "不适用：本机就能跑的小分析（用 execute_python / execute_r）——除非用户明确要求上云。\n"
        "凭据：用户先在 DCS 个人中心 → 访问令牌 创建 PAT（最长 1 年），再在 MemOmics「☁️ DCS 云」"
        "面板绑定。**不要向用户索要密码，也不要索要 PAT 文本**（让他自己在面板里粘贴）；"
        "如果工具报未绑定，就引导他去面板绑定。\n"
        "常用流程：status（先看绑定/CLI 状态）→ projects（列项目）→ use_project（切到目标项目）→ "
        "ls / find（找数据）→ 本地算 or container_exec（云上跑）→ upload / download（往返）→ "
        "tasks / task_logs（看任务）。\n"
        "⚠️ 计费与写操作：upload / upload 到的路径、container_open、投递任务都会产生云端费用或改动云端数据——"
        "执行前先跟用户确认（说清要传什么、传到哪、大概多大）；一次跑不完的长活优先走离线任务。\n"
        "⚠️ 配对用法：云端容器（OpenSandbox）与本地是两套文件系统；容器内路径是 /work/...，"
        "Files 里的路径是 /Files/...，本机是 E:/... 之类。路径不对会报错，先 ls 确认再动。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "bind", "unbind", "projects", "use_project", "current",
                         "ls", "find", "info", "download", "upload",
                         "container_open", "container_exec", "container_close",
                         "tasks", "task_logs", "raw"],
                "description": (
                    "要执行的动作：status=绑定/CLI 状态；projects/use_project/current=项目；"
                    "ls/find/info=浏览与查找 Files；download/upload=云↔本机传文件；"
                    "container_open/exec/close=云上在线容器；tasks/task_logs=离线任务；"
                    "raw=白名单逃生舱（跑任意非凭据类 dcs 子命令）。"
                ),
            },
            "path": {"type": "string",
                     "description": "ls/info/download：云上路径（如 /Files/proj/data.csv）；upload：本机文件路径"},
            "target": {"type": "string",
                       "description": "upload：云上目标路径（/Files/...）；download：本机目标目录"},
            "type": {"type": "string", "enum": ["web", "oss", "raysync", "ossutil", "tosutil"],
                     "description": "传输方式：小文件 web（≤100MB 上传 / ≤200MB 下载）；大文件用 oss"},
            "name": {"type": "string", "description": "find：文件名通配（*.csv）；use_project：项目名（精确匹配）"},
            "project": {"type": "string", "description": "use_project：项目 ID（P 开头）"},
            "size": {"type": "string", "description": "find：体积过滤，如 +100M / -1G"},
            "sn": {"type": "string", "description": "find：按样本文库编号（SN）过滤"},
            "sample": {"type": "string", "description": "find：按样本 ID 过滤"},
            "time": {"type": "string", "description": "find：时间范围，如 2024-01-01:2024-12-31"},
            "page_size": {"type": "integer", "description": "find/tasks：每页条数（≤200）"},
            "page": {"type": "integer", "description": "ls/find/tasks：页码（从 1 开始；返回里带 total，用于翻页）"},
            "long": {"type": "boolean",
                     "description": "ls：true = 附带文件大小/创建时间/完整路径（浏览目录时建议开）"},
            "command": {"type": "string",
                        "description": "container_exec：容器内 shell 命令；raw：dcs 子命令（如 \"workflow ls\"）"},
            "cwd": {"type": "string", "description": "container_exec：容器内工作目录"},
            "resource_id": {"type": "string", "description": "container_open：容器规格 ID（先用 raw: terminal ls_resource 查）"},
            "task_id": {"type": "string", "description": "task_logs：任务 ID（先用 tasks 查）"},
            "all": {"type": "boolean", "description": "tasks：true = 查全项目任务（-a）"},
            "pat": {"type": "string",
                    "description": "bind：PAT 文本。仅在用户主动把 PAT 直接发给你时才用；"
                                   "更推荐引导用户在「☁️ DCS 云」面板里粘贴。"},
            "timeout": {"type": "integer", "description": "container_exec：容器内命令超时秒数"},
        },
        "required": ["action"],
    },
}


def _register():
    from tools.registry import registry
    registry.register(
        name="dcs_cloud",
        toolset="memomics",
        schema=SCHEMA,
        handler=lambda args, **kw: _handle(args),
        check_fn=dcs_cloud_enabled,
        emoji="☁️",
        max_result_size_chars=40_000,
    )


def _handle(args):
    try:
        from memomics.connectors.dcs_cloud import dcs_cloud_handler
    except Exception as exc:   # 连接器缺失时报明确错误，而不是工具消失
        import json as _json
        return _json.dumps({"status": "error", "error": "连接器不可用: %s" % exc},
                           ensure_ascii=False, indent=2)
    return dcs_cloud_handler(args)


_register()