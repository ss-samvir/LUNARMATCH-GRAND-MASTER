import os
import json
import sqlite3
import uuid
import time
import math
from datetime import datetime, timezone
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    session,
    send_from_directory
)

from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image, ExifTags

import cv2
import numpy as np


# ============================================================
# LUNARMATCH V2 — GRAND MASTER BACKEND
# ============================================================

BASE = Path(__file__).resolve().parent

UPLOADS = BASE / "uploads"
RESULTS = BASE / "results"
DB = BASE / "lunarmatch.db"

UPLOADS.mkdir(exist_ok=True)
RESULTS.mkdir(exist_ok=True)


app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "lunarmatch-development-secret-change-me"
)

app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024


# ============================================================
# CONFIGURATION
# ============================================================

MAX_DIMENSION = 1600

SIFT_FEATURES = 5000
SIFT_CONTRAST = 0.018
SIFT_EDGE = 10
SIFT_SIGMA = 1.6

LOWE_RATIO = 0.76
RANSAC_THRESHOLD = 5.0
MIN_GEOMETRIC_MATCHES = 4

CLAHE_CLIP = 2.0
CLAHE_GRID = (8, 8)


# ============================================================
# DATABASE
# ============================================================

def db():
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = db()

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS analyses (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            created_at TEXT NOT NULL,
            result_json TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """
    )

    connection.commit()
    connection.close()


init_db()


# ============================================================
# GENERAL HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


# ============================================================
# GPS / EXIF HELPERS
# ============================================================

def gps_decimal(value):
    """
    Convert EXIF GPS rational / tuple representation
    into decimal degrees.
    """

    try:
        if hasattr(value, "numerator"):
            return float(value.numerator) / float(value.denominator)

        if isinstance(value, tuple):
            total = 0.0

            for index, item in enumerate(value):
                if hasattr(item, "numerator"):
                    number = float(item.numerator) / float(item.denominator)
                else:
                    number = float(item)

                total += number / (60 ** index)

            return total

        if isinstance(value, list):
            total = 0.0

            for index, item in enumerate(value):
                if hasattr(item, "numerator"):
                    number = float(item.numerator) / float(item.denominator)
                else:
                    number = float(item)

                total += number / (60 ** index)

            return total

        return float(value)

    except Exception:
        return None


# ============================================================
# MISSION / INSTRUMENT IDENTIFICATION
# ============================================================

def identify_instrument(metadata):
    """
    Instrument identification is deliberately conservative.

    We do NOT claim OHRC/TMC/IIRS merely because an image is
    lunar or because it comes from Chandrayaan-2.

    Identification requires explicit metadata/reference evidence.
    """

    text_parts = []

    for key in [
        "camera",
        "mission",
        "instrument",
        "image_id",
        "source"
    ]:
        value = metadata.get(key)

        if value:
            text_parts.append(str(value).lower())

    text = " ".join(text_parts)

    if "ohrc" in text or "orbiter high resolution camera" in text:
        return {
            "name": "OHRC",
            "status": "IDENTIFIED",
            "basis": "Explicit metadata/reference evidence"
        }

    if "tmc" in text or "terrain mapping camera" in text:
        return {
            "name": "TMC",
            "status": "IDENTIFIED",
            "basis": "Explicit metadata/reference evidence"
        }

    if (
        "iirs" in text
        or "imaging infrared spectrometer" in text
    ):
        return {
            "name": "IIRS",
            "status": "IDENTIFIED",
            "basis": "Explicit metadata/reference evidence"
        }

    return {
        "name": "UNKNOWN",
        "status": "NOT ESTABLISHED",
        "basis": "No explicit instrument identification available"
    }


# ============================================================
# METADATA EXTRACTION
# ============================================================

def read_metadata(path):
    """
    Extract available metadata without fabricating information.

    Sources:
    1. Embedded EXIF metadata
    2. Optional same-stem JSON sidecar

    Example:
        image_a.jpg
        image_a.json
    """

    result = {
        "available": False,

        "latitude": None,
        "longitude": None,
        "altitude": None,

        "acquisition_time": None,

        "camera": None,
        "make": None,

        "mission": None,
        "instrument": None,
        "image_id": None,

        "crs": None,
        "projection": None,
        "datum": None,

        "reference_source": None,

        "source": "No usable metadata detected",

        "metadata_confidence": "NONE"
    }

    try:
        image = Image.open(path)

        exif = image.getexif()

        tags = {
            ExifTags.TAGS.get(key, key): value
            for key, value in exif.items()
        }

        result["camera"] = tags.get("Model")
        result["make"] = tags.get("Make")

        result["acquisition_time"] = (
            tags.get("DateTimeOriginal")
            or tags.get("DateTime")
        )

        gps = tags.get("GPSInfo")

        if gps:

            gps_tags = {
                ExifTags.GPSTAGS.get(key, key): value
                for key, value in gps.items()
            }

            latitude = gps_tags.get("GPSLatitude")
            longitude = gps_tags.get("GPSLongitude")

            if latitude and longitude:

                lat = gps_decimal(latitude)
                lon = gps_decimal(longitude)

                if lat is not None:
                    if gps_tags.get("GPSLatitudeRef") in ["S", "s"]:
                        lat *= -1

                if lon is not None:
                    if gps_tags.get("GPSLongitudeRef") in ["W", "w"]:
                        lon *= -1

                result["latitude"] = lat
                result["longitude"] = lon

            altitude = gps_tags.get("GPSAltitude")

            if altitude:
                result["altitude"] = gps_decimal(altitude)

        # ----------------------------------------------------
        # OPTIONAL REFERENCE / MISSION SIDECAR
        # ----------------------------------------------------

        sidecar = path.with_suffix(".json")

        if sidecar.exists():

            try:
                side_data = json.loads(
                    sidecar.read_text(encoding="utf-8")
                )

                allowed_fields = [
                    "latitude",
                    "longitude",
                    "altitude",
                    "acquisition_time",
                    "camera",
                    "make",
                    "mission",
                    "instrument",
                    "image_id",
                    "crs",
                    "projection",
                    "datum",
                    "reference_source"
                ]

                for field in allowed_fields:

                    if (
                        field in side_data
                        and side_data[field] not in [None, ""]
                    ):
                        result[field] = side_data[field]

                result["source"] = (
                    "Embedded metadata + supplied reference metadata"
                )

            except Exception as error:

                result["metadata_sidecar_error"] = str(error)

        # ----------------------------------------------------
        # AVAILABILITY
        # ----------------------------------------------------

        metadata_fields = [
            "latitude",
            "longitude",
            "altitude",
            "acquisition_time",
            "camera",
            "make",
            "mission",
            "instrument",
            "image_id",
            "crs",
            "projection",
            "datum",
            "reference_source"
        ]

        available_values = [
            result[field]
            for field in metadata_fields
            if result[field] not in [None, ""]
        ]

        result["available"] = len(available_values) > 0

        if result["latitude"] is not None and result["longitude"] is not None:
            result["metadata_confidence"] = "COORDINATE_AVAILABLE"

        elif result["mission"] or result["instrument"]:
            result["metadata_confidence"] = "MISSION_METADATA"

        elif result["available"]:
            result["metadata_confidence"] = "PARTIAL"

        else:
            result["metadata_confidence"] = "NONE"

    except Exception as error:

        result["metadata_error"] = str(error)

    result["instrument_validation"] = identify_instrument(result)

    return result


# ============================================================
# IMAGE LOADING
# ============================================================

def load_image(path):

    image = cv2.imread(
        str(path),
        cv2.IMREAD_GRAYSCALE
    )

    if image is None:
        raise ValueError(
            "Unsupported or unreadable image."
        )

    height, width = image.shape

    return image, width, height


# ============================================================
# IMAGE RESIZING
# ============================================================

def resize_image(image):

    height, width = image.shape

    largest_dimension = max(height, width)

    if largest_dimension <= MAX_DIMENSION:
        return image

    scale = MAX_DIMENSION / float(largest_dimension)

    new_width = max(1, round(width * scale))
    new_height = max(1, round(height * scale))

    return cv2.resize(
        image,
        (new_width, new_height),
        interpolation=cv2.INTER_AREA
    )


# ============================================================
# IMAGE QUALITY
# ============================================================

def calculate_quality(image):

    image_float = image.astype(np.float32)

    # --------------------------------------------------------
    # Contrast
    # --------------------------------------------------------

    contrast = float(np.std(image_float))

    contrast_score = clamp(
        contrast / 64.0 * 100.0
    )

    # --------------------------------------------------------
    # Sharpness
    # --------------------------------------------------------

    laplacian = cv2.Laplacian(
        image,
        cv2.CV_64F
    )

    sharpness_raw = float(
        laplacian.var()
    )

    # Log scaling avoids extreme values dominating.
    sharpness_score = clamp(
        math.log1p(sharpness_raw) / math.log1p(1500) * 100
    )

    # --------------------------------------------------------
    # Brightness
    # --------------------------------------------------------

    brightness = float(
        np.mean(image_float)
    )

    if brightness < 20:
        brightness_score = 20

    elif brightness > 240:
        brightness_score = 25

    else:
        brightness_score = 100 - (
            abs(brightness - 127.5) / 127.5 * 35
        )

    quality = (
        contrast_score * 0.45
        + sharpness_score * 0.45
        + brightness_score * 0.10
    )

    return {
        "contrast_raw": round(contrast, 3),
        "contrast_score": round(contrast_score, 2),

        "sharpness_raw": round(sharpness_raw, 3),
        "sharpness_score": round(sharpness_score, 2),

        "brightness": round(brightness, 2),
        "brightness_score": round(brightness_score, 2),

        "quality_score": round(
            clamp(quality),
            2
        )
    }


# ============================================================
# PREPROCESSING
# ============================================================

def preprocess(image):

    clahe = cv2.createCLAHE(
        clipLimit=CLAHE_CLIP,
        tileGridSize=CLAHE_GRID
    )

    enhanced = clahe.apply(image)

    # Gentle denoising.
    enhanced = cv2.GaussianBlur(
        enhanced,
        (3, 3),
        0
    )

    return enhanced


# ============================================================
# SIFT FEATURE EXTRACTION
# ============================================================

def extract_features(image):

    sift = cv2.SIFT_create(
        nfeatures=SIFT_FEATURES,
        contrastThreshold=SIFT_CONTRAST,
        edgeThreshold=SIFT_EDGE,
        sigma=SIFT_SIGMA
    )

    keypoints, descriptors = sift.detectAndCompute(
        image,
        None
    )

    if keypoints is None:
        keypoints = []

    return keypoints, descriptors


# ============================================================
# MATCHING
# ============================================================

def ratio_matches(
    descriptors_a,
    descriptors_b,
    ratio=LOWE_RATIO
):

    if descriptors_a is None:
        return []

    if descriptors_b is None:
        return []

    if len(descriptors_a) < 2:
        return []

    if len(descriptors_b) < 2:
        return []

    matcher = cv2.BFMatcher(
        cv2.NORM_L2,
        crossCheck=False
    )

    knn = matcher.knnMatch(
        descriptors_a,
        descriptors_b,
        k=2
    )

    good = []

    for pair in knn:

        if len(pair) != 2:
            continue

        best, second = pair

        if best.distance < ratio * second.distance:
            good.append(best)

    return good


# ============================================================
# RECIPROCAL MATCHING
# ============================================================

def reciprocal_filter(
    descriptors_a,
    descriptors_b,
    forward_matches
):

    reverse_matches = ratio_matches(
        descriptors_b,
        descriptors_a,
        LOWE_RATIO
    )

    reverse_map = {
        match.queryIdx: match.trainIdx
        for match in reverse_matches
    }

    reciprocal = []

    for match in forward_matches:

        reverse_target = reverse_map.get(
            match.trainIdx
        )

        if reverse_target == match.queryIdx:
            reciprocal.append(match)

    return reciprocal


# ============================================================
# GEOMETRIC VERIFICATION
# ============================================================

def verify_geometry(
    keypoints_a,
    keypoints_b,
    matches
):

    if len(matches) < MIN_GEOMETRIC_MATCHES:

        return {
            "homography": None,
            "inliers": [],
            "verified_matches": 0,
            "inlier_ratio": 0.0,
            "geometric_consistency": 0.0,
            "verification_status": "INSUFFICIENT_MATCHES"
        }

    source_points = np.float32(
        [
            keypoints_a[m.queryIdx].pt
            for m in matches
        ]
    ).reshape(-1, 1, 2)

    destination_points = np.float32(
        [
            keypoints_b[m.trainIdx].pt
            for m in matches
        ]
    ).reshape(-1, 1, 2)

    try:

        homography, mask = cv2.findHomography(
            source_points,
            destination_points,
            cv2.RANSAC,
            RANSAC_THRESHOLD
        )

    except cv2.error:

        homography = None
        mask = None

    if homography is None or mask is None:

        return {
            "homography": None,
            "inliers": [],
            "verified_matches": 0,
            "inlier_ratio": 0.0,
            "geometric_consistency": 0.0,
            "verification_status": "GEOMETRY_NOT_ESTABLISHED"
        }

    mask = mask.ravel().astype(bool)

    inliers = [
        index
        for index, value in enumerate(mask)
        if value
    ]

    verified = len(inliers)

    ratio = (
        verified / len(matches) * 100
        if matches
        else 0
    )

    # A high inlier ratio indicates that many candidate
    # correspondences agree with the same geometric model.

    geometric_consistency = clamp(
        ratio
    )

    if verified >= 8 and ratio >= 60:
        status = "STRONG_GEOMETRIC_SUPPORT"

    elif verified >= 5 and ratio >= 40:
        status = "MODERATE_GEOMETRIC_SUPPORT"

    elif verified > 0:
        status = "WEAK_GEOMETRIC_SUPPORT"

    else:
        status = "NO_GEOMETRIC_SUPPORT"

    return {
        "homography": homography.tolist(),
        "inliers": inliers,
        "verified_matches": verified,
        "inlier_ratio": round(ratio, 2),
        "geometric_consistency": round(
            geometric_consistency,
            2
        ),
        "verification_status": status
    }


# ============================================================
# SPATIAL FEATURE COVERAGE
# ============================================================

def calculate_coverage(
    keypoints,
    matches,
    inlier_indices,
    grid_size=5
):

    if not keypoints:
        return 0.0

    if not inlier_indices:
        return 0.0

    occupied = set()

    width_estimate = max(
        [kp.pt[0] for kp in keypoints] or [1]
    )

    height_estimate = max(
        [kp.pt[1] for kp in keypoints] or [1]
    )

    width_estimate = max(width_estimate, 1)
    height_estimate = max(height_estimate, 1)

    for index in inlier_indices:

        match = matches[index]

        x, y = keypoints[
            match.queryIdx
        ].pt

        gx = int(
            x / width_estimate * grid_size
        )

        gy = int(
            y / height_estimate * grid_size
        )

        gx = min(grid_size - 1, max(0, gx))
        gy = min(grid_size - 1, max(0, gy))

        occupied.add(
            (gx, gy)
        )

    total_cells = grid_size * grid_size

    return round(
        len(occupied) / total_cells * 100,
        2
    )


# ============================================================
# MATCH SCORE
# ============================================================

def calculate_score(
    keypoints_a,
    keypoints_b,
    candidate_matches,
    verified_matches,
    inlier_ratio,
    coverage,
    quality_a,
    quality_b
):

    minimum_keypoints = max(
        1,
        min(
            len(keypoints_a),
            len(keypoints_b)
        )
    )

    # --------------------------------------------------------
    # Verification evidence
    # --------------------------------------------------------

    verification_score = (
        verified_matches
        / max(1, len(candidate_matches))
        * 100
    )

    # --------------------------------------------------------
    # Absolute verified-feature evidence
    # --------------------------------------------------------

    feature_score = clamp(
        verified_matches / 30 * 100
    )

    # --------------------------------------------------------
    # Geometry
    # --------------------------------------------------------

    geometry_score = clamp(
        inlier_ratio
    )

    # --------------------------------------------------------
    # Spatial coverage
    # --------------------------------------------------------

    coverage_score = clamp(
        coverage
    )

    # --------------------------------------------------------
    # Image quality
    # --------------------------------------------------------

    quality_score = (
        quality_a + quality_b
    ) / 2

    # --------------------------------------------------------
    # Combined evidence score
    # --------------------------------------------------------

    score = (
        verification_score * 0.30
        + feature_score * 0.20
        + coverage_score * 0.15
        + geometry_score * 0.25
        + quality_score * 0.10
    )

    # Avoid pretending that a very small number of matches
    # represents strong evidence.

    if verified_matches < 4:
        score *= 0.35

    elif verified_matches < 6:
        score *= 0.65

    score = clamp(score)

    # --------------------------------------------------------
    # Reliability classification
    # --------------------------------------------------------

    if verified_matches >= 12 and score >= 70:
        reliability = "HIGH"

    elif verified_matches >= 8 and score >= 55:
        reliability = "MODERATE"

    elif verified_matches >= 4 and score >= 35:
        reliability = "LOW"

    else:
        reliability = "INSUFFICIENT"

    return {
        "score": round(score, 2),
        "reliability": reliability,

        "verification_score": round(
            clamp(verification_score),
            2
        ),

        "feature_score": round(
            feature_score,
            2
        ),

        "coverage_score": round(
            coverage_score,
            2
        ),

        "geometry_score": round(
            geometry_score,
            2
        ),

        "quality_score": round(
            quality_score,
            2
        )
    }


# ============================================================
# CORRESPONDENCE VISUALIZATION
# ============================================================

def create_correspondence_map(
    image_a,
    keypoints_a,
    image_b,
    keypoints_b,
    matches,
    inlier_indices
):

    if image_a is None or image_b is None:
        return None

    # Draw all reciprocal matches lightly and verified
    # correspondences prominently.

    inlier_matches = [
        matches[index]
        for index in inlier_indices
    ]

    height_a, width_a = image_a.shape
    height_b, width_b = image_b.shape

    canvas = cv2.drawMatches(
        image_a,
        keypoints_a,
        image_b,
        keypoints_b,
        inlier_matches,
        None,
        flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS
    )

    # If no inliers exist, show candidate correspondences
    # rather than returning a blank visualization.

    if not inlier_matches and matches:

        preview_matches = matches[:80]

        canvas = cv2.drawMatches(
            image_a,
            keypoints_a,
            image_b,
            keypoints_b,
            preview_matches,
            None,
            flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS
        )

    output_id = uuid.uuid4().hex

    output_path = RESULTS / (
        f"correspondence_{output_id}.jpg"
    )

    cv2.imwrite(
        str(output_path),
        canvas,
        [
            cv2.IMWRITE_JPEG_QUALITY,
            90
        ]
    )

    return {
        "filename": output_path.name,
        "url": f"/results/{output_path.name}",
        "verified_lines": len(inlier_matches),
        "candidate_lines": len(matches)
    }


# ============================================================
# VALIDATION ENGINE
# ============================================================

def validate_scientific_metadata(
    metadata_a,
    metadata_b
):

    validation = {
        "overall_status": "NOT_ESTABLISHED",

        "instrument": {
            "image_a": metadata_a["instrument_validation"],
            "image_b": metadata_b["instrument_validation"]
        },

        "coordinate_validation": {
            "status": "NOT_AVAILABLE",
            "image_a": None,
            "image_b": None,
            "basis": None
        },

        "mission_validation": {
            "status": "NOT_ESTABLISHED",
            "mission_a": metadata_a.get("mission"),
            "mission_b": metadata_b.get("mission")
        },

        "projection_validation": {
            "status": "NOT_AVAILABLE",
            "image_a": metadata_a.get("projection"),
            "image_b": metadata_b.get("projection"),
            "crs_a": metadata_a.get("crs"),
            "crs_b": metadata_b.get("crs")
        },

        "reference_validation": {
            "status": "NOT_AVAILABLE",
            "source_a": metadata_a.get("reference_source"),
            "source_b": metadata_b.get("reference_source")
        },

        "warnings": []
    }

    # --------------------------------------------------------
    # Coordinates
    # --------------------------------------------------------

    coordinates_a_available = (
        metadata_a.get("latitude") is not None
        and metadata_a.get("longitude") is not None
    )

    coordinates_b_available = (
        metadata_b.get("latitude") is not None
        and metadata_b.get("longitude") is not None
    )

    if coordinates_a_available or coordinates_b_available:

        validation["coordinate_validation"]["status"] = (
            "PARTIAL"
        )

        validation["coordinate_validation"]["image_a"] = {
            "latitude": metadata_a.get("latitude"),
            "longitude": metadata_a.get("longitude")
        }

        validation["coordinate_validation"]["image_b"] = {
            "latitude": metadata_b.get("latitude"),
            "longitude": metadata_b.get("longitude")
        }

        validation["coordinate_validation"]["basis"] = (
            "Embedded or explicitly supplied metadata"
        )

    if coordinates_a_available and coordinates_b_available:

        validation["coordinate_validation"]["status"] = (
            "AVAILABLE_FOR_BOTH_IMAGES"
        )

    # --------------------------------------------------------
    # Mission
    # --------------------------------------------------------

    mission_a = metadata_a.get("mission")
    mission_b = metadata_b.get("mission")

    if mission_a or mission_b:

        validation["mission_validation"]["status"] = (
            "PARTIAL"
        )

    if mission_a and mission_b:

        if str(mission_a).strip().lower() == str(
            mission_b
        ).strip().lower():

            validation["mission_validation"]["status"] = (
                "CONSISTENT_METADATA"
            )

        else:

            validation["mission_validation"]["status"] = (
                "DIFFERENT_MISSION_METADATA"
            )

    # --------------------------------------------------------
    # Projection
    # --------------------------------------------------------

    projection_a = metadata_a.get("projection")
    projection_b = metadata_b.get("projection")

    crs_a = metadata_a.get("crs")
    crs_b = metadata_b.get("crs")

    if projection_a or projection_b or crs_a or crs_b:

        validation["projection_validation"]["status"] = (
            "PARTIAL"
        )

    if (
        projection_a
        and projection_b
        and crs_a
        and crs_b
    ):

        if (
            str(projection_a).lower()
            == str(projection_b).lower()
            and str(crs_a).lower()
            == str(crs_b).lower()
        ):

            validation["projection_validation"]["status"] = (
                "CONSISTENT"
            )

    # --------------------------------------------------------
    # Reference
    # --------------------------------------------------------

    source_a = metadata_a.get(
        "reference_source"
    )

    source_b = metadata_b.get(
        "reference_source"
    )

    if source_a or source_b:

        validation["reference_validation"]["status"] = (
            "REFERENCE_INFORMATION_PRESENT"
        )

    # --------------------------------------------------------
    # Warnings
    # --------------------------------------------------------

    if not coordinates_a_available:
        validation["warnings"].append(
            "Image A does not contain usable coordinates."
        )

    if not coordinates_b_available:
        validation["warnings"].append(
            "Image B does not contain usable coordinates."
        )

    if (
        metadata_a["instrument_validation"]["status"]
        != "IDENTIFIED"
    ):
        validation["warnings"].append(
            "Image A instrument identity is not established."
        )

    if (
        metadata_b["instrument_validation"]["status"]
        != "IDENTIFIED"
    ):
        validation["warnings"].append(
            "Image B instrument identity is not established."
        )

    # --------------------------------------------------------
    # Overall status
    # --------------------------------------------------------

    if (
        validation["coordinate_validation"]["status"]
        == "AVAILABLE_FOR_BOTH_IMAGES"
        or validation["mission_validation"]["status"]
        == "CONSISTENT_METADATA"
        or validation["projection_validation"]["status"]
        == "CONSISTENT"
    ):

        validation["overall_status"] = (
            "PARTIAL_SCIENTIFIC_VALIDATION"
        )

    else:

        validation["overall_status"] = (
            "COMPUTATIONAL_VALIDATION_ONLY"
        )

    return validation


# ============================================================
# INTERPRETATION
# ============================================================

def generate_interpretation(
    score,
    reliability,
    verified_matches,
    candidate_matches,
    inlier_ratio,
    coverage
):

    if reliability == "HIGH":

        return (
            "The analysis found a strong set of geometrically "
            "consistent feature correspondences. The result "
            "should be interpreted as strong computational "
            "evidence of visual correspondence, not as "
            "independent ground-truth localization."
        )

    if reliability == "MODERATE":

        return (
            "The analysis found a meaningful set of candidate "
            "correspondences with moderate geometric support. "
            "Additional reference data or independent validation "
            "would strengthen the scientific conclusion."
        )

    if reliability == "LOW":

        return (
            "Some correspondence evidence was detected, but the "
            "available geometric evidence is limited. The result "
            "should be treated cautiously and preferably checked "
            "against reference imagery or mission metadata."
        )

    if candidate_matches > 0:

        return (
            "Candidate correspondences were detected, but the "
            "system could not establish sufficient geometric "
            "evidence for a reliable correspondence conclusion. "
            "This is a legitimate negative/insufficient result."
        )

    return (
        "The images did not produce sufficient descriptor "
        "correspondences for geometric verification. This can "
        "occur when imagery differs strongly in content, "
        "resolution, illumination, texture or acquisition "
        "conditions."
    )


# ============================================================
# MAIN ANALYSIS
# ============================================================

def analyze(image_a_path, image_b_path):

    start_time = time.perf_counter()

    # ========================================================
    # ACQUIRE
    # ========================================================

    original_a, width_a, height_a = load_image(
        image_a_path
    )

    original_b, width_b, height_b = load_image(
        image_b_path
    )

    # ========================================================
    # QUALITY
    # ========================================================

    quality_a = calculate_quality(
        original_a
    )

    quality_b = calculate_quality(
        original_b
    )

    # ========================================================
    # PREPROCESS
    # ========================================================

    processed_a = resize_image(
        original_a
    )

    processed_b = resize_image(
        original_b
    )

    processed_a = preprocess(
        processed_a
    )

    processed_b = preprocess(
        processed_b
    )

    # ========================================================
    # FEATURE EXTRACTION
    # ========================================================

    keypoints_a, descriptors_a = extract_features(
        processed_a
    )

    keypoints_b, descriptors_b = extract_features(
        processed_b
    )

    # ========================================================
    # PRIMARY MATCHING
    # ========================================================

    raw_matches = ratio_matches(
        descriptors_a,
        descriptors_b
    )

    # ========================================================
    # RECIPROCAL MATCHING
    # ========================================================

    reciprocal_matches = reciprocal_filter(
        descriptors_a,
        descriptors_b,
        raw_matches
    )

    # ========================================================
    # GEOMETRIC VERIFICATION
    # ========================================================

    geometry = verify_geometry(
        keypoints_a,
        keypoints_b,
        reciprocal_matches
    )

    inlier_indices = geometry[
        "inliers"
    ]

    verified_matches = geometry[
        "verified_matches"
    ]

    # ========================================================
    # COVERAGE
    # ========================================================

    coverage = calculate_coverage(
        keypoints_a,
        reciprocal_matches,
        inlier_indices
    )

    # ========================================================
    # SCORE
    # ========================================================

    scoring = calculate_score(
        keypoints_a,
        keypoints_b,
        reciprocal_matches,
        verified_matches,
        geometry["inlier_ratio"],
        coverage,
        quality_a["quality_score"],
        quality_b["quality_score"]
    )

    # ========================================================
    # METADATA
    # ========================================================

    metadata_a = read_metadata(
        image_a_path
    )

    metadata_b = read_metadata(
        image_b_path
    )

    # ========================================================
    # SCIENTIFIC VALIDATION
    # ========================================================

    scientific_validation = validate_scientific_metadata(
        metadata_a,
        metadata_b
    )

    # ========================================================
    # CORRESPONDENCE MAP
    # ========================================================

    visualization = create_correspondence_map(
        processed_a,
        keypoints_a,
        processed_b,
        keypoints_b,
        reciprocal_matches,
        inlier_indices
    )

    # ========================================================
    # INTERPRETATION
    # ========================================================

    interpretation = generate_interpretation(
        scoring["score"],
        scoring["reliability"],
        verified_matches,
        len(reciprocal_matches),
        geometry["inlier_ratio"],
        coverage
    )

    # ========================================================
    # PROCESSING TIME
    # ========================================================

    processing_time = (
        time.perf_counter()
        - start_time
    ) * 1000

    # ========================================================
    # RESULT
    # ========================================================

    analysis_id = (
        visualization["filename"]
        .replace("correspondence_", "")
        .replace(".jpg", "")
        if visualization
        else uuid.uuid4().hex
    )

    result = {

        "analysis_id": analysis_id,

        "created_at": utc_now(),

        "engine": {
            "name": "LUNARMATCH Hybrid Correspondence Engine",

            "feature_detector": "SIFT",

            "descriptor": "SIFT",

            "matcher": "BFMatcher / L2",

            "matching": (
                "Lowe ratio test + reciprocal filtering"
            ),

            "geometric_model": "Homography",

            "verification": "RANSAC",

            "preprocessing": (
                "Resize + CLAHE + Gaussian smoothing"
            ),

            "max_dimension": MAX_DIMENSION,

            "sift_features": SIFT_FEATURES,

            "ratio_threshold": LOWE_RATIO,

            "ransac_threshold": RANSAC_THRESHOLD
        },

        "score": scoring["score"],

        "reliability": scoring["reliability"],

        "score_components": {
            "verification": scoring[
                "verification_score"
            ],

            "features": scoring[
                "feature_score"
            ],

            "coverage": scoring[
                "coverage_score"
            ],

            "geometry": scoring[
                "geometry_score"
            ],

            "quality": scoring[
                "quality_score"
            ]
        },

        "raw_matches": len(
            raw_matches
        ),

        "candidate_matches": len(
            reciprocal_matches
        ),

        "verified_matches": verified_matches,

        "inlier_ratio": geometry[
            "inlier_ratio"
        ],

        "feature_coverage": coverage,

        "geometric_consistency": geometry[
            "geometric_consistency"
        ],

        "homography_status": (
            "ESTABLISHED"
            if geometry["homography"] is not None
            else "NOT ESTABLISHED"
        ),

        "verification_status": geometry[
            "verification_status"
        ],

        "processing_time_ms": round(
            processing_time,
            1
        ),

        "image_a": {

            "width": width_a,

            "height": height_a,

            "keypoints": len(
                keypoints_a
            ),

            "quality": quality_a,

            "metadata": metadata_a
        },

        "image_b": {

            "width": width_b,

            "height": height_b,

            "keypoints": len(
                keypoints_b
            ),

            "quality": quality_b,

            "metadata": metadata_b
        },

        "scientific_validation": scientific_validation,

        "localization": {

            "status": (
                "AVAILABLE"
                if (
                    metadata_a.get("latitude") is not None
                    and metadata_a.get("longitude") is not None
                )
                else "NOT AVAILABLE"
            ),

            "latitude": metadata_a.get(
                "latitude"
            ),

            "longitude": metadata_a.get(
                "longitude"
            ),

            "basis": (
                "Image A embedded/reference metadata"
                if (
                    metadata_a.get("latitude") is not None
                    and metadata_a.get("longitude") is not None
                )
                else None
            )
        },

        "visualization": visualization,

        # Backward-compatible field for the current V2 UI.
        "result_image": (
            visualization["url"]
            if visualization
            else None
        ),

        "interpretation": interpretation,

        "validation_note": (
            "The correspondence score is a computational "
            "evidence indicator. It is not ground-truth "
            "positional accuracy and does not independently "
            "establish latitude/longitude."
        )
    }

    return result


# ============================================================
# TEMPLATE GLOBALS
# ============================================================

@app.context_processor
def globals():

    return {
        "logged_in": bool(
            session.get("user_id")
        ),

        "user_name": session.get(
            "user_name"
        )
    }


# ============================================================
# PAGES
# ============================================================

@app.route("/")
def home():

    return render_template(
        "home.html"
    )


@app.route("/<page>")
def page(page):

    allowed_pages = {
        "analyze",
        "results",
        "validation",
        "stress",
        "technology",
        "about",
        "contact",
        "signin",
        "signup"
    }

    if page not in allowed_pages:

        return render_template(
            "404.html"
        ), 404

    return render_template(
        f"{page}.html"
    )


# ============================================================
# AUTHENTICATION
# ============================================================

@app.post("/api/signup")
def signup():

    data = request.get_json() or {}

    name = data.get(
        "name",
        ""
    ).strip()

    email = data.get(
        "email",
        ""
    ).strip().lower()

    password = data.get(
        "password",
        ""
    )

    if not name:

        return jsonify(
            error="Name is required."
        ), 400

    if "@" not in email:

        return jsonify(
            error="Please enter a valid email address."
        ), 400

    if len(password) < 8:

        return jsonify(
            error=(
                "Password must contain at least "
                "8 characters."
            )
        ), 400

    try:

        connection = db()

        connection.execute(
            """
            INSERT INTO users
            (name, email, password, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                name,
                email,
                generate_password_hash(
                    password
                ),
                utc_now()
            )
        )

        connection.commit()

        user_id = connection.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]

        connection.close()

        session["user_id"] = user_id
        session["user_name"] = name

        return jsonify(
            ok=True
        )

    except sqlite3.IntegrityError:

        return jsonify(
            error=(
                "An account with this email "
                "already exists."
            )
        ), 409


