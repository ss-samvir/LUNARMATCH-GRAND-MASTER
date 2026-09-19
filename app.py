import os, json, sqlite3, uuid, math, time, re, tempfile
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, render_template, request, jsonify, session, send_from_directory, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image, ExifTags, ImageStat
import cv2
import numpy as np

BASE = Path(__file__).resolve().parent
UPLOADS = BASE / "uploads"
RESULTS = BASE / "results"
REPORTS = BASE / "reports"
DB = BASE / "lunarmatch.db"

for folder in (UPLOADS, RESULTS, REPORTS):
    folder.mkdir(exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "change-this-in-production")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

MAX_DIMENSION = 1600
MAX_FEATURES = 5000
LOWE_RATIO = 0.80
RANSAC_THRESHOLD = 5.0
MIN_IMAGE_SIDE = 32
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


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
    c.commit()
    c.close()


init_db()


def safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


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
        return {"status": "NOT APPLICABLE", "value": None}
    if value in (None, "", [], {}):
        return {"status": "NOT AVAILABLE", "value": None}
    return {"status": "VERIFIED" if verified else "AVAILABLE", "value": value}


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

    if any(k in haystack for k in ("OHRC", "ORBITER HIGH RESOLUTION CAMERA")):
        return {
            "status": "IDENTIFIED",
            "instrument": "OHRC",
            "mission": "Chandrayaan-2",
            "evidence": "Recognized from supplied filename/metadata."
        }

    if any(k in haystack for k in ("TMC-2", "TMC2", "TMC_2", "TMC 2", "TERRAIN MAPPING CAMERA")):
        return {
            "status": "IDENTIFIED",
            "instrument": "TMC-2",
            "mission": "Chandrayaan-2",
            "evidence": "Recognized from supplied filename/metadata."
        }

    if any(k in haystack for k in ("IIRS", "IMAGING INFRARED SPECTROMETER")):
        return {
            "status": "IDENTIFIED",
            "instrument": "IIRS",
            "mission": "Chandrayaan-2",
            "evidence": "Recognized from supplied filename/metadata."
        }

    return {
        "status": "NOT ESTABLISHED",
        "instrument": None,
        "mission": metadata.get("mission"),
        "evidence": "No reliable Chandrayaan-2 payload identifier was found."
    }


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
        tags = {ExifTags.TAGS.get(k, k): v for k, v in ex.items()}

        out["camera"] = tags.get("Model") or tags.get("Make")
        out["acquisition_time"] = tags.get("DateTimeOriginal") or tags.get("DateTime")

        gps = tags.get("GPSInfo")
        if gps:
            gps2 = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps.items()}
            lat = gps2.get("GPSLatitude")
            lon = gps2.get("GPSLongitude")

            if lat and lon:
                lat_v = gps_decimal(lat)
                lon_v = gps_decimal(lon)
                if lat_v is not None:
                    out["latitude"] = lat_v * (-1 if str(gps2.get("GPSLatitudeRef", "")).upper() == "S" else 1)
                if lon_v is not None:
                    out["longitude"] = lon_v * (-1 if str(gps2.get("GPSLongitudeRef", "")).upper() == "W" else 1)

            if gps2.get("GPSAltitude") is not None:
                out["altitude"] = gps_decimal(gps2.get("GPSAltitude"))

        side = path.with_suffix(".json")
        if side.exists():
            data = json.loads(side.read_text(encoding="utf-8"))
            aliases = {
                "instrument": ["instrument", "payload"],
                "mission": ["mission"],
                "image_id": ["image_id", "imageId"],
                "product_id": ["product_id", "productId"],
                "provenance": ["provenance", "source"],
                "crs": ["crs"],
                "projection": ["projection"],
                "datum": ["datum"],
                "latitude": ["latitude", "lat"],
                "longitude": ["longitude", "lon"],
                "altitude": ["altitude"],
                "acquisition_time": ["acquisition_time", "acquisitionTime", "date_time"],
            }

            for target, keys in aliases.items():
                for key in keys:
                    if data.get(key) not in (None, ""):
                        out[target] = data[key]
                        break

            out["source"] = "Embedded metadata + supplied reference metadata"

        out["available"] = any(
            out[k] not in (None, "", [], {})
            for k in out
            if k not in ("available", "source")
        )
    except Exception as exc:
        out["metadata_error"] = str(exc)

    return out


