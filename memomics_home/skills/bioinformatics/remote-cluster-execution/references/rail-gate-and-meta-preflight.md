# rail_review(pre) 本地口径拦截集群作业 + 元数据 levels 前置核查（2026-10-09 实测）

两条都在同一次 ssh23 DEG 投递里踩到，都是「不报错但会毁掉整批结果」的类型。

---

## 1. `rail_review(pre)` 只点本机 R → 集群 submit 被硬拦

### 事实

`rail_review(phase="pre", required_packages=[...])` 检查的是**本机** R/Python 包清单，
它**不知道集群 env 里有什么**。于是「跑在集群 R4.41 上、本地根本不需要」的包会把投递挡死：

```
{"phase":"pre","module_id":"deg","should_proceed":false,
 "issues":["Missing packages: RUVSeq"],"missing_packages":["RUVSeq"]}
```

接着任何 `submit` / `run` 都返回：

```
🛡️ rail_review(pre) 发现问题: Missing packages: RUVSeq。请修复后重新 rail_review(phase='pre')
通过再执行。（已连续拦截 1 次）
```

⚠️ **拦截覆盖 `run`**，所以「想先去集群上验一下这个包到底在不在」的那次 `run` 也被挡 ——
形成死锁：想证明集群有包，却必须先让本机有包。**不要指望用 `run` 去绕过。**

### ✅ 首选解：传 `location="cluster"`，根本不用装本地（2026-10-09 二次实测，取代下面三步）

`rail_review` 支持**按执行位置审查**：只查对应位置的包清单。集群作业带上 `location` + `node` + `env`，
上面的死锁**直接消失**：

```
rail_review(phase="pre", module_id="deg", method_name="...", skill_name="...",
            location="cluster", node="ssh23", env="R4.41",
            required_packages=["Seurat","edgeR","RUVSeq","MAST","lme4"])
```

同一次 MuSC 投递的对照实测：

| 写法 | 回执关键字段 | 结果 |
|---|---|---|
| 不传 `location` | `missing_packages:["RUVSeq"]` | ❌ 被拦 → 被迫装本地包 |
| `location="cluster", node="ssh23", env="R4.41"` | `location_line: 集群 ssh23/R4.41 —— 显式指定（节点上的 R 包清单，694 个包，缓存命中）`；`should_proceed:true` | ✅ **零本地安装** |

- **显式传 `location` 才有硬拦效力**；`location_source:"inferred"`（自动推断出来的位置）报出的问题**只警告、不拦执行**。
- **本地缺 ≠ 集群缺**，反之亦然（`ssh23/R4.41` 里 RUVSeq / MAST / lme4 / edgeR 都在）。
- 正确顺序：**先带 location 试 pre-review → 只有它仍报缺包，才走下面的补包三步。**
- ⛔ 仍不要少报 `required_packages` —— 只是把审查口径从「本机」换到「执行位置」，不是取消审查。

### 解绑三步（旧写法，仍有效；仅当 location 口径也报缺包时用）

1. `check_env(packages=[<缺的包>], language="R", auto_install=false)` 先确认本机确实缺（快速、无副作用）；
2. `check_env(..., auto_install=true)` → 走平台安装通道补到本机（返回 `installed_now: {...}`）；
3. 重新 `rail_review(phase="pre", ...)` → `should_proceed=true`，门禁自动解绑，投递放行。

### 必须主动交代口径（用户会当场质疑）

实测用户原话：**「集群不是有自己的环境吗？你用本地的干什么？用集群的环境 R4.4.1 跑啊」**。

那次安装**与运行无关**，纯为过本机门禁。汇报时必须一次说清并给证据，否则用户会认为你在拿本地环境跑：

- 作业命令里的解释器：`export PATH=<conda_root>/envs/<env>/bin:$PATH` + `Rscript <脚本>`
- 作业日志**首段**的集群包自检输出（`pkg RUVSeq TRUE` 之类）
- 明说「要不要卸掉本地那份，我可以卸」

### 不要做的

⛔ 不要为了让门禁通过就**少报** `required_packages` —— 门禁拦的是「你声明的依赖没装」，
瞒报 = 自己拆掉 pre 审查，把风险留到运行期。

---

## 2. 投递前必须核查分组列的**真实取值**（否则整批静默跳过）

### 症状

脚本每个亚群、每个比较组都打印 `跳过：组别缺失`，一个 CSV 都不出，**脚本本身零报错**，
退出码 0，看上去像「跑完了」。

### 根因

脚本硬编码了分组 levels：

```r
md$type <- factor(as.character(md$type),
                  levels = c("Y_Pre","Y_Post","O_Pre","O_Post","OD_Pre","OD_Post"))
```

而 rds 里 `type` 的真实取值是另一套命名：

```
Young_normal / Young_normal_Post / Old_normal / Old_normal_Post /
Old_diabete / Old_diabete_Post
```

