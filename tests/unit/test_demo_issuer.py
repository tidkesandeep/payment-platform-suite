from __future__ import annotations

import json

from demo.issuer import ensure_issuer_keys, load_issuer_private_key, load_issuer_public_jwk
from demo.mint import mint_chain


def test_public_jwk_never_contains_private_d(tmp_path):
    priv_path, pub_path = ensure_issuer_keys(tmp_path)
    pub = json.loads(pub_path.read_text(encoding="utf-8"))
    priv = json.loads(priv_path.read_text(encoding="utf-8"))
    assert "d" not in pub
    assert "d" in priv
    again = load_issuer_public_jwk(tmp_path)
    assert "d" not in again


def test_shared_issuer_can_mint_multiple_chains(tmp_path):
    ensure_issuer_keys(tmp_path)
    issuer = load_issuer_private_key(tmp_path)
    first = mint_chain(issuer_private_key=issuer)
    second = mint_chain(issuer_private_key=issuer)
    assert first.issuer_public_jwk == second.issuer_public_jwk
    assert first.intent["l3_payment"] != second.intent["l3_payment"]