def image_info(path):
    im = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if im is None:
        raise ValueError("Unsupported or unreadable image.")

    h, w = im.shape[:2]
    if min(h, w) < MIN_IMAGE_SIDE:
        raise ValueError(f"Image is too small. Minimum dimension is {MIN_IMAGE_SIDE}px.")

    channels = 1 if im.ndim == 2 else im.shape[2]
    color_mode = "GRAYSCALE" if channels == 1 else f"{channels}-CHANNEL"

    if im.ndim == 2:
    gray = im
elif im.shape[2] == 4:
    gray = cv2.cvtColor(im, cv2.COLOR_BGRA2GRAY)
else:
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)

    return {
        "image": im,
        "gray": gray,
        "width": w,
        "height": h,
        "channels": channels,
        "color_mode": color_mode,
        "dtype": str(im.dtype),
    }


def quality_metrics(gray):
    gray_f = gray.astype(np.float32)
    contrast = float(np.std(gray_f))
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    mean = float(np.mean(gray_f))
    dark_fraction = float(np.mean(gray_f < 20))
    bright_fraction = float(np.mean(gray_f > 235))

    # These are image-quality indicators, not scientific truth scores.
    contrast_component = min(100.0, contrast / 0.64)
    sharpness_component = min(100.0, math.log1p(sharpness) / math.log1p(1200) * 100)
    exposure_component = max(0.0, 100.0 - (dark_fraction + bright_fraction) * 180)

    quality = round(
        max(0.0, min(100.0, contrast_component * 0.4 + sharpness_component * 0.4 + exposure_component * 0.2)),
        2,
    )

    return {
        "contrast": round(contrast, 3),
        "sharpness_laplacian_variance": round(sharpness, 3),
        "mean_intensity": round(mean, 3),
        "dark_pixel_fraction": round(dark_fraction * 100, 2),
        "bright_pixel_fraction": round(bright_fraction * 100, 2),
        "quality_score": quality,
        "quality_basis": "contrast + Laplacian sharpness + exposure balance",
    }


def resize_once(gray):
    h, w = gray.shape
    scale = min(1.0, MAX_DIMENSION / max(h, w))
    if scale < 1:
        resized = cv2.resize(gray, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    else:
        resized = gray

    return resized, scale


def match_and_verify(ka, da, kb, db):
    bf = cv2.BFMatcher(cv2.NORM_L2)

    raw_knn = []
    ratio_matches = []

    if da is not None and db is not None and len(da) >= 2 and len(db) >= 2:
        raw_knn = bf.knnMatch(da, db, k=2)
        ratio_matches = [
            pair[0]
            for pair in raw_knn
            if len(pair) == 2 and pair[0].distance < LOWE_RATIO * pair[1].distance
        ]

    reciprocal_matches = []
    reverse_best = {}

    if da is not None and db is not None and len(da) >= 2 and len(db) >= 2:
        reverse_knn = bf.knnMatch(db, da, k=2)
        for pair in reverse_knn:
            if len(pair) == 2 and pair[0].distance < LOWE_RATIO * pair[1].distance:
                reverse_best[pair[0].queryIdx] = pair[0].trainIdx

        reciprocal_matches = [
            m for m in ratio_matches
            if reverse_best.get(m.trainIdx) == m.queryIdx
        ]

    H = None
    mask = None
    reprojection_errors = []

    if len(reciprocal_matches) >= 4:
        src = np.float32([ka[m.queryIdx].pt for m in reciprocal_matches]).reshape(-1, 1, 2)
        dst = np.float32([kb[m.trainIdx].pt for m in reciprocal_matches]).reshape(-1, 1, 2)

        H, mask = cv2.findHomography(src, dst, cv2.RANSAC, RANSAC_THRESHOLD)

        if H is not None and mask is not None:
            projected = cv2.perspectiveTransform(src, H)
            errors = np.linalg.norm(projected - dst, axis=2).reshape(-1)
            reprojection_errors = errors.tolist()

    inlier_indices = []
    if mask is not None:
        inlier_indices = [i for i, flag in enumerate(mask.ravel()) if int(flag) == 1]

    return {
        "raw_knn_matches": len(raw_knn),
        "ratio_candidates": len(ratio_matches),
        "reciprocal_matches": len(reciprocal_matches),
        "inlier_indices": inlier_indices,
        "reprojection_errors": reprojection_errors,
        "homography": H,
        "matches": reciprocal_matches,
    }


def spatial_distribution(matches, keypoints, width, height):
    if not matches or not keypoints:
        return {
            "status": "INSUFFICIENT",
            "occupied_grid_cells": 0,
            "grid_cells_total": 16,
            "coverage_percent": 0.0,
        }

    cells = set()
    for m in matches:
        x, y = keypoints[m.queryIdx].pt
        gx = min(3, max(0, int(x / max(width, 1) * 4)))
        gy = min(3, max(0, int(y / max(height, 1) * 4)))
        cells.add((gx, gy))

    coverage = len(cells) / 16 * 100

    return {
        "status": "GOOD" if coverage >= 50 else "LIMITED",
        "occupied_grid_cells": len(cells),
        "grid_cells_total": 16,
        "coverage_percent": round(coverage, 2),
    }


def transformation_quality(H):
    if H is None:
        return {
            "status": "NOT ESTABLISHED",
            "determinant": None,
            "condition_number": None,
        }

    try:
        h33 = H / H[2, 2] if abs(H[2, 2]) > 1e-12 else H
        determinant = float(np.linalg.det(h33[:2, :2]))
        condition = float(np.linalg.cond(h33[:2, :2]))

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
            "determinant": round(determinant, 6),
            "condition_number": round(condition, 3),
        }
    except Exception:
        return {"status": "UNDETERMINED", "determinant": None, "condition_number": None}


