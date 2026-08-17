# 页文件提交压力导致的 ArchR 大样本崩溃 — 诊断与处置（2026-08-07 实测）

## 场景

GSE278576 人海马 ATAC 40 样本 ArchR QC 批处理（create_arrow_qc.R，串行 run_serial_v2.sh + watchdog_v2.sh）。
hc73 是最大样本（fragments 5.42GB，其余 1.6-2.4GB），读取 fragments 到 42% 时崩溃。

## 崩溃日志（hc73.log 尾部关键行）

```
[E::hts_idx_load3] Could not load local index file 'E:/专利/Human_Hippocampus_ATAC/fragments/GSM8549648_hc73_atac_fragments.tsv.gz.tbi' : Not enough space
2026-08-07 18:43:08 : (GSM8549648_hc73 : 1 of 1) Reading TabixFile 42 Percent, 20.148 mins elapsed.
ERROR Found in .tabixToTmp for (GSM8549648_hc73 : 1 of 1)
<simpleError in forderv(data, seq_along(data), retGrp = FALSE, ...): 内部错误 range_str: failed to grow the 'marks' hash table. 请将此问题汇报给 data.table 问题追踪器。>
```

随后 `createArrowFiles` 返回空 → 脚本在 `ArchRProject()` 处报 `file.exists(...): 'file'参数无效`（ArrowFiles 为空向量）。

## 关键诊断步骤（顺序）

1. **三源验证**：PowerShell Get-Process（Rscript 36652 存活 CPU 1210s）、磁盘输出目录计数 33、hc73.log 尾部。
   注意：`tasklist //FI | grep` 可能返回空（MSYS 转码伪阴性）——最终裁决用 PowerShell Get-Process / ps -ef。
2. **物理内存**：TotalVisibleMemorySize 58281976 KB (~55.6GB)，FreePhysicalMemory 26346120 KB (~25GB)——**充足，不能排除问题**。
3. **页文件（关键）**：
   ```
   C:\pagefile.sys   AllocatedBaseSize=25600  CurrentUsage=72  PeakUsage=185
   AutomaticManagedPagefile : False
   ```
   PeakUsage 185% = 曾超配 → 页文件高压力。data.table 的 `forderv` 排序（按 chr/start/end 排序全部 fragments）需要大量虚拟内存提交。
4. **样本大小排序**：hc73 5.42GB 是最大样本，其他样本 1.6-2.4GB 全部通过 → 符合"页文件提交不足在大样本排序时暴露"的模式。

## 处置

- **不重写脚本**：脚本无 bug（33 个样本通过），失败是系统资源限制。
- **watchdog 自动续跑**：run_serial_v2.sh 的 SKIP 逻辑自动跳过已完成样本，hc73 失败后被记录（无 _filtered_cells.csv），
  剩余 6 个小样本继续跑，hc73 留在剩余列表等待后续重试。
- **缓解选项（需用户确认）**：
  a) 扩容页文件：`wmic computersystem set AutomaticManagedPagefile` 后手动设置更大初始/最大大小（需管理员）
  b) 大样本单独时段跑（系统空闲、无其他大内存进程时）
  c) 接受失败，仅对 hc73 用更保守参数（minFrags 上调等）单独处理

## 同类信号速查

| 错误 | 可能根因 |
|------|---------|
| `hts_idx_load3 ... Not enough space` | tabix 索引加载时虚拟内存提交失败（页文件压力） |
| `forderv ... failed to grow the 'marks' hash table` | data.table 排序 hash 表增长失败（页文件提交不足） |
| `WinError 1455 页面文件太小` | 任意 Windows 进程（如 python 加载 torch DLL）虚拟内存分配失败 |
| bash `fork: retry: Resource temporarily unavailable` / exit 0xC000012D | bash fork 资源枯竭（内存/页文件压力连带） |

## 预防

- 批量任务启动前若知道有超大样本（> 同批中位数 2 倍以上），先查页文件配置。
- 页文件峰值 >100% 时，大样本崩溃是预期而非例外。
- 内存诊断顺序：物理内存 → 页文件 → 每进程内存 → 样本大小分布。物理内存充足不能排除页文件问题。
