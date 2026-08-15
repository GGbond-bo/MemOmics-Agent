# -*- coding: utf-8 -*-
"""tar.gz 权限修正（批O5 2026-08-16）。

Windows 上 tar -czf 打包的文件全是 0666 → Linux 解压后 ./start.sh 报 Permission denied。
本脚本重写 tar.gz，把 *.sh（含 start.sh）权限改为 0755，其余保持 0644，
保证 Linux/macOS/Cluster 包解压后 ./start.sh 直接可用。

用法: python scripts/fix_tar_modes.py <pkg.tar.gz>
"""
import io
import os
import sys
import tarfile


def fix(path: str) -> int:
    if not os.path.isfile(path):
        print(f"[fix_tar_modes] {path} 不存在")
        return 1
    tmp = path + ".tmp"
    changed = 0
    try:
        with tarfile.open(path, "r:gz") as src, tarfile.open(tmp, "w:gz") as dst:
            for member in src:
                f = src.extractfile(member)
                data = f.read() if f else b""
                if member.name.endswith(".sh") and member.mode != 0o755:
                    member.mode = 0o755
                    changed += 1
                elif member.mode == 0:
                    member.mode = 0o755 if member.isdir() else 0o644
                dst.addfile(member, io.BytesIO(data))
    except Exception as e:
        print(f"[fix_tar_modes] 失败: {e}")
        if os.path.isfile(tmp):
            os.remove(tmp)
        return 1
    os.replace(tmp, path)
    print(f"[fix_tar_modes] {os.path.basename(path)}: {changed} 个 .sh 已设为 0755")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/fix_tar_modes.py <pkg.tar.gz>")
        sys.exit(1)
    sys.exit(fix(sys.argv[1]))