def draw_correspondence(a_gray, ka, kb, matches, inlier_indices, out_path):
    if not matches:
        # A clean side-by-side image is more honest than drawing meaningless lines.
        h = max(a_gray.shape[0], 1)
        blank = np.zeros((h, max(a_gray.shape[1], 1) * 2), dtype=np.uint8)
        cv2.imwrite(str(out_path), blank)
        return

    draw_matches = []
    inlier_set = set(inlier_indices)

    for i, m in enumerate(matches):
        # Preserve both inliers and outliers so the visualization represents verification.
        draw_matches.append(m)

    flags = cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS
    # Green/default OpenCV line rendering is not relied upon for scientific status;
    # the report separately provides the exact counts.
    canvas = cv2.drawMatches(
        a_gray,
        ka,
        a_gray,
        kb,
        draw_matches,
        None,
        flags=flags,
    )

    # Add an explicit legend-like header to the generated visualization.
    cv2.rectangle(canvas, (0, 0), (canvas.shape[1], 34), (12, 16, 24), -1)
    cv2.putText(
        canvas,
        f"RECIPROCAL MATCHES: {len(matches)} | VERIFIED INLIERS: {len(inlier_indices)} | OUTLIERS: {len(matches)-len(inlier_indices)}",
        (12, 23),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        (235, 240, 248),
        1,
        cv2.LINE_AA,
    )

    cv2.imwrite(str(out_path), canvas)


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

    # 03 EXTRACT
    t = time.perf_counter()
    sift = cv2.SIFT_create(
        nfeatures=MAX_FEATURES,
        contrastThreshold=0.02,
    )
    ka, da = sift.detectAndCompute(aa, None)
    kb, db_desc = sift.detectAndCompute(bb, None)
    stage_times["extract_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # 04 MATCH
    t = time.perf_counter()
    match_result = match_and_verify(ka, da, kb, db_desc)
    stage_times["match_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # 05 VERIFY
    t = time.perf_counter()
    reciprocal = match_result["matches"]
    inlier_indices = match_result["inlier_indices"]
    verified = len(inlier_indices)
    candidates = len(reciprocal)
    outliers = max(0, candidates - verified)

    inlier_ratio = verified / candidates * 100 if candidates else 0.0
    spatial = spatial_distribution(reciprocal, ka, aa.shape[1], aa.shape[0])
    reproj = match_result["reprojection_errors"]
    inlier_errors = [reproj[i] for i in inlier_indices if i < len(reproj)]
    reproj_mean = float(np.mean(inlier_errors)) if inlier_errors else None
    reproj_median = float(np.median(inlier_errors)) if inlier_errors else None
    reproj_max = float(np.max(inlier_errors)) if inlier_errors else None

    degenerate = False
    if verified >= 4:
        src_pts = np.float32([ka[reciprocal[i].queryIdx].pt for i in inlier_indices])
        dst_pts = np.float32([kb[reciprocal[i].trainIdx].pt for i in inlier_indices])
        if len(src_pts) >= 4:
            degenerate = (
                np.linalg.matrix_rank(src_pts - src_pts.mean(axis=0)) < 2
                or np.linalg.matrix_rank(dst_pts - dst_pts.mean(axis=0)) < 2
            )

    geom = transformation_quality(match_result["homography"])
    verification_status = (
        "VERIFIED"
        if verified >= 4 and not degenerate and match_result["homography"] is not None
        else "INSUFFICIENT"
    )
    stage_times["verify_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # 06 SCORE
    t = time.perf_counter()
    feature_coverage = (
        len({reciprocal[i].queryIdx for i in inlier_indices}) / max(1, len(ka)) * 100
    )
    correspondence_strength = min(
        100.0,
        inlier_ratio * 0.65 + min(100.0, feature_coverage) * 0.2 + spatial["coverage_percent"] * 0.15,
    )

    if verified >= 8 and inlier_ratio >= 50 and spatial["coverage_percent"] >= 40:
        reliability = "HIGH"
    elif verified >= 5 and inlier_ratio >= 30:
        reliability = "MODERATE"
    elif verified >= 1:
        reliability = "LOW"
    else:
        reliability = "INSUFFICIENT"

    score = min(
        100.0,
        verified / max(1, min(len(ka), len(kb))) * 100 * 0.35
        + inlier_ratio * 0.35
        + spatial["coverage_percent"] * 0.15
        + min(100.0, correspondence_strength) * 0.15,
    )

    if verification_status != "VERIFIED":
        score = min(score, 39.99)

    stage_times["score_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # 07 REPORT / VISUALIZATION
    t = time.perf_counter()
    analysis_id = uuid.uuid4().hex
    result_path = RESULTS / f"correspondence_{analysis_id}.jpg"

    # Draw on the two actual processed images, not duplicate Image A panels.
    if len(reciprocal) > 0:
        canvas = cv2.drawMatches(
            aa,
            ka,
            bb,
            kb,
            reciprocal,
            None,
            flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
        )
        cv2.rectangle(canvas, (0, 0), (canvas.shape[1], 38), (10, 14, 22), -1)
        cv2.putText(
            canvas,
            f"CORRESPONDENCE MAP | RECIPROCAL {len(reciprocal)} | INLIERS {verified} | OUTLIERS {outliers}",
            (12, 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (235, 240, 248),
            1,
            cv2.LINE_AA,
        )
        cv2.imwrite(str(result_path), canvas)
    else:
        # Explicit no-match visualization.
        h = max(aa.shape[0], bb.shape[0])
        w = aa.shape[1] + bb.shape[1]
        canvas = np.zeros((h, w), dtype=np.uint8)
        canvas[:aa.shape[0], :aa.shape[1]] = aa
        canvas[:bb.shape[0], aa.shape[1]:] = bb
        cv2.rectangle(canvas, (0, 0), (w, 38), (10, 14, 22), -1)
        cv2.putText(
            canvas,
            "CORRESPONDENCE MAP | NO VALID RECIPROCAL MATCHES",
            (12, 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (235, 240, 248),
            1,
            cv2.LINE_AA,
        )
        cv2.imwrite(str(result_path), canvas)

    stage_times["report_ms"] = round((time.perf_counter() - t) * 1000, 1)

    total_ms = round((time.perf_counter() - started) * 1000, 1)

    instrument_a = identify_instrument(a_path, a_meta)
    instrument_b = identify_instrument(b_path, b_meta)

    def image_result(info, path, metadata, scale, keypoints):
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
            "processing_resolution": f"{keypoints['processing_width']} × {keypoints['processing_height']}",
            "processing_scale_percent": round(scale * 100, 2),
            "keypoints": keypoints["count"],
            "feature_density_per_mp": round(
                keypoints["count"] / max(0.000001, info["width"] * info["height"] / 1_000_000),
                2,
            ),
            "quality": quality_metrics(info["gray"]),
            "metadata": metadata,
            "instrument": identify_instrument(path, metadata),
        }

    image_a = image_result(
        a_info,
        a_path,
        a_meta,
        scale_a,
        {
            "count": len(ka),
            "processing_width": aa.shape[1],
            "processing_height": aa.shape[0],
        },
    )

    image_b = image_result(
        b_info,
        b_path,
        b_meta,
        scale_b,
        {
            "count": len(kb),
            "processing_width": bb.shape[1],
            "processing_height": bb.shape[0],
        },
    )

    interpretation_points = []

    if verification_status == "VERIFIED":
        interpretation_points.append(
            f"{verified} reciprocal correspondences survived geometric verification."
        )
        interpretation_points.append(
            f"Inlier ratio is {inlier_ratio:.2f}% with mean inlier reprojection error "
            f"{reproj_mean:.2f}px." if reproj_mean is not None
            else "A geometric model was established, but reprojection error could not be summarized."
        )
        interpretation_points.append(
            f"Spatial feature coverage is {spatial['coverage_percent']:.2f}% of the 4×4 source grid."
        )
    else:
        interpretation_points.append(
            "The available evidence was insufficient to establish a reliable geometric correspondence."
        )
        if candidates == 0:
            interpretation_points.append("No reciprocal Lowe-ratio matches were available for verification.")
        elif verified == 0:
            interpretation_points.append(
                f"{candidates} reciprocal candidates were found, but none survived RANSAC verification."
            )
        if degenerate:
            interpretation_points.append("The candidate geometry was detected as degenerate.")

    interpretation_points.append(
        "This result measures image correspondence evidence; it does not by itself establish geographic identity or ground-truth lunar coordinates."
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

result = {
    "analysis_id": analysis_id,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "status": "COMPLETE",

    # Frontend-compatible summary fields
    "raw_matches": match_result["raw_knn_matches"],
    "candidate_matches": match_result["ratio_candidates"],
    "reciprocal_matches": match_result["reciprocal_matches"],
    "verified_matches": verified,
    "outliers": outliers,
    "feature_coverage": round(feature_coverage, 2),
    "correspondence_strength": round(correspondence_strength, 2),
    "inlier_ratio": round(inlier_ratio, 2),
    "geometric_consistency": round(
        max(0.0, 100.0 - (reproj_mean or 0.0) * 10.0)
        if reproj_mean is not None else 0.0,
        2
    ),
    "homography_status": (
        "ESTABLISHED"
        if match_result["homography"] is not None
        else "NOT ESTABLISHED"
    ),
    "verification_status": verification_status,
    "transformation_quality": geom["status"],
    "duplicate_match_detection": {
        "status": "CHECKED",
        "duplicate_query_indices": max(
            0,
            len(reciprocal) - len({m.queryIdx for m in reciprocal})
        ),
        "duplicate_reference_indices": max(
            0,
            len(reciprocal) - len({m.trainIdx for m in reciprocal})
        ),
    },

    "headline": "ANALYSIS COMPLETE — CORRESPONDENCE RESULT READY",
        "headline": "ANALYSIS COMPLETE — CORRESPONDENCE RESULT READY",
        "overall_match": round(score, 2),
        "score": round(score, 2),
        "reliability": reliability,
        "confidence": reliability,
        "image_quality": round((image_a["quality"]["quality_score"] + image_b["quality"]["quality_score"]) / 2, 2),
        "processing_time_ms": total_ms,
        "algorithm": {
            "feature_detector": "SIFT",
            "max_features": MAX_FEATURES,
            "matcher": "BFMatcher / L2",
            "lowe_ratio": LOWE_RATIO,
            "cross_check": "reciprocal Lowe-ratio verification",
            "geometric_model": "Homography + RANSAC",
            "ransac_threshold_px": RANSAC_THRESHOLD,
            "processing_max_dimension": MAX_DIMENSION,
        },
        "image_a": image_a,
        "image_b": image_b,
        "correspondence": {
            "raw_knn_matches": match_result["raw_knn_matches"],
            "lowe_ratio_candidates": match_result["ratio_candidates"],
            "reciprocal_matches": match_result["reciprocal_matches"],
            "verified_matches": verified,
            "outliers": outliers,
            "feature_coverage_percent": round(feature_coverage, 2),
            "correspondence_strength": round(correspondence_strength, 2),
            "spatial_distribution": spatial,
"duplicate_match_detection": {
    "status": "CHECKED",
    "duplicate_query_indices": max(
        0,
        len(reciprocal) - len({m.queryIdx for m in reciprocal})
    ),
    "duplicate_reference_indices": max(
        0,
        len(reciprocal) - len({m.trainIdx for m in reciprocal})
    ),
},
        },
        "geometric_verification": {
            "verification_status": verification_status,
            "model": "HOMOGRAPHY",
            "homography_status": "ESTABLISHED" if match_result["homography"] is not None else "NOT ESTABLISHED",
            "ransac": "EXECUTED" if len(reciprocal) >= 4 else "NOT EXECUTED — fewer than 4 reciprocal matches",
            "inliers": verified,
            "outliers": outliers,
            "inlier_ratio_percent": round(inlier_ratio, 2),
            "reprojection_error_mean_px": round(reproj_mean, 3) if reproj_mean is not None else None,
            "reprojection_error_median_px": round(reproj_median, 3) if reproj_median is not None else None,
            "reprojection_error_max_px": round(reproj_max, 3) if reproj_max is not None else None,
            "transformation_quality": geom,
            "degenerate_geometry": degenerate,
            "spatial_coverage": spatial,
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
                {
                    "instrument": "OHRC",
                    "mission": "Chandrayaan-2",
                    "role": "High-resolution optical image correspondence evidence",
                },
                {
                    "instrument": "TMC-2",
                    "mission": "Chandrayaan-2",
                    "role": "Topographic/stereo evidence when appropriate source products are supplied",
                },
                {
                    "instrument": "IIRS",
                    "mission": "Chandrayaan-2",
                    "role": "Spectral/material evidence when actual hyperspectral data and metadata are supplied",
                },
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
        "validation_note": "Scores describe correspondence/reliability evidence, not ground-truth geographic accuracy.",
    }

    return result


def build_pdf(result):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image as RLImage, PageBreak
    )
    from reportlab.lib.units import mm

    pdf_path = REPORTS / f"LUNARMATCH_Report_{result['analysis_id']}.pdf"

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="LMTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=23,
        textColor=colors.HexColor("#eaf4ff"),
        alignment=TA_CENTER,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="LMSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#6ed8ff"),
        spaceBefore=10,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="LMBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1b2530"),
    ))

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="LUNARMATCH V2 Analysis Report",
    )

    story = []

    def p(text, style="LMBody"):
        story.append(Paragraph(str(text), styles[style]))

    def table(rows, widths=None):
        t = Table(rows, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dcecf7")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0a1825")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b8c5cf")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f8fa")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 5))

    p("LUNARMATCH V2", "LMTitle")
    p("PLANETARY IMAGE CORRESPONDENCE & VALIDATION REPORT", "LMBody")
    p(result["headline"])
    p(f"Analysis ID: {result['analysis_id']}")
    p(f"Created: {result['created_at']}")

    story.append(Spacer(1, 6))
    p("1. Executive Result", "LMSection")
    table([
        ["Metric", "Measured result"],
        ["Overall match score", f"{result['overall_match']} / 100"],
        ["Reliability", result["reliability"]],
        ["Confidence band", result["confidence"]],
        ["Average image quality", f"{result['image_quality']} / 100"],
        ["Processing time", f"{result['processing_time_ms']} ms"],
    ])

    p("2. Input Image Analysis", "LMSection")
    for label in ("image_a", "image_b"):
        img = result[label]
        p(f"{'Source' if label == 'image_a' else 'Reference'} image")
        table([
            ["Property", "Value"],
            ["Filename", img["filename"]],
            ["Resolution", img["resolution"]],
            ["Format", img["format"]],
            ["File size", f"{img['file_size_mb']} MB"],
            ["Color mode", img["color_mode"]],
            ["Keypoints", img["keypoints"]],
            ["Feature density", f"{img['feature_density_per_mp']} / MP"],
            ["Processing resolution", img["processing_resolution"]],
            ["Quality score", img["quality"]["quality_score"]],
            ["Contrast", img["quality"]["contrast"]],
            ["Sharpness", img["quality"]["sharpness_laplacian_variance"]],
            ["EXIF/metadata", "AVAILABLE" if img["metadata"].get("available") else "NOT AVAILABLE"],
            ["Instrument", img["instrument"].get("instrument") or "NOT ESTABLISHED"],
        ])

    p("3. Feature Correspondence", "LMSection")
    c = result["correspondence"]
    table([
        ["Metric", "Value"],
        ["Raw KNN pairs", c["raw_knn_matches"]],
        ["Lowe-ratio candidates", c["lowe_ratio_candidates"]],
        ["Reciprocal matches", c["reciprocal_matches"]],
        ["Verified matches", c["verified_matches"]],
        ["Outliers", c["outliers"]],
        ["Feature coverage", f"{c['feature_coverage_percent']}%"],
        ["Correspondence strength", f"{c['correspondence_strength']} / 100"],
        ["Spatial distribution", c["spatial_distribution"]["status"]],
        ["Occupied 4×4 cells", c["spatial_distribution"]["occupied_grid_cells"]],
        ["Duplicate check", c["duplicate_match_detection"]["status"]],
    ])

    p("4. Geometric Verification", "LMSection")
    g = result["geometric_verification"]
    table([
        ["Metric", "Value"],
        ["Verification status", g["verification_status"]],
        ["Model", g["model"]],
        ["Homography", g["homography_status"]],
        ["RANSAC", g["ransac"]],
        ["Inliers", g["inliers"]],
        ["Outliers", g["outliers"]],
        ["Inlier ratio", f"{g['inlier_ratio_percent']}%"],
        ["Mean reprojection error", f"{g['reprojection_error_mean_px']} px"],
        ["Median reprojection error", f"{g['reprojection_error_median_px']} px"],
        ["Maximum reprojection error", f"{g['reprojection_error_max_px']} px"],
        ["Transformation quality", g["transformation_quality"]["status"]],
        ["Degenerate geometry", "YES" if g["degenerate_geometry"] else "NO"],
        ["Spatial coverage", f"{g['spatial_coverage']['coverage_percent']}%"],
    ])

    p("5. Analysis Pipeline", "LMSection")
    pipe = result["pipeline"]
    table([
        ["Stage", "Time"],
        ["01 ACQUIRE", f"{pipe['01_ACQUIRE']} ms"],
        ["02 PREPROCESS", f"{pipe['02_PREPROCESS']} ms"],
        ["03 EXTRACT", f"{pipe['03_EXTRACT']} ms"],
        ["04 MATCH", f"{pipe['04_MATCH']} ms"],
        ["05 VERIFY", f"{pipe['05_VERIFY']} ms"],
        ["06 SCORE", f"{pipe['06_SCORE']} ms"],
        ["07 REPORT", f"{pipe['07_REPORT']} ms"],
        ["TOTAL", f"{pipe['total_ms']} ms"],
    ])

    p("6. Correspondence Visualization", "LMSection")
    result_img = RESULTS / Path(result["result_image"]).name
    if result_img.exists():
        story.append(RLImage(str(result_img), width=180 * mm, height=95 * mm))
        story.append(Spacer(1, 6))

    p("7. Validation & Localization", "LMSection")
    for label in ("image_a", "image_b"):
        title = "Source" if label == "image_a" else "Reference"
        rows = [["Field", "Status", "Value"]]
        for field, item in result["metadata_validation"][label].items():
            rows.append([field.replace("_", " ").title(), item["status"], item["value"] or "—"])
        p(title)
        table(rows)

    p("8. Chandrayaan-2 Instrument Awareness", "LMSection")
    ia = result["instrument_awareness"]
    table([
        ["Payload", "Platform role"],
        ["OHRC", "High-resolution optical image correspondence evidence"],
        ["TMC-2", "Topographic/stereo evidence when appropriate source products are supplied"],
        ["IIRS", "Spectral/material evidence when actual hyperspectral data and metadata are supplied"],
    ])
    p(
        f"Image A identification: {ia['image_a'].get('instrument') or 'NOT ESTABLISHED'} — {ia['image_a']['evidence']}"
    )
    p(
        f"Image B identification: {ia['image_b'].get('instrument') or 'NOT ESTABLISHED'} — {ia['image_b']['evidence']}"
    )
    p(ia["important_limit"])

    p("9. Automated Interpretation", "LMSection")
    for point in result["interpretation"]["points"]:
        p("• " + point)

    p("10. Algorithm Configuration & Limitations", "LMSection")
    alg = result["algorithm"]
    table([
        ["Parameter", "Configuration"],
        ["Feature detector", alg["feature_detector"]],
        ["Maximum features", alg["max_features"]],
        ["Matcher", alg["matcher"]],
        ["Lowe ratio", alg["lowe_ratio"]],
        ["Cross-check", alg["cross_check"]],
        ["Geometric model", alg["geometric_model"]],
        ["RANSAC threshold", f"{alg['ransac_threshold_px']} px"],
        ["Maximum processing dimension", f"{alg['processing_max_dimension']} px"],
    ])
    p(result["validation_note"])
    p("Evidence before assumption. Missing metadata is reported as unavailable rather than fabricated.")

    doc.build(story)
    return pdf_path