→ `factor()` 全部变 NA → `grp %in% unique(ct$type)` 永远 FALSE → 每次 `next`。**只在日志里可见。**

### 前置核查（投递前必做）

1. **先探 levels 再投作业**：`unique(as.character(obj$type))` + `table()`。
   ⛔ **探针里不要套 `factor(levels=...)`** —— 那会把真值抹成 NA，看起来像「没有这个分组」。
2. 用**用户给定的**映射代码。用户给了 `dplyr::recode(...)` 就**原样用**，
   不要替换成自认为等价的实现（本轮用户明确说「按照这个代码，帮我修改一下」）。
3. ⚠️ **`dplyr::recode()` 的坑**：对**未命中**的值是**原样保留**（`default = NULL`），
   **不产生 NA** —— 所以 `if (anyNA(x)) stop()` **抓不到漏映射**。守卫必须写成集合判定：

   ```r
   short_codes <- c("Y_Pre","Y_Post","O_Pre","O_Post","OD_Pre","OD_Post")
   if (!all(md$type %in% short_codes))
     stop("type 映射失败：出现未映射取值 -> ",
          paste(setdiff(unique(md$type), short_codes), collapse = ", "))
   ```

4. 映射后**把 `table(mapped)` 打印进日志**，供事后核对（自证）。
5. 顺带在脚本开头打一行元数据摘要，把隐藏假设暴露出来：

   ```r
   cat(sprintf("[meta] 细胞 %d | 样本 %d | 个体 %d | 亚群 %d\n",
               ncol(obj), length(unique(md$Sample)),
               length(unique(md$individual)),
               length(unique(as.character(obj$annotation_L3)))))
   ```

   —— 个体数不对（例如把每个 cell 当一个人）会让配对随机效应 `(1|individual)` **静默降级**
   为无 RE 的 `bayesglm`，这一行是唯一能提前看出来的地方。

---

## 3. 本轮实际用的投递命令（可复用骨架）

```bash
cd <workdir>
export PATH=<conda_root>/envs/R4.41/bin:$PATH
echo "=== host=$(hostname) start=$(date '+%F %T') ===" > <out>.log
Rscript -e 'for (p in c(<pkgs>)) cat(sprintf("  pkg %-8s %s\n", p, requireNamespace(p, quietly=TRUE)))' >> <out>.log 2>&1
Rscript <脚本>.R >> <out>.log 2>&1
echo "=== done=$(date '+%F %T') rc=$? ===" >> <out>.log
```

- 首段包自检 = 集群侧环境自证的证据（也是向用户交代「跑的是集群 env」的凭据）。
- 日志**落共享工作盘**（`/cluster/...`），不要只落 `~/memomics_jobs/logs`（`/home` 不跨节点）。
- `submit` 返回 `exit=124 / Command timed out after 20s` 是**已知误报**，作业其实已起；
  用 `ps -ef | grep <脚本名>` + `tail` 日志核实，**不要重投**（重投会因脚本自身
  `if (file.exists(fn)) next` 断点续跑，但白占一次投递）。

---

## 4. `rail_review(post)` 在集群产物上是**两连误判** —— 先 pull 再复审（2026-10-09 实测）

集群作业跑完，按流程调 `rail_review(phase="post", output_dir="<集群绝对路径>")` →
**两次都是假失败**，且提示的方向会把人带偏：

### 误判 A：`Output directory not found: /cluster/.../MuSC_RUV_result`

post 审查是**在 Agent 本机磁盘上**找 `output_dir`，**看不见远端文件系统**。
拿集群路径喂它 → 必然 not found，看着像「产物没生成」。

**修法**：先 `remote_cluster action="pull"` 把表格/图拉回 `results/<sid>/`（铁规 4 的产物分工本来就要求这么做），
再把 `output_dir` 指到**本机拉回的目录** → `result_files` 立刻正确列出 4 个 csv。

### 误判 B：`未生成任何图片 — 每步至少 1 张图`

产物是纯表格（统计矩阵）时必然 `figure_count=0` → 判 failed。
**这不是"可忽略的提示"，是硬要求**：**纯统计任务也必须补一张结果可视化图**（覆盖率热图 / 柱状对比 / 分布），
否则 `rail_review(post)` 永远不过。

### 正确顺序（无坑版）

```
集群跑完
  → remote_cluster action="pull"（表/图/日志 → results/<sid>/）
  → 按需补一张结果图（纯统计任务：热图/柱状）
  → rail_review(phase="post", output_dir="<本机 results 目录>",
                code_executed=<完整脚本>)     ← 传 location="cluster" 也可，但 output_dir 必须是本机可读路径
  → skill_evolution(action="record_run")
```

### 如实汇报口径

若最终仍卡在某条软规则（如「关键步骤至少 2-3 张图」而本轮只出了 1 张）：
**说清"口径不匹配 + 为什么不硬凑第二张"**（纯计数任务第二张图无实质信息量），
不要补假产物、也不要把假的 `passed=true` 说给用户。