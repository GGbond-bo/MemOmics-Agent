---
name: imagej-analysis
description: ImageJ/Fiji 图像定量：本机或集群路径配置、图片上传、CZI/LIF/ND2 转换、肌纤维 CSA、颗粒计数与阳性面积占比。触发：ImageJ/Fiji/肌纤维横截面/CSA/MinFeret/细胞核计数/胶原面积/CZI/Bio-Formats。
when_to_use: 用户要用 ImageJ/Fiji 做显微图像定量、批量图像分析、肌纤维横截面测量、核/颗粒计数、阳性面积占比，或要把 CZI/LIF/ND2/VSI 转成 TIFF 时加载。
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  memomics:
    tags: [imagej, fiji, bioformats, microscopy, muscle, csa, segmentation, particle-analysis]
    difficulty: intermediate
    language: Python+ImageJ-Macro
    category: bioinformatics
---

# ImageJ 图像定量（本机 / 集群）

> 统一走 `imagej` 工具。它负责宏渲染、执行、产物回收、µm 换算、验收闸和 manifest；不要用 Python/PIL 重新实现 ImageJ 的阈值、分水岭或 Analyze Particles。

## 1. 用户准备

1. 左侧「⚙️ 设置」→ 展开「🔬 ImageJ 图像分析」。
2. 本机：填 ImageJ/Fiji 安装目录（含 `ImageJ.exe` / `Fiji.exe` / `ij.jar`），点「检测本机」。
3. 集群：先在「远端集群」建立连接，再填集群/节点/安装目录，点「检测集群」。
4. 可选：设置本机上传目录、本地保存目录、集群作业目录；保存时创建本机目录，集群目录在首次作业时创建。
5. 回到对话页，点亮右下角 **ImageJ** 开关。此开关只影响当前会话；每回合都会重新注入路径、插件快照和方法目录，关闭后不再注入。

## 2. 图片怎么进来

- **本机图片**：设置页点「📷 选择并上传图片」，支持多选与 TIFF/CZI/LIF/ND2/VSI；上传后绝对路径自动填入输入框。
- **聊天区 +**：选择本机文件/文件夹会插入绝对路径，也可直接作为 `input`。
- **集群已有图片**：直接给远端绝对路径或 glob，例如 `/data/fields/*.tif`。
- **本机图片 + 集群计算**：直接把本机路径给 `imagej(backend="cluster")`，工具会通过 `remote_cluster` 自动 SFTP 到作业目录；不要要求用户先手工上传。
- 厂商格式先用 `op="bf_convert"` 转 TIFF；装了 Bio-Formats 时可自动读取 `px_um`，manifest 的 `px_um_source=bf_metadata`。

## 3. 可用方法

| op | 用途 | 常用参数 |
|---|---|---|
| `csa` | 肌纤维横截面 CSA、Feret、MinFeret、圆度、纤维数 | `px_um, channel, threshold, smooth, invert, watershed, min_area_um2` |
| `count_objects` | 核、毛细血管及其他颗粒计数与密度 | 同上，另有 `min_circ, max_circ` |
| `area_fraction` | 胶原、DAB 或荧光阳性面积占比 | `px_um, channel, threshold, smooth, invert` |
| `bf_convert` | Bio-Formats 厂商格式转 TIFF | `channel`（0=全部），`px_um`（0=自动） |

方法目录以 `imagej(action="ops")` 的实时返回为准；缺插件时 `available=false`，不要用别的工具伪造结果。

## 4. 标准流程

```python
imagej(action="probe", backend="cluster")
imagej(action="ops", backend="cluster")
imagej(action="run", backend="cluster", op="csa",
        input="/data/S01_laminin.tif",
        params={"px_um": 0.5, "threshold": "Otsu", "smooth": 1.5,
                "watershed": True, "min_area_um2": 100})
imagej(action="batch", backend="cluster", op="csa",
        input="/data/fields/*.tif", params={"px_um": 0.5})
imagej(action="summarize", run_id="<batch 返回的 run_id>")
```

- 先单图：看 `outlines.png` 与指标，确认识别正确后再批量。
- 没给 `px_um` 且读不到标定：只报告像素值，不能编造 µm 数值。
- `gate_failed` 不是可用结果：读 `manifest.json` 的 `checks` 和 `console_tail`，调参后重跑。
- 结果汇报必须给 `run_id`、保存目录、逐图对象数/面积中位数与 manifest 路径。

## 5. CopilotJ 参考库（已本地化）

本技能的宏观设计参考了 [neurogeom/CopilotJ](https://github.com/neurogeom/CopilotJ)，并已把其知识库固定到
commit `3fcd9877e8898e1f3f65a2b8dd22f998f0ade18c` 导入本目录 `references/copilotj/`：

- 29 条宏/插件语法参考（`knowledge_bank/macro/`）
- 32 条任务配方（`knowledge_bank/task/`）
- 13 条研究/排错笔记（`knowledge_bank/research/`）

查入口：`references/copilotj/INDEX.md`；许可证：`LICENSE.apache-2.0`。
这些是**编写宏与排错时的参考资料**，不是已安装插件；其中出现的 TrackMate、Coloc 2、CLIJ2 等仍需单独安装并新增 op 后才能执行。
没有整合 CopilotJ 的 Fiji Bridge、MCP Server 或 Python 多智能体运行时——那条路线要求 GUI Fiji + Java 17+，与本技能的无人值守批处理不同。

## 6. 当前边界

- 集群已装 Bio-Formats 7.3.1；本机是否安装以「检测本机」为准。
- 当前四个 op 覆盖常规阈值分割与测量，不等于已装齐 Fiji 全部插件；TrackMate、Coloc 2、StarDist 等需要另行安装与新增 op。
- 集群 SGE/qsub 当前不可用，批量作业顺序执行；每个作业独立 DISPLAY、目录与超时。