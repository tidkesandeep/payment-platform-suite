"""Test helpers around demo.mint. Memory nonce store stays test-only."""

from __future__ import annotations

from demo.mint import MintedChain, mint_chain
from payment_platform.contracts import PaymentAttempt

__all__ = ["MintedChain", "MemoryNonceStore", "agent_attempt", "mint_chain"]


class MemoryNonceStore:
    def __init__(self) -> None:
        self._seen: set[str] = set()

    def claim_intent_nonce(self, nonce: str) -> bool:
        if not nonce or nonce in self._seen:
            return False
        self._seen.add(nonce)
        return True


def agent_attempt(minted: MintedChain, **overrides) -> PaymentAttempt:
    payload = dict(
        idempotency_key="k",
        customer_id="cust_001",
        merchant_id=minted.merchant_id,
        amount_minor=minted.amount_minor,
        currency=minted.currency,
        merchant_category="5411",
        country="US",
        channel="agent",
        agent_id=minted.agent_id,
        intent=minted.intent,
        device_id="dev_ok",
    )
    payload.update(overrides)
    return PaymentAttempt(**payload)
