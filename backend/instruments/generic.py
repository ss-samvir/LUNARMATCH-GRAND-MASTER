from pathlib import Path
from typing import Any, Dict, Tuple

from .base import InstrumentValidator


class GenericValidator(InstrumentValidator):
    name = "GENERIC"

    def matches(self, path: Path, metadata: Dict[str, Any], context: Dict[str, Any]) -> Tuple[bool, str]:
        return True, "fallback"

    def validate(self, path: Path, metadata: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "instrument": None,
            "status": "NOT ESTABLISHED",
            "evidence_level": "generic",
            "checks": {},
            "warnings": [],
        }
