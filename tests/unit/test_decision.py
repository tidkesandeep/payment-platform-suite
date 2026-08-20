from __future__ import annotations

from payment_platform.decision import decide


def test_low_fraud_approves():
    record = decide(
        transaction_id="t1",
        authorization_status="HUMAN",
        authorization_reason="human_path",
        fraud_score=0.12,
        fraud_band="LOW",
        policy_status="PASS",
        policy_violations=[],
    )
    assert record.decision == "approve"
    assert record.state == "AUTHORIZED"


def test_medium_challenges():
    record = decide(
        transaction_id="t1",
        authorization_status="VALID",
        authorization_reason="intent_verified",
        fraud_score=0.4,
        fraud_band="MEDIUM",
        policy_status="PASS",
        policy_violations=[],
    )
    assert record.decision == "challenge"
    assert record.state == "CHALLENGED"


def test_high_reviews():
    record = decide(
        transaction_id="t1",
        authorization_status="VALID",
        authorization_reason="intent_verified",
        fraud_score=0.8,
        fraud_band="HIGH",
        policy_status="PASS",
        policy_violations=[],
    )
    assert record.decision == "review"
    assert record.state == "MANUAL_REVIEW"


def test_critical_risk_declines():
    record = decide(
        transaction_id="t1",
        authorization_status="VALID",
        authorization_reason="intent_verified",
        fraud_score=0.97,
        fraud_band="CRITICAL",
        policy_status="PASS",
        policy_violations=[],
    )
    assert record.decision == "decline"
    assert record.state == "RISK_DECLINED"


def test_unknown_reviews():
    record = decide(
        transaction_id="t1",
        authorization_status="HUMAN",
        authorization_reason="human_path",
        fraud_score=None,
        fraud_band="UNKNOWN",
        policy_status="PASS",
        policy_violations=[],
    )
    assert record.state == "MANUAL_REVIEW"


def test_policy_fail_wins_over_low_fraud():
    record = decide(
        transaction_id="t1",
        authorization_status="VALID",
        authorization_reason="intent_verified",
        fraud_score=0.01,
        fraud_band="LOW",
        policy_status="FAIL",
        policy_violations=["max_amount_minor"],
    )
    assert record.decision == "decline"
    assert record.state == "POLICY_VIOLATION"


def test_invalid_intent_wins_over_everything():
    record = decide(
        transaction_id="t1",
        authorization_status="INVALID",
        authorization_reason="stub_fail_closed",
        fraud_score=0.01,
        fraud_band="LOW",
        policy_status="PASS",
        policy_violations=[],
    )
    assert record.state == "INTENT_INVALID"
