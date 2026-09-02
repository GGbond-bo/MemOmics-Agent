#!/bin/bash
# ASCII-only inspector (avoid pwsh->wsl Chinese encoding issues)
echo "== mm-heal/MemOmics top =="
ls ~/mm-heal/MemOmics 2>/dev/null | head -8
echo "== .venv state =="
ls -la ~/mm-heal/MemOmics/.venv/bin/ 2>/dev/null | head -8
if [ -f ~/mm-heal/MemOmics/.venv/bin/python ]; then
  ~/mm-heal/MemOmics/.venv/bin/python -m pip --version 2>&1 | head -1
  ~/mm-heal/MemOmics/.venv/bin/python -c "import fastapi; print('FASTAPI OK', fastapi.__version__)" 2>&1 | head -1
fi
echo "== miniconda installed? =="
ls ~/mm-heal/MemOmics/miniconda_env/bin/python 2>/dev/null && echo MINICONDA_PRESENT || echo MINICONDA_ABSENT
echo "== heal_run.log tail =="
tail -30 /tmp/heal_run.log 2>/dev/null || echo NO_LOG
echo "== running servers =="
ss -ltnp 2>/dev/null | grep -E '8899|8898' || echo NO_LISTENER
echo "== mm-fresh =="
ls ~/mm-fresh 2>/dev/null || echo NO_FRESH_DIR
echo DONE