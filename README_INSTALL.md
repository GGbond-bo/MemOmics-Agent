# MemOmics 安装指南（v2026-10-09）

MemOmics 是一个跑在**本机**的组学分析 Agent：自带 WebUI、技能库、文献库与知识库，
所有数据留在你自己的电脑/服务器上。

---

## 一、包与安装

| 包 | 用途 |
|----|------|
| `MemOmics-Windows.zip` | Windows 完整包（内置 Python + Miniconda，**不需要预装环境**） |
| `MemOmics-macOS-arm64.tar.gz` | Apple 芯片 Mac 完整包（M1/M2/M3/M4） |
| `MemOmics-macOS-x86_64.tar.gz` | Intel 芯片 Mac 完整包 |
| `MemOmics-update.zip` | **老用户更新包**（只有代码，几分钟装完，不动你的数据/环境） |

解压后目录名就是 **`MemOmics`**；你可以把它改成任何名字（如 `MemOmics-Agent`、`MemOmics-2`），
更新与启动都不依赖目录名。

### Windows

```bat
:: 1. 解压 zip（目录名随意）
:: 2. 双击 启动.bat（首次会自动安装内置 Miniconda 与依赖，需要几分钟）
:: 3. 浏览器打开 http://localhost:8899
```

### macOS

```bash
tar xzf MemOmics-macOS-arm64.tar.gz       # Intel 用 -x86_64
cd MemOmics
chmod +x start.sh                          # 首次需要可执行权限
xattr -dr com.apple.quarantine .           # 若被 Gatekeeper 拦（"已损坏"/"无法验证开发者"）
./start.sh
```

### Linux / 服务器 / 集群

```bash
tar xzf MemOmics-Linux.tar.gz
cd MemOmics && chmod +x start.sh && ./start.sh          # 默认 8899 端口
./start.sh 9000                                        # 或指定端口
# 常驻（服务器）：参考 launchers/memomics.service（systemd）
```

首次启动会自动创建 Python 环境；**R 不需要预装全部包**，分析缺包时会自动安装。

---

## 二、首次配置

1. 浏览器打开 `http://localhost:8899`
2. 按向导填 LLM API（Provider / Base URL / API Key / Model，例如 DeepSeek 的
   `https://api.deepseek.com/v1` + `deepseek-chat`）
3. 左侧栏底部「环境检测」可随时查看 Python / R / GPU / 磁盘与缺包情况

也可以直接编辑 `memomics_home/config.yaml`，或走「设置」面板。

---

## 三、默认设置（新装就是这样）

- **片头动画：关闭**（想开：侧栏「🎬 片头设置」）
- **界面：浅色主题、无背景图**（想换：设置里的主题 / 背景）
- **文献库、知识库：空的** —— 导入你自己的文献（PDF/DOI）后即可检索、提问、写作
- **技能库：只带产品自带技能** —— 你自己沉淀的技能、脚本、笔记不会随包分发；
  想扩展可以从「技能库」在线安装或自己创建（`create-bio-skill`）

---

## 四、更新（重要：目录名不用匹配）

**方式 1（推荐）：让 MemOmics 自己更新**
打开 MemOmics →「检查更新」→ 一键应用 → 按提示重启。
它会把更新包覆盖到**当前正在运行的那份代码所在目录**，目录名是什么都能更新成功。

**方式 2：手动覆盖**
1. 下载 `MemOmics-update.zip`，解压得到 `MemOmics/` 文件夹
2. 用包内脚本（自动定位安装目录、只覆盖代码、跳过你的数据、不删任何文件）：
   - Windows：双击 `update_windows.bat`
   - macOS/Linux：`chmod +x update_macos_linux.sh && ./update_macos_linux.sh`
3. 或手工把解压内容复制进安装目录（"全部覆盖"），**注意不要覆盖 `memomics_home` 里的
   `config.yaml` / `state.db` / `memories` 等用户数据**
4. 重启 MemOmics

- 更新说明详见包内 `更新说明.txt`
- 旧版本（≤ v2026-09-10）的数据目录叫 `hermes_home`：首次启动会**自动迁移**为
  `memomics_home`（只搬不删，旧目录改名为 `hermes_home.migrated_<时间戳>` 备份）
- 更早的更新包根目录曾叫 `MemOmics-update`，解压出的那个文件夹可以删掉，不影响使用

---

## 五、常见问题

| 现象 | 处理 |
|------|------|
| Windows 双击没反应 | 右键「以管理员身份运行」；或查看 `log/` 下的启动日志 |
| macOS 提示"已损坏" | `xattr -dr com.apple.quarantine .` 后重试 |
| 端口被占用 | `./start.sh 9000` 换端口；Windows 改 `启动.bat` 里的端口或设环境变量 `MEMOMICS_PORT` |
| 浏览器打不开 | 确认命令行窗口没有报错；确认访问的是 `http://localhost:8899` |
| R 包安装慢/失败 | 配置国内镜像 `options(repos=...)`；或在「环境检测」里逐个安装 |
| 想迁移机器 | 整个程序目录拷走，再单独拷 `memomics_home`（配置+记忆+文献） |

---

## 六、目录结构速查

```
MemOmics/
├── 启动.bat / start.sh          # 启动入口
├── start_macos.sh / start_linux.sh
├── webui/                       # WebUI 与后端
├── memomics/                    # 分析引擎
├── hermes-agent/                # Agent 框架
├── python/ miniconda/           # 内置运行环境（仅完整包）
├── memomics_home/               # 你的数据：配置、记忆、会话、文献、技能、知识库
│   ├── config.yaml              # API 配置（含密钥，勿外传）
│   ├── papers/                  # 文献库（默认空）
│   ├── knowledge_base/          # 知识库（默认空）
│   └── skills/                  # 技能库
└── 更新说明.txt / update_*.bat/sh   # 更新用说明与脚本
```

## 七、发布与反馈

GitHub: <https://github.com/GGbond-bo/MemOmics-Agent> （Releases 页有各平台安装包与 SHA256）