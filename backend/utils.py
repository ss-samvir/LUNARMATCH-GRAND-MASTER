import math
import re
import uuid
from pathlib import Path
from typing import Any, Dict

from werkzeug.utils import secure_filename


def json_safe(value: Any) -> Any:
    import numbers
    import numpy as np

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        v = float(value)
        return v if math.isfinite(v) else None
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, Path):
        return str(value)
    try:
        return json_safe(value.item())
    except Exception:
        return str(value)


def save_uploaded_file(uploaded, directory: Path, prefix: str = "upload") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    original = secure_filename(uploaded.filename or "")
    if not original:
        raise ValueError("Uploaded file must have a filename.")
    suffix = Path(original).suffix.lower()
    target = directory / f"{prefix}_{uuid.uuid4().hex}{suffix}"
    uploaded.save(target)
    return target


def bounded_float(value):
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except Exception:
        return None
