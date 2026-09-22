from pathlib import Path
import os

BASE = Path(__file__).resolve().parents[1]

MAX_PRODUCT_BYTES = int(os.environ.get("LUNARMATCH_MAX_PRODUCT_BYTES", 25 * 1024 * 1024))
MAX_IMAGE_DIMENSION = int(os.environ.get("LUNARMATCH_MAX_IMAGE_DIMENSION", 8192))
MIN_IMAGE_SIDE = int(os.environ.get("LUNARMATCH_MIN_IMAGE_SIDE", 32))

SUPPORTED_IMAGE_SUFFIXES = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"
}
PDS4_SUFFIXES = {".xml", ".lbl", ".pds4"}

ROTATION_MAX_DEGREES = 180.0
ROTATION_MAX_STEPS = 37
BENCHMARK_MAX_CASES = 1000

TEMP_ROOT = BASE / "backend_tmp"
ROTATION_ROOT = TEMP_ROOT / "rotation"
INSPECTION_ROOT = TEMP_ROOT / "inspection"
BENCHMARK_ROOT = TEMP_ROOT / "benchmark"

for folder in (TEMP_ROOT, ROTATION_ROOT, INSPECTION_ROOT, BENCHMARK_ROOT):
    folder.mkdir(parents=True, exist_ok=True)
