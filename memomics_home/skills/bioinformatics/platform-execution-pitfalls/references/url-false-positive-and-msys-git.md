# 会话要求块误报 + Windows git-bash 路径/克隆回退（2026-10-12 实测）

## 一、会话要求块把 URL 报成「路径不存在」——误报，别去核实

**现象**（本轮真实注入文本）：
用户消息里给了 `https://github.com/org/repo.git`，系统注入的「会话要求」块却写：

```
⚠️ 以下要求中的路径不存在，请向用户核实是否已更新/作废：
https://github.com/org/repo（用户已确认但路径不存在，请立即向用户核实！）
```

**根因**：那是**通用路径存在性检查器**（不是针对本次消息的语义判断）把该条目当磁盘路径去
`os.path.exists()` —— URL 当然不在磁盘上。

**判定**：**任何带协议前缀的条目一律是误报** —— `https://` / `http://` / `git@` / `ftp://`。
真路径告警（盘符、`results/...`）才需要处理。

**对策**
1. **不要**因为这条告警去问用户"这个路径是不是作废了" —— 白烧一整轮，用户会答"那是网址"。
2. 以**用户最新一条消息**里的 URL/路径为准；历史条目只是背景上下文。
3. 用户中途纠偏 URL（"说错了，是这个 &lt;另一个仓库&gt;"）时，**前一个目标的全部调研结论整体作废**，
   不复用、不合并、不"兼容考虑"。

**本轮实测代价**：收到第一个仓库 URL 后，先花了几轮查它的安装要求（OS 支持矩阵、wheel 平台、
GPU/驱动版本），用户更正为另一个仓库后那些结论**全部作废**。
正确动作：一旦发现目标可能是错的，**先花一次工具调用确认仓库身份（README/描述/技术栈）再深入**，
身份确认后再做完整调研 —— 比"先深挖再被纠正"省一半。

---

## 二、git-bash 下 `git -C /e/...` 必失败 —— 改用子 shell `cd`

**现象**：helper 脚本里写 `git -C "$REPO" log -1`，而 `$REPO=/e/MemOmics-Agent/third_party/CRL`
（MSYS 形态）→

```
fatal: cannot change to '/e/MemOmics-Agent/third_party/CRL': No such file or directory
```

**根因**：git-for-windows 是**原生 Win32 程序**，不认 MSYS 的 `/e/` 形路径（它要 `E:/` 或 `E:\`）。
路径由 shell 展开传给 `-C`，shell 认、git 不认 —— 所以看着"路径明明存在"却报不存在。

**对策**：脚本里不用 `-C`，改子 shell（由 bash 先 `cd` 到 MSYS 路径，再调 git）：

```bash
(cd "$REPO" && git log -1 --format="%h %ad %s")
```

**适用判据**：只要 helper 脚本在 git-bash 里跑、且路径来自 `pwd` / 参数 / `$HOME` 推导，
就用子 shell 形态；把 Windows 盘符**硬编码**写进脚本时才可直接用 `git -C "E:/..."`。

同族坑（SOUL 铁律 30）：MSYS 路径给 cmd / 其它原生 Windows 程序一律不认；
Windows 下命令里路径一律写 `E:/...` 或 `E:\\...`，禁止 `/e/...`。

---

## 三、克隆外部仓库的回退阶梯（逐级再试，别一步跳到底）

| 级 | 手段 | 何时用 |
|---|---|---|
| ① | `git clone https://github.com/<owner>/<repo>.git` | 默认先试，别预设它不通 |
| ② | `GIT_SSL_BACKEND=openssl git clone <同 URL>` | ① 报 TLS/握手类错误（如 `schannel: failed to receive handshake`）时重试 |
| ③ | **同源 Gitee 镜像** `https://gitee.com/<owner>/<repo>.git` | ①② 都失败 |
| ④ | release 页下载源码 zip / 单模板 zip | 只要其中一部分模板，或不需要 git 历史 |

**用 ③ 前必须验同一性**：比对 README / 项目描述 / 最近 commit 信息 / 版本号，
确认镜像与上游**确为同一仓库**（Gitee 上存在同名不同内容的仓 —— 别换错源）。
安装后**回写 commit 与版本号**到技能/记忆，供日后核对（本轮：`commit b8b4142` = v4.1.1）。

**克隆前先清点磁盘**：大仓库（数百 MB ~ GB 级）先看目标盘剩余空间，
并按用户"经验数据只落 E 盘"的惯例选盘，不要默认 C 盘。