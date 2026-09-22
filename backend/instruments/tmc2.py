from pathlib import Path
from typing import Any, Dict, Tuple

from .base import InstrumentValidator


VIEW_TOKENS = {
    "fore": ("FORE", "FWD", "FORWARD"),
    "nadir": ("NADIR",),
    "aft": ("AFT", "REAR"),
}


class TMC2Validator(InstrumentValidator):
    name = "TMC-2"

    def matches(self, path: Path, metadata: Dict[str, Any], context: Dict[str, Any]) -> Tuple[bool, str]:
        archive_members = " ".join((context.get("archive") or {}).get("members", []))
        hay = " ".join([
            path.name,
            str(metadata.get("instrument") or ""),
            str(metadata.get("product_id") or ""),
            context.get("label_text") or "",
            archive_members,
        ]).upper()
        return (
            any(token in hay for token in ("TMC-2", "TMC2", "TMC_2", "TERRAIN MAPPING CAMERA"))
        ), "TMC-2 token"

    def validate(self, path: Path, metadata: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        names = " ".join((context.get("archive") or {}).get("members", [])).upper()
        label = (context.get("label_text") or "").upper()
        hay = f"{path.name.upper()} {label} {names}"
        views = [
            view for view, tokens in VIEW_TOKENS.items()
            if any(token in hay for token in tokens)
        ]

        warnings = []
        if len(views) < 2:
            warnings.append(
                "The supplied product does not establish a multi-view stereo set from its available signatures."
            )

        return {
            "instrument": "TMC-2",
            "status": "VALIDATED" if len(views) >= 2 else "IDENTIFIED_LIMITED",
            "evidence_level": (
                "product-label"
                if context.get("source_type") in {"pds4-label", "archive"}
                else "filename-or-metadata"
            ),
            "checks": {
                "instrument_signature": True,
                "view_signatures_found": views,
                "stereo_set_signature": len(views) >= 2,
            },
            "warnings": warnings,
        }
