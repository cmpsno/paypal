"""Offline ML model — standard library inference only.

This module scores rows from the Zenodo offline dataset. It NEVER
scores a live PayPal transaction: a live transaction has no v1-v28
features, and this model was trained on v1-v28 + amount.

How it works (Option C):
  - The model was trained offline with scikit-learn (see
    ~/workspace/paypal-ml-baseline/, train_baseline.py).
  - Its weights were exported to backend/ml/model.json: scaler means
    and scales, 29 coefficients, intercept, and the decision
    threshold (0.99, tuned on the precision-recall curve).
  - Inference here is a dot product + sigmoid in the standard
    library. No scikit-learn, numpy, or any new dependency at
    runtime — the training script verified this reproduces sklearn
    to within 7.9e-07.

Top signals: for a scored row, each feature's contribution is
coefficient * standardized value. The top 3 by absolute value are
returned as *statistical signals* (e.g. "v5") — never as behaviours.
v1-v28 are PCA components; nobody knows what behaviour one of them
represents, and this module never invents one.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent

_MODEL: dict | None = None
_SAMPLES: dict | None = None


def load_model() -> dict:
    """Load backend/ml/model.json (cached after first load)."""
    global _MODEL
    if _MODEL is None:
        _MODEL = json.loads((HERE / "model.json").read_text())
    return _MODEL


def load_samples() -> dict:
    """Load backend/ml/samples.json — real Zenodo rows (cached)."""
    global _SAMPLES
    if _SAMPLES is None:
        _SAMPLES = json.loads((HERE / "samples.json").read_text())
    return _SAMPLES


def feature_vector(amount: float, v: dict) -> list[float]:
    """Build the model's input: log1p(amount), then v1..v28.

    All 28 PCA features are required. A missing feature is an error,
    not a silent zero — a zero would be a made-up value.
    """
    missing = [f"v{i}" for i in range(1, 29) if f"v{i}" not in v]
    if missing:
        raise ValueError(f"missing PCA features: {', '.join(missing)}")
    return [math.log1p(amount)] + [float(v[f"v{i}"]) for i in range(1, 29)]


def predict_proba(amount: float, v: dict) -> float:
    """Probability of fraud for one Zenodo-style row, 0.0–1.0."""
    model = load_model()
    x = feature_vector(amount, v)
    z = sum(
        c * ((xi - m) / s)
        for c, xi, m, s in zip(
            model["coefficients"], x, model["scaler_mean"], model["scaler_scale"]
        )
    )
    z += model["intercept"]
    return 1.0 / (1.0 + math.exp(-z))


def top_signals(amount: float, v: dict, k: int = 3) -> list[dict]:
    """Top-k contributing features, by absolute contribution.

    Each entry is {"feature": "v5", "contribution": 2.31}. The
    contribution is coefficient * standardized value — a statistical
    signal, not a behaviour. Feature names only are shown in the UI;
    the numbers are here for transparency and tests.
    """
    model = load_model()
    x = feature_vector(amount, v)
    contribs = [
        {"feature": name, "contribution": round(float(c * ((xi - m) / s)), 3)}
        for name, c, xi, m, s in zip(
            model["features"], model["coefficients"], x,
            model["scaler_mean"], model["scaler_scale"],
        )
    ]
    contribs.sort(key=lambda d: -abs(d["contribution"]))
    return contribs[:k]


def score(amount: float, v: dict) -> dict:
    """Score one row: probability, FLAG/PASS at the tuned threshold,
    and the top contributing statistical signals."""
    model = load_model()
    prob = predict_proba(amount, v)
    return {
        "probability": round(prob, 4),
        "decision": "FLAG" if prob >= model["threshold"] else "PASS",
        "threshold": model["threshold"],
        "top_signals": top_signals(amount, v),
    }
