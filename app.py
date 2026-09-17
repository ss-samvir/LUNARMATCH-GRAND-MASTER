import os
import io
import json
import uuid
import sqlite3
import secrets
import hashlib
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from functools import wraps

import cv2
import numpy as np
from PIL import Image, ExifTags
from flask import (
    Flask,
    request,
    jsonify,
    session,
    redirect,
    url_for,
    render_template,
    send_file,
    abort,
)

# ============================================================
# LUNARMATCH V3
# Evidence-first lunar image correspondence platform
#
# IMPORTANT:
# - No fabricated coordinates
# - No fabricated instrument identity
# - No fake scientific claims
# - No admin panel
# - Guest users can perform basic correspondence
# - Registered users receive research-workspace features
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
REPORT_DIR = os.path.join(BASE_DIR, "reports")
DB_PATH = os.path.join(BASE_DIR, "lunarmatch.db")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "CHANGE_THIS_SECRET_KEY_BEFORE_PUBLIC_DEPLOYMENT"
)

app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

# ============================================================
# ENGINE CONFIGURATION
# ============================================================

MAX_DIMENSION = 1600

SIFT_FEATURES = 5000
SIFT_CONTRAST = 0.018
SIFT_EDGE = 10
SIFT_SIGMA = 1.6

LOWE_RATIO = 0.76
RANSAC_THRESHOLD = 5.0

CLAHE_CLIP = 2.0
CLAHE_GRID = (8, 8)

ALLOWED_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp",
    "tif",
    "tiff",
}

MAX_ANALYSIS_HISTORY = 100


# ============================================================
# DATABASE
# ============================================================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            profession TEXT NOT NULL,
            institution TEXT,
            study_level TEXT,
            course TEXT,
            study_year TEXT,
            usage_reason TEXT,
            research_area TEXT,
            intended_use TEXT,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_id TEXT NOT NULL UNIQUE,
            user_id INTEGER,
            image_a_name TEXT NOT NULL,
            image_b_name TEXT NOT NULL,
            score REAL,
            verified INTEGER,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            email TEXT,
            feedback_type TEXT NOT NULL,
            rating INTEGER,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )

    conn.commit()
    conn.close()


init_db()


# ============================================================
# GENERAL HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def clean_text(value, maximum=500):
    if value is None:
        return ""
    return str(value).strip()[:maximum]


def allowed_file(filename):
    if not filename or "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()
    return extension in ALLOWED_EXTENSIONS


def safe_json(value):
    try:
        return json.loads(value)
    except Exception:
        return {}


def json_response(data, status=200):
    return jsonify(data), status


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        180000,
    )

    return (
        salt.hex()
        + ":"
        + digest.hex()
    )


def verify_password(password, stored):
    try:
        salt_hex, digest_hex = stored.split(":", 1)

        salt = bytes.fromhex(salt_hex)

        calculated = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            180000,
        ).hex()

        return secrets.compare_digest(calculated, digest_hex)

    except Exception:
        return False


def current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    conn = get_db()

    user = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    conn.close()

    return user


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return json_response(
                    {
                        "ok": False,
                        "error": "Authentication required.",
                        "code": "AUTH_REQUIRED",
                    },
                    401,
                )

            return redirect(url_for("signin"))

        return function(*args, **kwargs)

    return wrapper


# ============================================================
# WELCOME EMAIL
# ============================================================

def send_welcome_email(user):
    """
    Sends a real email only when SMTP credentials are configured.

    Required environment variables:
        SMTP_HOST
        SMTP_PORT
        SMTP_USERNAME
        SMTP_PASSWORD
        MAIL_FROM

    Optional:
        SMTP_USE_TLS=true

    If these are not configured, the application does NOT pretend
    that an email was sent.
    """

    host = os.environ.get("SMTP_HOST")
    port = os.environ.get("SMTP_PORT")
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    mail_from = os.environ.get("MAIL_FROM")

    if not all([host, port, username, password, mail_from]):
        return {
            "sent": False,
            "reason": "Email service is not configured."
        }

    try:
        port = int(port)

        message = EmailMessage()

        message["Subject"] = "Welcome to LUNARMATCH"
        message["From"] = mail_from
        message["To"] = user["email"]

        message.set_content(
            f"""
Welcome to LUNARMATCH, {user["name"]}.

Your LUNARMATCH research workspace has been created successfully.

You can now:
• perform lunar image correspondence
• save analysis results
• access detailed validation evidence
• run robustness tests
• generate scientific PDF reports
• maintain your analysis history

Username: {user["username"]}

Thank you for exploring LUNARMATCH.

LUNARMATCH
Lunar Image Correspondence & Geometric Verification
"""
        )

        use_tls = os.environ.get(
            "SMTP_USE_TLS",
            "true"
        ).lower() == "true"

        with smtplib.SMTP(host, port, timeout=20) as server:

            if use_tls:
                server.starttls()

            server.login(username, password)
            server.send_message(message)

        return {
            "sent": True,
            "reason": "Welcome email sent."
        }

    except Exception as exc:

        app.logger.warning(
            "Welcome email could not be sent: %s",
            exc
        )

        return {
            "sent": False,
            "reason": "Email service returned an error."
        }


# ============================================================
# IMAGE HELPERS
# ============================================================

def read_image(file_storage):
    raw = file_storage.read()

    if not raw:
        raise ValueError("The uploaded image is empty.")

    array = np.frombuffer(raw, dtype=np.uint8)

    image = cv2.imdecode(
        array,
        cv2.IMREAD_COLOR
    )

    if image is None:
        raise ValueError(
            "The uploaded file could not be decoded as an image."
        )

    return image, raw


def resize_image(image):
    height, width = image.shape[:2]

    largest = max(height, width)

    if largest <= MAX_DIMENSION:
        return image

    scale = MAX_DIMENSION / float(largest)

    return cv2.resize(
        image,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_AREA,
    )


def image_to_jpeg_bytes(image):
    success, encoded = cv2.imencode(
        ".jpg",
        image,
        [cv2.IMWRITE_JPEG_QUALITY, 90],
    )

    if not success:
        return None

    return encoded.tobytes()


