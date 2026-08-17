# Resume Pipeline Pattern — 断点续跑

## 触发场景

Pipeline 中途崩溃（样本 N 跑到一半进程死了），已完成样本完好，需从崩溃点继续。

## 核心设计原则

1. **不依赖 JSON 状态文件** — 直接用磁盘文件存在性判断完成状态
2. **双重过滤防 macOS `._*` 垃圾** — `not f.name.startswith("._")` + `f.stat().st_size > 100_000_000`
3. **跳过已完成 = `filtered.h5` 存在且 > 1MB**
4. **串行 + 逐样本验证** — 每跑完一个立即检查产出

## 参考脚本结构

```python
OUTPUT_DIR = r"PROJECT_DATA_DIR\cellbender_output"
INPUT_DIR = r"F:\raw_matrix_h5"

def verify_output(sample):
    """检查 filtered.h5 是否存在且 > 1MB"""
    fpath = os.path.join(OUTPUT_DIR, sample, f"{sample}_raw_output_filtered.h5")
    if os.path.exists(fpath) and os.path.getsize(fpath) > 1_000_000:
        return True, fpath
    return False, None

# 双重过滤：排除 ._ 前缀 + 文件太小
all_files = sorted([
    f for f in os.listdir(INPUT_DIR)
    if f.endswith(".h5ad") and not f.startswith("._")
])

pending = []
for f in all_files:
    sample = f.replace("_raw.h5ad", "")
    if verify_output(sample)[0]:
        print(f"跳过 {sample} — 已完成")
        continue
    pending.append(sample)

for i, sample in enumerate(pending):
    # ... subprocess.Popen + wait + verify
```

## 教训

- `glob("*.h5ad")` 在跨平台目录中会匹配 macOS `._*` 资源分支文件 → 加 size 过滤（h5ad < 100MB = 垃圾）
- 不要用 `_pipeline_progress.json` 判断完成状态 → 直接 stat filtered.h5
- Pipeline 日志的 mtime 是判断"是否还在跑"的最可靠信号
- 跨会话恢复时（脚本被移入 _TRASH、心跳死亡、产出丢失）→ 完整 8 步协议见 `references/cross-session-pipeline-recovery.md`
