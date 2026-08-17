---
name: windows-bioinformatics-batch-processing
description: "Windows生信批量任务执行规程：进程生命周期管理、GPU内存、进度监控、错误恢复。适用于CellBender/scanpy/Seurat等需要在Windows上用GPU跑大批量样本的场景"
when_to_use: "在Windows上启动长时间运行的生信批量任务（10+样本，每样本>5分钟）时加载，确保进程不因会话中断而死亡，LLM主动监控进度。系统唤醒(#N)主线进度检查也适用 — 协议见 references/agent-side-wakeup-check.md"
version: 1.9.2
author: MemOmics
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [windows, batch, process-management, cellbender, gpu]
    difficulty: advanced
    language: Python
    category: General Utility
---

## 🔴 铁规 0: 先调查再回答 — 禁止凭推理断言系统状态

> 📑 2026-08-08 GSE278576 40 样本批量踩坑速查 → `references/batch-concurrency-monitoring-pitfalls.md`（多实例 tmp 竞争 / cmd.exe//c MSYS 转义 / PowerShell $_ 转义 / tasklist grep 误报 / watchdog 误重启 / bridge 兜底）

**这是用户最愤怒的错误模式。** 当用户问"现在还在跑吗？"时，凭"之前做了规划所以不可能在跑"推理断言"没有在跑"——但进程表里有 2 个 CellBender 各占 7.2 GB RAM，GPU 73%。

**⚠️ 反向陷阱：GPU 占用 ≠ 分析在跑（本机实测 2026-08-08）**。`nvidia-smi` 显示 50% / 9.4GB 占用时，桌面应用（QQBrowser/微信/Steam/千问/Doubao/Edge WebView）常驻 GPU 可把利用率顶到 30-60%，**与生信任务完全无关**。验证两步：
```
① nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
   → 全是 QQ/Steam/浏览器 → 桌面占用，非生信
② tasklist | grep -iE "Rscript|python|cellbender"
   → 0 个 → 无分析进程
```
**结论必须以 tasklist 进程列表为准，GPU % 仅作参考**——GPU 高不能断言"在跑"，GPU 低也不能断言"没跑"（CPU 型任务如 ArchR 不占 GPU）。

**⚠️ PID 解析兜底（2026-08-08 唤醒 #4 实测）**：`nvidia-smi --query-compute-apps` 对部分 PID 返回 `[Insufficient Permissions]`（需管理员权限），`wmic process where "ProcessId=N"` 也无输出（同样无权限）。兜底用 PowerShell 解析 PID → 进程名 + CommandLine：
```
powershell -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Select-Object ProcessId,CommandLine | Format-List"
```
→ 靠 CommandLine 区分真实计算进程 vs **基础设施残留进程**。本机实测 python.exe 里有 2× `webui/server.py`（Hermes WebUI）+ 2× `cellbender_guardian.py`（守护脚本残留）——这些**不是计算进程**，不能误判为"分析在跑"或"分析残留"。Rscript.exe / 具体生信脚本的 CommandLine 才是判定依据。

**⚠️ task_plan.md 跨会话残留陷阱**：恢复会话时，task_plan.md 可能描述的是已完成的旧任务（如 CellBender），而实际运行的是完全不同的新任务（如 ArchR ATAC-seq）。四源交叉验证（进程+GPU+文件+日志）必须在读取 task_plan.md 后立即执行。当 task_plan.md 与系统状态矛盾时 → 以系统状态为准 → 更新 task_plan.md。详见 `references/session-resumption-stale-taskplan.md`。

**🏁 终态唤醒验证（任务完成后的循环唤醒）**：长任务终态后 LoopX 仍会唤醒。正确动作 = 三源验证 + 等用户指令，**绝不自动启动红线阶段**（如"待用户确认"的 P4）。唤醒记录只在结论变化时追加 — 连续 2-3 次相同结论后**停止追加**（task_plan 曾膨胀到 864 行全是重复"终态保持"记录），只验证+汇报。

**🧭 唤醒导航：session 目录可能没有自己的 task_plan.md**（实测 2026-08-08，1135ed52 人海马 ATAC 无 task_plan.md，其 P4 进度记录在父 session 1c1890da 的 task_plan Phase 4 段落）。唤醒时先 `search_files("task_plan.md", path=results)` 全盘找，再按 `.loopx/goals/*/runs/` 最新时间戳 + `token_usage.jsonl` 新鲜度判断活跃 session；找不到 task_plan 的 session 去父 session 找。不要因为"当前 session 无 task_plan"就断定无主线。

**🗺️ 多 task_plan.md 并存时选活跃文件（mtime 排序）**：根目录 `task_plan.md` 与 `results/{session_dir}/task_plan.md` 可能并存且新旧不一（实测根目录 7-30 旧版 vs results/ 下 8-08 活跃版）。唤醒时先 `search_files(pattern="task_plan.md", target="files")` 全盘找，再 `ls -lt` 按 mtime 排序**取最新修改的那个**，不要默认读根目录。选错文件会把已完成的旧任务当主线。

**🖥️ GPU 占用 ≠ 我们的任务**：nvidia-smi 显示占用（如 45%/9.4GB）但 tasklist 无 Rscript/python/分析进程 → 归因其他应用（浏览器/NVIDIA 容器/qmlauncher），**不误报为"任务在跑"，也不写告警**。三源验证里进程与 GPU 必须配对解读：有进程+有占用=我们的任务在跑；无进程+有占用=别人的。

**task_plan 压缩配方（>250 行必做，防膨胀）**：`grep -n "^## \|^# " task_plan.md` 列全部 section → 只保留核心块（头部/最新唤醒检查/终态确认/数据/参数映射/任务范围/Environment/Phase 状态/故障记录/Decisions Made/红线）→ write_file 重写压缩版 + 追加本轮检查。实测 864 行 → 93 行，零信息丢失。写后若有 `modified by sibling subagent` 警告 → 重新 read_file 核验内容完整性（并发唤醒可能同时写）。编号纪律：唤醒记录编号 = grep 最大号 + 1，禁抄消息头（终态 ≠ 从 0 重计）；终态完整记录已存在 → 不重复追加。陷阱：`.arrow` glob 计数 ≠ 样本数（临时/子目录副本虚增，实测 46 vs 40），权威完成信号是每样本完成文件（`*_filtered_cells.csv` / `*_filtered.h5`）计数 == N
  - **glob 陷阱**：`ls */_filtered_cells.csv` 返回 0！实际文件名是 `{sample}_filtered_cells.csv`（如 `GSM8549615_hc77_filtered_cells.csv`），glob 必须写 `*/*_filtered_cells.csv`。顶层 `ls | wc -l` 计数 = 样本数 + 非样本文件（实测 42 = 40 GSM 目录 + QC_summary_all40.csv + check_procs.ps1），不是样本数。目录名 `GSM8549615_hc77` ~ `GSM8549654_hc9`（GSM 连续 40 个）。；进程判定勿用裸 `R\.exe` grep（`er.exe` 子串误报 Container/explorer/crashpad 等，见 reference）。详见 `references/terminal-state-wakeup-verification.md`。

**⚠️🔥 空模板 task_plan.md — 严禁从其他 session 推断任务 (2026-07-30 实锤)**：当 task_plan.md 的 Goal 是占位符（如 "你是谁？"、"执行用户任务"），Phase 待办是泛化描述（"直接开始执行"）时 → **此 session 从未被赋予真实任务**。禁止：读取其他 session 的 system_log.jsonl 来推断"应该跑什么"、扫描其他 session 的 pending batch job 来自动启动。当前 session 的唯一信源是用户在**本轮对话中**的明确指令。详见 `references/empty-template-taskplan-no-resume.md`。

**⚠️ 关键误区**：这不是跨会话问题。即使在同一连续会话中，Agent 也可能因为信任"历史失败记录"（如日志里写着前 6 个失败了）而推断"整个 pipeline 停了"，不查实时状态就下结论。**三连击不是"跨会话时要做"，是"每次回答系统状态前必须做"。**

### 三连击检查法（回答系统状态问题前必须全做）

```python
import subprocess

def check_system_state() -> dict:
    """先查再回答——不可省略。"""
    state = {}
    
    # 1. tasklist: 相关的 python/cellbender 进程
    tasklist = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"],
        capture_output=True, text=True
    )
    state["python_processes"] = [l.strip() for l in tasklist.stdout.split("\n") if l.strip()]
    
    # 2. nvidia-smi: GPU 占用
    gpu = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True
    )
    state["gpu"] = gpu.stdout.strip()
    
    # 3. dir: 检查输出目录
    ls = subprocess.run(["dir", work_dir, "/B"], shell=True, capture_output=True, text=True)
    state["dir_contents"] = [l for l in ls.stdout.split("\n") if l.strip()]
    
    return state
```

**执行顺序**: 用户问系统状态问题 → 执行三连击 → 根据数据回答 → 绝不说"我不知道"或"应该没有"。

**⚠️ git-bash (MSYS) 下 tasklist 参数必须双斜杠 `//FI //FO`（2026-08-02 唤醒实证）**：在 bash 里写 `tasklist /FI "IMAGENAME eq Rscript.exe"` 会被 MSYS 路径转换把 `/FI` 当成路径处理 → tasklist 报错或返回空。正确写法是双斜杠：
```bash
tasklist //FI "IMAGENAME eq Rscript.exe" //FO CSV 2>/dev/null | head -20
# 也适用于 //IM //NH //V 等所有 tasklist 开关
```
Python `subprocess.run(["tasklist", "/FI", ...])` 不受影响（列表参数不经过 MSYS 转换）。skill 中所有 bash 一行的 tasklist 示例均按此双斜杠写法执行。

**⚠️⚠️ `//FI` 过滤也可能静默返回空 — 禁止把空输出当"无进程"证据（2026-08-07 唤醒 #2 实测）**：GSE278576 ArchR 批处理中，6 个 Rscript.exe 在跑（3 个 1.3-1.8GB 活跃 + 3 个轻量），但 `tasklist //FI "IMAGENAME eq Rscript.exe" 2>/dev/null | head -20` 返回**空**、`grep -c` 返回 0 → 一度误判"进程已死"。实际进程健在。**判定铁律：`//FI` 过滤为空时，禁止直接下"没有进程"结论——必须先用裸 `tasklist | grep -iE "<name>"` 交叉验证**。若裸 grep 也空，再结合日志 mtime + 磁盘产出做四条件间接判定（铁规 0）。伪阴性（有进程却报无）比伪阳性（无进程却报有）更危险——它直接触发用户最愤怒的"凭什么说没在跑"模式。

**⚠️⚠️⚠️ `//FI` 也会响亮失败 + `2>/dev/null` 把报错吞成"空"（2026-08-07 唤醒 #3 复实证）**：同一 GSE278576 批处理，`tasklist //FI "IMAGENAME eq Rscript.exe" 2>/dev/null | tail -5` 返回空（一度疑"无 Rscript"），去掉 `2>/dev/null` 后 `tasklist //FI ... 2>&1` 露出真面目：`无效参数/选项 - '//FI'`——**MSYS 双斜杠写法在部分终端上下文仍被拒绝，且 stderr 重定向把响亮错误伪装成静默空输出**。**判定铁律升级：① 查进程时禁止 `2>/dev/null` 吞 stderr——先 `2>&1` 看是否有"无效参数"类真实报错，报错=探测失效≠无进程；② 任何 tasklist 开关写法（//FI //FO）在本环境都不保证可靠，唯一兜底 = 裸 `tasklist | iconv -f GBK -t UTF-8 | grep -iE "<name>"`；③ 进程存活的最终裁决 = 大内存 worker 进程 + 最新样本日志 mtime 增长（hc5579.log "Reading TabixFile 17%" 01:55 仍在写 = 活着），不要被 tasklist 探测失败带偏。**

**⚠️⚠️⚠️ 开关失败是全局的（//FI //FO 都空），可靠探测 = 裸 `tasklist | iconv | grep`（2026-08-07 唤醒 #2 二次实证）**：同一唤醒里 `//FI` 空之后，`tasklist //FO CSV` 也返回空、PowerShell `Get-Process | Where Name -match` 也返回空——三个方法全空才误判"死亡"。但裸 `tasklist 2>/dev/null | iconv -f GBK -t UTF-8 | grep -iE "Rscript|cmd\.exe|bash"` 一次性找到了 Rscript.exe + cmd + bash 全进程树（进程其实一直健在）。**判定铁律升级：① 任何带开关的 tasklist（//FI //FO //IM 等）在 git-bash 都可能静默失败 → 交叉验证一律用无开关裸 tasklist + `iconv -f GBK -t UTF-8` 转码 + grep；② PowerShell 进程查询（Get-Process / Get-CimInstance CommandLine）在本环境同样可能静默返回空，空结果不可作为"无进程"证据；③ 三源全空才判死，且汇报必须说明"哪几个方法查了都空"（如 //FI 空 + //FO 空 + PS 空 + 日志冻结）而不是笼统说"没进程"。**

**✅ `ps -W` = MSYS 原生 Windows 进程探测 — 最简可靠兜底，优先于 PowerShell（2026-08-07 memomics-1135ed52 唤醒 #6 实测）**：`ps -W`（MSYS 自带，直接列出所有 Windows 进程：PID + 启动时间 + 完整 Windows 路径）**零转义、零 PowerShell、零 iconv**。本唤醒实测探测失败链：`tasklist //FI` 空 → PowerShell 内联 `$_` 被 bash 展开成 `/e/MEMOMICS_HOME` 崩掉 → `cmd //c "tasklist | findstr"` 引号地狱 → 最后 `ps -W | grep` 一把命中。用法：
```bash
ps -W 2>/dev/null | grep -iE "Rscript|python|ArchR" | grep -viE "NvContainer|crashpad|QQBrowser|qq|Steam|explorer|GameViewer"
# 输出含 PID + 启动时间 + 完整路径 → 与样本日志 START 时间比对即可确认活体
# 唤醒 #6 实测: 2 个 Rscript.exe 启动 02:25:04 ↔ hc76 日志 START 02:25:10 → 任务健康推进（之前 tasklist 空误判"进程已死"，ps -W 纠正）
```
**判定口诀：tasklist 开关失败 → 第一兜底 = `ps -W | grep`（注意进程名子串规则，`R\\.exe` 后缀会命中 Container.exe 等噪音 → 用 `grep -viE` 排除或直接锚定 `Rscript`）→ 需要 CommandLine 细节时才写 .ps1 CIM（转义地狱，最后手段）。**

**✅ PowerShell 内联可用 — 关键在 `\$` 转义（2026-08-07 memomics-1135ed52 唤醒 #2 实证）**：git-bash 双引号里 `powershell -Command "Get-Process | Where-Object {\$_.ProcessName -match 'Rscript|bash|sh'} | Select-Object ProcessName,Id,StartTime | Format-Table -AutoSize"` 一把成功，输出含 PID + 启动时间（Rscript.exe 38964 launcher 7.9MB + 64316 worker 1.86GB + bash 进程树）——worker 启动时间与样本日志 START 行交叉 = 铁证级活体。此前多次"PowerShell 内联崩掉"的根因是 **bash 双引号内未转义 `$_`**（被 bash 展开成上一条命令的最后一个参数 → 语法崩）。**规则：bash 双引号内 PowerShell 变量一律 `\$` 转义（`\$_.ProcessName` 而非 `$_`）；`-match 'A|B|C'` 联合进程名查询可用；Select ProcessName,Id,StartTime 三列足以做日志交叉验证；只有需要 CommandLine 深度细节时才退回 .ps1 CIM。** 与 `ps -W`/`ps -ef` 同为第一兜底级，优先于 tasklist 开关。
> **✅ 零转义替代 = 单引号整段包裹 `-Command`（2026-08-07 memomics-1135ed52 唤醒 #4 实测）**：`powershell -Command 'Get-Process | Where-Object {$_.ProcessName -match "Rscript|bash|sh"} | Select-Object Id,ProcessName,CPU,StartTime | Format-Table -AutoSize'` 一把成功——bash 单引号内 `$_` 原样传给 PowerShell，**无需 `\\$` 转义**。⚠️ PowerShell 内部字符串改用双引号（`-match "..."`），避免单引号冲突。**双引号外+`\\$` 内转义 vs 单引号外+内双引号，两种都可行；单引号整段更省心（零转义失败点），推荐优先。** 唤醒 #4 首试用了双引号+裸 `$_`（被 bash 展开成 `/e/MEMOMICS_HOME.ProcessName` → cmdlet 找不到）——裸 `$_` 是唯一必崩写法。

**✅ 普通 `ps -ef`（不带 -W）也列出 Windows 进程 + PID + 启动时间 + 完整路径 — 比 `ps -W` 更直接的活体证据（2026-08-07 memomics-1135ed52 唤醒 #15 实测）**：本唤醒 `tasklist //FI "IMAGENAME eq cmd.exe"` 又返回空（cmd.exe 实际健在），但 `ps -ef | grep -iE "Rscript|cmd"` 一次命中：`23136 8485 4723 ? 03:09:52 C:\WINDOWS\system32\cmd.exe /c E:\...\run_GSM8549621_hc5614.bat`——**PID + 启动时间 03:09:52 ↔ 样本日志 START 03:09:59 秒级吻合 = 铁证级活体**，零转义、零 PowerShell、零 iconv，还比 `ps -W` 多给启动时间（可直接对照样本日志 START 行）。**进程树三层（bash 调度 / cmd 包装 / Rscript worker）用普通 `ps -ef | grep -iE "bash|cmd|Rscript"` 一目了然，无需 CIM 联合查询。判定优先级：`ps -ef | grep 进程名` 与 `ps -W | grep 进程名` 同级第一兜底（前者给启动时间、后者给 Windows 路径），均优于 PowerShell。**

**✅ 最优简模式 = 精确进程名子串 `grep "Rscript"`（2026-08-07 唤醒 #13 实证，推荐优先）**：本轮用 `grep -c "Rscript"` 一次返回 2（launcher 7.7MB + worker 2GB），`grep "Rscript"` 两行精确输出 PID+内存，零噪音零转码（无需 iconv）。原理：`Rscript` 是**完整进程名 token**，没有任何噪音进程包含该子串；而 `R\.exe` 失败是因为 `r.exe` 是**通用后缀**，被子串匹配进 Container.exe/crashpad_handler.exe 等。**判定：进程名本身是唯一 token（Rscript/python/cellbender）→ 直接 `grep "进程名"`（大小写敏感、不带 .exe 也匹配到 .exe）最干净；只有通用名（如 bash/cmd）才需要 `grep -iE "^bash"` 锚定或 `grep -v` 排除噪音。**

**✅ 简单形 `Get-Process <精确名>` = 最可靠进程探针，计数准确（2026-08-07 memomics-1135ed52 唤醒 #5 实测）**：本轮 `tasklist //FI "IMAGENAME eq Rscript.exe" 2>/dev/null | head` 又空（//FI 失效 + 2>/dev/null 吞错，铁规 0 复犯，一度误判"进程已死"）→ 换 `powershell.exe -NoProfile -Command "(Get-Process Rscript -ErrorAction SilentlyContinue) | Select-Object Id,CPU,WorkingSet64,StartTime | Format-Table -AutoSize"` **一把返回恰好 2 个**（launcher 54748 7.9MB CPU 0 + worker 59668 ~1GB CPU 133s），与 monitor.log `procs=2` 完全吻合 = 计数可靠、launcher/worker 结构清晰。**规则：对唯一 token 进程名（Rscript/python/cellbender）优先用简单形 `Get-Process <名>`（不写 Where-Object、不碰 `$_` 转义 = 零转义失败点），可靠性优于 tasklist //FI、简单性优于复杂 PowerShell 形式；StartTime 列可与样本日志 START 行交叉验证活体。此前记录的"PS 静默空"均发生在 Where-Object/-match 复杂形式，简单形式本环境实测稳定。**

**✅ 多进程名简单形 `Get-Process -Name A,B,C` + CPU 列 = launcher/worker 判别 + 活体铁证（2026-08-07 memomics-1135ed52 唤醒 #7 实测）**：本轮先复犯"宽泛 grep + head 截断"陷阱（`tasklist | grep -iE "Rscript|R\\.exe|python|cmd\\.exe" | head -10` 被 `R\\.exe` 后缀命中的 Container.exe/Svr.exe/launcher.exe 噪音填满前 10 行——这些进程名全以 `r.exe` 结尾，Rscript 行被 head 截出视野，唤醒 #17 已记录同类）。随后 `powershell -NoProfile -Command "Get-Process -Name Rscript,R,cmd -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,CPU,StartTime,Path | Format-List"` **一把全中**：cmd 12732/16136 + Rscript launcher 54748（CPU 0）+ Rscript worker 59668（CPU 947s，StartTime 11:30:40 ↔ 样本日志 START 11:30:46 秒级吻合）。**CPU 秒列是决定性的：worker CPU 数百秒且持续增长 = 真在计算；launcher CPU 0 = 仅包装壳**。`-Name A,B,C` 多进程名简单形（无 Where-Object、无 `$_` 转义）一次性覆盖进程树三层，比逐个单名查询更省一轮。

**⚠️⚠️⚠️⚠️⚠️ watchdog/monitor 是 bash 脚本进程，不是 Windows 进程名 — `Get-Process -Name watchdog_v2` 必失败且 exit 1（2026-08-07 memomics-1135ed52 唤醒 #8 实测）**：本唤醒先用 `powershell -Command "Get-Process Rscript ...; Get-Process -Name watchdog_v2 -ErrorAction SilentlyContinue ..."` 查 watchdog 存活 → Rscript 部分正常返回（PID 58912），watchdog 部分**空输出 + exit code 1** → 触发 Hermes terminal"连续失败 7 次（上限 3）"结构错误门禁。**根因：watchdog_v2.sh / monitor_serial.sh 是用 `PowerShell Start-Process bash` 或 `nohup bash` 拉起的，进程表中只有 `bash.exe`，没有名为 `watchdog_v2` 的 Windows 进程**——按脚本名查进程 = 查询不存在的进程名 = PowerShell exit 1（`-ErrorAction SilentlyContinue` 只吞错误显示，不保证 exit 0）。**判定铁律：① 任何按脚本名（watchdog*/monitor*/run_serial*）的 `Get-Process -Name` 查询都是错的——bash 脚本的进程名永远是 `bash.exe`/`sh.exe`；② watchdog 存活正确探针 = monitor.log mtime 新鲜度（每 2min 更新 = 活，本唤醒实测 18:49:29 最新）+ `Get-Process bash`（核对 PID 与启动时间）+ `Get-CimInstance ... -Filter "Name='bash.exe'" | Select CommandLine` grep 脚本名；③ 查询失败返回 exit 1 时，**先检查是否查了不存在的进程名**（探测设计问题）而不是误判"进程死了"——exit 1 ≠ 无进程，可能是进程名写错了；④ 混合查询时把 watchdog 部分拆开或直接删掉，用 monitor.log 时间戳做 watchdog 活体主证据。**

