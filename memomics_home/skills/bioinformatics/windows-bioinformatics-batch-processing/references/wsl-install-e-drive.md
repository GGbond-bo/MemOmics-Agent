# WSL 安装到非 C 盘（E:\WSL）+ 首次初始化（实测 2026-08-31）

## 场景
Windows 生信工具缺平台支持（pyBigWig / rtracklayer libBigWig / bigWigAverageOverBed 全部只有 Linux/macOS）→ 需要 WSL 提供 Linux 跑 bigWig 打分等。用户指定装到 E 盘（磁盘充裕，C 盘不落经验数据）。

## 安装流程（需管理员 → 弹 UAC 用户点"是"）
1. 写安装脚本 `E:\wsl_install.cmd`（普通用户可写 E 盘）：
```cmd
@echo off
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Lxss" /v BasePath /t REG_SZ /d "E:\WSL" /f
dism /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
wsl --install -d Ubuntu
echo ===DONE===
```
2. 提权运行（不 -Wait，立即返回，随后轮询日志）：
```
powershell.exe -NoProfile -Command "Start-Process cmd.exe -Verb RunAs -ArgumentList '/c','E:\wsl_install.cmd > E:\wsl_install.log 2>&1'"
```
   - **日志必须放 E 盘（或普通用户可读处）**：管理员写的 C:\ 根文件普通用户读不了，轮询会失败
3. 轮询 `tail E:/wsl_install.log`：功能启用两个 100% → wsl --install 下载（几分钟）→ `===DONE===`
4. 验证安装：`wsl.exe --list` （UTF-16LE，见坑 4）；`reg query HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Lxss /s` 看发行版注册详情（Version=2=WSL2、BasePath、OOBE 状态）；`du -sh /c/Users/<user>/AppData/Local/wsl/` 确认镜像非空

## ⛔ 坑 1：HKLM BasePath=E:\WSL 对 store 版 WSL 不生效！
- 注册表确实写入了（`reg query HKLM\...\Lxss` 能看到 BasePath=E:\WSL），但 **Ubuntu 发行版仍装到 `C:\Users\<user>\AppData\Local\wsl\<guid>\ext4.vhdx`**（store 版 WSL 2.7.x 用自己的路径管理，HKLM BasePath 是老流程）
- 验证：HKCU 的发行版条目 BasePath = `C:\Users\23136\AppData\Local\wsl\{guid}`（本机实测 1.4GB）
- **迁移 E 盘必须在发行版可用后**（完成后或重启后）：
  `wsl --shutdown` → `wsl --export Ubuntu E:\ubuntu-backup.tar` → `wsl --unregister Ubuntu` → `wsl --import Ubuntu E:\WSL\Ubuntu E:\ubuntu-backup.tar --version 2` → 删 tar
- 不要在 OOBE 未完成时做 export/import（vhdx 正在被写/锁）

## ⛔ 坑 2：OOBE 锁死发行版 — root 也进不去
- `wsl --install -d Ubuntu` 下载注册后触发首次初始化（"Create a default Unix user account"），**只要 OOBE 未完成，发行版被锁**：
  - `wsl -d Ubuntu -u root -- whoami` 挂起超时（即使 -u root）
  - `wsl --shutdown` 也挂起（OOBE 持有 WSL 服务）
- 无法从代理侧绕过。两条路：
  ① 提示用户看屏幕上的提权 cmd 窗口，输入"用户名+回车 → 密码+回车"（日志会继续写，如尾行 `Create a default Unix user account: <输入>` 后出现 "may take a while"）
  ② 放弃交互 → 告知用户重启后自己运行 `wsl` 完成初始化（正常交互，~30 秒）
- 提权上下文的卡死进程普通权限杀不掉（`Stop-Process -Force` 也拒绝，SilentlyContinue 吞错后进程还在）→ 别浪费时间，留给重启复位

## ⛔ 坑 3：git-bash 杀进程的 MSYS 转义
- `taskkill //F //PID 1234` → 报"无效参数/选项 - '//F'"（MSYS 把 `//F` 原样传，没按预期转 `/F`）
- 正确：`powershell.exe -NoProfile -Command "Stop-Process -Id 1234 -Force -ErrorAction SilentlyContinue"`（普通进程可杀；管理员上下文进程会被拒，此时等重启）

## ⛔ 坑 4：日志/output 编码（UTF-16LE + GBK 混排）
- `wsl --install` 输出 UTF-16LE（进度条 `[===71.8%===]`）+ cmd echo 中文 GBK → 直接读乱码
- 清洗：`tr -c '[:print:]' '\n' < log | grep -v '^\s*$' | tail -15`（提取 ASCII 结构/数字看进度）；UTF-16 段用 `tail -c 800 log | iconv -f UTF-16LE -t UTF-8`
- `wsl.exe --list` 输出也是 UTF-16LE：`wsl.exe --list 2>&1 | iconv -f UTF-16LE -t UTF-8 | tr -d '\0'`

## 安装产物（2026-08-31 本机实测）
- WSL2 store 版 2.7.12.0（C:\Program Files\WSL\）+ Ubuntu 26.04 注册（Version=2）
- vhdx 1.4GB：`C:\Users\23136\AppData\Local\wsl\1fb83261-d85b-441f-a959-737a7a7c481d\ext4.vhdx`
- 脚本 `E:\wsl_install.cmd`、日志 `E:\wsl_install.log`
- 重启后待办：① 完成 Ubuntu 初始化（用户 `wsl` 建账户）② 迁移 C→E:\WSL\Ubuntu（export/import）③ `pip install pybigwig` 跑 L1 打分

## 相关
- 跨物种专利 L1 phyloP 打分 → `cross-species-atac-conservation`（references/bigwig-windows-read.md、bigwigaverageoverbed-usage.md）