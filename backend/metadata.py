from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import ExifTags, Image

from .pds4 import infer_text_value
from .utils import bounded_float


def gps_decimal(value):
    try:
        if hasattr(value, "numerator") and hasattr(value, "denominator"):
            denominator = float(value.denominator)
            return float(value.numerator) / denominator if denominator else None
        if isinstance(value, (tuple, list)):
            total = 0.0
            for i, item in enumerate(value):
                if hasattr(item, "numerator") and hasattr(item, "denominator"):
                    denominator = float(item.denominator)
                    part = float(item.numerator) / denominator if denominator else 0.0
                else:
                    part = float(item)
                total += part / (60 ** i)
            return total
        return float(value)
    except Exception:
        return None


def _first(data: dict, *keys):
    for key in keys:
        if data.get(key) not in (None, ""):
            return data[key]
    return None


def read_metadata(path: Path, pds4_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
        "coordinate_source": None,
        "footprint": None,
        "source": "Embedded image metadata",
    }

    try:
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}:
            im = Image.open(path)
            exif = im.getexif()
            tags = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}

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
                        out["latitude"] = -lat_v if str(gps2.get("GPSLatitudeRef", "")).upper() == "S" else lat_v
                    if lon_v is not None:
                        out["longitude"] = -lon_v if str(gps2.get("GPSLongitudeRef", "")).upper() == "W" else lon_v
                    if out["latitude"] is not None and out["longitude"] is not None:
                        out["coordinate_source"] = "EXIF GPS"

                if gps2.get("GPSAltitude") is not None:
                    out["altitude"] = gps_decimal(gps2["GPSAltitude"])

        sidecar = path.with_suffix(".json")
        if sidecar.exists():
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            aliases = {
                "instrument": ("instrument", "payload"),
                "mission": ("mission",),
                "image_id": ("image_id", "imageId"),
                "product_id": ("product_id", "productId"),
                "provenance": ("provenance", "source"),
                "crs": ("crs",),
                "projection": ("projection",),
                "datum": ("datum",),
                "latitude": ("latitude", "lat"),
                "longitude": ("longitude", "lon"),
                "altitude": ("altitude",),
                "acquisition_time": ("acquisition_time", "acquisitionTime", "date_time"),
                "coordinate_source": ("coordinate_source", "coordinateSource"),
                "footprint": ("footprint", "bounds", "bbox"),
            }
            for target, keys in aliases.items():
                value = _first(data, *keys)
                if value is not None:
                    out[target] = value
            out["source"] = "Embedded metadata + supplied reference metadata"

        ctx = pds4_context or {}
        fields = ctx.get("label_fields", {})
        label_text = ctx.get("label_text", "")
        if fields or label_text:
            out["mission"] = out["mission"] or infer_text_value(fields, label_text, ("mission_name", "mission"))
            out["instrument"] = out["instrument"] or infer_text_value(
                fields, label_text, ("instrument_name", "instrument_id", "instrument")
            )
            out["image_id"] = out["image_id"] or infer_text_value(fields, label_text, ("image_id",))
            out["product_id"] = out["product_id"] or infer_text_value(fields, label_text, ("product_id",))
            out["crs"] = out["crs"] or infer_text_value(fields, label_text, ("crs", "coordinate_reference_system"))
            out["projection"] = out["projection"] or infer_text_value(fields, label_text, ("projection", "map_projection"))
            out["datum"] = out["datum"] or infer_text_value(fields, label_text, ("datum", "reference_surface"))
            out["acquisition_time"] = out["acquisition_time"] or infer_text_value(
                fields, label_text, ("start_date_time", "acquisition_time", "date_time")
            )

            lat_text = infer_text_value(
                fields, label_text, ("latitude", "center_latitude", "sub_spacecraft_latitude")
            )
            lon_text = infer_text_value(
                fields, label_text, ("longitude", "center_longitude", "sub_spacecraft_longitude")
            )
            if out["latitude"] is None:
                out["latitude"] = bounded_float(lat_text)
            if out["longitude"] is None:
                out["longitude"] = bounded_float(lon_text)
            if out["latitude"] is not None or out["longitude"] is not None:
                out["coordinate_source"] = out["coordinate_source"] or "PDS4 label"
            out["source"] = "PDS4/product metadata"

        out["available"] = any(
            value not in (None, "", [], {})
            for key, value in out.items()
            if key not in {"available", "source"}
        )
    except Exception as exc:
        out["metadata_error"] = str(exc)

    return out