**⚠️⚠️⚠️ Get-Process 列表查询 exit 1 + \\\"连续失败 N 次\\\"横幅 ≠ 命令失败 — 输出可能完全有效（2026-08-07 memomics-1135ed52 唤醒 #11 实测）**：`powershell -Command \\\"Get-Process Rscript,sh,bash -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,StartTime,CPU | Format-Table -AutoSize\\\"` 返回 **exit_code 1** 并触发 Hermes 结构化错误横幅 \\\"连续失败 10 次（上限 3）\\\"，但**输出正文完整有效**（Rscript 12376 + 5 个 bash 进程 + 启动时间 + CPU 全齐），直接用该数据完成了三源验证。**根因：`-Name` 列表里 `sh` 不匹配任何进程（MSYS 下是 bash.exe 不是 sh.exe）→ PowerShell 产生非终止错误 → 进程 exit code 变为 1**（`-ErrorAction SilentlyContinue` 只吞显示不吞 exit code），而其他名字（Rscript/bash）的数据照常打印。**判定铁律：① PowerShell 命令返回 exit 1 时先看**输出正文**是否有真实数据行——有 = 命令实际成功，exit 1 只是某个查询名无匹配的副作用；② 不要因 Hermes \\\"连续失败 N 次\\\"横幅就丢弃/重写命令（该计数器把历史上同目录的 exit 1 累积进来，本唤醒 10 次是跨唤醒累积不是本次失败）；③ 规避：`-Name` 列表只放确实存在的进程名（Rscript/bash/cmd），不确定的名字用 `Get-CimInstance ... -Filter \\\"Name='X'\\\"` 单独查（该形式不存在名时 exit 0 + 空输出，不污染退出码）。**

**⚠️⚠️⚠️⚠️ 复合 bash 命令 exit 1 变体 — 最后一段 tail/grep 失败，前面段输出仍有效（2026-08-07 memomics-1135ed52 唤醒 #36 实测）**：`ls -d .../ArchR_Arrow_QC_Filtered/*/ | wc -l; echo \\\"---\\\"; tail -5 /e/专利/Human_Hippocampus_ATAC/batch/monitor.log` 返回 **exit_code 1 + \\\"连续失败 28 次\\\"横幅**，一度疑\"磁盘/日志全查不到\"——但**原始输出（\\\"--- 原始输出 ---\\\" 段）里 `37`（DONE_MARK 计数）+ 目录列表完全有效**，只有最后一段 `tail` 因路径不存在（batch/ 目录已迁移到 session 目录）返回非零。**根因：复合命令的退出码 = 最后一段的退出码，任何一段 tail/grep 命中不存在文件都会把整体拖成 exit 1**。**判定铁律：① 复合命令 exit 1 时先看**输出正文**前面段是否已有有效数据（`wc -l` 数字、目录列表）——有 = 前面段成功，exit 1 只是尾段探测失败的副作用；② 判断\"哪段失败\"= 看最后一段的操作对象（tail/grep 的目标文件/路径是否真的存在），而不是整条命令重写重试（重试 = 白烧轮次 + 喂\"连续失败\"计数器）；③ 修正 = 用已验证存在的路径重跑**只有失败的那一段**（本唤醒：monitor.log 真正位置 = `results/{session}/batch/monitor.log`，从 watchdog_v3.sh CONFIG 读出的权威路径），不要整条命令原样重发。**

**⚠️⚠️⚠️⚠️ 宽泛 grep 模式 + `head -N` 截断 = 伪阴性陷阱（2026-08-07 memomics-1135ed52 唤醒 #17 实测）**：首轮探测用 `tasklist | grep -iE "R\.exe|Rterm|Rscript|archr|cmd\.exe" | head -20`——grep 模式**确实包含** Rscript，但 tasklist 输出按名称/会话排序，`R\.exe` 后缀命中的一堆噪音（NVDisplay.Container.exe、crashpad_handler.exe、qmlauncher.exe 等）先占满前 20 行，`head -20` 把 Rscript 行**截出视野** → 一度疑"无 Rscript 进程"。实际 Rscript.exe PID 64624（1.37GB worker）健在。**陷阱本质：宽泛模式 + head 截断的组合 = 目标行被噪音顶出窗口，不是"进程不存在"。判定铁律：① 唯一 token 进程名（Rscript/python/cellbender）永远用精确 `grep "进程名"`，不要混进 `R\.exe` 类后缀模式再 head 截断；② 宽泛模式探测时**不要加 `head -N`**（或用 `grep -m` 只取首个匹配），宁可全量输出后人工扫；③ 唯一可靠兜底 = `tasklist | findstr /i "Rscript"`（Windows 原生 findstr 直连管道，零转义零转换，本唤醒实测一把命中，无需 cmd //c 包装）。**
> 🔴 **变体：grep 模式含 `python` + head 截断 = 平台服务填满窗口，Rscript 被顶出（2026-08-07 memomics-1135ed52 唤醒 #15 实测）**：首轮探测 `tasklist | grep -i -E "Rscript|python|archr|cellbender" | head -20` 返回**全是 python.exe**（~20 个平台 webui/框架常驻服务，铁规 0 平台服务条目）——`python` 模式把平台服务全收进来填满 head -20 窗口，**Rscript 行在窗口之外被截掉** → 一度疑"无 Rscript 进程"；实际 Rscript 63748 (hc35) 健在（随后 `Get-CimInstance Win32_Process | Where-Object {\$_.Name -match 'Rscript|bash|...'}` 一把命中全进程树 + CommandLine 精确显示 `create_arrow_qc.R GSM8549653_hc35`）。**陷阱本质与 #17 相同（宽泛模式 + head 截断 = 目标行被噪音顶出窗口），但噪音来源不同：#17 是 `R\.exe` 后缀命中系统进程；本变体是 `python` 模式命中平台常驻服务（本机恒有 20+ 个 python.exe）**。判定口诀：① 探测模式里**不要包含 `python`**——它是平台服务高频噪音，直接污染 head 窗口；② 唯一 token 进程名（Rscript/python/cellbender）单独精确 grep 或走 CIM；③ 需要全树时用 `Get-CimInstance` 联合查询 + CommandLine（最终裁决器），不要靠宽泛 grep + head。

**⚠️⚠️⚠️⚠️ 进程生死最终裁决器 = Get-CimInstance + CommandLine（2026-08-07 memomics-1135ed52 唤醒 #4 实测）**：GSE278576 串行批处理检查时，`process(action='list')` 空（脱离式任务预期行为）+ `tasklist //FI` 空 + `Get-Process Rscript` 返回 **13 个**进程（把 bash/cmd 包装也数进去了，数量严重误导）——三项线索全指向"批处理死了"，差点误判。**改用 `Get-CimInstance Win32_Process -Filter \"Name='Rscript.exe'\" | Select ProcessId,CreationDate,CommandLine` 一锤定音**：真实只有 **2 个** Rscript worker，CommandLine 精确显示 `create_arrow_qc.R GSM8549617_hc5579` + Age 27min → 任务健康推进中，之前所有"空/多"都是探测层失真。**判定铁律（最终版）：进程生死与批处理推进状态的唯一权威证据 = CIM 查询的 CommandLine**——能看到具体跑哪个脚本、哪个样本、启动多久。Get-Process 计数（13 vs 真实 2）、tasklist 各种开关（可能静默空）、process(list)（脱离式任务恒空）都只作线索不作裁决；三者与 CIM 矛盾时以 CIM 为准。可复用脚本见 `scripts/check_procs.ps1`。

**✅ 单 PID 的 CommandLine 查询 = 用 `-Filter "ProcessId=N"`，完全绕开 `$_` 转义（2026-08-07 memomics-1135ed52 唤醒 #10 实测）**：当已经知道 PID（如从 `ps -ef` / `Get-Process` 拿到 bash 主循环 PID 5580）时，`Get-CimInstance Win32_Process -Filter "ProcessId=5580" | Select-Object ProcessId,CommandLine` **零 `Where-Object`、零 `$_`、零转义失败点**，一把返回该 PID 的完整命令行（本唤醒实测：`"C:\Program Files\Git\usr\bin\bash.exe" batch/run_serial_v2.sh` → 确认 5580 就是 run_serial 主循环）。**规则：查"这个 PID 在跑什么"一律用 `-Filter "ProcessId=N"` 形式；只有"按进程名/命令行模式查一组"才需要 `-Filter "Name='X'"` 或 `Where-Object`（后者在 bash 双引号里必须 `\$` 转义或整段单引号包裹）。** 这是 CIM 三形式里最省心的：ProcessId= / Name='x' / Where-Object，按需选，转义风险递增。

**⚠️ 复杂 PowerShell 内联在 bash 里是转义地狱 — 写 .ps1 文件 + -File 执行（2026-08-07 唤醒 #4 实测）**：`powershell -Command "Get-CimInstance ... Substring(...) ..."` 内联命令在 git-bash 里被反斜杠/引号转义反复搞崩（连续失败 8 次，触到"连续失败上限 3"门禁）。**可靠做法 = `write_file` 写 .ps1 脚本 → `powershell.exe -NoProfile -ExecutionPolicy Bypass -File check_procs.ps1`**——零转义问题，且脚本可复用（`param([string]$ProcName)` 查 Rscript/python 任一进程名）。同理 **`wmic` 在较新 Windows 已被微软移除**（`'wmic' 不是内部或外部命令`），不要浪费时间试 wmic，直接走 CIM。
> 🔴 **计算属性 hashtable `@{N=...;E={...}}` = 内联必崩区 — 直接 .ps1，不要试内联（2026-08-07 唤醒 #26 复实证）**：`powershell -Command "Get-Process Rscript | Select-Object Id,StartTime,CPU,@{N='RAM_GB';E={[math]::Round($_.WS/1GB,2)}} | Format-Table -AutoSize"` 在 git-bash 双引号里 exit 1 + 连续失败 15 次（含跨唤醒累积），`$_` 在 hashtable 的 `E={}` script block 内被 bash 展开成路径 → cmdlet 找不到。同一轮改 `write_file check_procs.ps1`（纯 ASCII）+ `powershell -ExecutionPolicy Bypass -File` **一把成功**。**内联安全区 = 简单形 `Get-Process -Name A,B,C` / `-Filter "ProcessId=N"` / 单引号整段包裹 -Command；内联必崩区 = `Where-Object {$_...}`、`ForEach-Object {$_...}`、`@{N=;E={$_...}}` 计算属性、双引号内嵌 `$_`——凡含 `$_` 于花括号 script block 内 → 直接 write_file .ps1，一次到位，不要试内联省事**。
> 🔴 **最快恢复 = 先丢计算属性列，再考虑 .ps1（2026-08-07 唤醒 #30 复实证 — 必崩区第 3 次被踩）**：本轮又双引号 + `@{N='RAM_GB';E={[math]::Round($_.WorkingSet64/1GB,2)}}` 查进程 → **连续失败 20 次**（跨唤醒累积，触发"连续失败上限 3"门禁）。恢复只用 1 轮：**把计算属性整段删掉**（RAM_GB 列本来就非必需——三源验证只需要 `Id,StartTime,CPU`），改用单引号整段包裹 `powershell -Command 'Get-Process Rscript -ErrorAction SilentlyContinue | Select-Object Id,StartTime | Format-Table -AutoSize; ...'` **一把成功**。**决策口诀：① 必崩区自检——内联命令里出现 `$_` 于花括号 script block 内（Where-Object/ForEach-Object/@{N=;E=}）→ 停手，先问"这个列/条件能不能不要"；② 计算属性列（RAM 换算等）非判定必需 → 直接删列 + 单引号整段，比重写 .ps1 更快更省轮次；③ 只有 RAM 等计算值确实是判定必需（如区分 launcher 7.9MB vs worker 1.9GB）才写 .ps1；④ 写了但失败 ≤2 次就换路，不要硬刚到"连续失败上限"门禁（20 次 ≈ 白烧 20 轮）。**

### ⚠️ python.exe ≠ 分析在跑 — 平台常驻服务区分（2026-08-03 唤醒 #21 实证）

三连击查 tasklist 时，**看到 python.exe 不代表分析在跑**。MemOmics 平台自身以 python.exe 常驻：
- `MEMOMICS_HOME\.venv\Scripts\python.exe webui\server.py`（webui 服务）
- 其它 Hermes 框架运行时进程（`webui\..\cellbender` 等服务）

**判定方法**：查 CommandLine 区分平台服务 vs 分析任务：

```powershell
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | ForEach-Object { Write-Output ('PID=' + $_.ProcessId + ' | ' + $_.CommandLine) }"
```

**分类规则**：
- ✅ **平台服务**：CommandLine 含 `webui\\server.py` / `.venv\\Scripts\\python.exe` / MemOmics 框架路径 → 常驻正常，**不是分析任务**
- 🔴 **分析任务**：CommandLine 含分析脚本名（cellbender/scanpy/archr/run_pipeline 等）或对应 Rscript.exe / GPU 高占用

**✅ 多进程名联合查询 — 揭示完整批处理进程树（2026-08-07 唤醒 #2 实证，优于单名过滤）**：批量 R/ArchR 任务下，用单进程名过滤（如只查 Rscript）会漏掉调度器，且 `wmic` 在本环境静默返回空。联合查询一次看清三层结构：

```powershell
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.Name -match 'bash|cmd|Rscript' } | Select-Object ProcessId,Name,CommandLine | Format-List" 2>/dev/null
```

**批处理三层结构识别**（GSE278576 实测）：
1. **调度器层**：`bash.exe -lic "set +m; bash run_batch.sh 3"`（bash → bash → bash 多层包装是 MSYS 嵌套启动的正常现象，不是僵尸）
2. **cmd 包装层**：`cmd.exe /c .../run_GSMxxxx.bat`（R 必须走 cmd.exe /c 铁规 16）
3. **worker 层**：`Rscript.exe ... create_arrow_qc.R <sample>` — **判断"是否还在跑"以 worker 层为准**（大内存 1.3-1.8GB 活跃 Rscript + 日志 mtime 增长 = 在跑；只剩轻量 Rscript 几 MB = 已挂）

**判定"调度器还活着"**：CommandLine 含 `run_batch.sh` 的 bash.exe 存在 = 调度器在跑，会在 worker 空位后自动拉起下一个样本。调度器死了但 worker 还活着 = 当前样本跑完后批次停摆——此时需人工重启调度器（`bash run_batch.sh N` 带 remaining.txt 去重跳过已完成）。

> 当 `wmic process get ProcessId,CommandLine` 返回空时，**直接换 Get-CimInstance 联合查询**，不要卡在 wmic 上反复重试（wmic 在较新 Windows 已被微软移除——`'wmic' 不是内部或外部命令`，2026-08-07 本环境实测，任何返回空都应视为"工具不存在"而非"无进程"）。

**⚠️ CommandLine 查询可能返回空 — 间接判定回退（2026-08-03 唤醒 #7 实证）**：git-bash 环境下 `wmic process where ... get commandline` 和 `powershell Get-CimInstance ... Select CommandLine` 都可能**静默返回空**（exit 0 但无内容），此时无法靠 CommandLine 区分服务/任务。改用**四条件间接判定**：
1. `tasklist` grep 分析特征进程名（Rscript/cellbender/ptrepack/run_pipeline）— 有 = 分析在跑
2. `nvidia-smi` GPU 占用 — CellBender 等训练任务会占满 ~16GB VRAM；平台 webui 常驻 ~4GB 属正常
3. `find results/{session}/ -newermt "YYYY-MM-DD" -type f` — 24h 内无新分析产出 = 无进行中任务
4. `alerts.json` 不存在 = 无告警
**四条件齐备（无特征进程 + GPU 低占用 + 24h 无新产出 + 无 alerts）才判定"无任务在跑"**，再汇报。

**GPU 判定注意**：平台 webui 常驻可占 ~4GB VRAM（唤醒 #21 实测 GPU 21%/4.2GB/16.3GB 实为空闲）。**显存/低占用率单独不能证明分析在跑**——以进程 CommandLine 为准：无分析脚本进程 + 低利用率 = 空闲，正常汇报，不要误报"有任务在跑"。
- ⚠️ **`nvidia-smi --query-compute-apps` 大量 PID 全 N/A ≠ 分析在跑（2026-08-02 唤醒 #11 实测）**：git-bash 下该查询可能返回几十个 PID 但 `used_memory` 全是 `[N/A]`——这些是常驻进程/驱动上下文，不是计算负载证据。**判定口诀：compute-apps 的 N/A 列表不可用作"有任务在跑"的证据**；真正有效的是 ① GPU 利用率%（低=空闲）② CommandLine 是否含分析脚本名 ③ 24h 内磁盘新产出。三个都不满足 → 空闲，即使 compute-apps 列了 40+ PID。

**⚠️⚠️⚠️ R 脚本的 batch 日志 mtime 冻结 ≠ stall — stdout 重定向是块缓冲（2026-08-07 memomics-1135ed52 唤醒 #2 实测）**：`run_serial.sh` 用 `cmd.exe /c "Rscript ... > batch/logs/{sample}.log 2>&1"` 跑 ArchR 单样本。hc78 的 addDoubletScores 实际跑了 4.5min（01:45:22→01:49:50）且**成功完成**，但 `batch/logs/GSM8549616_hc78.log` 的 mtime 冻结在 01:45（重定向后 R 的 stdout 是**块缓冲**，进度行不实时落盘，只在 flush/退出时一次性写全）→ 一度误判"进程死了"。**ArchR 的正确活体信号是它自己的内部日志 `ArchRLogs/ArchR-<module>-<hash>-Date-*.log`（实时逐行写，mtime 持续增长 = 模块在跑）**。判定顺序：batch 日志 mtime 冻结 → 查 `ArchRLogs/` 下最新模块日志 mtime 是否增长 → 增长 = 在跑（继续等）；不增长 + 进程查询全空 = 真死。最后 cat batch 日志尾部看是否有 `=== DONE ===`（hc78 完整跑完 01:49:52，含 addDoubletScores done 4.5min / filterDoublets 1012 cells 14.2% / P3 saved）——**样本可能早已完成而串行循环已自动跳到下一个样本**。

**✅ ArchRLogs 最新日志 = 识别"当前在跑哪个样本"的最快探针（2026-08-07 memomics-1135ed52 唤醒 #10 实测）**：`search_files(pattern="*.log", path=".../ArchR_Arrow_QC/ArchRLogs/")` 按 mtime 排序的最新 `ArchR-createArrows-<hash>-Date-<ts>.log`，其**文件头/首行直接标注当前样本**（如 `(GSM8549650_hc26 : 1 of 1)`）+ 当前阶段（如 `tileChromSizes` 120 chunks = 早期；`Tabix Bed To Temporary File` = 读片段中）。**比逐个猜"哪个 Rscript 在跑哪个样本"快得多**——一个 tail 就同时给出样本名 + 阶段。判定：最新 createArrows 日志的 GSM 样本名 ≠ task_plan 写的旧样本 = 循环已自动推进到新样本（无需再查 CommandLine）。**样本完成的确认信号 = 该样本的旧 createArrows 日志尾部出现 `Completed / End Time / Elapsed Time Minutes = N`（如 hc19 18:56:54 End, Elapsed 11.3min）——"End Time + Elapsed"双字段 = 正常收尾，不是崩溃**（崩溃是 `has encountered an error, checking if any ArrowFiles completed` 字样）。同一轮里读"最新日志首行（当前样本）+ 前一个样本日志尾部（完成确认）"即可完整还原串行推进状态。

**✅ P2 addDoubletScores 阶段的活体信号 = `ArchR-addDoubletScores-*.log` 的 "Simulating and Projecting Doublets, X mins elapsed"（2026-08-07 memomics-1135ed52 唤醒 #29 实测）**：样本进入 P2 后，**createArrows 日志会停更**（P1 阶段日志已写完：Arrow 创建成功 → CellStats → Adding Additional Feature Counts），当前活跃日志变成 `ArchR_Arrow_QC/ArchRLogs/ArchR-addDoubletScores-<hash>-Date-<ts>.log`。该日志的**唯一逐行进度信号 = `Simulating and Projecting Doublets, X.XXX mins elapsed.`**（如 20:06:49 显示 2.658 mins elapsed）——elapsed 分钟数增长 = 在跑。⚠️ **P2 阶段无逐样本/逐行进度输出，属正常**（ArchR 内部 doublet 模拟/投影是整体计算，不写进度条），不要因"没有新行"误判 stall；正确三证据 = ① addDoubletScores 日志里 elapsed 分钟数增长（或最新时间戳新鲜）② Rscript worker CPU 秒数持续增长 ③ monitor.log procs=1 done 计数不变（P2 不落 DONE_MARK）。**P2 时长参考：~5min/样本**（hc40: 19:43:34 启动 → 19:48 产出 filtered_cells.csv；hc212191: 20:04:09 启动 → 预计 ~20:10）——超过 ~10min 且无任何信号才可疑。找 P2 日志用 `find ArchR_Arrow_QC/ArchRLogs -name "ArchR-addDoubletScores*"`（最新 mtime 即当前样本）。

### 汇报模板

**🔴 催进度/连续追问时 → 一句话回复（2026-08-07 停滞事故实证）**：用户连发"进度呢？""心跳机制还在吗？""ping，用一句话回复"时 = 用户已不耐烦/怀疑系统失联。此时**只给一句话**：状态（在跑/死了/停滞 X 分钟）+ 关键数字（X/40）+ 已采取的动作。**禁止**甩大表格、多段报告、流程图。三源验证照做（铁规 0），但**汇报压缩成一句话**。示例："管线 25/40 时调度器死了，hc1265 完成后停滞 95 分钟，已重启，hc8 正在跑。" 长报告留到用户主动要求详细时再给。

```markdown
## ✅ 实际状态（查了，不是猜的）

### Python 进程（{n} 个活着）
```
PID   RAM        推测
16312  7.2 GB  🔴 CellBender #1
28208  7.2 GB  🔴 CellBender #2
```

### GPU
```
{util}% 占用, {used_mb} MB / {total_mb} MB
```

### 目录
```
{work_dir}/ 存在 → 内容: [dir listing]
```
```

---

## 🔴 铁规 1.5: 系统唤醒恢复协议 — 唤醒轮次不代确认【v1.4 新增】

当收到 `[系统唤醒 #N] 检查主线任务进度`（心跳/定时唤醒）时，按此协议执行：

### 唤醒必做 7 步（顺序执行）

> **📊 LoopX 状态头解读（2026-08-07 唤醒 #1 实测）**：唤醒消息顶部现在带 `LoopX 状态：goal: active | attention: ok | todos: none`。解读规则：
> - `goal: active` = 系统级目标存活，**不是**"有任务要跑"的信号
> - `todos: none` = 待办清单为空 — **仅当与 task_plan 终态（全部 complete + 停止标记）互为印证时才是终态信号** → 本次唤醒只汇报不执行；⚠️ **todos:none 也可能出现在任务进行中（唤醒 #26 实测：35/40 跑中、hc212191 活跃，LoopX 仍报 todos:none）——LoopX 待办 ≠ task_plan Phase，判断是否终态一律以 task_plan Phase 状态为准，todos:none 单独不构成停止理由**
> - `attention: ok` = 无注意力告警，正常
> - ⛔ `todos: none` + task_plan 终态 → 禁止因唤醒 prompt 里"继续执行下一个待办"字面化而自行发明工作；正确动作 = 读 task_plan + cron 检查（同批）+ 汇报 + 列选项

