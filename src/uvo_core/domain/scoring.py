"""Pure risk-scoring primitives over domain inputs.

First tenant is CPV-spend concentration (HHI); the Phase-4 red-flag engine
builds on this. No infrastructure dependencies — plain numbers in, numbers out —
so it is fully testable against the in-memory fakes with zero containers.
"""

from __future__ import annotations

from collections.abc import Sequence


def cpv_concentration(values: Sequence[float]) -> tuple[list[float], float]:
    """Herfindahl-Hirschman concentration over CPV spend values.

    Returns ``(shares, hhi)`` where ``shares`` are each value's fraction of the
    positive total (0..1, aligned with the input order) and ``hhi`` is the sum of
    squared shares (0..1, rounded to 4 dp). An empty or all-non-positive input
    yields zeroed shares and an HHI of 0.
    """
    total = sum(v for v in values if v > 0)
    if total <= 0:
        return [0.0 for _ in values], 0.0
    shares = [(v / total if v > 0 else 0.0) for v in values]
    hhi = round(sum(s * s for s in shares), 4)
    return shares, hhi
