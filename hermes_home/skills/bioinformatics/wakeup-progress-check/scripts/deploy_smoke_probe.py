#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""部署生效性探针 —— 「改了盘上的文件，正在跑的进程是否真的装载了它？」

判据：进程启动时刻 vs 文件 mtime
    进程启动 < 文件 mtime  ⇒ 该进程里跑的是旧代码【需重启】
    进程启动 > 文件 mtime  ⇒ 已装载【无需重启】

用法：
    python deploy_smoke_probe.py --file <被改的文件>                  # 自动枚举 python/Rscript 进程
    python deploy_smoke_probe.py --file <文件> --pids 54408,43864      # 只看指定 PID
    python deploy_smoke_probe.py --file <文件> --names python.exe,Rscript.exe
    python deploy_smoke_probe.py --file <文件> --match-cmdline webui,server.py --port 8899   # ★推荐

⚠️ 进程判据陷阱之一：按镜像名枚举会误报「已装载」（2026-10-01 memomics-afd2d418 实测）
    按**镜像名**枚举（python.exe）会把**瞬时/无关子进程**当成"服务"——它们恰好在
    文件改动**之后**启动 ⇒ 误报「晚于文件 ⇒ 已装载」。实测：两个 python PID 被判"已装载"，
    复跑时已 NoSuchProcess，命令行也根本不是 webui/server.py。
    四条对策（本脚本已内置）：
      ① 用 --match-cmdline 过滤命令行（真实 webui 服务 = 同时含 webui + server.py）
      ② 判定前重查一次 PID 是否仍存在（瞬时进程第二次查就消失 → 剔除而非采信）
      ③ 输出带 cmdline，便于人工核对"它到底是不是那个服务"
      ④ ★排除探针自身及其祖先 PID —— --match-cmdline 的词会写进**探针自己的 argv**，
         内联 `python -c "...'server.py' in cl and 'webui' in cl..."` 同样把字面量放进自身命令行
         ⇒ 探针**匹配到自己**（连同承载它的 bash 父进程），凭空多出若干"候选服务"。
         签名速记：候选的 start 全都等于"探针跑的那一秒钟" ⇒ 自匹配，不是服务。
         （2026-10-01 唤醒 #3 实测：多出 2×python + 3×bash 共 5 个假候选。）
    ⛔ 判「已装载」必须比判「需重启」更严：任何改动后启动的无关进程都会命中「晚于」。

⚠️⚠️ 进程判据陷阱之二（与 ④ 组合出来的假阴性）：祖先排除把「服务本体」一起排掉
    （2026-10-01 唤醒 #9 memomics-afd2d418 实测）
    本探针由 terminal 工具启动 ⇒ 它是 **webui 服务进程的子进程**（链：服务 PID → bash → python 探针）
    ⇒ 服务本体**必然落在探针的祖先链里**，被 ④ 的"排除自身及祖先"整条剔除
    ⇒ 输出退化成 `[WARN] 未发现候选进程 —— 无法判定`，**该报的"需重启"反而看不见**。
    实测排除名单里出现 43864（监听 8899 的真实服务）+ 54408（start.bat 包装壳）。
    → 修复（本脚本已内置「祖先豁免」+ `--port`）：
      ① **祖先豁免**：被判排除的祖先 PID，若 **仍存活 且 启动时刻早于探针 ≥5 秒**（自匹配的假候选
         都诞生于"探针跑的那一秒钟"，长命进程不可能是自匹配），并且 **命令行满足 --match-cmdline
         或 它持有 LISTEN 套接字** → 重新纳入候选、标记 `[祖先豁免]`，拒绝静默丢弃；
      ② **`--port 8899`（最硬判据）**：真实服务 = **监听端口**的那个进程，与祖先链、与命令行文本
         都无关；给出端口时按 `CONN_LISTEN` 建 端口→pid 映射，命中即服务本体（优先于命令行匹配）；
      ③ 两条判据都拿不到（无 psutil / 无端口）时才退回"无法判定"，并**打印被排除/被豁免的 PID**，
         让读者能区分"没找到"还是"找到了但被排除"。
    💡 最稳的调用口径 = `--port <服务端口>` + `--match-cmdline <服务关键字>` 两者都给：
       端口管"认得出服务"，命令行关键字管"没端口时也不误报"。

