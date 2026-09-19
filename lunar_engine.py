import math

import cv2
import numpy as np

# Golden, compatibility-focused configuration derived from the original
# browser LunarMatch engine. The thresholds are kept unchanged.
MAX_FEATURES = 500
PATCH_RADIUS = 5
MATCH_RATIO = 0.78
RANSAC_ITERATIONS = 180
RANSAC_THRESHOLD = 10.0


def calculate_quality(gray):
    gray_f = np.asarray(gray, dtype=np.float32)
    h, w = gray_f.shape
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
    return {"contrast": round(contrast_score, 3), "sharpness": round(sharpness_score, 3), "quality": round(quality, 3)}


def detect_features(gray):
    """Vectorized equivalent of the original gradient/corner detector."""
    gray = np.asarray(gray, dtype=np.float32)
    h, w = gray.shape
    border = 8
    step = max(2, int(min(w, h) / 180))

    if h <= 2 * border or w <= 2 * border:
        return []

    ys = np.arange(border, h - border, step, dtype=np.int32)
    xs = np.arange(border, w - border, step, dtype=np.int32)
    if ys.size == 0 or xs.size == 0:
        return []

    center = gray[np.ix_(ys, xs)]
    gx = gray[np.ix_(ys, xs + 1)] - gray[np.ix_(ys, xs - 1)]
    gy = gray[np.ix_(ys + 1, xs)] - gray[np.ix_(ys - 1, xs)]
    g = np.sqrt(gx * gx + gy * gy)
    gxx = gray[np.ix_(ys, xs + 1)] + gray[np.ix_(ys, xs - 1)] - 2.0 * center
    gyy = gray[np.ix_(ys + 1, xs)] + gray[np.ix_(ys - 1, xs)] - 2.0 * center
    score = g * 0.7 + np.abs(gxx * gyy) * 0.3

    keep = g >= 12.0
    if not np.any(keep):
        return []

    yy, xx = np.nonzero(keep)
    scores = score[yy, xx]

    # Stable descending sort reproduces the browser engine's stable sort for ties.
    order = np.argsort(-scores, kind="stable")
    min_distance = max(8.0, min(w, h) / 35.0)
    min_dist_sq = min_distance * min_distance

    selected = []
    # Spatial hash for exact-equivalent minimum-distance suppression.
    # Because candidates are processed in descending score order, checking
    # the current bucket and its 8 neighbors is sufficient to reproduce the
    # original pairwise distance rule while avoiding O(candidates * 500).
    cell_size = min_distance
    buckets = {}

    for idx in order:
        x = int(xs[xx[idx]])
        y = int(ys[yy[idx]])
        cx = int(np.floor(x / cell_size))
        cy = int(np.floor(y / cell_size))
        valid = True

        for by in range(cy - 1, cy + 2):
            for bx in range(cx - 1, cx + 2):
                for chosen_index in buckets.get((bx, by), ()): 
                    chosen = selected[chosen_index]
                    dx = x - chosen["x"]
                    dy = y - chosen["y"]
                    if dx * dx + dy * dy < min_dist_sq:
                        valid = False
                        break
                if not valid:
                    break
            if not valid:
                break

        if valid:
            selected.append({"x": x, "y": y, "score": float(scores[idx])})
            bucket = buckets.setdefault((cx, cy), [])
            bucket.append(len(selected) - 1)
            if len(selected) >= MAX_FEATURES:
                break

    return selected


def build_descriptors(gray, features):
    """Vectorized 11x11 edge-padded patch descriptor construction."""
    gray = np.asarray(gray, dtype=np.float32)
    if not features:
        return []

    r = PATCH_RADIUS
    ys = np.asarray([f["y"] for f in features], dtype=np.int32)
    xs = np.asarray([f["x"] for f in features], dtype=np.int32)
    padded = np.pad(gray, r, mode="edge")
    offsets = np.arange(-r, r + 1, dtype=np.int32)
    yi = ys[:, None, None] + r + offsets[None, :, None]
    xi = xs[:, None, None] + r + offsets[None, None, :]
    patches = padded[yi, xi].reshape(len(features), -1).astype(np.float32, copy=False)

    patches -= patches.mean(axis=1, keepdims=True)
    std = np.sqrt(np.mean(patches * patches, axis=1, keepdims=True))
    std[std == 0] = 1.0
    patches /= std

    out = []
    for i, feature in enumerate(features):
        item = dict(feature)
        item["descriptor"] = patches[i]
        out.append(item)
    return out


def _descriptor_matrix(features):
    if not features:
        return np.empty((0, (2 * PATCH_RADIUS + 1) ** 2), dtype=np.float32)
    return np.stack([f["descriptor"] for f in features]).astype(np.float32, copy=False)


