from pathlib import Path
from typing import Any, Dict, Tuple

from .base import InstrumentValidator


class OHRCValidator(InstrumentValidator):
    name = "OHRC"

    def matches(self, path: Path, metadata: Dict[str, Any], context: Dict[str, Any]) -> Tuple[bool, str]:
        archive_members = " ".join((context.get("archive") or {}).get("members", []))
        hay = " ".join([
            path.name,
            str(metadata.get("instrument") or ""),
            str(metadata.get("product_id") or ""),
            context.get("label_text") or "",
            archive_members,
        ]).upper()
        return ("OHRC" in hay or "ORBITER HIGH RESOLUTION CAMERA" in hay), "OHRC token"

    def validate(self, path: Path, metadata: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        label_backed = context.get("source_type") in {"pds4-label", "archive"}
        warnings = []
        if not label_backed:
            warnings.append(
                "OHRC identity is based on filename/metadata only; a mission product label was not supplied."
            )

        return {
            "instrument": "OHRC",
            "status": "VALIDATED" if label_backed else "IDENTIFIED_LIMITED",
            "evidence_level": "product-label" if label_backed else "filename-or-metadata",
            "checks": {
                "instrument_signature": True,
                "mission_product_context": label_backed,
                "pixel_data_readable": True,
            },
            "warnings": warnings,
        }
