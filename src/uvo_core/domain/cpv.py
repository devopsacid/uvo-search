"""CPV (Common Procurement Vocabulary) helpers shared by every delivery layer."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_LABELS_PATH = Path(__file__).parent / "data" / "cpv_labels.json"
_DEFAULT_CODE = "00000000"


def cpv_prefix(code: str | None) -> str:
    """Normalise a CPV code to its 8 digit form (check digit and separators dropped)."""
    if not code:
        return _DEFAULT_CODE
    digits = code.replace("-", "").replace(" ", "")[:8]
    return digits.ljust(8, "0")


@lru_cache(maxsize=1)
def load_cpv_labels() -> dict[str, dict[str, str]]:
    """Return ``{code: {"sk": ..., "en": ...}}`` (loaded once per process)."""
    return json.loads(_LABELS_PATH.read_text(encoding="utf-8"))


def cpv_label_sk(code: str) -> str:
    """Slovak label for an 8 digit CPV code, falling back to the code itself."""
    return load_cpv_labels().get(code, {}).get("sk") or code
