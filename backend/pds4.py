from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import xml.etree.ElementTree as ET

from .models import Evidence

MISSION_TOKENS = ("CHANDRAYAAN-2", "CHANDRAYAAN2", "CHANDRAYAAN 2")
INSTRUMENT_TOKENS = {
    "OHRC": ("OHRC", "ORBITER HIGH RESOLUTION CAMERA"),
    "TMC-2": ("TMC-2", "TMC2", "TMC_2", "TERRAIN MAPPING CAMERA", "TERRAIN MAPPING CAMERA-2"),
    "IIRS": ("IIRS", "IMAGING INFRARED SPECTROMETER"),
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_xml_label(path: Path) -> Dict[str, Any]:
    result = {
        "valid_xml": False,
        "root": None,
        "fields": {},
        "text": "",
        "errors": [],
    }
    try:
        root = ET.parse(path).getroot()
        fields: Dict[str, Any] = {}
        texts: List[str] = []
        for elem in root.iter():
            key = _local(elem.tag)
            value = (elem.text or "").strip()
            if not value:
                continue
            texts.append(value)
            if key not in fields:
                fields[key] = value
            elif isinstance(fields[key], list):
                fields[key].append(value)
            else:
                fields[key] = [fields[key], value]
        result.update({
            "valid_xml": True,
            "root": _local(root.tag),
            "fields": fields,
            "text": " ".join(texts)[:2_000_000],
        })
    except Exception as exc:
        result["errors"].append(str(exc))
    return result


def inspect_archive(path: Path) -> Dict[str, Any]:
    result = {
        "is_archive": zipfile.is_zipfile(path),
        "members": [],
        "labels": [],
        "product_files": [],
        "text": "",
        "errors": [],
    }
    if not result["is_archive"]:
        return result
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            result["members"] = names[:5000]
            result["labels"] = [
                n for n in names
                if Path(n).suffix.lower() in {".xml", ".lbl", ".pds4"}
            ][:200]
            result["product_files"] = [
                n for n in names
                if Path(n).suffix.lower() in {
                    ".img", ".imq", ".qub", ".qmap", ".jp2",
                    ".png", ".jpg", ".tif", ".tiff", ".dat", ".bin"
                }
            ][:500]
            snippets = []
            for name in result["labels"][:50]:
                snippets.append(zf.read(name).decode("utf-8", errors="ignore")[:1_000_000])
            result["text"] = " ".join(snippets)[:2_000_000]
    except Exception as exc:
        result["errors"].append(str(exc))
    return result


def find_pds4_context(path: Path) -> Dict[str, Any]:
    suffix = path.suffix.lower()
    context = {
        "source_type": "image",
        "label_fields": {},
        "label_text": "",
        "archive": None,
    }
    if suffix in {".xml", ".lbl", ".pds4"}:
        parsed = parse_xml_label(path)
        context["source_type"] = "pds4-label"
        context["label_fields"] = parsed["fields"]
        context["label_text"] = parsed["text"]
        context["label_errors"] = parsed["errors"]
    elif zipfile.is_zipfile(path):
        context["source_type"] = "archive"
        context["archive"] = inspect_archive(path)
        context["label_text"] = context["archive"]["text"]
    return context


def infer_text_value(fields: Dict[str, Any], text: str, names: Iterable[str]) -> Optional[str]:
    wanted = {n.lower() for n in names}
    for key, value in fields.items():
        if key.lower() in wanted:
            if isinstance(value, list):
                return str(value[0]) if value else None
            return str(value)

    upper = text.upper()
    for token in names:
        pattern = rf"{re.escape(token.upper())}\\s*[:=]\\s*[\'\"]?([^<>\\r\\n\'\"]+)"
        match = re.search(pattern, upper)
        if match:
            return match.group(1).strip()
    return None


def detect_mission_and_instrument(
    path: Path,
    metadata: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    archive_members = " ".join((context.get("archive") or {}).get("members", []))
    haystack = " ".join([
        path.name,
        str(metadata.get("mission") or ""),
        str(metadata.get("instrument") or ""),
        str(metadata.get("image_id") or ""),
        str(metadata.get("product_id") or ""),
        context.get("label_text") or "",
        archive_members,
    ]).upper()

    mission = metadata.get("mission")
    if not mission and any(token in haystack for token in MISSION_TOKENS):
        mission = "Chandrayaan-2"

    instrument = metadata.get("instrument")
    evidence: List[Evidence] = []

    if context.get("source_type") in {"pds4-label", "archive"}:
        for name, tokens in INSTRUMENT_TOKENS.items():
            if any(token in haystack for token in tokens):
                instrument = instrument or name
                evidence.append(Evidence(
                    source=context["source_type"],
                    field="instrument",
                    value=name,
                    strength="strong",
                    note="Instrument identifier found in supplied product/label content.",
                ))
                break

    if not instrument:
        for name, tokens in INSTRUMENT_TOKENS.items():
            if any(token in haystack for token in tokens):
                instrument = name
                evidence.append(Evidence(
                    source="filename-or-metadata",
                    field="instrument",
                    value=name,
                    strength="limited",
                    note="Instrument identifier found outside a mission product label.",
                ))
                break

    if mission:
        evidence.append(Evidence(
            source="product-or-metadata",
            field="mission",
            value=mission,
            strength="strong" if context.get("source_type") != "image" else "limited",
        ))

    return {
        "mission": mission,
        "instrument": instrument,
        "evidence": evidence,
    }