def _distance_matrix(features_a, features_b):
    a = _descriptor_matrix(features_a)
    b = _descriptor_matrix(features_b)
    if not len(a) or not len(b):
        return np.empty((len(a), len(b)), dtype=np.float32)
    a2 = np.sum(a * a, axis=1, keepdims=True)
    b2 = np.sum(b * b, axis=1, keepdims=True).T
    d2 = a2 + b2 - 2.0 * (a @ b.T)
    np.maximum(d2, 0.0, out=d2)
    return np.sqrt(d2, out=d2)


def match_features(features_a, features_b, distances):
    if not features_a or not features_b or distances.shape[1] < 2:
        return []
    order = np.argpartition(distances, kth=1, axis=1)[:, :2]
    first = order[:, 0]
    second = order[:, 1]
    d1 = distances[np.arange(len(features_a)), first]
    d2 = distances[np.arange(len(features_a)), second]
    swap = d2 < d1
    chosen = first.copy()
    chosen[swap] = second[swap]
    d_best = d1.copy()
    d_best[swap] = d2[swap]
    d_second = d2.copy()
    d_second[swap] = d1[swap]
    mask = d_best < d_second * MATCH_RATIO
    idxs = np.flatnonzero(mask)
    return [{"a": int(i), "b": int(chosen[i]), "distance": float(d_best[i])} for i in idxs]


def reciprocal_matches(matches, distances):
    if not matches or distances.size == 0:
        return []
    reverse_best = np.argmin(distances, axis=0)
    return [m for m in matches if int(reverse_best[m["b"]]) == m["a"]]


def solve_affine(p1, p2, p3, q1, q2, q3):
    A = np.asarray([[p1["x"], p1["y"], 1.0], [p2["x"], p2["y"], 1.0], [p3["x"], p3["y"], 1.0]], dtype=np.float64)
    bx = np.asarray([q1["x"], q2["x"], q3["x"]], dtype=np.float64)
    by = np.asarray([q1["y"], q2["y"], q3["y"]], dtype=np.float64)
    try:
        sx = np.linalg.solve(A, bx)
        sy = np.linalg.solve(A, by)
    except np.linalg.LinAlgError:
        return None
    return {"a": float(sx[0]), "b": float(sx[1]), "tx": float(sx[2]), "c": float(sy[0]), "d": float(sy[1]), "ty": float(sy[2])}


def verify_geometry(features_a, features_b, matches):
    if len(matches) < 3:
        return {"model": None, "inlier_indices": [], "reprojection_errors": [], "ratio": 0.0, "consistency": 0.0}

    src = np.asarray([[features_a[m["a"]]["x"], features_a[m["a"]]["y"]] for m in matches], dtype=np.float64)
    dst = np.asarray([[features_b[m["b"]]["x"], features_b[m["b"]]["y"]] for m in matches], dtype=np.float64)

    # With exactly three matches, affine estimation has one possible sample.
    # Repeating a 180-iteration RANSAC loop would add latency without adding
    # any new information, so solve that case directly.
    if len(matches) == 3:
        model = solve_affine(
            features_a[matches[0]["a"]], features_a[matches[1]["a"]], features_a[matches[2]["a"]],
            features_b[matches[0]["b"]], features_b[matches[1]["b"]], features_b[matches[2]["b"]],
        )
        if model is None:
            return {"model": None, "inlier_indices": [], "reprojection_errors": [], "ratio": 0.0, "consistency": 0.0}
        projected_x = model["a"] * src[:, 0] + model["b"] * src[:, 1] + model["tx"]
        projected_y = model["c"] * src[:, 0] + model["d"] * src[:, 1] + model["ty"]
        errors = np.hypot(projected_x - dst[:, 0], projected_y - dst[:, 1])
        inliers = np.flatnonzero(errors <= RANSAC_THRESHOLD).tolist()
        ratio = len(inliers) / 3.0
        return {"model": model, "inlier_indices": inliers, "reprojection_errors": errors.tolist(), "ratio": ratio, "consistency": max(0.0, min(100.0, ratio * 100.0))}

    rng = np.random.default_rng(42)
    best_model = None
    best_inliers = []

    for _ in range(RANSAC_ITERATIONS):
        idx = rng.choice(len(matches), size=3, replace=False)
        model = solve_affine(
            features_a[matches[int(idx[0])]["a"]], features_a[matches[int(idx[1])]["a"]], features_a[matches[int(idx[2])]["a"]],
            features_b[matches[int(idx[0])]["b"]], features_b[matches[int(idx[1])]["b"]], features_b[matches[int(idx[2])]["b"]],
        )
        if model is None:
            continue
        projected_x = model["a"] * src[:, 0] + model["b"] * src[:, 1] + model["tx"]
        projected_y = model["c"] * src[:, 0] + model["d"] * src[:, 1] + model["ty"]
        errors = np.hypot(projected_x - dst[:, 0], projected_y - dst[:, 1])
        inliers = np.flatnonzero(errors <= RANSAC_THRESHOLD).tolist()
        if len(inliers) > len(best_inliers):
            best_model = model
            best_inliers = inliers

    if best_model is None:
        errors = []
    else:
        projected_x = best_model["a"] * src[:, 0] + best_model["b"] * src[:, 1] + best_model["tx"]
        projected_y = best_model["c"] * src[:, 0] + best_model["d"] * src[:, 1] + best_model["ty"]
        errors = np.hypot(projected_x - dst[:, 0], projected_y - dst[:, 1]).tolist()

    ratio = len(best_inliers) / max(1, len(matches))
    return {"model": best_model, "inlier_indices": best_inliers, "reprojection_errors": errors, "ratio": ratio, "consistency": max(0.0, min(100.0, ratio * 100.0))}


