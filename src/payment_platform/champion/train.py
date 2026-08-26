"""Train the in-process XGBoost champion. Time-ordered split. No hot-path blend."""

from __future__ import annotations

import json

import xgboost as xgb
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_score,
    recall_score,
    roc_auc_score,
)

from payment_platform.champion.columns import FEATURE_NAMES, metrics_path, model_path
from payment_platform.champion.dataset import synthetic_ieee_like


def train_and_save(*, n: int = 8000, seed: int = 7) -> dict:
    x, y, _timestamps = synthetic_ieee_like(n=n, seed=seed)
    cut = int(len(x) * 0.8)
    x_train, x_test = x[:cut], x[cut:]
    y_train, y_test = y[:cut], y[cut:]
    dtrain = xgb.DMatrix(x_train, label=y_train, feature_names=FEATURE_NAMES)
    dtest = xgb.DMatrix(x_test, label=y_test, feature_names=FEATURE_NAMES)
    params = {
        "max_depth": 4,
        "eta": 0.25,
        "subsample": 0.9,
        "colsample_bytree": 0.9,
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "nthread": 1,
        "seed": seed,
    }
    booster = xgb.train(params, dtrain, num_boost_round=48, evals=[(dtest, "test")], verbose_eval=False)
    proba = booster.predict(dtest)
    pred = (proba >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, pred, labels=[0, 1]).ravel()
    metrics = {
        "n_train": int(len(x_train)),
        "n_test": int(len(x_test)),
        "split": "time-ordered-80-20",
        "auc_roc": float(roc_auc_score(y_test, proba)),
        "pr_auc": float(average_precision_score(y_test, proba)),
        "precision": float(precision_score(y_test, pred, zero_division=0)),
        "recall": float(recall_score(y_test, pred, zero_division=0)),
        "fpr": float(fp / (fp + tn)) if (fp + tn) else 0.0,
        "fnr": float(fn / (fn + tp)) if (fn + tp) else 0.0,
        "source": "synthetic-ieee-like plus optional data/ieee-cis CSV",
        "hot_path": "xgboost-champion-only",
    }
    dest = model_path()
    booster.save_model(dest)
    metrics_path().write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    return metrics


def main() -> int:
    metrics = train_and_save()
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
