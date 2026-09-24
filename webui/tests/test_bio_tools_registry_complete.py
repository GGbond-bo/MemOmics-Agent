# -*- coding: utf-8 -*-
"""bio_tools 自注册模块必须被包 __init__ 导入（2026-09-24 真机事故回归）。

事故现场（真机会话 memomics-8c18d732 / 条目 13-gsea / 2026-09-24 18:13）：
  SOUL.md 铁律 28/35 要求「开工前用 ask_user 弹意图确认表单」，门禁也反复提示
  「⛔ 开工前意图没确认」，但模型自己的推理里写得明明白白：
      「工具列表里没有 ask_user」「工具列表里确实没有 ask_user」「它不在我的工具清单」
  原因：模型看到的工具来自 hermes-agent/model_tools.py 的 from memomics import bio_tools，
  而 memomics/bio_tools/__init__.py 只导入了 27 个子模块，漏了 3 个自注册模块：
      ask_user（澄清/意图确认）、evidence_table（证据表写+查）、prisma_flow（PRISMA 流程）
  工具没注册 → 模型看不到 → 铁律要求的能力事实上不可用，agent 只能猜着做
  （同一会话随后未经用户同意自行 install.packages("fgsea")，撞了铁律 29）。

锁死的契约：
  1. memomics/bio_tools/ 下任何调用 registry.register(...) 的模块，都必须在
     __init__.py 里被显式导入，否则模型看不到这个工具；
  2. 真的 import memomics.bio_tools 之后，ask_user / evidence_write /
     evidence_query / prisma_flow 必须出现在 tools.registry 里；
  3. 这三种能力属于「用户交互 + 证据链」，缺一个都不是「少个工具」这么简单：
     ask_user 缺了 = 意图确认流程整体失效。
"""
import ast
import json
import os
import subprocess
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_BIO = os.path.join(_ROOT, "memomics", "bio_tools")
_INIT = os.path.join(_BIO, "__init__.py")
_HERMES = os.path.join(_ROOT, "hermes-agent")

# 事故里被漏掉的那三个（真源：各自模块内的 registry.register(name=...)）
_MUST_BE_REGISTERED = ("ask_user", "evidence_write", "evidence_query", "prisma_flow")


def _self_registering_modules():
    """返回 bio_tools 下会注册工具的模块名（函数内注册 + 顶层调用）。"""
    out = []
    for fn in sorted(os.listdir(_BIO)):
        if not fn.endswith(".py") or fn == "__init__.py":
            continue
        path = os.path.join(_BIO, fn)
        with open(path, encoding="utf-8", errors="replace") as f:
            src = f.read()
        if "registry.register(" not in src:
            continue
        try:
            tree = ast.parse(src, filename=path)
        except SyntaxError:
            continue
        called = any(
            isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
            and stmt.value.func.id.startswith("_register")
            for stmt in tree.body
        )
        if called:
            out.append(fn[:-3])
    return out


def _imported_in_init():
    with open(_INIT, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            for alias in node.names:
                names.add(alias.name)
    return names


def test_every_self_registering_module_is_imported_by_init():
    """任何自注册模块漏在 __init__ 外 → 模型看不到这个工具（事故根因）。"""
    modules = set(_self_registering_modules())
    imported = _imported_in_init()
    missing = sorted(modules - imported)
    assert not missing, (
        "这些 bio_tools 模块会注册工具，但 memomics/bio_tools/__init__.py 没导入它们，"
        "模型工具列表里不会有它们：%s" % missing
    )


def test_init_only_imports_existing_modules():
    """反向检查：__init__ 里别写错模块名（写错会 ImportError 拖垮整个包）。"""
    imported = _imported_in_init()
    on_disk = {fn[:-3] for fn in os.listdir(_BIO) if fn.endswith(".py") and fn != "__init__.py"}
    ghost = sorted(imported - on_disk)
    assert not ghost, "__init__.py 导入了不存在的模块：%s" % ghost


def test_registry_really_contains_the_tools_after_package_import():
    """真跑一遍 import（独立子进程，避免污染 pytest 进程）后查 registry。"""
    code = (
        "import json, sys\n"
        "sys.path.insert(0, %r)\n"
        "sys.path.insert(0, %r)\n"
        "import memomics.bio_tools\n"
        "from tools.registry import registry\n"
        "print(json.dumps(sorted(registry.get_tool_names_for_toolset('memomics'))))\n"
    ) % (_ROOT, _HERMES)
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300, cwd=_ROOT)
    assert proc.returncode == 0, "import memomics.bio_tools 失败：%s" % (proc.stderr or "")[-800:]
    names = json.loads((proc.stdout or "").strip().splitlines()[-1])
    for tool in _MUST_BE_REGISTERED:
        assert tool in names, (
            "工具 %s 没注册进 registry（模型看不到它）—— 现有 memomics 工具 %d 个：%s"
            % (tool, len(names), names)
        )


def test_package_import_is_robust():
    """单个模块注册失败不能把整包带崩（各模块 _register 自己吞异常）。"""
    code = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "sys.path.insert(0, %r)\n"
        "import memomics.bio_tools as b\n"
        "print('OK', len([n for n in dir(b) if not n.startswith('_')]))\n"
    ) % (_ROOT, _HERMES)
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300, cwd=_ROOT)
    assert proc.returncode == 0, (proc.stderr or "")[-800:]
    assert "OK" in (proc.stdout or "")
