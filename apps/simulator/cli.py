"""HTTP traffic generator. Posts to /v1/payments; never produces to Kafka/Redpanda."""

from __future__ import annotations

import argparse
import sys
import time
import uuid

import httpx


def build_payload(*, channel: str, index: int) -> dict:
    key = f"sim-{uuid.uuid4()}"
    if channel == "agent":
        return {
            "idempotency_key": key,
            "customer_id": f"cust_sim_{index % 50}",
            "merchant_id": "mer_789",
            "amount_minor": 12550,
            "currency": "USD",
            "merchant_category": "5411",
            "country": "US",
            "device_id": "dev_sim",
            "ip_address": "10.0.0.1",
            "channel": "agent",
            "agent_id": "agent_coffee_buyer",
            "intent": {"stub": True},
        }
    return {
        "idempotency_key": key,
        "customer_id": f"cust_sim_{index % 50}",
        "merchant_id": "mer_789",
        "amount_minor": 12550,
        "currency": "USD",
        "merchant_category": "5411",
        "country": "US",
        "device_id": "dev_sim",
        "ip_address": "10.0.0.1",
        "channel": "human",
        "agent_id": None,
        "intent": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="POST payments at the local API")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default="sk_test_demo")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--channel", choices=("human", "agent"), default="human")
    parser.add_argument("--rate", type=float, default=0.0, help="optional delay between posts (seconds)")
    args = parser.parse_args(argv)

    url = args.base_url.rstrip("/") + "/v1/payments"
    headers = {"X-API-Key": args.api_key, "Content-Type": "application/json"}
    ok = 0
    with httpx.Client(timeout=10.0) as client:
        for i in range(args.count):
            payload = build_payload(channel=args.channel, index=i)
            response = client.post(url, headers=headers, json=payload)
            print(f"{response.status_code} {response.text}")
            if response.status_code == 200:
                ok += 1
            if args.rate:
                time.sleep(args.rate)
    print(f"completed {ok}/{args.count} HTTP 200", file=sys.stderr)
    return 0 if ok == args.count else 1


if __name__ == "__main__":
    raise SystemExit(main())