@app.context_processor
def globals():
    return {
        "logged_in": bool(session.get("user_id")),
        "user_name": session.get("user_name"),
    }


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/<page>")
def page(page):
    allowed = {
        "analyze", "results", "validation", "stress", "technology",
        "about", "contact", "signin", "signup"
    }
    if page not in allowed:
        return render_template("404.html"), 404
    return render_template(page + ".html")


@app.post("/api/signup")
def signup():
    d = request.get_json() or {}
    name = d.get("name", "").strip()
    email = d.get("email", "").strip().lower()
    pw = d.get("password", "")

    if not name or not email or len(pw) < 8:
        return jsonify(error="Name, email and a password of at least 8 characters are required."), 400

    try:
        c = db()
        c.execute(
            "INSERT INTO users(name,email,password,created_at) VALUES(?,?,?,?)",
            (name, email, generate_password_hash(pw), datetime.now(timezone.utc).isoformat()),
        )
        c.commit()
        uid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.close()
        session["user_id"] = uid
        session["user_name"] = name
        return jsonify(ok=True)
    except sqlite3.IntegrityError:
        return jsonify(error="An account with that email already exists."), 409


@app.post("/api/signin")
def signin():
    d = request.get_json() or {}
    c = db()
    u = c.execute(
        "SELECT * FROM users WHERE email=?",
        (d.get("email", "").strip().lower(),),
    ).fetchone()
    c.close()

    if not u or not check_password_hash(u["password"], d.get("password", "")):
        return jsonify(error="Invalid email or password."), 401

    session["user_id"] = u["id"]
    session["user_name"] = u["name"]
    return jsonify(ok=True)


