import os
import json
import sqlite3
import uuid
import math
import numbers
import time
from pathlib import Path
from datetime import datetime, timezone

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    session,
    send_from_directory,
    send_file,
)
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image, ExifTags
import cv2
import numpy as np

from lunar_engine import run as run_lunarmatch_engine, draw_correspondence as draw_custom_correspondence


# =========================================================
# PATHS / APP CONFIGURATION
# =========================================================

BASE = Path(__file__).resolve().parent
UPLOADS = BASE / "uploads"
RESULTS = BASE / "results"
REPORTS = BASE / "reports"
DB = BASE / "lunarmatch.db"

for folder in (UPLOADS, RESULTS, REPORTS):
    folder.mkdir(exist_ok=True)

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-in-production",
)

app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024


# =========================================================
# ANALYSIS CONFIGURATION
# =========================================================

MAX_DIMENSION = 1600
MAX_FEATURES = 5000
LOWE_RATIO = 0.80
RANSAC_THRESHOLD = 5.0
MIN_IMAGE_SIDE = 32
FREE_GUEST_ANALYSIS_LIMIT = 5

ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
}


# =========================================================
# DATABASE
# =========================================================

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = db()

    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS analyses(
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            created_at TEXT NOT NULL,
            result_json TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """
    )

    # Backward-compatible schema migration for guest analysis history.
    columns = {row[1] for row in c.execute("PRAGMA table_info(analyses)").fetchall()}
    if "guest_id" not in columns:
        c.execute("ALTER TABLE analyses ADD COLUMN guest_id TEXT")

    c.commit()
    c.close()


init_db()


# =========================================================
# GENERAL HELPERS
# =========================================================

def safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def get_guest_id():
    """Create/retrieve the anonymous browser-session identifier used for guest history."""
    guest_id = session.get("guest_id")
    if not guest_id:
        guest_id = uuid.uuid4().hex
        session["guest_id"] = guest_id
    return guest_id


def guest_analysis_count(guest_id):
    c = db()
    row = c.execute(
        "SELECT COUNT(*) AS count FROM analyses WHERE guest_id=? AND user_id IS NULL",
        (guest_id,),
    ).fetchone()
    c.close()
    return int(row["count"] or 0)


def json_safe(value):
    """Recursively convert NumPy/OpenCV/Pillow values into strict JSON types."""
    if value is None or isinstance(value, (str, bool, int)):
        return value

    if isinstance(value, float):
        return value if math.isfinite(value) else None

    if isinstance(value, numbers.Integral):
        return int(value)

    if isinstance(value, numbers.Real):
        value = float(value)
        return value if math.isfinite(value) else None

    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())

    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]

    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}

    if isinstance(value, Path):
        return str(value)

    try:
        return json_safe(value.item())
    except Exception:
        return str(value)


def gps_decimal(value):
    try:
        if hasattr(value, "numerator") and hasattr(value, "denominator"):
            den = float(value.denominator)
            return float(value.numerator) / den if den else None

        if isinstance(value, (tuple, list)):
            total = 0.0

            for i, item in enumerate(value):
                if hasattr(item, "numerator") and hasattr(item, "denominator"):
                    den = float(item.denominator)
                    part = float(item.numerator) / den if den else 0.0
                else:
                    part = float(item)

                total += part / (60 ** i)

            return total

        return float(value)

    except Exception:
        return None


def status_item(value, *, verified=False, applicable=True):
    if not applicable:
        return {
            "status": "NOT APPLICABLE",
            "value": None,
        }

    if value in (None, "", [], {}):
        return {
            "status": "NOT AVAILABLE",
            "value": None,
        }

    return {
        "status": "VERIFIED" if verified else "AVAILABLE",
        "value": value,
    }


# =========================================================
# INSTRUMENT IDENTIFICATION
# =========================================================

def identify_instrument(path, metadata):
    """
    Instrument identification is deliberately conservative.
    It only reports an instrument when metadata, filename or supplied
    reference text gives a recognizable Chandrayaan-2 payload signal.
    """

    haystack = " ".join(
        str(x or "")
        for x in [
            path.name,
            metadata.get("mission"),
            metadata.get("instrument"),
            metadata.get("image_id"),
            metadata.get("provenance"),
            metadata.get("product_id"),
        ]
    ).upper()

    if any(
        k in haystack
        for k in (
            "OHRC",
            "ORBITER HIGH RESOLUTION CAMERA",
        )
    ):
        return {
            "status": "IDENTIFIED",
            "instrument": "OHRC",
            "mission": "Chandrayaan-2",
            "evidence": "Recognized from supplied filename/metadata.",
        }

    if any(
        k in haystack
        for k in (
            "TMC-2",
            "TMC2",
            "TMC_2",
            "TMC 2",
            "TERRAIN MAPPING CAMERA",
        )
    ):
        return {
            "status": "IDENTIFIED",
            "instrument": "TMC-2",
            "mission": "Chandrayaan-2",
            "evidence": "Recognized from supplied filename/metadata.",
        }

    if any(
        k in haystack
        for k in (
            "IIRS",
            "IMAGING INFRARED SPECTROMETER",
        )
    ):
        return {
            "status": "IDENTIFIED",
            "instrument": "IIRS",
            "mission": "Chandrayaan-2",
            "evidence": "Recognized from supplied filename/metadata.",
        }

    return {
        "status": "NOT ESTABLISHED",
        "instrument": None,
        "mission": metadata.get("mission"),
        "evidence": "No reliable Chandrayaan-2 payload identifier was found.",
    }


# =========================================================
# METADATA
# =========================================================

def read_metadata(path):
    out = {
        "available": False,
        "latitude": None,
        "longitude": None,
        "altitude": None,
        "acquisition_time": None,
        "camera": None,
        "mission": None,
        "instrument": None,
        "crs": None,
        "projection": None,
        "datum": None,
        "image_id": None,
        "product_id": None,
        "provenance": None,
        "source": "Embedded image metadata",
    }

    try:
        im = Image.open(path)

        ex = im.getexif()

        tags = {
            ExifTags.TAGS.get(k, k): v
            for k, v in ex.items()
        }

        out["camera"] = (
            tags.get("Model")
            or tags.get("Make")
        )

        out["acquisition_time"] = (
            tags.get("DateTimeOriginal")
            or tags.get("DateTime")
        )

        gps = tags.get("GPSInfo")

        if gps:
            gps2 = {
                ExifTags.GPSTAGS.get(k, k): v
                for k, v in gps.items()
            }

            lat = gps2.get("GPSLatitude")
            lon = gps2.get("GPSLongitude")

            if lat and lon:
                lat_v = gps_decimal(lat)
                lon_v = gps_decimal(lon)

                if lat_v is not None:
                    out["latitude"] = lat_v * (
                        -1
                        if str(
                            gps2.get("GPSLatitudeRef", "")
                        ).upper() == "S"
                        else 1
                    )

                if lon_v is not None:
                    out["longitude"] = lon_v * (
                        -1
                        if str(
                            gps2.get("GPSLongitudeRef", "")
                        ).upper() == "W"
                        else 1
                    )

            if gps2.get("GPSAltitude") is not None:
                out["altitude"] = gps_decimal(
                    gps2.get("GPSAltitude")
                )

        # Optional JSON sidecar metadata
        side = path.with_suffix(".json")

        if side.exists():
            data = json.loads(
                side.read_text(encoding="utf-8")
            )

            aliases = {
                "instrument": [
                    "instrument",
                    "payload",
                ],
                "mission": [
                    "mission",
                ],
                "image_id": [
                    "image_id",
                    "imageId",
                ],
                "product_id": [
                    "product_id",
                    "productId",
                ],
                "provenance": [
                    "provenance",
                    "source",
                ],
                "crs": [
                    "crs",
                ],
                "projection": [
                    "projection",
                ],
                "datum": [
                    "datum",
                ],
                "latitude": [
                    "latitude",
                    "lat",
                ],
                "longitude": [
                    "longitude",
                    "lon",
                ],
                "altitude": [
                    "altitude",
                ],
                "acquisition_time": [
                    "acquisition_time",
                    "acquisitionTime",
                    "date_time",
                ],
            }

            for target, keys in aliases.items():
                for key in keys:
                    if data.get(key) not in (None, ""):
                        out[target] = data[key]
                        break

            out["source"] = (
                "Embedded metadata + supplied reference metadata"
            )

        out["available"] = any(
            out[k] not in (None, "", [], {})
            for k in out
            if k not in (
                "available",
                "source",
            )
        )

    except Exception as exc:
        out["metadata_error"] = str(exc)

    return out


# =========================================================
# IMAGE INFORMATION
# =========================================================

def image_info(path):
    im = cv2.imread(
        str(path),
        cv2.IMREAD_UNCHANGED,
    )

    if im is None:
        raise ValueError(
            "Unsupported or unreadable image."
        )

    h, w = im.shape[:2]

    if min(h, w) < MIN_IMAGE_SIDE:
        raise ValueError(
            f"Image is too small. "
            f"Minimum dimension is {MIN_IMAGE_SIDE}px."
        )

    channels = (
        1
        if im.ndim == 2
        else im.shape[2]
    )

    color_mode = (
        "GRAYSCALE"
        if channels == 1
        else f"{channels}-CHANNEL"
    )

    # Correct handling for grayscale,
    # BGR and BGRA images.
    if im.ndim == 2:
        gray = im

    elif im.shape[2] == 4:
        gray = cv2.cvtColor(
            im,
            cv2.COLOR_BGRA2GRAY,
        )

    else:
        gray = cv2.cvtColor(
            im,
            cv2.COLOR_BGR2GRAY,
        )

    return {
        "image": im,
        "gray": gray,
        "width": w,
        "height": h,
        "channels": channels,
        "color_mode": color_mode,
        "dtype": str(im.dtype),
    }


# =========================================================
# IMAGE QUALITY
# =========================================================

def quality_metrics(gray):
    gray_f = gray.astype(np.float32)

    contrast = float(
        np.std(gray_f)
    )

    sharpness = float(
        cv2.Laplacian(
            gray,
            cv2.CV_64F,
        ).var()
    )

    mean = float(
        np.mean(gray_f)
    )

    dark_fraction = float(
        np.mean(gray_f < 20)
    )

    bright_fraction = float(
        np.mean(gray_f > 235)
    )

    # These are image-quality indicators,
    # not scientific truth scores.
    contrast_component = min(
        100.0,
        contrast / 0.64,
    )

    sharpness_component = min(
        100.0,
        math.log1p(sharpness)
        / math.log1p(1200)
        * 100,
    )

    exposure_component = max(
        0.0,
        100.0
        - (
            dark_fraction
            + bright_fraction
        )
        * 180,
    )

    quality = round(
        max(
            0.0,
            min(
                100.0,
                contrast_component * 0.4
                + sharpness_component * 0.4
                + exposure_component * 0.2,
            ),
        ),
        2,
    )

    return {
        "contrast": round(
            contrast,
            3,
        ),
        "sharpness_laplacian_variance": round(
            sharpness,
            3,
        ),
        "mean_intensity": round(
            mean,
            3,
        ),
        "dark_pixel_fraction": round(
            dark_fraction * 100,
            2,
        ),
        "bright_pixel_fraction": round(
            bright_fraction * 100,
            2,
        ),
        "quality_score": quality,
        "quality_basis": (
            "contrast + Laplacian sharpness "
            "+ exposure balance"
        ),
    }


# =========================================================
# RESIZE
# =========================================================

def resize_once(gray):
    h, w = gray.shape

    scale = min(
        1.0,
        MAX_DIMENSION / max(h, w),
    )

    if scale < 1:
        resized = cv2.resize(
            gray,
            (
                round(w * scale),
                round(h * scale),
            ),
            interpolation=cv2.INTER_AREA,
        )
    else:
        resized = gray

    return resized, scale


# =========================================================
# MATCHING + GEOMETRIC VERIFICATION
# =========================================================

def match_and_verify(ka, da, kb, db):
    """
    Robust SIFT correspondence and geometric verification.

    Reciprocal Lowe-ratio matches are treated as strong evidence,
    but they are NOT a hard gate for geometric verification.
    Lowe-ratio candidates are allowed into RANSAC so that a valid
    geometric relationship can still be discovered when reciprocal
    filtering is too strict for small or difficult images.
    """

    empty_result = {
        "raw_knn_matches": 0,
        "ratio_candidates": 0,
        "ratio_matches": [],
        "reciprocal_matches": [],
        "inlier_indices": [],
        "reprojection_errors": [],
        "homography": None,
        "matches": [],
    }

    if da is None or db is None:
        return empty_result

    if len(da) < 2 or len(db) < 2:
        return empty_result

    bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)

    try:
        forward_knn = bf.knnMatch(da, db, k=2)
        reverse_knn = bf.knnMatch(db, da, k=2)
    except cv2.error:
        return empty_result

    raw_knn_matches = len(forward_knn)

    # ---------------------------------------------------------
    # Adaptive Lowe-ratio candidate generation
    # ---------------------------------------------------------

    # Keypoint coordinates are used only to avoid making image-size
    # assumptions inside this function. The primary baseline remains
    # LOWE_RATIO = 0.80; for difficult/small imagery we expand the
    # candidate pool progressively rather than changing the global
    # configuration permanently.
    ratio_thresholds = [LOWE_RATIO, 0.85, 0.90]

    def ratio_filter(knn_matches, ratio):
        good = []

        for pair in knn_matches:
            if len(pair) != 2:
                continue

            m, n = pair

            if n.distance <= 0:
                continue

            if m.distance < ratio * n.distance:
                good.append(m)

        return good

    forward_candidates = []
    for ratio in ratio_thresholds:
        candidates = ratio_filter(forward_knn, ratio)

        if len(candidates) > len(forward_candidates):
            forward_candidates = candidates

        if len(candidates) >= 8:
            forward_candidates = candidates
            break

    reverse_candidates = []
    for ratio in ratio_thresholds:
        candidates = ratio_filter(reverse_knn, ratio)

        if len(candidates) > len(reverse_candidates):
            reverse_candidates = candidates

        if len(candidates) >= 8:
            reverse_candidates = candidates
            break

    # ---------------------------------------------------------
    # Reciprocal matching
    # ---------------------------------------------------------

    reverse_pairs = {
        (m.queryIdx, m.trainIdx)
        for m in reverse_candidates
    }

    reciprocal_matches = [
        m
        for m in forward_candidates
        if (m.trainIdx, m.queryIdx) in reverse_pairs
    ]

    # ---------------------------------------------------------
    # Candidate pool for geometric verification
    # ---------------------------------------------------------

    reciprocal_keys = {
        (m.queryIdx, m.trainIdx)
        for m in reciprocal_matches
    }

    ordered_candidates = []

    # Put reciprocal matches first because they are stronger evidence.
    ordered_candidates.extend(reciprocal_matches)

    # Then add all other Lowe-ratio candidates.
    for m in forward_candidates:
        key = (m.queryIdx, m.trainIdx)
        if key not in reciprocal_keys:
            ordered_candidates.append(m)

    # Remove duplicate query/reference pairs while preserving order.
    unique_candidates = []
    seen = set()

    for m in ordered_candidates:
        key = (m.queryIdx, m.trainIdx)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(m)

    result = {
        "raw_knn_matches": raw_knn_matches,
        "ratio_candidates": len(forward_candidates),
        "ratio_matches": forward_candidates,
        "reciprocal_matches": reciprocal_matches,
        "inlier_indices": [],
        "reprojection_errors": [],
        "homography": None,
        "matches": unique_candidates,
    }

    # ---------------------------------------------------------
    # Geometric verification
    # ---------------------------------------------------------

    if len(unique_candidates) < 4:
        return result

    src = np.float32([
        ka[m.queryIdx].pt
        for m in unique_candidates
    ]).reshape(-1, 1, 2)

    dst = np.float32([
        kb[m.trainIdx].pt
        for m in unique_candidates
    ]).reshape(-1, 1, 2)

    try:
        H, mask = cv2.findHomography(
            src,
            dst,
            cv2.RANSAC,
            RANSAC_THRESHOLD,
            maxIters=3000,
            confidence=0.995,
        )
    except cv2.error:
        H, mask = None, None

    if H is None or mask is None:
        return result

    inlier_indices = [
        i
        for i, flag in enumerate(mask.ravel())
        if int(flag) == 1
    ]

    try:
        projected = cv2.perspectiveTransform(src, H)
        errors = np.linalg.norm(
            projected - dst,
            axis=2,
        ).reshape(-1)
        reprojection_errors = errors.tolist()
    except cv2.error:
        reprojection_errors = []

    result.update({
        "inlier_indices": inlier_indices,
        "reprojection_errors": reprojection_errors,
        "homography": H,
    })

    return result


# =========================================================
# SPATIAL DISTRIBUTION
# =========================================================

def spatial_distribution(
    matches,
    keypoints,
    width,
    height,
):
    if not matches or not keypoints:
        return {
            "status": "INSUFFICIENT",
            "occupied_grid_cells": 0,
            "grid_cells_total": 16,
            "coverage_percent": 0.0,
        }

    cells = set()

    for m in matches:
        x, y = keypoints[
            m.queryIdx
        ].pt

        gx = min(
            3,
            max(
                0,
                int(
                    x
                    / max(width, 1)
                    * 4
                ),
            ),
        )

        gy = min(
            3,
            max(
                0,
                int(
                    y
                    / max(height, 1)
                    * 4
                ),
            ),
        )

        cells.add(
            (gx, gy)
        )

    coverage = (
        len(cells)
        / 16
        * 100
    )

    return {
        "status": (
            "GOOD"
            if coverage >= 50
            else "LIMITED"
        ),
        "occupied_grid_cells": len(cells),
        "grid_cells_total": 16,
        "coverage_percent": round(
            coverage,
            2,
        ),
    }


# =========================================================
# TRANSFORMATION QUALITY
# =========================================================

def transformation_quality(H):
    if H is None:
        return {
            "status": "NOT ESTABLISHED",
            "determinant": None,
            "condition_number": None,
        }

    try:
        h33 = (
            H / H[2, 2]
            if abs(H[2, 2]) > 1e-12
            else H
        )

        determinant = float(
            np.linalg.det(
                h33[:2, :2]
            )
        )

        condition = float(
            np.linalg.cond(
                h33[:2, :2]
            )
        )

        if not np.isfinite(condition):
            status = "DEGENERATE"
        elif condition > 1000:
            status = "POOR"
        elif condition > 100:
            status = "LIMITED"
        else:
            status = "STABLE"

        return {
            "status": status,
            "determinant": round(
                determinant,
                6,
            ),
            "condition_number": round(
                condition,
                3,
            ),
        }

    except Exception:
        return {
            "status": "UNDETERMINED",
            "determinant": None,
            "condition_number": None,
        }


# =========================================================
# CORRESPONDENCE DRAWING HELPER
# =========================================================

def draw_correspondence(
    a_gray,
    b_gray,
    ka,
    kb,
    matches,
    inlier_indices,
    out_path,
):
    if not matches:
        h = max(
            a_gray.shape[0],
            1,
        )

        blank = np.zeros(
            (
                h,
                max(
                    a_gray.shape[1],
                    1,
                ) * 2,
            ),
            dtype=np.uint8,
        )

        cv2.imwrite(
            str(out_path),
            blank,
        )

        return

    draw_matches = list(matches)

    flags = cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS

    canvas = cv2.drawMatches(
        a_gray,
        ka,
        b_gray,
        kb,
        draw_matches,
        None,
        flags=flags,
    )

    cv2.rectangle(
        canvas,
        (0, 0),
        (
            canvas.shape[1],
            34,
        ),
        (12, 16, 24),
        -1,
    )

    cv2.putText(
        canvas,
        (
            f"CANDIDATE MATCHES: {len(matches)} "
            f"| VERIFIED INLIERS: {len(inlier_indices)} "
            f"| OUTLIERS: "
            f"{len(matches) - len(inlier_indices)}"
        ),
        (12, 23),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        (235, 240, 248),
        1,
        cv2.LINE_AA,
    )

    cv2.imwrite(
        str(out_path),
        canvas,
    )


# =========================================================
# MAIN ANALYSIS ENGINE
# =========================================================

def analyze(a_path, b_path):
    started = time.perf_counter()
    stage_times = {}

    # 01 ACQUIRE
    t = time.perf_counter()
    a_info = image_info(a_path)
    b_info = image_info(b_path)
    a_meta = read_metadata(a_path)
    b_meta = read_metadata(b_path)
    stage_times["acquire_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # 02 PREPROCESS
    t = time.perf_counter()
    aa, scale_a = resize_once(a_info["gray"])
    bb, scale_b = resize_once(b_info["gray"])
    stage_times["preprocess_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # 03 EXTRACT + PRIMARY MATCHING
    t = time.perf_counter()
    primary = run_lunarmatch_engine(aa, bb)
    stage_times["extract_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # 04 MATCH / CROSS-CHECK
    # The primary LunarMatch engine is authoritative. The SIFT branch is
    # intentionally deferred until after primary verification so a strong
    # result does not pay the SIFT cost on the critical request path.
    match_started = time.perf_counter()
    sift_result = None

    # 05 VERIFY — primary LunarMatch evidence
    verify_started = time.perf_counter()
    features_a = primary["features_a"]
    features_b = primary["features_b"]
    raw_matches = primary["raw_matches"]
    reciprocal_matches = primary["reciprocal_matches"]
    inlier_indices = primary["geometry"]["inlier_indices"]
    inlier_matches = primary["inlier_matches"]

    verified = len(inlier_matches)
    candidates = len(reciprocal_matches)
    outliers = max(0, candidates - verified)
    inlier_ratio = verified / max(1, candidates) * 100.0
    spatial_coverage = primary["coverage"]
    spatial = {
        "status": "GOOD" if spatial_coverage >= 40 else "LIMITED" if spatial_coverage > 0 else "INSUFFICIENT",
        "occupied_grid_cells": round(spatial_coverage / 4.0),
        "grid_cells_total": 25,
        "coverage_percent": round(spatial_coverage, 2),
        "grid": "5×5 source coverage",
    }
    errors = primary["geometry"]["reprojection_errors"]
    inlier_errors = [errors[i] for i in inlier_indices if i < len(errors)]
    reproj_mean = float(np.mean(inlier_errors)) if inlier_errors else None
    reproj_median = float(np.median(inlier_errors)) if inlier_errors else None
    reproj_max = float(np.max(inlier_errors)) if inlier_errors else None
    H = primary["homography"]

    # Degeneracy check mirrors the original engine's intent.
    degenerate = False
    if len(inlier_matches) >= 3:
        src_pts = np.asarray([[features_a[m["a"]]["x"], features_a[m["a"]]["y"]] for m in inlier_matches], dtype=np.float64)
        dst_pts = np.asarray([[features_b[m["b"]]["x"], features_b[m["b"]]["y"]] for m in inlier_matches], dtype=np.float64)
        degenerate = (
            np.linalg.matrix_rank(src_pts - src_pts.mean(axis=0)) < 2
            or np.linalg.matrix_rank(dst_pts - dst_pts.mean(axis=0)) < 2
        )

    transform_quality = (
        transformation_quality(H)
        if H is not None else
        {"status": "NOT ESTABLISHED", "determinant": None, "condition_number": None}
    )

    verification_status = (
        "VERIFIED"
        if H is not None and verified >= 5 and not degenerate
        else "LIMITED"
    )

    # Fast-path rule: when the primary LunarMatch evidence is already
    # geometrically coherent, return immediately without running the
    # independent SIFT diagnostic. This preserves the primary evidence while
    # removing unnecessary latency from the submission-critical path.
    primary_strong_enough = (
        H is not None
        and verified >= 3
        and not degenerate
        and inlier_ratio >= 100.0
    )

    if primary_strong_enough:
        sift_result = {
            "raw_knn_matches": 0,
            "ratio_candidates": 0,
            "reciprocal_matches": [],
            "inlier_indices": [],
            "matches": [],
            "homography": None,
            "skipped": True,
        }
        sift_skipped_reason = (
            "Fast path: primary LunarMatch evidence was already geometrically coherent."
        )
    else:
        sift = cv2.SIFT_create(nfeatures=500, contrastThreshold=0.02)
        sift_ka, sift_da = sift.detectAndCompute(aa, None)
        sift_kb, sift_db = sift.detectAndCompute(bb, None)
        sift_result = match_and_verify(sift_ka, sift_da, sift_kb, sift_db)
        sift_result["skipped"] = False
        sift_skipped_reason = None

    stage_times["verify_ms"] = round((time.perf_counter() - verify_started) * 1000, 1)
    stage_times["match_ms"] = round((time.perf_counter() - match_started) * 1000, 1)

    # 06 SCORE — EXACT ORIGINAL LUNARMATCH SCORE FORMULA
    t = time.perf_counter()
    feature_coverage = (
        len({m["a"] for m in inlier_matches})
        / max(1, len(features_a))
        * 100.0
    )
    correspondence_strength = primary["geometry"]["consistency"]
    score = float(primary["score"])
    confidence_value = float(primary["confidence_value"])
    reliability = primary["confidence_label"]
    stage_times["score_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # 07 REPORT / VISUALIZATION
    t = time.perf_counter()
    analysis_id = uuid.uuid4().hex
    result_path = RESULTS / f"correspondence_{analysis_id}.jpg"
    draw_custom_correspondence(
        aa, bb, features_a, features_b,
        reciprocal_matches, inlier_indices,
        result_path,
    )
    stage_times["report_ms"] = round((time.perf_counter() - t) * 1000, 1)
    total_ms = round((time.perf_counter() - started) * 1000, 1)

    instrument_a = identify_instrument(a_path, a_meta)
    instrument_b = identify_instrument(b_path, b_meta)

    def image_result(info, path, metadata, scale, feature_count, quality, instrument):
        return {
            "filename": path.name,
            "file_size_bytes": path.stat().st_size,
            "file_size_mb": round(path.stat().st_size / (1024 * 1024), 3),
            "format": path.suffix.lower().replace(".", "").upper(),
            "width": info["width"],
            "height": info["height"],
            "resolution": f"{info['width']} × {info['height']}",
            "channels": info["channels"],
            "color_mode": info["color_mode"],
            "valid": True,
            "processing_resolution": f"{info['gray'].shape[1]} × {info['gray'].shape[0]}",
            "processing_scale_percent": round(scale * 100, 2),
            "keypoints": feature_count,
            "feature_density_per_mp": round(
                feature_count / max(0.000001, info["width"] * info["height"] / 1_000_000),
                2,
            ),
            "quality": {
                "contrast": quality["contrast"],
                "sharpness_laplacian_variance": quality["sharpness"],
                "mean_intensity": round(float(np.mean(info["gray"])), 3),
                "dark_pixel_fraction": round(float(np.mean(info["gray"] < 20) * 100), 2),
                "bright_pixel_fraction": round(float(np.mean(info["gray"] > 235) * 100), 2),
                "quality_score": quality["quality"],
                "quality_basis": "contrast + gradient-edge sharpness",
            },
            "metadata": metadata,
            "instrument": instrument,
        }

    image_a = image_result(
        a_info, a_path, a_meta, scale_a,
        len(features_a), primary["quality_a"], instrument_a,
    )
    image_b = image_result(
        b_info, b_path, b_meta, scale_b,
        len(features_b), primary["quality_b"], instrument_b,
    )

    # Secondary SIFT diagnostics are reported, but do not replace the primary score.
    sift_verified = len(sift_result["inlier_indices"])
    sift_candidates = sift_result["ratio_candidates"]
    sift_reciprocal = len(sift_result["reciprocal_matches"])
    sift_inlier_ratio = sift_verified / max(1, len(sift_result.get("matches", []))) * 100.0
    sift_homography = sift_result["homography"] is not None

    interpretation_points = []
    interpretation_points.append(
        f"{verified} custom feature correspondences were geometrically consistent."
    )
    interpretation_points.append(
        f"{candidates} mutual patch-descriptor candidates were evaluated by affine RANSAC."
    )
    if reproj_mean is not None:
        interpretation_points.append(
            f"Mean inlier reprojection error was {reproj_mean:.2f}px."
        )
    interpretation_points.append(
        f"Primary 5×5 spatial coverage was {spatial_coverage:.2f}%."
    )
    if sift_result.get("skipped"):
        interpretation_points.append(
            "Secondary SIFT cross-check was skipped by the fast path because the primary "
            "LunarMatch evidence was already geometrically coherent."
        )
    else:
        interpretation_points.append(
            f"Secondary SIFT cross-check produced {sift_candidates} Lowe-ratio candidates, "
            f"{sift_reciprocal} reciprocal matches and {sift_verified} geometric inliers."
        )
    interpretation_points.append(
        "This result measures image-correspondence evidence; it does not by itself establish "
        "geographic identity or ground-truth lunar coordinates."
    )

    metadata_validation = {
        "image_a": {
            "latitude": status_item(a_meta.get("latitude")),
            "longitude": status_item(a_meta.get("longitude")),
            "altitude": status_item(a_meta.get("altitude")),
            "acquisition_time": status_item(a_meta.get("acquisition_time")),
            "mission": status_item(a_meta.get("mission")),
            "instrument": status_item(a_meta.get("instrument") or instrument_a.get("instrument")),
            "crs": status_item(a_meta.get("crs")),
            "projection": status_item(a_meta.get("projection")),
            "datum": status_item(a_meta.get("datum")),
            "image_id": status_item(a_meta.get("image_id")),
            "product_id": status_item(a_meta.get("product_id")),
            "provenance": status_item(a_meta.get("provenance")),
        },
        "image_b": {
            "latitude": status_item(b_meta.get("latitude")),
            "longitude": status_item(b_meta.get("longitude")),
            "altitude": status_item(b_meta.get("altitude")),
            "acquisition_time": status_item(b_meta.get("acquisition_time")),
            "mission": status_item(b_meta.get("mission")),
            "instrument": status_item(b_meta.get("instrument") or instrument_b.get("instrument")),
            "crs": status_item(b_meta.get("crs")),
            "projection": status_item(b_meta.get("projection")),
            "datum": status_item(b_meta.get("datum")),
            "image_id": status_item(b_meta.get("image_id")),
            "product_id": status_item(b_meta.get("product_id")),
            "provenance": status_item(b_meta.get("provenance")),
        },
    }

    duplicate_query_indices = max(
        0,
        candidates - len({m["a"] for m in reciprocal_matches}),
    )
    duplicate_reference_indices = max(
        0,
        candidates - len({m["b"] for m in reciprocal_matches}),
    )
    duplicate_match_detection = {
        "status": "CHECKED",
        "duplicate_query_indices": duplicate_query_indices,
        "duplicate_reference_indices": duplicate_reference_indices,
    }

    return {
        "analysis_id": analysis_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "COMPLETE",
        "raw_matches": len(raw_matches),
        "candidate_matches": candidates,
        "reciprocal_matches": candidates,
        "verified_matches": verified,
        "outliers": outliers,
        "feature_coverage": round(feature_coverage, 2),
        "correspondence_strength": round(correspondence_strength, 2),
        "inlier_ratio": round(inlier_ratio, 2),
        "geometric_consistency": round(primary["geometry"]["consistency"], 2),
        "homography_status": "ESTABLISHED" if H is not None else "NOT ESTABLISHED",
        "verification_status": verification_status,
        "transformation_quality": transform_quality["status"],
        "duplicate_match_detection": duplicate_match_detection,
        "headline": "ANALYSIS COMPLETE — CORRESPONDENCE RESULT READY",
        "overall_match": round(score, 2),
        "score": round(score, 2),
        "reliability": reliability,
        "confidence": reliability,
        "confidence_detail": {"label": reliability, "value": round(confidence_value, 2)},
        "image_quality": round((primary["quality_a"]["quality"] + primary["quality_b"]["quality"]) / 2.0, 2),
        "processing_time_ms": total_ms,
        "algorithm": {
            "feature_detector": "LUNARMATCH custom gradient/corner detector + normalized 11×11 patch descriptor",
            "max_features": 500,
            "matcher": "Brute-force normalized patch distance",
            "lowe_ratio": 0.78,
            "cross_check": "Mutual nearest-neighbor patch matching",
            "geometric_model": "Affine transform + deterministic RANSAC",
            "ransac_threshold_px": 10.0,
            "processing_max_dimension": MAX_DIMENSION,
            "secondary_cross_check": "SIFT + BFMatcher + reciprocal Lowe-ratio + homography RANSAC",
        },
        "engine_summary": {
            "primary": "Original LunarMatch custom patch-correspondence engine",
            "secondary": "Independent SIFT/BFMatcher cross-check",
            "primary_score_drives_result": True,
            "fusion_mode": "Primary score preserved; secondary engine is diagnostic cross-check only.",
        },
        "image_a": image_a,
        "image_b": image_b,
        "correspondence": {
            "raw_knn_matches": len(raw_matches),
            "lowe_ratio_candidates": candidates,
            "reciprocal_matches": candidates,
            "verified_matches": verified,
            "outliers": outliers,
            "feature_coverage_percent": round(feature_coverage, 2),
            "correspondence_strength": round(correspondence_strength, 2),
            "spatial_distribution": spatial,
            "duplicate_match_detection": duplicate_match_detection,
        },
        "geometric_verification": {
            "verification_status": verification_status,
            "model": "AFFINE",
            "homography_status": "ESTABLISHED" if H is not None else "NOT ESTABLISHED",
            "ransac": "EXECUTED" if candidates >= 3 else "NOT EXECUTED — fewer than 3 mutual patch candidates",
            "inliers": verified,
            "outliers": outliers,
            "inlier_ratio_percent": round(inlier_ratio, 2),
            "reprojection_error_mean_px": round(reproj_mean, 3) if reproj_mean is not None else None,
            "reprojection_error_median_px": round(reproj_median, 3) if reproj_median is not None else None,
            "reprojection_error_max_px": round(reproj_max, 3) if reproj_max is not None else None,
            "transformation_quality": transform_quality,
            "degenerate_geometry": degenerate,
            "spatial_coverage": spatial,
        },
        "sift_cross_check": {
            "status": "SKIPPED_FAST_PATH" if sift_result.get("skipped") else "EXECUTED",
            "reason": sift_skipped_reason,
            "raw_knn_matches": sift_result["raw_knn_matches"],
            "lowe_ratio_candidates": sift_candidates,
            "reciprocal_matches": sift_reciprocal,
            "verified_matches": sift_verified,
            "inlier_ratio_percent": round(sift_inlier_ratio, 2),
            "homography_status": "ESTABLISHED" if sift_homography else "NOT ESTABLISHED",
            "ransac_threshold_px": RANSAC_THRESHOLD,
        },
        "pipeline": {
            "01_ACQUIRE": stage_times["acquire_ms"],
            "02_PREPROCESS": stage_times["preprocess_ms"],
            "03_EXTRACT": stage_times["extract_ms"],
            "04_MATCH": stage_times["match_ms"],
            "05_VERIFY": stage_times["verify_ms"],
            "06_SCORE": stage_times["score_ms"],
            "07_REPORT": stage_times["report_ms"],
            "total_ms": total_ms,
        },
        "instrument_awareness": {
            "image_a": instrument_a,
            "image_b": instrument_b,
            "supported_payloads": [
                {"instrument": "OHRC", "mission": "Chandrayaan-2", "role": "High-resolution optical image correspondence evidence"},
                {"instrument": "TMC-2", "mission": "Chandrayaan-2", "role": "Topographic/stereo evidence when appropriate source products are supplied"},
                {"instrument": "IIRS", "mission": "Chandrayaan-2", "role": "Spectral/material evidence when actual hyperspectral data and metadata are supplied"},
            ],
            "important_limit": "Instrument support does not mean an instrument was used unless its identity is established from supplied data/metadata.",
        },
        "metadata_validation": metadata_validation,
        "interpretation": {
            "type": "evidence_based",
            "points": interpretation_points,
            "ground_truth_warning": "Image correspondence is not geographic ground truth.",
        },
        "result_image": f"/results/{result_path.name}",
        "validation_note": "Scores describe primary image correspondence/reliability evidence, not ground-truth geographic accuracy.",
    }

# =========================================================
# PDF REPORT
# =========================================================

def build_pdf(result):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import (
        getSampleStyleSheet,
        ParagraphStyle,
    )
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        Image as RLImage,
    )
    from reportlab.lib.units import mm

    pdf_path = (
        REPORTS
        / f"LUNARMATCH_Report_{result['analysis_id']}.pdf"
    )

    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="LMTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=19,
            leading=23,
            textColor=colors.HexColor(
                "#eaf4ff"
            ),
            alignment=TA_CENTER,
            spaceAfter=8,
        )
    )

    styles.add(
        ParagraphStyle(
            name="LMSection",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=colors.HexColor(
                "#6ed8ff"
            ),
            spaceBefore=10,
            spaceAfter=6,
        )
    )

    styles.add(
        ParagraphStyle(
            name="LMBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor(
                "#1b2530"
            ),
        )
    )

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=(
            "LUNARMATCH V2 Analysis Report"
        ),
    )

    story = []

    def p(text, style="LMBody"):
        story.append(
            Paragraph(
                str(text),
                styles[style],
            )
        )

    def table(rows, widths=None):
        t = Table(
            rows,
            colWidths=widths,
            repeatRows=1,
        )

        t.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.HexColor(
                            "#dcecf7"
                        ),
                    ),
                    (
                        "TEXTCOLOR",
                        (0, 0),
                        (-1, 0),
                        colors.HexColor(
                            "#0a1825"
                        ),
                    ),
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.35,
                        colors.HexColor(
                            "#b8c5cf"
                        ),
                    ),
                    (
                        "FONTNAME",
                        (0, 0),
                        (-1, 0),
                        "Helvetica-Bold",
                    ),
                    (
                        "FONTNAME",
                        (0, 1),
                        (-1, -1),
                        "Helvetica",
                    ),
                    (
                        "FONTSIZE",
                        (0, 0),
                        (-1, -1),
                        7.5,
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "TOP",
                    ),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [
                            colors.white,
                            colors.HexColor(
                                "#f5f8fa"
                            ),
                        ],
                    ),
                    (
                        "LEFTPADDING",
                        (0, 0),
                        (-1, -1),
                        4,
                    ),
                    (
                        "RIGHTPADDING",
                        (0, 0),
                        (-1, -1),
                        4,
                    ),
                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, -1),
                        4,
                    ),
                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, -1),
                        4,
                    ),
                ]
            )
        )

        story.append(t)
        story.append(
            Spacer(
                1,
                5,
            )
        )

    p(
        "LUNARMATCH V2",
        "LMTitle",
    )

    p(
        "PLANETARY IMAGE CORRESPONDENCE & "
        "VALIDATION REPORT",
        "LMBody",
    )

    p(result["headline"])

    p(
        f"Analysis ID: "
        f"{result['analysis_id']}"
    )

    p(
        f"Created: "
        f"{result['created_at']}"
    )

    story.append(
        Spacer(
            1,
            6,
        )
    )

    # -----------------------------------------------------
    # 1
    # -----------------------------------------------------

    p(
        "1. Executive Result",
        "LMSection",
    )

    table(
        [
            [
                "Metric",
                "Measured result",
            ],
            [
                "Overall match score",
                f"{result['overall_match']} / 100",
            ],
            [
                "Reliability",
                result["reliability"],
            ],
            [
                "Confidence band",
                result["confidence"],
            ],
            [
                "Average image quality",
                f"{result['image_quality']} / 100",
            ],
            [
                "Processing time",
                f"{result['processing_time_ms']} ms",
            ],
        ]
    )

    # -----------------------------------------------------
    # 2
    # -----------------------------------------------------

    p(
        "2. Input Image Analysis",
        "LMSection",
    )

    for label in (
        "image_a",
        "image_b",
    ):
        img = result[label]

        p(
            "Source image"
            if label == "image_a"
            else "Reference image"
        )

        table(
            [
                [
                    "Property",
                    "Value",
                ],
                [
                    "Filename",
                    img["filename"],
                ],
                [
                    "Resolution",
                    img["resolution"],
                ],
                [
                    "Format",
                    img["format"],
                ],
                [
                    "File size",
                    f"{img['file_size_mb']} MB",
                ],
                [
                    "Color mode",
                    img["color_mode"],
                ],
                [
                    "Keypoints",
                    img["keypoints"],
                ],
                [
                    "Feature density",
                    f"{img['feature_density_per_mp']} / MP",
                ],
                [
                    "Processing resolution",
                    img[
                        "processing_resolution"
                    ],
                ],
                [
                    "Quality score",
                    img[
                        "quality"
                    ][
                        "quality_score"
                    ],
                ],
                [
                    "Contrast",
                    img[
                        "quality"
                    ][
                        "contrast"
                    ],
                ],
                [
                    "Sharpness",
                    img[
                        "quality"
                    ][
                        "sharpness_laplacian_variance"
                    ],
                ],
                [
                    "EXIF/metadata",
                    (
                        "AVAILABLE"
                        if img[
                            "metadata"
                        ].get("available")
                        else "NOT AVAILABLE"
                    ),
                ],
                [
                    "Instrument",
                    (
                        img[
                            "instrument"
                        ].get("instrument")
                        or "NOT ESTABLISHED"
                    ),
                ],
            ]
        )

    # -----------------------------------------------------
    # 3
    # -----------------------------------------------------

    p(
        "3. Feature Correspondence",
        "LMSection",
    )

    c = result[
        "correspondence"
    ]

    table(
        [
            [
                "Metric",
                "Value",
            ],
            [
                "Raw KNN pairs",
                c[
                    "raw_knn_matches"
                ],
            ],
            [
                "Lowe-ratio candidates",
                c[
                    "lowe_ratio_candidates"
                ],
            ],
            [
                "Reciprocal matches",
                c[
                    "reciprocal_matches"
                ],
            ],
            [
                "Verified matches",
                c[
                    "verified_matches"
                ],
            ],
            [
                "Outliers",
                c["outliers"],
            ],
            [
                "Feature coverage",
                f"{c['feature_coverage_percent']}%",
            ],
            [
                "Correspondence strength",
                f"{c['correspondence_strength']} / 100",
            ],
            [
                "Spatial distribution",
                c[
                    "spatial_distribution"
                ]["status"],
            ],
            [
                "Occupied 4×4 cells",
                c[
                    "spatial_distribution"
                ]["occupied_grid_cells"],
            ],
            [
                "Duplicate check",
                c[
                    "duplicate_match_detection"
                ]["status"],
            ],
        ]
    )

    # -----------------------------------------------------
    # 4
    # -----------------------------------------------------

    p(
        "4. Geometric Verification",
        "LMSection",
    )

    g = result[
        "geometric_verification"
    ]

    table(
        [
            [
                "Metric",
                "Value",
            ],
            [
                "Verification status",
                g[
                    "verification_status"
                ],
            ],
            [
                "Model",
                g["model"],
            ],
            [
                "Primary geometry",
                g[
                    "model"
                ],
            ],
            [
                "RANSAC",
                g["ransac"],
            ],
            [
                "Inliers",
                g["inliers"],
            ],
            [
                "Outliers",
                g["outliers"],
            ],
            [
                "Inlier ratio",
                f"{g['inlier_ratio_percent']}%",
            ],
            [
                "Mean reprojection error",
                f"{g['reprojection_error_mean_px']} px",
            ],
            [
                "Median reprojection error",
                f"{g['reprojection_error_median_px']} px",
            ],
            [
                "Maximum reprojection error",
                f"{g['reprojection_error_max_px']} px",
            ],
            [
                "Transformation quality",
                g[
                    "transformation_quality"
                ]["status"],
            ],
            [
                "Degenerate geometry",
                (
                    "YES"
                    if g[
                        "degenerate_geometry"
                    ]
                    else "NO"
                ),
            ],
            [
                "Spatial coverage",
                f"{g['spatial_coverage']['coverage_percent']}%",
            ],
        ]
    )

    # -----------------------------------------------------
    # 5
    # -----------------------------------------------------

    p(
        "5. Analysis Pipeline",
        "LMSection",
    )

    pipe = result[
        "pipeline"
    ]

    table(
        [
            [
                "Stage",
                "Time",
            ],
            [
                "01 ACQUIRE",
                f"{pipe['01_ACQUIRE']} ms",
            ],
            [
                "02 PREPROCESS",
                f"{pipe['02_PREPROCESS']} ms",
            ],
            [
                "03 EXTRACT",
                f"{pipe['03_EXTRACT']} ms",
            ],
            [
                "04 MATCH",
                f"{pipe['04_MATCH']} ms",
            ],
            [
                "05 VERIFY",
                f"{pipe['05_VERIFY']} ms",
            ],
            [
                "06 SCORE",
                f"{pipe['06_SCORE']} ms",
            ],
            [
                "07 REPORT",
                f"{pipe['07_REPORT']} ms",
            ],
            [
                "TOTAL",
                f"{pipe['total_ms']} ms",
            ],
        ]
    )

    # -----------------------------------------------------
    # 6
    # -----------------------------------------------------

    p(
        "6. Correspondence Visualization",
        "LMSection",
    )

    result_img = (
        RESULTS
        / Path(
            result["result_image"]
        ).name
    )

    if result_img.exists():
        story.append(
            RLImage(
                str(result_img),
                width=180 * mm,
                height=95 * mm,
            )
        )

        story.append(
            Spacer(
                1,
                6,
            )
        )

    # -----------------------------------------------------
    # 7
    # -----------------------------------------------------

    p(
        "7. Validation & Localization",
        "LMSection",
    )

    for label in (
        "image_a",
        "image_b",
    ):
        title = (
            "Source"
            if label == "image_a"
            else "Reference"
        )

        rows = [
            [
                "Field",
                "Status",
                "Value",
            ]
        ]

        for field, item in result[
            "metadata_validation"
        ][label].items():
            rows.append(
                [
                    field.replace(
                        "_",
                        " ",
                    ).title(),
                    item["status"],
                    item["value"]
                    or "—",
                ]
            )

        p(title)
        table(rows)

    # -----------------------------------------------------
    # 8
    # -----------------------------------------------------

    p(
        "8. Chandrayaan-2 Instrument Awareness",
        "LMSection",
    )

    ia = result[
        "instrument_awareness"
    ]

    table(
        [
            [
                "Payload",
                "Platform role",
            ],
            [
                "OHRC",
                (
                    "High-resolution optical "
                    "image correspondence evidence"
                ),
            ],
            [
                "TMC-2",
                (
                    "Topographic/stereo evidence "
                    "when appropriate source "
                    "products are supplied"
                ),
            ],
            [
                "IIRS",
                (
                    "Spectral/material evidence "
                    "when actual hyperspectral "
                    "data and metadata are supplied"
                ),
            ],
        ]
    )

    p(
        "Image A identification: "
        f"{ia['image_a'].get('instrument') or 'NOT ESTABLISHED'}"
        f" — {ia['image_a']['evidence']}"
    )

    p(
        "Image B identification: "
        f"{ia['image_b'].get('instrument') or 'NOT ESTABLISHED'}"
        f" — {ia['image_b']['evidence']}"
    )

    p(
        ia["important_limit"]
    )

    # -----------------------------------------------------
    # 9
    # -----------------------------------------------------

    p(
        "9. Automated Interpretation",
        "LMSection",
    )

    for point in result[
        "interpretation"
    ]["points"]:
        p(
            "• " + point
        )

    # -----------------------------------------------------
    # 10
    # -----------------------------------------------------

    p(
        "10. Algorithm Configuration & Limitations",
        "LMSection",
    )

    alg = result[
        "algorithm"
    ]

    table(
        [
            [
                "Parameter",
                "Configuration",
            ],
            [
                "Feature detector",
                alg[
                    "feature_detector"
                ],
            ],
            [
                "Maximum features",
                alg[
                    "max_features"
                ],
            ],
            [
                "Matcher",
                alg["matcher"],
            ],
            [
                "Lowe ratio",
                alg[
                    "lowe_ratio"
                ],
            ],
            [
                "Cross-check",
                alg[
                    "cross_check"
                ],
            ],
            [
                "Geometric model",
                alg[
                    "geometric_model"
                ],
            ],
            [
                "RANSAC threshold",
                f"{alg['ransac_threshold_px']} px",
            ],
            [
                "Maximum processing dimension",
                f"{alg['processing_max_dimension']} px",
            ],
        ]
    )

    p(
        result["validation_note"]
    )

    p(
        "Evidence before assumption. "
        "Missing metadata is reported as "
        "unavailable rather than fabricated."
    )

    doc.build(story)

    return pdf_path


# =========================================================
# TEMPLATE GLOBALS
# =========================================================

@app.context_processor
def globals():
    return {
        "logged_in": bool(
            session.get("user_id")
        ),
        "user_name": session.get(
            "user_name"
        ),
    }


# =========================================================
# PAGE ROUTES
# =========================================================

@app.route("/")
def home():
    return render_template(
        "home.html"
    )


@app.route("/<page>")
def page(page):
    allowed = {
        "analyze",
        "results",
        "validation",
        "stress",
        "technology",
        "about",
        "contact",
        "signin",
        "signup",
        "history",
    }

    if page not in allowed:
        return (
            render_template(
                "404.html"
            ),
            404,
        )
        if page == "history" and not session.get("user_id"):
            return redirect("/signin")

    return render_template(
        page + ".html"
    )


# =========================================================
# AUTHENTICATION
# =========================================================

@app.post("/api/signup")
def signup():
    d = request.get_json() or {}

    name = d.get(
        "name",
        "",
    ).strip()

    email = d.get(
        "email",
        "",
    ).strip().lower()

    pw = d.get(
        "password",
        "",
    )

    if (
        not name
        or not email
        or len(pw) < 8
    ):
        return jsonify(
            error=(
                "Name, email and a password "
                "of at least 8 characters are required."
            )
        ), 400

    try:
        c = db()

        c.execute(
            """
            INSERT INTO users(
                name,
                email,
                password,
                created_at
            )
            VALUES(?,?,?,?)
            """,
            (
                name,
                email,
                generate_password_hash(pw),
                datetime.now(
                    timezone.utc
                ).isoformat(),
            ),
        )

        uid = c.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]

        guest_id = session.get("guest_id")
        migrated_history = 0

        if guest_id:
            cur = c.execute(
                """
                UPDATE analyses
                SET user_id=?
                WHERE guest_id=?
                  AND user_id IS NULL
                """,
                (uid, guest_id),
            )
            migrated_history = cur.rowcount

        c.commit()
        c.close()

        session["user_id"] = uid
        session["user_name"] = name

        return jsonify(
            ok=True,
            history_migrated=migrated_history,
            message="Account created successfully."
        )

    except sqlite3.IntegrityError:
        return jsonify(
            error=(
                "An account with that email "
                "already exists."
            )
        ), 409


@app.post("/api/signin")
def signin():
    d = request.get_json() or {}

    c = db()

    u = c.execute(
        "SELECT * FROM users WHERE email=?",
        (
            d.get(
                "email",
                "",
            )
            .strip()
            .lower(),
        ),
    ).fetchone()

    guest_id = session.get("guest_id")

    c.close()

    if (
        not u
        or not check_password_hash(
            u["password"],
            d.get(
                "password",
                "",
            ),
        )
    ):
        return jsonify(
            error="Invalid email or password."
        ), 401

    migrated_history = 0

    if guest_id:
        c = db()
        cur = c.execute(
            """
            UPDATE analyses
            SET user_id=?
            WHERE guest_id=?
              AND user_id IS NULL
            """,
            (u["id"], guest_id),
        )
        migrated_history = cur.rowcount
        c.commit()
        c.close()

    session["user_id"] = u["id"]
    session["user_name"] = u["name"]

    return jsonify(
        ok=True,
        history_migrated=migrated_history,
        message="Signed in successfully."
    )


@app.post("/api/signout")
def signout():
    session.clear()

    return jsonify(
        ok=True
    )


# =========================================================
# ANALYSIS API
# =========================================================

@app.post("/api/analyze")
def api_analyze():
    is_guest = not session.get("user_id")
    guest_id = get_guest_id() if is_guest else None

    if is_guest:
        used = guest_analysis_count(guest_id)
        remaining = max(0, FREE_GUEST_ANALYSIS_LIMIT - used)
        if remaining <= 0:
            return jsonify(
                error="Your free analysis allowance has been used.",
                code="REGISTRATION_REQUIRED",
                registration_required=True,
                free_limit=FREE_GUEST_ANALYSIS_LIMIT,
                used=used,
                remaining=0,
            ), 403

    if (
        "image_a" not in request.files
        or "image_b" not in request.files
    ):
        return jsonify(
            error=(
                "Upload Image A and Image B."
            )
        ), 400

    a = request.files[
        "image_a"
    ]

    b = request.files[
        "image_b"
    ]

    if (
        not a.filename
        or not b.filename
    ):
        return jsonify(
            error=(
                "Both image filenames "
                "are required."
            )
        ), 400

    a_suffix = Path(
        a.filename
    ).suffix.lower()

    b_suffix = Path(
        b.filename
    ).suffix.lower()

    if (
        a_suffix not in ALLOWED_EXTENSIONS
        or b_suffix not in ALLOWED_EXTENSIONS
    ):
        return jsonify(
            error=(
                "Unsupported image format."
            )
        ), 415

    aid = uuid.uuid4().hex

    ap = (
        UPLOADS
        / f"{aid}_a{a_suffix}"
    )

    bp = (
        UPLOADS
        / f"{aid}_b{b_suffix}"
    )

    a.save(ap)
    b.save(bp)

    try:
        result = analyze(
            ap,
            bp,
        )

    except Exception as exc:
        for pth in (
            ap,
            bp,
        ):
            try:
                pth.unlink(
                    missing_ok=True
                )
            except Exception:
                pass

        return jsonify(
            error=str(exc)
        ), 422

    # Normalize every response value before SQLite/Flask serialization.
    # This prevents NumPy/OpenCV/Pillow scalar objects from turning the
    # successful analysis into an HTML 500 response that the browser cannot parse.
    try:
        result = json_safe(result)
    except Exception as exc:
        app.logger.exception("Analysis JSON normalization failed")
        return jsonify(
            error=(
                "Analysis completed, but its result could not be serialized: "
                f"{exc}"
            )
        ), 500

    try:
        c = db()

        c.execute(
            """
            INSERT INTO analyses(
                id,
                user_id,
                guest_id,
                created_at,
                result_json
            )
            VALUES(?,?,?,?,?)
            """,
            (
                result["analysis_id"],
                session.get(
                    "user_id"
                ),
                guest_id,
                result["created_at"],
                json.dumps(
                    result,
                    allow_nan=False,
                ),
            ),
        )

        c.commit()
        c.close()

    except Exception as exc:
        try:
            c.close()
        except Exception:
            pass
        app.logger.exception("Analysis result persistence failed")
        return jsonify(
            error=(
                "Analysis completed but the result could not be saved: "
                f"{exc}"
            )
        ), 500

    return jsonify(
        result
    )


# =========================================================
# RESULT HISTORY / USAGE
# =========================================================

@app.get("/api/usage")
def api_usage():
    guest = not session.get("user_id")

    if guest:
        guest_id = get_guest_id()
        used = guest_analysis_count(guest_id)
        remaining = max(0, FREE_GUEST_ANALYSIS_LIMIT - used)
        return jsonify(
            authenticated=False,
            free_limit=FREE_GUEST_ANALYSIS_LIMIT,
            used=used,
            remaining=remaining,
            registration_required=remaining == 0,
        )

    c = db()
    row = c.execute(
        "SELECT COUNT(*) AS count FROM analyses WHERE user_id=?",
        (session["user_id"],),
    ).fetchone()
    c.close()

    return jsonify(
        authenticated=True,
        unlimited_access=True,
        total_analyses=int(row["count"] or 0),
        registration_required=False,
    )


def _history_rows():
    user_id = session.get("user_id")

    if user_id:
        c = db()
        rows = c.execute(
            """
            SELECT id, created_at, result_json
            FROM analyses
            WHERE user_id=?
            ORDER BY created_at DESC
            LIMIT 100
            """,
            (user_id,),
        ).fetchall()
        c.close()
        return rows

    guest_id = get_guest_id()
    c = db()
    rows = c.execute(
        """
        SELECT id, created_at, result_json
        FROM analyses
        WHERE guest_id=? AND user_id IS NULL
        ORDER BY created_at DESC
        LIMIT 100
        """,
        (guest_id,),
    ).fetchall()
    c.close()
    return rows


@app.get("/api/results")
def api_results():
    return jsonify(
        [json.loads(row["result_json"]) for row in _history_rows()]
    )


@app.get("/api/history")
def api_history():
    items = []
    for row in _history_rows():
        result = json.loads(row["result_json"])
        items.append({
            "analysis_id": row["id"],
            "created_at": row["created_at"],
            "score": result.get("overall_match", result.get("score")),
            "confidence": result.get("confidence"),
            "verified_matches": result.get("verified_matches"),
            "headline": result.get("headline", "Analysis complete"),
            "image_a": result.get("image_a", {}).get("filename"),
            "image_b": result.get("image_b", {}).get("filename"),
        })
    return jsonify(items)


def _can_access_analysis(analysis_id):
    c = db()
    row = c.execute(
        "SELECT * FROM analyses WHERE id=?",
        (analysis_id,),
    ).fetchone()
    c.close()

    if not row:
        return None

    if session.get("user_id"):
        if row["user_id"] == session["user_id"]:
            return row
        return None

    guest_id = session.get("guest_id")
    if guest_id and row["guest_id"] == guest_id and row["user_id"] is None:
        return row

    return None


@app.get("/api/history/<analysis_id>")
def api_history_item(analysis_id):
    row = _can_access_analysis(analysis_id)
    if not row:
        return jsonify(error="Analysis not found."), 404

    return jsonify(json.loads(row["result_json"]))


# =========================================================
# PDF REPORT API
# =========================================================

@app.get("/api/report/<analysis_id>")
def api_report(analysis_id):
    c = db()

    row = c.execute(
        """
        SELECT result_json
        FROM analyses
        WHERE id=?
        """,
        (
            analysis_id,
        ),
    ).fetchone()

    c.close()

    if not row:
        return jsonify(
            error="Analysis not found."
        ), 404

    result = json.loads(
        row["result_json"]
    )

    pdf_path = build_pdf(
        result
    )

    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=(
            f"LUNARMATCH_Report_"
            f"{analysis_id}.pdf"
        ),
        mimetype="application/pdf",
    )


# =========================================================
# HEALTH
# =========================================================

@app.get("/api/health")
def health():
    return jsonify(
        status="online",
        service="LUNARMATCH V2",
        engine=(
            "Original LunarMatch custom patch "
            "correspondence + SIFT cross-check"
        ),
        validation=(
            "metadata-aware; "
            "no coordinate fabrication"
        ),
        report="PDF enabled",
        instrument_awareness=[
            "OHRC",
            "TMC-2",
            "IIRS",
        ],
    )


# =========================================================
# RESULT IMAGE FILES
# =========================================================

@app.route("/results/<path:name>")
def result_file(name):
    return send_from_directory(
        RESULTS,
        name,
    )


# =========================================================
# ERROR HANDLING
# =========================================================

@app.errorhandler(Exception)
def internal_server_error(error):
    # Keep API failures machine-readable so the Analyze page can display
    # the actual server error instead of reporting only "invalid response".
    app.logger.exception("Unhandled LUNARMATCH server error")
    return jsonify(
        error=(
            "Internal analysis server error: "
            f"{error}"
        )
    ), 500

@app.errorhandler(413)
def too_large(e):
    return jsonify(
        error=(
            "Maximum upload size "
            "is 25 MB."
        )
    ), 413


# =========================================================
# LOCAL DEVELOPMENT
# =========================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000,
            )
        ),
        debug=False,
    )
