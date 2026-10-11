# MemOmics-Agent

> **面向生物信息学的自主科研 Agent**：接入你的 API Key，用自然语言把科学问题变成完整分析流水线——从环境校验、数据读取、质控分析，到出版级图表与结论交付，全程自主执行、自主审查、自我纠错。同时，自主搭建知识库，查阅、提炼、翻译、引用文献，润色、设计文章，科研全方位一体。

[![Platform](https://img.shields.io/badge/平台-Windows%20%7C%20macOS-blue)](#下载与安装)
[![Python](https://img.shields.io/badge/Python-3.11%2B-green)](#系统要求)
[![R](https://img.shields.io/badge/R-4.2%2B-276dc3)](#系统要求)
[![Skills](https://img.shields.io/badge/生信技能-300%2B-orange)](#核心能力)

---

## 下载与安装

最新版本：**[v2026-10-11](https://github.com/GGbond-bo/MemOmics-Agent/releases/latest)**

| 你是谁 | 下载 | 怎么用 |
|---|---|---|
| 新用户（Windows） | `MemOmics-Windows.zip` | 解压 → 双击 `启动.bat` → 浏览器开 `http://127.0.0.1:8899` |
| 新用户（macOS Apple 芯片） | `MemOmics-macOS-arm64.tar.gz` | 解压 → `bash start_macos.sh` |
| 新用户（macOS Intel） | `MemOmics-macOS-x86_64.tar.gz` | 解压 → `bash start_macos.sh` |
| **老用户升级** | `MemOmics-update.zip` | 关闭程序 → 解压**整体覆盖旧目录**（脚本会先核对目录名）→ 重启，`.venv` 与 `memomics_home` 全部保留 |

> Linux / HPC 集群版按需单独发布；集群远程执行模块（`memomics/bio_tools/remote_cluster.py` + WebUI「🖥 集群」面板）随包提供，可直接对接你的跳板机/计算节点。

### v2026-10-11 更新要点

- **凭据全链路脱敏**：设置页、`/api/models/*`、`/api/usage/*` 一律只回显 `sk-****` 掩码，明文密钥不再出现在任何接口响应里
- **云平台绑定三态**：点「绑定」后按钮进入“正在绑定中…”，成功/失败都有明确结论与失败原因（失败落盘 `dcs_last_error.txt`，令牌已脱敏）
- **集群密钥自动化**：自动探测 `~/.ssh/id_*`；本机一把都没有时点安装会自动生成一对 ed25519 再装，不再报「找不到公钥文件」
- **旧缓存自动清理**：前端用 `ui_build` 指纹识别版本变更，自动清理 theme/背景/片头等本地缓存，升级后不会停在旧界面
- **包内零个人路径**：所有开发机路径/用户名在打包时统一清洗为 `<安装目录>`

---

## 它是什么

MemOmics-Agent 是一个以 [Hermes](https://github.com/NousResearch/hermes-agent) Agent 框架的工具层为底座、专为组学数据分析打造的自主科研 Agent。你只需要给出**数据路径 + 科学问题**，它会自主完成：

```
加载技能 → 环境校验 → 执行前审查 →（必要时）多角色辩论
→ R/Python 持久内核执行 → 执行后审查 → 经验沉淀 → 结果交付
```

- **你负责提问，它负责把活干完**：长任务后台运行 + 心跳监督，跑完自动汇报
- **任务全程留痕**：每步写磁盘任务账本（task_plan.md），崩溃/重启后可恢复续跑
- **不会撒谎的审查**：执行前查依赖环境、执行后查产出文件，任一不达标都会拦住并要求修复后再交

## 核心能力

| 方向 | 内容 |
|---|---|
| scRNA-seq | QC / CellBender 去背景 / 归一化 / 聚类 / 注释 / 轨迹 / 细胞通讯 / SCENIC 调控网络 |
| scATAC-seq | ArchR 全流程（Arrow → QC → 降维 → Peak Calling → Motif） |
| 空间转录组 & Bulk | 空间降维与注释；Bulk RNA 差异表达与富集 |
| 多组学 | 代谢组 / 蛋白组 / 微生物组 / 表观（甲基化、ChIP-seq） |
| 统计与检验 | t-test / Wilcoxon / 回归 / 相关性 + BH-FDR 多重校正，自动选择正确方法 |
| 出版级可视化 | UMAP / 热图 / 火山图 / 小提琴图 / 箱线图，CNS 风格排版，300dpi PNG/SVG/PDF |
| 文献与知识库 | 文献导入 / 翻译 / 提取 / 整理；证据链分级（L0–L3）；物种 × 组织 × 方向三维知识库随用随查 |
| 云与集群 | DCS 云（项目/数据/任务/投递/下载队列）、远端集群（跳板机、免密安装、远程作业） |

**400+ 生信技能模块**：每个分析方向都有成文操作规程（参数铁律、已知坑位、验证清单），Agent 按技能执行而不是自由发挥。

## 架构亮点

1. **审轨（rail_review）**：执行前 pre 审查（skill 加载、依赖包真实可用、参数合规）+ 执行后 post 审查（产出文件存在且非空、代码完整、结论有效）。环境检查**多库自动发现**，不再误报。
2. **辩论门控（debate_analysis）**：高影响结论/入库/出报告前触发多角色辩论（L0-L2 三级，按风险分级），防止「看似合理实则错误」的结果溜过去。
3. **持久内核**：`execute_r` / `execute_python` 同会话常驻 R/Python worker——几十 GB 对象读一次常驻内存，后续步骤秒级热调用，不再反复 readRDS。
4. **自愈监督（看门狗）**：以**进程级 CPU / 内存 / IO 证据**区分「真在算」「真卡死」「网关挂起」——几十万细胞的长时间计算绝不误杀；进程真冻结时自动唤醒 Agent 诊断并解决，而不是摆烂。Windows/Linux 统一实现。
5. **长任务全托管**：CellBender 批量等 >30 分钟任务自动后台运行 + 心跳监控（三源交叉验证），完事即报；任务类型（普通/长任务）自动判别、设施自动配齐。
6. **完成即停**：任务完成后自动归档 + 停止自检唤醒，不烧多余 token；进行中则持续监督。
7. **三层长期记忆**：L1 常驻注入（用户铁律/高频经验）→ L2 向量检索注入 → L3 归档永不删除，自动打分流转，长会话不爆内存、经验不丢失。
8. **会话持久化**：state.db 存全部消息与工具调用，重启/重连后无缝续聊。
9. **一键更新**：WebUI 内检查更新 → 下载 update 包 → 覆盖代码并保留用户数据；更新前自动核对安装目录名。
10. **旧安装自愈（fix bundle）**：升级后首次启动自动迁移配置级修复，无需手动处理。

## 快速开始

### Windows（开箱即用）

1. 下载 `MemOmics-Windows.zip`，解压（路径不含中文为佳）
2. 双击 `启动.bat` —— 首次自动装依赖（Python 缺失时自动装内置 Miniconda）
3. 浏览器打开 `http://127.0.0.1:8899`
4. 左侧「⚙️ 设置」填入 API Key（DeepSeek / GPT / Claude 等 **任意 OpenAI 兼容网关**）
5. 开始提问，例如：

```
"D:\my_data\scores_meta.csv 里面有我的 AUCell 打分，
 样本名是 samplename，组别是 type，帮我可视化一下这些分数"
```

### macOS

```bash
tar -xzf MemOmics-macOS-arm64.tar.gz && cd MemOmics && bash start_macos.sh
```

## 隐私与数据

- **安装包内不含任何开发者个人信息**：无本机路径、无用户名、无密钥、无文献库/知识库内容（`memomics_home` 只带技能与空白骨架）
- **你的密钥只存本机**：写在你自己的 `memomics_home/`（`config.yaml` / `provider_keys.json` / `dcs_cloud.json` 等），不会上传，也不会被接口明文回显（一律 `sk-****` 掩码）
- **文献库与知识库从空开始**：随包不带任何论文与知识条目，全部由你自己导入/积累
- **片头与背景为默认状态**：安装即默认外观（无片头、浅色背景），可在设置里自行调整

## 系统要求

| 组件 | 要求 | 说明 |
|---|---|---|
| Python | 3.11 – 3.13 | 首启自动建 venv + 装依赖（Windows 包已内置独立运行时） |
| R | ≥ 4.5（可选） | Seurat / ArchR 等 R 分析需要 |
| 内存 | ≥ 16GB（推荐 32GB+） | 单细胞大对象分析 |
| GPU | 可选 | CellBender 等去污染大幅加速 |

## 目录结构

```
MemOmics/
├── memomics/            # 领域核心：分析工具、知识库、控制平面、进程监控
├── webui/               # Web 服务：会话、审查门禁、自愈看门狗、任务状态机
├── hermes-agent/        # Agent 底座：Hermes 框架工具执行器、持久内核、记忆
├── memomics_home/       # 技能库(400+) / 记忆 / 文献 / 会话数据库（用户数据区）
├── results/             # 每个会话的分析结果（独立目录）
├── launchers/           # 各平台启动器与 systemd 服务模板
├── 启动.bat / start_macos.sh / start_linux.sh
├── update_windows.ps1 / update_windows.bat / update_macos_linux.sh
└── scripts/             # 环境校验、修复迁移等自愈脚本
```

## 升级旧安装

下载 `MemOmics-update.zip` → 关闭旧程序 → 解压**整体覆盖旧目录**（注意先核对解压出的目录名与你的安装目录名一致，脚本也会自动匹配）→ 重新启动。
`memomics_home`（API 配置/会话/记忆/技能）、`results/`、`.venv` 全部保留；首次启动自动执行修复迁移；底部状态栏可核对 `fix_bundle` 版本号。详见 `README_INSTALL.md`。

## 常见问题

- **支持哪些模型 API？** 任意 OpenAI 兼容接口（DeepSeek、GPT、Claude、本地 vLLM 等），WebUI 设置页切换。
- **端口被占用？** `启动.bat 9000` 换端口，或结束旧实例后重启。
- **提示「执行保护」拦截？** 这是审轨在把关：先让 Agent 按要求修正环境/参数，重跑 `rail_review` 通过即放行；或直接发新消息重置本轮审查状态。
- **任务卡住不动？** 系统会按进程 CPU/内存/IO 自动判断是「在算」还是「卡死」；真卡死会自动唤醒 Agent 诊断处理。
- **升级后界面还是旧的？** 刷新一次页面即可（前端会自动比对构建指纹并清理旧缓存）。

## 技术栈与致谢

- [Hermes](https://github.com/NousResearch/hermes-agent) Agent 框架（MIT，© Nous Research）：MemOmics 借用其**工具层**（工具执行器 / 持久内核 / 会话与记忆原语），源码 vendor 于 `hermes-agent/`，其 LICENSE 保留在该目录。WebUI、运行逻辑（审轨/看门狗/长任务托管）与生信工具链为 MemOmics 自研。
- [LoopX](https://github.com/) 控制平面（MIT，vendor 于 `memomics/vendor/loopx`）
- Seurat / Scanpy / ArchR / data.table 等社区生信生态

## License

本仓库整体以 MIT 发布（见 [LICENSE](LICENSE)）；`hermes-agent/` 与 `memomics/vendor/loopx` 等 vendor 组件分别遵循其原始许可，版权归各自作者所有。