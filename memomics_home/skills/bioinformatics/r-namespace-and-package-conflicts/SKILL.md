---
name: r-namespace-and-package-conflicts
description: "R/Bioconductor 包之间的命名空间冲突与遮蔽诊断 —— S4 泛型抢走同名函数（unable to find an inherited method）、library 顺序导致的 masked、多 R 版本 PATH 打架导致 DLL LoadLibrary 失败。触发：unable to find an inherited method / masked from 'package:xxx' / 明明装了包却 could not find function / 两个 R 版本 / LoadLibrary failure / 换环境就崩。"
when_to_use: "R 脚本报『函数找不到』『没有继承方法』但包确实装了时；同一份代码换个会话/换台机器就崩时；机器上装了多个 R 版本时。先查本 skill 再动手重装/换环境。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  memomics:
    tags: [r, namespace, masking, s4-generic, bioconductor, dependency-conflict, troubleshooting]
    difficulty: intermediate
    language: R
    category: bioinformatics
---

# R 命名空间与包冲突诊断

> **核心判据：如果「明明装了包」却报函数找不到，先怀疑遮蔽，不要先怀疑环境。**
> 装包/换环境/换 R 版本是**最后**手段，不是第一反应 —— 它们会抹掉证据、浪费一轮长作业。

## 🔴 决策树

```
R 报错：函数/方法找不到
  ├─ "unable to find an inherited method for function 'X' for signature 'object = \"Y\"'"
  │   → Case 1：S4 泛型遮蔽（本文件最重要的一条）
  ├─ library() 打印 "The following object is masked from 'package:xxx'"
  │   → Case 2：普通函数遮蔽（同源，修法相同）
  ├─ "could not find function" 但 requireNamespace()=TRUE
  │   → Case 1/2 二选一（先跑诊断三连）
  ├─ LoadLibrary failure / DLL 加载失败 / 两个 R 版本
  │   → Case 3：多 R 版本 PATH 打架
  └─ 其他
      → 才考虑缺包（check_env）/ 版本不匹配（sessionInfo()）
```

---

## Case 1：S4 泛型遮蔽 —— 最阴的一类（2026-10-09 实测）

### 症状

```r
Error: unable to find an inherited method for function 'cpm' for signature 'object = "DGEList"'
```

**它长得像"包没装/版本不对"，其实都不是。** 一旦看到 `for signature 'object = "..."'` 这个尾巴，
基本可以锁定是 S4 泛型问题。

### 根因

某包把该名字定义成 **S4 泛型**，于是裸调用走 S4 dispatch；而**这个泛型没有你那个类的方法**
→ dispatch 直接失败。

实测实例（R 4.4.1 + Seurat + edgeR + RUVSeq + MAST）：

| 环节 | 事实 |
|---|---|
| 谁遮蔽了谁 | `MAST` 载入的 `SingleCellExperiment` 定义了 S4 泛型 `cpm`，劫持了 `edgeR::cpm()` |
| 为什么必崩 | SCE 的泛型只有 SCE 方法，**没有 `DGEList` 方法** |
| 崩在哪 | 脚本第一次调用 `cpm(d_e)`（`d_e` 是 `DGEList`）→ 整脚本 `Execution halted` |
| 改了几行 | **1 行**：`cpm(d_e)` → `edgeR::cpm(d_e)` |

### 诊断四连（先确诊，别乱改）

```r
find("cpm")                                          # ① 搜索路径上谁在提供这个名字
methods::isGeneric("cpm")                            # ② 是不是 S4 泛型（TRUE = 被泛型劫持）
"cpm" %in% conflicts(detail = TRUE)$`package:edgeR`  # ③ 原包是否被遮蔽
edgeR::cpm(dge)                                      # ④ 显式命名空间调用是否正常（实测 3x4 OK）
```

**判读**：④ 正常 + 裸调用报错 = **确诊遮蔽**。
→ 此时**不要**卸包、装包、换环境、换 R 版本；那些都是错误归因。

### 修法