def calculate_image_quality(image):
    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )

    contrast = float(np.std(gray))

    sharpness = float(
        cv2.Laplacian(
            gray,
            cv2.CV_64F
        ).var()
    )

    brightness = float(np.mean(gray))

    # These are heuristic quality indicators, not
    # scientific truth measurements.

    contrast_score = min(
        100.0,
        max(
            0.0,
            (contrast / 64.0) * 100.0
        )
    )

    sharpness_score = min(
        100.0,
        max(
            0.0,
            (sharpness / 500.0) * 100.0
        )
    )

    brightness_penalty = abs(
        brightness - 128.0
    ) / 128.0

    brightness_score = max(
        0.0,
        100.0 - brightness_penalty * 100.0
    )

    quality = (
        contrast_score * 0.35
        + sharpness_score * 0.45
        + brightness_score * 0.20
    )

    return {
        "contrast": round(contrast, 3),
        "sharpness": round(sharpness, 3),
        "brightness": round(brightness, 3),
        "quality_score": round(
            min(100.0, max(0.0, quality)),
            2
        ),
    }


def preprocess(image):
    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )

    clahe = cv2.createCLAHE(
        clipLimit=CLAHE_CLIP,
        tileGridSize=CLAHE_GRID,
    )

    enhanced = clahe.apply(gray)

    enhanced = cv2.GaussianBlur(
        enhanced,
        (3, 3),
        0
    )

    return enhanced


# ============================================================
# METADATA
# ============================================================

EXIF_TAGS = {
    value: key
    for key, value in ExifTags.TAGS.items()
}


def rational_to_float(value):
    try:
        if isinstance(value, tuple):
            return float(value[0]) / float(value[1])

        return float(value)

    except Exception:
        return None


def convert_gps_coordinate(value, reference):
    try:
        degrees = rational_to_float(value[0])
        minutes = rational_to_float(value[1])
        seconds = rational_to_float(value[2])

        if None in [degrees, minutes, seconds]:
            return None

        coordinate = (
            degrees
            + minutes / 60.0
            + seconds / 3600.0
        )

        if reference in ["S", "W"]:
            coordinate *= -1

        return coordinate

    except Exception:
        return None


def extract_metadata(raw_bytes, original_filename):
    metadata = {
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
        "metadata_confidence": "NONE",
        "source_filename": original_filename,
    }

    try:
        image = Image.open(
            io.BytesIO(raw_bytes)
        )

        exif = image.getexif()

        if exif:

            decoded = {}

            for key, value in exif.items():
                decoded[
                    ExifTags.TAGS.get(
                        key,
                        str(key)
                    )
                ] = value

            gps = decoded.get("GPSInfo")

            if gps:

                gps_decoded = {}

                for key, value in gps.items():
                    gps_decoded[
                        ExifTags.GPSTAGS.get(
                            key,
                            str(key)
                        )
                    ] = value

                lat = gps_decoded.get("GPSLatitude")
                lat_ref = gps_decoded.get("GPSLatitudeRef")

                lon = gps_decoded.get("GPSLongitude")
                lon_ref = gps_decoded.get("GPSLongitudeRef")

                if lat and lat_ref:
                    metadata["latitude"] = convert_gps_coordinate(
                        lat,
                        lat_ref
                    )

                if lon and lon_ref:
                    metadata["longitude"] = convert_gps_coordinate(
                        lon,
                        lon_ref
                    )

            metadata["make"] = decoded.get("Make")
            metadata["camera"] = decoded.get("Model")
            metadata["acquisition_time"] = decoded.get(
                "DateTimeOriginal"
            )

            if (
                metadata["latitude"] is not None
                and metadata["longitude"] is not None
            ):
                metadata["metadata_confidence"] = "EXIF_COORDINATES"

            elif any(
                [
                    metadata["make"],
                    metadata["camera"],
                    metadata["acquisition_time"],
                ]
            ):
                metadata["metadata_confidence"] = "EXIF_GENERAL"

    except Exception:
        pass

    return metadata


# ============================================================
# INSTRUMENT VALIDATION
# ============================================================

INSTRUMENTS = {
    "OHRC": [
        "OHRC",
        "Orbiter High Resolution Camera",
    ],
    "TMC": [
        "TMC",
        "Terrain Mapping Camera",
    ],
    "IIRS": [
        "IIRS",
        "Imaging Infrared Spectrometer",
    ],
}


def identify_instrument(metadata):
    values = []

    for key in [
        "instrument",
        "camera",
        "mission",
        "reference_source",
    ]:
        value = metadata.get(key)

        if value:
            values.append(
                str(value).lower()
            )

    combined = " ".join(values)

    for code, names in INSTRUMENTS.items():

        for name in names:

            if name.lower() in combined:

                return {
                    "code": code,
                    "name": names[1],
                    "status": "ESTABLISHED",
                    "basis": "Metadata/reference evidence",
                }

    return {
        "code": "UNKNOWN",
        "name": "Instrument not established",
        "status": "NOT_ESTABLISHED",
        "basis": "No trusted instrument metadata was found.",
    }


# ============================================================
# SIFT + MATCHING
# ============================================================

def create_sift():
    return cv2.SIFT_create(
        nfeatures=SIFT_FEATURES,
        contrastThreshold=SIFT_CONTRAST,
        edgeThreshold=SIFT_EDGE,
        sigma=SIFT_SIGMA,
    )


def extract_features(processed):
    sift = create_sift()

    keypoints, descriptors = sift.detectAndCompute(
        processed,
        None
    )

    return keypoints, descriptors


def calculate_reciprocal_matches(
    descriptors_a,
    descriptors_b,
):
    if descriptors_a is None or descriptors_b is None:
        return []

    if len(descriptors_a) < 2:
        return []

    if len(descriptors_b) < 2:
        return []

    matcher = cv2.BFMatcher(
        cv2.NORM_L2,
        crossCheck=False
    )

    forward = matcher.knnMatch(
        descriptors_a,
        descriptors_b,
        k=2
    )

    backward = matcher.knnMatch(
        descriptors_b,
        descriptors_a,
        k=2
    )

    good_forward = {}

    for pair in forward:

        if len(pair) < 2:
            continue

        first, second = pair

        if first.distance < LOWE_RATIO * second.distance:
            good_forward[
                (
                    first.queryIdx,
                    first.trainIdx
                )
            ] = first

    good_backward = set()

    for pair in backward:

        if len(pair) < 2:
            continue

        first, second = pair

        if first.distance < LOWE_RATIO * second.distance:
            good_backward.add(
                (
                    first.trainIdx,
                    first.queryIdx
                )
            )

    reciprocal = []

    for key, match in good_forward.items():

        if key in good_backward:
            reciprocal.append(match)

    reciprocal.sort(
        key=lambda item: item.distance
    )

    return reciprocal


