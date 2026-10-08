# 写脚本 & 装包两类平台坑（2026-10-04 实测）

> 本文是 `platform-execution-pitfalls` 的补充。该 SKILL.md 已达 ~101 KB（超 100k 上限，
> 需要拆分成 references/），新坑一律先落这里，等 SKILL.md 瘦身后再收编。

---

## 坑 A：中文文案写进 Python 源码 → ASCII 引号引发 SyntaxError

**现象**

`write_file` 落脚本时 lint 报：

```
SyntaxError: invalid syntax. Perhaps you forgot a comma? (line N, column 4)
```

指向的那行**看着完全正常**，逗号也都在。重看两遍还是没问题。

**根因**

中文句子里嵌了 ASCII 双引号，把外层双引号字符串**提前闭合**了：

```python
tb(s, 0.8, 6.4, 11.7, 0.3,
   "知识资产也都是"临时"的，不带证据门槛。", size=12.5)   # ← 字符串在这里断掉
```

Python 看到的是 `"知识资产也都是"` 紧跟 `临时` 标识符 → 报"是不是忘了逗号"。

**规避**

中文文案里的引号一律用中文引号「」『』（或把外层引号换成单引号）：

```python
   "知识资产也都是「临时」的，不带证据门槛。", size=12.5)
```

**通用规则**

1. 凡 `write_file` 写**含中文的 .py / .R 脚本**，落盘后**第一件事看 lint 返回**。
2. 报 `forgot a comma?` / `invalid syntax` 且目标行肉眼正常时，**第一反应就是
   "这行里有没有 ASCII 引号断了字符串"**——不要反复重写同一行。
3. 同一坑也会出现在 f-string、docstring、SQL 字符串里（中文注释里带 `"` 同样炸）。
4. 这条不限于 deck 脚本：任何"中文内容 + Python 生成器"的交付物构建脚本都适用
   （HTML 报告、DOCX、PPTX、图表脚本）。

**为什么值得单独记**：中文长句里带引号极常见（引用用户原话、术语强调、条件值），
而报错信息完全不提示真正原因，容易在同一行上反复徒劳重写。

---

## 坑 B：check_env 装的包，持久内核里 import 不到

**现象**

```
check_env(packages=["pptx"])        → {"installed_now": {"pptx": "Python"}}
execute_python: from pptx import Presentation
                                    → ModuleNotFoundError: No module named 'pptx'
```

check_env 明确说装好了，内核里就是找不到。

**根因**

`check_env` 的**安装目标 ≠ 持久内核所在的解释器**。
持久内核实际使用的解释器是项目 venv（本机实测
`E:\MemOmics-Agent\.venv\Scripts\python.exe`），而 check_env 可能装到了另一个 Python
（系统 Python / 另一个 venv / conda env）。两者 site-packages 互不可见。

**规避（三步，别跳第一步）**

```python
# ① 在内核里先问清楚"我是谁"——不要猜
import sys, sysconfig
print(sys.executable)                       # 持久内核的解释器
print(sysconfig.get_paths()["purelib"])     # 它真正读的 site-packages
```

```bash
# ② 把包装进"这个"解释器
#    铁律 29：装进项目内 venv，禁止 pip install --user、禁止装系统 Python
cd /e/MemOmics-Agent && ./.venv/Scripts/python.exe -m pip install python-pptx
```

```python
# ③ 回内核复验
import pptx; print("OK", pptx.__version__)
```

**推广**

- 任何「第三方包 + 要在 `execute_python` / `execute_r` 里跑」的组合，都先对齐解释器。
- **不要只凭 check_env 的 "installed" 就开写代码**——check_env 过了不代表内核能用。
- R 侧同理：先 `print(R.home())`、`print(.libPaths())` 确认内核实际读哪个库目录，
  再决定 `install.packages(lib=...)` 的落点。
- 装完包环境指纹变了，下次 `env_inventory(action="verify")` 会自动发现并刷新清单，
  不需要手工重扫。

**与铁律 29 的关系**

铁律 29 管"缺包时要不要装、装到哪（项目内）"；本坑补的是它没写的那半截——
**"check_env 报已安装"不等于"内核里可用"**，仍需按上面的三步复核一次。