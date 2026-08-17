# =============================================================================
# ptrepack: Compress CellBender output for Seurat Read10X_h5()
# Source: User's actual production run
# =============================================================================
$ErrorActionPreference = "Continue"
$ptrepack = "C:\Users\USERNAME\AppData\Local\Programs\Python\Python312\Scripts\ptrepack.exe"
$cbDir    = "E:\monkey\cellbender"
$outDir   = "E:\monkey\cellbender_seurat"

$samples = @(
    "CRR278961", "CRR278962", "CRR278963", "CRR278964",
    "CRR278998", "CRR279006", "CRR279013", "CRR279014",
    "CRR279022", "CRR279023", "CRR279024", "CRR279038",
    "CRR279041", "CRR279045", "CRR279047"
)

$null = New-Item -ItemType Directory -Force -Path $outDir

foreach ($s in $samples) {
    $inFile  = Join-Path (Join-Path $cbDir $s) "cellbender_output_filtered.h5"
    $outFile = Join-Path $outDir "${s}_filtered_seurat.h5"

    if (-not (Test-Path $inFile)) {
        Write-Output "[$s] SKIP: $inFile not found"
        continue
    }

    Write-Output "[$s] ptrepack --complevel 5 ..."
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    & $ptrepack --complevel 5 "${inFile}:/matrix" "${outFile}:/matrix" 2>&1

    if (Test-Path $outFile) {
        Write-Output "  -> $outFile [OK]"
    } else {
        Write-Output "  -> ERROR"
    }
}
Write-Output "ALL DONE!"
