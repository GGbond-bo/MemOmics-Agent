@echo off
rem 2026-08-21: 全局 UTF-8 模式 —— 所有 text=True 子进程(Git/conda/R/nvidia-smi/tasklist 等)
rem 的输出按 UTF-8 解码，消除中文 Windows(GBK) 下 subprocess reader 线程 UnicodeDecodeError。
set PYTHONUTF8=1
cd /d E:\MemOmics-Agent
set HERMES_HOME=E:\MemOmics-Agent\hermes_home
set PYTHONPATH=E:\MemOmics-Agent;E:\MemOmics-Agent\hermes-agent
set MEMOMICS_PORT=8899
E:\MemOmics-Agent\.venv\Scripts\python.exe webui\server.py >> E:\MemOmics-Agent\server-detached.log 2>&1