def calculate_homography(
    keypoints_a,
    keypoints_b,
    matches,
):
    if len(matches) < 4:

        return {
            "homography": None,
            "inliers": 0,
            "inlier_ratio": 0.0,
            "verified": False,
            "reason": "Fewer than four geometrically usable matches.",
        }

    source = np.float32(
        [
            keypoints_a[m.queryIdx].pt
            for m in matches
        ]
    ).reshape(-1, 1, 2)

    destination = np.float32(
        [
            keypoints_b[m.trainIdx].pt
            for m in matches
        ]
    ).reshape(-1, 1, 2)

    try:

        homography, mask = cv2.findHomography(
            source,
            destination,
            cv2.RANSAC,
            RANSAC_THRESHOLD,
        )

    except Exception:

        homography = None
        mask = None

    if homography is None or mask is None:

        return {
            "homography": None,
            "inliers": 0,
            "inlier_ratio": 0.0,
            "verified": False,
            "reason": "A stable homography could not be estimated.",
        }

    mask = mask.ravel().astype(bool)

    inliers = int(np.sum(mask))

    ratio = (
        inliers / float(len(matches))
        if matches
        else 0.0
    )

    verified = (
        inliers >= 10
        and ratio >= 0.20
    )

    return {
        "homography": homography,
        "inliers": inliers,
        "inlier_ratio": ratio,
        "verified": verified,
        "mask": mask,
        "reason": (
            "Sufficient geometric consistency detected."
            if verified
            else "Geometric consistency is below the verification threshold."
        ),
    }


# ============================================================
# EVIDENCE SCORING
# ============================================================

def calculate_evidence_score(
    keypoints_a,
    keypoints_b,
    matches,
    geometry,
    quality_a,
    quality_b,
):
    kp_a = len(keypoints_a)
    kp_b = len(keypoints_b)

    candidate_count = len(matches)

    inliers = geometry["inliers"]
    inlier_ratio = geometry["inlier_ratio"]

    quality_average = (
        quality_a["quality_score"]
        + quality_b["quality_score"]
    ) / 2.0

    # Correspondence evidence
    correspondence_score = min(
        100.0,
        candidate_count / 5.0
    )

    # Geometric evidence
    geometric_score = min(
        100.0,
        inlier_ratio * 100.0
    )

    # Inlier count contribution
    inlier_count_score = min(
        100.0,
        inliers / 2.0
    )

    # Image quality contribution
    quality_score = quality_average

    total = (
        correspondence_score * 0.25
        + geometric_score * 0.40
        + inlier_count_score * 0.20
        + quality_score * 0.15
    )

    return {
        "total": round(
            min(100.0, max(0.0, total)),
            2
        ),
        "components": {
            "correspondence": round(
                correspondence_score,
                2
            ),
            "geometric_consistency": round(
                geometric_score,
                2
            ),
            "inlier_count": round(
                inlier_count_score,
                2
            ),
            "image_quality": round(
                quality_score,
                2
            ),
        },
        "formula": {
            "correspondence_weight": 0.25,
            "geometric_weight": 0.40,
            "inlier_count_weight": 0.20,
            "quality_weight": 0.15,
        },
        "note": (
            "This is an evidence score for this computational pipeline, "
            "not a calibrated probability that two images show the same place."
        ),
    }


# ============================================================
# CORRESPONDENCE VISUALIZATION
# ============================================================

def create_match_visualization(
    image_a,
    keypoints_a,
    image_b,
    keypoints_b,
    matches,
    geometry,
):
    if not matches:
        return None

    draw_matches = matches[:120]

    mask = geometry.get("mask")

    if mask is not None:
        mask_for_draw = mask[:len(draw_matches)].tolist()
    else:
        mask_for_draw = None

    try:

        output = cv2.drawMatches(
            image_a,
            keypoints_a,
            image_b,
            keypoints_b,
            draw_matches,
            None,
            matchColor=(0, 230, 180),
            singlePointColor=(255, 255, 255),
            matchesMask=mask_for_draw,
            flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
        )

        return image_to_jpeg_bytes(output)

    except Exception:
        return None


# ============================================================
# VALIDATION
# ============================================================

def validate_coordinates(metadata):
    lat = metadata.get("latitude")
    lon = metadata.get("longitude")

    if lat is None or lon is None:

        return {
            "status": "NOT_AVAILABLE",
            "latitude": None,
            "longitude": None,
            "basis": "No trusted coordinate metadata was found.",
        }

    if not (
        -90 <= float(lat) <= 90
        and -180 <= float(lon) <= 180
    ):

        return {
            "status": "INVALID",
            "latitude": None,
            "longitude": None,
            "basis": "Extracted coordinate values were outside valid ranges.",
        }

    return {
        "status": "AVAILABLE",
        "latitude": round(float(lat), 8),
        "longitude": round(float(lon), 8),
        "basis": "Coordinate metadata embedded in the supplied image.",
    }


def build_validation(metadata_a, metadata_b):
    instrument_a = identify_instrument(metadata_a)
    instrument_b = identify_instrument(metadata_b)

    coordinate = validate_coordinates(metadata_a)

    warnings = []

    if instrument_a["status"] != "ESTABLISHED":
        warnings.append(
            "Image A instrument identity was not established from supplied metadata."
        )

    if instrument_b["status"] != "ESTABLISHED":
        warnings.append(
            "Image B instrument identity was not established from supplied metadata."
        )

    if coordinate["status"] == "NOT_AVAILABLE":
        warnings.append(
            "No trusted latitude/longitude source was available for Image A."
        )

    warnings.append(
        "Instrument identity is not inferred from visual appearance alone."
    )

    warnings.append(
        "No independent lunar reference catalogue is assumed by this analysis."
    )

    return {
        "instrument": {
            "A": instrument_a,
            "B": instrument_b,
        },
        "coordinate_validation": coordinate,
        "mission_validation": {
            "status": "METADATA_ONLY",
            "text": (
                "Mission/instrument identity is reported only when supplied "
                "metadata provides supporting evidence."
            ),
        },
        "projection_validation": {
            "status": (
                "AVAILABLE"
                if metadata_a.get("projection")
                else "NOT_AVAILABLE"
            ),
            "projection": metadata_a.get("projection"),
            "crs": metadata_a.get("crs"),
            "datum": metadata_a.get("datum"),
        },
        "reference_validation": {
            "status": (
                "AVAILABLE"
                if metadata_a.get("reference_source")
                else "NOT_AVAILABLE"
            ),
            "source": metadata_a.get("reference_source"),
        },
        "warnings": warnings,
        "overall": (
            "PARTIAL"
            if warnings
            else "SUPPORTED"
        ),
    }