1. **核对 session ID** — `search_files(results, task_plan.md)` 可能返回多个 task_plan。只读**当前 session 目录**（`results/{session_dir}/`）下的那份。其他 session 的 task_plan 是参考不是指令（跨 session 污染铁律）。
   - **✅ 最快定位当前活跃任务 = `results/` 按 mtime 排序（2026-08-07 唤醒 #12 实证）**：根目录 `task_plan.md` 是 8 天前（7/30）的 Monkey CellBender 旧任务，但 `ls -lat results/ | head -15` 一眼看出最新修改的 session 目录 = `memomics-1135ed52`（8/7 20:31）→ 读该目录下的 `task_plan.md` 即当前主线（人海马 GSE278576 40 样本 ArchR QC）。**比对照 system_log.jsonl 快得多**——活跃任务必然有频繁写入的 session 目录（task_plan.md 每次唤醒都 patch），mtime 最新即活跃；多个候选时再叠加\"哪个目录有 run_serial/watchdog 脚本 + 活跃日志\"二次确认。判定顺序：`ls -lat results/` 找最新 session → 读其 task_plan 核对 Goal 与当前会话一致 → 不一致才回退 system_log.jsonl 深挖。
   - **⚠️ 根目录 task_plan 可能是其他 session 残留（2026-08-03 唤醒 #7 实证）**：`MEMOMICS_HOME/task_plan.md`（根目录）描述的是 Monkey CellBender 批处理任务，但当前 session（memomics-2f229850）的真实主线是 hdWGCNA/F2 分析。**判定方法**：① `search_files(results, task_plan*.md)` 列出所有 task_plan；② 对照当前 session 目录（system_log.jsonl 位置 + 产出文件）确定真正归属；③ session 的任务可能记录在 `task_plan_CLOSED.md.bak`（用户"停止，不需要task_plan了"后归档改名）——读到 CLOSED 标记 = 主线已结束，只汇报不续跑。
2. **核对 Goal 字段** — task_plan 的 Goal 必须与当前会话用户实际要求一致。占位 Goal（"你是谁？"）或空模板 → 不自动执行（详见 `references/empty-template-taskplan-no-resume.md`）。
3. **读 Current Phase + Phases 状态** — 完成/待办一目了然。
4. **产物完整性复查** — `search_files` 每个已完成 Phase 的输出目录 + 读 verify 状态文件（如 `verify_xxx_status.txt`，注意是磁盘产出，不是 task_plan 自述）。
5. **查 alerts.json** — 存在 → 按 urgency 处理；不存在 = 无异常（直接列在汇报里）。
6. **查后台进程/日志** — ⚠️ **脱离式批处理（run_serial.sh / subprocess.Popen / start /B 启动）不在 Hermes `process(action='list')` 追踪内——返回空是预期行为，绝不代表"无后台任务"（2026-08-07 memomics-1135ed52 唤醒实测：process(list) 空，但 tasklist 裸 grep 显示 Rscript 54040 (1.6GB) + bash/cmd 进程链，批处理正常推进到第 3 个样本）**。判定脱离式任务"还在跑"必须用：① tasklist 裸 grep（Rscript/bash/cmd 进程存在 + 大内存 worker）② DONE_MARK 目录计数增长 ③ 最新样本 log 的 mtime 增长（>4min 无变化 = 可能 stall）。Hermes 追踪的 PID 存在时才走三源验证；process(list) 空 + 上述三证据齐 = 任务在跑，不是任务死了。再 `read_file(log/system_log.jsonl, offset=-30)` 读尾部 → **确认无用户新指令**（**只有显式用户消息才是响应触发器；工具调用条目不是**——每次唤醒自己都会在日志尾部追加 search_files/read_file/patch 等工具调用记录，这些是本轮/上轮唤醒的簿记，不是指令；无则只汇报状态，不把历史日志自行解读为任务指令）。唤醒 #18 实证：日志尾部出现上一轮唤醒自身的 read_file/patch 条目 → 判定"无新用户指令"，仅汇报状态。
7. **报告 + 给选项（A/B/C/D），不做任何自动启动**。

### ⛔ task_plan 滞后于用户在场期间的追加执行（2026-08-03 唤醒 #20 实证）

唤醒时发现 task_plan 停留在 07-31，但 08-01 用户在场期间实际完成了 5 项追加执行（hdWGCNA 官方重跑成功、debate 服务修复、正式辩论归档、teaching 脚本、CNS 图）——**全部未回写 task_plan**。且 task_plan 记录的"hdWGCNA 在 MF 不可行"负面结论已被官方全基因集重跑推翻（power=10 R²=0.982, 11 模块；首次失败根因是 top3000 HVG 子集参数问题，不是方法问题）。

**判别要点**：
- ⛔ 引用 task_plan 的 Phase 状态或"负面结果/失败"前，必须用文件系统证据交叉验证：`verify_*.txt` 时间戳或产出文件 mtime **晚于 task_plan 最后更新时间** = 未回写证据
- ⛔ task_plan 记录的负面结论不是永久事实——后续重跑可能成功；引用前先查产出目录是否有更新的 verify 文件
- ✅ 唤醒发现滞后 → **先回写 task_plan（补录遗漏 Phase/追加记录），再汇报**；禁止基于过时 task_plan 自动执行下一步
- ✅ 唤醒汇报 = 三源验证结果 + task_plan 滞后情况 + 修正后的真实状态，而不是 task_plan 的复述

### ⛔ 唤醒记录追加格式（审计链）

**🔴🔴 终态唤醒写 task_plan 前必做五连 + 锚点铁律（2026-08-08 终态 #0 复犯实证：变体 6 已记录仍再犯）**：本唤醒在 65KB/787 行（远超 250 行阈值）且已含 3+ 条完整终态记录的 task_plan 顶部，又追加第 4 条全量终态记录，标题直接抄系统消息头 `唤醒 #0`（文件内已有 #0/#0b/#4 终态记录，最大号已达 #40+），且 patch 锚点选了共享头部块（`**Session**` + `**创建/更新**` 时间戳 + `## 唤醒 #N` 头——变体 4/5 明令禁止的雷区）。**硬顺序：写 task_plan 前先做这 5 步，缺一不可**：
1. `grep -o "唤醒 #[0-9]*" task_plan.md | sort -t'#' -k2 -n | tail -1` → 新记录编号 = 最大号 + 1；**禁止抄系统消息头 #N，禁止自造"新周期/新循环/唤醒 #0"复合标签**（终态唤醒也不例外，终态 ≠ 从 0 重计）
2. `wc -l task_plan.md` → >250 行 = 先压缩例行记录（压成一行摘要），压缩是追加前第 1 步，不是顺带
3. 已有 🏁 终态/终态保持完整记录 + 三源验证无变化 → **只验证 + 汇报，不再追加全量终态记录**（重复 = 审计链噪音；若判断必须留痕，用一行例行摘要替换旧例行行，不新增全量段）
4. patch 锚点只选自己正文唯一行（带样本名/唯一数字），**永不锚共享头部块**（标题/Session/创建更新时间戳/`## 唤醒 #N` 头）
5. 已追加且发现违规 → 修正：新记录标题改回 `唤醒 #<最大号+1>`；若是纯重复终态段 → patch 删掉自己的冗余段（锚冗余段本身，不锚共享头）

**⚠️ 唤醒编号 = task_plan 内 session 自增序号，与系统唤醒消息头 #N 不同源（2026-08-07 memomics-1135ed52 唤醒 #35 实证）**：系统消息头显示 `[系统唤醒 #13]`（LoopX 全局计数），但 task_plan 已记录到 唤醒 #34 → 本唤醒追加记录正确编号为 **唤醒 #35**（延续 task_plan 现有最大序号 +1）。**禁止用系统唤醒头 #N 直接做 task_plan 记录编号**——两个计数器的步进/起点都不同，用消息头 #N 会与既有记录同号或跳号，破坏审计链连续性（同号重复还会触发 sibling 去重逻辑误判）。**规则：追加唤醒记录前先 grep task_plan 现有最大 `唤醒 #N`，新记录 = 最大号 +1；消息头 #N 只用于区分"这是新的一轮唤醒"，不进入 task_plan。**
> 🔴 **变体 6（2026-08-08 终态唤醒 #0 实测）：自造复合标签（"唤醒 #0-新周期"）同样是编号违规 + 重复终态记录**——终态 task_plan（752 行 / 62KB，远超 250 行压缩阈值）已含 `🏁 终态确认` + `唤醒 #4` + `唤醒 #0` 三条完整终态记录，最大编号已达 #40；本唤醒却追加了第 4 条全量终态记录，标题写成 `唤醒 #0-新周期`（抄了系统消息头 #0 + 自造后缀），正确做法是 grep 最大号 → **#41**。两条铁律叠加：① 编号永远 = `grep -o "唤醒 #[0-9]*" task_plan.md | sort -t'#' -k2 -n | tail -1` +1，终态唤醒也不例外，禁止抄消息头或自造标签；② 终态条目已存在完整版（变体 5 规则）→ 后续终态唤醒**只验证 + 汇报，不再追加全量记录**——三源验证无变化时按"例行瘦身例外"一行摘要替换即可，重复终态记录 = 审计链噪音，也是"task_plan >250 行先压缩再追加"（唤醒 #31/#34 规则）的直接违反。压缩自检是追加前第 1 步，终态 + 已有多份完整记录 = 最该压缩/跳写的场景。
> ✅ **终态零写入正向案例（2026-08-08 唤醒 #1 实测，memomics-1135ed52 终态复验）**：task_plan 已达 787 行 / 65KB（远超 250 行阈值），文件顶部已含 `🏁 终态确认` + `唤醒 #0b/#4/#0` 多条完整终态记录（含 40/40、Keep 265,909、P4 待确认红线）。本轮唤醒只做：① 三源验证（PowerShell Get-Process Rscript/R=0 + watchdog/run_serial/fallback/bridge/guardian 残留 grep + 磁盘 GSM*/ 计数 40/40 + cron 目录仅 ticker 系统文件）② 汇报状态 + 列下一步选项 → **对 task_plan 零写入，P4 红线未触碰**。这是正确的终态行为：文件已超阈值且终态记录已多份完整，追加任何内容（哪怕一行摘要）都是变体 6 违规 + 进一步撑大文件；压缩维护（65KB→250 行内）是专门清理动作，不是例行唤醒的职责（并发写 = 变体 4/5 风险）。**判定口诀：终态 + 文件超阈值 + 完整记录已在 → 验证 + 汇报即可，零写入 = 最优**；task_plan 压缩建议在汇报里作为可选下一步提出（如\"需要我压缩 task_plan 吗\"），留给用户在场拍板。
> 🔴 **复犯实证（2026-08-07 memomics-1135ed52 唤醒 #18/LoopX）：规则在磁盘 ≠ 实操遵守——LoopX 消息头的编号太显眼，还是会拿来用**。task_plan 当时已记录到唤醒 #36（LoopX #17）、sibling 21:12:38 又写了 #37，但本唤醒仍以消息头 `[系统唤醒 #18]` 作为 task_plan 记录编号写成"唤醒 #18"，正确编号应为 **#38**（最大号+1）。后果叠加：编号错 + 头部锚点 patch 把 sibling #37 头吞掉（见 sibling 变体 4）。**强制自检：写 task_plan 唤醒记录前，先 `grep -o "唤醒 #[0-9]*" task_plan.md | sort -t'#' -k2 -n | tail -1` 拿到真实最大号，再决定编号——禁止直接抄消息头 #N，无论它多显眼。**
> 🔴 **变体 2（同序列下一轮实测）：不抄消息头但信任"顶部最新记录"同样错 — 顶部记录 ≠ 全文件最大号**。本唤醒读 task_plan 时顶部最新记录是 `唤醒 #18`（21:12），据此追加 `唤醒 #19`——但文件中部还躺着 `唤醒 #36/#37`（sibling 21:12:38 写入）→ 编号回退 18 个号，审计链断号。**根因：task_plan 顶部是"最近被 patch 的位置"（新记录常插顶部），不是"最大号所在位置"——sibling 并发下大号记录可能写在文件中部/尾部**。**判定铁律：① 追加唤醒记录前，编号依据 = grep 全文件最大 `唤醒 #N`（`grep -o "唤醒 #[0-9]*" task_plan.md | sort -t'#' -k2 -n | tail -1`），顶部记录只作"最近状态"参考，**绝不**当最大号；② 出现"顶部 #18、中部 #37"这种断号 = 既有记录已乱（sibling 冲突），新记录编号 = 全文件最大号 +1 即可，不要试图补齐断号；③ 汇报里写明"按全文件最大号 #37 → 本次记录 #38"，让审计链可追溯。**

每次唤醒检查完成后，在 task_plan.md 末尾**追加**（不覆盖）一行更新记录：
```
> 更新于 {日期} 唤醒 #{N}：{检查结果摘要}。{门禁状态}未自动执行。
```
- 保留历史唤醒记录（如"唤醒 #2 停止自动重试"），新记录追加在后面
- 目的：审计唤醒轮次、决策轨迹、门禁何时设置/是否被尊重——后续唤醒和用户都能回溯
- 反例：覆盖旧记录 = 丢失"谁在何时决定停重试/待确认"的痕迹，门禁可能被无意解除
- **例行重复记录的瘦身例外（唤醒 #8 验证）**：连续多次唤醒状态完全相同的例行记录（如"Phase 1-3 复查通过，Phase 4 待确认"）可以直接替换上一条例行记录，防止页脚无限膨胀；但**关键决策记录（停止重试 / 待确认门禁 / 参数变更）任何情况下不得覆盖**——替换前先确认被替换行只含例行状态、不含决策信息
- 🔴 **批处理长任务的唤醒记录必须定期压缩 — 否则 task_plan 膨胀到不可读（2026-08-07 memomics-1135ed52 唤醒 #31 实测）**：40 样本 ArchR 批处理连续唤醒到 #31 时 task_plan 已达 444 行 / 31KB，其中 ~90% 是例行唤醒记录（三源验证 + 剩余 + 预计 + cron 检查），真正有长期价值的只有故障接管 / 决策 / 参数变更几条。**压缩触发阈值：唤醒记录 ≥15 条或 task_plan >250 行时，追加新唤醒记录前必须执行压缩自检（`grep -c "唤醒 #" task_plan.md` 计数 + `wc -l` 行数）→ 超阈值先压缩再追加——压缩不是"顺带"**——把旧例行记录压成一行摘要（`#N 20:11 36/40 hc35 67% 无干预`），保留：Goal / Environment / Phase 状态表 / 红线 + 关键决策记录（故障接管、门禁、参数变更、sibling 冲突处理）原样。压缩是审计链的**整理不是删除**：每行摘要保留时间戳 + 关键数字，决策记录完整保留，后续唤醒仍能回溯"谁在何时设的门禁"。单条例行记录从全量 15 行压到 1 行，30 条就省 ~400 行。**注意：压缩动作本身也要用 patch 而不是 write_file 全量覆盖**（并发唤醒场景下 write_file 会丢 sibling 记录，铁规 1.5 多 Agent 规则同样适用）。
- 🔴 **复犯实证（2026-08-07 唤醒 #34）：#31 定阈值后 #33/#34 仍连续追加全量例行记录，task_plan 膨胀到 552 行 / 42KB（30+ 条唤醒记录）——"顺带执行"表述太弱。硬顺序：压缩自检是追加前的第 1 步；超阈值时压缩对象 = 除最新 2-3 条外的全部例行记录（保留最近几条供近期回溯），关键决策记录不受影响。**
- ⚠️ **patch 表格行注意管道符 — `||` 双管道会破坏 markdown 表格（2026-08-07 唤醒 #34 实测）**：patch Phase 状态行时误写成 `|| P1+P2+P3`（旧串行首 `|` 保留 + 新串又加 `|`）→ 表格渲染错乱需第二轮 patch 修复。patch markdown 表格行时 new_string 必须完整含行首单管道 `|`，patch 后 `read_file` 核对该行无 `||` 残留。
- **门禁内嵌行的替换判定（唤醒 #9→#16 验证）**：例行记录常把门禁状态内嵌在文本里（如"Phase 4 仍保持待用户确认（唤醒不代确认——既有决策），debate 裁决待用户在场手动触发"）。这类行**可以**被替换——只要新行**原样重申**同一门禁。禁止覆盖的是门禁状态本身变更的记录（如"待确认"改成"已执行"、"停止重试"改成"已重试成功"）。判定口诀：**门禁照抄可替换，门禁变更必须留。** 唤醒 #16 实证：替换 #15 例行行时原样重申门禁短语，审计链完整。

### ⛔ 多 Agent 并发唤醒 — task_plan.md 写入冲突（2026-08-07 memomics-1135ed52 唤醒 #1 实测）

同一任务可能被**多个唤醒 Agent（sibling subagent）同时监控**：本唤醒 patch task_plan.md 时收到警告 "file was modified by sibling subagent 'a64a5bb9-...' at 18:19:29 — after this agent's last read at 18:07:46"。另一个 Agent 也在读同一个 task_plan 并写入唤醒 #3 检查记录。

**规则**：
1. **写 task_plan.md 前先 re-read**（patch 工具会自动警告并提示 re-read）；若收到 sibling 修改警告 → 先读最新版再合并 patch，不要盲写覆盖
2. **两份唤醒记录可以共存**——sibling 记录"唤醒 #3 检查"、本 Agent 记录故障接管细节，都是审计链的一部分；用 patch 合并而不是 write_file 全量覆盖
3. **多 Agent 各自部署 watchdog 时注意去重**——若两个 watchdog 都在跑，保留脱离生命周期那个（PowerShell Start-Process），杀掉 Hermes 管理的重复实例（`process(action='kill')`），防止将来双启动 run_serial
4. 判断"任务是否已被 sibling 接管"：读 task_plan 最新 mtime + 检查是否有比自己更新的唤醒记录条目

### ⛔ 既有门禁决定不可被后续唤醒推翻

task_plan 已记录的门禁决定（如"停止自动重试，待用户在场时手动触发"、"Phase 4 待用户确认"）是**跨唤醒持久**的：
- 后续唤醒（#3/#4/...#N）必须尊重，不得因为"这次 API 可能好了"就擅自重启被停止的重试
- 唯一能解除门禁的是：**用户在场时的明确指令**
- 唤醒 #6 案例：Phase 3 debate 被 #2 停重试、Phase 4 待确认 → #6 复查产物后直接汇报等待，未触碰任何门禁 —— 这是正确示范

### ⛔ 用户确认门（本 session 核心教训）

task_plan 中标注 **「待用户确认后执行」** 的 Phase，**任何唤醒轮次都无权代替用户确认启动**。唤醒 #2 不代确认 → #3 → #4 同理。理由：
- 唤醒是无人值守的定时检查，用户不在场 → 擅自启动 = 未经同意启动分析
- 与"删数据/擅自重跑"同一级别的信任破坏（用户最严重投诉类别）
- 唤醒的职责是：**复查已完成为止的产物 → 报告状态 → 列选项 → 等用户拍板**

⚠️ **唤醒不得把"继续执行下一个待办"字面化**。唤醒 prompt 常写"继续执行下一个待办"，但若下一 Phase 标注待用户确认 → 停下来报告，不要执行。待办是 pending 还是 waiting-for-user，以 task_plan 标注为准。

### ⛔ 终态处理：全部 Phase complete + 停止标记（唤醒 #9 实证）

当 task_plan 显示 **所有 Phase 均 complete** 且 Current Phase 段含 `> ⛔ 用户下达"停止"命令`（或类似门禁）时：

1. **停止标记是硬门禁**，与"待用户确认"同一级别——即使 `> ⏭️ 后续（等待数据/等待用户）` 注释里写了下一步（如"跨物种对比"），那只是**备忘，不是执行指令**。只有用户当前在场明确说"继续/开始下一步"才能推进。
2. **汇报格式应明确终态**：Phase 状态表 + 关键产出验证 + 明确结论（"无未完成待办 / 无运行中进程 / 不需要继续执行"），然后列下一步选项等待用户。
3. **顺手关心跳（终态唤醒每次必查，不只完成那一刻）**：若该任务还挂着 heartbeat cron（`cronjob(action="list")` 检查），全部 complete 后应 `cronjob(action="remove")` 关闭——否则每 15m/30m 空唤醒烧 token。这是心跳的**主 Agent 侧关闭路径**（正常完成路径，不是用户取消路径）。
   - ⚠️ **2026-08-02 唤醒 #11（memomics-1c1890da ArchR 会话）实证**：task_plan 显示 Phase 1-6 全部完成 + 停止标记已就位，但唤醒只做了产物复查+三源验证就汇报，**没有执行 `cronjob(action="list")`**。若该会话还挂着心跳，后续每 15m/30m 仍在空唤醒烧 token。**判别口诀：只要读到"全部 complete + 停止/等待标记"，本轮就必须执行 `cronjob(action="list")`**——有残留→remove；无→把"无残留 cron"写进汇报。跨唤醒漏关是常态（完成时刻没关、后续唤醒也没补查），所以每次终态唤醒都要重新确认，不能只在任务完成那一刻检查一次。
   - ⚠️ **2026-08-02 唤醒 #16（同一 memomics-1c1890da 会话）复犯实证**：再次读到"Phase 1-6 全部完成 + 停止命令"终态，根目录 task_plan 识别正确（根目录是 Monkey CellBender 别的 session 的任务，不是本 session）、三源验证正确、终态汇报正确——**但仍然漏掉 `cronjob(action="list")`**。skill 已明确记录 #11 的教训却再次跳过，说明"顺手关心跳"的措辞强度不够。**升级为硬顺序：终态唤醒的第 1 个工具调用就应该是 `cronjob(action="list")`（与"读本 session task_plan"并列，先于产物复查）**。汇报模板同步升级：终态汇报必须包含一行 `cron 检查：有残留→已 remove / 无残留`。
   - 🔴 **2026-08-02 唤醒 #18（同一 memomics-1c1890da 会话）第三次复犯实证 — 规则在磁盘 ≠ 规则生效**：升级为"硬顺序"后 #18 仍只做"读 task_plan + search_files + tasklist/nvidia-smi"就汇报，**汇报里依然没有 `cron 检查` 字段**。根因：**唤醒时 Agent 未加载本 skill**——规则躺在 skill 文件里，而唤醒 prompt 只说"读 task_plan → 看产出 → 继续待办"，不会自动带出这条规则。三次漏查（#11/#16/#18）证明：**只写进 skill 不够，必须在记忆层有兜底**（本规则已同步写入 memory 的跨 session 污染铁律条目）。唤醒 Agent 强制自检：终态汇报发出前逐字段核对——`cron 检查` 字段缺失 = 汇报不完整 = 禁止发出。同理 `下载进度数字` 必须磁盘实测（#18 又引用了 task_plan 文本的"2/40"而未 search_files 实测 GSE278576 目录——#7 教训复犯）；实测失败时在汇报中明确写"未实测"而不是引用旧文本。
   - 🔴 **第四次复犯（2026-08-02 终态唤醒，同一 memomics-1c1890da 会话）— 结构性修复：`cronjob(action="list")` 必须与"读 task_plan"放进同一并行工具调用批次**：即使 skill 三处记录 + memory 兜底，本次终态唤醒（读到"Phase 1-6 全部完成 + 停止命令 + Phase 7 pending"）**依然只做"读 task_plan → search_files → tasklist"就汇报**，无 `cronjob(action="list")`、汇报无 `cron 检查` 字段。为什么前三次教训都记着还漏？因为"第 1 个工具调用"是**顺序性**指令——唤醒把"读 task_plan"当第 1 步后，后续步骤注意力就转到产物复查，cron 检查被挤掉。**本规则升级（替换"硬顺序"表述）**：终态判定信号（task_plan 显示全 complete + 停止/等待标记）出现在读 task_plan 结果的同时，`cronjob(action="list")` 必须和读 task_plan **放在同一个并行工具调用批次**（同一轮 `read_file(task_plan)` + `cronjob(action="list")` + `search_files` 一起发出），而不是作为下一步单独调用——同批 = 不可能被遗忘。汇报模板中 `cron 检查` 行是**硬字段**：有残留→已 remove；无→写"无残留 cron"；未查→禁止发出汇报。
