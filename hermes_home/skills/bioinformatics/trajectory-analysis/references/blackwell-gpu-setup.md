# Blackwell GPU (RTX 50 Series) CUDA Setup for scTour

> Verified on: RTX 5070 Ti (sm_120, Blackwell architecture), Windows 11, 2026-07-07

## Problem

`torch.cuda.is_available()` returns `False` even though `nvidia-smi` shows the GPU. PyTorch installed via `pip install torch` (default PyPI, CPU-only) or via `uv pip install torch` (also CPU-only on Windows).

The PyTorch cu124 index (`https://download.pytorch.org/whl/cu124`) only provides `torch<=2.6.0`, which supports up to sm_90 (Hopper). Blackwell (sm_120) requires PyTorch ≥2.8.0.

## Solution

Install PyTorch from the **cu128 test channel**:

```bash
pip install "torch>=2.8.0" --index-url https://download.pytorch.org/whl/test/cu128
```

This downloads ~2.7GB (includes CUDA 12.8 runtime). Time: ~5-10 minutes on 100Mbps.

## Disk Space Warning

The cu128 package is ~2.7GB and pip needs additional space for extraction. If `C:` drive has less than 10GB free, set the temp directory to another drive **before** installing:

```bash
# Create temp dir on E: drive (or any drive with >10GB free)
mkdir -p /e/tmp
TMPDIR="/e/tmp" TEMP="/e/tmp" TMP="/e/tmp" pip install "torch>=2.8.0" \
  --index-url https://download.pytorch.org/whl/test/cu128 --force-reinstall --no-cache-dir
```

Without this, you'll get `OSError: [Errno 28] No space left on device` midway through the download. Confirmed on a 201GB C: drive with 5.7GB free.

## Verification

```bash
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0)}')"
```

Expected output:
```
PyTorch: 2.11.0+cu128
CUDA: True
GPU: NVIDIA GeForce RTX 5070 Ti
```

## uv Caveat

When using `uv pip install`, the `--index-url` must point to the **only** index, or use `--extra-index-url` + `--index-strategy unsafe-best-match`:

```bash
# Works (single index):
uv pip install "torch>=2.8" --index-url https://download.pytorch.org/whl/test/cu128

# Also works (multiple indexes):
uv pip install "torch>=2.8" --extra-index-url https://download.pytorch.org/whl/test/cu128 --index-strategy unsafe-best-match
```

## CPU Fallback

If the 2.7GB download is impractical, CPU mode is still acceptable for <50k cells × 1,000 HVGs:
- 11,630 cells × 1,000 HVGs × 344 epochs: **~2.5 minutes per run** on modern CPU (no GPU)
- 3 runs completed in ~7 minutes total