# ============================================================
# INTERPRETATION
# ============================================================

def interpret_result(score, verified, inliers):
    if verified and score >= 70:
        return {
            "label": "STRONG CORRESPONDENCE EVIDENCE",
            "summary": (
                "The two observations contain substantial feature "
                "correspondence with geometric consistency."
            ),
        }

    if verified:
        return {
            "label": "GEOMETRICALLY CONSISTENT",
            "summary": (
                "A geometrically consistent correspondence was detected, "
                "but the evidence should be interpreted with the reported metrics."
            ),
        }

    if inliers >= 5:
        return {
            "label": "WEAK / INCONCLUSIVE",
            "summary": (
                "Some matching structure was detected, but the available "
                "geometric evidence is insufficient for strong verification."
            ),
        }

    return {
        "label": "NO STRONG CORRESPONDENCE",
        "summary": (
            "The current computational evidence does not establish "
            "a strong correspondence between the observations."
        ),
    }


# ============================================================
# ANALYSIS ENGINE
# ============================================================

def analyze_images(file_a, file_b):
    image_a_original, raw_a = read_image(file_a)
    image_b_original, raw_b = read_image(file_b)

    metadata_a = extract_metadata(
        raw_a,
        file_a.filename
    )

    metadata_b = extract_metadata(
        raw_b,
        file_b.filename
    )

    image_a = resize_image(
        image_a_original
    )

    image_b = resize_image(
        image_b_original
    )

    quality_a = calculate_image_quality(
        image_a
    )

    quality_b = calculate_image_quality(
        image_b
    )

    processed_a = preprocess(image_a)
    processed_b = preprocess(image_b)

    keypoints_a, descriptors_a = extract_features(
        processed_a
    )

    keypoints_b, descriptors_b = extract_features(
        processed_b
    )

    matches = calculate_reciprocal_matches(
        descriptors_a,
        descriptors_b,
    )

    geometry = calculate_homography(
        keypoints_a,
        keypoints_b,
        matches,
    )

    evidence = calculate_evidence_score(
        keypoints_a,
        keypoints_b,
        matches,
        geometry,
        quality_a,
        quality_b,
    )

    validation = build_validation(
        metadata_a,
        metadata_b,
    )

    interpretation = interpret_result(
        evidence["total"],
        geometry["verified"],
        geometry["inliers"],
    )

    visualization = create_match_visualization(
        image_a,
        keypoints_a,
        image_b,
        keypoints_b,
        matches,
        geometry,
    )

    visualization_url = None

    if visualization:

        visualization_id = (
            uuid.uuid4().hex
            + ".jpg"
        )

        visualization_path = os.path.join(
            UPLOAD_DIR,
            visualization_id
        )

        with open(
            visualization_path,
            "wb"
        ) as handle:
            handle.write(visualization)

        visualization_url = (
            "/media/"
            + visualization_id
        )

    result = {
        "engine": {
            "name": "LUNARMATCH Correspondence Engine",
            "version": "3.0",
            "feature_detector": "SIFT",
            "matcher": "BFMatcher / L2",
            "ratio_test": LOWE_RATIO,
            "reciprocal_matching": True,
            "geometric_model": "Homography",
            "verification": "RANSAC",
            "ransac_threshold_px": RANSAC_THRESHOLD,
            "max_dimension_px": MAX_DIMENSION,
            "preprocessing": [
                "grayscale",
                "CLAHE",
                "Gaussian smoothing",
            ],
        },

        "images": {
            "A": {
                "filename": file_a.filename,
                "original_width": int(
                    image_a_original.shape[1]
                ),
                "original_height": int(
                    image_a_original.shape[0]
                ),
                "processed_width": int(
                    image_a.shape[1]
                ),
                "processed_height": int(
                    image_a.shape[0]
                ),
            },

            "B": {
                "filename": file_b.filename,
                "original_width": int(
                    image_b_original.shape[1]
                ),
                "original_height": int(
                    image_b_original.shape[0]
                ),
                "processed_width": int(
                    image_b.shape[1]
                ),
                "processed_height": int(
                    image_b.shape[0]
                ),
            },
        },

        "quality": {
            "A": quality_a,
            "B": quality_b,
        },

        "features": {
            "keypoints_A": len(keypoints_a),
            "keypoints_B": len(keypoints_b),
        },

        "matching": {
            "reciprocal_matches": len(matches),
            "lowe_ratio": LOWE_RATIO,
        },

        "geometry": {
            "inliers": geometry["inliers"],
            "inlier_ratio": round(
                geometry["inlier_ratio"],
                4
            ),
            "verified": bool(
                geometry["verified"]
            ),
            "reason": geometry["reason"],
        },

        "evidence": evidence,

        "metadata": {
            "A": metadata_a,
            "B": metadata_b,
        },

        "validation": validation,

        "localization": {
            "status": (
                "AVAILABLE"
                if validation["coordinate_validation"]["status"]
                == "AVAILABLE"
                else "NOT_AVAILABLE"
            ),
            "latitude": validation[
                "coordinate_validation"
            ]["latitude"],
            "longitude": validation[
                "coordinate_validation"
            ]["longitude"],
            "basis": validation[
                "coordinate_validation"
            ]["basis"],
        },

        "interpretation": interpretation,

        "visualization_url": visualization_url,

        "limitations": [
            "The evidence score is not a probability.",
            "Visual correspondence alone does not prove geographic identity.",
            "Coordinates are never inferred without a trusted source.",
            "Instrument identity is not visually guessed.",
            "No independent lunar reference catalogue is assumed.",
            "A calibrated pixel-to-lunar-coordinate localization engine is not claimed by this version.",
        ],

        "created_at": utc_now(),
    }

    return result


