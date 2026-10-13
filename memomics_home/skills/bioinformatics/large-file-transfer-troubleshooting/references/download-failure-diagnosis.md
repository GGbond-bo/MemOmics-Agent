# 云端批次下载失败 —— 实测证据链与排查记录

> 场景：从 DCS Cloud `/Files/Monica/snRNAseq/annotated_objects/` 下载一个 **9.38 GB 单文件**
> `.rds` 到本机 `E:\zhangxiao`，面板报：
>
> ```
> ✗ 失败
> 0 B / 9.4 GB
> 0% · 用时 1s · → E:\zhangxiao
> 提交批次下载任务失败
> 提示：Fix failed items and resubmit
> ```

---

## 1. 症状解析：先定阶段

| 信号 | 读法 |
|---|---|
| `用时 1s` | 任务**根本没跑起来** |
| `0 B` 已传 | 一个字节都没走 |
| `0%` | 无进度记录 |
| `提交批次下载任务失败` | 失败点在**提交/建单**，不在传输 |
| `Fix failed items and resubmit` | 平台把该文件标成了 **failed item**，要求先修再重投 |

⇒ 结论：**不要查网络**。方向是「提交前的校验」与「建单参数（通道/体积）」。

---

## 2. 三源取证实测结果

| # | 检查项 | 工具动作 | 实测值 | 判定 |
|---|---|---|---|---|
| ① | 云上文件是否存在 | `dcs_cloud(action="ls", path="/Files/Monica/snRNAseq/annotated_objects", long=True)` | `20261008_PFC_substates_mapped.rds` = **10,069,730,145 B**（9.38 GB）`entity_id=NB2026100814382497165083` | ✅ 存在；**单文件**（非目录） |
| ② | 凭据 | `dcs_cloud(action="context")` | `current_user=zhangbo11`，PAT `expires_at=2026-11-09` | ✅ 未过期 |
| ③ | 项目欠费 | 同上 | `P24Z10200N1046` `is_arrears=false`（当前项目） | ✅ 不欠费 |
| ④ | 默认下载目录 | 同上 | `download_dir = E:\zhangxiao` | ✅ 与报错里的目标一致 |
| ⑤ | **本地目标文件** | `read_file("E:\\zhangxiao\\20261008_PFC_substates_mapped.rds", limit=1)` | **`file_size: 0`** | ❌ **0 字节空壳残留** |
| ⑥ | **本地残件** | `read_file("...\\20261008_PFC_substates_mapped.rds.crswap", limit=1)` | **`file_size: 1,528,815,307`**（1.53 GB），`total_lines: 2,524,397` | ❌ **未提交的写入残件** |

> 注意 ⑤ 与 ⑥ 的矛盾：目标文件 0 字节，交换文件却有 1.53 GB。
> 这正是 File System Access API 的**未收尾**状态 —— 数据还在 `.crswap` 里，从未改名成正式文件。
> 同时提示：UI 的 `0 B / 0%` 计数器**不跟随浏览器端写入**，不能拿它判断"有没有传过"。

---

## 3. 根因（两条，叠加）

### 根因 A：目标端残留 → 平台条目预校验拒绝（最直接）

- 目标路径已存在**同名 0 字节文件** → "已存在但无效"的条目 → 判 `failed items`
  → 平台回「Fix failed items and resubmit」。
- 旁边 **1.53 GB 的 `.crswap`** 是同一件事的物证：
  面板这条下载走的是 **Chromium File System Access API 浏览器端流式直写**
  （用户通过目录选择器选定本地目录），流未正常 `close()` 就中断 → 残件留在磁盘。
- 平台**不会自动覆盖**，只会把该条目标失败。

### 根因 B：单文件体积超通道上限（叠加因素）

- 9.38 GB **单文件**；`web` 通道下载上限约 **200 MB**，且不支持文件夹 / FastQ / BAM。
- 1 秒即失败、0 字节传输，与"通道侧直接拒绝建单"吻合。
- ⇒ 大文件必须走 **`oss` / `raysync`** 通道。

---

## 4. 修复方案（已向用户弹窗确认）

```
1) 删除 E:\zhangxiao\20261008_PFC_substates_mapped.rds        ← 0 字节空壳
2) 删除 E:\zhangxiao\20261008_PFC_substates_mapped.rds.crswap ← 1.53 GB 残件
3) 核查 E: 盘剩余空间 ≥ 9.4 GB ×1.2 ≈ 12 GB
4) 改用 oss 通道重投（不要再用 web）
5) 后台跑 + notify_on_complete；重投后用 read_file.file_size 复核进度
```

给出的勾选方案（单选）：清理残件+换 oss 通道 / 只清理后原通道重试一次 /
只清理不下载（用户自己去面板重试） / 换成按细胞类型拆分的小文件。

---

## 5. 同目录参考：可作替代的较小文件

同目录 `/Files/Monica/snRNAseq/annotated_objects/` 共 9 个 `.rds`，体积跨度很大，
当整包过大时可作为"换更小文件"的候选：

| 文件 | 大小 |
|---|---|
| `20260914_combined_endo_An.rds` | 990,920,960 B（0.92 GB） |
| `20260914_combined_opc_An.rds` | 1,302,850,144 B（1.21 GB） |
| `HC_neuron_annotated.rds` | 1,440,779,821 B（1.34 GB） |
| `20260924_combined_micro_An.rds` | 2,258,451,516 B（2.10 GB） |
| `20260914_combined_asto_An_ZX.rds` | 3,095,941,303 B（2.88 GB） |
| `20260914_combined_oligo_An.rds` | 9,594,878,712 B（8.94 GB） |
| `20261008_PFC_substates_mapped.rds` | 10,069,730,145 B（9.38 GB）← 本次失败 |
| `20260922_PFC_neurons_subcluster_An.rds` | 10,106,818,433 B（9.41 GB） |
| `20261010_HC_substates_mapped.rds` | 11,736,658,547 B（10.93 GB） |

---

## 6. 可复用的判据（沉淀）

1. **`用时 1s` + `0 B` ⇒ 提交阶段失败**：不查网络、不查限速、不找运行日志（任务没跑）。
2. **提交阶段失败第一条先看目标端残留**：0 字节同名文件 / `.crswap`。
3. **`.crswap` = 浏览器端流式写入未收尾的物证**，必须单独删除（不是目标文件的别名）。
4. **UI 的字节计数可能不跟随浏览器端写入** ⇒ 以 `read_file.file_size` 实测为准。
5. **免 shell 取证**：`read_file(path, limit=1)` 返回 `file_size` / `is_binary`，
   对二进制同样有效 —— shell 不可用也能定因。
6. **> 200MB 单文件不用 web 通道**；修复前先量目标盘剩余空间。