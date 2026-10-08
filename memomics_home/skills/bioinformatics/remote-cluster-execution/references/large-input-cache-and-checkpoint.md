# 大输入持久化 · 任务标记 · 长任务检查点（2026-10-08 用户拍板落地方案 A）

> 触发：任何**要读 ≥100MB 输入**（`.rds` / `.h5ad` / 大表格 / `.bam` / `.loom` / `.zarr`）的集群或本地分析；
> 任何**预计 >60 分钟**的长程任务。
> 来源：用户原话——「检测到执行读取数据分析，弹窗询问用户要不要持久化，**大于 100M 的内容，都要推荐持久化**。
> 比如 RDS、h5ad，一些超大表格也是一样，并**做好任务标记，方便清理**。」

---

## 一、为什么不是「持久进程」（先认清问题）

用户问的是「集群 R 进程能不能持久化，总不能每次都读一次吧？我这个才 600M，我的 MF 可是有 10G」。

- 集群**能**做常驻会话（SGE 有 `qlogin`/`qrsh`，`screen` 在位），但代价是**一直占核和内存**、
  节点宕机/被清场即全丢、受 walltime 限制 → **不该默认上**。
- 真正被罚的不是「进程不持久」，而是**把一条链拆成一堆小作业** → 大输入被读 n 次。
- 所以方案 A = **一个作业跑完整链 + 读一次就落精简缓存 + 阶段检查点**。

| 场景 | 做法 |
|---|---|
| 大输入 + 一条管线 | ✅ **单作业**跑完（读一次） |
| 大输入 + 反复调版式/参数 | ✅ **精简缓存**（reductions+meta，约原文件 5%）→ 后续秒级 |
| 大输入 + 真·交互式来回调 | ⚠️ 才考虑常驻会话（Rserve / 文件队列 daemon），代价见上 |

---

## 二、>>100MB 输入的强制流程（agent 侧）

```
分析前拿到输入路径
   ↓
python -m memomics.bio_tools.large_cache scan <路径> [--min-mb 100] --json
   ↓
recommend 非空（有 ≥100MB 项）？
   ├─ 是 → ask_user(kind="intent", multi_select=true) 弹窗：
   │        「检测到 X.rds（10.4 GB）——要不要建持久化缓存/检查点？」
   │        选项：① 建精简缓存+检查点（推荐，重跑不重读）② 不建，本次读完即弃
   │             ③ 只建检查点不建缓存（省空间）④ 保持原文件不动，仅登记标记
   │      → 用户答复后：python -m memomics.bio_tools.large_cache mark ...
   └─ 否 → 不弹窗，直接跑（600MB 以下重读一次不到 40 秒，没必要打扰用户）
```

**判据是「值不值得打扰」**：≥100MB 才推荐持久化；低于阈值不弹窗（用户明确要求）。

## 三、任务标记（方便清理）

```bash
# 建标记：读了什么 / 缓存放哪 / 产物是什么 / 几时过期
python -m memomics.bio_tools.large_cache mark \
  --task-id MF_light_20261008 --title "MF 10GB 长任务" \
  --input /hwfssz3/PS_JLU/zhangbo/MF_clean_annotation_umap.rds \
  --cache-root /hwfssz3/PS_JLU/zhangbo/MF_work/cache \
  --artifact /hwfssz3/PS_JLU/zhangbo/MF_work/cache/light.rds \
  --remote --ttl-days 14 --session-dir results/<sid>

# 看全 / 自证 / 清理（默认 dry-run）
python -m memomics.bio_tools.large_cache list [--stale-days 14]
python -m memomics.bio_tools.large_cache verify <task_id>
python -m memomics.bio_tools.large_cache clean <task_id>            # 只演示
python -m memomics.bio_tools.large_cache clean <task_id> --yes      # 真删
python -m memomics.bio_tools.large_cache clean --stale-days 14 --yes
```

落点：`<runtime>/cache_markers/<task_id>.json`（原子写）+ `index.jsonl`（总索引）。
`MEMOMICS_RUNTIME_DIR` 可改根（默认 `<repo>/memomics_home/runtime`）。

**标记 schema 要点**：`inputs[].fingerprint`（size + 首尾 1MB sha256，**不整读 10GB**）、
`cache_root`（清理范围的唯一依据）、`artifacts[]`、`expires_at`、`remote`、`cleanup_cmd`。

## 四、清理的三道闸（删错比不删贵）

1. **原始数据保护**：`artifacts` 里若出现 `inputs` 中任一路径 → **拒绝**（原始文件永不删）。
2. **cache_root 约束**：产物必须落在声明的 `cache_root` 内，否则拒绝；未声明 `cache_root` → 整体拒绝（不猜范围）。
3. **默认 dry-run**：不加 `--yes`/`--force` 只打印将删项。

另：**远端产物只打印 `rm -rf` 命令**，由 `remote_cluster action="run"` 执行——不在本机假装删掉了。
清理后标记**不物理删除**，改 `status=cleaned` 留痕。

## 五、长任务检查点模板（方案 A 主体）

| 文件 | 作用 |
|---|---|
| `scripts/checkpoint_job.R` | 单作业三段式：`0_load_cache`（读一次→`cache/light.rds`）→ `1_compute` → `2_figures`；每阶段落 `ckpt/<name>.done`（含**参数指纹**，`tools::md5sum` 打在参数文本上，只用 base R），指纹一致→**跳过**；全程 `#TASK:` 打点 |
| `scripts/run_cluster_job.sh` | SGE/Slurm 投递包装：显式 `PATH=$CONDA_ROOT/envs/$ENV_NAME/bin`（铁规 2）、日志落 `$WORKDIR/log/`、透传退出码 |

断点续跑语义：**同参数重投 → 跳过已完成阶段；改参数 → 只重跑受影响阶段；大输入不再重读**。

## 六、诚实边界

- `est_cache_size_mb` 是**经验估算**（rds/h5ad ≈5%、表格 ≈20%），非实测——提示用户「缓存大概多大」，不是承诺。
- 精简缓存**丢了原始稀疏矩阵**（只留 reductions + meta），所以「需要重算表达量」的步骤仍要回原文件
  ——缓存适合「出图/调参/统计/元数据类」反复跑，不适合替代原始数据。
- 检查点指纹只覆盖**显式传入的参数**；脚本内硬编码的常量改了但没进参数 → 指纹不变，会被误跳过。
  （要严格就改常量时手动 `rm ckpt/<stage>.done`。）