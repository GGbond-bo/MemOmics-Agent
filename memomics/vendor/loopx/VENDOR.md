# LoopX（vendored）

本目录是 **LoopX** 的本地副本（vendored copy），供 MemOmics 的长任务控制平面使用。

- **上游来源**：[loopx-project/loopx](https://github.com/loopx-project/loopx)
- **对应版本 / 标签**：[`v0.4.1`](https://github.com/loopx-project/loopx/tree/v0.4.1)
- **本目录声明的版本**：`0.4.1`（见 `__init__.py`）
- **许可证**：MIT（见本目录 `LICENSE`，与上游 `v0.4.1` 的许可证文本逐字一致，仅换行归一化）

## 本地补丁说明

本副本**不是纯快照**：相对上游 `v0.4.1` 有 10 个文件带本地改动。
升级 LoopX 或核对 API 兼容性时，请先看这些文件（数值为本地/上游字符数）：

| 文件 | 本地 | 上游 | 说明 |
|---|---:|---:|---|
| `quota.py` | 116461 | 111652 | 配额与暂停判定扩展 |
| `todos.py` | 85610 | 84259 | 待办状态扩展 |
| `control_plane/scheduler/scheduler_hint.py` | 52999 | 51009 | 调度提示扩展 |
| `presentation/renderers/quota_markdown.py` | 54958 | 54696 | 配额渲染调整 |
| `control_plane/quota/monitor_poll.py` | 28525 | 28334 | 轮询监控调整 |
| `doctor.py` | 50821 | 50657 | 自检文案与判据补充 |
| `file_lock.py` | 11968 | 1870 | **改动最大**：本地文件锁实现重写/扩展 |
| `control_plane/scheduler/automation_liveness.py` | 7779 | 7143 | 存活判定调整 |
| `presentation/renderers/quota_event_markdown.py` | 4990 | 4853 | 事件渲染调整 |
| `presentation/markdown.py` | 1820 | 994 | 渲染工具函数扩展 |

其余 257 个文件与上游 `v0.4.1` **逐字节相同**（含换行符），可直接对照上游阅读。
`LICENSE` 为上游许可证的本地副本（上游对应文件路径为仓库根 `LICENSE`）。

生成方式：`python tools/loopx_vendor_audit.py`（按 git blob 与文本两种口径比对，
换行符差异不计为改动）。

---

## Vendored copy（English）

This directory is a vendored copy of [LoopX](https://github.com/loopx-project/loopx)
at tag [`v0.4.1`](https://github.com/loopx-project/loopx/tree/v0.4.1), licensed MIT.

It is **not a pristine snapshot**: 10 files carry local patches (see the table above;
`file_lock.py` differs the most). The remaining 257 files are byte-identical to upstream
`v0.4.1`. Check the patched files first when evaluating upstream API compatibility.