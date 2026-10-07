# WSL 内后台任务判活：进程表空 ≠ 进程死（2026-08-31 实证）

## 事故还原

L1 全量打分（`l1_full_peaks_human.py`，52.5 万 peaks × 3 轨道）在 WSL Ubuntu 内跑。
`process(action='list')` 返回空 → 一度误判"打分进程死了/被中断"并提出续跑方案（l1_resume_human.py）。
随后实查：WSL 内 `ps aux` 有 `python3 l1_full_peaks_human.py`（PID 302，CPU 27%），
输出文件 `v3/l1_full_human.csv` 10 秒采样行数持续增长（275,755 → 326,305 → 366,001 → 376,472 行 / 71.7%）。
**进程根本没死，是 `process list` 看不到 WSL 内部进程。**

另一干扰信号：`proc_e5dc0b99ade7` 以 exit code 2 退出（bash `unexpected EOF`）——
那是**删除确认门禁**拦截"rm -rf v3 && 重跑"命令后生成的提示脚本自身报错，与打分进程无关。
把它当成"打分进程死了"的证据是误判链的一环。

## 判活三查（缺一不可）

```bash
# ① Windows 侧进程（只看得到非 WSL 进程）
process(action='list')  # 或 tasklist

# ② WSL 内部真实进程（关键！）
wsl.exe -d Ubuntu -u root -- bash -lc "ps aux | grep -E 'python|l1_full' | grep -v grep"

# ③ 输出文件增长采样（最硬的证据）
wc -l v3/l1_full_human.csv && sleep 10 && wc -l v3/l1_full_human.csv
# 行数/大小在增长 = 进程活着
```

**判死标准：②无进程 且 ③文件不再增长（两次采样间隔 10-15s 完全不变）→ 才说"死了"。**

## 规则

1. **在 WSL/容器里跑的长任务，Windows `process list` 为空是正常现象，不是死亡信号。**
2. **判活靠输出产物增长 + WSL ps，不靠 process list。**
3. **未判死前禁止 `rm -rf` 产出目录重跑**——删除确认门禁（rm 需用户确认）会拦截该命令并让它整体 exit，反而容易误当成"进程失败"。
4. **判活后停止轮询**：确认进程活着 + 文件在增长 → 向用户汇报状态 → 等 completion 通知，不要每轮重复同一个 wc/ps 监控命令（系统循环检测会拦截）。
5. 输出文件尾部停在中间染色体（如 chr9）只是**当前进度**，不是中断证据——先用判活三查，再下结论。