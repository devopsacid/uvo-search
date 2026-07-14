"""Shared helpers for the public /v1 API: cursor pagination + envelope."""

import base64
import binascii

from uvo_api.routers.v1.models import Pagination
from uvo_api.v1_errors import ApiV1Error


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def decode_cursor(cursor: str | None) -> int:
    """Decode an offset cursor; None/empty means start. Invalid cursors 400."""
    if not cursor:
        return 0
    try:
        offset = int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, TypeError, binascii.Error) as exc:
        raise ApiV1Error(400, "invalid_cursor", "The cursor parameter is malformed.") from exc
    if offset < 0:
        raise ApiV1Error(400, "invalid_cursor", "The cursor parameter is malformed.")
    return offset


def next_pagination(offset: int, limit: int, returned: int, total: int | None) -> Pagination:
    """Return a Pagination with a next_cursor when more rows likely remain."""
    next_offset = offset + limit
    if returned < limit:
        return Pagination(next_cursor=None)
    if total is not None and next_offset >= total:
        return Pagination(next_cursor=None)
    return Pagination(next_cursor=encode_cursor(next_offset))
