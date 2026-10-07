"""MemOmics connectors —— 外部平台/服务连接器（每个连接器一个模块，互不依赖）。

目前只有一个：
    * ``dcs_cloud`` —— 华大 DCS Cloud / GenPilot 连接器（PAT + 官方 dcs CLI 底板）。

约定（与 memomics/bio_tools 的工具薄壳配合）：
    * 连接器模块只负责"跟外部系统对话"（凭据、CLI/HTTP 调用、结构化结果）；
    * 暴露面统一是 ``xxx_handler(args: dict) -> str``（返回 JSON 字符串），
      这样 agent 工具与 WebUI HTTP 端点能共用同一个实现；
    * 不许在模块导入时做网络/子进程动作（import 失败会拖垮整个包）。
"""