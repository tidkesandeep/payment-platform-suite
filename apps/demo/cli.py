"""Drive human and agent payments against a running API. Never produces to Kafka."""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

from demo.issuer import load_issuer_private_key
from demo.mint import mint_chain


def human_payload(*, device_id: str = "dev_ok") -> dict:
    return {
        "idempotency_key": f"demo-human-{uuid.uuid4()}",
        "customer_id": "cust_demo_human",
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


def agent_payload(minted, *, device_id: str = "dev_ok") -> dict:
    return {
        "idempotency_key": f"demo-agent-{uuid.uuid4()}",
        "customer_id": "cust_demo_agent",
        "merchant_id": minted.merchant_id,
        "amount_minor": minted.amount_minor,
        "currency": minted.currency,
        "merchant_category": "5411",
        "country": "US",
        "device_id": device_id,
        "ip_address": "10.0.0.1",
        "channel": "agent",
        "agent_id": minted.agent_id,
        "intent": minted.intent,
    }


def wait_ready(client: httpx.Client, base_url: str, *, timeout_s: float = 30.0) -> None:
    deadline = time.time() + timeout_s
    health = base_url.rstrip("/") + "/health"
    while time.time() < deadline:
        try:
            response = client.get(health)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise SystemExit(f"API not ready at {health}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Human + agent demo against /v1/payments")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default="sk_test_demo")
    parser.add_argument("--keys", required=True, help="directory with issuer.priv.jwk from payment-demo-issuer")
    args = parser.parse_args(argv)

    issuer_private = load_issuer_private_key(Path(args.keys))
    headers = {"X-API-Key": args.api_key, "Content-Type": "application/json"}
    payments = args.base_url.rstrip("/") + "/v1/payments"
    holds = args.base_url.rstrip("/") + "/v1/holds"

    scenarios = [
        ("human_low", "human", "dev_ok", "AUTHORIZED"),
        ("agent_low", "agent", "dev_ok", "AUTHORIZED"),
        ("agent_high", "agent", "dev_high", "MANUAL_REVIEW"),
        ("agent_critical", "agent", "dev_critical", "RISK_DECLINED"),
    ]

    results: list[dict] = []
    with httpx.Client(timeout=15.0) as client:
        wait_ready(client, args.base_url)
        for name, channel, device_id, expected in scenarios:
            if channel == "human":
                payload = human_payload(device_id=device_id)
            else:
                minted = mint_chain(issuer_private_key=issuer_private)
                payload = agent_payload(minted, device_id=device_id)
            response = client.post(payments, headers=headers, json=payload)
            body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            state = body.get("state")
            row = {
                "scenario": name,
                "http": response.status_code,
                "state": state,
                "expected": expected,
                "transaction_id": body.get("transaction_id"),
                "ok": response.status_code == 200 and state == expected,
            }
            results.append(row)
            print(json.dumps(row))
        listed = client.get(holds, headers={"X-API-Key": args.api_key})
        print(json.dumps({"holds_http": listed.status_code, "holds": listed.json() if listed.status_code == 200 else None}))

    failed = [row for row in results if not row["ok"]]
    if failed:
        print(f"demo failed: {len(failed)} scenario(s)", file=sys.stderr)
        return 1
    print("demo ok: human AUTHORIZED, agent AUTHORIZED, H MANUAL_REVIEW, H2 RISK_DECLINED", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