# ============================================================
# REPORT GENERATION
# ============================================================

def generate_pdf_report(analysis):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
            PageBreak,
        )

    except ImportError:
        raise RuntimeError(
            "PDF report dependency is not installed."
        )

    public_id = analysis.get(
        "public_id",
        uuid.uuid4().hex
    )

    filename = (
        "LUNARMATCH_Report_"
        + public_id
        + ".pdf"
    )

    path = os.path.join(
        REPORT_DIR,
        filename
    )

    document = SimpleDocTemplate(
        path,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    story = []

    story.append(
        Paragraph(
            "LUNARMATCH",
            styles["Title"]
        )
    )

    story.append(
        Paragraph(
            "Lunar Image Correspondence & Geometric Verification",
            styles["Heading2"]
        )
    )

    story.append(
        Spacer(1, 8)
    )

    story.append(
        Paragraph(
            "Scientific analysis report",
            styles["Normal"]
        )
    )

    story.append(
        Paragraph(
            "Analysis ID: "
            + str(public_id),
            styles["Normal"]
        )
    )

    story.append(
        Paragraph(
            "Generated: "
            + str(analysis.get("created_at", utc_now())),
            styles["Normal"]
        )
    )

    story.append(
        Spacer(1, 14)
    )

    evidence = analysis["evidence"]
    geometry = analysis["geometry"]
    features = analysis["features"]
    matching = analysis["matching"]

    table_data = [
        ["Metric", "Value"],
        [
            "Evidence score",
            f'{evidence["total"]:.2f}/100'
        ],
        [
            "Keypoints — Image A",
            str(features["keypoints_A"])
        ],
        [
            "Keypoints — Image B",
            str(features["keypoints_B"])
        ],
        [
            "Reciprocal matches",
            str(matching["reciprocal_matches"])
        ],
        [
            "RANSAC inliers",
            str(geometry["inliers"])
        ],
        [
            "Inlier ratio",
            f'{geometry["inlier_ratio"] * 100:.2f}%'
        ],
        [
            "Geometric verification",
            "VERIFIED"
            if geometry["verified"]
            else "NOT VERIFIED"
        ],
    ]

    table = Table(
        table_data,
        colWidths=[75 * mm, 85 * mm]
    )

    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#111827"),
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white,
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
            ]
        )
    )

    story.append(table)

    story.append(
        Spacer(1, 14)
    )

    story.append(
        Paragraph(
            "Interpretation",
            styles["Heading2"]
        )
    )

    story.append(
        Paragraph(
            analysis["interpretation"]["label"],
            styles["Heading3"]
        )
    )

    story.append(
        Paragraph(
            analysis["interpretation"]["summary"],
            styles["Normal"]
        )
    )

    story.append(
        Spacer(1, 12)
    )

    story.append(
        Paragraph(
            "Coordinate validation",
            styles["Heading2"]
        )
    )

    localization = analysis["localization"]

    if localization["status"] == "AVAILABLE":

        story.append(
            Paragraph(
                "Latitude: "
                + str(localization["latitude"]),
                styles["Normal"]
            )
        )

        story.append(
            Paragraph(
                "Longitude: "
                + str(localization["longitude"]),
                styles["Normal"]
            )
        )

        story.append(
            Paragraph(
                "Basis: "
                + localization["basis"],
                styles["Normal"]
            )
        )

    else:

        story.append(
            Paragraph(
                "No trusted coordinate source was available.",
                styles["Normal"]
            )
        )

    story.append(
        Spacer(1, 12)
    )

    story.append(
        Paragraph(
            "Instrument / mission evidence",
            styles["Heading2"]
        )
    )

    instrument = analysis["validation"]["instrument"]

    story.append(
        Paragraph(
            "Image A: "
            + instrument["A"]["name"]
            + " — "
            + instrument["A"]["status"],
            styles["Normal"]
        )
    )

    story.append(
        Paragraph(
            "Image B: "
            + instrument["B"]["name"]
            + " — "
            + instrument["B"]["status"],
            styles["Normal"]
        )
    )

    story.append(
        Spacer(1, 12)
    )

    story.append(
        Paragraph(
            "Method",
            styles["Heading2"]
        )
    )

    story.append(
        Paragraph(
            "The current pipeline uses SIFT feature extraction, "
            "BFMatcher with L2 distance, Lowe ratio filtering, "
            "reciprocal matching, homography estimation and "
            "RANSAC geometric verification.",
            styles["Normal"]
        )
    )

    story.append(
        Spacer(1, 12)
    )

    story.append(
        Paragraph(
            "Scientific limitations",
            styles["Heading2"]
        )
    )

    for limitation in analysis["limitations"]:

        story.append(
            Paragraph(
                "• " + limitation,
                styles["Normal"]
            )
        )

    document.build(story)

    return path


# ============================================================
# PAGE ROUTES
# ============================================================

@app.context_processor
def inject_user():
    user = current_user()

    return {
        "logged_in": user is not None,
        "user_name": (
            user["name"]
            if user
            else None
        ),
        "current_user": user,
    }


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/analyze")
def analyze_page():
    return render_template("analyze.html")


@app.route("/results")
def results_page():
    return render_template("results.html")


@app.route("/validation")
def validation_page():
    return render_template("validation.html")


@app.route("/stress")
def stress_page():
    return render_template("stress.html")


@app.route("/science")
def science_page():
    return render_template("science.html")


@app.route("/about")
def about_page():
    return render_template("about.html")


@app.route("/contact")
def contact_page():
    return render_template("contact.html")


@app.route("/feedback")
def feedback_page():
    return render_template("feedback.html")


@app.route("/signin")
def signin():
    if session.get("user_id"):
        return redirect(
            url_for("workspace")
        )

    return render_template("signin.html")


@app.route("/signup")
def signup():
    if session.get("user_id"):
        return redirect(
            url_for("workspace")
        )

    return render_template("signup.html")


@app.route("/workspace")
@login_required
def workspace():
    return render_template("workspace.html")


# ============================================================
# AUTH API
# ============================================================

