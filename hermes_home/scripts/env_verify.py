"""
MemOmics 环境验证器
每次 Agent 启动时运行，确保所有工具路径有效。
路径不存在 → 重新发现 → 更新 environment.json → 实在没有 → 提示安装命令。
"""

import json
import os
import sys
import shutil
import subprocess
from datetime import datetime

ENV_PATH = "E:/MemOmics-Agent/hermes_home/environment.json"

def load_env():
    """加载环境文件"""
    if not os.path.exists(ENV_PATH):
        return {"tools": {}, "version": "1.0", "updated_at": str(datetime.now())}
    with open(ENV_PATH) as f:
        return json.load(f)

def save_env(data):
    """保存环境文件"""
    data["updated_at"] = str(datetime.now())
    with open(ENV_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def discover_python():
    """发现 Python 路径"""
    paths = {}
    # 系统 Python (CellBender 宿主)
    candidates = [
        r"C:\Users\23136\AppData\Local\Programs\Python\Python312\python.exe",
        r"C:\Users\23136\AppData\Local\Programs\Python\Python311\python.exe",
        r"C:\Python312\python.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            paths["python"] = c
            break
    if "python" not in paths:
        paths["python"] = sys.executable
    
    # venv Python
    venv_candidates = [
        r"E:\MemOmics-Agent\.venv\Scripts\python.exe",
    ]
    for c in venv_candidates:
        if os.path.exists(c):
            paths["python_venv"] = c
            break
    
    return paths

def discover_tool(name, exe_name, python_path, pip_package=None):
    """发现工具路径"""
    # 1. shutil.which
    path = shutil.which(exe_name)
    if path and os.path.exists(path):
        return path
    
    # 2. 推测 Scripts 目录
    if python_path:
        scripts_dir = os.path.join(os.path.dirname(python_path), "Scripts")
        candidate = os.path.join(scripts_dir, exe_name + ".exe" if sys.platform == "win32" else exe_name)
        if os.path.exists(candidate):
            return candidate
    
    # 3. pip show 查找
    pip_pkg = pip_package or name
    try:
        result = subprocess.run(
            [python_path, "-m", "pip", "show", pip_pkg],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.split("\n"):
            if line.startswith("Location:"):
                loc = line.split(":",1)[1].strip()
                candidate = os.path.join(loc, "..", "..", "Scripts", exe_name + ".exe")
                candidate = os.path.normpath(candidate)
                if os.path.exists(candidate):
                    return candidate
    except:
        pass
    
    return None

def verify_and_repair():
    """主函数：验证所有工具，缺失的重新发现"""
    env = load_env()
    tools = env.get("tools", {})
    
    repairs_needed = []
    missing = []
    
    # 检查每个工具
    for name, info in tools.items():
        if not isinstance(info, dict):
            continue
        path = info.get("path")
        if path and os.path.exists(path):
            print(f"  ✅ {name}: {path}")
            info["verified"] = True
        else:
            print(f"  ⚠️ {name}: 路径失效 ({path})")
            info["verified"] = False
            missing.append(name)
    
    # 重新发现缺失的工具
    if missing:
        print(f"\n🔍 重新发现 {len(missing)} 个工具...")
        
        py_path = tools.get("python", {}).get("path", sys.executable)
        
        discovery_map = {
            "cellbender": ("cellbender.exe", "cellbender"),
            "ptrepack": ("ptrepack.exe", "tables"),
        }
        
        for name in missing:
            if name in discovery_map:
                exe, pkg = discovery_map[name]
                new_path = discover_tool(name, exe, py_path, pkg)
                if new_path:
                    tools[name]["path"] = new_path
                    tools[name]["verified"] = True
                    repairs_needed.append((name, new_path))
                    print(f"    ✅ {name} 重新发现: {new_path}")
                else:
                    print(f"    ❌ {name} 无法自动发现，需要手动安装")
                    # 保留 install_commands
                    cmd = env.get("install_commands", {}).get(name, f"pip install {pkg}")
                    print(f"       安装命令: {cmd}")
    
    env["tools"] = tools
    save_env(env)
    
    # 汇总
    total = len([t for t in tools.values() if isinstance(t, dict)])
    verified = len([t for t in tools.values() if isinstance(t, dict) and t.get("verified")])
    
    print(f"\n📊 环境验证完成: {verified}/{total} 工具就绪")
    
    if repairs_needed:
        print(f"🔧 自动修复: {len(repairs_needed)} 个")
    
    still_missing = len([t for t in tools.values() if isinstance(t, dict) and not t.get("verified")])
    if still_missing:
        print(f"⚠️ {still_missing} 个工具仍不可用，运行前需要安装")
    
    return {
        "verified": verified,
        "total": total,
        "missing": still_missing,
        "repaired": len(repairs_needed)
    }

if __name__ == "__main__":
    print("=" * 60)
    print("MemOmics Environment Validator")
    print("=" * 60)
    result = verify_and_repair()
    print("=" * 60)
