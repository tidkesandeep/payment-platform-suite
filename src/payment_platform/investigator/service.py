"""Read-only investigator. Builds a case file; never mutates transactions.state."""

from __future__ import annotations

from typing import Any

from payment_platform.features.vector import FeatureVector
from payment_platform.ids import new_ulid
from payment_platform.investigator.limits import ToolRateLimiter
from payment_platform.investigator.template import render_case
from payment_platform.investigator.tools import (
    InvestigationNotFound,
    RateLimited,
    ToolDenied,
    as_tool_data,
    assert_allowlisted,
)


class Investigator:
    def __init__(
        self,
        db: Any,
        scorer: Any,
        *,
        metrics: Any = None,
        limiter: ToolRateLimiter | None = None,
        max_per_minute: int = 60,
    ):
        self._db = db
        self._scorer = scorer
        self._metrics = metrics
        self._limiter = limiter or ToolRateLimiter(max_per_minute=max_per_minute)

    def invoke(
        self,
        tool: str,
        arguments: dict[str, Any] | None,
        *,
        agent_id: str,
        investigation_id: str | None = None,
    ) -> dict[str, Any]:
        args = arguments if isinstance(arguments, dict) else {}
        try:
            assert_allowlisted(tool)
        except ToolDenied as denied:
            self._finish(agent_id, tool, args, investigation_id, error=denied.reason, ok=False)
            raise
        if not self._limiter.allow(agent_id, tool):
            self._finish(agent_id, tool, args, investigation_id, error="rate_limited", ok=False)
            raise RateLimited(tool)
        try:
            payload = self._dispatch(tool, args, agent_id=agent_id)
        except InvestigationNotFound:
            self._finish(agent_id, tool, args, investigation_id, error="not_found", ok=False)
            raise
        except (ToolDenied, RateLimited):
            raise
        except Exception as exc:
            self._finish(
                agent_id, tool, args, investigation_id, error=str(exc), ok=False
            )
            raise
        wrapped = as_tool_data(payload)
        if investigation_id is None and isinstance(payload, dict):
            minted = payload.get("investigation_id")
            if isinstance(minted, str):
                investigation_id = minted
        self._finish(agent_id, tool, args, investigation_id, result=wrapped, ok=True)
        return wrapped

    def open_case(self, *, transaction_id: str, agent_id: str) -> dict[str, Any]:
        row = self._db.get_transaction(transaction_id)
        if row is None:
            raise InvestigationNotFound(transaction_id)
        created = self.invoke(
            "create_investigation",
            {"transaction_id": transaction_id},
            agent_id=agent_id,
        )
        investigation_id = str(created["payload"]["investigation_id"])
        txn = self.invoke(
            "get_transaction",
            {"transaction_id": transaction_id},
            agent_id=agent_id,
            investigation_id=investigation_id,
        )
        features = self.invoke(
            "get_features",
            {"transaction_id": transaction_id},
            agent_id=agent_id,
            investigation_id=investigation_id,
        )
        intent = self.invoke(
            "verify_intent",
            {"transaction_id": transaction_id},
            agent_id=agent_id,
            investigation_id=investigation_id,
        )
        shap = self._shap(txn["payload"], features["payload"])
        case = render_case(
            transaction=txn["payload"],
            features=features["payload"],
            intent=intent["payload"],
            shap=shap,
        )
        status = "escalated" if case["escalation"] else "open"
        self._db.save_investigation_case(investigation_id, case_file=case, status=status)
        return {
            "investigation_id": investigation_id,
            "transaction_id": transaction_id,
            "status": status,
            "case_file": case,
        }

    def _dispatch(self, tool: str, args: dict[str, Any], *, agent_id: str) -> dict[str, Any]:
        transaction_id = str(args.get("transaction_id") or "")
        if tool == "create_investigation":
            if not transaction_id:
                raise InvestigationNotFound("")
            if self._db.get_transaction(transaction_id) is None:
                raise InvestigationNotFound(transaction_id)
            investigation_id = new_ulid()
            self._db.insert_investigation(
                investigation_id=investigation_id,
                transaction_id=transaction_id,
                agent_id=agent_id,
            )
            return {"investigation_id": investigation_id, "transaction_id": transaction_id}
        if not transaction_id:
            raise InvestigationNotFound("")
        if tool == "get_transaction":
            row = self._db.get_transaction(transaction_id)
            if row is None:
                raise InvestigationNotFound(transaction_id)
            return _jsonable(row)
        if tool == "get_features":
            decision = self._db.get_decision_json(transaction_id) or {}
            return (decision.get("fraud") or {}).get("features") or {}
        if tool == "verify_intent":
            decision = self._db.get_decision_json(transaction_id) or {}
            auth = decision.get("authorization") or {}
            return {
                "status": auth.get("status"),
                "reason": auth.get("reason"),
                "source": "stored_decision",
            }
        raise ToolDenied(tool)

    def _shap(self, transaction: dict[str, Any], features: dict[str, Any] | None) -> list[dict[str, Any]] | None:
        if str(transaction.get("state") or "") == "AUTHORIZED":
            return None
        if not features or not hasattr(self._scorer, "shap_values"):
            return None
        try:
            return self._scorer.shap_values(FeatureVector.from_dict(features))
        except Exception:
            return None

    def _finish(
        self,
        agent_id: str,
        tool: str,
        args: dict[str, Any],
        investigation_id: str | None,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        ok: bool,
    ) -> None:
        try:
            self._db.append_investigator_audit(
                investigation_id=investigation_id,
                agent_id=agent_id,
                tool=tool,
                arguments=args,
                result=result,
                error=error,
            )
        except Exception:
            pass
        if self._metrics is None:
            return
        if ok:
            self._metrics.inc_investigator_call(tool, "ok")
        else:
            self._metrics.inc_investigator_call(tool, "error")
            self._metrics.inc_investigator_failure(tool)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value
