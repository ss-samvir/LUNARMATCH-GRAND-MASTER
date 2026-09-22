from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .coordinates import coordinate_status, derive_analysis_grid, validate_geo_pair
from .image_validation import inspect_image
from .metadata import read_metadata
from .models import GeoReference, ProductIdentity, ValidationReport
from .pds4 import detect_mission_and_instrument, find_pds4_context
from .registry import validate_instrument


NON_IMAGE = {".xml", ".lbl", ".pds4", ".zip"}


def inspect_product(path: Path) -> Dict[str, Any]:
    context = find_pds4_context(path)

    if path.suffix.lower() not in NON_IMAGE:
        image = inspect_image(path)
    else:
        image = {
            "readable": True,
            "format": path.suffix.lower().lstrip(".").upper(),
            "width": None,
            "height": None,
            "channels": None,
            "dtype": None,
            "color_mode": None,
            "quality": None,
            "errors": [],
        }

    metadata = read_metadata(path, context)
    detection = detect_mission_and_instrument(path, metadata, context)
    instrument = validate_instrument(path, metadata, context)

    geo = GeoReference(
        latitude=metadata.get("latitude"),
        longitude=metadata.get("longitude"),
        altitude=metadata.get("altitude"),
        crs=metadata.get("crs"),
        projection=metadata.get("projection"),
        datum=metadata.get("datum"),
        source=metadata.get("coordinate_source"),
        coordinate_status=coordinate_status(metadata),
        analysis_grid=derive_analysis_grid(
            metadata.get("latitude"), metadata.get("longitude")
        ),
    )

    errors = list(image.get("errors") or [])
    errors.extend(context.get("label_errors") or [])
    errors.extend((context.get("archive") or {}).get("errors") or [])

    warnings = list(instrument.get("warnings") or [])

    product = ProductIdentity(
        product_class=context.get("source_type", "image"),
        mission=detection.get("mission"),
        instrument=instrument.get("instrument") or detection.get("instrument"),
        confidence=instrument.get("status", "NOT ESTABLISHED"),
        evidence=detection.get("evidence") or [],
    )

    checks = {
        "file_exists": path.exists(),
        "file_size_bytes": path.stat().st_size if path.exists() else None,
        "image_readable": image.get("readable"),
        "pds4_context_type": context.get("source_type"),
        "pds4_labels_detected": len(context.get("label_fields", {})),
        "archive_detected": bool(context.get("archive")),
        "instrument_validation": instrument,
        "geographic_coordinates": geo.as_dict(),
        "ground_truth_status": "NOT ESTABLISHED",
    }

    return ValidationReport(
        readable=not errors,
        product=product,
        image=image,
        metadata=metadata,
        georeference=geo,
        checks=checks,
        warnings=warnings,
        errors=errors,
    ).as_dict()


def validate_pair_geography(image_a: Dict[str, Any], image_b: Dict[str, Any]) -> Dict[str, Any]:
    return validate_geo_pair(image_a, image_b)
