# Task Plan: Monkey CellBender Batch — 13 Remaining Samples

## Goal
继续完成 E:/monkey/ 下 13 个待处理 CRR 样本的 CellBender remove-background。
2/15 已完成（CRR278961, CRR278962），13 个待跑。

## Current Phase
Phase 2

## Phases

### Phase 1: 环境验证 + 脚本准备 ✅
- [x] 确认路径：E:/monkey/（原始 task_plan 的 F:/CellBender_v2 不存在）
- [x] 扫描样本：15 个 CRR，2 done，13 pending
- [x] 对比已完成样本命令行（pitfall 36）
- [x] 写 run_remaining.py 批量脚本
**Status:** completed

### Phase 2: 执行 CellBender（13 个样本串行）
- [ ] 后台启动 run_remaining.py
- [ ] 部署 heartbeat_v2.py 监控
- [ ] 部署 error_scanner.py
**Status:** in_progress

### Phase 3: ptrepack → Seurat h5
- [ ] 所有 filtered.h5 完成后，ptrepack 转 seurat_h5/
**Status:** pending

### Phase 4: 统计汇总
- [ ] 生成 Post-CellBender 汇总表
**Status:** pending

## Environment
| Tool | Path |
|------|------|
| CellBender | C:/Users/23136/AppData/Local/Programs/Python/Python312/Scripts/cellbender.exe |
| Python | C:/Users/23136/AppData/Local/Programs/Python/Python312/python.exe |
| TMPDIR | E:/tmp |
| Input | E:/monkey/h5ad/*.h5ad |
| Output | E:/monkey/cellbender/{sample}/cellbender_output_filtered.h5 |
| GPU | RTX 5070 Ti, 16 GB VRAM |
| sitecustomize | torch.save patched v4 + torch.load weights_only=False ✅ |

## Parameters (from completed CRR278961)
```
--projected-ambient-count-threshold 5
--learning-rate 0.0001
--training-fraction 0.9
--low-count-threshold 20
--epochs 150
--checkpoint-mins 5
--cuda
```

## Samples
| Sample | Size | Status |
|--------|------|--------|
| CRR278961 | 130M | ✅ DONE |
| CRR278962 | 60M | ✅ DONE |
| CRR278963 | 65M | ⏳ PENDING |
| CRR278964 | 60M | ⏳ PENDING |
| CRR278998 | 119M | ⏳ PENDING |
| CRR279006 | 148M | ⏳ PENDING |
| CRR279013 | 228M | ⏳ PENDING |
| CRR279014 | 129M | ⏳ PENDING |
| CRR279022 | 168M | ⏳ PENDING |
| CRR279023 | 158M | ⏳ PENDING |
| CRR279024 | 163M | ⏳ PENDING |
| CRR279038 | 287M | ⏳ PENDING |
| CRR279041 | 126M | ⏳ PENDING |
| CRR279045 | 248M | ⏳ PENDING |
| CRR279047 | 248M | ⏳ PENDING |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
|       |         |            |

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 使用 CRR278961 完全相同的参数 | pitfall 36：必须对比已完成样本命令行，不能凭记忆写 |
| 不用 --total-droplets-included | 已完成样本没用，且已验证成功 |
| 不用 --expected-cells | 已完成样本没用 |
| checkpoint-mins=5（不是 120） | 与已完成样本一致 |
