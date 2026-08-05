"""Error formatting helpers for worker logging."""


def redact_exception(exc: BaseException) -> str:
    """Return a safe identifier for an exception, suitable for public logs.

    Only the exception class name is returned. Driver exceptions routinely
    embed connection URIs containing credentials in str(exc), and the
    ingestion_log collection is served by an unauthenticated endpoint.
    Log the full detail to stderr instead.
    """
    return type(exc).__name__
