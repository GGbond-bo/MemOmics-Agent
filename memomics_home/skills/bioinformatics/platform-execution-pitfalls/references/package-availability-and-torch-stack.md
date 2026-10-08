# 包可用性判定 与 torch/torchvision 栈修复

来源：2026-09-24 会话（在 execute_python 内核里跑 scvi-tools）。

## 一、「这个包到底装没装」——三个数据源，只有一个算数

| 数据源 | 它查的是什么 | 可信度 |
|---|---|---|
| `check_env(packages=[...])` | 它自己那套探测清单 | ⚠️ **会误报**：可能返回 `installed` / `installed_now`，而执行层根本 import 不到 |
| **execute 内核里的实测 `import`** | 真正要跑代码的那个解释器 | ✅ **唯一权威判据** |
| `rail_review(pre)` 的 `Missing packages` | 它自己那套解释器（不看 lib_user / 系统 Python312 的 site-packages） | ⚠️ 反向也会误报（真装了却报缺） |

**实测冲突案例**：`check_env(packages=["scvi-tools","scikit-learn","umap-learn"])` 返回
`installed` + 同批 `installed_now`，紧接着内核里 `import scvi` → **`ModuleNotFoundError: No module named 'scvi'`**。
同时 `rail_review(pre, required_packages=[...])` 报 `Missing packages: scvi-tools, scikit-learn, umap-learn`
并**硬阻断所有执行类工具**（连只读 terminal 一起被拦）。

⇒ 处置顺序：
1. **先在内核里实测**：`import sys; print(sys.executable)` + 逐个 `importlib.util.find_spec("<pkg>")`
   —— 一次调用打印「解释器路径 + 每个包 OK/MISS」。
2. **以该解释器为准装包**（`<sys.executable> -m pip install ...`），不是以 `check_env` 的回执为准。
3. `rail_review(pre)` 的 `required_packages` **只列该步真实必需、且审查器能解析到的包**；
   拿不准就**不传该参数**（回执立即 `should_proceed=true`，脚本一行不用改）。
   ⚠️ 被拦期间**不要反复重试** execute_* / terminal（会累计「连续拦截 N 次」并触发强制干预）。

### ⚠️ 内核解释器 ≠ environment.json 声明的解释器
`environment.json` 可能声明 execute_python 用 `E:/MemOmics-Agent/.venv/Scripts/python.exe`，
而**内核实测跑的是另一个**（本会话实测为 `C:/Users/<user>/AppData/Local/Programs/Python/Python312/python.exe`）。
⇒ **装包前先 `print(sys.executable)` 确认**，否则会「装到 A、跑在 B」，白忙一轮。
（同族：该环境带 `sitecustomize` 补丁，import 时会先打印一行 `[sitecustomize] torch.save patched v4 …`，属正常噪声。）

---

## 二、torch / torchvision 版本错配：`operator torchvision::nms does not exist`

### 症状与传播链
```
import scvi
  → RuntimeError: operator torchvision::nms does not exist
       File "torch/_library/fake_impl.py", line 50, in register
         if torch._C._dispatch_has_kernel_for_dispatch_key(self.qualname, "Meta"):
```
**看着像 scVI 坏了，其实是 torchvision 自身 import 就崩**，经
`scvi → lightning → torchmetrics → torchvision` 一路带崩。

### 诊断：逐层单独 import，一眼定位
```bash
P="<内核解释器绝对路径>"
"$P" -c "import torch; print(torch.__version__, torch.version.cuda)"   # 先确认 torch 没被动过
"$P" -c "import torchvision; print(torchvision.__version__)"
"$P" -c "import torchmetrics"
"$P" -c "import scvi; print(scvi.__version__)"
"$P" -m pip show torchvision | grep -iE "^(Name|Version|Required-by)"
```

### 修复：按官方配对表装匹配版本
torch ↔ torchvision 必须成对（**0.27 配 torch 2.12；0.26 配 2.11；0.25 配 2.10；0.24 配 2.9**）。
```bash
"$P" -m pip install "torchvision==0.26.0" --index-url https://download.pytorch.org/whl/cu128
```
实测：`torch 2.11.0+cu128` + 把 `torchvision 0.27.0` 降到 `0.26.0+cu128` → `import scvi` 立即成功
（scvi-tools 1.5.1），且 **torch 未被连带改动**、`cuda True` 保持。

### 三条纪律
1. **不要卸载 torchvision 了事** —— 先看 `Required-by`（实测被 `docling-ibm-models` / `spandrel` 依赖），
   卸了会连带打断别的项目。降级到配对版本是正解；同理**不要为了迁就 torchvision 去升 torch**（GPU 环境风险更大）。
2. **改完必须复核 torch 未降级**：`torch.__version__` / `torch.cuda.is_available()`。
3. **`pip install scvi-tools` 本身 exit=0 也可能埋下这个雷** —— 它会把 lightning/torchmetrics 等一并带入，
   而版本错配只在**首次 import** 时暴露。装完立刻 `import scvi` 验证，别等到跑分析才发现。
   若 import 链上确认只有 torchvision 崩且无反向依赖，替代方案是把 torchvision 版本对齐而不是删。

---

## 三、安装类命令的时长纪律
- 包安装 / 长任务：`terminal` foreground **timeout 上限 600s**（传 900 直接被工具拒绝、命令一行没跑）；
  超过就 `background=True` + `notify_on_complete=True`，或把 timeout 压到 600 以内。
- 安装完在同一条命令里接 `import` 验证（`pip install -q ... ; python -c "import X; print(X.__version__)"`），
  省一轮往返、也避免「以为装好了」。