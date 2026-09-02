#!/bin/bash
# Cluster first-boot reproduction: broken pip-less .venv + polluted PYTHONPATH
# Runs the FIXED start.sh on a fresh tar extract on port 8897.
set -x
export PATH=/usr/bin:/bin:/usr/local/bin

echo "=== [B] venv creation isolation check ==="
rm -rf /tmp/vb && mkdir -p /tmp/vb && cd /tmp/vb
export PYTHONPATH=/opt/compiler/gcc:/software/lib/python3.11/site-packages:/home/user/.local
env -u PYTHONPATH /root/memomics-test/MemOmics/miniconda_env/bin/python -m venv .good
.good/bin/python -m pip --version 2>&1 | head -1
echo "B_RESULT: pip visible above = isolation OK"

echo "=== [A] fresh extract + broken venv + polluted PYTHONPATH ==="
cd /root
rm -rf mm-heal
mkdir mm-heal && cd mm-heal
tar -xzf /mnt/e/release/MemOmics-Linux.tar.gz
cd MemOmics
cp /mnt/e/MemOmics-Agent/launchers/start_linux.sh start.sh
chmod +x start.sh
# manufacture the broken venv exactly like the cluster user's
/root/memomics-test/MemOmics/miniconda_env/bin/python -m venv --without-pip .venv
echo "manufactured .venv pip check:"
.venv/bin/python -m pip --version 2>&1 | head -1

export PYTHONPATH=/opt/compiler/gcc:/software/lib/python3.11/site-packages:/home/user/.local
echo "=== running start.sh 8897 (full first boot) ==="
bash start.sh 8897 > /tmp/heal_run.log 2>&1 &
BOOT_PID=$!
# poll up to 15 min for health on 8897
OK=no
for i in $(seq 1 150); do
  sleep 6
  if curl -s --max-time 3 http://localhost:8897/api/health 2>/dev/null | grep -q '"ok"'; then
    OK=yes; break
  fi
  if ! kill -0 $BOOT_PID 2>/dev/null; then
    echo "boot process exited early at iter $i"; break
  fi
done
echo "HEALTH_OK=$OK"
echo "=== start.sh output tail ==="
tail -35 /tmp/heal_run.log
echo "=== venv pip after boot ==="
.venv/bin/python -m pip --version 2>&1 | head -1
echo "=== fastapi after boot ==="
.venv/bin/python -c "import fastapi; print('FASTAPI', fastapi.__version__)" 2>&1 | head -1
# stop the booted instance (pid file)
if [ -f log/webui.pid ]; then kill $(cat log/webui.pid) 2>/dev/null; fi
kill $BOOT_PID 2>/dev/null
echo ALL_DONE