### ⛔ cronjob 工具不在工具集时的 cron 检查兜底 — 读 ticker 文件（2026-08-07 memomics-1135ed52 唤醒 #1 实证）

本 skill 多处要求 `cronjob(action="list")` 检查残留，但**工具集里不一定有 cronjob 函数**（本轮唤醒函数列表无此工具），且 `hermes cron list` CLI 不在 PATH（`hermes: command not found`）。此时 cron 残留检查的可靠方法 = 直接读 Hermes 内部状态文件：

```bash
# 1. ticker 心跳是否活着（epoch 秒，转本地时间看新鲜度）
cat /e/MEMOMICS_HOME/hermes_home/cron/ticker_last_success
cat /e/MEMOMICS_HOME/hermes_home/cron/ticker_heartbeat
date -d @$(cat /e/MEMOMICS_HOME/hermes_home/cron/ticker_last_success) '+%H:%M:%S' 2>/dev/null
# 2. cron 是否在写执行记录（mtime 近期更新 = 有任务在跑/刚跑过）
ls -la /e/MEMOMICS_HOME/hermes_home/cron/executions.db
ls -la /e/MEMOMICS_HOME/hermes_home/cron/output/
```

- `ticker_last_success` 与 `ticker_heartbeat` 是 epoch 秒；新鲜（转本地时间在最近几分钟内）= **ticker 心跳活着 = cron 机制在跑**
- `executions.db` mtime + `output/` 目录内容 = 是否有 cron 任务实际在写（output/ 空 + db mtime 老 = 无活跃任务）
- 汇报仍含 `cron 检查` 硬字段，写法示例：`cron 检查：ticker 心跳活着（02:03），output/ 空，无残留任务` 或 `cron 检查：无残留`
- 不要因为 `cronjob` 工具缺失就跳过 cron 检查——文件兜底 30 秒完成，与读 task_plan 同一并行批次发出
- 🔴 **唤醒 #6（同一 session，#1 已记录此兜底仍复犯）实证**：`cronjob(action="list")` 报"Tool does not exist"后，本轮只把"cronjob 不存在"当结论就继续三源验证，**没有去读 ticker 文件**——规则躺在 skill 里 ≠ 本轮已执行。**修复：cronjob 缺失时，`read_file(/e/MEMOMICS_HOME/hermes_home/cron/ticker_last_success)` 必须与"读 task_plan"同一并行批次发出**，汇报仍含 `cron 检查` 硬字段（如"ticker 心跳活着（02:03），output/ 空，无残留任务"）。同批次 = 不可能被遗忘；顺序指令（"下一步再查"）已多次证明失效。
- ✅ **jobs.json 直接列 job 清单 — 比 ticker 文件更直接的残留判定（2026-08-07 memomics-1135ed52 唤醒 #0 实证）**：ticker 文件只能判断 cron 机制是否活着，**看不到有哪些 job**。直接 `read_file("C:/Users/USERNAME/.hermes/cron/jobs.json")`（`~/.hermes/cron/jobs.json`）列出全部 job（含 `name` / `schedule` / `enabled` / `state` / `next_run_at` / `workdir`）——本唤醒实测：仅 4 个老任务（每日文献分析 / holographic-maintenance / memory-trim-check / daily-wiki-summary，next_run_at 全停 6 月），无本任务心跳 job → 直接判"无残留 cron"，且能引用具体 job 名单给用户看。⚠️ **路径注意：jobs.json 在 `~/.hermes/cron/`（C:/Users/USERNAME/.hermes/cron/），ticker 文件在 `/e/MEMOMICS_HOME/hermes_home/cron/`——两个目录都查**。判定分工：jobs.json 给 job 清单（有没有残留），ticker 给机制活性（cron 是否在跑），互补。汇报示例：`cron 检查：jobs.json 仅 4 个老任务（文献/记忆维护/wiki），无本任务心跳，无残留`。
- ⚠️ **`hermes_home/runtime/jobs.json` 是 Hermes 运行时会话历史，不是 cron job 清单 — 读错文件 = 浪费轮次（2026-08-07 memomics-1135ed52 唤醒 #13 实测）**：唤醒做 cron 残留检查时先读到了 `MEMOMICS_HOME/hermes_home/runtime/jobs.json`，其结构是 `job_id / session_id / label=agent_conversation / state / created_at`——这是**历史 Agent 会话的运行记录**（几十条 succeeded/interrupted，跨 08-03 全天的 session 列表），**不是 cron 任务**。cron 残留判定的正确文件是 `~/.hermes/cron/jobs.json`（字段 `name/schedule/enabled/next_run_at`，见上条）。**判定口诀：字段含 `session_id`/`label=agent_conversation` 的是 runtime 历史，不是 cron；字段含 `schedule`/`next_run_at` 的才是 cron job 清单**。同时注意 `search_files(pattern="cron*", path=hermes_home)` 命中的是 LSP node_modules 里的 crontab 类型定义（pyright typeshed），不是 Hermes cron 目录——文件名 glob 不会下钻进 `cron/` 目录，找 ticker 文件要 `search_files(pattern="*", path=".../hermes_home/cron")`。
- ⚠️ **`hermes cron list` 空输出 + exit 0 ≠ 无 cron — 仍需文件兜底确认（2026-08-07 memomics-1135ed52 唤醒 #13 实测）**：`hermes cron list 2>&1 | head -60` 返回 `{"output": "", "exit_code": 0}`——既不是 skill 早前记录的"hermes: command not found"（exit 127），也不是 job 清单。空 + exit 0 的原因可能是 CLI 存在但子命令静默无输出、或 stderr 被吞。**规则：`hermes cron list` 的任何结果（not found / 空 / 报错）都不足以单独下"无残留 cron"结论——统一走文件兜底（`~/.hermes/cron/jobs.json` 清单 + `hermes_home/cron/ticker_*` 活性）**，与读 task_plan 同一并行批次。中程唤醒（任务仍 in_progress、心跳由 watchdog/guardian 独立进程承担）时 task_plan 已记录的"心跳非 cron"可以佐证，但终态唤醒必须实测文件。

4. **不要因"全完成"跳过状态验证**：仍应快速核验产物（search_files）+ 确认无后台进程残留，汇报里给出证据，而不是只报"完成"。

### ⛔ 已完成 Phase 清理偏好 — 用户明确要求"完成的就删除掉"（2026-08-02 实证）

当用户说"完成的就删除掉，task_plan"（或类似"清理 task_plan"指令）时，这是**清理偏好，不是删除任务**：

- **删除**：已 complete 的 Phase 详细记录（任务清单、输出、Errors Encountered 表、Decisions Made 表——它们已完成使命）
- **保留**：Goal（任务定义）+ Environment（环境信息仍有用）+ Current Phase 摘要行 + **未完成待办**（如"Phase 7 跨物种对比 — pending"）
- 目的：让 task_plan 回到"快速恢复状态"的核心价值——只看未完成的，不看已完成的历史
- 示例：90 行 (5KB) → 34 行 (1.6KB)，只留 Goal + Environment + "Phase 1-6 完成 ✅" 摘要 + "Phase 7 pending"
- ⚠️ 与"唤醒记录追加"不冲突：清理是用户在场主动发指令时做；唤醒记录是每次唤醒被动追加

### ⛔ debate_analysis 自动重试上限

debate_analysis（或依赖 LLM API 的裁决类工具）连续失败 ≥3-4 次且根因是 API 层故障 → **停止自动重试**：
- 在 task_plan Decisions/Errors 记录："debate 裁决第 N 次失败（API 层故障），停止自动重试，待用户在场时手动触发"
- API 故障是环境态，重试不会因次数增加而变好 → 只会烧 token + 阻塞主流程
- 不要编码成"debate_analysis 不可用"（负面断言）——是**重试策略**：封顶、记录、交还用户触发

### ⛔ 阻塞 Phase 的前置数据检查 — 唤醒汇报必须含数据下载进度（唤醒 #4 实证）

当 task_plan 显示 Phase 1-N 全部完成、下一 Phase（如猴-人跨物种对比）处于 **pending 且阻塞原因为"数据下载中（用户手动）"** 时，唤醒检查必须在汇报中包含**前置数据下载进度**——阻塞原因本身就是"数据未齐"，汇报不含下载进度 = 汇报不完整：

1. **数文件** — `search_files(pattern="*", path="<数据下载目录>")` 统计已下载样本数（如实测 2/40）
   > ⛔ **进度数字必须磁盘实测，勿直接引用 task_plan 文本（唤醒 #7 复盘）**：task_plan 自述的"当前 2/40"是**上次更新时的快照**，用户可能已继续下载/续传。唤醒汇报里的下载进度数字必须以 `search_files` 实测目录为准；task_plan 文本只作线索不作证据。同一原则适用于任何 task_plan 自述的计数（产出文件数、已完成样本数）——磁盘证据优先于文本复述。
2. **检查每样本完整性** — 配套文件是否齐全。ATAC 例：`fragments.tsv.gz` 主文件 + `.tbi.gz` 索引**必须成对**；主文件在但索引缺失 = 下载未完成/不完整 → 该样本暂不可直接喂 createArrowFiles
   > ⚠️ **实测示例（memomics-1c1890da GSE278576，2026-08-02 终态唤醒）**：目录实测 hc77 ✅ 含 `GSM8549615_hc77_atac_fragments.tsv.gz` + `.tbi.gz`（成对完整）；hc78 ⚠️ 仅 `GSM8549616_hc78_atac_fragments.tsv.gz`，**缺 `.tbi.gz` 索引 = 样本不完整，不可直接喂 createArrowFiles**。汇报必须逐样本标记 ✅/⚠️，不能只写"2/40 就位"——用户要一眼看到"还差什么"（hc78 缺索引，需续传或重新下载）。
3. **汇报格式** — 下载进度表 + 每样本完整/不完整标记（hc77 ✅含索引 / hc78 ⚠️缺索引），让用户一眼看出"还差什么"
4. **选项给出** — 基于进度给可执行选项（如"继续下载剩余样本" vs "用已就位的 hc77/hc78 先做小规模试跑"），**由用户拍板，唤醒不代启动**

> 前置数据检查与已完成 Phase 的产物复查同等重要。已完成的 Phase 复核 + 阻塞 Phase 的前置缺口 + 三源验证，三者齐备才是完整的唤醒终态汇报。

### 唤醒汇报模板（精简）

```markdown
✅ 唤醒 #N 检查完成。汇报状态：
- Phase 进度表（已完成 ✅ / 待确认 ⏸ / 未开始 ⏳）
- 产物完整性复查结果（每 Phase 图/表/RDS 数量 + verify 结果）
- alerts / 后台进程 / 日志异常 → 无
- ⚠️ 停在 XX Phase：task_plan 标注「待用户确认」，唤醒不代确认
- 下一步选项：A/B/C/D（请确认）
```

**门禁溯源（唤醒 #14 验证）**：每个阻塞点必须引用**设定该门禁的唤醒号**——如"Phase 4 待确认（唤醒 #2 不代确认——既有决策）"、"debate 裁决停止重试（第 4 次 API 层失败，唤醒 #2 记录）"。用户能审计"谁在何时设的门禁"，而非只看到门禁存在；后续唤醒也能快速定位源头记录。

**选项要可直接回复**：给出用户能原样打出的具体指令（如 `继续 Phase 4` / `触发 debate 裁决`），优于纯 A/B/C/D 抽象标签——用户在唤醒间不在场，醒来后一句话即可放行。

---

## ⚠️ 进程存活验证 — 勿用 tasklist //FI（2026-08-07 实测）

MSYS/git-bash 下 `tasklist //FI "IMAGENAME eq Rscript.exe"` 返回**空输出**（//FI 转义问题），会误判"进程全死"。必须用 PowerShell：

```bash
powershell.exe -NoProfile -Command "(Get-Process Rscript -ErrorAction SilentlyContinue | Select-Object Id,StartTime,CPU | Format-Table | Out-String)"
# 查特定 PID
powershell.exe -NoProfile -Command "(Get-Process -Id 26925 -ErrorAction SilentlyContinue).StartTime"
```

三源验证：① PowerShell 查 Rscript ② monitor.log 时间戳是否仍更新 ③ 样本 log 尾部最后动作。`ps aux` 也能看到 bash 脚本，但看不到 Rscript.exe（Windows 原生进程不映射）。

## 🔴 铁规 2: Windows 进程生命周期 — 必须脱离式启动

Hermes 的 `terminal(background=true, notify_on_complete=true)` 创建的进程绑定在 Hermes 会话生命周期上。
当 Hermes 会话回收、上下文压缩、或 LLM 更换时 → **后台进程静默死亡（无日志、无提示）**。

### ✅ 正确做法：subprocess.Popen 脱离式启动

```python
import subprocess, os, sys

def launch_detached(cmd: str, log_path: str, cwd: str = None) -> int:
    """启动脱离 Hermes 生命周期的 Windows 系统级后台进程"""
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'w') as log_f:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            cwd=cwd,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW  # 系统级脱离
        )
    return proc.pid
```

### ✅ 或使用 start /B

```bat
rem launcher.bat — 关掉终端也不影响
start /B python F:\path\to\run_pipeline.py > stdout.log 2>&1
```

## 🔴 铁规 3: LLM 主动巡检 — 不等人问

脱离式启动后，LLM 不能再依赖 process.poll() — 改为每轮对话前读磁盘日志文件：

```python
def check_progress(log_path: str) -> dict:
    """读日志文件提取进度"""
    import re
    if not os.path.exists(log_path):
        return {"status": "not_started", "last_line": ""}
    with open(log_path, 'r') as f:
        lines = f.readlines()
    last_line = lines[-1].strip() if lines else ""
    # 提取样本号: "Processing sample 5/26"
    match = re.search(r'(\d+)/(\d+)', last_line)
    return {"status": "running", "last_line": last_line,
            "progress": f"{match.group(1)}/{match.group(2)}" if match else "unknown"}
```

**巡检频率**: 每 2 分钟一次（用户明确要求，2026-07-24 验证）。

**推荐监控架构（2026-07-24 验证可行）**：

第 1 层 — 后台 shell 死循环写 monitor.log：
```bash
while true; do
  now=$(date '+%H:%M:%S')
  gpu=$(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader | head -1)
  s1=$(tail -1 "cellbender_output/S1/run.log" | grep -oP 'epoch \d+' | tail -1)
  done_count=$(ls cellbender_output/*/cellbender_output_filtered.h5 2>/dev/null | wc -l)
  echo "[$now] GPU=$gpu | S1=$s1 | done=$done_count/26" >> monitor.log
  sleep 120
done
```

第 2 层 — Agent 周期性读 monitor.log + 三源验证（nvidia-smi + tasklist + dir），主动汇报。

**⚠️ execute_code 超时陷阱**：`execute_code` 内 `time.sleep(120)` + terminal 调用 → 300s 后 stdout 全部丢失。不要用 execute_code 做长时间轮询。

**⚠️ MSYS bash `sleep && tail` 缓冲区陈旧陷阱 (2026-07-30 验证)**：Windows 原生进程（如 CellBender `subprocess.Popen`）写日志时，MSYS bash 的管道层不一定实时看到新写入的内容。`sleep 120 && tail -5 log` 可能返回 3 分钟前的旧行——因为 bash 的文件描述符在 sleep 期间持有的是旧缓冲区快照。**正确做法**：用 `read_file` 直接读文件（绕过 bash 管道层），或分开两个 terminal 调用（不用 sleep 串联），或直接读心跳 monitor 日志。

**⚠️ 文件名陷阱**：CellBender 产出是 `cellbender_output_filtered.h5`，不是 `filtered.h5`。`ls */filtered.h5` 永远返回空。

**汇报模板**: `| 样本 | epoch | 进度 | GPU | 已完成 |`

## 🔴 铁规 4: 串行执行 — 一次一个样本

| 资源 | 单样本 | 两个并行后果 |
|------|--------|-------------|
| RAM | ~7 GB | 14+ GB → OOM |
| VRAM | ~10 GB | 分配冲突 → crash |
| Checkpoint | 稳定 | 互相覆盖 → hash mismatch |
| 输出 h5 | 正常写盘 | 无产出 |

**⚠️ ArchR 场景（2026-08-07 实测，GSE278576 40 样本）**：并发 3 跑 `createArrowFiles` → 5/7 样本在 `.filterCellsFromArrow` 阶段失败，错误 `Cannot open file 'E:\...\tmp\tmp-<hash>.arrow' does not exist`。**根因不是内存，是 ArchR 1.0.3 所有实例共享同一 `outputDirectory/tmp/` 目录** —— 多进程竞争清理临时 Arrow 文件。60GB RAM 能撑并发 ≠ ArchR 能并发。**ArchR Windows 版唯一稳定模式 = 并发 1**。

```python
# ✅ 正确：for 循环串行
for i, sample in enumerate(samples, 1):
    logger.info(f"[{i}/{n}] 开始 {sample}")
    result = subprocess.run(cmd, ...)  # 阻塞等待
    verify_output(output_path)
    logger.info(f"[{i}/{n}] ✅ 完成 {sample}")

# ❌ 错误：并行启动
for sample in samples:
    subprocess.Popen(cmd, ...)  # 多个同时跑
```

**⛔ 串行调度器模式（run_serial.sh，2026-08-07 验证）**：
- 逐个样本：生成 `.bat`（cmd.exe /c 铁规）→ 前台执行（阻塞等待）→ 完成检查 `ArchR_Arrow_QC_Filtered/{s}/{s}_filtered_cells.csv`
- **已完成检查**（SKIP 逻辑）：`filtered_cells.csv` 存在 = 样本完成 → 跳过（崩溃重启用同一列表自动去重）
- **失败不崩**：单样本失败 → 记录 `FAILED $s` → 继续下一个（watchdog 循环，铁规 11）
- 逐样本日志：`batch/logs/{sample}.log` + `END $s OK/FAILED exit=$ec`
- **⛔ 串行循环活体探针 = 下一个样本 .bat 的 mtime（2026-08-07 memomics-1135ed52 唤醒 #2 实测）**：run_serial.sh 每处理一个样本都重新生成 `batch/run_{sample}.bat`。hc78 完成后 `run_GSM8549617_hc5579.bat` 的 mtime 变为 01:49（旧 .bat 都是 01:19-01:26）→ 立即证明循环活着且已自动推进到 hc5579（其日志 START 01:49:58）。**判定口诀：新 .bat mtime + 新样本 log 出现 START = 循环自动推进正常；进程查询空但 .bat mtime 很新 = 不能判死，用裸 `tasklist | iconv | grep` 再验**。

