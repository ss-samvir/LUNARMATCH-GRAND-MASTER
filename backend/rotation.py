from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Iterator

import cv2
import numpy as np

from .config import ROTATION_MAX_DEGREES, ROTATION_MAX_STEPS, ROTATION_ROOT


def validate_angles(angles: Iterable[float]) -> list[float]:
    cleaned = []
    for raw in angles:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(value):
            continue
        value = max(-ROTATION_MAX_DEGREES, min(ROTATION_MAX_DEGREES, value))
        cleaned.append(round(value, 3))
    return cleaned[:ROTATION_MAX_STEPS] or [0.0]


def rotate_image(gray: np.ndarray, degrees: float) -> np.ndarray:
    height, width = gray.shape[:2]
    center = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(center, float(degrees), 1.0)

    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    bound_width = int((height * sin) + (width * cos))
    bound_height = int((height * cos) + (width * sin))

    matrix[0, 2] += (bound_width / 2.0) - center[0]
    matrix[1, 2] += (bound_height / 2.0) - center[1]

    return cv2.warpAffine(
        gray,
        matrix,
        (bound_width, bound_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )


def save_rotation(gray: np.ndarray, degrees: float, session_id: str) -> Path:
    ROTATION_ROOT.mkdir(parents=True, exist_ok=True)
    path = ROTATION_ROOT / f"{session_id}_rot_{degrees:+06.1f}.png"
    cv2.imwrite(str(path), gray)
    return path


def stream_reanalysis(
    image_a_path: Path,
    image_b_path: Path,
    angles: Iterable[float],
    rotate_target: str = "b",
) -> Iterator[Dict[str, Any]]:
    from lunar_engine import run as run_lunarmatch_engine

    image_a = cv2.imread(str(image_a_path), cv2.IMREAD_GRAYSCALE)
    image_b = cv2.imread(str(image_b_path), cv2.IMREAD_GRAYSCALE)
    if image_a is None or image_b is None:
        yield {
            "type": "error",
            "message": "Both uploaded images must be readable.",
        }
        return

    target = rotate_target.lower().strip()
    if target not in {"a", "b"}:
        target = "b"

    session_id = uuid.uuid4().hex
    angle_list = validate_angles(angles)

    yield {
        "type": "started",
        "session_id": session_id,
        "rotate_target": target,
        "angles": angle_list,
        "total": len(angle_list),
    }

    for index, angle in enumerate(angle_list, start=1):
        started = time.perf_counter()
        rotated_a = rotate_image(image_a, angle) if target == "a" else image_a
        rotated_b = rotate_image(image_b, angle) if target == "b" else image_b

        analysis = run_lunarmatch_engine(rotated_a, rotated_b)
        preview = save_rotation(
            rotated_a if target == "a" else rotated_b,
            angle,
            session_id,
        )

        yield {
            "type": "stage",
            "index": index,
            "total": len(angle_list),
            "angle": angle,
            "stage": "REANALYZE",
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 1),
            "score": round(float(analysis.get("score", 0.0)), 2),
            "confidence": analysis.get("confidence_label"),
            "confidence_value": round(float(analysis.get("confidence_value", 0.0)), 2),
            "verified_matches": len(analysis.get("inlier_matches", [])),
            "candidate_matches": len(analysis.get("reciprocal_matches", [])),
            "coverage_percent": round(float(analysis.get("coverage", 0.0)), 2),
            "geometry_consistency": round(
                float(analysis.get("geometry", {}).get("consistency", 0.0)), 2
            ),
            "preview_path": f"/api/v2/rotation-preview/{preview.name}",
        }

    yield {
        "type": "complete",
        "session_id": session_id,
        "total": len(angle_list),
    }