@app.post("/api/signin")
def signin():

    data = request.get_json() or {}

    email = data.get(
        "email",
        ""
    ).strip().lower()

    password = data.get(
        "password",
        ""
    )

    connection = db()

    user = connection.execute(
        """
        SELECT *
        FROM users
        WHERE email = ?
        """,
        (email,)
    ).fetchone()

    connection.close()

    if (
        not user
        or not check_password_hash(
            user["password"],
            password
        )
    ):

        return jsonify(
            error="Invalid email or password."
        ), 401

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]

    return jsonify(
        ok=True
    )


@app.post("/api/signout")
def signout():

    session.clear()

    return jsonify(
        ok=True
    )


# ============================================================
# ANALYSIS API
# ============================================================

@app.post("/api/analyze")
def api_analyze():

    if (
        "image_a" not in request.files
        or "image_b" not in request.files
    ):

        return jsonify(
            error=(
                "Please upload both Image A "
                "and Image B."
            )
        ), 400

    image_a = request.files[
        "image_a"
    ]

    image_b = request.files[
        "image_b"
    ]

    if not image_a.filename:

        return jsonify(
            error="Image A has no filename."
        ), 400

    if not image_b.filename:

        return jsonify(
            error="Image B has no filename."
        ), 400

    analysis_upload_id = uuid.uuid4().hex

    suffix_a = (
        Path(image_a.filename)
        .suffix
        .lower()
    )

    suffix_b = (
        Path(image_b.filename)
        .suffix
        .lower()
    )

    if not suffix_a:
        suffix_a = ".jpg"

    if not suffix_b:
        suffix_b = ".jpg"

    path_a = UPLOADS / (
        f"{analysis_upload_id}_a{suffix_a}"
    )

    path_b = UPLOADS / (
        f"{analysis_upload_id}_b{suffix_b}"
    )

    image_a.save(path_a)
    image_b.save(path_b)

    try:

        result = analyze(
            path_a,
            path_b
        )

    except Exception as error:

        return jsonify(
            error=str(error)
        ), 422

    # --------------------------------------------------------
    # Save result
    # --------------------------------------------------------

    connection = db()

    connection.execute(
        """
        INSERT INTO analyses
        (id, user_id, created_at, result_json)
        VALUES (?, ?, ?, ?)
        """,
        (
            result["analysis_id"],
            session.get("user_id"),
            result["created_at"],
            json.dumps(result)
        )
    )

    connection.commit()
    connection.close()

    return jsonify(
        result
    )


