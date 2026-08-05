"""Error formatting helpers for worker logging."""


def redact_exception(exc: BaseException) -> str:
    """Return a safe identifier for an exception, suitable for public logs.

    Only the exception class name is returned. Driver exceptions routinely
    embed connection URIs containing credentials in str(exc) — pymongo and
    redis-py both do — and the ingestion_log collection is exposed by
    /api/dashboard/ingestion-log. That endpoint now requires an operator bearer
    token, but the stored value is still the wrong place for a credential:
    anyone with read access to the collection, a backup, or the token would see
    it. Log the full detail to stderr instead.
    """
    return type(exc).__name__