退出码：0 = 全部已装载；1 = 存在需重启的进程；2 = 参数/环境问题。
配套口径：**没重启就不得声称「改动已生效」**——本探针只回答「需要不需要重启」，
          不回答「代码改对了没」（那由单测/自检脚本回答）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
import time

# Windows FILETIME(100ns, 1601-01-01) → unix 秒的偏移
FILETIME_EPOCH_DELTA = 11644473600


def _unix_to_str(ts: float) -> str:
    try:
        return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:  # noqa: BLE001
        return f"{ts:.0f}"


def _self_and_ancestors() -> set[int]:
    """探针自身 + 其祖先进程的 PID（必须从候选里排除）。

    ⛔ 不排除就会**自匹配**：`--match-cmdline webui,server.py` 这几个词会原样进入
    探针自己的命令行；内联 `python -c "...'server.py' in cl and 'webui' in cl..."` 同理。
    于是探针（以及跑它的 bash）会被当成"候选服务"，而它们的启动时刻 **必然晚于**
    被改文件 ⇒ 直接制造「已装载」假阳性。
    （2026-10-01 memomics-afd2d418 唤醒 #3 实测：多出 2×python + 3×bash 假候选。）

    ⚠️ 但排除必须配「祖先豁免」（见 rescue_ancestor_service）：探针由 terminal 工具启动，
    是 **webui 服务进程的子进程** ⇒ 服务本体会落在祖先链里被误排除
    （2026-10-01 唤醒 #9 实测：43864 被排除 → 输出"未发现候选进程"）。
    """
    pids = {os.getpid()}
    try:
        import psutil  # type: ignore

        for parent in psutil.Process(os.getpid()).parents():
            pids.add(int(parent.pid))
    except Exception:  # noqa: BLE001
        pass
    return pids


def _ancestors() -> list[int]:
    """探针的祖先进程 PID（近→远），不含自身。供「祖先豁免」复核用。"""
    try:
        import psutil  # type: ignore

        return [int(p.pid) for p in psutil.Process(os.getpid()).parents()]
    except Exception:  # noqa: BLE001
        return []


def listen_pids(ports: list[int]) -> dict[int, list[int]]:
    """端口 → 监听它的 PID 列表（CONN_LISTEN）。最硬的服务判据，与祖先链/命令行文本无关。"""
    out: dict[int, list[int]] = {}
    try:
        import psutil  # type: ignore

        for c in psutil.net_connections(kind="inet"):
            if c.status != psutil.CONN_LISTEN or not c.laddr:
                continue
            if c.laddr.port in ports and c.pid:
                out.setdefault(int(c.pid), []).append(int(c.laddr.port))
    except Exception:  # noqa: BLE001
        pass
    return out


def rescue_ancestor_service(ancestors: list[int], terms: tuple[str, ...],
                            port_map: dict[int, list[int]],
                            probe_start: float, min_age: float = 5.0) -> list[tuple[int, str, str, str]]:
    """祖先豁免：把"被排除的祖先里其实是服务本体"的那些捞回来。

    判据（三条同时满足）：
      ① 仍存活；
      ② 启动时刻 **早于探针 ≥ min_age 秒** —— 自匹配的假候选（探针自己 + 承载它的 bash）
         都诞生于"探针跑的那一秒钟"，长命进程不可能是自匹配；
      ③ 命令行满足 --match-cmdline，**或** 它持有 LISTEN 套接字（服务本体特征）。
    返回 (pid, name, cmdline, 豁免理由)。⛔ 不许静默丢弃 —— 静默丢弃会伪装成"没找到"。
    """
    out: list[tuple[int, str, str, str]] = []
    try:
        import psutil  # type: ignore
    except Exception:  # noqa: BLE001
        return out
    for pid in ancestors:
        if pid == os.getpid():
            continue
        started = proc_start_unix(pid)
        if started is None or probe_start - started < min_age:
            continue
        try:
            p = psutil.Process(pid)
            name = p.name()
            cl = " ".join(p.cmdline())
        except Exception:  # noqa: BLE001
            continue
        hit_cmd = bool(terms) and all(t in cl for t in terms)
        hit_port = pid in port_map
        if not (hit_cmd or hit_port):
            continue
        why = ("持有 LISTEN 端口 " + ",".join(map(str, port_map.get(pid, [])))) if hit_port else ""
        if hit_cmd:
            why = (why + " + " if why else "") + "命令行命中 " + ",".join(terms)
        out.append((pid, name, cl, why))
    return out


