# 后台命令监督纪律 + ArchR 安装连环坑（2026-08-09 会话实测）

## 用户铁律：后台命令必须主动盯 — 不许 fire-and-forget

用户多次纠正："你都不监督的？""你要盯着啊，报错了你不解决怎么办？"
**这是用户对 Agent 最长期的不满** = 启动后台命令（安装/构建/下载/批处理）后不主动 poll，
进程死了也不知道，等用户问"装好了吗/还在跑吗"才发现。

### 执行模型真相（用户问"为什么不会一直盯着"时的诚实解释）

本 Agent 是请求-响应模型，两次消息之间不存活：
- `notify_on_complete` 只在 Agent"醒着等通知"时生效
- 用户新消息会开启新 turn，吞掉旧通知
- **唯一可靠的监督手段 = 每个 turn 开头主动 process(list)/poll**，把"查后台状态"做成习惯动作

### 分任务类型做法

| 任务类型 | 正确做法 |
|---------|---------|
| 安装/构建（ArchR 等，5-40min）| **优先 foreground + 大 timeout（600s）分步盯着跑**——每步看报错→补依赖→下一步；必须 background 时 `notify_on_complete=true` + **下一个 turn 开始就 process(poll)** |
| 下载（GB 级，>10min）| background + notify + 断点续传循环；中途至少 poll 一次确认进程活着、文件在增长 |
| 批处理（40 样本级）| 部署独立 watchdog/heartbeat + bridge 兜底（见 batch-concurrency-monitoring-pitfalls.md），**每次唤醒 turn 第一步先查** |

## ArchR 安装连环坑（2026-08-09，后台装 6+ 次静默死）

后台 `terminal(background=true)` 装 R 包进程 segfault/exit 1 时**无任何通知**，
Agent 直到用户问才发现——6+ 次重复踩同一坑。修复模式：

### 装通 R 4.5.3 + ArchR 1.0.3 的真实顺序（Windows）

1. 装 R 4.5.3 到独立目录（不和 4.4.2 冲突，不勾"加入系统 PATH"）
2. 复用 Rtools44 的 gcc（Rtools45 装不上时）：`cmd /c mklink /J C:/rtools44 C:/rtools44` 或 PATH 里补 ucrt64/bin
3. `.libPaths` 隔离：每个 R 版本独立库，脚本顶部显式 `.libPaths(c('USER_R_LIBS/R-x.y.z', .libPaths()))`
   - ⚠️ 本会话 R 4.6.1 被 `~/.Rprofile` 硬编码劫持到 R-4.4.2 库 → 装包全装错位置，根因 = 修 .Rprofile 按版本分派
4. BiocManager（清华 CRAN 镜像 + Westlake Bioconductor 镜像）
5. 依赖链逐个装并验证：TFMPvalue（需 R≥4.5）→ TFBSTools → motifmatchr → chromVAR → BSgenome → DirichletMultinomial → nabor → ggplot2/plotly/dplyr 生态 → BSgenome.Hsapiens.UCSC.hg38（697MB）
6. ArchR GitHub 本体（依赖装齐后 2 分钟）
- bash(MSYS) 下 R 4.5.3 segfault（信号处理冲突）→ 用 `cmd.exe /c` 或全路径 Rscript 绕过
- 装包连锁缺依赖（devtools→usethis→magrittr）→ 逐个装并验证，不要一次装一串
- 前台 `Rscript -e 'parse("x.R")'` 可验证 R 脚本语法，比整跑快

### 本会话踩过的具体死路（避免重试）

| 路径 | 结果 |
|------|------|
| R 4.6.1 + Bioc 3.23（无 Rtools46）| 🔴 GitHub 包编译死路 |
| R 4.4.2 + Bioc 3.20 | 🔴 TFMPvalue 需 R≥4.5 死路 |
| `install_github` 已废弃 | 🔴 用 `pak::pak()`（用户偏好）|
| Rtools45 官网 URL 猜错 | ⚠️ 下到 992B 网页 → 正确文件从 CRAN 镜像站 |
| 后台装不盯 | 🔴 静默死 6+ 次 |

## 用户偏好要点

- 用户技术强、能分辨 Agent 是查了还是猜了——安装路径必须实测，不能编
- 用户不接受"正在后台安装"这种声明后不检查的做法——说出口就要有 process(poll) 佐证
- 报错不可怕，可怕的是不报——失败必须立即报告根因
