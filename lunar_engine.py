import math
import numpy as np
import cv2

MAX_FEATURES = 500
PATCH_RADIUS = 5
MATCH_RATIO = 0.78
RANSAC_ITERATIONS = 180
RANSAC_THRESHOLD = 10.0


def calculate_quality(gray):
    h, w = gray.shape
    gray_f = gray.astype(np.float32)
    mean = float(np.mean(gray_f))
    variance = max(0.0, float(np.mean(gray_f * gray_f) - mean * mean))
    contrast = math.sqrt(variance)
    if h > 2 and w > 2:
        gx = gray_f[1:-1, 2:] - gray_f[1:-1, :-2]
        gy = gray_f[2:, 1:-1] - gray_f[:-2, 1:-1]
        avg_edge = float(np.sqrt(gx * gx + gy * gy).mean())
    else:
        avg_edge = 0.0
    contrast_score = max(0.0, min(100.0, contrast / 64.0 * 100.0))
    sharpness_score = max(0.0, min(100.0, avg_edge / 35.0 * 100.0))
    quality = 0.55 * contrast_score + 0.45 * sharpness_score
    return {
        "contrast": round(contrast_score, 3),
        "sharpness": round(sharpness_score, 3),
        "quality": round(quality, 3),
    }


def detect_features(gray):
    h, w = gray.shape
    candidates = []
    border = 8
    step = max(2, int(min(w, h) / 180))
    for y in range(border, h - border, step):
        for x in range(border, w - border, step):
            gx = float(gray[y, x + 1] - gray[y, x - 1])
            gy = float(gray[y + 1, x] - gray[y - 1, x])
            g = math.sqrt(gx * gx + gy * gy)
            if g < 12:
                continue
            gxx = float(gray[y, x + 1] + gray[y, x - 1] - 2.0 * gray[y, x])
            gyy = float(gray[y + 1, x] + gray[y - 1, x] - 2.0 * gray[y, x])
            corner = abs(gxx * gyy)
            candidates.append({"x": x, "y": y, "score": g * 0.7 + corner * 0.3})
    candidates.sort(key=lambda p: p["score"], reverse=True)
    selected = []
    min_distance = max(8.0, min(w, h) / 35.0)
    min_dist_sq = min_distance * min_distance
    for point in candidates:
        valid = True
        for chosen in selected:
            dx = point["x"] - chosen["x"]
            dy = point["y"] - chosen["y"]
            if dx * dx + dy * dy < min_dist_sq:
                valid = False
                break
        if valid:
            selected.append(point)
        if len(selected) >= MAX_FEATURES:
            break
    return selected


def describe_feature(gray, point):
    h, w = gray.shape
    descriptor = []
    r = PATCH_RADIUS
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            x = min(w - 1, max(0, int(round(point["x"] + dx))))
            y = min(h - 1, max(0, int(round(point["y"] + dy))))
            descriptor.append(float(gray[y, x]))
    desc = np.asarray(descriptor, dtype=np.float32)
    desc -= float(np.mean(desc))
    std = math.sqrt(float(np.mean(desc * desc))) or 1.0
    desc /= std
    return desc


def build_descriptors(gray, features):
    return [
        {**point, "descriptor": describe_feature(gray, point)}
        for point in features
    ]


def descriptor_distance(a, b):
    d = a - b
    return math.sqrt(float(np.dot(d, d)))


def match_features(features_a, features_b):
    forward = []
    if not features_a or not features_b:
        return forward
    for i, feature_a in enumerate(features_a):
        best = None
        second = None
        for j, feature_b in enumerate(features_b):
            distance = descriptor_distance(feature_a["descriptor"], feature_b["descriptor"])
            if best is None or distance < best["distance"]:
                second = best
                best = {"a": i, "b": j, "distance": distance}
            elif second is None or distance < second["distance"]:
                second = {"a": i, "b": j, "distance": distance}
        if best and second and best["distance"] < second["distance"] * MATCH_RATIO:
            forward.append(best)
    return forward


def reciprocal_matches(features_a, features_b, matches):
    reverse_best = {}
    for j, feature_b in enumerate(features_b):
        best_index = -1
        best_distance = float("inf")
        for i, feature_a in enumerate(features_a):
            distance = descriptor_distance(feature_b["descriptor"], feature_a["descriptor"])
            if distance < best_distance:
                best_distance = distance
                best_index = i
        reverse_best[j] = best_index
    return [m for m in matches if reverse_best.get(m["b"]) == m["a"]]