def list_pids(names: list[str], cmdline_terms: tuple[str, ...] = (),
              exclude: set[int] | None = None) -> list[tuple[int, str, str]]:
    """枚举候选进程 (pid, name, cmdline)。

    cmdline_terms 非空时，只保留命令行**同时包含全部词**的进程——这是判定
    「它到底是不是那个目标服务」的唯一可靠办法（见 docstring 的进程判据陷阱）。
    exclude 中的 PID（探针自身及祖先）一律跳过，避免自匹配假阳性。
    """
    out: list[tuple[int, str, str]] = []
    ex = exclude or set()
    try:
        import psutil  # type: ignore

        want = {n.lower() for n in names}
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            pid = int(p.info["pid"])
            if pid in ex:
                continue
            nm = (p.info.get("name") or "").lower()
            if nm not in want:
                continue
            cl = " ".join(p.info.get("cmdline") or [])
            if cmdline_terms and not all(t in cl for t in cmdline_terms):
                continue
            out.append((pid, p.info.get("name") or nm, cl))
        return out
    except Exception:  # noqa: BLE001
        pass
    if cmdline_terms:
        # 退化路径拿不到命令行 ⇒ 无法过滤。宁可报空，也不退回"按镜像名"而误报「已装载」。
        print("[WARN] 无 psutil，无法按 --match-cmdline 过滤；请改用 --pids 显式指定目标进程")
        return []
    for n in names:
        try:
            raw = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH", "/FI", f"IMAGENAME eq {n}"],
                capture_output=True, text=True, timeout=20,
            ).stdout
        except Exception:  # noqa: BLE001
            continue
        for line in raw.splitlines():
            parts = [x.strip('"') for x in line.split('","')]
            if len(parts) >= 2 and parts[0].lower() == n.lower():
                try:
                    pid = int(parts[1])
                except ValueError:
                    continue
                if pid in ex:
                    continue
                out.append((pid, parts[0], ""))
    return out


