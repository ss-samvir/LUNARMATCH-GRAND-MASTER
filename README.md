# LUNARMATCH V2 — Grand Master Build 01

This is a separate continuation of the original LUNARMATCH prototype. The original source is preserved under `legacy_v1/` and is not used as the active V2 UI.

## Run

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5000`.

## Current V2 engine

SIFT + BFMatcher + Lowe ratio test + reciprocal matching + RANSAC homography verification. Scores are correspondence/reliability indicators, **not ground-truth accuracy**.

## Metadata policy

V2 reads embedded EXIF GPS/time/camera metadata when available. It also supports an explicit same-basename `.json` sidecar for reference metadata. Coordinates are never inferred or fabricated. For lunar/planetary products, future adapters can preserve mission-specific coordinate reference systems, projections, datums and product identifiers.

## Next build layers

- ground-truth dataset import and benchmark runner
- repeatable stress-test execution and charts
- richer planetary localization and CRS handling
- standards documentation / OGC-relevant interoperability
- report generation
- result history dashboard
- production authentication/session hardening
- polished 3D visualization and correspondence explorer
