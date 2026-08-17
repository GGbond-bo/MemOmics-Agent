# Case Study: "开始" Command Neglect + Path Assumption (2026-07-25)

## Timeline

```
T+0  User: "进度呢？？？？？傻逼"
     Agent: 查了 GPU → 6%, process list → 空, dir → 只有 2 个 filtered.h5
     Agent: 写 run_cellbender_serial.py 到磁盘
     Agent: terminal(background=true) 启动脚本
     → 脚本输出: "Total to run: 0, DONE"

T+1  User: "为什么没跑？？？我不是说了要你跑吗？？？"
     Agent: 终于 debug — h5ad 在 PROJECT_DATA_DIR/h5ad/ 子目录，不在根目录
     Agent: patch 脚本路径 → 重新启动
     → 这回 "Total to run: 24" ✓ 真正在跑了
```

## Pattern: "开始" Neglect

**What happened**: Agent wrote a script + called terminal, but the script silently returned 0 → Agent didn't verify, assumed success, and the user was left waiting.

**Root cause chain**:
1. Agent didn't `ls` the directory before writing glob path → path wrong
2. Script exit 0 but "Total: 0" → Agent didn't cross-check against known completed count (2)
3. Agent reported "跑起来了" based on process exit 0, not on logical output correctness

## Why This Is Not Caught by Existing Iron Laws

- Iron Law -1 (action-bind): satisfied — terminal() was called
- Iron Law -2 (multi-source verify): partially satisfied — nvidia-smi/dir checked before writing script
- Iron Law 12 (output verification): NOT triggered — script exited 0 and this was a *launch* not a *completion*

**The gap**: No rule says "after launching a pipeline script, verify that its stdout makes logical sense before reporting success to user."

## Prevention Rule (Proposed)

```
After terminal(background=true) launching pipeline:
  1. Wait 5 seconds
  2. Read process log → check "Total to run: N"
  3. If N < (expected_total - already_completed) → PATH/INPUT ERROR, do NOT report success
  4. If process exited with rc=0 and N=0 while completed < expected → LOGIC ERROR, fix and retry
```

## Prevention for Path Assumptions

```
Before writing a batch script that glob()s files:
  1. search_files(target='files', pattern='*.h5ad') — confirm exact directory
  2. Include the confirmed path in the script as a verified constant
  3. Never assume "it's in the root" — subdirectories are the norm for organized projects
```