def proc_start_unix(pid: int) -> float | None:
    """取进程启动的 unix 秒；取不到返回 None。"""
    try:
        import psutil  # type: ignore

        return float(psutil.Process(pid).create_time())
    except Exception:  # noqa: BLE001
        pass
    try:
        raw = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).StartTime.ToFileTimeUtc()"],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip()
        if not raw:
            return None
        return float(raw) / 1e7 - FILETIME_EPOCH_DELTA
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="部署生效性探针（进程启动时刻 vs 文件 mtime）")
    ap.add_argument("--file", required=True, help="被改动的文件路径")
    ap.add_argument("--pids", default="", help="只看指定 PID，逗号分隔；留空=自动枚举")
    ap.add_argument("--names", default="python.exe,Rscript.exe",
                    help="自动枚举的进程名，逗号分隔")
    ap.add_argument("--match-cmdline", default="",
                    help="命令行必须同时包含这些词（逗号分隔），如 webui,server.py —— "
                         "用于只认真实目标服务，避免瞬时子进程误报「已装载」")
    ap.add_argument("--port", default="",
                    help="★最硬判据：目标服务监听的端口（如 8899）。命中 LISTEN 映射的 PID 直接算服务本体，"
                         "不受祖先排除影响 —— terminal 启动的探针是服务子进程，不加这个可能报不出服务")
    ap.add_argument("--quiet", action="store_true", help="只打印结论行")
    a = ap.parse_args()

    if not os.path.exists(a.file):
        print(f"[FAIL] 文件不存在：{a.file}")
        return 2
    st = os.stat(a.file)
    f_mtime = st.st_mtime
    probe_start = time.time()

    if not a.quiet:
        print("=" * 66)
        print(f"部署生效性探针  file = {a.file}")
        print(f"  文件 size={st.st_size} B   mtime={_unix_to_str(f_mtime)}  unix={f_mtime:.0f}")
        print("-" * 66)

    terms = tuple(t.strip() for t in a.match_cmdline.split(",") if t.strip())
    ports = [int(t.strip()) for t in a.port.split(",") if t.strip().isdigit()]
    port_map = listen_pids(ports) if ports else {}
    excluded: set[int] = set()
    if ports and not a.quiet:
        print(f"  [端口] {ports} → PID {sorted(port_map)}（LISTEN，最硬服务判据）")

    if a.pids.strip():
        cands = []
        for tok in a.pids.split(","):
            tok = tok.strip()
            if tok.isdigit():
                cands.append((int(tok), "pid", ""))
    else:
        if not terms:
            print("[WARN] 未加 --match-cmdline：按镜像名枚举会把瞬时/无关子进程算成"
                  "\"服务\"，可能误报『晚于文件 ⇒ 已装载』。建议加 --match-cmdline webui,server.py")
        excluded = _self_and_ancestors()
        cands = list_pids([n.strip() for n in a.names.split(",") if n.strip()],
                          terms, exclude=excluded)
        if not a.quiet:
            print(f"  [排除] 探针自身及祖先 PID {sorted(excluded)} —— 其命令行含 --match-cmdline"
                  f" 的同名字面量，不排除会自匹配成假候选")
        # ① 端口命中的进程（即便不是祖先，也可能因命令行不同而漏）
        for pid, ps_ in sorted(port_map.items()):
            if all(pid != c[0] for c in cands):
                cands.append((pid, "listen", f"LISTEN {','.join(map(str, ps_))}"))
        # ② 祖先豁免：服务本体必然在探针的祖先链里，不能静默丢弃
        rescued = rescue_ancestor_service(_ancestors(), terms, port_map, probe_start)
        for pid, name, cl, why in rescued:
            if all(pid != c[0] for c in cands):
                cands.append((pid, name, cl))
            if not a.quiet:
                print(f"  [祖先豁免] PID {pid} {name} —— {why}（祖先≠自匹配：它早于探针 ≥5s，"
                      f"是真服务；静默排除会伪装成「没找到」）")

    if not cands:
        print("[WARN] 未发现候选进程 —— 无法判定。")
        if excluded:
            print(f"       已排除 {len(excluded)} 个自身/祖先 PID（豁免复核后仍为 0 命中）："
                  f"{sorted(excluded)}")
        print("       目标服务确实在跑时：加 `--port <端口>`（最硬判据）或 `--pids <PID>` 显式指定。")
        return 2

    # 判定前重查：瞬时子进程会在两次查询之间消失 —— 它们不是目标服务，剔除而非采信
    alive: list[tuple[int, str, str, float]] = []
    vanished: list[int] = []
    for pid, name, cl in cands:
        started = proc_start_unix(pid)
        if started is None:
            vanished.append(pid)
        else:
            alive.append((pid, name, cl, started))
    if vanished and not a.quiet:
        print(f"  [剔除] PID {', '.join(map(str, vanished))} 在两次查询之间已消失"
              f"（瞬时子进程，不是目标服务）")

    if not alive:
        print("[WARN] 所有候选进程都已消失 —— 无有效判定对象（瞬时进程特征）")
        return 2

    stale = []
    for pid, name, cl, started in alive:
        if started < f_mtime:
            verdict = "早于文件 ⇒ 【需重启】"
            stale.append(pid)
        else:
            verdict = "晚于文件 ⇒ 已装载"
        if not a.quiet:
            shown = f"   cmd={cl[:70]}" if cl else ""
            print(f"  PID {pid:<8} {name:<12} start={_unix_to_str(started)} ({started:.0f})  {verdict}{shown}")

    print("-" * 66)
    if stale:
        print(f"结论：{len(stale)} 个进程早于文件改动（PID {', '.join(map(str, stale))}）"
              f" ⇒ 需重启这些进程后再验证，未重启前不得声称改动已生效。")
        return 1
    print("结论：候选进程均不早于文件改动 ⇒ 改动已被装载（仍需跑功能自检确认行为正确）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())