# ============================================================
# RESULT HISTORY
# ============================================================

@app.get("/api/results")
def api_results():

    connection = db()

    if session.get("user_id"):

        rows = connection.execute(
            """
            SELECT id, created_at, result_json
            FROM analyses
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 30
            """,
            (
                session.get("user_id"),
            )
        ).fetchall()

    else:

        rows = connection.execute(
            """
            SELECT id, created_at, result_json
            FROM analyses
            WHERE user_id IS NULL
            ORDER BY created_at DESC
            LIMIT 30
            """
        ).fetchall()

    connection.close()

    return jsonify(
        [
            json.loads(
                row["result_json"]
            )
            for row in rows
        ]
    )


# ============================================================
# HEALTH
# ============================================================

@app.get("/api/health")
def health():

    return jsonify(

        status="online",

        service="LUNARMATCH V2",

        version="2.0-grand-master",

        engine=(
            "SIFT + BFMatcher + Lowe Ratio "
            "+ Reciprocal Filtering + RANSAC"
        ),

        validation=(
            "Metadata-aware OHRC/TMC/IIRS "
            "validation architecture"
        ),

        localization=(
            "Coordinates displayed only "
            "when legitimately available"
        ),

        scientific_integrity=(
            "No coordinate fabrication"
        )
    )


# ============================================================
# RESULT FILES
# ============================================================

@app.route("/results/<path:name>")
def result_file(name):

    return send_from_directory(
        RESULTS,
        name
    )


# ============================================================
# FILE SIZE ERROR
# ============================================================

@app.errorhandler(413)
def file_too_large(error):

    return jsonify(
        error=(
            "Maximum upload size is 25 MB."
        )
    ), 413


# ============================================================
# GENERAL ERROR
# ============================================================

@app.errorhandler(500)
def internal_error(error):

    return jsonify(
        error=(
            "LunarMatch encountered an internal "
            "processing error."
        )
    ), 500


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