def calculate_coverage(features_a, inlier_matches):
    if not features_a or not inlier_matches:
        return 0.0
    min_x = min(p["x"] for p in features_a); max_x = max(p["x"] for p in features_a)
    min_y = min(p["y"] for p in features_a); max_y = max(p["y"] for p in features_a)
    range_x = max(1.0, max_x - min_x); range_y = max(1.0, max_y - min_y)
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
        verification_score * 0.30 + feature_score * 0.20 + coverage * 0.15 + geometry * 0.25 + quality * 0.10,
    ))


def confidence_label(score):
    if score >= 80: return "HIGH"
    if score >= 60: return "MODERATE"
    if score >= 40: return "LOW"
    return "VERY LOW"


def run(gray_a, gray_b):
    gray_a = np.asarray(gray_a, dtype=np.float32)
    gray_b = np.asarray(gray_b, dtype=np.float32)
    quality_a = calculate_quality(gray_a)
    quality_b = calculate_quality(gray_b)
    features_a = build_descriptors(gray_a, detect_features(gray_a))
    features_b = build_descriptors(gray_b, detect_features(gray_b))
    distances = _distance_matrix(features_a, features_b)
    raw = match_features(features_a, features_b, distances)
    reciprocal = reciprocal_matches(raw, distances)
    geometry = verify_geometry(features_a, features_b, reciprocal)
    inlier_matches = [reciprocal[i] for i in geometry["inlier_indices"]]
    coverage = calculate_coverage(features_a, inlier_matches)
    average_quality = (quality_a["quality"] + quality_b["quality"]) / 2.0
    score = calculate_score(len(inlier_matches), len(reciprocal), coverage, geometry["consistency"], average_quality)
    confidence_value = max(0.0, min(100.0, score * 0.92 + geometry["consistency"] * 0.08))
    return {
        "features_a": features_a, "features_b": features_b,
        "raw_matches": raw, "reciprocal_matches": reciprocal,
        "geometry": geometry, "inlier_matches": inlier_matches,
        "coverage": coverage, "quality_a": quality_a, "quality_b": quality_b,
        "average_quality": average_quality, "score": score,
        "confidence_value": confidence_value, "confidence_label": confidence_label(confidence_value),
        "homography": None if geometry["model"] is None else np.asarray([[geometry["model"]["a"], geometry["model"]["b"], geometry["model"]["tx"]], [geometry["model"]["c"], geometry["model"]["d"], geometry["model"]["ty"]], [0.0, 0.0, 1.0]], dtype=np.float64),
    }


def custom_to_cv_keypoints(features):
    return [cv2.KeyPoint(float(f["x"]), float(f["y"]), 1.0) for f in features]


def custom_to_cv_matches(matches):
    return [cv2.DMatch(int(m["a"]), int(m["b"]), float(m["distance"])) for m in matches]


def draw_correspondence(gray_a, gray_b, features_a, features_b, matches, inlier_indices, out_path):
    h1, w1 = gray_a.shape; h2, w2 = gray_b.shape
    gap = 24; header_h = 62; max_width = 1600
    scale = min(1.0, (max_width - gap) / max(1, w1 + w2))
    wa, wb = max(1, round(w1 * scale)), max(1, round(w2 * scale))
    ha, hb = max(1, round(h1 * scale)), max(1, round(h2 * scale))
    height = header_h + max(ha, hb); width = wa + gap + wb
    canvas = np.full((height, width, 3), 9, dtype=np.uint8)
    canvas[header_h:header_h + ha, :wa] = cv2.cvtColor(cv2.resize(gray_a, (wa, ha), interpolation=cv2.INTER_AREA), cv2.COLOR_GRAY2BGR)
    canvas[header_h:header_h + hb, wa + gap:wa + gap + wb] = cv2.cvtColor(cv2.resize(gray_b, (wb, hb), interpolation=cv2.INTER_AREA), cv2.COLOR_GRAY2BGR)
    inlier_set = set(inlier_indices)
    for index, match in enumerate(matches):
        p = features_a[match["a"]]; q = features_b[match["b"]]
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
