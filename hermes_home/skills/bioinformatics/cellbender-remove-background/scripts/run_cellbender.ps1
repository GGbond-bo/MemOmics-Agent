# =============================================================================
# CellBender Batch Run Script (Proven)
# Source: User's actual production run on 15 monkey skeletal muscle samples
# =============================================================================
# Usage:
#   powershell -ExecutionPolicy Bypass -File run_cellbender.ps1
#
# CRITICAL: Set $env:PYTHONPATH='' before every cellbender call!
# =============================================================================

$ErrorActionPreference = "Continue"
$cellbender = "C:\Users\USERNAME\AppData\Local\Programs\Python\Python312\Scripts\cellbender.exe"
$h5adDir = "E:\monkey\h5ad"
$cbDir   = "E:\monkey\cellbender"

# Samples to process
$samples = @(
    "CRR278961", "CRR278962", "CRR278963", "CRR278964",
    "CRR278998", "CRR279006", "CRR279013", "CRR279014",
    "CRR279022", "CRR279023", "CRR279024", "CRR279038",
    "CRR279041", "CRR279045", "CRR279047"
)

Write-Output "========================================"
Write-Output "CellBender Batch Run at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Output "Samples: $($samples.Count)"
Write-Output "========================================"

foreach ($s in $samples) {
    $inFile  = Join-Path $h5adDir "$s.h5ad"
    $outDir  = Join-Path $cbDir $s
    $outFile = Join-Path $outDir "cellbender_output.h5"
    $logFile = Join-Path $outDir "run.log"

    $null = New-Item -ItemType Directory -Force -Path $outDir

    # Clean old checkpoint (avoid hash mismatch)
    $ckpt = Join-Path $outDir "ckpt.tar.gz"
    if (Test-Path $ckpt) { Remove-Item $ckpt -Force }

    Write-Output "`n========================================"
    Write-Output "[$s] Starting at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    Write-Output "  Input:  $inFile"
    Write-Output "  Output: $outFile"
    Write-Output "========================================"

    Push-Location $outDir
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

    & $cellbender remove-background `
        --input $inFile `
        --output $outFile `
        --projected-ambient-count-threshold 5 `
        --checkpoint-mins 120 `
        --learning-rate 0.0001 `
        --training-fraction 0.9 `
        --low-count-threshold 20 `
        --epochs 150 `
        --cuda 2>&1 | Tee-Object -FilePath $logFile

    Pop-Location

    # Verify by output file existence (NOT exit code)
    if (Test-Path $outFile) {
        Write-Output "[$s] SUCCESS: $outFile exists"
    } else {
        Write-Output "[$s] FAILED: output not found"
    }
    Write-Output "[$s] Finished at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
}

Write-Output "`n========================================"
Write-Output "ALL DONE at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Output "========================================"