1. **只改调用点**，逻辑零变化：`cpm(d_e)` → `edgeR::cpm(d_e)`。
2. **一次排查完同批代码**（只修一个函数会一路崩，浪费一整轮长作业）：
   对同批里所有可疑的裸调用逐个跑 `find("X")` / `isGeneric("X")`。
   ⚠️ **别假设"挨着的函数也脏"** —— 实测本轮只有 `cpm` 一个被劫持，
   `calcNormFactors` / `glmFit` / `estimateGLMCommonDisp` / `estimateGLMTagwiseDisp` / `DGEList` 全干净。
3. **长期纪律**：跨 Bioconductor 包混用（Seurat + edgeR + RUVSeq + MAST + SingleCellExperiment 之类）时，
   对**通用短名函数**（`cpm` / `counts` / `assay` / `colData` / `normalize`）一律写 `pkg::fun()`。
   显式前缀**不依赖 `library()` 顺序**、可复现，是唯一稳的写法。
4. 改完**先跑冒烟版**（只跑第一个迭代单元）确认那处正是崩点，再放全量。

### ⚠️ 为什么"之前明明能跑"

**遮蔽取决于 `library()` 顺序与当时载入了哪些包**，不是代码"变坏"了。
之前的 notebook 没同时载入 `SingleCellExperiment` 的泛型 → 侥幸通过。
所以正确说法是「**老代码一直带着这个隐患，这次撞上了**」，
而不是「可能版本不同」——**后者是错的归因**，用户会追问。

---

## Case 2：普通函数遮蔽

`library()` 输出里的这段**不要忽略**：

```
The following object is masked from 'package:edgeR':
    cpm
```

修法与 Case 1 相同（显式 `pkg::fun`），诊断用 `find("X")` + `conflicts()`。
**纪律**：脚本里看到 `masked from` 警告，就把被遮蔽的那个函数改成显式前缀 —— 当场 1 行，别等崩。

---

## Case 3：多 R 版本 PATH 打架 → DLL LoadLibrary 失败

### 症状

`LoadLibrary failure` / 加载包时 DLL 报错 / 同一个包在一处能载入、另一处不能。
**根因**：机器上有多个 R 版本，`PATH` 里排前面的不是你要的那个（或与包编译时用的 R 不匹配）。

### 判据与修法

1. 先看**到底在用哪个 R**：`Rscript -e 'print(R.version.string); print(.libPaths())'`
   —— 别假定 PATH 里的 `Rscript` 就是你想要的那个版本。
2. **用绝对路径调用目标 R**，不依赖 PATH：
   ```bash
   "C:/Program Files/R/R-4.5.3/bin/x64/Rscript.exe" script.R      # Windows 示例
   /path/to/envs/R4.41/bin/Rscript script.R                        # conda env 示例
   ```
   并在作业脚本里**显式指定解释器**（集群侧同见 `remote-cluster-execution` 铁规 2）。
3. 包的编译版本必须与 R 版本匹配：`R 4.5.3` 的库不能用 `Rtools45` 之外的工具链编
   （实测唯一可编译组合可能是更早的 R + 对应 Rtools；**先确认工具链版本再决定用哪个 R**）。
4. 版本不匹配且无法重编 → 换用**已编译好该包的那个 R 版本**，而不是硬编。

---

## 汇报要求（用户会验证归因）

出这类问题时，必须把三件事讲清：

1. **性质**：这不是环境问题、也不是代码写错了，是**包之间的命名空间冲突**（Case 1/2）
   或**多版本解释器打架**（Case 3）。
2. **证据**：贴诊断命令的**实际输出**（`find()` / `isGeneric()` / `R.version.string`），不要只给结论。
3. **改动面**：明确说"只改了 N 行"，并列出**没动**的地方 —— 用户按最小改动验收。

⛔ 不要把「之前能跑」解释成「版本不同/环境变了」——那是错的归因，且会让人去重装包。
⛔ 不要在没跑 `find()` / `isGeneric()` 的情况下说"应该是包冲突"——本 skill 存在的意义就是**先确诊**。

## 复核脚本

`scripts/diagnose_masking.R` —— 传函数名 + 原包名，一次输出 `find` / `isGeneric` / `conflicts` /
显式调用四项事实，用于确诊与汇报取证。

## 相关

- 集群上跑 R 时的解释器/环境纪律 → `remote-cluster-execution`（铁规 2：作业脚本必须显式定义解释器）
- 平台侧 pre-review 的包口径（本地缺 ≠ 集群缺）→ `remote-cluster-execution` 铁规 3.1