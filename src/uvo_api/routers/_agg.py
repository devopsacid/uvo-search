"""Deprecated shim — the firma aggregation helpers moved to
``uvo_core.adapters.mongo.analytics`` in Phase 3. Re-exported for one release.
"""

from uvo_core.adapters.mongo.analytics import (
    _firma_core_agg,
    _firma_partners_agg,
    _market_cpv_agg,
)

__all__ = ["_firma_core_agg", "_firma_partners_agg", "_market_cpv_agg"]
