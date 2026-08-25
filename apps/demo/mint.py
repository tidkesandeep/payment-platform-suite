"""Official L1–L3 minting for the local demo and tests. Not used on authorize."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric import ec
from verifiable_intent import (
    AllowedMerchantConstraint,
    AllowedPayeeConstraint,
    CheckoutLineItemsConstraint,
    CheckoutMandate,
    FinalPaymentMandate,
    IssuerCredential,
    MandateMode,
    PaymentAmountConstraint,
    PaymentL3Mandate,
    PaymentMandate,
    UserMandate,
    create_layer1,
    create_layer2_autonomous,
    create_layer3_payment,
)
from verifiable_intent.crypto.disclosure import build_selective_presentation, hash_bytes
from verifiable_intent.crypto.signing import generate_es256_key, public_key_to_jwk

_PAYMENT_INSTRUMENT = {
    "type": "mastercard.srcDigitalCard",
    "id": "synthetic-card-1",
    "description": "Synthetic **** 0000",
}
_DEMO_ITEM = {"id": "sku-demo-1", "title": "Demo item"}


@dataclass(frozen=True)
class MintedChain:
    intent: dict
    issuer_public_key: ec.EllipticCurvePublicKey
    issuer_public_jwk: dict
    agent_id: str
    merchant_id: str
    amount_minor: int
    currency: str
    l2_nonce: str
    l3_nonce: str


def mint_chain(
    *,
    agent_id: str = "agent_coffee_buyer",
    merchant_id: str = "mer_789",
    amount_minor: int = 12550,
    currency: str = "USD",
    min_amount: int = 1,
    max_amount: int = 50_000,
    l3_amount: int | None = None,
    l3_payee_id: str | None = None,
    l3_currency: str | None = None,
    l2_exp_offset: int = 3600,
    l3_exp_offset: int = 300,
    now: int | None = None,
    issuer_private_key: ec.EllipticCurvePrivateKey | None = None,
) -> MintedChain:
    issued_at = int(time.time()) if now is None else now
    issuer_priv = issuer_private_key or generate_es256_key()
    user_priv = generate_es256_key()
    agent_priv = generate_es256_key()
    user_jwk = public_key_to_jwk(user_priv)
    agent_jwk = public_key_to_jwk(agent_priv)
    merchant = {
        "id": merchant_id,
        "name": "Demo Merchant",
        "website": "https://merchant.example",
    }
    l3_merchant = dict(merchant)
    if l3_payee_id is not None:
        l3_merchant = {
            "id": l3_payee_id,
            "name": "Other Merchant",
            "website": "https://other.example",
        }
    bound_amount = amount_minor if l3_amount is None else l3_amount
    bound_currency = currency if l3_currency is None else l3_currency
    l2_nonce = str(uuid.uuid4())
    l3_nonce = str(uuid.uuid4())

    l1 = create_layer1(
        IssuerCredential(
            iss="https://www.mastercard.com",
            sub="user-demo-001",
            iat=issued_at,
            exp=issued_at + 86400,
            aud="https://wallet.example.com",
            cnf_jwk=user_jwk,
            email="demo@example.com",
            pan_last_four="0000",
            scheme="Mastercard",
        ),
        issuer_priv,
    )
    l1_ser = l1.serialize()

    l2 = create_layer2_autonomous(
        UserMandate(
            nonce=l2_nonce,
            aud="https://agent.example",
            iat=issued_at,
            iss="https://wallet.example.com",
            exp=issued_at + l2_exp_offset,
            mode=MandateMode.AUTONOMOUS,
            sd_hash=hash_bytes(l1_ser.encode("ascii")),
            checkout_mandate=CheckoutMandate(
                vct="mandate.checkout.open.1",
                cnf_jwk=agent_jwk,
                cnf_kid=agent_id,
                constraints=[
                    AllowedMerchantConstraint(allowed=[merchant]),
                    CheckoutLineItemsConstraint(
                        items=[{"id": "line-item-1", "acceptable_items": [_DEMO_ITEM], "quantity": 1}],
                    ),
                ],
            ),
            payment_mandate=PaymentMandate(
                vct="mandate.payment.open.1",
                cnf_jwk=agent_jwk,
                cnf_kid=agent_id,
                payment_instrument=_PAYMENT_INSTRUMENT,
                constraints=[
                    PaymentAmountConstraint(currency=currency, min=min_amount, max=max_amount),
                    AllowedPayeeConstraint(allowed=[merchant]),
                ],
            ),
            merchants=[merchant],
            acceptable_items=[_DEMO_ITEM],
        ),
        user_priv,
    )
    l2_ser = l2.serialize()
    payment_disc = _find_disclosure(
        l2, lambda v: isinstance(v, dict) and v.get("vct") == "mandate.payment.open.1"
    )
    merchant_disc = _find_disclosure(l2, lambda v: isinstance(v, dict) and v.get("id") == merchant_id)
    if payment_disc is None or merchant_disc is None:
        raise RuntimeError("minted L2 is missing payment or merchant disclosures")
    l2_base = l2_ser.split("~")[0]
    l2_payment_ser = build_selective_presentation(l2_base, [payment_disc, merchant_disc])

    l3 = create_layer3_payment(
        PaymentL3Mandate(
            nonce=l3_nonce,
            aud="https://www.mastercard.com",
            iat=issued_at,
            iss="https://agent.example.com",
            exp=issued_at + l3_exp_offset,
            final_payment=FinalPaymentMandate(
                transaction_id=f"synthetic-txn-{uuid.uuid4().hex[:8]}",
                payee=l3_merchant,
                payment_amount={"currency": bound_currency, "amount": bound_amount},
                payment_instrument=_PAYMENT_INSTRUMENT,
            ),
            final_merchant=l3_merchant,
        ),
        agent_priv,
        l2_base,
        payment_disc,
        merchant_disc,
        kid=agent_id,
    )

    issuer_public_jwk = public_key_to_jwk(issuer_priv.public_key())
    return MintedChain(
        intent={
            "l1": l1_ser,
            "l2": l2_ser,
            "l3_payment": l3.serialize(),
            "l2_payment": l2_payment_ser,
        },
        issuer_public_key=issuer_priv.public_key(),
        issuer_public_jwk=issuer_public_jwk,
        agent_id=agent_id,
        merchant_id=merchant_id,
        amount_minor=bound_amount,
        currency=bound_currency,
        l2_nonce=l2_nonce,
        l3_nonce=l3_nonce,
    )


def _find_disclosure(sd_jwt, predicate) -> str | None:
    for disc_str, disc_val in zip(sd_jwt.disclosures, sd_jwt.disclosure_values):
        value = disc_val[-1] if disc_val else None
        if predicate(value):
            return disc_str
    return None
