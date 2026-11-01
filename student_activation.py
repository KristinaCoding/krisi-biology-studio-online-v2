"""Temporary student invitation activation storage.

Activation records are stored server-side, never in browser cookies.
"""

import secrets
import time
from threading import Lock

ACTIVATION_LIFETIME_SECONDS = 600

_records = {}
_lock = Lock()


def create_activation_record(user_id, access_token, refresh_token):
    """Create a short-lived, single-use activation record."""
    activation_id = secrets.token_urlsafe(32)

    with _lock:
        now = time.time()

        expired = [
            key for key, record in _records.items()
            if record["expires_at"] <= now
        ]

        for key in expired:
            del _records[key]

        _records[activation_id] = {
            "user_id": str(user_id),
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": now + ACTIVATION_LIFETIME_SECONDS,
        }

    return activation_id


def consume_activation_record(activation_id):
    """Retrieve and remove an activation record exactly once."""
    with _lock:
        record = _records.pop(activation_id, None)

    if record is None:
        return None

    if record["expires_at"] <= time.time():
        return None

    return record