def solve_affine(p1, p2, p3, q1, q2, q3):
    matrix = np.asarray([
        [p1["x"], p1["y"], 1.0],
        [p2["x"], p2["y"], 1.0],
        [p3["x"], p3["y"], 1.0],
    ], dtype=np.float64)
    bx = np.asarray([q1["x"], q2["x"], q3["x"]], dtype=np.float64)
    by = np.asarray([q1["y"], q2["y"], q3["y"]], dtype=np.float64)
    try:
        sx = np.linalg.solve(matrix, bx)
        sy = np.linalg.solve(matrix, by)
    except np.linalg.LinAlgError:
        return None
    return {
        "a": float(sx[0]), "b": float(sx[1]), "tx": float(sx[2]),
        "c": float(sy[0]), "d": float(sy[1]), "ty": float(sy[2]),
    }


def transform_point(model, point):
    return {
        "x": model["a"] * point["x"] + model["b"] * point["y"] + model["tx"],
        "y": model["c"] * point["x"] + model["d"] * point["y"] + model["ty"],
    }


def affine_to_homography(model):
    if model is None:
        return None
    return np.asarray([
        [model["a"], model["b"], model["tx"]],
        [model["c"], model["d"], model["ty"]],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64)


def verify_geometry(features_a, features_b, matches):
    if len(matches) < 3:
        return {"model": None, "inlier_indices": [], "reprojection_errors": [], "ratio": 0.0, "consistency": 0.0}
    rng = np.random.default_rng(42)
    best_model = None
    best_inliers = []
    for _ in range(RANSAC_ITERATIONS):
        try:
            indices = rng.choice(len(matches), size=3, replace=False).tolist()
        except ValueError:
            break
        model = solve_affine(
            features_a[matches[indices[0]]["a"]],
            features_a[matches[indices[1]]["a"]],
            features_a[matches[indices[2]]["a"]],
            features_b[matches[indices[0]]["b"]],
            features_b[matches[indices[1]]["b"]],
            features_b[matches[indices[2]]["b"]],
        )
        if model is None:
            continue
        inliers = []
        for i, match in enumerate(matches):
            projected = transform_point(model, features_a[match["a"]])
            target = features_b[match["b"]]
            error = math.hypot(projected["x"] - target["x"], projected["y"] - target["y"])
            if error <= RANSAC_THRESHOLD:
                inliers.append(i)
        if len(inliers) > len(best_inliers):
            best_model = model
            best_inliers = inliers
    reprojection_errors = []
    if best_model is not None:
        for match in matches:
            projected = transform_point(best_model, features_a[match["a"]])
            target = features_b[match["b"]]
            reprojection_errors.append(math.hypot(projected["x"] - target["x"], projected["y"] - target["y"]))
    ratio = len(best_inliers) / max(1, len(matches))
    return {
        "model": best_model,
        "inlier_indices": best_inliers,
        "reprojection_errors": reprojection_errors,
        "ratio": ratio,
        "consistency": max(0.0, min(100.0, ratio * 100.0)),
    }


def calculate_coverage(features_a, inlier_matches):
    if not features_a or not inlier_matches:
        return 0.0
    min_x = min(p["x"] for p in features_a)
    max_x = max(p["x"] for p in features_a)
    min_y = min(p["y"] for p in features_a)
    max_y = max(p["y"] for p in features_a)
    range_x = max(1.0, max_x - min_x)
    range_y = max(1.0, max_y - min_y)
    cells = set()
    for match in inlier_matches:
        p = features_a[match["a"]]
        gx = int(((p["x"] - min_x) / range_x) * 5)
        gy = int(((p["y"] - min_y) / range_y) * 5)
        cells.add((max(0, min(4, gx)), max(0, min(4, gy))))
    return len(cells) / 25.0 * 100.0


def calculate_score(verified, candidate, coverage, geometry, quality):
    verification_score = max(0.0, min(100.0, verified / max(1, candidate) * 100.0))
    feature_score = max(0.0, min(100.0, verified / 30.0 * 100.0))
    return max(0.0, min(100.0,
        verification_score * 0.30
        + feature_score * 0.20
        + coverage * 0.15
        + geometry * 0.25
        + quality * 0.10,
    ))


def confidence_label(score):
    if score >= 80:
        return "HIGH"
    if score >= 60:
        return "MODERATE"
    if score >= 40:
        return "LOW"
    return "VERY LOW"


def run(gray_a, gray_b):
    quality_a = calculate_quality(gray_a)
    quality_b = calculate_quality(gray_b)
    features_a = build_descriptors(gray_a, detect_features(gray_a))
    features_b = build_descriptors(gray_b, detect_features(gray_b))
    raw = match_features(features_a, features_b)
    reciprocal = reciprocal_matches(features_a, features_b, raw)
    geometry = verify_geometry(features_a, features_b, reciprocal)
    inlier_matches = [reciprocal[i] for i in geometry["inlier_indices"]]
    coverage = calculate_coverage(features_a, inlier_matches)
    average_quality = (quality_a["quality"] + quality_b["quality"]) / 2.0
    score = calculate_score(len(inlier_matches), len(reciprocal), coverage, geometry["consistency"], average_quality)
    confidence_value = max(0.0, min(100.0, score * 0.92 + geometry["consistency"] * 0.08))
    return {
        "features_a": features_a,
        "features_b": features_b,
        "raw_matches": raw,
        "reciprocal_matches": reciprocal,
        "geometry": geometry,
        "inlier_matches": inlier_matches,
        "coverage": coverage,
        "quality_a": quality_a,
        "quality_b": quality_b,
        "average_quality": average_quality,
        "score": score,
        "confidence_value": confidence_value,
        "confidence_label": confidence_label(confidence_value),
        "homography": affine_to_homography(geometry["model"]),
    }


def custom_to_cv_keypoints(features):
    return [cv2.KeyPoint(float(f["x"]), float(f["y"]), 1.0) for f in features]


def custom_to_cv_matches(matches):
    return [cv2.DMatch(int(m["a"]), int(m["b"]), float(m["distance"])) for m in matches]


def draw_correspondence(gray_a, gray_b, features_a, features_b, matches, inlier_indices, out_path):
    h1, w1 = gray_a.shape
    h2, w2 = gray_b.shape
    gap = 24
    header_h = 62
    max_width = 1600
    scale = min(1.0, (max_width - gap) / max(1, w1 + w2))
    wa, wb = max(1, round(w1 * scale)), max(1, round(w2 * scale))
    ha, hb = max(1, round(h1 * scale)), max(1, round(h2 * scale))
    height = header_h + max(ha, hb)
    width = wa + gap + wb
    canvas = np.full((height, width, 3), 9, dtype=np.uint8)
    a_img = cv2.resize(cv2.cvtColor(gray_a, cv2.COLOR_GRAY2BGR), (wa, ha), interpolation=cv2.INTER_AREA)
    b_img = cv2.resize(cv2.cvtColor(gray_b, cv2.COLOR_GRAY2BGR), (wb, hb), interpolation=cv2.INTER_AREA)
    canvas[header_h:header_h + ha, :wa] = a_img
    canvas[header_h:header_h + hb, wa + gap:wa + gap + wb] = b_img
    inlier_set = set(inlier_indices)
    for index, match in enumerate(matches):
        p = features_a[match["a"]]
        q = features_b[match["b"]]
        pxy = (int(round(p["x"] * scale)), header_h + int(round(p["y"] * scale)))
        qxy = (wa + gap + int(round(q["x"] * scale)), header_h + int(round(q["y"] * scale)))
        good = index in inlier_set
        cv2.line(canvas, pxy, qxy, (230, 245, 255) if good else (85, 90, 100), 2 if good else 1, cv2.LINE_AA)
        if good:
            cv2.circle(canvas, pxy, 4, (245, 250, 255), -1, cv2.LINE_AA)
            cv2.circle(canvas, qxy, 4, (245, 250, 255), -1, cv2.LINE_AA)
    cv2.rectangle(canvas, (0, 0), (width - 1, header_h - 1), (11, 18, 28), -1)
    cv2.putText(canvas, "LUNARMATCH CORRESPONDENCE", (14, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (235, 245, 255), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"{len(matches)} CANDIDATES  |  {len(inlier_indices)} VERIFIED  |  {len(matches) - len(inlier_indices)} OUTLIERS", (14, 47), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 205, 235), 1, cv2.LINE_AA)
    cv2.imwrite(str(out_path), canvas, [cv2.IMWRITE_JPEG_QUALITY, 94])