@app.post("/api/signup")
def api_signup():

    data = request.get_json(
        silent=True
    ) or {}

    required = [
        "name",
        "phone",
        "email",
        "username",
        "password",
        "profession",
    ]

    for field in required:

        if not clean_text(
            data.get(field)
        ):
            return json_response(
                {
                    "ok": False,
                    "error": (
                        field.replace("_", " ").title()
                        + " is required."
                    ),
                },
                400,
            )

    name = clean_text(
        data.get("name"),
        120
    )

    phone = clean_text(
        data.get("phone"),
        40
    )

    email = clean_text(
        data.get("email"),
        180
    ).lower()

    username = clean_text(
        data.get("username"),
        60
    ).lower()

    password = str(
        data.get("password")
    )

    profession = clean_text(
        data.get("profession"),
        80
    )

    if len(password) < 8:

        return json_response(
            {
                "ok": False,
                "error": (
                    "Password must contain at least 8 characters."
                ),
            },
            400,
        )

    if "@" not in email:

        return json_response(
            {
                "ok": False,
                "error": "Please enter a valid email address.",
            },
            400,
        )

    institution = clean_text(
        data.get("institution"),
        180
    )

    study_level = clean_text(
        data.get("study_level"),
        100
    )

    course = clean_text(
        data.get("course"),
        120
    )

    study_year = clean_text(
        data.get("study_year"),
        40
    )

    usage_reason = clean_text(
        data.get("usage_reason"),
        250
    )

    research_area = clean_text(
        data.get("research_area"),
        200
    )

    intended_use = clean_text(
        data.get("intended_use"),
        300
    )

    conn = get_db()

    try:

        cursor = conn.execute(
            """
            INSERT INTO users (
                name,
                phone,
                email,
                username,
                password_hash,
                profession,
                institution,
                study_level,
                course,
                study_year,
                usage_reason,
                research_area,
                intended_use,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                phone,
                email,
                username,
                hash_password(password),
                profession,
                institution,
                study_level,
                course,
                study_year,
                usage_reason,
                research_area,
                intended_use,
                utc_now(),
            ),
        )

        conn.commit()

        user_id = cursor.lastrowid

        user = conn.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    except sqlite3.IntegrityError:

        conn.close()

        return json_response(
            {
                "ok": False,
                "error": (
                    "That email or username is already registered."
                ),
            },
            409,
        )

    conn.close()

    session["user_id"] = user_id

    email_result = send_welcome_email(
        user
    )

    return json_response(
        {
            "ok": True,
            "message": (
                "Your LUNARMATCH research workspace is ready."
            ),
            "welcome_email": email_result,
            "redirect": "/workspace",
        }
    )


@app.post("/api/signin")
def api_signin():

    data = request.get_json(
        silent=True
    ) or {}

    identity = clean_text(
        data.get("identity"),
        180
    ).lower()

    password = str(
        data.get("password")
        or ""
    )

    if not identity or not password:

        return json_response(
            {
                "ok": False,
                "error": "Username/email and password are required.",
            },
            400,
        )

    conn = get_db()

    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE LOWER(email) = ?
           OR LOWER(username) = ?
        """,
        (
            identity,
            identity,
        ),
    ).fetchone()

    conn.close()

    if not user or not verify_password(
        password,
        user["password_hash"]
    ):

        return json_response(
            {
                "ok": False,
                "error": "Incorrect login details.",
            },
            401,
        )

    session["user_id"] = user["id"]

    return json_response(
        {
            "ok": True,
            "message": "Signed in successfully.",
            "redirect": "/workspace",
        }
    )


@app.post("/api/signout")
def api_signout():

    session.clear()

    return json_response(
        {
            "ok": True,
            "redirect": "/",
        }
    )


# ============================================================
# PROFILE
# ============================================================

@app.get("/api/profile")
@login_required
def api_profile():

    user = current_user()

    if not user:
        return json_response(
            {
                "ok": False,
                "error": "User not found.",
            },
            404,
        )

    data = dict(user)

    data.pop(
        "password_hash",
        None
    )

    return json_response(
        {
            "ok": True,
            "profile": data,
        }
    )


# ============================================================
# ANALYSIS API
# ============================================================

@app.post("/api/analyze")
def api_analyze():

    file_a = request.files.get(
        "image_a"
    )

    file_b = request.files.get(
        "image_b"
    )

    if not file_a or not file_b:

        return json_response(
            {
                "ok": False,
                "error": "Please provide two images.",
            },
            400,
        )

    if not allowed_file(
        file_a.filename
    ):

        return json_response(
            {
                "ok": False,
                "error": "Image A has an unsupported file type.",
            },
            400,
        )

    if not allowed_file(
        file_b.filename
    ):

        return json_response(
            {
                "ok": False,
                "error": "Image B has an unsupported file type.",
            },
            400,
        )

    try:

        result = analyze_images(
            file_a,
            file_b
        )

    except ValueError as exc:

        return json_response(
            {
                "ok": False,
                "error": str(exc),
            },
            400,
        )

    except Exception as exc:

        app.logger.exception(
            "Analysis error"
        )

        return json_response(
            {
                "ok": False,
                "error": (
                    "The analysis engine encountered an unexpected error."
                ),
                "detail": str(exc)
                if app.debug
                else None,
            },
            500,
        )

    public_id = uuid.uuid4().hex

    result["public_id"] = public_id

    user_id = session.get(
        "user_id"
    )

    conn = get_db()

    conn.execute(
        """
        INSERT INTO analyses (
            public_id,
            user_id,
            image_a_name,
            image_b_name,
            score,
            verified,
            result_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            public_id,
            user_id,
            file_a.filename,
            file_b.filename,
            result["evidence"]["total"],
            int(
                result["geometry"]["verified"]
            ),
            json.dumps(
                result,
                separators=(",", ":")
            ),
            utc_now(),
        ),
    )

    conn.commit()
    conn.close()

    return json_response(
        {
            "ok": True,
            "analysis": result,
        }
    )


@app.get("/api/results")
def api_results():

    public_id = clean_text(
        request.args.get("id"),
        100
    )

    if public_id:

        conn = get_db()

        row = conn.execute(
            """
            SELECT *
            FROM analyses
            WHERE public_id = ?
            """,
            (public_id,),
        ).fetchone()

        conn.close()

        if not row:

            return json_response(
                {
                    "ok": False,
                    "error": "Analysis not found.",
                },
                404,
            )

        result = safe_json(
            row["result_json"]
        )

        return json_response(
            {
                "ok": True,
                "analysis": result,
            }
        )

    user_id = session.get(
        "user_id"
    )

    if not user_id:

        return json_response(
            {
                "ok": True,
                "analyses": [],
                "message": (
                    "Sign in to view saved analysis history."
                ),
            }
        )

    conn = get_db()

    rows = conn.execute(
        """
        SELECT
            public_id,
            image_a_name,
            image_b_name,
            score,
            verified,
            created_at
        FROM analyses
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (
            user_id,
            MAX_ANALYSIS_HISTORY,
        ),
    ).fetchall()

    conn.close()

    return json_response(
        {
            "ok": True,
            "analyses": [
                dict(row)
                for row in rows
            ],
        }
    )


