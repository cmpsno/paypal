"""Dashboard server — one process, stdlib only, no new dependency.

Run from the repo root:
    python3 -m backend.app
Then open http://localhost:8000

What it does:
  GET  /                    -> the dashboard (frontend/index.html)
  GET  /style.css, /app.js, /config.js -> dashboard assets
  GET  /health              -> {"ok": true} (Render health check)
  GET  /api/transactions    -> every transaction scored so far, newest first
  POST /api/score           -> score one transaction, record it, return it
  POST /api/reset           -> clear demo-session history (for repeatable demos)
  GET  /api/predictions     -> logged predictions, newest first (the feedback loop)
  POST /api/outcomes        -> record a confirmed outcome (fraud/legitimate)
  GET  /api/monitoring      -> volumes, hold rate, confirmed metrics, drift signals
  GET  /api/offline-model   -> offline ML model card (metrics, limits)
  GET  /api/offline-samples -> three real Zenodo rows
  POST /api/offline-score   -> score one Zenodo-style row (amount + v1-v28)

CORS: the API sends Access-Control-Allow-Origin: * so the same
dashboard can also be hosted on GitHub Pages (a different origin)
and call this server on Render. No credentials or secrets are
involved — the API only scores demo transactions.

POST /api/score body (JSON):
  {
    "amount": 400.0,
    "payee_id": "payee-new",        // optional; null/omitted = unknown payee
    "sandbox_status": "SUCCESS"     // or INSTRUMENT_DECLINED, TRANSACTION_REFUSED, ...
  }
  // is_first_payee is NOT submitted: history computes it from
  // transactions already scored this session.

The server enriches the transaction from demo-session history
(median, velocity, first-payee) before scoring, exactly like
backend/demo_sandbox.py does. History lives in memory only and
resets when the server restarts — this is a demo, not a database.

The server never calls PayPal itself. The Sandbox demo script
is separate. The dashboard scores what you submit, using the
same classify() the tests cover.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from backend.history import TransactionHistory
from backend.ml import inference as offline_ml
from backend.models import NormalizedTransaction
from backend import monitoring
from backend.risk import config
from backend.risk.classifier import classify
from backend.risk.explainer import explain

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

HISTORY = TransactionHistory()
SCORED: list[dict] = []  # newest first, each is one scored transaction


def score_transaction(payload: dict) -> dict:
    """Build, enrich, score, record, and return one transaction."""
    try:
        amount = float(payload.get("amount", 0))
    except (TypeError, ValueError):
        raise ValueError("amount must be a number")

    payee_id = payload.get("payee_id") or None
    tx = NormalizedTransaction(
        transaction_id=payload.get("transaction_id") or uuid.uuid4().hex[:8],
        amount=amount,
        payee_id=payee_id,
        timestamp=datetime.now(timezone.utc),
        sandbox_status=payload.get("sandbox_status") or "SUCCESS",
        is_first_payee=bool(payload.get("is_first_payee", False)),
    )
    tx = HISTORY.enrich(tx)
    result = classify(tx)
    HISTORY.record(tx)

    record = {
        "transaction_id": tx.transaction_id,
        "amount": tx.amount,
        "payee_id": tx.payee_id,
        "sandbox_status": tx.sandbox_status,
        "account_median_amount": tx.account_median_amount,
        "txns_last_60m": tx.txns_last_60m,
        "same_payee_small_txns_last_10m": tx.same_payee_small_txns_last_10m,
        "is_first_payee": tx.is_first_payee,
        "score": result.score,
        "decision": result.decision,
        "reason_codes": result.reason_codes,
        "top_reason": result.top_reason,
        # Plain-English sentence from the explainer. The score and
        # decision above are already final -- this only explains them.
        "explanation": explain(result, tx),
        "timestamp": tx.timestamp.isoformat() if tx.timestamp else None,
    }
    SCORED.insert(0, record)
    # Feedback loop: log the prediction (score, decision, reasons,
    # model version, timestamp). Logging never changes the score —
    # it is the record the loop measures against later, when a
    # confirmed outcome arrives.
    monitoring.LOG.log(
        model=config.MODEL_VERSION,
        transaction_id=tx.transaction_id,
        decision=result.decision,
        amount=tx.amount,
        score=result.score,
        reason_codes=result.reason_codes,
    )
    return record


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the console clean
        pass

    def _send_json(self, status: int, data) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # noqa: N802 - http.server naming
        # CORS preflight, for the GitHub Pages dashboard calling Render.
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_response(404)
            self.end_headers()
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - http.server naming
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send_file(FRONTEND / "index.html", "text/html")
        elif parsed.path == "/style.css":
            self._send_file(FRONTEND / "style.css", "text/css")
        elif parsed.path == "/app.js":
            self._send_file(FRONTEND / "app.js", "text/javascript")
        elif parsed.path == "/config.js":
            self._send_file(FRONTEND / "config.js", "text/javascript")
        elif parsed.path == "/health":
            self._send_json(200, {"ok": True})
        elif parsed.path == "/api/transactions":
            self._send_json(200, SCORED)
        elif parsed.path == "/api/offline-model":
            # The evaluated offline model: what it is, what it scored,
            # and the limits. Numbers come from the Step 1 evaluation
            # (~/workspace/paypal-ml-baseline/evaluation.md) — they are
            # reported here, not computed live.
            self._send_json(200, {
                "model": "logistic_regression",
                "trained_on": "Zenodo dataset (Fatah & Rashid, CC BY 4.0), "
                              "57,394 rows, 111 fraud (0.193%)",
                "features": ["log1p(amount)"] + [f"v{i}" for i in range(1, 29)],
                "threshold": offline_ml.load_model()["threshold"],
                "note": "OFFLINE ONLY. This model was trained on the Zenodo "
                        "dataset and never scores a live PayPal transaction — "
                        "a live transaction has no v1-v28 features. The live "
                        "rules engine above is the live decision-maker.",
                "evaluation": {
                    "method": "stratified 5-fold CV, out-of-fold; threshold "
                              "tuned on the PR curve (max F1), frozen for the "
                              "held-out test",
                    "amount_only": {"pr_auc": 0.2134, "f1": 0.354,
                                    "precision": 0.2632, "recall": 0.5405},
                    "amount_plus_v": {"pr_auc": 0.7415, "f1": 0.824,
                                      "precision": 0.7869, "recall": 0.8649},
                    "held_out_test_amount_plus_v": {"pr_auc": 0.7849,
                                                    "precision": 0.84,
                                                    "recall": 0.9545},
                    "baselines": {
                        "predict_all_legitimate": {"accuracy": 0.9981, "recall": 0.0},
                        "amount_rules": {"recall": 1.0, "precision": 0.007,
                                         "flagged_share": 0.275},
                    },
                },
                "limits": [
                    "Only 111 fraud rows — recall is roughly 0.79-0.92, not a point.",
                    "Labels come from the original system's decisions; missed fraud is plausibly recorded as not-fraud.",
                    "This is not PayPal data and not real customer banking data.",
                    "The 0.99 threshold is a calibration artifact of balanced class weights — at that threshold 79% of flagged rows are fraud, not 99%.",
                ],
            })
        elif parsed.path == "/api/offline-samples":
            self._send_json(200, offline_ml.load_samples())
        elif parsed.path == "/api/predictions":
            self._send_json(200, monitoring.LOG.recent(50))
        elif parsed.path == "/api/monitoring":
            self._send_json(200, monitoring.LOG.summary())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):  # noqa: N802 - http.server naming
        parsed = urlparse(self.path)
        if parsed.path == "/api/reset":
            HISTORY._txns.clear()
            SCORED.clear()
            monitoring.LOG.clear()
            self._send_json(200, {"ok": True})
            return
        if parsed.path == "/api/outcomes":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length) or b"{}")
                entry = monitoring.LOG.record_outcome(
                    str(payload.get("transaction_id") or ""),
                    str(payload.get("outcome") or ""),
                )
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            except (json.JSONDecodeError, TypeError):
                self._send_json(400, {"error": "body must be valid JSON"})
                return
            self._send_json(200, entry)
            return
        if parsed.path != "/api/score" and parsed.path != "/api/offline-score":
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            if parsed.path == "/api/offline-score":
                # Offline only: scores a Zenodo-style row (amount + v1-v28)
                # with the exported model. Never a PayPal transaction.
                try:
                    amount = float(payload.get("amount", 0))
                except (TypeError, ValueError):
                    raise ValueError("amount must be a number")
                v = payload.get("features") or {}
                record = offline_ml.score(amount, v)
                record["amount"] = amount
                # Log it too — the loop covers both models, each under
                # its own version, so their records never mix.
                monitoring.LOG.log(
                    model=monitoring.OFFLINE_MODEL_VERSION,
                    transaction_id=payload.get("transaction_id") or uuid.uuid4().hex[:8],
                    decision=record["decision"],
                    amount=amount,
                    probability=record["probability"],
                    reason_codes=[s["feature"] for s in record["top_signals"]],
                )
                self._send_json(200, record)
                return
            record = score_transaction(payload)
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except (json.JSONDecodeError, TypeError):
            self._send_json(400, {"error": "body must be valid JSON"})
            return
        self._send_json(200, record)


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Dashboard at http://localhost:{port}")
    print("Press Ctrl+C to stop. History resets on restart.")
    server.serve_forever()


if __name__ == "__main__":
    main()
