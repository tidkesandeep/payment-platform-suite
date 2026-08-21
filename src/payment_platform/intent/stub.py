"""Intent verification stub. Fails closed for agent paths. No homemade crypto."""

from __future__ import annotations

from typing import Protocol

from payment_platform.contracts import AuthStatus, IntentResult, PaymentAttempt


class IntentVerifier(Protocol):
    def verify(self, request: PaymentAttempt) -> IntentResult: ...


class StubIntentVerifier:
    """Phase 1 stub. Agent payments are INVALID unless a test injects VALID."""

    def __init__(self, *, fail_closed: bool = True, injected: IntentResult | None = None):
        self.fail_closed = fail_closed
        self.injected = injected

    def verify(self, request: PaymentAttempt) -> IntentResult:
        if request.channel == "human":
            return IntentResult(
                status=AuthStatus.HUMAN.value,
                reason="human_path",
                claims={},
            )
        if self.injected is not None:
            return self.injected
        if not self.fail_closed:
            return IntentResult(
                status=AuthStatus.VALID.value,
                reason="stub_open_local_only",
                claims={"agent_id": request.agent_id},
            )
        return IntentResult(
            status=AuthStatus.INVALID.value,
            reason="stub_fail_closed",
            claims={},
        )
