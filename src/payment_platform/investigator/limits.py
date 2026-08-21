"""Per-agent, per-tool rate limits for the investigator."""

from __future__ import annotations

import time
from collections import deque


class ToolRateLimiter:
    def __init__(self, max_per_minute: int = 60):
        self.max_per_minute = max(1, int(max_per_minute))
        self._hits: dict[tuple[str, str], deque[float]] = {}

    def allow(self, agent_id: str, tool: str) -> bool:
        now = time.monotonic()
        key = (agent_id, tool)
        window = self._hits.setdefault(key, deque())
        cutoff = now - 60.0
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= self.max_per_minute:
            return False
        window.append(now)
        return True