- 🔴 **调度器静默死亡 — done 冻结 + procs=0 + monitor 活着 ≠ pipeline 活着（2026-08-07 95 分钟事故）**：`run_serial.sh` 在样本完成后可能静默死亡（MSYS bash 被回收/退出），而 `monitor_serial.sh` 继续每 3 分钟写 done 计数。**判定口诀**：done 计数冻结 + 无 worker 进程 + monitor 还在写 = 调度器死了（不是任务在跑）。monitor.log 活着只能证明 monitor 活着，不能证明 pipeline 活着。**修复 = 监控闭环**：停滞检测分支必须加自动重启逻辑（`nohup bash run_serial.sh &`），SKIP 机制保证幂等。防重复重启用 `ps -W | grep run_serial.sh`。详见 `references/scheduler-death-auto-restart.md`。
- ⚠️ **两个同脚本名的调度器 bash 实例同时存在 ≠ "双主循环兜底" — 是重复调度器风险，须验证单实例（2026-08-07 memomics-1135ed52 唤醒 #15 实测）**：`Get-CimInstance` 查到 **PID=5580 和 PID=31292 两个 `bash.exe batch/run_serial_v2.sh` 同时存活**。task_plan 曾把这种状态写成"双 bash 主循环兜底"（正向表述）——**这是错误框架**。按本 skill 自身多实例铁律（重启风暴 / tmp 竞争 / 锁碎片化），两个调度器实例 = 潜在并发派工 → ArchR tmp 竞争。本次健康（procs=1 单 worker hc35 + done 推进正常）只能说明**其中一个实例已 stale/阻塞在锁上**，不能说明双实例无害。**判定口诀：① 看到两个同脚本名 bash 实例 → 第一反应是"谁是多启动的重复实例"（watchdog 在 procs 探测空窗期误判归零后重复拉起是已知根因），不是"多一层保险"；② 验证 = worker 计数（procs 必须 =1，>1 立刻警惕 tmp 竞争）+ 锁文件（.run_serial_v2.pid 内容 vs 存活 PID 对应关系）+ 两个实例的启动时间差（新启动的那个是可疑重复）；③ 汇报用词：写"发现重复调度器实例，已核实仅单实例派工（procs=1）"或"需人工清理 PID 31292"，**禁止写"双主循环兜底"这类正向化表述**——它让后续唤醒误以为双实例是设计意图而放松警惕。**
- ✅ **standalone watchdog_v2.sh 端到端自愈全闭环验证（2026-08-07 18:06→18:22，memomics-1135ed52）**：独立看门狗（PowerShell Start-Process 脱离 Hermes 生命周期，PID 12800）检测到 `procs=0 + done=32/40` → 自动启动 sanctioned 版 `run_serial_v2.sh`（PID 27369）→ **hc11 第三次尝试成功**（18:22:51 OK: 3603→3344 cells, doublet 7.19%，前两次失败均因并发 tmp 竞争）→ 自动串行 hc73 → 33/40——**全程零人工干预**。**关键决策：不杀正在跑的 Rscript（Hermes terminal 链持有）**——等它自然退出/失败（P1 完成后崩溃 → procs=0），watchdog 检测归零后自动重启主循环，而不是手动 kill 浪费已有进度。设计要点：监控（monitor-serial-loop.sh）与重启（watchdog-serial.sh）分离，重启目标必须是当前 sanctioned 脚本名（内嵌 monitor 的自动重启曾因硬编码旧脚本名级联崩溃）。**模板：`templates/watchdog-serial.sh`**（改 DONE_DIR/TOTAL/RUN_SCRIPT 等 6 变量即可复用；含 300s 冷却 + pgrep 双保险防重复启动）。
- ✅ **watchdog_v3 最小可靠版**：锁文件 + 60s 轮询 + 自动跳过已完成样本 + 全完自退。**模板：`templates/watchdog-v3-minimal.sh`**（改 5 个 CONFIG 变量即可复用；无冷却/无重启逻辑，适合已有上层 guardian 或无需自愈的简单场景）。
- 🔴 **wait-loop 兜底接管模板 — 守护层（watchdog+guardian）双死时收尾剩余样本**：**模板：`templates/fallback-takeover-waitloop.sh`**（改 7 个 CONFIG 变量：OUTDIR/LOGDIR/RSCRIPT/CREATE_SCRIPT/WORKDIR/MLOG/LOCKDIR/INFLIGHT_SAMPLE/REMAIN_SAMPLE/HEARTBEAT_STALE_S 即可复用）。核心 = 等 in-flight 样本输出目录出现 → 检查剩余样本已存在则退出 → monitor.log mtime 心跳活性判定（age≥180s 才接管）→ 接管锁 LAUNCH 剩余样本。与 watchdog 同 LOCKDIR 防双启动，绝不 kill 进程。部署前必须 mock 三分支行为级验证（已存在退出 / 心跳停更接管 / 心跳活跃等待）。
- 🔴 **watchdog 的 REMAINING 数组 = 独立续跑权威 — run_serial 主循环死亡后 watchdog 仍能独自推完全批（2026-08-07 memomics-1135ed52 唤醒 #35 实测）**：批处理后期 `run_serial_v3.sh` 主循环**已不在进程列表**（死了/被回收），但 watchdog_v3（bash 9596/35172 双实例，mkdir 原子锁互斥）仍在跑，其 REMAINING 数组含全部剩余样本（hc19/hc73），且每 60s 检查 `Rscript 计数 == 0` 时从数组里**跳过已有输出目录的样本**启动下一个 → 主循环死了也照样推完（hc73 → hc19 → 40/40）。**判定口诀：① 汇报\\\"谁在推进\\\"时以 watchdog 的 REMAINING 数组为准，不以 run_serial 是否存活为准**——主循环死亡 ≠ 批处理停滞，只要 watchdog/guardian 活着且其数组覆盖剩余样本，任务自动续跑；② 验证 watchdog 会续跑剩余样本 = 读 watchdog_v3.sh 的 REMAINING 数组 + 确认它用 `[ ! -d \"$OUTDIR/$SAMPLE\" ]` 跳过已完成（幂等去重）；③ REMAINING 数组是**启动时快照**，不随进度收缩（与 remaining_v2.txt 同理）——靠输出目录存在性判断跳过，不是靠数组长度；④ 汇报措辞：\\\"run_serial 主循环已退出（watchdog 承担推进），剩余 hc19 由 watchdog REMAINING 自动续跑\\\"——不要因为主循环死了就报\\\"任务停了\\\"。
- 🔴🔥 **watchdog_v3 双实例 ≠ 互斥保险 — 是 mkdir 锁死锁信号，monitor.log 冻结 + CPU 0 + 陈旧 lockdir PID 三连证（2026-08-07 memomics-1135ed52 唤醒 #36 实测）**：唤醒 #35 把 \\\"bash 9596/35172 双实例，mkdir 原子锁互斥\\\" 当成正向（互斥=一个持锁一个等待）→ #36 实测发现 monitor.log 停在 20:54:56（13min 未更新）、两个 watchdog bash 进程 **CPU 0 增长**、lockdir/pid 是 **20:34 的旧持有者 40473**（当前两个 bash 是 20:53:56 启动）→ **这是锁死锁：持锁实例已死（或锁未释放），新实例卡在 `while ! mkdir` 循环里互相等，谁都没进主循环**。**判定铁律：① 双 watchdog 实例同时存活 + monitor.log 冻结（>2 个周期不更新）+ 两进程 CPU 不增长 = 锁死锁，不是\\\"双保险\\\"——\\\"mkdir 原子锁互斥\\\"表述只适用于一个实例在正常跑主循环、另一个 SKIP 退出的情形，两个都卡住 = 锁从未被释放；② 锁死锁的根因 = watchdog_v3.sh 的 `kill -0 $owner` stale 自愈在 MSYS PID 命名空间下不可靠（lockdir 写的是 MSYS PID，`kill -0` 检查可能永远失败/误判），陈旧 lockdir 永远清不掉 → 后续实例全部卡在 while 循环；③ 诊断顺序：monitor.log 冻结 → `ps -ef | grep watchdog` 看双实例 + CPU → `cat lockdir/pid` 对比当前存活 PID（不一致 = 陈旧锁）→ 判定死锁；④ 汇报必须写明\\\"watchdog 心跳停更但不影响核心推进\\\"（worker 独立于 watchdog 存活时任务仍健康），不要把监控层死亡报成任务死亡。**
- 🔴🔴 **锁死锁恢复 = bridge 兜底脚本（等输出目录出现 → 启动剩余样本），不杀 worker 不杀 watchdog（2026-08-07 memomics-1135ed52 唤醒 #36 实测）**：唤醒 #36 发现 watchdog_v3 锁死锁（monitor.log 冻结 13min）且 **Rscript 26484 (hc73) 的父进程 = watchdog 35172** → **不能杀 watchdog**（PowerShell Stop-Process 杀 bash 父进程会连带回收其子进程树，正在跑的 hc73 进度会丢）。同时 run_serial_v2 已 ALL DONE（不再续跑）、watchdog REMAINING 数组虽含 hc19 但 watchdog 锁死 → 唯一安全恢复 = **部署独立 bridge 脚本**：`watchdog_hc19_bridge.sh`（`Start-Process -WindowStyle Hidden` 脱离 Hermes 生命周期）每 60s 检查 `[ -d "$OUTDIR/GSM8549648_hc73" ]`（hc73 的 DONE_MARK 输出目录）→ 出现即 `sleep 30`（等文件 settle）→ 再查 hc19 是否已被其他机制启动 → 未启动则 `Rscript create_arrow_qc.R GSM8549649_hc19` 补跑 → 3h 超时自退。**判定口诀：① 锁死锁/监控层死亡时，恢复动作三选：worker 父进程是 watchdog → 杀 watchdog 会丢 worker 进度 → 用 bridge 兜底（等 DONE_MARK 出现再启动剩余）；worker 独立（nohup/subprocess）→ 可直接杀死锁 watchdog 换新；run_serial 还活着 → 只需重启 watchdog 主循环；② bridge 的核心判断 = 等待目标样本的**输出目录**（DONE_MARK 落盘）而不是进程消失（进程消失可能=崩溃，目录出现=确认完成）；③ bridge 自带幂等（启动前再查一次目标是否已被其他机制启动）+ 心跳日志（bridge_<name>.log 每 15 轮写一次）+ 超时自退（防永久空转）；④ 部署后立即验证 5 项：`bash -n` 语法 + 进程存活（Get-CimInstance CommandLine 含脚本名）+ START 心跳 + worker 不受影响 + 磁盘进度不变——**脚本 = 任务关键路径，不验证不许部署**（铁规 13.5 行为级验证）。模板见 `templates/watchdog-bridge-wait-for-output.sh`。**
- ✅ **Guardian No-Op 技术**：当无法停掉 cron/调度器时，把目标脚本替换为无害 no-op stub（只写日志 + exit 0）。详见 `references/guardian-noop-technique.md`。
- ✅ **guardian 层 = 给 watchdog 也配一个看门狗（2026-08-07 18:56，memomics-1135ed52 唤醒 #11 实测）**：watchdog 自身也可能死（18:56:07 `guardian: watchdog_v2 已死，重新拉起` → `WATCHDOG_V2 START 18:56:07`）。**自愈架构应分层：Rscript worker → run_serial_v2 调度器 → watchdog_v2 → guardian**，guardian 只负责一件事——轮询 watchdog 活体（monitor.log mtime 新鲜度 / `Get-Process bash` PID）并在其死亡时重新 `Start-Process` 拉起。唤醒检查时若看到 `guardian: watchdog_v2 已死，重新拉起` 字样：这是**自愈成功事件**（三层全部存活），不是故障；汇报中应如实写"guardian 自动重拉"作为正向证据。判定：guardian 存活 = monitor.log 持续每 2min 更新；guardian 也死了 = monitor.log 冻结 + 无 bash 进程 + watchdog 不在 → 三层全挂才需人工接管。**⚠️ guardian 连续快速重拉 ≠ 失控（2026-08-07 唤醒 #12 实测）**：watchdog 三次死亡（18:56/19:13/19:14），guardian 在 19:13:14 与 19:14:29 相隔仅 1 分钟连续重拉——只要 run_serial_v2 主循环存活（核心推进者），watchdog 死多少次都能被 guardian 拉回，进度不受影响。汇报写"guardian 自动重拉（N 次）"作正向证据即可，不要误判为故障去人工干预。**主循环活体才是真正关心的**（`Get-CimInstance ... -Filter "ProcessId=<PID>"` 确认 CommandLine 含 run_serial_v2.sh）。
- ⚠️ **guardian 的"已死，隐藏窗口拉起 / WATCHDOG START"日志行 = 重拉尝试，不是成功证明 — monitor.log 心跳续写才是 watchdog 活体（2026-08-07 memomics-1135ed52 唤醒 #16 实测）**：20:19:53 guardian 记录 `guardian: watchdog_v3 已死，隐藏窗口拉起` + `WATCHDOG_V3 START`，但 lockdir PID 38878 随后死亡、monitor.log 心跳冻结（20:19:53 后再无行）→ **本次重拉实际失败（拉起即死）**。判定层级：① watchdog 活体 = monitor.log mtime 持续每 2min 更新（不是"已拉起"日志行存在）；② **monitor.log 冻结 + 主循环 bash 存活（`Get-CimInstance -Filter "ProcessId=<PID>"` 看 CommandLine 含 run_serial_v2.sh）+ Rscript worker 存活 = watchdog 监控层已挂但核心任务健康**，照常汇报"X/40 跑中，watchdog 心跳停更不影响推进"；③ 不要因为看到"已拉起"字样就断言 watchdog 活着，也不要因重拉失败就认为任务死了——核心推进永远看主循环 + worker，监控层只是心跳。

- ✅ **guardian DISABLED 态不是退出 — watchdog 死亡时自动恢复重拉（2026-08-07 唤醒 #18 实测）**：monitor.log 显示 `guardian: DISABLED (watchdog_v3 active)`（19:26）后，watchdog_v3 仍每 ~3 分钟死亡一次（19:30:47 / 19:33:11），guardian **自动从 DISABLED 态恢复并重拉**（`guardian: watchdog_v3 已死，隐藏窗口拉起` + `WATCHDOG_V3 START`）。期间 Rscript worker (hc40) 完全不受影响：42%→92% 正常推进，done=34/40 持续更新。**判定口诀：① guardian 的 DISABLED 字样只表示"当前 watchdog 健康时静默"，不是"guardian 停止工作"——watchdog 一死它立刻恢复重拉，所以 DISABLED 不等于守护失效；② watchdog_v3 以 ~3min 频率反复死亡是本架构的**正常稳态**（bash 脚本进程被 MSYS 回收），不需要任何干预，只要 monitor.log 每 2min 更新 + Rscript worker 日志 mtime 增长 + done 计数推进 = 三层自愈闭环在工作；③ 汇报把"guardian DISABLED + 自动重拉 N 次 + worker 进度推进"写成正向证据链，不要写"watchdog 反复死"引发用户恐慌。**
- 🔴 **watchdog 心跳停更 + guardian 进程不在 = 守护层双死 → 部署 wait-loop 兜底接管（2026-08-07 memomics-1135ed52 唤醒 #36 实测，模板 `templates/fallback-takeover-waitloop.sh`）**：批处理收尾期（38/40，hc73 跑中 + hc19 待补跑）发现 monitor.log 心跳冻结 10min（最后 20:54:56）+ `ps -W` 无 guardian + watchdog 锁 pid 40473 已死（`grep 40473` 只命中 PPID 列）→ 守护层（watchdog+guardian）双死，hc73 完成后 hc19 将无人补跑（hc19 已 segfault 失败过，run_serial 主循环已 ALL DONE 不会自动重试）。此时**不能 kill 正在跑的 hc73 worker**（Rscript 26484 2.26GB，17% 推进正常）。**正确动作 = 部署独立 wait-loop 兜底脚本（后台启动）**：① 与 watchdog_v3 同 LOCKDIR（mkdir 原子锁）→ watchdog 若存活恢复则 SKIP 退出，绝不双启动 hc19；② 循环等 hc73 输出目录出现（`while [ ! -d "$OUTDIR/GSM..._hc73" ]`）；③ hc73 完成后检查 hc19 输出目录（存在→退出）；④ 用 monitor.log mtime 判定 watchdog 活性（`stat -c %Y` age <180s = 活跃 → 继续等 watchdog 处理；age ≥180s = 失效 → 接管锁 LAUNCH hc19）；⑤ 绝不 kill 任何进程、绝不重跑 hc73。**判定口诀：监控层（watchdog/guardian/bash 调度）全死 ≠ 计算层（Rscript worker）死——worker 日志 mtime 还在增长 = 任务健康，缺的只是"下一个样本谁来拉"；守护层双死时不要人工 kill/重启，部署 wait-loop 兜底让它在当前 worker 自然结束后接管；兜底脚本必须带锁 + 心跳活性判定，否则与恢复的 watchdog 双启动造成 tmp 竞争。**
- 🔴🔥 **自动重启钩子硬编码旧脚本 = 每次重启都在复现 bug（2026-08-07 memomics-1135ed52 17:35-18:00 级联崩溃根因）**：monitor_serial.sh 的自动重启分支写死 `nohup bash run_serial.sh`（旧 bat 版），而当时 sanctioned 的是 `run_serial_v2.sh`（bash 直调 Rscript 版）。调度器一死 → monitor 自动重启旧版 → 旧版 + v2 并发 → ArchR tmp 竞争 → hc11/hc73/hc19/hc26/hc40 连环失败 → 又触发重启 → 恶性循环（monitor.log 可见 17:45/17:50 连续 MONITOR START）。**铁律：① 修/重写批量脚本后，必须同步更新 monitor 自动重启钩子里的脚本名 + pgrep 防重模式（`pgrep -f "bash.*run_serial_v2.sh"` 而非旧名）；② 自动重启钩子要重启"当前 sanctioned 版本"，不是"上次写死的名字"——检查钩子时逐字核对脚本名；③ 版本增殖必须退休旧版**：run_serial.sh / run_serial_v2.sh / run_serial_v3.sh 并存时锁也碎片化（.run_serial.lock/ + .run_serial_v2.pid + .run_serial_v3.pid 三个锁名互不排斥）→ 单实例锁形同虚设。新建 v2/v3 时把旧版改名 .bak 归档 + 统一锁名，避免"以为有锁实际没有"。完整事故复盘与恢复清单见 `references/auto-restart-hook-stale-script.md`。
- 🔴🔥🔥 **重启风暴 → 脚本级 unlink(tmp) 地雷 → 级联失败（2026-08-07 二次实锤，17:35 后 8 样本全失败的真正机制）**：monitor 连续 6 次 MONITOR START（重启风暴）→ 3 个 Rscript 并发（17:48:34 `procs=3`）→ 但**真正删掉别人 tmp 的凶手不是 ArchR，是样本脚本开头的 pre-clean**：`create_arrow_qc.R` 启动时 `if (dir.exists(tmp_dir)) unlink(tmp_dir, recursive=TRUE)` ——单实例是合理清理，多实例并发时 = 进程 A 无差别删除进程 B 正在写入的 tmp-arrow → `.tabixToTmp Cannot open file ... does not exist`（hc11 失败日志原句）。**判定口诀：连续样本 FAILED + 失败都是 "Cannot open file" → 先查并发（`Get-Process Rscript` 计数）再查磁盘/权限；样本脚本里任何无条件的 `unlink(tmp_dir)` 在批量场景都是并发地雷**——要么删掉，要么只允许持有当前实例锁的进程删。修复 = watchdog_v2 三重防并发：300s 冷却 + `pgrep -f "bash.*run_serial_v2.sh"` 双保险 + procs==0 归零确认后才启动。完整时间线/根因链/修复代码见 `references/restart-storm-tmp-cascade.md`。
- ⚠️ **失败样本重试日志的残留错误 ≠ 新失败 — ArchRProject `file.exists` 错误是重试前的旧记录（2026-08-07 memomics-1135ed52 唤醒 #8 实测）**：hc73 上次因页文件压力崩溃后，run_serial 在末尾自动重试它。查 `batch/logs/GSM8549648_hc73.log` 尾部看到 `错误于file.exists(object@sampleColData$ArrowFiles): 'file'参数无效` + `停止执行` —— 容易误判"重试又崩了"。**根因：这是上次失败（无 Arrow 产物）时 saveArchRProject/ArchRProject 构造阶段的残留错误行，不是本次重试的新错误**。**判定口诀：看失败样本日志尾部出现 ArchRProject/file.exists 类错误时，先看该行的时间戳 + 当前进程在跑哪个样本（`Get-CimInstance ... CommandLine`）**——若当前 Rscript 跑的是别的样本（如 hc19），说明 hc73 残留日志是旧记录，重试还没轮到它；只有当 Rscript CommandLine 正指向该样本且日志 mtime 在增长，才需要当心。残留日志 + 当前样本不同 = 正常排队等待重试，不要误报"又失败"。**
- **✅ `run_serial_auto.out` = 批处理全程时间线探针（2026-08-07 memomics-1135ed52 唤醒 #12 实测）**：run_serial_v2 主循环把每个样本的 START/END 行追加到 `batch/run_serial_auto.out`（如 `START GSM8549653_hc35 20:08:41` / `END GSM8549652_hc212191 OK exit=0 20:08:41` / `END GSM8549649_hc19 FAILED exit=139 18:56:55` / `RUN_SERIAL_V2 SKIP: 已有实例在跑 (PID 27369)`）。**一个 `cat run_serial_auto.out | tail -20` 同时给出：已完成样本清单 + 各自 OK/FAILED + 退出码 + 精确时间戳 + 当前正在跑哪个样本（最后一行只有 START 没有 END）+ 调度器锁拦截记录（证明单实例防重生效）**——比逐个查 batch/logs/*.log 快得多，是串行推进状态的第一证据源。判定：最后一行 START 无 END = 当前样本在跑；END FAILED exit=139（segfault）或 exit=1（脚本错误）需留意；SKIP 行出现 = 防重复锁在工作。与 .bat mtime 探针（铁规 4）、DONE_MARK 计数（铁规 4）互补：时间线给历史全貌，DONE_MARK 给当前完成数，.bat mtime 给推进瞬时证据。

**⛔ 进度度量 = DONE_MARK 目录计数，不是 .arrow 文件数（2026-08-07 memomics-1135ed52 唤醒实测）**：`search_files(pattern="*.arrow", path=ArchR_Arrow_QC)` 返回 **9 个匹配**，但根目录真实 Arrow 只有 3 个——saveArchRProject 嵌套 bug（见 atac-seq-memomics skill）在 `FilteredProjects/` 深层留下重复 .arrow 副本，数文件会严重虚高。**唯一可靠进度 = `ls ArchR_Arrow_QC_Filtered/ | wc -l`（含 `{s}/{s}_filtered_cells.csv` 的样本目录数）**。根目录有 .arrow ≠ 样本完成（P3 才落 DONE_MARK）；DONE_MARK 存在 = 样本完成。汇报"X/40 完成"必须来自 DONE_MARK 计数。

**🔴 unfiltered Arrow + QualityControl 子目录出现 ≠ 完成 — 那是 P1 中间产物（2026-08-07 唤醒 #26 实测）**：hc212191 的 `ArchR_Arrow_QC/GSM8549652_hc212191.arrow`（997MB, 19:58:38）+ `ArchR_Arrow_QC/QualityControl/GSM8549652_hc212191/`（19:58:55）都已出现，但 `ArchR_Arrow_QC_Filtered/` 计数仍 35/40、该样本 filtered 目录不存在——它还在 P3 Filtered Arrow 创建中（ArchRLogs 19:58:56 Computing TSS Enrichment Scores）。**判定：unfiltered Arrow 在 `ArchR_Arrow_QC/`（P1 产物），DONE_MARK 在 `ArchR_Arrow_QC_Filtered/`（P3 产物）——中间产物出现只证明 P1/P2 完成，绝不能据此报"该样本完成"；看到 unfiltered Arrow + QC 子目录 = 样本正在 P2/P3 过渡，预计 ~10min 后落 DONE_MARK（参照同批 hc40 时间线：Arrow 19:36:58 → filtered CSV 19:48）**。

**⛔ DONE_MARK 目录 glob 陷阱 — 目录名是 `GSM*_hc*/` 不是 `hc*/`（2026-08-07 memomics-1135ed52 唤醒 #10 实测）**：样本短名是 `hc11`/`hc26` 等，但输出目录带 GSM 前缀（`GSM8549647_hc11/`）。`ls -d .../ArchR_Arrow_QC_Filtered/hc*/` 返回 **0** → 差点误判"输出目录全没了"；实际 `ls -d .../ArchR_Arrow_QC_Filtered/*/ | wc -l` = 33（正常）。**判定口诀：DONE_MARK 计数一律用通配 `*/`（或 `GSM*/`），禁止用样本短名 `hc*/` 做 glob——短名只出现在目录后缀**。同理 `search_files(pattern="*", target="files", path=输出目录)` 按 mtime 排序也能看最新产出目录（最新 mtime = 最近完成样本）。

