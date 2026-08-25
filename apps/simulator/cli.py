"""HTTP traffic generator. Posts to /v1/payments; never produces to Kafka/Redpanda."""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

import httpx


def build_human_payload(*, index: int, device_id: str = "dev_sim") -> dict:
    return {
        "idempotency_key": f"sim-{uuid.uuid4()}",
        "customer_id": f"cust_sim_{index % 50}",
        "merchant_id": "mer_789",
        "amount_minor": 12550,
        "currency": "USD",
        "merchant_category": "5411",
        "country": "US",
        "device_id": device_id,
        "ip_address": "10.0.0.1",
        "channel": "human",
        "agent_id": None,
        "intent": None,
    }


def build_agent_payload(*, index: int, intent: dict, agent_id: str, device_id: str = "dev_sim") -> dict:
    return {
        "idempotency_key": f"sim-{uuid.uuid4()}",
        "customer_id": f"cust_sim_{index % 50}",
        "merchant_id": "mer_789",
        "amount_minor": 12550,
        "currency": "USD",
        "merchant_category": "5411",
        "country": "US",
        "device_id": device_id,
        "ip_address": "10.0.0.1",
        "channel": "agent",
        "agent_id": agent_id,
        "intent": intent,
    }


def _select_channel(mode: str, index: int) -> str:
    if mode == "both":
        return "human" if index % 2 == 0 else "agent"
    return mode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="POST payments at the local API")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default="sk_test_demo")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--channel", choices=("human", "agent", "both"), default="human")
    parser.add_argument("--keys-dir", default="", help="issuer JWK directory (required for agent/both)")
    parser.add_argument("--rate", type=float, default=0.0, help="optional delay between posts (seconds)")
    parser.add_argument(
        "--tps",
        type=float,
        default=0.0,
        help="modest target posts per second (capped at 200; never produces to Kafka)",
    )
    args = parser.parse_args(argv)

    issuer_private = None
    if args.channel in {"agent", "both"}:
        if not args.keys_dir:
            print("agent traffic requires --keys-dir from payment-demo-issuer", file=sys.stderr)
            return 2
        from demo.issuer import load_issuer_private_key
        from demo.mint import mint_chain as _mint

        issuer_private = load_issuer_private_key(Path(args.keys_dir))
        mint_chain = _mint
    else:
        mint_chain = None

    url = args.base_url.rstrip("/") + "/v1/payments"
    headers = {"X-API-Key": args.api_key, "Content-Type": "application/json"}
    ok = 0
    with httpx.Client(timeout=15.0) as client:
        for i in range(args.count):
            channel = _select_channel(args.channel, i)
            if channel == "agent":
                minted = mint_chain(issuer_private_key=issuer_private)
                payload = build_agent_payload(
                    index=i, intent=minted.intent, agent_id=minted.agent_id
                )
            else:
                payload = build_human_payload(index=i)
            response = client.post(url, headers=headers, json=payload)
            print(f"{response.status_code} {response.text}")
            if response.status_code == 200:
                ok += 1
            if args.tps > 0:
                delay = 1.0 / min(args.tps, 200.0)
                time.sleep(delay)
            elif args.rate:
                time.sleep(args.rate)
    print(f"completed {ok}/{args.count} HTTP 200", file=sys.stderr)
    return 0 if ok == args.count else 1


if __name__ == "__main__":
    raise SystemExit(main())
