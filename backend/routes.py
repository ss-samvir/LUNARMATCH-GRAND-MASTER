from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, request, send_from_directory

from .benchmark import run_benchmark
from .config import BENCHMARK_MAX_CASES, ROTATION_ROOT
from .coordinates import validate_geo_pair
from .product_validation import inspect_product
from .rotation import stream_reanalysis
from .utils import json_safe, save_uploaded_file

backend_api = Blueprint("backend_v2", __name__, url_prefix="/api/v2")


@backend_api.get("/health")
def health():
    return jsonify({
        "status": "online",
        "version": "research-backend-v2",
        "existing_engine_preserved": True,
        "features": [
            "generic image inspection",
            "PDS4/XML/archive context inspection",
            "OHRC validation",
            "TMC-2 product signature validation",
            "IIRS spectral/QUBE signature validation",
            "metadata and coordinate validation",
            "derived analysis grid",
            "live rotation/reanalysis stream",
            "manifest-driven benchmark up to 1000 cases",
        ],
        "scientific_boundary": (
            "Instrument identity and geographic ground truth are only reported "
            "when the required evidence is supplied."
        ),
    })


@backend_api.post("/inspect")
def inspect_endpoint():
    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify(error="Upload a file in multipart field 'file'."), 400

    directory = Path(current_app.root_path) / "backend_tmp" / "inspection"
    path = save_uploaded_file(uploaded, directory, "inspect")
    try:
        return jsonify(json_safe(inspect_product(path)))
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


@backend_api.post("/validate-geography")
def validate_geography_endpoint():
    data = request.get_json(silent=True) or {}
    return jsonify(json_safe(
        validate_geo_pair(data.get("image_a") or {}, data.get("image_b") or {})
    ))


@backend_api.post("/rotate-stream")
def rotate_stream_endpoint():
    image_a = request.files.get("image_a")
    image_b = request.files.get("image_b")
    if image_a is None or image_b is None:
        return jsonify(error="Upload image_a and image_b."), 400

    raw_angles = request.form.get("angles", "0")
    rotate_target = request.form.get("rotate_target", "b")

    try:
        parsed_angles = json.loads(raw_angles)
        if not isinstance(parsed_angles, list):
            parsed_angles = [parsed_angles]
    except Exception:
        parsed_angles = [value.strip() for value in raw_angles.split(",") if value.strip()]

    directory = Path(current_app.root_path) / "backend_tmp" / "rotation"
    image_a_path = save_uploaded_file(image_a, directory, "image_a")
    image_b_path = save_uploaded_file(image_b, directory, "image_b")

    def generate():
        try:
            for event in stream_reanalysis(
                image_a_path,
                image_b_path,
                parsed_angles,
                rotate_target,
            ):
                yield json.dumps(json_safe(event), allow_nan=False) + "\n"
        finally:
            for path in (image_a_path, image_b_path):
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass

    return Response(generate(), mimetype="application/x-ndjson")


@backend_api.get("/rotation-preview/<path:name>")
def rotation_preview(name):
    return send_from_directory(ROTATION_ROOT, name)


@backend_api.post("/benchmark/run")
def benchmark_run_endpoint():
    data = request.get_json(silent=True) or {}
    manifest = data.get("manifest_path")
    if not manifest:
        return jsonify(error="Provide manifest_path on the server."), 400

    manifest_path = Path(str(manifest)).resolve()
    if not manifest_path.exists():
        return jsonify(error="Benchmark manifest not found."), 404

    max_cases = int(data.get("max_cases", BENCHMARK_MAX_CASES))
    max_cases = max(1, min(BENCHMARK_MAX_CASES, max_cases))

    root = Path(str(data["root"])).resolve() if data.get("root") else manifest_path.parent

    return jsonify(json_safe(
        run_benchmark(manifest_path, root=root, max_cases=max_cases)
    ))