**⛔ `comm -23` 对比两清单前必须先统一名称格式 — GSM 前缀 vs 短名混比 = 全部样本假"未完成"（2026-08-07 memomics-1135ed52 唤醒 #35 实测）**：用 `comm -23` 找"未完成样本"时，done 清单来自 `ls .../Filtered/*/ | sed 's/.*\///;s/\///'`（得 `GSM8549615_hc77` 全名格式），all 清单来自 `ls fragments/*.tsv.gz | sed 's/.*GSM[0-9]*_//'`（得 `hc77` 短名格式）→ **两清单 token 完全不同，comm 逐行比较全部不匹配 → 40 个样本全显示"未完成"**（假阴性，当时差点据此误报任务异常）。**判定口诀：① 用 comm/join/diff 对比样本清单前，先统一两侧名称格式**（要么都带 GSM 前缀、要么都只留短名，sed 必须一致）；② 本数据集 GSM 编号对 40 样本是**顺序连续的**（8549615..8549654），而 hc 短名是任意顺序 → 找缺口用 GSM 编号连续性判断最可靠（输出目录里缺哪个 GSM 号 = 该样本未完成，如缺 8549648=hc73、8549649=hc19）；③ comm 出现"全部不匹配"时第一反应 = 检查两侧格式是否一致，不是信结果；④ 最省事 = 直接 `ls -d .../Filtered/GSM*/` 列目录名人工比对（本唤醒 38 个目录一列就看清缺哪两个）。

**⚠️ 裸 `*`（无尾斜杠）会把输出目录里的辅助脚本文件数进去 — 计数用 `GSM*/` 或 `*/`（2026-08-07 memomics-1135ed52 唤醒 #35 实测）**：本唤醒先 `ls -d .../ArchR_Arrow_QC_Filtered/* | wc -l` 返回 **38**，再用 `ls -d .../GSM* | wc -l` 实测 **37**——差 1 的元凶是 `check_procs.ps1`（监控脚本）被放进了输出目录，裸 `*` 同时匹配文件和目录把它数了进去。**规则：进度计数一律 `GSM*/`（前缀锚定，天然排除脚本）或 `*/`（尾斜杠限定目录）；裸 `*` 计数若比预期多 1-2，先查输出目录里是否有辅助脚本（check_procs.ps1 / cleanup.ps1 / verify 工具）混入再下"多了一个样本"结论。**
> 🔴 **变体：连 glob 都不加，裸 `ls <dir> | wc -l` 同样把文件数进去（2026-08-07 memomics-1135ed52 唤醒 #18 实测）**：`ls E:/.../ArchR_Arrow_QC_Filtered/ 2>/dev/null | wc -l` 返回 **39**（把同目录的 check_procs.ps1 文件也数了），随后 `ls -d .../ArchR_Arrow_QC_Filtered/*/ | wc -l` = **38**。判定口诀：**任何不带尾斜杠 glob 的 `ls | wc -l` 都可能混入辅助脚本文件，进度计数铁律 = 带 `*/` 或 `GSM*/` 的 `ls -d`**；实测数字比预期多 1-2 先怀疑辅助脚本被数，不是"多了样本"。

**⛔ 逐样本日志/输入路径按短名 glob 定位，禁止按顺序猜 GSM 前缀 — GSE278576 的 GSM 编号与 hc 短名非顺序对应（2026-08-07 memomics-1135ed52 唤醒 #16 实测）**：查 hc35 的 batch 日志时按"hc 短名顺序对应"猜成 `batch/logs/GSM8549651_hc35.log`（那是 **hc40** 的文件）→ tail 空 → 一度以为"hc35 日志为空/无输出"；实际正确文件是 `batch/logs/GSM8549653_hc35.log`（含完整 P1 进度：START 20:08:47 → TabixFile 8%-100% → Arrow → CellStats 8220 cells / TSS 9.504）。**GSM 与 hc 的映射：hc35=GSM8549653、hc40=GSM8549651（hc40 的 GSM 编号反而比 hc35 小）——不是顺序关系**。判定口诀：① 找某 hc 短名的日志/输入/输出一律 glob 定位（`ls batch/logs/*hc35*` / `find <dir> -name "*hc35*"`），不要手工拼 GSM 前缀；② 空 tail ≠ 日志无内容，先 `ls -la <path>` 验证路径存在（可能是文件名猜错）再下"无输出"结论；③ 从任务清单/下载清单查 hc↔GSM 映射表，不靠编号推断。

**⛔ DONE_MARK 路径以实际脚本为准，task_plan 文本可能滞后（2026-08-07 memomics-1135ed52 唤醒 #3 实证）**：task_plan 写"输出 `ArchR_Arrow_QC`"，但 run_serial.sh / monitor_serial.sh 的 DONE_MARK 与 create_arrow_qc.R 的 `out_filtered` 实际都写 `ArchR_Arrow_QC_Filtered`——文本与脚本矛盾时**以脚本源码为准**（读 R 脚本确认 out_root/out_filtered/DONE_MARK 三个变量一致），不要按 task_plan 字面去数目录，否则会把"正在正常产出"误判成"路径错误/停滞"。

**✅ 样本内（in-flight）进度探针 = 当前样本输出文件 mtime+大小增长（2026-08-07 memomics-1135ed52 唤醒 #15 实测）**：DONE_MARK 计数只证明**已完成**样本数；对**正在跑的当前样本**，活体信号 = 它的输出文件（如 `GSM8549621_hc5614.arrow`）**mtime 持续更新 + 大小持续增长**（实测 03:26 时已写 1.65GB，参照同批最终体积 ~1.7GB → 接近完成）。此时 batch 日志可能因块缓冲冻结（铁规 0 唤醒 #2）、ArchRLogs 进度行也可能暂时停更（"Creating ArrowFile From Temporary File" 阶段无逐行输出）——**输出文件本身的 mtime/大小就是唯一可靠的在写证据**。判定：当前样本输出文件 mtime 新鲜（最近 1-3 分钟内）+ 大小与同类样本最终体积可比 → 在跑，继续等；mtime 冻结 >10min + 进程查询全空 → 真死。**汇报"第 X/40 正在处理"时给出：进程（ps -ef）+ 输出文件 mtime/大小（dir 实测）+ 日志最新阶段三证据，缺一不算核实。**

**✅ Filtered Arrow 阶段逐染色体进度 = P2/P3 阶段的精确 ETA 探针（2026-08-07 memomics-1135ed52 唤醒 #20 实测）**：样本进入 P2/P3 后，createArrows 日志尾部出现 `.filterCellsFromArrow Fragments-Chr-(N of 24)-chrN`（实测：19:40:22 `Creating Filtered Arrow File` → 19:40:25 `.filterCellsFromArrow Fragments-Chr-(1 of 24)-chr1`, nRows=7880 过滤后 barcodes）——**该阶段以染色体为单位逐条推进，`(N of 24)` 直接给出完成比例**，比 batch 日志（块缓冲冻结）和输出文件 mtime（可能滞后）更精确。判定：看到 `Creating Filtered Arrow File` = Arrow 已创建成功、进入最后过滤阶段；`(N of 24)` 计数 + 过滤后 barcodes 数即可估算剩余时间（小样本 chr1 后段约 1-2min/chr，24 chr 全程 ~5-10min）。该阶段 log 无 DONE 标记前 Rscript worker 仍应存活（Get-Process 确认）。

## 🔴 铁规 4.5: 完成度对账 — done 目录 + 跑中 + 已知待跑 = 全集；少了就是有样本被静默丢弃【v2.2 新增】

**2026-08-07 memomics-1135ed52 唤醒 #39 实测（hc19 静默丢失）**：40 样本 ArchR 批处理后期，磁盘输出目录计数 37/40 + 跑中 hc9 + 已知待重试 hc73 = 39 ≠ 40 → **差 1 个样本**。逐项排查发现 hc19 实际 segfault（`END GSM8549649_hc19 FAILED exit=139`，`.tmpToArrow ERROR`，无 `{s}_filtered_cells.csv`），但**此前唤醒 #9/#10 误记为"hc19 正常完成"**——只看到日志推进到 End Time/Elapsed 就下结论，从未核对 DONE_MARK 文件是否存在。这就是"日志推进 ≠ 样本完成"的实锤：`createArrows 日志尾部出现 End Time + Elapsed` 只证明 createArrowFiles 阶段结束，**不能**证明 P3 filtered_cells.csv 已落盘。

**完成度对账公式（长批处理每个唤醒必做）**：
```
磁盘 done 目录数 + 跑中样本数 + 已知待跑/待重试数 = 样本全集数
（40 样本：37 + 1 + 2 = 40 ✓；39 ≠ 40 → 立即找缺失的那个样本）
```
- 对账数 < 全集 → **一定有样本被静默丢弃**（失败但没进重试队列），逐个样本 `ls DONE_MARK/{s}/{s}_filtered_cells.csv` 找出缺哪个
- ✅ **每样本完整性一键验证 — DONE_MARK 双产物循环（2026-08-08 终态唤醒实测，memomics-1135ed52）**：目录数对账齐 ≠ 每样本双产物都在（目录存在但 .arrow 或 filtered_cells.csv 缺失 = 不完整样本）。用循环逐样本验证两者齐全：
```bash
for d in .../ArchR_Arrow_QC_Filtered/GSM*/; do
  if ls "$d"*.arrow >/dev/null 2>&1 && ls "$d"*_filtered_cells.csv >/dev/null 2>&1; then echo -n ""; else echo "INCOMPLETE: $d"; fi
done
# 无 INCOMPLETE 输出 = 40/40 双产物齐全（比单独数目录更严；"$d" 带引号防中文路径/空格）
```
终态验收四件套（目录计数 + 此循环 + `Get-Process Rscript`==0 + cron 检查）可一次 terminal 批量完成（本唤醒实测 4 条命令一轮出齐），无需多轮拆分。**终态唤醒最小流程**：task_plan 已有多条完整终态确认记录时（如本会话已有 4+ 条 40/40 终态条目），后续终态唤醒 = 定位 session（`ls -lt results/*/task_plan.md`）→ 读 task_plan 确认终态+红线 → 一轮 fresh 验证批量 → 汇报（含 cron 检查硬字段），**不再追加冗余全量记录**（变体 5 规则：终态条目已完整 → 只验证 + 汇报）。
- ⛔ 禁止拿 previous wake 记录的"完成"当证据——**每次唤醒都重新核对磁盘**（前序唤醒可能基于"日志推进到哪"而非"DONE_MARK 存在"误判完成，唤醒 #9/#10 的 hc19 就是活例）
- ⛔ 样本完成的唯一铁证 = `{s}_filtered_cells.csv` 存在（铁规 5"不信任 exit code"的扩展：不信任"日志显示完成"，只信 DONE_MARK 落盘）

**静默丢弃的双根因（两机制叠加才丢样本）**：
1. run_serial 主循环的剩余列表是**启动时快照**，失败样本不重新入队（列表遍历一遍就 ALL DONE）→ 失败 = 永久丢失，除非 watchdog 兜底
2. watchdog 的 REMAINING 数组是**硬编码清单**，若启动时没包含某失败样本 → watchdog 也永远不会启动它 → 双重漏网
→ **修复 = 补 watchdog 数组 + 重启 watchdog（见下）**；更稳的长效方案 = watchdog 用"全集 − done 目录"动态重建数组（如 run_serial_v2 的 SKIP 逻辑），不要硬编码 REMAINING。

**⚠️ 补 watchdog 数组必须双副本同步（batch + guardian 权威）— 只改一处会被 guardian 覆盖回滚（2026-08-07 memomics-1135ed52 唤醒 #39 实测）**：watchdog_v3.sh 有两个副本——`batch/watchdog_v3.sh`（运行副本）+ `E:/release/guardian_authority/watchdog_v3.sh`（guardian 每轮 `cmp -s` 校验、发现不一致就用 AUTH 覆盖 batch）。**只改 batch 副本 = guardian 下一轮就把修复覆盖掉；必须两处同改**。改完用 `cmp -s <batch> <auth>` 验证一致（guardian 的 cmp 不触发覆盖 = 修复安全），再重启 watchdog 让新数组生效。

**替换 watchdog 实例的正确姿势（worker 在跑不用杀）**：
1. 新数组已双副本落盘 → `powershell Stop-Process -Id <旧 watchdog WINPID> -Force`（taskkill //F 在 MSYS 必失败，见铁规 10）
2. **不要杀正在跑的 Rscript worker**——它独立于 watchdog，杀掉浪费已有进度
3. 旧 watchdog 死亡时若已 LAUNCH 下一个样本（20:53:56 实测 hc73 已被旧实例拉起）→ 没关系：新 watchdog 实例（含新数组）会等待当前 worker 结束后从数组里继续（lockdir mkdir 原子锁防双实例）
4. 用 `powershell Start-Process -WindowStyle Hidden -FilePath bash.exe -ArgumentList "-c","cd <batch> && bash watchdog_v3.sh >> watchdog_v3.out 2>&1"` 拉起（Hermes terminal 禁止 nohup/& 后台包装，Start-Process 隐藏窗口是脱离生命周期标准姿势）
5. 验证：`ps -ef | grep watchdog_v3.sh` 唯一实例 + monitor.log 心跳续写；行为级验证（模拟磁盘状态断言 LAUNCH 顺序）见"部署前必须行为级验证"一节

> 完整案例（hc19 时间线/诊断/修复/验证）见 `references/hc19-silent-drop-reconciliation.md`

**✅ 40/40 终态验收四证据（2026-08-07 memomics-1135ed52 唤醒 #6 实测，P1+P2+P3 全完成）**：批处理 done 计数到齐后，终态验收 = ① **`filtered_cells.csv` 计数 == 总数**（40/40）——**不要数 .arrow**（实测输出目录 46 个 .arrow vs 40 个 CSV：多出的 6 个是 saveArchRProject 嵌套副本 + 失败重试残留的 unfiltered 副本，.arrow 计数必然虚高，CSV 才是 DONE_MARK）；② `Get-Process Rscript` 计数 == 0（无残留 worker）；③ watchdog/monitor 日志出现 `ALL DONE (N/N)`（实测 watchdog_v3 monitor.log 22:30:05 `procs=0 done=40/40` → ALL DONE）；④ cron 检查无残留。四证据齐 → task_plan 顶部写 🏁 终态确认记录 + Phase 状态表标 completed；下一步（如 P4 merge）保持红线**待用户确认**，唤醒绝不代启动。终态验收用的完整命令组合：`ls -d .../GSM*/ | wc -l`（目录数）+ `find ... -name "*_filtered_cells.csv" | wc -l`（CSV 数）+ `Get-Process Rscript`（worker 计数）+ tail monitor.log（ALL DONE 行）。**页文件风险点样本（hc73 5.42GB 最大样本）终态重试成功（21:42:56，7758→6555 cells, 15.51% doublet）**——大样本崩溃后不要人工放弃，等系统压力缓解自动重试即可成功。

**⛔ 终态 QC 汇总表禁止从 filtered_cells.csv 解析 doublet 率 — CSV 是过滤后保存，解析必得 0%（2026-08-07 终态汇总实测）**：写 40 样本 QC 汇总时用 Python 解析每个 `*_filtered_cells.csv` 的 `DoubletFilter` 列统计 doublet → 40 个样本 doublet 全 0、Dbl% 全 0.00%，表格严重误导（看起来"没去双联"）。**根因：filtered_cells.csv 是 filterDoublets 之后保存的（P3 产物），只含 Keep 细胞，`DoubletFilter` 列整列都是 `"Keep"`——从该文件解析"去掉了多少 doublet"在数学上必然为 0**。**修复：doublet 数/比例唯一权威来源 = run_serial_auto.out 的 END 行 / 各样本日志 CellStats 前后差值（如 hc73 7758→6555 = 1203 doublet / 15.51%；hc19 6495→5652 = 843 / 12.98%）；QC 汇总表只放 `CellsKept_afterQC` + `ArrowSizeGB` 两列，doublet 统计单独注明"见各样本日志/终态确认"，不写误导性的 Dbl% 列。**口诀：汇总表想放 doublet 率 → 去 run_serial_auto.out / ArchRLogs 找过滤前细胞数（CellStats）与 CSV 行数之差；不要解析 filtered CSV 的任何列算 doublet——那列只有 Keep。**

## 🔴 铁规 5: 输出验证 — 不信任 exit code

exit code 0 ≠ 有输出。一些深度学习工具（如 CellBender）训练跑完但保存失败时 exit code 0。

```python
def verify_output(file_path: str, min_size: int = 100_000) -> bool:
    if not os.path.exists(file_path):
        logger.error(f"❌ 文件不存在: {file_path}")
        return False
    actual = os.path.getsize(file_path)
    if actual < min_size:
        logger.error(f"❌ 文件太小: {actual} bytes (< {min_size})")
        return False
    logger.info(f"✅ 验证通过: {file_path} ({actual/1e6:.1f} MB)")
    return True
```

## 🔴 铁规 6: GPU 检测 — 启动前确认

```python
import subprocess, json
result = subprocess.run(
    ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
     "--format=csv,noheader,nounits"],
    capture_output=True, text=True
)
print(result.stdout)
# 检查至少一个 GPU 可用
```

## 🔴 铁规 7: 日志结构 — 持久化可读

```
F:/batch_project/
├── logs/
│   └── pipeline.log         # 带时间戳的运行日志
├── output/{sample}/         # 每个样本的输出
├── scripts/
│   └── run_pipeline.py      # 核心 watchdog 脚本
├── summary/
│   └── stats.tsv            # 全部样本汇总表
└── launcher.bat             # 脱离式启动器
```

## 🔴 铁规 8: 目录命名 — 语义化

❌ `cellbender_gzzkq8fy`（随机 session ID，无意义）  
✅ `PROJECT_DATA_DIR\output\4CL_SD_D4_1_scRNA\`

## 🔴 铁规 9: 参数确认 — 启动前输出模板

每次启动批量任务前，LLM 必须输出此确认表：

```markdown
### 参数确认
| 参数 | 值 | 来源 |
|------|-----|------|
| --fpr | 0.01 | 官方默认 |
| --learning-rate | 1e-4 | 官方默认 |
| GPU | CUDA | 显式指定 |
| sitecustomize | v4 deployed | TypeError+AttributeError |
| PYTHONPATH | cleared | env -u |
| 执行模式 | 串行 | 一次一个 |
```
---

## 🔴 铁规 10: 启动前杀残留进程 — 防撞车 + 防 Zombie Cascade

批处理启动前，检查并杀死所有同类的残留进程。CellBender 尤其容易残留：训练被中断后进程活着但不输出日志，启动新的 CellBender 后会跟残留进程同时使用 GPU 导致 OOM / checkpoint 冲突。

**⚠️ Zombie Cascade 模式 (2026-07-24 验证)**：当 pipeline 父进程被 Hermes 会话终止时，CellBender 子进程（通过 `subprocess.run()` 阻塞调用产生）变为孤儿。每次重启 pipeline 又产生新孤儿 → 累积 3+ 个僵尸 → 11+ GB RAM 被吃 → 后续样本报 `numpy._core._exceptions._ArrayMemoryError`。

**检测方法**：CellBender 进程名是 `python.exe`（不是 `cellbender.exe`），必须查命令行：

```powershell
powershell "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*cellbender*' } | Select-Object ProcessId, CommandLine"
```

```python
import subprocess, os

def kill_residual_cellbender():
    """查找并杀死所有 CellBender 孤儿进程（进程名是 python.exe，需查命令行）"""
    import csv, io
    
    # 方法 1: Powershell 查命令行（最可靠）
    ps = subprocess.run(
        ["powershell", "-Command",
         "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*cellbender*' } | Select-Object -ExpandProperty ProcessId"],
        capture_output=True, text=True
    )
    pids = [line.strip() for line in ps.stdout.split("\n") if line.strip().isdigit()]
    
    if pids:
        for pid in pids:
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
        print(f"已杀 {len(pids)} 个 CellBender 僵尸: {pids}")
    
    # 方法 2: 从 tasklist 查大内存 python 进程（兜底）
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"],
        capture_output=True, text=True
    )
    reader = csv.reader(io.StringIO(result.stdout))
    for row in reader:
        if len(row) >= 5:
            try:
                mem_kb = int(row[4].replace('"','').replace(' K','').replace(',',''))
                if mem_kb > 4_000_000:  # > 4 GB RAM → 大概率 CellBender
                    pid = row[1].replace('"','')
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                    print(f"已杀大内存进程 PID={pid} ({mem_kb/1e6:.0f} GB)")
            except: pass
```

**清理产出目录**：
```python
import shutil, glob
# 删掉无 filtered.h5 的孤儿目录
for d in glob.glob("cellbender_output/*"):
    if not glob.glob(f"{d}/*filtered*"):
        shutil.rmtree(d, ignore_errors=True)
```

**⚠️ taskkill //F 在 git-bash 必失败 — 杀进程用 PowerShell Stop-Process（2026-08-07 memomics-1135ed52 故障恢复实测）**：bash 终端里 `taskkill //F //T //PID 41164` 报 `无效参数/选项 - '//F'`（MSYS 把 `//F` 当路径/参数吞掉，四个 taskkill 全失败、进程一个没杀掉，验证时才发现 3 个 Rscript 还活着）。**唯一可靠写法**：
```bash
# ✅ PowerShell Stop-Process — 零 MSYS 转义（bash 双引号内 PowerShell 变量记得 \\$ 转义）
powershell.exe -NoProfile -Command "Stop-Process -Id 59032,63804,48200 -Force -ErrorAction SilentlyContinue"
powershell.exe -NoProfile -Command "Stop-Process -Name Rscript -Force -ErrorAction SilentlyContinue"   # 按进程名批量
# ✅ 按 CommandLine 精确杀批处理进程树（bash/cmd/Rscript 全杀，不误伤平台服务）
powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -match 'run_serial|monitor_serial|create_arrow' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force -ErrorAction SilentlyContinue }"
```
**kill 后必须 `sleep 2` + 复查进程列表**（Stop-Process 也可能因权限/竞态漏杀；`(Get-Process Rscript -ErrorAction SilentlyContinue | Measure-Object).Count` 确认归零再继续）。Python subprocess 里 `taskkill /F /PID`（列表参数，不经 MSYS）不受影响。

**使用时机**: 
- 每次 `run_pipeline.py` 启动前（不是启动后）
- 当发现日志停在某个样本但 GPU 无活动时
- 用户说"重跑"时

详见 `cellbender-batch-pipeline` skill 的 `references/zombie-cascade-recipe.md`。

---

## 🔴 铁规 11: Watchdog 循环 — 失败不崩，继续下一个

批量任务中一个样本失败不应该终止整个批次。使用 watchdog 循环模式：

```python
def run_batch(samples: list, process_fn, log_file: str) -> dict:
    """Watchdog 循环：一个失败→记录→继续下一个"""
    results = {}
    total = len(samples)
    
    for i, sample in enumerate(samples, 1):
        write_log(log_file, f"[{i}/{total}] 开始 {sample}")
        try:
            ok = process_fn(sample)
            results[sample] = {"status": "ok" if ok else "fail"}
            if not ok:
                # 验证产出失败（文件不存在/太小）
                write_log(log_file, f"[{i}/{total}] ❌ 产出验证失败 → 继续下一个")
        except Exception as e:
            # 捕获所有异常，不崩循环
            results[sample] = {"status": "error", "error": str(e)}
            write_log(log_file, f"[{i}/{total}] ❌ 异常: {str(e)[:200]} → 继续下一个")
            traceback.print_exc()
        finally:
            time.sleep(5)  # GPU 释放间隔
    
    n_ok = sum(1 for v in results.values() if v.get("status") == "ok")
    write_log(log_file, f"DONE: {n_ok}/{total} 成功")
    return results
```

