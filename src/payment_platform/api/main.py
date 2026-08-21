from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis import Redis
from redis.exceptions import RedisError

from payment_platform.authorize import AppDeps, AuthorizeError, authorize_payment
from payment_platform.config import Settings, settings as default_settings
from payment_platform.db import PostgresStore
from payment_platform.champion.model import XGBoostChampion
from payment_platform.features.store import FeatureStore
from payment_platform.features.vector import FeatureVector
from payment_platform.fraud import StubChampionScorer
from payment_platform.intent import StubIntentVerifier
from payment_platform.observability.jsonlog import configure_json_logging
from payment_platform.observability.metrics import PlatformMetrics
from payment_platform.observability.tracing import make_tracer
from payment_platform.velocity import VelocityStore


def create_app(
    *,
    settings: Settings | None = None,
    deps: AppDeps | None = None,
) -> FastAPI:
    cfg = settings or default_settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if deps is not None:
            app.state.deps = deps
            yield
            return
        configure_json_logging()
        db = PostgresStore(cfg.database_url)
        db.ensure_schema()
        redis = Redis.from_url(cfg.redis_url, decode_responses=True)
        try:
            scorer = XGBoostChampion.load(timeout_ms=cfg.score_timeout_ms)
        except Exception:
            scorer = StubChampionScorer()
        app.state.deps = AppDeps(
            settings=cfg,
            db=db,
            velocity=VelocityStore(redis, db),
            intent=StubIntentVerifier(fail_closed=cfg.intent_fail_closed),
            scorer=scorer,
            features=FeatureStore(redis),
            metrics=PlatformMetrics(),
            tracer=make_tracer(),
        )
        app.state.redis = redis
        try:
            yield
        finally:
            redis.close()
            db.close()

    app = FastAPI(title="Payment Platform", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(AuthorizeError)
    async def authorize_error_handler(_request: Request, exc: AuthorizeError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.body)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": "validation_failed", "details": [str(e) for e in exc.errors()]},
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready(request: Request) -> JSONResponse:
        current: AppDeps = request.app.state.deps
        try:
            current.db.ping()
        except Exception:
            return JSONResponse(status_code=503, content={"status": "not_ready", "reason": "postgres"})
        redis_ok = True
        redis = getattr(request.app.state, "redis", None)
        if redis is not None:
            try:
                redis.ping()
            except (RedisError, OSError):
                redis_ok = False
        status = "ready" if redis_ok else "ready-degraded"
        try:
            lag = current.db.outbox_lag()
        except Exception:
            lag = -1
        p95_ms = None
        if current.metrics is not None:
            current.metrics.set_outbox_lag(lag)
            p95 = current.metrics.decision_p95_seconds()
            if p95 is not None:
                p95_ms = round(p95 * 1000, 3)
        return JSONResponse(
            {
                "status": status,
                "redis": redis_ok,
                "outbox_lag": lag,
                "p95_decision_ms": p95_ms,
                "slo": {
                    "decision_p95_ms_target": 100,
                    "contractual": False,
                },
            }
        )

    @app.post("/v1/payments")
    async def create_payment(
        request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        current: AppDeps = request.app.state.deps
        raw = await request.body()
        secret = _api_secret(x_api_key, authorization)
        if not secret:
            _observe_http(current, "/v1/payments", 401)
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        try:
            api_key_id = current.db.resolve_api_key(
                secret, current.settings.api_key, current.settings.api_key_id
            )
        except Exception:
            _observe_http(current, "/v1/payments", 503)
            return JSONResponse(status_code=503, content={"error": "unavailable"})
        if api_key_id is None:
            _observe_http(current, "/v1/payments", 401)
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            _observe_http(current, "/v1/payments", 422)
            return JSONResponse(
                status_code=422,
                content={"error": "validation_failed", "details": ["body must be JSON"]},
            )
        if not isinstance(body, dict):
            _observe_http(current, "/v1/payments", 422)
            return JSONResponse(
                status_code=422,
                content={"error": "validation_failed", "details": ["body must be a JSON object"]},
            )
        status_code, payload = authorize_payment(
            deps=current,
            api_key_id=api_key_id,
            raw_body=body,
            idempotency_key=idempotency_key,
            body_bytes_len=len(raw),
        )
        _observe_http(current, "/v1/payments", status_code)
        return JSONResponse(status_code=status_code, content=payload)

    @app.get("/metrics")
    def metrics(request: Request) -> Response:
        current: AppDeps = request.app.state.deps
        if current.metrics is None:
            return Response(status_code=404, content="metrics disabled")
        try:
            current.metrics.set_outbox_lag(current.db.outbox_lag())
        except Exception:
            pass
        return Response(
            generate_latest(current.metrics.registry),
            media_type=CONTENT_TYPE_LATEST,
        )

    @app.get("/v1/payments/{transaction_id}")
    def get_payment(transaction_id: str, request: Request) -> JSONResponse:
        current: AppDeps = request.app.state.deps
        try:
            row = current.db.get_transaction(transaction_id)
        except Exception:
            return JSONResponse(status_code=503, content={"error": "unavailable"})
        if row is None:
            return JSONResponse(status_code=404, content={"error": "not_found"})
        return JSONResponse(_serialize_row(row))

    @app.post("/v1/payments/{transaction_id}/explain")
    def explain(transaction_id: str, request: Request) -> JSONResponse:
        current: AppDeps = request.app.state.deps
        row = current.db.get_transaction(transaction_id)
        if row is None:
            return JSONResponse(status_code=404, content={"error": "not_found"})
        body = _serialize_row(row)
        body["shap"] = None
        if row.get("state") == "AUTHORIZED":
            body["note"] = "SHAP is not computed on APPROVE"
            return JSONResponse(body)
        # SHAP is on-demand only. The authorize path never computes it.
        scorer = current.scorer
        decision = current.db.get_decision_json(transaction_id) or {}
        raw_features = (decision.get("fraud") or {}).get("features")
        if raw_features and hasattr(scorer, "shap_values"):
            try:
                body["shap"] = scorer.shap_values(FeatureVector.from_dict(raw_features))
            except Exception:
                body["shap"] = None
                body["note"] = "SHAP explainer failed"
        else:
            body["note"] = "SHAP requires the XGBoost champion and stored features"
        return JSONResponse(body)

    return app


def _observe_http(deps: AppDeps, path: str, status: int) -> None:
    if deps.metrics is not None:
        deps.metrics.observe_http(path, status)


def _api_secret(x_api_key: str | None, authorization: str | None) -> str | None:
    if x_api_key:
        return x_api_key
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if hasattr(value, "isoformat"):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("payment_platform.api.main:app", host="0.0.0.0", port=8000, reload=False)
