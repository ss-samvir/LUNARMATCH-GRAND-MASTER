from __future__ import annotations

from typing import Any, Dict, Optional


def normalize_longitude(longitude: float) -> float:
    value = float(longitude)
    while value < -180.0:
        value += 360.0
    while value > 180.0:
        value -= 360.0
    return value


def coordinate_status(metadata: Dict[str, Any]) -> str:
    lat = metadata.get("latitude")
    lon = metadata.get("longitude")
    if lat is None and lon is None:
        return "NOT AVAILABLE"
    if lat is None or lon is None:
        return "INCOMPLETE"
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return "INVALID"
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return "INVALID RANGE"
    return "AVAILABLE"


def derive_analysis_grid(
    latitude: Optional[float],
    longitude: Optional[float],
    rows: int = 18,
    columns: int = 36,
) -> Optional[Dict[str, Any]]:
    if latitude is None or longitude is None:
        return None
    lat = float(latitude)
    lon = normalize_longitude(float(longitude))
    if not (-90.0 <= lat <= 90.0):
        return None

    row = min(rows - 1, max(0, int((90.0 - lat) / 180.0 * rows)))
    col = min(columns - 1, max(0, int((lon + 180.0) / 360.0 * columns)))

    return {
        "type": "analysis-grid",
        "rows": rows,
        "columns": columns,
        "row": row,
        "column": col,
        "cell": f"{row:02d}:{col:02d}",
        "coordinate_basis": "center latitude/longitude",
        "note": "Derived indexing grid; not an official lunar reference grid.",
    }


def validate_geo_pair(image_a: Dict[str, Any], image_b: Dict[str, Any]) -> Dict[str, Any]:
    status_a = coordinate_status(image_a)
    status_b = coordinate_status(image_b)

    result = {
        "status": "NOT ESTABLISHED",
        "image_a": {
            "status": status_a,
            "latitude": image_a.get("latitude"),
            "longitude": image_a.get("longitude"),
            "grid": derive_analysis_grid(image_a.get("latitude"), image_a.get("longitude")),
        },
        "image_b": {
            "status": status_b,
            "latitude": image_b.get("latitude"),
            "longitude": image_b.get("longitude"),
            "grid": derive_analysis_grid(image_b.get("latitude"), image_b.get("longitude")),
        },
        "coordinate_source": {
            "image_a": image_a.get("coordinate_source"),
            "image_b": image_b.get("coordinate_source"),
        },
        "ground_truth": False,
        "notes": [],
    }

    if status_a == "AVAILABLE" and status_b == "AVAILABLE":
        result["status"] = "COORDINATES AVAILABLE"
        result["notes"].append(
            "Both centers have usable coordinates, but coordinate availability is not independent ground-truth validation."
        )
    else:
        result["notes"].append(
            "A geographic validation result cannot be established from incomplete or missing coordinates."
        )

    return result
