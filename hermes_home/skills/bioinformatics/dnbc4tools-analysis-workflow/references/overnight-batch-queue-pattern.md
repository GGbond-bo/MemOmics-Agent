# 夜间批量排队模式（"先跑两三个，我早上醒来看看"）— 2026-09-01 实测

## 场景
用户要跑大批量 ATAC 文库（如 24 个、每个 88–174G fq），但当晚只要求先出 2–3 个结果，
早上醒来再看。此时**不要**直接全量循环（磁盘可能爆：F 盘 222G 余量 vs 全量输出 500G–2TB），
也不要在 Hermes 会话里挂前台进程（会话回收进程对象就丢）。

## 核心模式：试点单库（已在跑） + 排队脚本（nohup 挂后台，串行接后续库）

### 1. 试点已启动但跑完即退 → 补一个"接力排队"脚本
- 试点用 `SLIB=<文库> bash atac_run_batch.sh` 启动单库模式：**跑完当前库就退出**，
  不会自动接下一个（环境变量已实测确认）。
- 用户要 2–3 个 → 另写 `atac_queue_next.sh`：先等试点完成（轮询完成标志），再串行跑后续库。

### 2. 完成标志（复用为 跳过/等待 双重判据）
**⚠️ 实际路径（2026-09-01 实测修正）**：`atac run --outdir $OUT --name $s` 的最终产物在
**`$OUT/$s/output/singlecell.csv`**——outdir 下**多一层 name 子目录**（不是 `$OUT/output/`）。
- 批量脚本用它做断点续跑（已完跳过）
- 排队脚本用它做"等试点完成"的轮询判据（30s × 720 ≈ 12h 上限）
- 写脚本前先 `find $OUT -name singlecell.csv` 确认真实层级，别按猜的路径写。

### 3. 排队脚本骨架（已验证可跑）
```bash
#!/bin/bash
# 等 <PILOT> 完成 → 串行跑 <S1> → <S2>
DNBC=/opt/dnbc4tools3.1/dnbc4tools
GENOME=/data/GRCh38_ref/GRCh38_atac_index/Homo_sapiens
OUT=/mnt/f/output; LOG=$OUT/logs
# 等待试点完成（含进程消失兜底：batch 脚本被 kill 也能接上）
for i in $(seq 1 720); do
  [ -f "$OUT/<PILOT>/output/singlecell.csv" ] && break
  if ! pgrep -f "atac_run_batch.sh" >/dev/null && [ ! -f "$OUT/<PILOT>/output/singlecell.csv" ]; then
    tail -20 "$LOG/<PILOT>.log" >> "$LOG/batch.log"; break   # 试点死了也接上
  fi
  sleep 30
done
for s in <S1> <S2>; do
  [ -f "$OUT/$s/output/singlecell.csv" ] && { echo "SKIP $s"; continue; }
  r1=$(ls "$DATA/$s/"*_1.fq.gz | sort | paste -sd,)
  r2=$(ls "$DATA/$s/"*_2.fq.gz | sort | paste -sd,)
  "$DNBC" atac run --name "$s" --fastq1 "$r1" --fastq2 "$r2" \
    --genomeDir "$GENOME" --outdir "$OUT/$s" --threads 16 --darkreaction auto \
    > "$LOG/$s.log" 2>&1
done
```

### 4. 用 nohup 挂进 WSL，脱离 Hermes 会话
```bash
wsl -e bash -c "chmod +x /path/to/atac_queue_next.sh && \
  nohup bash /path/to/atac_queue_next.sh > /mnt/f/output/logs/queue.log 2>&1 & echo QUEUE_STARTED"
```
⚠️ 启动命令末尾 `&` + 立即 echo——`wsl -e bash -c "nohup ... & echo pid=$!"` 是前台返回，
nohup 的子进程留在 WSL 内部继续跑（Hermes 的 background process 对象随会话消失，WSL 内 nohup 不受影响）。

## 关键教训
1. **选库先排序**：`for d in */; do du -sh "$d"; done | sort -h` 选最小 2–3 个先跑
   （磁盘紧时保证最快出结果 + 试点体积可推算全量总账）。
2. **串行不并行**：ATAC 单库输出 40–80G，2 个并行非常可能爆余量盘；排队脚本天然串行。
3. **Hermes process(list) 看不到 WSL 内 nohup 进程**：查状态必须
   `wsl -e bash -c "ps aux | grep dnbc4tools"` + `tail <outdir>/<name>.log`（日志落在 F 盘）。
4. **向用户交付可检视的产物路径**：告诉用户早上看 `F:\output\<文库名>\output\singlecell.csv`
   （每库一个）+ `F:\output\logs\batch.log`（全部批次状态），PPATH 明确。
5. 排队脚本也要走铁律 24 的 skill_evolution(record_run) 沉淀，否则后续 terminal 被拦截。
6. **挂完排队脚本必须 ps 验证真在跑**（2026-09-01 事故）：`nohup ... &` 后
   `wsl -e bash -lc "ps -ef | grep atac_queue"` 确认；本会话声称已挂好但实际只有单库实例在跑，
   排队链从没生效——向用户报"已启动"前必须工具验证。
7. **磁盘告急先问用户再停**：输出盘将爆（余量 < 单库占用）时，展示实测数据+止损方案
   （换盘/边跑边删/只跑试点）让用户选；不要单方面 kill 用户已启动的比对任务（信任损失不可逆）。
8. **单库磁盘占用量级**：88–174G fq.gz → parse 阶段中间 fq 就 ~64G，全流程 >180G/库；
   批量前按此核算输出盘，`df -h` 余量 <200G/库即危险。