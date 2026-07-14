"""Issue or revoke API keys for the public /v1 API.

Keys are stored in the Mongo ``api_keys`` collection as the sha256 hex digest of
the raw key. The raw key is shown exactly once, at issue time.

Usage:
  python -m scripts.issue_api_key --email a@b.sk --plan pro
  python -m scripts.issue_api_key --revoke uvo_a1b2c3d4
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorClient

from uvo_api.auth import hash_key
from uvo_api.config import ApiSettings

_PLANS = ("free", "pro", "business")
_PREFIX_LEN = 12  # chars of the raw key stored for revocation lookup


def _generate_key() -> str:
    return f"uvo_{secrets.token_urlsafe(32)}"


async def _issue(email: str, plan: str) -> None:
    raw_key = _generate_key()
    settings = ApiSettings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    try:
        db = client[settings.mongodb_database]
        await db["api_keys"].insert_one(
            {
                "key_hash": hash_key(raw_key),
                "key_prefix": raw_key[:_PREFIX_LEN],
                "plan": plan,
                "owner_email": email,
                "active": True,
                "created_at": datetime.now(UTC),
            }
        )
    finally:
        client.close()

    print(f"API key issued for {email} (plan: {plan})")
    print(f"  prefix (for revocation): {raw_key[:_PREFIX_LEN]}")
    print("  raw key (shown once, store it now):")
    print(f"  {raw_key}")


async def _revoke(prefix: str) -> None:
    settings = ApiSettings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    try:
        db = client[settings.mongodb_database]
        result = await db["api_keys"].update_many(
            {"key_prefix": prefix}, {"$set": {"active": False}}
        )
    finally:
        client.close()
    print(f"Revoked {result.modified_count} key(s) matching prefix {prefix}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Issue or revoke public /v1 API keys.")
    parser.add_argument("--email", help="Owner email for a new key.")
    parser.add_argument("--plan", choices=_PLANS, default="free", help="Plan for a new key.")
    parser.add_argument("--revoke", metavar="KEY_PREFIX", help="Revoke keys by prefix.")
    args = parser.parse_args()

    if args.revoke:
        asyncio.run(_revoke(args.revoke))
        return
    if not args.email:
        parser.error("--email is required to issue a key (or use --revoke KEY_PREFIX)")
    asyncio.run(_issue(args.email, args.plan))


if __name__ == "__main__":
    sys.exit(main())
