"""Dashboard server — one process, stdlib only, no new dependency.

Run from the repo root:
    python3 -m backend.app
Then open http://localhost:8000

What it does:
  GET  /                    -> the dashboard (frontend/index.html)
  GET  /style.css, /app.js  -> dashboard assets
  GET  /api/transactions    -> every transaction scored so far, newest first
  POST /api/score           -> score one transaction, record it, return it
  POST /api/reset           -> clear demo-session history (for repeatable demos)

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
from backend.models import NormalizedTransaction
from backend.risk.classifier import classify

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
        "is_first_payee": tx.is_first_payee,
        "score": result.score,
        "decision": result.decision,
        "reason_codes": result.reason_codes,
        "top_reason": result.top_reason,
        "timestamp": tx.timestamp.isoformat() if tx.timestamp else None,
    }
    SCORED.insert(0, record)
    return record


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the console clean
        pass

    def _send_json(self, status: int, data) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
        elif parsed.path == "/api/transactions":
            self._send_json(200, SCORED)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):  # noqa: N802 - http.server naming
        parsed = urlparse(self.path)
        if parsed.path == "/api/reset":
            HISTORY._txns.clear()
            SCORED.clear()
            self._send_json(200, {"ok": True})
            return
        if parsed.path != "/api/score":
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
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
