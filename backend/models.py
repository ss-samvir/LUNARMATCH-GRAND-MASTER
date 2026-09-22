from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Evidence:
    source: str
    field: str
    value: Any
    strength: str = "informational"
    note: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "field": self.field,
            "value": self.value,
            "strength": self.strength,
            "note": self.note,
        }


@dataclass
class GeoReference:
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    crs: Optional[str] = None
    projection: Optional[str] = None
    datum: Optional[str] = None
    source: Optional[str] = None
    coordinate_status: str = "NOT AVAILABLE"
    analysis_grid: Optional[Dict[str, Any]] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
            "crs": self.crs,
            "projection": self.projection,
            "datum": self.datum,
            "source": self.source,
            "coordinate_status": self.coordinate_status,
            "analysis_grid": self.analysis_grid,
        }


@dataclass
class ProductIdentity:
    product_class: str
    mission: Optional[str]
    instrument: Optional[str]
    confidence: str
    evidence: List[Evidence] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "product_class": self.product_class,
            "mission": self.mission,
            "instrument": self.instrument,
            "confidence": self.confidence,
            "evidence": [e.as_dict() for e in self.evidence],
        }


@dataclass
class ValidationReport:
    readable: bool
    product: ProductIdentity
    image: Dict[str, Any]
    metadata: Dict[str, Any]
    georeference: GeoReference
    checks: Dict[str, Any]
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "readable": self.readable,
            "product": self.product.as_dict(),
            "image": self.image,
            "metadata": self.metadata,
            "georeference": self.georeference.as_dict(),
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
        }


@dataclass
class BenchmarkCase:
    case_id: str
    image_a: str
    image_b: str
    expected_match: Optional[bool] = None
    expected_latitude_a: Optional[float] = None
    expected_longitude_a: Optional[float] = None
    expected_latitude_b: Optional[float] = None
    expected_longitude_b: Optional[float] = None


@dataclass
class BenchmarkSummary:
    requested: int
    processed: int
    failed: int
    match_labelled_cases: int
    confusion: Dict[str, Optional[int]]
    mean_score: Optional[float]
    median_score: Optional[float]
    mean_verified: Optional[float]
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "requested": self.requested,
            "processed": self.processed,
            "failed": self.failed,
            "match_labelled_cases": self.match_labelled_cases,
            "confusion": self.confusion,
            "mean_score": self.mean_score,
            "median_score": self.median_score,
            "mean_verified": self.mean_verified,
            "notes": self.notes,
        }
