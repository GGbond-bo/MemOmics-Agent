# Memory/context logic gate - fast offline regression for the
# single-session context + memory architecture (P1-P5, hygiene, REQUIREMENTS).
# Usage:  pwsh scripts/gate_memory.ps1   (exit 0 = green)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }

Write-Host '== Memory/context gate (offline) =='
& $py -m pytest webui/tests/test_context_arch.py `
       webui/tests/test_requirements_memory.py `
       webui/tests/test_long_context.py `
       webui/tests/test_single_session_stress.py `
       -q
Write-Host "GATE EXIT: $LASTEXITCODE"
exit $LASTEXITCODE
