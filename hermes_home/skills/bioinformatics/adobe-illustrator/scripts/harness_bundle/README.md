# harness_bundle — cli-anything-illustrator 自包含快照

- 内容：`cli_anything.illustrator`（16 命令版），与项目 `.venv` 已装版同步。
- 用途：`scripts/ai.py` 找不到已装 exe 时的**零安装回退**（`PYTHONPATH` 指向本目录，`python -m cli_anything.illustrator`）。
- 同步规则：上游 harness 源码改动后（`results/memomics-ad6fdb02/software_control/illustrator/agent-harness/`），
  把 `cli_anything/illustrator/**` 重新拷到本目录，保持快照=已装版。
- 快照日期：2026-10-04 · Illustrator 30.0.0 全量验证版。