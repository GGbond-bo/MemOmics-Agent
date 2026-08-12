@echo off
cd /d E:\MemOmics-Agent
set HERMES_HOME=E:\MemOmics-Agent\hermes_home
set PYTHONPATH=E:\MemOmics-Agent;E:\MemOmics-Agent\hermes-agent
set MEMOMICS_PORT=8899
E:\MemOmics-Agent\.venv\Scripts\python.exe webui\server.py >> E:\MemOmics-Agent\server-detached.log 2>&1
