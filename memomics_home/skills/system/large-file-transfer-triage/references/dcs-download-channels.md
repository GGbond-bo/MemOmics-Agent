# 平台传输通道枚举与错误码（DCS Cloud 实测，2026-10-12）

## 1. 合法下载类型（平台侧硬约束）

用 `type="<通道>"` 调用下载时，平台只接受这几个值（错误提示逐字原文）：

```
下载类型不合法
detail.business_code: 1204
hint: 请使用 web、raysync、ossutil、tosutil、obsutil、aws 或 mount
```

→ 合法枚举 = **`web / raysync / ossutil / tosutil / obsutil / aws / mount`**
→ ⚠️ **没有裸 `oss`**。历史笔记里写的「大文件换 `oss`」是**错的**，传 `type="oss"` 一定被 1204 拒。
   要换通道就从上面 7 个里挑，首选 `raysync`（大文件高速），其次 `ossutil`。

## 2. 各通道适用与实测结果

| 通道 | 适用 | 实测（本项目 P24Z10200N1046 / BGI-时空） |
|---|---|---|
| `web` | 小文件，**单文件下载上限约 200 MB**（上传约 100 MB）；不支持文件夹 / FastQ / BAM | 945 MB 建单即判 failed item |
| `raysync` | 大文件高速传输 | ❌ `404 数据模块未知错误`，`business_code: 10099`，`api_msg: 未找到` |
| `ossutil` / `tosutil` / `obsutil` | 需要相应 CLI 客户端的对象存储通道 | 未实测；`raysync` 不通时可试 |
| `aws` / `mount` | 对象存储 / 挂载 | 未实测 |

**解读**：通道是否可用是**账号/项目级开通状态**，不是参数写对就能用。
`raysync` 返 404/10099 = **该通道在你的项目/区域没开通**，属于平台侧配置，Agent 改不了。

## 3. 失败记录的几个字段怎么读

一条 `✗ 失败 · 0 B / 945.0 MB · 0% · 用时 0.5s · → E:\zhangxiao · 提交批次下载任务失败 / Fix failed items and resubmit`：

| 字段 | 含义 |
|---|---|
| `0 B` + `0%` + `用时 <1s` | **提交阶段就被拒**，一个字节都没传 → 不是断线 |
| `945.0 MB` | 平台侧的**源文件体积**；拿它去和云上 `ls` 的真实 size **逐字节对照**（吻合 = 源文件没问题） |
| `Fix failed items and resubmit` | 平台把该条目判成 failed item；常见前置校验：通道超限、目标路径条目冲突（0 字节同名空壳） |
| `→ E:\zhangxiao` | 目标目录；**必须 `ls -la` 看这个目录里有什么**（空壳 / `.crswap`） |

## 4. 绕过通道限制的唯一现实路径

**浏览器手动下载**：用户在 DCS 网页里直接下，实测 **9.4 GB 成功**（走 Chromium File System Access
流式写入，目标目录会出现持续增长的 `<名>.crswap`，写完原子改名为目标文件）。
→ 通道没开通（raysync/ossutil 都不通）时，这就是可行路径，明确推荐给用户，别承诺平台侧能开通。