from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_fingerprint(body: dict[str, Any]) -> str:
    """SHA-256 of the request body excluding the idempotency key."""
    payload = {k: v for k, v in body.items() if k != "idempotency_key"}
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
