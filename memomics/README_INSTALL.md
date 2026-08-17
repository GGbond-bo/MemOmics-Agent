# MemOmics-Agent 安装指南

## 系统要求

| 组件 | 要求 | 必需？ |
|------|------|--------|
| Python | 3.11 - 3.13 | ✅ 必需 |
| R | >= 4.3.0 | 📊 生信分析需要 |
| NVIDIA GPU | 可选 | 🚀 大数据集加速 |
| 内存 | >= 16GB | 💡 推荐 32GB+ |
| 磁盘 | >= 5GB | 📦 程序+依赖 |

---

## 快速开始

### 一、安装

#### Linux / macOS
```bash
# 1. 解压
tar xzf MemOmics-Agent.tar.gz
cd MemOmics-Agent

# 2. 启动（自动创建 venv + 安装依赖）
chmod +x start.sh
./start.sh
```

#### Windows
```bat
:: 1. 解压
:: 2. 双击 start.bat
start.bat
```

### 二、首次配置

1. 启动后浏览器打开 `http://localhost:8899`
2. 首次访问会弹出 **API 配置向导**
3. 填入你的 LLM API 信息：
   - **Provider**: OpenAI (兼容) / Anthropic
   - **API Base URL**: 如 `https://api.deepseek.com/v1`
   - **API Key**: 如 `sk-...`
   - **Model**: 如 `deepseek-chat` / `gpt-4o`
4. 点击「开始使用」

> 也可以通过环境变量配置（见 `.env.example`），或直接编辑 `hermes_home/config.yaml`

### 三、环境检测

点击左侧栏底部「🔧 环境检测」，查看：
- Python / R 版本
- GPU 信息
- CPU / 内存 / 磁盘
- 已安装的 Python 和 R 包
- 缺失的包（R 包会在分析时自动安装）

---

## R 环境配置

### 安装 R

- **Linux**: `sudo apt install r-base` 或 [CRAN](https://cran.r-project.org/bin/linux/)
- **macOS**: `brew install r` 或 [CRAN](https://cran.r-project.org/bin/macosx/)
- **Windows**: [CRAN](https://cran.r-project.org/bin/windows/)

### R 包安装

MemOmics **不需要预装所有 R 包**。分析时遇到缺包会自动通过 `BiocManager::install()` 安装。

如果想预装核心包：
```r
install.packages(c("Seurat", "dplyr", "ggplot2", "patchwork", "future"))
if (!require("BiocManager")) install.packages("BiocManager")
BiocManager::install(c("glmGamPoi", "DESeq2", "SingleR", "harmony"))
```

完整 R 包清单见 `R_packages.txt`。

### 安装 BiocManager
```r
if (!require("BiocManager", quietly = TRUE))
    install.packages("BiocManager")
```

### GitHub 包（部分特殊包）
```r
if (!require("remotes")) install.packages("remotes")
remotes::install_github("chris-mcginnis-ucsf/DoubletFinder")
remotes::install_github("squarechapman/SoupX")
```

---

## 服务器 / 集群部署

### 基本部署

```bash
# 在服务器上
cd /opt/MemOmics-Agent
./start.sh 8080

# 远程访问
http://server-ip:8080
```

### 无外网集群

如果集群没有外网：

1. **R/Python 包**: 在有网的机器上准备好 conda 环境，传到集群
2. **文献检索**: `web_search` 功能需要外网。在本地电脑搜文献，结果传到集群
3. **知识库**: MemOmics 内置生信知识库，**离线可用**
4. **Skills**: 272 个 skill 模板已内置，**离线可用**
5. **API 调用**: 需要 LLM API 能从集群访问（如果集群有内网代理）

### SSH 端口转发

如果集群只允许 localhost 访问：
```bash
# 在本地电脑
ssh -L 8899:localhost:8899 user@cluster
# 然后本地浏览器打开 http://localhost:8899
```

### 多用户部署

每个用户独立运行自己的 MemOmics 实例：
```bash
# 用户各自启动在不同端口
./start.sh 8899  # 用户 A
./start.sh 8900  # 用户 B
```

---

## Web 搜索配置

MemOmics 支持多种 web 搜索后端（用于文献检索）：

| 后端 | 费用 | 需 API Key | 配置 |
|------|------|-----------|------|
| **ddgs** (默认) | 免费 | 否 | 无需配置 |
| tavily | 免费 1000次/月 | 是 | `TAVILY_API_KEY` |
| exa | 付费 | 是 | `EXA_API_KEY` |
| searxng | 免费 (自建) | 否 | `SEARXNG_URL` |
| brave-free | 免费 | 是 | `BRAVE_SEARCH_API_KEY` |

默认使用 ddgs（DuckDuckGo），零配置即可用。

---

## 配置文件

| 文件 | 作用 |
|------|------|
| `hermes_home/config.yaml` | LLM API + 全局配置 |
| `hermes_home/model_config.json` | 当前模型配置（首次向导写入） |
| `hermes_home/memories/USER.md` | 用户画像（自动学习） |
| `hermes_home/memories/MEMORY.md` | 记忆（自动积累） |
| `.env` | 环境变量（可选，见 `.env.example`） |

---

## 常见问题

### Q: 启动报错 "Python not found"
A: 安装 Python 3.11+，确保在 PATH 中。

### Q: R 分析报错 "there is no package called 'XXX'"
A: 正常，agent 会自动安装。如果自动安装失败，手动安装：
```r
BiocManager::install("XXX")
```

### Q: GPU 没有被检测到
A: 确保 `nvidia-smi` 命令可用。无 GPU 也能运行，只是大数据集较慢。

### Q: 端口被占用
A: `./start.sh 9000` 或 `set MEMOMICS_PORT=9000 && start.bat`

### Q: 如何切换模型
A: 左侧「⚙️ 设置」→ 选择模型。支持 DeepSeek / GPT / Claude 等。

### Q: 会话数据在哪
A: `hermes_home/state.db`（SQLite）+ `results/` 目录（分析结果）

---

## 技术支持

- 基于 [Hermes Agent](https://github.com/NousResearch/) 框架
- 内置 272 个生信技能模板
- 物种/组织/方向三维知识库
- 铁轨审查 + 多角色辩论机制

---
*MemOmics-Agent v2.0*
