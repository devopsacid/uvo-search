"""Exception detail must never reach the publicly-served ingestion_log.

/api/dashboard/ingestion-log is anonymous. pymongo and redis-py embed the
full connection URI — including credentials — in their exception messages,
so only the exception type may be persisted.
"""

from uvo_workers.errors import redact_exception


def test_redacts_message_keeps_type():
    exc = ConnectionError("connection to mongodb://uvo:s3cret@mongo:27017 refused")
    assert redact_exception(exc) == "ConnectionError"


def test_does_not_leak_credentials():
    exc = RuntimeError("auth failed for redis://:hunter2@redis:6379")
    result = redact_exception(exc)
    assert "hunter2" not in result
    assert "redis://" not in result


def test_handles_exception_with_empty_message():
    assert redact_exception(ValueError()) == "ValueError"
