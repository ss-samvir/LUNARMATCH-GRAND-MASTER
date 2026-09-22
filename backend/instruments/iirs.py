from pathlib import Path
from typing import Any, Dict, Tuple

from .base import InstrumentValidator


class IIRSValidator(InstrumentValidator):
    name = "IIRS"

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
            "IIRS" in hay or "IMAGING INFRARED SPECTROMETER" in hay
        ), "IIRS token"

    def validate(self, path: Path, metadata: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        members = (context.get("archive") or {}).get("members", [])
        all_names = " ".join(members).upper()
        label = (context.get("label_text") or "").upper()

        qube_signature = (
            "QUBE" in all_names
            or "QUBE" in label
            or ".QUB" in all_names
        )
        spectral_signature = any(
            token in label
            for token in ("SPECTRAL", "WAVELENGTH", "BAND", "BANDS")
        )

        warnings = []
        if not qube_signature:
            warnings.append(
                "No QUBE-like spectral-product signature was found in the supplied archive/label."
            )
        if not spectral_signature:
            warnings.append(
                "No explicit spectral-band/wavelength signature was found in the supplied label."
            )

        return {
            "instrument": "IIRS",
            "status": "VALIDATED" if qube_signature and spectral_signature else "IDENTIFIED_LIMITED",
            "evidence_level": (
                "product-label"
                if context.get("source_type") in {"pds4-label", "archive"}
                else "filename-or-metadata"
            ),
            "checks": {
                "instrument_signature": True,
                "qube_like_signature": qube_signature,
                "spectral_metadata_signature": spectral_signature,
            },
            "warnings": warnings,
        }
