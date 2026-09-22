from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2

from .config import BENCHMARK_MAX_CASES
from .models import BenchmarkCase, BenchmarkSummary


def load_cases(manifest_path: Path, root: Optional[Path] = None) -> List[BenchmarkCase]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_cases = data.get("cases") if isinstance(data, dict) else data
    if not isinstance(raw_cases, list):
        raise ValueError("Benchmark manifest must contain a 'cases' list.")

    base = root or manifest_path.parent
    cases = []

    for index, item in enumerate(raw_cases[:BENCHMARK_MAX_CASES], start=1):
        a = Path(str(item["image_a"]))
        b = Path(str(item["image_b"]))
        if not a.is_absolute():
            a = base / a
        if not b.is_absolute():
            b = base / b

        cases.append(BenchmarkCase(
            case_id=str(item.get("id", index)),
            image_a=str(a),
            image_b=str(b),
            expected_match=item.get("expected_match"),
            expected_latitude_a=item.get("expected_latitude_a"),
            expected_longitude_a=item.get("expected_longitude_a"),
            expected_latitude_b=item.get("expected_latitude_b"),
            expected_longitude_b=item.get("expected_longitude_b"),
        ))

    return cases


def run_pair_case(case: BenchmarkCase) -> Dict[str, Any]:
    from lunar_engine import run as run_lunarmatch_engine

    image_a = cv2.imread(case.image_a, cv2.IMREAD_GRAYSCALE)
    image_b = cv2.imread(case.image_b, cv2.IMREAD_GRAYSCALE)
    if image_a is None or image_b is None:
        raise ValueError("One or both benchmark images could not be decoded.")

    result = run_lunarmatch_engine(image_a, image_b)
    score = float(result.get("score", 0.0))

    return {
        "id": case.case_id,
        "image_a": case.image_a,
        "image_b": case.image_b,
        "score": round(score, 3),
        "confidence": result.get("confidence_label"),
        "confidence_value": round(float(result.get("confidence_value", 0.0)), 3),
        "verified_matches": len(result.get("inlier_matches", [])),
        "candidate_matches": len(result.get("reciprocal_matches", [])),
        "coverage_percent": round(float(result.get("coverage", 0.0)), 3),
        "geometry_consistency": round(float(result.get("geometry", {}).get("consistency", 0.0)), 3),
        "observed_match": score >= 40.0,
        "expected_match": case.expected_match,
        "error": None,
    }


def run_benchmark(
    manifest_path: Path,
    root: Optional[Path] = None,
    max_cases: int = BENCHMARK_MAX_CASES,
) -> Dict[str, Any]:
    cases = load_cases(manifest_path, root=root)[:max_cases]
    results = []
    failed = 0

    for case in cases:
        try:
            results.append(run_pair_case(case))
        except Exception as exc:
            failed += 1
            results.append({
                "id": case.case_id,
                "image_a": case.image_a,
                "image_b": case.image_b,
                "error": str(exc),
            })

    valid = [r for r in results if "score" in r]
    labelled = [
        r for r in valid
        if r.get("expected_match") is not None
    ]

    confusion = {
        "true_positive": None,
        "true_negative": None,
        "false_positive": None,
        "false_negative": None,
    }
    if labelled:
        confusion = {key: 0 for key in confusion}
        for row in labelled:
            expected = bool(row["expected_match"])
            observed = bool(row["observed_match"])
            if expected and observed:
                confusion["true_positive"] += 1
            elif not expected and not observed:
                confusion["true_negative"] += 1
            elif not expected and observed:
                confusion["false_positive"] += 1
            else:
                confusion["false_negative"] += 1

    scores = [r["score"] for r in valid]
    verified = [r["verified_matches"] for r in valid]

    summary = BenchmarkSummary(
        requested=len(cases),
        processed=len(valid),
        failed=failed,
        match_labelled_cases=len(labelled),
        confusion=confusion,
        mean_score=statistics.fmean(scores) if scores else None,
        median_score=statistics.median(scores) if scores else None,
        mean_verified=statistics.fmean(verified) if verified else None,
        notes=[
            "Results describe only the supplied empirical benchmark cases.",
            "No 500–1000 case performance claim is valid until a real labelled dataset is processed.",
            "The 40-point observed_match split is an operational benchmark rule, not geographic ground truth.",
        ],
    )

    return {
        "summary": summary.as_dict(),
        "cases": results,
    }