@app.post("/api/signout")
def signout():
    session.clear()
    return jsonify(ok=True)


@app.post("/api/analyze")
def api_analyze():
    if "image_a" not in request.files or "image_b" not in request.files:
        return jsonify(error="Upload Image A and Image B."), 400

    a = request.files["image_a"]
    b = request.files["image_b"]

    if not a.filename or not b.filename:
        return jsonify(error="Both image filenames are required."), 400

    a_suffix = Path(a.filename).suffix.lower()
    b_suffix = Path(b.filename).suffix.lower()

    if a_suffix not in ALLOWED_EXTENSIONS or b_suffix not in ALLOWED_EXTENSIONS:
        return jsonify(error="Unsupported image format."), 415

    aid = uuid.uuid4().hex
    ap = UPLOADS / f"{aid}_a{a_suffix}"
    bp = UPLOADS / f"{aid}_b{b_suffix}"

    a.save(ap)
    b.save(bp)

    try:
        result = analyze(ap, bp)
    except Exception as exc:
        for pth in (ap, bp):
            try:
                pth.unlink(missing_ok=True)
            except Exception:
                pass
        return jsonify(error=str(exc)), 422

    c = db()
    c.execute(
        "INSERT INTO analyses(id,user_id,created_at,result_json) VALUES(?,?,?,?)",
        (
            result["analysis_id"],
            session.get("user_id"),
            result["created_at"],
            json.dumps(result),
        ),
    )
    c.commit()
    c.close()

    return jsonify(result)