**关键原则**:
- 不抛 `SystemExit` / `sys.exit()` — 用返回值传递失败
- 不依赖 Hermes `notify_on_complete` — 日志写磁盘，LLM 通过读日志监控
- 每个样本独立运行、独立清理、独立验证

---

## 🔴 铁规 12: 启动前 5 项强制检查 — 缺一不可【v1.2 新增】

每次启动批处理 pipeline 前，必须完成这 5 项检查。少一项都不准说"跑起来了"。

### 检查 1: 杀干净旧进程 — 防并行撞车

**不仅要杀 CellBender 僵尸，还要杀旧的 pipeline 脚本进程**。这是本 session 最致命的错误：旧的 `scripts/run_pipeline.py` (PID 29796) 没被杀，新脚本 `run_cellbender_serial.py` 同时启动 → 2 个 CellBender 并行 → 内存双倍 → ArrayMemoryError。

```powershell
# 杀所有含 "run_pipeline" / "run_cellbender" 的 python 进程
powershell "Get-WmiObject Win32_Process | Where-Object { ($_.CommandLine -like '*run_pipeline*') -or ($_.CommandLine -like '*run_cellbender*') -or ($_.CommandLine -like '*remove-background*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host 'Killed' $_.ProcessId }"
```

### 检查 2: 脚本文件落盘确认

```python
assert os.path.exists(script_path), f"脚本不存在: {script_path}"
assert os.path.getsize(script_path) > 100, f"脚本为空: {script_path}"
```

### 检查 3: GPU 空闲确认

```python
gpu_util = get_gpu_util()
assert gpu_util < 10, f"GPU 仍被占用: {gpu_util}%"
```

### 检查 4: 输入文件存在 + 路径正确确认

**本 session 严重错误**：Agent 用了 `PROJECT_DATA_DIR/*.h5ad` 但实际文件在 `PROJECT_DATA_DIR/h5ad/*.h5ad`（子目录）→ `Total to run: 0` → 仍报告"跑起来了！"。

```python
h5ad_files = glob.glob(os.path.join(H5AD_DIR, "**", "*.h5ad"), recursive=True)
assert len(h5ad_files) > 0, f"未找到 h5ad 文件: {H5AD_DIR}"
print(f"找到 {len(h5ad_files)} 个 h5ad 文件")
```

### 检查 5: 终端成功启动 + GPU 升温确认

`write_file` 只是落盘了 .py 文件，不等于跑起来了。必须：
1. 用 `terminal()` 实际执行脚本
2. 等 5 秒确认进程存活
3. 等 60 秒确认 GPU 升温

```python
# write_file 后
result = terminal(f"start /B python {script_path} > pipeline.log 2>&1")
# 5 秒后确认进程存活
time.sleep(5)
proc_check = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe"], ...)
assert "run_cellbender" in proc_check.stdout, "pipeline 进程未出现!"
# 60 秒后确认 GPU 活动
time.sleep(60)
gpu = get_gpu_util()
assert gpu > 10, f"GPU 无活动 ({gpu}%)，进程可能卡住或路径错误"
```

### 启动确认输出模板（缺一项不准说"跑起来了"）

```markdown
## ✅ 启动确认（查了，不是说的）

| 检查项 | 结果 |
|--------|------|
| 旧进程已杀 | PID 29796, 41688 killed ✓ |
| 脚本落盘 | PROJECT_DATA_DIR/run_cellbender_serial.py (2.4 KB) ✓ |
| GPU 空闲 | 6% ✓ |
| h5ad 文件 | 26 个 ✓ |
| 进程存活 | PID 51234, 60s 后 GPU 升温 ✓ |
```

> ⛔ **缺任何一项 → 不准说"跑起来了"。先修，再确认。**

---

## 🔴 铁规 13: 心跳监控必须实际部署 — 不能说"我会查"【v1.2 新增】

**本 session 最打脸的错误**：Agent 说"2分钟报一次"，用户问"你怎么搭的？"→ Agent 承认"根本没有"。说心跳但没写监控脚本 = 撒谎。用户不傻，一眼看穿。

### 部署心跳（启动 pipeline 后立即执行）

```bash
# 启动 pipeline 后，立即部署心跳监控
nohup bash -c '
echo "heartbeat started at $(date)" >> PROJECT_DATA_DIR/monitor.log
while true; do
  now=$(date "+%H:%M:%S")
  gpu=$(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader 2>/dev/null | head -1 || echo "N/A")
  epoch=$(tail -5 PROJECT_DATA_DIR/cellbender_output/*/cellbender_run.log 2>/dev/null | grep -oP "epoch \d+" | tail -1 || echo "none")
  done_count=$(find PROJECT_DATA_DIR/cellbender_output -name "cellbender_output_filtered.h5" 2>/dev/null | wc -l)
  echo "[$now] GPU=$gpu | epoch=$epoch | done=$done_count/26" >> PROJECT_DATA_DIR/monitor.log
  sleep 120
done
' &
```

### 验证心跳（1 分钟后检查）

```bash
ls -la PROJECT_DATA_DIR/monitor.log          # 文件必须存在
tail -3 PROJECT_DATA_DIR/monitor.log          # 时间戳必须在最近 2 分钟内
```

> ⛔ **心跳没部署 → 不准说"我会查进度"。用户问"你怎么搭的？"时必须有磁盘文件可展示。**

---

---

## 🔴 铁规 13.5: 自包含监控循环脚本 — 用户说\"后台\"时的标准交付【v1.8 新增】

用户说**\"后台\"**（或\"挂后台监控\"）时，交付物 = **一个自包含的监控循环脚本**（写盘 + 验证 + 启动），不是\"我会继续查\"的口头承诺。2026-08-07 memomics-1135ed52 实测模板：`templates/monitor-serial-loop.sh`。

### 三源检查（每轮循环内）

| 源 | 命令 | 说明 |
|----|------|------|
| ① 进程数 | `powershell.exe -NoProfile -Command "(Get-Process Rscript -ErrorAction SilentlyContinue | Measure-Object).Count"` | **本环境实测可靠**（tasklist `//FI` 与 `Where-Object -match` 曾静默返回空，见铁规 0） |
| ② 产出数 | `ls "$DONE_DIR"/*/*_filtered_cells.csv \| wc -l` | DONE_MARK 计数 = 唯一可靠进度（铁规 4） |
| ③ 日志年龄 | `stat -c %Y` 最新 log mtime vs now | 停更 > STALL_MIN 分钟 = 可能 stall |

### 判定逻辑

- **停滞 ALERT**：`done < TOTAL` 且 `procs == 0` 且 `log_age > STALL_MIN` → 写 `alerts.json`（进程查询为空但 DONE_MARK 计数增长 = 不是真死，不要误报）
- **恢复清除**：下一次循环恢复正常 → `rm alerts.json`（alerts 是瞬态信号，恢复即清）
- **完成 COMPLETE**：`done >= TOTAL` → 写 `alerts.json`（severity=info, ALL DONE）+ `break` 退出循环 → **Hermes `notify_on_complete=true` 触发自动唤醒** → 汇报完成
- **循环进度行**：每轮 `echo "[$TS] done=X/TOTAL procs=N log=NAME age=Ym" >> monitor.log`（Agent 或唤醒轮次直接 `cat monitor.log` 即可汇报，不必每次重查三源）
- **📍 monitor.log 物理位置 = `results/{session_dir}/batch/monitor.log`，不在输出目录（2026-08-07 memomics-1135ed52 唤醒 #4 实测）**：唤醒时先到输出目录（`E:/专利/.../ArchR_Arrow_QC_Filtered/`）找 monitor.log 扑空，再 find 才定位到 `results/<session>/batch/`。**找日志一律先查 session 目录下 batch/（与 run_serial*.sh、watchdog*.sh、remaining.txt 同层），不要在输出目录浪费时间**。同理 `remaining_v2.txt`、`run_serial_auto.out` 也在同一 batch/ 目录。
- ⚠️ **`remaining_v2.txt` 是静态初始清单，不随进度收缩（2026-08-07 memomics-1135ed52 唤醒 #37 实测）**：hc11 已于 18:22 完成、hc73 已失败过一次，但 remaining_v2.txt 仍完整列出全部 8 个待跑样本（含已完成的 hc11）——它只是 run_serial_v2 启动时的输入列表快照，**永远不更新**。**判定口诀：① 看批处理进度一律以 run_serial_auto.out（START/END 时间线）+ DONE_MARK 目录计数（铁规 4）为准，`cat remaining_v2.txt` 列出 8 个 ≠ 还有 8 个要跑；② 已完成样本由 run_serial_v2 的 SKIP 逻辑（filtered_cells.csv 存在即跳过）去重，不以 remaining_v2.txt 内容判断；③ 若拿 remaining_v2.txt 报"还剩 X 个"会被用户当场揭穿（37/40 完成但清单显示 8 个）——进度数字必须磁盘实测（run_serial_auto.out + GSM*/ 目录计数）。**
- **🔴 watchdog/guardian 脚本权威目录 = `E:/release/guardian_authority/`，且脚本本身是路径权威源（2026-08-07 memomics-1135ed52 唤醒 #36 实测）**：本唤醒先在 `E:/专利/Human_Hippocampus_ATAC/batch/`、`find /e/专利 -maxdepth 3 -name "*.sh"`、`find /e/ -maxdepth 4 -name "watchdog_v3.sh"` 反复找脚本/日志，扑空多轮才定位到 watchdog_v3.sh 在 `E:/release/guardian_authority/`（guardian 的权威副本目录，guardian 每轮校验恢复）。**⚠️ `find` 在 `专利/` 中文路径下也可能返回 0**（与 search_files 同病，铁规 16.5）。**判定口诀：① 找批处理脚本/日志前先直接 `ls E:/release/guardian_authority/`（watchdog*/guardian*.sh 的固定家），不要从输出目录反向搜；② `read_file watchdog_v3.sh` 顶部 CONFIG 段一次给出全部权威路径（OUTDIR / LOGDIR=results/{session}/batch/logs / MLOG=results/{session}/batch/monitor.log / CREATE_SCRIPT / WORKDIR）——**脚本即路径权威源**，读它比 find 全盘快得多；③ 汇报时把\"从 watchdog_v3.sh 读到的路径\"作为证据链一部分，避免后续唤醒重复摸索。

### 部署方式

```bash
# 语法检查
bash -n batch/monitor_serial.sh && echo "SYNTAX OK"
# 后台启动（监控脚本本身轻量，可挂 Hermes 生命周期；计算 worker 仍按铁规 2 脱离式）
terminal(background=true, command="bash batch/monitor_serial.sh", notify_on_complete=true)
# 验证第一轮写入
sleep 5 && cat batch/monitor.log   # 必须出现 "[TS] done=... procs=... log=..." 行
```

### ⛔ 部署前必须行为级验证（不是只 bash -n）

系统/用户要求\"验证\"时，写临时验证脚本测试**判定逻辑分支**，不是只看语法。2026-08-07 实测方法：

1. **逻辑判定验证**（5 项）：① PowerShell 进程计数有效性 ② 产出计数 glob ③ 停滞判定（强制 `SIM_PROCS=0` + touch 20min 前日志 → 必须触发 ALERT）④ 完成判定（模拟 40 个 CSV → 必须 COMPLETE）⑤ 正常态不误报
2. **循环行为验证**（3 项）：复制核心逻辑、`sleep` 缩到 2s、用**真实 DONE_DIR/LOG_DIR** 数据源跑 3 轮 → 断言 monitor.log 写入 3 行 + 无 ALERT + 检测值有效
3. **⚠️ 测试脚本自身缺陷陷阱**：**不要用真实系统状态测试需要不同状态的分支**。首次验证③用真实 procs=2（hc5579 在跑）测停滞分支 → 必然不触发 → 误报 FAIL。修正：分支测试必须**显式模拟目标状态**（`SIM_PROCS=0`）。反向也证明：真实 procs=2 时监控不误发 ALERT = 正确行为，不是 bug。
4. 临时验证脚本写真实 Windows 路径（铁规 16.5），跑完 `rm -f hermes-verify-*` + `ls 无残留` 清理。

> 模板见 `templates/monitor-serial-loop.sh`（每项目改 4 个变量：DONE_DIR/LOG_DIR/MON_LOG/TOTAL/PROC_NAME 等，其余通用）。

---

## 🔴 铁规 14: 每样本产出即时三态验证 — 不能等全部跑完【v1.2 新增】

**本 session 的教训**：11 个样本跑完只有 log 无 filtered.h5，Agent 没发现。因为 subprocess 返回码不可靠。

### 三态分类（不是 OK/FAIL 二分类）

```python
def verify_one_sample(output_dir: str, sample_name: str) -> str:
    """返回 'ok' | 'posterior_only' | 'failed' """
    filtered = os.path.join(output_dir, "cellbender_output_filtered.h5")
    full_output = os.path.join(output_dir, "cellbender_output.h5")
    
    # 延迟重试：文件系统可能延迟写入
    for attempt in range(5):
        if os.path.exists(filtered) and os.path.getsize(filtered) > 20_000_000:
            sz_mb = os.path.getsize(filtered) / (1024 * 1024)
            print(f"  [{idx}/{total}] {sample} ✅ {sz_mb:.1f} MB filtered.h5")
            return "ok"
        time.sleep(1)
    
    # 兜底：filtered 不存在但 posterior 存在 → ptrepack 可以直接处理
    if os.path.exists(full_output) and os.path.getsize(full_output) > 50_000_000:
        print(f"  [{idx}/{total}] {sample} ⚠️ posterior 存在 but filtered 缺失 → ptrepack 可补救")
        return "posterior_only"
    
    print(f"  [{idx}/{total}] {sample} ❌ 完全无产出")
    return "failed"
```

| 状态 | 触发条件 | 行动 |
|------|---------|------|
| `ok` | filtered.h5 > 20 MB | 跳过，不重跑 |
| `posterior_only` | cellbender_output.h5 > 50 MB，filtered 缺失 | **ptrepack 直接处理，不用重跑 CellBender！** |
| `failed` | 两文件都不存在 | 需重跑 CellBender |

> **本 session 有 7 个 `posterior_only` 样本被当成 `failed`，浪费了 ptrepack 直接处理的机会。** 每个样本跑完后立即三态验证，不要等到全部跑完才汇总。

---

## 🔴 铁规 15: Guardian 快照 — 修改脚本前先备份【v1.1】


## 🔧 R 多版本库路径隔离【v1.3】

当同时使用多个 R 版本（如 R 4.4.2 跑 Seurat/Signac + R 4.5.3 跑 ArchR），必须确保每个版本使用独立库路径。若 `.Rprofile` 硬编码旧版路径，新版 R 的 `.libPaths()` 会被劫持 → `library()` 全部失败。

**修复**：`.Rprofile` 用 `R.version$major.minor` 动态构建库路径。详见 `references/r-multi-version-library-isolation.md`。

**跨环境调用**：
```bash
"C:/Program Files/R/R-4.5.3/bin/Rscript.exe" archr_atac.R    # R 4.5.3
"C:/Users/.../R/R-4.4.2/bin/x64/Rscript.exe" seurat.R        # R 4.4.2
```

## ⛔ 中文路径在 batch 脚本中的编码陷阱（2026-08-07 实测）【v2.0 新增】

**症状**：write_file 写到 `E:\专利\...\batch\run_xxx.bat` 的 UTF-8 bat 文件，bash→cmd.exe 执行时 `cmd.exe /c "E:\专利\...\run_xxx.bat"` → `系统找不到指定的路径` (EXIT_CODE=3)。

**根因**：write_file 写 UTF-8 编码，cmd.exe 按系统代码页（GBK）解析中文路径 → 编码不匹配 → 路径乱码 → 找不到文件。

**✅ 唯一正确做法**：bat 文件只传 ASCII 参数，中文路径全部在 R/Python 脚本内部拼接。

```bash
# ❌ 不对 — bat 文件含中文路径
cmd.exe /c "E:\专利\Human_Hippocampus_ATAC\batch\run_hc8.bat"
# → 系统找不到指定的路径（GBK 乱码）

# ✅ 正确 — bat 只传 ASCII 参数，中文路径在 R 脚本内部处理
# run_xxx.bat 内容：
"C:\Program Files\R\R-4.5.3\bin\x64\Rscript.exe" --vanilla "batch/create_arrow_qc.R" "hc8"
# R 脚本内部: setwd("E:/专利/Human_Hippocampus_ATAC") — R 内部 UTF-8 处理中文路径可行
```

> 同一原理：bash 里直接用 `ls "E:/专利/..."` 也可能失败（MSYS 路径转换）。
> **⚠️ search_files(target="files") 在中文路径下可能返回 0 匹配 — 交叉验证用 terminal find（2026-08-07 唤醒 #26 实测）**：`search_files(pattern="hc212191*", target="files", path="E:/专利/Human_Hippocampus_ATAC")` 返回 total_count=0，但同目录 `find . -name "*hc212191*"` 立即命中 4 个文件（fragments + arrow + QC 子目录）——中文路径（专利/）下 glob 命中不可靠。**规则：中文路径下 search_files(target="files") 返回 0 时，先用 `find <path> -name "*<pattern>*"` 交叉验证再下"文件不存在"结论；`read_file`/search_files(content 模式) 不受此影响（英文路径 results/ 下 task_plan 检索正常）。**

---

## ⛔ 页文件(pagefile)提交压力诊断 — 物理内存空闲 ≠ 内存够用【v2.1 新增】

**2026-08-07 memomics-1135ed52 实测（hc73 5.42GB 最大样本崩溃）**：ArchR 批处理中最大样本 hc73（5.42GB fragments）读取到 42% 时崩溃，日志双错误：

```
[E::hts_idx_load3] Could not load local index file '...tsv.gz.tbi' : Not enough space
<simpleError in forderv(...): 内部错误 range_str: failed to grow the 'marks' hash table>
```

**但物理内存空闲 26GB / 59.7GB**——不是 RAM 不够。真正根因是 **Windows 页文件提交（pagefile commit）压力**：`C:\pagefile.sys` 分配 25.6GB、当前 72%、**峰值 185%（曾超配）**。data.table 排序时 hash table 增长需要虚拟内存提交空间，页文件提交不足 → `Not enough space` + hash table 增长失败。

**判定流程（大样本崩溃 + "Not enough space"/"hash table" 类错误时）**：

```bash
# 1. 物理内存（可能充足，不能据此排除）
powershell -NoProfile -Command "Get-CimInstance Win32_OperatingSystem | Select TotalVisibleMemorySize,FreePhysicalMemory | Format-List"
# 2. 页文件配置与压力（关键！）
powershell -NoProfile -Command "Get-CimInstance Win32_PageFileUsage | Select Name,AllocatedBaseSize,CurrentUsage,PeakUsage | Format-Table"
powershell -NoProfile -Command "Get-CimInstance Win32_ComputerSystem | Select AutomaticManagedPagefile | Format-List"
# 3. 区分最大样本：文件大小排序，最大样本最先崩（hc73 5.42GB vs 其余 1.6-2.4GB）
```

**经验规律**：
- 同一批次中小样本全过、**最大样本在排序阶段崩**（`forderv`/hash table/`Not enough space`）→ 先查页文件，不是脚本 bug
- 页文件峰值 PeakUsage > 100% = 曾超配 = 高压力 → 大样本重试大概率再崩
- 缓解选项（需用户确认后执行）：扩 pagefile（`wmic computersystem set AutomaticManagedPagefile` 或手动调大）、把大样本拆到系统空闲时单独跑、减少同机其他大内存进程
- 批量脚本里 `data.table` 排序是页文件消耗大户；`hts_idx_load3 Not enough space` 是 tabix 加载索引时分配失败的同源信号

> 完整诊断过程/崩溃日志/处置清单见 `references/pagefile-pressure-large-sample-crash.md`

---

## ⚠️ write_file 写的 .ps1 必须加 UTF-8 BOM — 否则 PowerShell 5.1 中文路径乱码【v2.1 新增】

**2026-08-07 memomics-1135ed52 实测**：write_file 写 `check_status.ps1`（UTF-8 无 BOM）→ `powershell -File check_status.ps1` 报 **exit 127** + 乱码（`/T�R C L R 1Y%` 类二进制噪音）。根因：**PowerShell 5.1 按系统 ANSI 代码页（GBK）解析无 BOM 的 .ps1 文件**，脚本里的中文路径 `E:/专利/...` UTF-8 字节被 GBK 解析成乱码 → 语法/路径错误。

**✅ 修复：write_file 后给 .ps1 补 UTF-8 BOM（utf-8-sig）**：

```python
with open(ps1_path, 'r', encoding='utf-8') as f:
    content = f.read()
with open(ps1_path, 'w', encoding='utf-8-sig') as f:  # BOM 前缀
    f.write(content)
```

**判定**：`head -c 3 file.ps1 | xxd` 前 3 字节应为 `ef bb bf`。写 .ps1 时**任何含中文路径/中文字符串的脚本都必须 BOM**；纯 ASCII 脚本不受影响。验证：`powershell -File` 后 exit=0 且输出正常。

**⚠️⚠️ 2026-08-07 二次实测 — 中文不止在路径里会炸，脚本内部任何中文字符（含 hashtable 键名）都会在 GBK 下乱码 → 首选纯 ASCII 脚本**：写验证 harness 时用了中文键名（`'RSCRIPT 段标记' = $text -match ...`）→ PowerShell 报 `== : 无法将"=="识别为 cmdlet` + ParserError（UTF-8 中文被 GBK 误读，引号/等号错位 → 语法崩）。**根因不是路径，是脚本体内的中文字符串/键名**。**处理分级：① 首选 = .ps1 脚本（尤其验证/诊断 harness）一律纯 ASCII**——英文键名/标记/注释，零编码风险、连 BOM 都不需要；② 只有非用中文不可（如脚本要输出中文汇报文本）才补 UTF-8 BOM；③ 验证 harness 若因中文键名解析失败，重写为 ASCII 版即可（实测：同一 harness 中文键名 ParserError → ASCII 键名 5/5 PASS + exit 0）。**口诀：脚本内容是英文、路径是中文 → 纯 ASCII 够用；脚本内容也要中文 → BOM。**

