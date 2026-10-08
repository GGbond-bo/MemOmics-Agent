# ArchR Peak Calling — 实战陷阱与张潇 cCRE 参数（2026-08-30 实测）

## 流程顺序（官方 + 实测确认）

```
pathToMacs2 <- findMacs2()                    # 12.2 第一件事（找不到就手动给绝对路径）
proj <- addGroupCoverages(proj, groupBy=...)  # 12.1 峰值前必须跑，否则 addReproduciblePeakSet 报错
proj <- addReproduciblePeakSet(proj, groupBy=..., pathToMacs2=pathToMacs2)
proj <- addPeakMatrix(proj, force=TRUE)       # ★★★ 常被漏掉的一步
```

## ⚠️ 坑 1：getMatrixFromProject 报 "useMatrix is not in Available Matrices"

**症状**：`getMatrixFromProject(proj, useMatrix="PeakMatrix")` → `useMatrix is not in Available Matrices see getAvailableMatrices`

**根因**：`addReproduciblePeakSet` 只生成 peak 坐标集合（PeakSet），**不生成 细胞×peak 计数矩阵**。PeakMatrix 必须单独显式 `addPeakMatrix()` 才会构建。

**修复**：补跑 `proj <- addPeakMatrix(proj, force=TRUE)` → `getAvailableMatrices(proj)` 确认含 "PeakMatrix" → 再 getMatrixFromProject。两个物种（人/猴）都要检查这一步，不能只跑一个。

## ⚠️ 坑 2：saveArchRProject vs saveRDS

- `saveRDS(proj)` 只保存内存里的 R 对象（metadata + cellColData + 指向 Arrow 的路径引用），**PeakSet/PeakMatrix 不会完整保存**；下次 readRDS 回来访问不了新增矩阵。
- ArchR 项目必须用 `saveArchRProject(proj, outputDirectory=..., force=TRUE, load=TRUE)` 保存 → 之后 `loadArchRProject(目录)` 恢复。
- call peak 后立即 `saveArchRProject`（force=TRUE 有些版本是 overwrite=TRUE，实测 formals 是 `force`）。

## ⚠️ 坑 3：addGroupCoverages 报 "HDF5. File accessibility. Unable to open file"（H5Fcreate 失败）

**症状**（实测日志）：
```
Astro (1 of 8): CellGroups N = 5
Group Astro._.O2_Hip_3 (1 of 40)
Number of Cells = 500
Error in H5Fcreate(file): HDF5. File accessibility. Unable to open file.
```

**真正根因（这次实测定位）**：`getOutputDirectory(proj)` 指向**别人的目录**（loadArchRProject 加载的 Project 的 outputDirectory 写死在他人的路径，如 `/hwfssz3/PS_JLU/zhangxiao6/...`），当前用户对该目录**没有写权限** → ArchR 创建 GroupCoverages/*.h5 失败。加 GroupCoverages 需要写权限（要生成新文件），只有读权限不够。

**排查顺序**（按实测效率）：
1. `getOutputDirectory(proj)` — 看输出目录是不是自己有权写的目录（第一优先查这个）
2. `df -h` 磁盘/配额满？（本次 80% 但可用 25T，不是根因但通用）
3. 上次中断残留损坏 .h5 → `unlink(file.path(out, "GroupCoverages"), recursive=TRUE)` + `force=TRUE` 重跑
4. 50 线程并行写 H5 冲突 → 降到 `addArchRThreads(8)` 或更少

**修复**：`copyArchRProject(projToCopy=proj, outputDirectory="你自己有写权限的目录")` 复制到自己目录跑；或只改 `proj@projectMetadata$outputDirectory`（内存中）再跑。⚠️ copyArchRProject 可能只复制 metadata 不复制 Arrow（Arrow 仍指向他人目录），失败时报错就用第二种（改 outputDirectory + saveArchRProject 到自己目录）。

## ⚠️ 坑 4：CPU 没动静 ≠ 卡死

`addGroupCoverages` 是**磁盘 I/O 密集型**（读几百个 Arrow 文件），CPU 低是正常的；`addReproduciblePeakSet` 里 MACS2 是单线程，50 核下总 CPU 看着也低。判断是否在跑：`ps aux | grep macs2`（有输出=到 MACS2 阶段了）、`ls -lh GroupCoverages/` 文件在增长。50 线程对 PeakMatrix 没帮助（I/O bound）。

## ⚠️ 坑 5：MACS2 找不到（findMacs2 扑空）

conda env 装的 MACS2 不在 PATH 时 `findMacs2()` 找不到，但路径是真实的（如 `/hwfssz3/PS_JLU/zhangxiao6/software/miniconda3/envs/MACS2/bin/macs2`）。直接手动指定 `pathToMacs2 <- "完整路径"`，先 `system(paste(pathToMacs2, "--version"))` 验证。或 `Sys.setenv(PATH=paste0(dirname, ":", Sys.getenv("PATH")))` 再 findMacs2。

## 张潇 NHPABC cCRE 论文参数（人猴海马项目直接抄这份）

```
addGroupCoverages:  minCells=40, maxCells=5,000, minReplicates=2, maxReplicates=10
addReproduciblePeakSet: maxPeaks=500,000, cutOff=0.01
输出: 501-bp fixed-width peaks
过滤门槛（cCRE 前）: 每个体 >10 nuclei / 每 age group >100 nuclei 的细胞类型才做
```
实测人脑 40 donors → 525,137 个 peak，宽度全部 501bp（getPeakSet GRanges 是闭区间 end-start+1=501，width=501 正常，勿误判为 500）。

## 猴脑 genomeAnnotation 核对（勿用人类 hg38）

猴（食蟹猴 T2T-MFA8v1.1）的 chromSizes 是 `NC_088375.1`–`NC_088395.1`（21 条，RefSeq accession 命名），不是 chr1-22。addGroupCoverages/addReproduciblePeakSet **不需要**显式 load BSgenome（Arrow 已存 genomeAnnotation），但绝不能用人类 hg38 包跑猴数据。