@app.get("/api/results")
def api_results():
    c = db()
    if session.get("user_id"):
        rows = c.execute(
            "SELECT id,created_at,result_json FROM analyses WHERE user_id=? OR user_id IS NULL ORDER BY created_at DESC LIMIT 30",
            (session.get("user_id"),),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT id,created_at,result_json FROM analyses WHERE user_id IS NULL ORDER BY created_at DESC LIMIT 30"
        ).fetchall()
    c.close()
    return jsonify([json.loads(r["result_json"]) for r in rows])


@app.get("/api/report/<analysis_id>")
def api_report(analysis_id):
    c = db()
    row = c.execute(
        "SELECT result_json FROM analyses WHERE id=?",
        (analysis_id,),
    ).fetchone()
    c.close()

    if not row:
        return jsonify(error="Analysis not found."), 404

    result = json.loads(row["result_json"])
    pdf_path = build_pdf(result)

    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=f"LUNARMATCH_Report_{analysis_id}.pdf",
        mimetype="application/pdf",
    )


@app.get("/api/health")
def health():
    return jsonify(
        status="online",
        service="LUNARMATCH V2",
        engine="Python OpenCV SIFT + BFMatcher + reciprocal matching + RANSAC",
        validation="metadata-aware; no coordinate fabrication",
        report="PDF enabled",
        instrument_awareness=["OHRC", "TMC-2", "IIRS"],
    )


@app.route("/results/<path:name>")
def result_file(name):
    return send_from_directory(RESULTS, name)


@app.errorhandler(413)
def too_large(e):
    return jsonify(error="Maximum upload size is 25 MB."), 413


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False,
    )
