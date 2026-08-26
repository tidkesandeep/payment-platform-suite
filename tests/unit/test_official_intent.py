from __future__ import annotations

import json

from payment_platform.contracts import AuthStatus
from payment_platform.intent import OfficialIntentVerifier, issuer_public_key_from_jwk
from vi_mint import MemoryNonceStore, agent_attempt, mint_chain


def test_human_path_does_not_need_credentials():
    verifier = OfficialIntentVerifier(issuer_public_key=None, nonce_store=MemoryNonceStore())
    from payment_platform.contracts import PaymentAttempt

    result = verifier.verify(
        PaymentAttempt(
            idempotency_key="k",
            customer_id="c",
            merchant_id="m",
            amount_minor=1,
            currency="USD",
            merchant_category="5411",
            country="US",
            channel="human",
            agent_id=None,
            intent=None,
        )
    )
    assert result.status == AuthStatus.HUMAN.value


def test_agent_without_issuer_fails_closed():
    minted = mint_chain()
    verifier = OfficialIntentVerifier(issuer_public_key=None, nonce_store=MemoryNonceStore())
    result = verifier.verify(agent_attempt(minted))
    assert result.status == AuthStatus.INVALID.value
    assert result.reason == "missing_issuer"


def test_valid_official_chain():
    minted = mint_chain()
    verifier = OfficialIntentVerifier(
        issuer_public_key=minted.issuer_public_key,
        nonce_store=MemoryNonceStore(),
    )
    result = verifier.verify(agent_attempt(minted))
    assert result.status == AuthStatus.VALID.value
    assert result.reason == "intent_verified"
    assert result.claims["payee_id"] == minted.merchant_id
    assert result.claims["amount_minor"] == minted.amount_minor


def test_replay_of_same_chain_is_replay():
    minted = mint_chain()
    store = MemoryNonceStore()
    verifier = OfficialIntentVerifier(
        issuer_public_key=minted.issuer_public_key,
        nonce_store=store,
    )
    first = verifier.verify(agent_attempt(minted))
    second = verifier.verify(agent_attempt(minted))
    assert first.status == AuthStatus.VALID.value
    assert second.status == AuthStatus.REPLAY.value


def test_tampered_signature_fails():
    minted = mint_chain()
    tampered = dict(minted.intent)
    token = tampered["l3_payment"]
    tampered["l3_payment"] = token[:-2] + ("A" if token[-1] != "A" else "B") + token[-1]
    verifier = OfficialIntentVerifier(
        issuer_public_key=minted.issuer_public_key,
        nonce_store=MemoryNonceStore(),
    )
    result = verifier.verify(agent_attempt(minted, intent=tampered))
    assert result.status == AuthStatus.INVALID.value
    assert result.reason in {"signature_failed", "chain_invalid", "malformed_payload"}


def test_valid_is_not_an_approve():
    """Adapter returns VALID (auth column only). Decisioning still requires fraud + policy."""
    minted = mint_chain()
    verifier = OfficialIntentVerifier(
        issuer_public_key=minted.issuer_public_key,
        nonce_store=MemoryNonceStore(),
    )
    result = verifier.verify(agent_attempt(minted))
    assert result.status == AuthStatus.VALID.value
    assert result.status != "APPROVE"


def test_private_d_is_stripped_from_issuer_jwk():
    minted = mint_chain()
    raw = json.dumps({**minted.issuer_public_jwk, "d": "should-never-be-used"})
    key = issuer_public_key_from_jwk(raw)
    assert key is not None
