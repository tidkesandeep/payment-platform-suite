"""Official Mastercard Verifiable Intent adapter.

Calls the published `verifiable_intent` library. Does not implement
cryptography, mint credentials, or treat a valid signature as an approve.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from cryptography.hazmat.primitives.asymmetric import ec

from payment_platform.contracts import AuthStatus, IntentResult, PaymentAttempt

_LOG = logging.getLogger("payment_platform.intent")

_PAYMENT_OPEN = "mandate.payment.open.1"
_PAYMENT_FINAL = "mandate.payment.1"


class NonceStore(Protocol):
    def claim_intent_nonce(self, nonce: str) -> bool:
        """Return True if the nonce is new; False if it was already presented."""


class OfficialIntentVerifier:
    """Network-side verifier: official chain + constraints, then platform bindings."""

    def __init__(
        self,
        *,
        issuer_public_key: ec.EllipticCurvePublicKey | None,
        nonce_store: NonceStore | None,
    ):
        self._issuer_public_key = issuer_public_key
        self._nonce_store = nonce_store

    def verify(self, request: PaymentAttempt) -> IntentResult:
        try:
            return self._verify(request)
        except Exception:
            _LOG.exception("intent verifier failed closed")
            return IntentResult(
                status=AuthStatus.INVALID.value,
                reason="intent_fail_closed",
                claims={},
            )

    def _verify(self, request: PaymentAttempt) -> IntentResult:
        if request.channel == "human":
            return IntentResult(
                status=AuthStatus.HUMAN.value,
                reason="human_path",
                claims={},
            )

        payload = request.intent
        if not isinstance(payload, dict):
            return _invalid("missing_payload")
        l1_ser = payload.get("l1")
        l2_ser = payload.get("l2")
        l3_ser = payload.get("l3_payment")
        if not all(isinstance(part, str) and part for part in (l1_ser, l2_ser, l3_ser)):
            return _invalid("missing_payload")
        l2_payment_ser = payload.get("l2_payment")
        if l2_payment_ser is not None and not isinstance(l2_payment_ser, str):
            return _invalid("malformed_payload")

        if self._issuer_public_key is None:
            return _invalid("missing_issuer")

        from verifiable_intent.crypto.sd_jwt import decode_sd_jwt
        from verifiable_intent.verification.chain import verify_chain
        from verifiable_intent.verification.constraint_checker import (
            StrictnessMode,
            check_constraints,
        )

        try:
            l1 = decode_sd_jwt(l1_ser)
            l2 = decode_sd_jwt(l2_ser)
            l3 = decode_sd_jwt(l3_ser)
        except Exception:
            return _invalid("malformed_payload")

        chain = verify_chain(
            l1,
            l2,
            l3_payment=l3,
            issuer_public_key=self._issuer_public_key,
            l1_serialized=l1_ser,
            l2_serialized=l2_ser,
            l2_payment_serialized=l2_payment_ser if isinstance(l2_payment_ser, str) else None,
        )
        if not chain.valid:
            reason = _chain_reason(chain.errors)
            status = AuthStatus.EXPIRED.value if reason == "expired" else AuthStatus.INVALID.value
            return IntentResult(status=status, reason=reason, claims={"errors": list(chain.errors)})

        payment_mandate = _payment_mandate(chain.l2_claims, (_PAYMENT_OPEN, _PAYMENT_FINAL))
        if not payment_mandate:
            return _invalid("missing_payment_mandate")
        constraints = payment_mandate.get("constraints") or []
        if not isinstance(constraints, list):
            return _invalid("malformed_payload")

        fulfillment = _payment_mandate(chain.l3_payment_claims, (_PAYMENT_FINAL,))
        if not fulfillment:
            return _invalid("missing_fulfillment")
        fulfillment = dict(fulfillment)
        fulfillment["allowed_merchants"] = _resolve_payees(l2, constraints)

        constraint_result = check_constraints(
            constraints,
            fulfillment,
            mode=StrictnessMode.STRICT,
        )
        if not constraint_result.satisfied:
            return IntentResult(
                status=AuthStatus.INVALID.value,
                reason="constraint_violation",
                claims={"violations": list(constraint_result.violations)},
            )

        l2_nonce = chain.l2_claims.get("nonce")
        l3_nonce = chain.l3_payment_claims.get("nonce")
        if not isinstance(l2_nonce, str) or not l2_nonce:
            return _invalid("missing_nonce")
        if not isinstance(l3_nonce, str) or not l3_nonce:
            return _invalid("missing_nonce")
        if self._nonce_store is None:
            return _invalid("nonce_store_unavailable")
        for nonce in (f"l2:{l2_nonce}", f"l3:{l3_nonce}"):
            if not self._nonce_store.claim_intent_nonce(nonce):
                return IntentResult(
                    status=AuthStatus.REPLAY.value,
                    reason="replay",
                    claims={"l2_nonce": l2_nonce},
                )

        agent_kid = _cnf_kid(payment_mandate)
        payee = fulfillment.get("payee") if isinstance(fulfillment.get("payee"), dict) else {}
        payee_id = payee.get("id") if isinstance(payee, dict) else None
        payment_amount = (
            fulfillment.get("payment_amount")
            if isinstance(fulfillment.get("payment_amount"), dict)
            else {}
        )
        bound_amount = payment_amount.get("amount") if isinstance(payment_amount, dict) else None
        bound_currency = payment_amount.get("currency") if isinstance(payment_amount, dict) else None

        claims = {
            "agent_kid": agent_kid,
            "payee_id": payee_id,
            "amount_minor": bound_amount,
            "currency": bound_currency,
            "l2_nonce": l2_nonce,
            "mode": "autonomous",
        }

        if not isinstance(agent_kid, str) or agent_kid != request.agent_id:
            return IntentResult(
                status=AuthStatus.INVALID.value,
                reason="agent_mismatch",
                claims=claims,
            )
        if not isinstance(bound_amount, int) or bound_amount != request.amount_minor:
            return IntentResult(
                status=AuthStatus.INVALID.value,
                reason="amount_mismatch",
                claims=claims,
            )
        if not isinstance(payee_id, str) or payee_id != request.merchant_id:
            return IntentResult(
                status=AuthStatus.INVALID.value,
                reason="merchant_mismatch",
                claims=claims,
            )
        if not isinstance(bound_currency, str) or bound_currency != request.currency:
            return IntentResult(
                status=AuthStatus.INVALID.value,
                reason="claim_mismatch",
                claims=claims,
            )

        return IntentResult(
            status=AuthStatus.VALID.value,
            reason="intent_verified",
            claims=claims,
        )


def issuer_public_key_from_jwk(raw: str) -> ec.EllipticCurvePublicKey | None:
    """Parse an issuer *public* JWK. Private `d` material is stripped, never used."""
    if not raw or not raw.strip():
        return None
    try:
        jwk = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(jwk, dict):
        return None
    public_jwk = {key: value for key, value in jwk.items() if key != "d"}
    try:
        from verifiable_intent.crypto.signing import jwk_to_public_key

        return jwk_to_public_key(public_jwk)
    except Exception:
        return None


def _invalid(reason: str, claims: dict[str, Any] | None = None) -> IntentResult:
    return IntentResult(
        status=AuthStatus.INVALID.value,
        reason=reason,
        claims=claims or {},
    )


def _chain_reason(errors: list[str]) -> str:
    joined = " ".join(errors).lower()
    if "expired" in joined:
        return "expired"
    if "signature" in joined:
        return "signature_failed"
    return "chain_invalid"


def _payment_mandate(claims: dict[str, Any], vcts: tuple[str, ...]) -> dict[str, Any]:
    delegates = claims.get("delegate_payload")
    if not isinstance(delegates, list):
        return {}
    for delegate in delegates:
        if isinstance(delegate, dict) and delegate.get("vct") in vcts:
            return delegate
    return {}


def _cnf_kid(mandate: dict[str, Any]) -> str | None:
    cnf = mandate.get("cnf")
    if not isinstance(cnf, dict):
        return None
    jwk = cnf.get("jwk")
    if not isinstance(jwk, dict):
        return None
    kid = jwk.get("kid")
    return kid if isinstance(kid, str) and kid else None


def _resolve_payees(l2: Any, constraints: list[Any]) -> list[dict[str, Any]]:
    from verifiable_intent.crypto.disclosure import hash_disclosure

    disc_by_hash: dict[str, Any] = {}
    for disc_str, disc_val in zip(l2.disclosures, l2.disclosure_values):
        disc_by_hash[hash_disclosure(disc_str)] = disc_val
    resolved: list[dict[str, Any]] = []
    for constraint in constraints:
        if not isinstance(constraint, dict):
            continue
        if constraint.get("type") != "mandate.payment.allowed_payees":
            continue
        for ref in constraint.get("allowed") or []:
            ref_hash = ref.get("...") if isinstance(ref, dict) else ""
            if not isinstance(ref_hash, str) or ref_hash not in disc_by_hash:
                continue
            value = disc_by_hash[ref_hash][-1]
            if isinstance(value, dict):
                resolved.append(value)
    return resolved
