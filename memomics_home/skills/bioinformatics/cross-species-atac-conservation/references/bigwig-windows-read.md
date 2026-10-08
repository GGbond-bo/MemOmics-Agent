# L1 本地 bigWig 读取：Windows 工具链实测（2026-08-30）

## 背景

L1 序列保守性需要给 100 万级 peak（human 525,137 + monkey 538,420）在 phyloP/phastCons bigWig 上批量打均值。
23GB 保守性资源落盘 `E:/专利/L1_resources/`（`hg38.phyloP100way.bw` 9.87GB / `hg38.phastCons100way.bw` 5.89GB / `hg38.phyloP30way.bw` 8.40GB），
下载脚本 `E:/专利/P3_L1_data/download_l1_resources.py`（URLLib 分块 + progress 日志 + md5 校验：`43858006bdf98145b6fd239490bd0478`）。

## 工具链决策矩阵（全部实测）

| 方案 | 结果 | 备注 |
|------|------|------|
| `pip install pybigwig` | ❌ 无 Windows wheel，源码编译缺 C 编译器 | PyPI 只有 Linux/macOS 编译产物 |
| R `rtracklayer` `BigWigFile()/summary()` | ❌ Windows 报 `UCSC library operation failed` | rtracklayer 在 Linux 上可用，Windows 缺 kent library 二进制（两次实测） |
| 手写纯 Python bigWig 解析 | ⚠️ 半通：header/B+tree magic 正确，fullData 布局推断错 | 不值得继续（见下方 header 布局），先找现成工具 |
| ~~`conda install -c conda-forge pybigwig`~~ | ❌ **实测失败（2026-08-30）** `PackagesNotFoundInChannelsError: pybigwig not available from current channels` | ⛔ **本文件曾误标"✅ 正解"，错。conda-forge win-64 无 pybigwig** |
| UCSC 命令行 `bigWigAverageOverBed` | ❌ 无 Windows 官方二进制 | Linux/WSL 上是最优批量工具 |
| **R `bigWig` 包编译（risserlin/bigWig，自带 libBigWig C 库）** | ⚠️ **未尝试——Windows 最有望** | 本机有 Rtools45，`install.packages("bigWig", repos=NULL)` 或 `pak::pak("risserlin/bigWig")` 试编译 |
| **装 WSL 后 Linux pybigwig** | ⚠️ 未尝试 | 标准路（Linux 有 wheel），但要下载发行版+重启电脑；`wsl.exe --status` 输出 UTF-16LE 需转码，未安装时提示 exit=50 |

**Windows 读 bigWig 定论（2026-08-30）**：pip ❌ + conda-forge ❌ + rtracklayer ❌ + 手写 ❌ → **本机无现成读取路径**；只剩 R `bigWig` 包编译（最有望）/ WSL / 集群三选一，选哪条先问用户。

## bigWig 二进制布局（手写解析会踩的坑）

- **header offset 字段是 uint64，从第 8 字节开始**：0-3 magic(0x888FFC26), 4-5 version, 6-7 zoomLevels,
  8-15 chromTreeOffset, 16-23 fullDataOffset, 24-31 fullIndexOffset, 32-33 fieldCount ...
  误用 4 字节 / 从 24 字节读，会得到 chromTreeOffset=344 但 fullDataOffset=0 的错乱结果。
- 大文件（>4GB）：chromTreeOffset 可落在 7.6GB 处；fullIndexOffset（~7.6GB）是索引区起点，不是数据起点。
  `fullDataOffset`(24196) → fullIndexOffset 之间才是顺序排列的数据块。
- B+ tree magic = 0x78CA8C91（344 处验证通过）；blockSize/keySize/valSize/itemCount 各 1 字节在 magic 后。
- 数据块 header 24 字节（chromId/start/end/itemStep/itemSpan/type/reserved/itemCount），type 1=bedGraph/2=varStep/3=fixedStep ——
  但**手写按 24 字节顺序扫描读出的 chromId 全乱**（如 2897730），说明布局推断有偏差，不再深挖（现成工具已通）。

## 判断流程（下次遇到"读不了 bigWig"）

1. **先确认操作系统**：Linux/macOS/WSL → `pip install pybigwig`（有 wheel）✅；Windows → pip ❌ + conda-forge ❌，直接跳第 4 步三选一
2. 不要花超 30 分钟手写解析器；header 对齐可以用 hexdump 确认，但全量数据块解析交给现成库
3. UCSC hgdownload 只提供 .bw + .mod（无文本 bedGraph 替代），必须解析二进制
4. **Windows 剩余选项（问用户选）**：① R `bigWig` 包源码编译（本机 Rtools45，最快试）② 装 WSL 用 Linux pybigwig（标准，要重启）③ 回集群跑（数据/工具在集群时）