from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import cv2
import numpy as np

from .config import MAX_IMAGE_DIMENSION, MIN_IMAGE_SIDE


def inspect_image(path: Path) -> Dict[str, Any]:
    result = {
        "readable": False,
        "format": path.suffix.lower().lstrip(".").upper() or None,
        "width": None,
        "height": None,
        "channels": None,
        "dtype": None,
        "color_mode": None,
        "quality": None,
        "errors": [],
    }

    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        result["errors"].append("File is not a readable OpenCV image.")
        return result

    height, width = image.shape[:2]
    if min(height, width) < MIN_IMAGE_SIDE:
        result["errors"].append(f"Minimum image dimension is {MIN_IMAGE_SIDE}px.")
    if max(height, width) > MAX_IMAGE_DIMENSION:
        result["errors"].append(
            f"Image exceeds the configured validation dimension of {MAX_IMAGE_DIMENSION}px."
        )

    channels = 1 if image.ndim == 2 else image.shape[2]
    if image.ndim == 2:
        gray = image
        color_mode = "GRAYSCALE"
    elif channels == 4:
        gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
        color_mode = "4-CHANNEL"
    else:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        color_mode = f"{channels}-CHANNEL"

    contrast = float(np.std(gray.astype(np.float32)))
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    dark_fraction = float(np.mean(gray < 20) * 100.0)
    bright_fraction = float(np.mean(gray > 235) * 100.0)

    result.update({
        "readable": not result["errors"],
        "width": int(width),
        "height": int(height),
        "channels": int(channels),
        "dtype": str(image.dtype),
        "color_mode": color_mode,
        "quality": {
            "contrast": round(contrast, 3),
            "sharpness_laplacian_variance": round(sharpness, 3),
            "dark_pixel_fraction": round(dark_fraction, 2),
            "bright_pixel_fraction": round(bright_fraction, 2),
        },
    })
    return result
