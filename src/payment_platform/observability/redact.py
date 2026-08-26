"""Strip secrets from log text. Demo keys and DSNs must not hit stdout."""

from __future__ import annotations

import re

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk_(?:live|test)_[A-Za-z0-9]+"), "sk_***"),
    (re.compile(r"(?i)(postgresql://[^:/?\s]+:)([^@/\s]+)"), r"\1***"),
    (re.compile(r"(?i)(password=)[^&\s]+"), r"\1***"),
    (re.compile(r'"d"\s*:\s*"[^"]+"'), '"d":"***"'),
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "[REDACTED PRIVATE KEY]",
    ),
)


def redact_text(value: str) -> str:
    redacted = value
    for pattern, replacement in _PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