**⚠️⚠️⚠️ 2026-08-07 三次实测（唤醒 #36）— 修正上一口诀：中文**路径**写在 .ps1 体内同样必炸，纯 ASCII 不够**：write_file `check_status.ps1`（UTF-8 无 BOM，脚本内容全 ASCII，但体内含 `Get-ChildItem 'E:\专利\...\ArchR_Arrow_QC_Filtered'`）→ `powershell -File` 报 **PathNotFound**（`专利` UTF-8 字节被 GBK 解析成乱码 → 路径不存在），磁盘计数拿不到。**上一口诀"脚本内容是英文、路径是中文 → 纯 ASCII 够用"是错的——PowerShell 5.1 按 GBK 读整个 .ps1 文件，路径字符串里的中文一样乱码。正确分工：① .ps1 内**任何中文**（路径或字符串）都要 BOM，否则走 PowerShell 只查 ASCII 对象（进程名/内存/PID）；② 中文路径的磁盘/文件计数（`ls -d /e/专利/.../GSM*/`）**交给 bash 做**，不要混进 .ps1；③ 本唤醒实测的可靠组合 = PowerShell .ps1 查进程（Id/StartTime/CPU，纯 ASCII）+ `ls -d` 查中文路径输出目录（bash 中文路径实测可靠）——两路各管各的，不要在 PowerShell 里碰中文路径。**

---

## ⚠️ bash fork 失败 = 内存/页文件压力信号 — 换轻量探测【v2.1 新增】

**2026-08-07 memomics-1135ed52 实测**：内存压力期 bash 报 `dofork: child -1 - CreateProcessW failed ... errno 11` / `fork: retry: Resource temporarily unavailable`，terminal 命令 exit 3221225773 (0xC000012D)。**这不是命令写错，是系统 fork 资源枯竭**（页文件压力连带）。

**应对**：
1. 不要反复重试同一命令（会触发"连续失败上限"门禁，白烧轮次）
2. 换**最轻量**探测：单个 `tail -N` / `ls` / `ps -ef | grep`（不 spawn 额外进程树）
3. PowerShell 用 `-File` 走磁盘脚本（`-Command` 内联反而更重）
4. 深诊断用 `execute_python`（其 subprocess 不经 bash fork）而非 bash 多级管道
5. 该信号同时是页文件压力的佐证（见上节）——大样本任务可能正在崩

---

## ⚠️ read_file 读活跃追加日志可能返回陈旧尾部 — 用 terminal tail 交叉验证【v2.1 新增】

**2026-08-07 memomics-1135ed52 实测**：read_file 读 `monitor.log` 显示"停在 18:35:11"（9 分钟无更新）→ 差点判 watchdog 死亡；同轮 `tail -5 monitor.log`（terminal）却显示 18:45:25 仍在每 2 分钟写入。**read_file 对持续追加的日志文件可能读到分页/缓冲的陈旧快照**。

**规则**：判定"日志/心跳停止更新"前，必须用 `tail -N <log>`（terminal，绕过 read_file 分页）交叉验证；read_file 与 tail 矛盾时以 tail 为准。同一原则适用于 mtime 判定：`ls -la log` 看 mtime 是否新鲜，而不是只依赖 read_file 内容。

---

## ⛔ sibling subagent 可能写重复编号+陈旧信息的唤醒记录 — 需去重清理【v2.1 新增】

**2026-08-07 memomics-1135ed52 唤醒 #7 实测**：多 Agent 并发监控同一任务时，sibling subagent 写了"唤醒 #7（18:45）"记录**基于过时信息**（认为 hc73 还在跑 42%），本 Agent 随后写"唤醒 #7（18:47）"准确版（hc73 已失败 + hc19 已续跑）→ task_plan 出现**两个同号 #7**，且先写的那个信息已错。

**规则**：
1. 收到"file modified by sibling subagent"警告后，patch 前先 re-read，**检查是否有同编号唤醒记录已存在**
2. 同编号重复 → 保留信息准确的版本，删除陈旧版（用 patch 精确删陈旧段，不要 write_file 全量覆盖）
3. 合并后再验证：`grep -c "唤醒 #7"` == 1 + 陈旧版本的关键断言（如"hc73 跑中"）不再出现
4. 与既有规则"两份唤醒记录可以共存"的区别：**不同编号的共存**（都是审计链一部分）；**同编号重复 = 冲突**，须去重

**⚠️⚠️ 变体：自己的 patch 已先落盘再收到 sibling 警告 — 可能制造空头/半截同号记录（2026-08-07 memomics-1135ed52 唤醒 #12 实测）**：本唤醒先 patch task_plan（更新 P1+P2+P3 状态行 + 追加空头 `## ✅ 唤醒 #12` 标题，正文还没写），patch 返回 success 但带警告 "file was modified by sibling subagent '4d836305-...' at 19:15:34 — after this agent's last read at 19:14:42"。re-read 后发现 sibling 已写入**完整准确的唤醒 #12 记录**（含 CellStats 10,281 cells / Frags=11,457 / TSS=8.716）。**危险点：自己的 patch 已把空头 `## 唤醒 #12` 插进文件，可能和 sibling 的同号标题形成重复**。正确收尾：① patch 带 sibling 警告 ≠ patch 没生效——`success: true` 时自己的编辑已落盘，必须 re-read 核对是否制造了重复；② re-read 确认 sibling 记录完整准确后，**用 patch 精确删除自己留下的空头/半截同号段**（`grep -c "唤醒 #12"` 应 == 1）；③ 若 re-read 发现文件结构已正常（空头与 sibling 标题被合并/替换），也要 `grep` 验证计数 == 1 再下"结构正常"结论，不要凭目测就宣称无需改动。**口诀：patch 收到 sibling 警告 → 自己的改动已生效 → re-read + grep 计数 → 有重复就删自己的半截段，保留 sibling 完整版。**

**⚠️⚠️⚠️ 变体 2（最常见结局，2026-08-07 memomics-1135ed52 唤醒 #13 实测）：patch 失败 `Found N matches` + sibling 警告 = sibling 已写掉同号完整记录 → 正确动作 = re-read 确认后跳过写入**：本唤醒准备 patch task_plan 追加唤醒 #13 记录，patch 返回 **`Found 10 matches for old_string`** + 警告 \"file was modified by sibling subagent 'c104f49c-...' at 19:22:42 — after this agent's last read\"。re-read 后发现 sibling 已写入**完整准确的唤醒 #13 记录**（含 hc40 19:21:35 启动 / 34/40 / watchdog 自动续跑全部关键数字）——old_string 之所以不再唯一，正是因为 sibling 已把同一 anchor 行替换成了同号完整段。**正确收尾：① `Found N matches` 失败 ≠ 脚本/工具错误——并发唤醒场景这是**高频信号**，先假设\"目标内容已被 sibling 写掉\"，而不是\"old_string 写重复了\"；② re-read 后判定标准 = 同号标题存在 + 内容覆盖本次三源验证的关键数字（当前样本名 + 完成计数 + 时间戳）→ sibling 版已完整，**本轮什么都不写**（不追加、不替换、不删自己的——因为自己什么都没落盘）；③ 与变体 #12 的区别：本变体自己的 patch 根本没生效（失败而非 success+警告），所以无空头段可删、无重复可去重；与 #7 的区别：sibling 记录是准确版而非陈旧版，无需清理；④ 汇报中写明\"task_plan 已由 sibling 更新至唤醒 #N，与本轮三源验证一致，未重复写入\"——这是审计链完整且协作正确的证据，不是偷懒。**口诀：并发唤醒 patch 失败（Found N matches）→ 第一反应是\"sibling 已写掉\" → re-read 验证同号记录完整 → 直接跳过写入，最干净的结局就是什么都不写。

**⚠️⚠️⚠️⚠️ 变体 3（2026-08-07 memomics-1135ed52 唤醒 #16 实测）：自己的 patch 成功落盘 + sibling 同号记录也完整准确 → 重编号自己的为下一个号，保留两份**：本唤醒 19:30 patch task_plan 追加"唤醒 #15 (19:30)"记录**成功**（success: true），但带警告 "file was modified by sibling subagent 'eff139a3-...' at 19:28:39"。re-read 后发现 sibling 已在 19:28 写了**同号 #15 且内容完整准确**（hc40 CPU 403s / TabixFile 25% / done=34/40）——文件里出现**两个同号 #15**，且**双方都是完整准确的唤醒记录**（不是变体 #12 的空头半截，也不是变体 #7 的陈旧错误版）。**正确收尾：① 两个同号记录都完整准确时，既不删 sibling 也不删自己（删任何一方都丢审计链）——把自己的标题重编号为下一个可用号（`## ✅ 唤醒 #15` → `## ✅ 唤醒 #16`，用 patch 只改标题行，正文保留）；② 重编号后用 `grep -c "唤醒 #15"` == 1 且 `grep -c "唤醒 #16"` == 1 验证无同号重复；③ 汇报中说明"sibling 已写 #15，我的重编号为 #16"——这是协作正确且审计链完整的证据。**口诀：patch 成功 + sibling 警告 → re-read 判三方：sibling 版陈旧错误 → 删陈旧版（变体 #7）；自己的是空头半截 → 删自己的半截（变体 #12）；双方都完整准确 → 重编号自己的为 #N+1（变体 3，本次）。****
- ⚠️⚠️⚠️⚠️⚠️ **变体 4（2026-08-07 memomics-1135ed52 唤醒 #18/LoopX 实测）：patch 成功 + 头部锚点吞掉 sibling 的不同编号记录头 — 最隐蔽的并发破坏形态**。本唤醒 patch task_plan 顶部（old_string 锚定"标题 + **创建/更新** 时间戳行 + `## 唤醒 #N 检查` 标题头"这一整块共享头部），patch 返回 success 但带警告 "modified by sibling subagent 'a20040d1-...' at 21:12:38"。re-read 后发现：**sibling 已在 21:12:38 写入完整的 `唤醒 #37` 记录（正确编号），而我的 patch 用 fuzzy 匹配把 sibling 的 #37 标题头连同头部块一起替换成了我的 `唤醒 #18` 标题**（我自己还用了错误的 LoopX 编号 #18 而非 #38）→ sibling 的 #37 正文变成无头残段，审计链断号（#36 → 残段 → #18 → ...）。**根因：标题 + 创建/更新时间戳 + 唤醒 #N 标题头是每个 writer 都改的共享区，fuzzy 匹配 9 策略下 old_string 会命中 sibling 刚插入的结构相似内容**——变体 #12/#13 都是"自己的 patch 没生效/制造同号重复"，本次是**自己 patch 成功但替换掉了 sibling 的异号记录头**。**判定铁律：① patch 锚点禁止选共享头部块（标题/创建时间戳/更新行/`## 唤醒 #N` 标题头），要锚自己的正文首行（如"三源验证（PowerShell..."）或带唯一样本名的行——共享头任何 writer 都可能改，锚它 = 等着吞别人；② 收到 sibling 警告 + patch 成功 → 必 re-read 检查"文件里是否还有 sibling 的完整记录"（`grep -c "唤醒 #37"` == 1 + 该记录正文完整）——若发现 sibling 头被我吞掉，用 patch 恢复 sibling 标题头（把残段头部补回 `## ✅ 唤醒 #37 检查（...）`），再把自己的记录重编号为 #N+1 放后面；③ 若正文都还没写（我的 old_string 只锚了头部就替换），恢复成本低——补回 sibling 头即可，但**下次绝不再锚共享头**；④ 上报时如实写"patch 吞掉 sibling #37 头已恢复"，这是审计链诚实的一部分。**口诀：**共享头部块 = 雷区，anchor 只准选自己正文的唯一行；patch 成功 + sibling 警告 → re-read 查对方记录是否完整，被吞就补回头，别假装没发生。**

- ⚠️⚠️⚠️⚠️⚠️⚠️ **变体 5（2026-08-07 memomics-1135ed52 终态唤醒实测）：终态确认条目 = 最高并发写热点 — 两个 sibling + 自己同分钟竞写，锚共享头必炸出整块重复文件头**。任务全部完成时**多个唤醒 loop 会在同一分钟竞写"40/40 完成"终态条目**（实测 23:45:19 sibling A 写 + 23:45:55 sibling B 又写 + 自己 23:46 再写 = 三方并发）。本唤醒错误链条：① patch 的 old_string 又锚了**共享头部块**（`# Task Plan:` 标题 + `**Session**` + `**创建/更新**` 时间戳行 + `## 唤醒 #N 标题头`——正是变体 4 明令禁止的雷区，fuzzy 匹配 9 策略命中 sibling A 刚插入的相似结构）；② patch 返回 success + sibling 警告 → re-read 发现**文件中部被插入一整块缩进的重复文件头**（幽灵块：`  # Task Plan: ...` / `  **Session**` / `  ## 唤醒 #19` 全部缩进 2 空格），且 `**创建/更新**` 行被并发 writer 写坏成 `2026-08-08 00:xx`（模板占位符未替换就落盘）；③ 第一轮清理 patch 又因 sibling B 23:45:55 的再修改而错配（fuzzy 命中不同区域）→ **需要第二轮 patch 才彻底干净**。**判定铁律：① 终态/完成确认条目是并发唤醒最高冲突点——看到 done=40/40 时先假设"sibling 可能也在写"，写前 `grep -o "唤醒 #[0-9]*" | sort -t'#' -k2 -n | tail -1` 取真实最大号，且优先选择"只验证 + 若已有完整终态条目则不重复写"；② 锚点永不选共享头（标题/Session/创建更新时间戳/`## 唤醒 #N` 头）——只锚自己正文的唯一行；③ 清理重复块用 patch 锚**被插入的幽灵块本身**（缩进特征 + 重复内容），不要用旧头部做锚（旧头已被并发改掉）；④ patch 后 `grep -c "# Task Plan"` == 1 且 `grep -c "唤醒 #19"` == 1，凭计数验证结构而非目测；⑤ 时间戳被并发写坏成占位符（`00:xx`）时顺手修正为真实时间；⑥ 终态条目一份足够——sibling 已写完整版时**跳过写入**（变体 2 逻辑），自己已写就**不再追加第三份**，多份 = 审计链噪音。**口诀：终态 = 并发雷区，先 grep 最大号再决定写不写；锚点禁选共享头；幽灵重复块用块本身做锚清理；`grep -c 标题 == 1` 计数收尾；sibling 已写完整终态 → 什么都不写最干净。**

---

## 🔴 铁规 16: R on Windows — 必须用 cmd.exe /c，禁止 bash【v1.3】

**2026-07-29 血训**：R 4.5.x（及更高版本）在 bash (git-bash/MSYS) 下**必定 segfault**。
Rcpp/RcppArmadillo 的内存布局与 MSYS 的 POSIX 信号模拟冲突。各种症状：
- 直接 `Rscript script.R` → segmentation fault
- `terminal("Rscript script.R")` → segfault
- `library()` 后的内存分配 → segfault

### ✅ 唯一正确做法

```bash
# ❌ 不对 — bash 下 R 必死
Rscript my_script.R

# ✅ 正确 — Windows cmd 包装
cmd.exe /c "set PATH=D:\rtools45\x86_64-w64-mingw32.static.posix\bin;D:\rtools45\mingw64\bin;%PATH% && C:\PROGRA~1\R\R-4.5.3\bin\Rscript.exe --vanilla my_script.R"
```

### ⛔ 所有 R 命令必须走 cmd.exe /c

| 场景 | 正确写法 |
|------|---------|
| 运行脚本 | `cmd.exe /c "Rscript --vanilla script.R"` |
| 安装包 | `cmd.exe /c "Rscript -e 'install.packages(...)'"` |
| 检查库 | `cmd.exe /c "Rscript -e '.libPaths()'"` |
| background 后台 | `cmd.exe /c "Rscript script.R"` + `terminal(background=TRUE)` |

### 什么不能用 bash 调 R

- `terminal("Rscript ...")` — 默认走 bash
- `R CMD INSTALL` — 同上
- 任何在 `bash -c` 内嵌的 R 调用

### 为什么以前 R 4.4.2 在 bash 下没崩

R 4.4.2 没有 RcppArmadillo 15.x+ 的某些内存对齐要求，恰好在 MSYS 下幸存。
R 4.5+ 引入了更严格的 C++17 内存模型 → 与 MSYS 的 POSIX 模拟冲突 → segfault。
这不是 bug，是两个世界的边界条件——R 在 Windows 上用 ucrt64 工具链，bash 用 MSYS，两者不可混用。

---

## 🔴 铁规 16.5: MSYS 临时路径 ≠ Windows 原生路径 — 临时脚本必须写真实 Windows 路径【v1.6】

**2026-08-02 实测（MeSH 语义索引验证脚本）**：`$(cygpath -u "$TEMP")` 解析为 MSYS 虚拟路径 `/tmp`。bash 里 `cat > /tmp/script.py` 写盘成功、`ls /tmp/script.py` 看得到，但 Windows 原生 Python 打开时报：

```
python: can't open file 'E:\\tmp\\hermes-verify-193.py': [Errno 2] No such file or directory
```

原生 Python 把 `/tmp/xxx.py` 按 Windows 路径规则解析成 `E:\tmp\xxx.py`（MSYS 的 /tmp 映射），而文件实际写在 MSYS 虚拟 /tmp（可能映射到别的真实目录）→ **路径不一致，打不开**。

### ✅ 唯一正确做法

临时脚本（要被原生 Python/Rscript 执行的）一律写**真实 Windows 路径**：

```bash
# ❌ 不对 — MSYS 虚拟路径，原生解释器打不开
cat > "$(cygpath -u "$TEMP")/verify.py" << 'EOF' ...
python "$(cygpath -u "$TEMP")/verify.py"   # → E:\tmp\verify.py 不存在

# ✅ 正确 — 真实 Windows 路径
write_file(path="C:/Users/<user>/AppData/Local/Temp/verify.py", content=...)
python "C:/Users/<user>/AppData/Local/Temp/verify.py"
```

或直接用 `write_file` 工具写盘（它处理真实路径），避免 heredoc + cygpath 组合。

### 判定规则

| 写入位置 | bash 能看到? | 原生 Python/Rscript 能开? |
|---------|:---:|:---:|
| MSYS `/tmp`（`$(cygpath -u "$TEMP")`） | ✅ | ❌ 解析成 E:\tmp 打不开 |
| 真实 Windows 路径 `C:/Users/<user>/AppData/Local/Temp` | ✅ | ✅ |
| 项目结果目录 `results/.../` | ✅ | ✅ |

> 同一原理已记入 `pubmed-mesh-annotation` skill 的 Pitfalls 表（MeSH 验证脚本场景）。

---

## 🔴 铁规 17.5: hdWGCNA 结果验证 — 首次失败≠不可行，审稿人五问必答【v1.7 新增】

WGCNA/hdWGCNA 分析完成**不是终点**——本环境已踩过"task_plan 记录负面结论但官方 workflow 重跑成功"的坑（power=10 R²=0.982, 11 模块 vs 首次 R² max 0.72 全落单一模块）。

引用任何 task_plan/日志里的"XX 方法不可行"负面结论前：
1. **查产出目录是否有更新的 verify 文件**（mtime 晚于 task_plan = 未回写证据）
2. **确认失败参数**——多数"不可行"是参数子集问题（如 top3000 HVG 而非全基因集），不是方法问题
3. **审稿人五问**（metacell 伪重复→个体级 n 复核 / 纤维类型混杂→组成校正 / 0-GO 模块→独立基因集验证 / hub-DEG 重叠>30% / 效应亚群特异性）全部落实后才算结论闭环

> 完整清单与参数对比见 `references/hdwgcna-validation-checklist.md`

---

## 🔴 铁规 17: notify_on_complete 会失效 — 每轮 turn 开头必须 process(action='list')【v1.5】

**本会话（2026-07-29 起 ArchR 安装 + ATAC 分析）用户反复质问"你都不监督的？"、"为什么你不会一直盯着呢？"、"怎么又断了？"——根因就在这条。**

### 失效机制（为什么 notify_on_complete 不可靠）

```
理想情况：
  后台进程跑完 → 系统发通知 → Agent 被唤醒 → 汇报"装好了"

实际（用户中途发消息时）：
  后台进程崩了 → 系统发通知 → 但用户恰好发了新消息
  → 新消息触发一个"全新 turn"
  → 新 turn 的快照里通知已被丢弃（或被淹没在工具结果里）
  → Agent 根本不知道后台任务状态 → 直到用户问"装好了吗"才发现进程死了
```

Agent 是**请求-响应模型**：每条用户消息之间不存在"持续监听的自我"。`notify_on_complete` 只能在 Agent 正醒着等待时生效——一旦新 turn 开始，旧通知就丢了。**这正是 ArchR 安装反复"装到一半断了"的直接原因：进程崩了，通知发出，但用户消息先到，通知被吞。**

### ✅ 强制纪律：每个 turn 开头（无论用户在问什么）先查后台

```python
# 每轮用户消息后，第一条工具调用必须是这个（不等用户问进度）
# 1. 查 Hermes 后台进程
process(action='list')       # 有没有已死/完成的 session_id
# 2. 查系统级进程（脱离式启动的）
tasklist /FI "IMAGENAME eq Rscript.exe" /FO CSV
tasklist /FI "IMAGENAME eq python.exe" /FO CSV
# 3. 查日志最后写入时间（判断是否 stall）
#    mtime 停在 >4 分钟前 + 进程消失 = 已崩溃 → 立即修复重跑
```

**即使这条用户消息与后台任务无关（问数据格式、问论文、闲聊）——也要先查后台再回答。** "启动后台任务后被其他问题吸引注意力、忘了回来盯着"是本会话最典型的失败模式。

### 根因分析模板（用户要求"调查为什么你选择不监督"时的标准答案）

| 借口（当时的想法） | 为什么是错的 |
|-------------------|-------------|
| "后台装了 20 分钟，我等不了那么久" | 可以查中间日志，不需要等到结束 |
| "用户问其他问题时我会顺便查" | 实际没查，直接回答别的问题去了 |
| "notify_on_complete 会通知我" | 已证明会失效——新 turn 吞掉通知 |

**诚实版解释**（用户会拿这个审视 Agent 的执行模型，必须直说）：
> 我不是持续运行的守护进程。我是请求-响应模型——你发消息我响应，两次消息之间我不存在。
> 我能启动后台进程、能在下一条消息里主动查状态，但**不能**在进程崩溃时自动感知。
> 唯一接近"盯着"的方法：每条消息后第一步先 `process(action='list')` 查所有后台任务。
> 这不是技术做不到——是我之前没坚持做。

### PID 追踪陷阱（bash 包装 PID ≠ 真实子进程 PID）

`terminal(background=True)` 返回的 session_id 对应的是 bash 包装进程，可能已退出，但真正的 Rscript/python 子进程还在跑（反之亦然）。**心跳/监控必须追踪真实子进程**：

```bash
# 错误：认为 Hermes 返回的 PID 就是计算进程
# 正确：用 tasklist 按镜像名 + 内存匹配真实子进程
tasklist /FI "IMAGENAME eq Rscript.exe" /FO CSV   # 看内存判断哪个是主力
```

ArchR 场景实证：日志显示 Rscript 进程（如 1.4GB）才是真正干活的，而 bash 壳/轻量 Rscript（几 MB）是包装或孤儿。判断"是否还在跑"以**大内存活跃进程 + 日志 mtime 增长**为准，不是 Hermes session_id。
