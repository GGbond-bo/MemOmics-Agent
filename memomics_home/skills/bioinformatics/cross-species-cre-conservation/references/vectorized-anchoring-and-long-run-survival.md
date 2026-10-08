# 向量化配对 & 长任务存活性（2026-09-12 实施 ①②③ 实战教训）

> 触发场景：重写任何「万级基因 × 百万级 tile」的跨物种配对脚本；或某个长任务**没报错就消失**。
> 标本脚本：`E:/MemOmics-Agent/results/memomics-7839e23a/scripts/fix_v10_v2_grid_drift_depth.py`
> 产出目录：`E:/专利/M2/FIX_v10/{00_cache,01_unified_grid,02_depth_correction,03_drift_removal,04_combined,99_report}`

---

## 1. 死法一：逐组 DataFrame 布尔扫描 = O(n²)（v1 崩在这里）

**v1 的写法**（读起来完全正常，实际是灾难）：

```python
for mg, (hg, sym) in bridge.items():        # 16,160 次循环
    msub = m_bin[m_bin.gid == mg]           # ← 每次都对百万行表做全表布尔扫描
    hsub = h_bin[h_bin.gid == hg]
    j = msub.merge(hsub, on='bin', suffixes=('_m','_h'))
    for t in j.itertuples():                # ← 结果再堆进 tuple 列表
        rows1.append((sym, t.Z_m, t.Z_h, ...))
```

复杂度 ≈ 16,160 × 10⁶ = **数百亿次比较** → 内存与时间同时爆。
**症状**：`条件0 基线` 打印完（17 min 处）进程消失，**log 无 traceback**。

**v2 的向量化写法**（O(n log n)，秒级）：

```python
# 猴侧 gid → 人侧 gid/symbol 的桥接表（一次性建）
br = pd.DataFrame([(mg, hg, sym) for mg, (hg, sym) in bridge.items()],
                  columns=['m_gid', 'h_gid', 'symbol'])

def pair_bin(mbin, hbin, br):
    """(gene,bin) 级配对 —— 两次 merge 取代万次布尔扫描"""
    d = mbin.merge(br, left_on='gid', right_on='m_gid')                       # 猴 bin → 人 gid
    d = d.merge(hbin, left_on=['h_gid', 'bin'], right_on=['gid', 'bin'],
                suffixes=('_m', '_h'))                                        # 按 (人 gid, bin) 配对
    return d[['symbol', 'Z_m', 'Z_h', 'p_m', 'p_h', 'bin', 'count_m', 'count_h']]
```

基因级同理（原来用 `mz.loc[mg,'Z']` 万次索引）：

```python
def pair_gene(magg, hagg, br):
    d = magg.merge(br, left_on='gid', right_on='m_gid')
    return d.merge(hagg, left_on='h_gid', right_on='gid', suffixes=('_m','_h'))
```

**通用判据**：只要出现 `for x in 万级列表: df[df.col == x]` → 立即改成 `merge` / `map`。
`groupby().apply()` 逐组也没好到哪去，别用。

## 2. 死法二：大 n 上的蒙特卡洛置换

`N_PERM = 20000` 在**门控后的小数组**（n≈900）上没问题（1.8e7 次操作，秒级）；
**直接套到全量数组**（n≈10⁵–10⁶）= 2×10¹⁰ 次 → 卡死。

```python
def perm_eff(n, cap_ops=2e7, floor=2000, ceiling=N_PERM):
    """置换次数随 n 自适应，保持总操作量有界"""
    return int(min(ceiling, max(floor, cap_ops / max(n, 1))))
```

**更省的办法（同向计数专用）**：打乱一侧符号**保持其边际正负比例不变**，所以"同向计数"的零分布
= **独立配对模型**，可直接解析算期望与方差，无需模拟：

