# 大输入清单与 `large_cache` 的真实边界（2026-10-08 实测）

配套：铁规 10（≥100MB 必须弹窗 + 落标记）、`memomics/bio_tools/large_cache.py`。

## 1. 事故与根因（为什么这份 reference 存在）

- 本 skill 已写好铁规 10，随后仍对集群上 **662MB** 的
  `/cluster/share/user/Muscle_96_38/Umap/MuSC_exercise_clean_dele_cluster_umap.rds`
  直接写脚本 + `submit`，**无 scan / 无弹窗 / 无标记**。
- 用户追问：「**你没有持久化吗？**」
- 三条实证（复查用这三条，别只靠记忆）：
  1. 体积 `stat -c '%s'` = `693958736`（662 MB）→ ≥100MB，**应触发**；
  2. `mtime` 仍是 `2026-06-11 10:55` → 作业**只读**，一个字节没动；
  3. `~/memomics_jobs/` 下只有 `logs/` + `scripts/`、**无 marker** → 确认没落标记。
- **根因不是"不知道规矩"，是规矩没接在执行路径上**（拿到路径 → 投作业之间无强制前置步骤）。
  → 修法：把铁规 10 当**前置门禁**，在「写脚本之前」执行。

## 2. `large_cache` CLI 的真实接口（源码核实，别凭猜）

```
usage: large_cache [-h] {scan,mark,list,show,verify,clean} ...

scan   --min-mb MIN_MB [--json] paths [paths ...]
mark   --task-id TASK_ID [--title T] [--input P] [--cache-root P]
       [--cache-scope S] [--artifact A] [--remote] [--note N]
       [--ttl-days N] [--session-dir P] [--min-mb M]
```

🔴 **`scan` 只认本机路径**：

- 实现走 `os.path.exists(p)` / `os.path.getsize(p)` / `_dir_size(p)`（`large_cache.py:150-163`）；
- **没有 `--remote` 参数**（模块 docstring 亦写明"不在本机访问远端"）；
- 喂集群路径（`/cluster/...`）→ 返回 `{"exists": false, "size": 0}`，**不是报错**，
  所以很容易被误读成"没有大文件"。
- ⇒ **集群输入的体积必须另取**（`stat -c '%s|%y|%n'`），判定后再 `mark`。

🔴 **`mark` 有 `--remote`**：集群产物必须带，否则 `clean` 会因本机 `os.path.exists=False`
走不到"只打印 `rm -rf` 命令"的分支（`large_cache.py:395-397` 注释即为此而写）。

## 3. 实测：`Muscle_96_38/Umap/` 是「成批大文件」目录

一次 `ls -la` 就暴露出 6 个同量级 RDS（这就是要建"项目大输入清单"的理由）：

| 文件 | 体积 |
|---|---|
| `FAP_clean_annotation.rds` | 1.76 GB |
| `EC_pericyte_exercise_clean_annotated.rds` | 861 MB |
| `Immune_exercise_clean_umap.rds` | 832 MB |
| `MuSC_exercise_clean_dele_cluster_umap.rds` | **662 MB（本次触发项）** |
| `ANKRD1_exercise_reannalyse_umap.rds` | 581 MB |
| `GALNTL6_exercise_reannalyse_umap.rds` | 483 MB |

⇒ 该项目的正确做法不是"这次补一个 MuSC 的标记"，而是**一次把 ≥100MB 的项全部 `mark`**，
形成清单；下次换文件名（Users 常逐个调用不同细胞类型）就不再重漏。

## 4. 判别与成本口径（why 阈值是 100MB 而不是更低）

- 600MB 的 MuSC **整套"读盘 + 画 2 张图"实测 0.78 min** → 单次重读 ≈ 40 秒，
  **不值得为它单独建常驻会话**；所以阈值下"不打扰用户"是对的。
- 真正贵的是**反复调版式 / 长链多步**（每次重读 0.6–1.8 GB）。→ 这类走铁规 9
  （一个作业跑完整链 + 精简缓存），而不是靠"再多读几次"。
- 精简缓存只留 `reductions + meta`（≈ 原文件 5%）；
  **需要重算表达量的下游步骤仍须回原文件**——这是固有边界，不是 bug。

## 5. 复查用只读命令（一次跑完，别分多轮 → 铁规 6）

```bash
# 体积 + 同目录清单 + 标记账本，一条命令
stat -c '%s|%y|%n' <绝对路径>
ls -la --time-style=long-iso <同目录> | head -20
ls -la ~/memomics_jobs/            # 无 marker 目录 = 没落标记
```

本机侧查标记：`python -m memomics.bio_tools.large_cache list`（读本机 marker 目录，
不要指望在集群 `~/memomics_jobs/` 下看到 marker —— 标记落在**本机**会话侧）。