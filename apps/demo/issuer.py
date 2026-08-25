"""Generate a local demo issuer keypair into a directory. Private keys stay off git."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from verifiable_intent.crypto.signing import (
    generate_es256_key,
    jwk_to_private_key,
    private_key_to_jwk,
    public_key_to_jwk,
)

PRIV_NAME = "issuer.priv.jwk"
PUB_NAME = "issuer.pub.jwk"


def ensure_issuer_keys(directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    priv_path = directory / PRIV_NAME
    pub_path = directory / PUB_NAME
    if priv_path.is_file():
        private_key = load_issuer_private_key(directory)
        pub_path.write_text(json.dumps(public_key_to_jwk(private_key.public_key())), encoding="utf-8")
        return priv_path, pub_path
    private_key = generate_es256_key()
    priv_path.write_text(json.dumps(private_key_to_jwk(private_key)), encoding="utf-8")
    try:
        priv_path.chmod(0o600)
    except OSError:
        pass
    pub_path.write_text(json.dumps(public_key_to_jwk(private_key.public_key())), encoding="utf-8")
    return priv_path, pub_path


def load_issuer_private_key(directory: Path):
    payload = json.loads((directory / PRIV_NAME).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "d" not in payload:
        raise ValueError("issuer private JWK is missing")
    return jwk_to_private_key(payload)


def load_issuer_public_jwk(directory: Path) -> dict:
    payload = json.loads((directory / PUB_NAME).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("issuer public JWK is missing")
    return {key: value for key, value in payload.items() if key != "d"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a local Verifiable Intent issuer keypair")
    parser.add_argument("--keys", required=True, help="directory for issuer JWKs (volume, not git)")
    args = parser.parse_args(argv)
    _priv, pub = ensure_issuer_keys(Path(args.keys))
    material = json.loads(pub.read_text(encoding="utf-8"))
    if "d" in material:
        raise SystemExit("refusing to write a private key into the public JWK file")
    print(f"issuer public jwk written to {pub}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