```python
ph = (Zh > 0).mean(); pm = (Zm > 0).mean()
base  = ph*pm + (1-ph)*(1-pm)          # 期望同向率（基准，非 50%！）
# 方差 = n·base·(1-base) 的近似；严谨版用超几何（固定 Zm 符号计数）
# 汇报格式固定四列：obs / base / delta_pp / z
```

> 首次实施时若已把 `perm=N_PERM` 写进全量分支，等于给自己埋一颗定时炸弹——**全量与门控后两条分支的 perm 必须分开设定**。

## 3. 判活 / 判死（"没有 traceback 就消失"怎么定性）

| 查什么 | 怎么查 | 结论 |
|---|---|---|
| log 是否在推进 | `os.path.getmtime(log)` / `wc -l` | mtime 停住 = 卡死或被杀的近似信号 |
| 进程在不在 | `psutil.process_iter(['pid','name','cmdline'])` 按 **cmdline 匹配脚本名** | Windows 上 `wmic` 可能不存在；`tasklist` **看不到命令行**，只靠进程名会误判 |
| **有没有 traceback** | `tail` log 全文 | **log 尾部无 traceback 而进程消失 = 被外部杀掉（OOM / 父进程回收），不是代码报错**；此时不要再"修报错"，去查内存/复杂度 |

另：`terminal(background=True) ... \| tee log` 的退出码是 **tee 的**（恒 0）——
**"exit code 0" 不代表脚本成功**，必须看 log 尾部有没有 traceback / 完成行。

## 4. 存活性设计（写任何 >10 分钟脚本前先做）

```
① 阶段缓存   昂贵中间件（tile→基因锚定表）落 00_cache/*.parquet；命中即跳过
              （pyarrow 24.0.0 本机可用；人侧锚定 4 min / 猴侧 4 min，崩一次就白跑）
② 逐阶段落盘 每个条件算完立刻 to_csv，崩溃时前面所有阶段不丢
③ print(flush=True)   管道到 tee 时 stdout 是块缓冲，不 flush 会导致"跑到一半的日志全丢"
④ 用 execute_python 持久内核分步跑（能看到真实异常）
             不要 terminal python xx.py 冷启动长脚本
⑤ 量级断言   assert 1e6 < n_anchored < 1e7 之类，把静默错误挡在统计之前
```

## 5. 修复项 → 目录映射（用户明确要求"文件标好对应目录"）

| 目录 | 内容 | 命名 |
|---|---|---|
| `00_cache/` | 锚定缓存 | `anchored_tiles_{human,monkey}.parquet` |
| `01_unified_grid/` | 修复① 统一元件网格 | `ortholog_grid_pairs.csv`、`..._drift_centered.csv`、`baseline_gene_level_pairs.csv`、`fix1_grid_stats.json` |
| `02_depth_correction/` | 修复② 深度校正 | `anchored_grid_depth_corrected.csv`、`fix2_null_params.json`、`fix2_depth_stratified_concordance.csv` |
| `03_drift_removal/` | 修复③ 消除漂移 | `drift_centered_gene_level_pairs.csv`、`fix3_drift_stats.json` |
| `04_combined/` | 四条件对照 | `concordance_4conditions.{csv,json}` |
| `99_report/` | 运行日志 | `fix1_fix3_run.log` |

原则：**按任务项/修复项分目录，不按时间戳**；每个子目录自带 `fixN_*_stats.json`（参数+关键数字），
让结论与数字同处一目录可定位。

## 6. 跨聚合层的阈值陷阱（实施 ① 时必然踩）

统一网格后统计单元从**基因级**变成 **(gene, bin) 级** —— bin 内 tile 数少 ⇒ Stouffer Z 整体偏小。
**沿用基因级的 τ_A=12 会把网格结果几乎筛空**（看似"方法没效果"，其实是阈值不可比）。
⇒ 跨聚合层比较**必须改用分位数匹配阈值**（各层取同分位，如各取 |Z| 前 9%），
并在报告里写明"阈值按层分位数匹配"，否则用户会以为网格化把信号弄没了。