# ============================================================
# PDF REPORT
# ============================================================

@app.get("/api/report/<public_id>")
@login_required
def api_report(public_id):

    conn = get_db()

    row = conn.execute(
        """
        SELECT *
        FROM analyses
        WHERE public_id = ?
          AND user_id = ?
        """,
        (
            public_id,
            session["user_id"],
        ),
    ).fetchone()

    conn.close()

    if not row:

        return json_response(
            {
                "ok": False,
                "error": (
                    "This report belongs to a different user "
                    "or does not exist."
                ),
            },
            404,
        )

    analysis = safe_json(
        row["result_json"]
    )

    analysis["public_id"] = public_id

    try:

        path = generate_pdf_report(
            analysis
        )

    except RuntimeError as exc:

        return json_response(
            {
                "ok": False,
                "error": str(exc),
            },
            500,
        )

    except Exception:

        app.logger.exception(
            "PDF generation error"
        )

        return json_response(
            {
                "ok": False,
                "error": "Could not generate the PDF report.",
            },
            500,
        )

    return send_file(
        path,
        as_attachment=True,
        download_name=os.path.basename(path),
        mimetype="application/pdf",
    )


# ============================================================
# FEEDBACK API
# ============================================================

@app.post("/api/feedback")
def api_feedback():

    data = request.get_json(
        silent=True
    ) or {}

    message = clean_text(
        data.get("message"),
        3000
    )

    feedback_type = clean_text(
        data.get("feedback_type"),
        80
    )

    if not message:

        return json_response(
            {
                "ok": False,
                "error": "Please enter your feedback.",
            },
            400,
        )

    if not feedback_type:

        return json_response(
            {
                "ok": False,
                "error": "Please select a feedback type.",
            },
            400,
        )

    rating = data.get(
        "rating"
    )

    try:

        if rating not in [
            None,
            "",
        ]:
            rating = int(rating)

            if not 1 <= rating <= 5:
                rating = None

    except Exception:

        rating = None

    user = current_user()

    name = clean_text(
        data.get("name"),
        120
    )

    email = clean_text(
        data.get("email"),
        180
    )

    user_id = None

    if user:

        user_id = user["id"]

        if not name:
            name = user["name"]

        if not email:
            email = user["email"]

    conn = get_db()

    conn.execute(
        """
        INSERT INTO feedback (
            user_id,
            name,
            email,
            feedback_type,
            rating,
            message,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            name,
            email,
            feedback_type,
            rating,
            message,
            utc_now(),
        ),
    )

    conn.commit()
    conn.close()

    return json_response(
        {
            "ok": True,
            "message": (
                "Thank you. Your feedback has been recorded."
            ),
        }
    )


# ============================================================
# REAL STRESS TESTING
# ============================================================

def transform_image(image, test_type, severity):

    severity = max(
        0.0,
        min(
            1.0,
            float(severity)
        )
    )

    if test_type == "rotation":

        angle = 5.0 + severity * 35.0

        height, width = image.shape[:2]

        center = (
            width / 2.0,
            height / 2.0
        )

        matrix = cv2.getRotationMatrix2D(
            center,
            angle,
            1.0
        )

        return cv2.warpAffine(
            image,
            matrix,
            (width, height),
            borderMode=cv2.BORDER_REFLECT
        )

    if test_type == "scale":

        scale = (
            1.0
            - 0.45 * severity
        )

        height, width = image.shape[:2]

        resized = cv2.resize(
            image,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_AREA,
        )

        canvas = np.zeros_like(image)

        new_h, new_w = resized.shape[:2]

        y = max(
            0,
            (height - new_h) // 2
        )

        x = max(
            0,
            (width - new_w) // 2
        )

        crop_h = min(
            new_h,
            height - y
        )

        crop_w = min(
            new_w,
            width - x
        )

        canvas[
            y:y + crop_h,
            x:x + crop_w
        ] = resized[
            :crop_h,
            :crop_w
        ]

        return canvas

    if test_type == "brightness":

        delta = int(
            20 + severity * 80
        )

        result = image.astype(
            np.int16
        )

        result += delta

        return np.clip(
            result,
            0,
            255
        ).astype(np.uint8)

    if test_type == "contrast":

        factor = (
            1.0
            + severity * 1.5
        )

        result = image.astype(
            np.float32
        )

        result = (
            (result - 128.0)
            * factor
            + 128.0
        )

        return np.clip(
            result,
            0,
            255
        ).astype(np.uint8)

    if test_type == "noise":

        sigma = (
            5.0
            + severity * 45.0
        )

        noise = np.random.normal(
            0,
            sigma,
            image.shape
        )

        result = (
            image.astype(np.float32)
            + noise
        )

        return np.clip(
            result,
            0,
            255
        ).astype(np.uint8)

    if test_type == "blur":

        kernel_size = int(
            3
            + round(
                severity * 10
            ) * 2
        )

        kernel_size = max(
            3,
            min(
                23,
                kernel_size
            )
        )

        if kernel_size % 2 == 0:
            kernel_size += 1

        return cv2.GaussianBlur(
            image,
            (
                kernel_size,
                kernel_size
            ),
            0
        )

    if test_type == "crop":

        height, width = image.shape[:2]

        keep = (
            1.0
            - severity * 0.45
        )

        new_h = int(
            height * keep
        )

        new_w = int(
            width * keep
        )

        y = (
            height - new_h
        ) // 2

        x = (
            width - new_w
        ) // 2

        cropped = image[
            y:y + new_h,
            x:x + new_w
        ]

        return cv2.resize(
            cropped,
            (width, height),
            interpolation=cv2.INTER_AREA,
        )

    raise ValueError(
        "Unsupported stress transformation."
    )


def run_stress_analysis(
    base_image,
    transformed_image,
):
    base_processed = preprocess(
        base_image
    )

    transformed_processed = preprocess(
        transformed_image
    )

    keypoints_a, descriptors_a = extract_features(
        base_processed
    )

    keypoints_b, descriptors_b = extract_features(
        transformed_processed
    )

    matches = calculate_reciprocal_matches(
        descriptors_a,
        descriptors_b
    )

    geometry = calculate_homography(
        keypoints_a,
        keypoints_b,
        matches
    )

    quality_a = calculate_image_quality(
        base_image
    )

    quality_b = calculate_image_quality(
        transformed_image
    )

    evidence = calculate_evidence_score(
        keypoints_a,
        keypoints_b,
        matches,
        geometry,
        quality_a,
        quality_b,
    )

    return {
        "score": evidence["total"],
        "keypoints_base": len(keypoints_a),
        "keypoints_test": len(keypoints_b),
        "matches": len(matches),
        "inliers": geometry["inliers"],
        "inlier_ratio": geometry["inlier_ratio"],
        "verified": geometry["verified"],
        "quality_base": quality_a,
        "quality_test": quality_b,
    }


@app.post("/api/stress")
def api_stress():

    file = request.files.get(
        "image"
    )

    test_type = clean_text(
        request.form.get(
            "type"
        ),
        50
    )

    severity_raw = request.form.get(
        "severity",
        "0.5"
    )

    if not file:

        return json_response(
            {
                "ok": False,
                "error": "Please provide an image.",
            },
            400,
        )

    if not allowed_file(
        file.filename
    ):

        return json_response(
            {
                "ok": False,
                "error": "Unsupported image type.",
            },
            400,
        )

    try:

        severity = float(
            severity_raw
        )

        severity = max(
            0.0,
            min(
                1.0,
                severity
            )
        )

    except Exception:

        return json_response(
            {
                "ok": False,
                "error": "Invalid stress severity.",
            },
            400,
        )

    try:

        base_image, raw = read_image(
            file
        )

        base_image = resize_image(
            base_image
        )

        transformed = transform_image(
            base_image,
            test_type,
            severity
        )

        baseline = run_stress_analysis(
            base_image,
            base_image
        )

        stressed = run_stress_analysis(
            base_image,
            transformed
        )

        degradation = (
            baseline["score"]
            - stressed["score"]
        )

        stability = max(
            0.0,
            min(
                100.0,
                100.0 - max(
                    0.0,
                    degradation
                )
            )
        )

        transformed_bytes = image_to_jpeg_bytes(
            transformed
        )

        transformed_url = None

        if transformed_bytes:

            transformed_id = (
                "stress_"
                + uuid.uuid4().hex
                + ".jpg"
            )

            transformed_path = os.path.join(
                UPLOAD_DIR,
                transformed_id
            )

            with open(
                transformed_path,
                "wb"
            ) as handle:
                handle.write(
                    transformed_bytes
                )

            transformed_url = (
                "/media/"
                + transformed_id
            )

        return json_response(
            {
                "ok": True,
                "stress": {
                    "type": test_type,
                    "severity": round(
                        severity,
                        3
                    ),
                    "baseline": baseline,
                    "test": stressed,
                    "score_change": round(
                        degradation,
                        2
                    ),
                    "stability": round(
                        stability,
                        2
                    ),
                    "verified": stressed[
                        "verified"
                    ],
                    "interpretation": (
                        "Correspondence remained geometrically verified "
                        "under this transformation."
                        if stressed["verified"]
                        else
                        "Verification was not maintained under this transformation."
                    ),
                    "transformed_image": transformed_url,
                },
            }
        )

    except ValueError as exc:

        return json_response(
            {
                "ok": False,
                "error": str(exc),
            },
            400,
        )

    except Exception:

        app.logger.exception(
            "Stress test error"
        )

        return json_response(
            {
                "ok": False,
                "error": "Stress testing failed unexpectedly.",
            },
            500,
        )


# ============================================================
# MEDIA
# ============================================================

@app.route("/media/<filename>")
def media(filename):

    # Only serve generated media files.
    # Do not accept arbitrary filesystem paths.

    if (
        "/" in filename
        or "\\"
        in filename
        or ".."
        in filename
    ):
        abort(404)

    path = os.path.join(
        UPLOAD_DIR,
        filename
    )

    if not os.path.isfile(path):
        abort(404)

    return send_file(
        path
    )


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    sift_available = True

    try:
        create_sift()
    except Exception:
        sift_available = False

    database_available = True

    try:

        conn = get_db()

        conn.execute(
            "SELECT 1"
        )

        conn.close()

    except Exception:

        database_available = False

    return json_response(
        {
            "ok": (
                sift_available
                and database_available
            ),
            "service": "LUNARMATCH",
            "version": "3.0",
            "engine": {
                "opencv": cv2.__version__,
                "sift": sift_available,
            },
            "database": database_available,
            "features": {
                "correspondence": True,
                "geometric_verification": True,
                "metadata_extraction": True,
                "coordinate_provenance": True,
                "stress_testing": True,
                "pdf_reports": True,
                "feedback": True,
                "welcome_email": bool(
                    os.environ.get("SMTP_HOST")
                ),
            },
        }
    )


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(413)
def file_too_large(error):

    if request.path.startswith("/api/"):

        return json_response(
            {
                "ok": False,
                "error": (
                    "The uploaded file is larger than 25 MB."
                ),
            },
            413,
        )

    return (
        "Uploaded file is larger than 25 MB.",
        413
    )


@app.errorhandler(404)
def not_found(error):

    if request.path.startswith("/api/"):

        return json_response(
            {
                "ok": False,
                "error": "API endpoint not found.",
            },
            404,
        )

    return render_template(
        "home.html"
    ), 404


@app.errorhandler(500)
def internal_error(error):

    app.logger.exception(
        "Unhandled server error"
    )

    if request.path.startswith("/api/"):

        return json_response(
            {
                "ok": False,
                "error": (
                    "The server encountered an unexpected error."
                ),
            },
            500,
        )

    return (
        "LUNARMATCH encountered an unexpected server error.",
        500
    )


# ============================================================
# DEVELOPMENT ENTRY POINT
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=True,
    )
