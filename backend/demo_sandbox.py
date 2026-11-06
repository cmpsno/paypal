"""End-to-end Sandbox demo, one transaction at a time.

Usage:
  PAYPAL_CLIENT_ID=... PAYPAL_CLIENT_SECRET=... \
    python3 -m backend.demo_sandbox --amount 620 --mock INSTRUMENT_DECLINED

Without credentials it prints exactly where to get them and exits
— it never attempts a network call without them, and it never
prints the secret.

What it does, in order:
  1. OAuth token (Sandbox)
  2. Create a CAPTURE order for --amount
  3. Capture it, with the PayPal-Mock-Response header when --mock
     is given (INSTRUMENT_DECLINED or TRANSACTION_REFUSED)
  4. Map the response to a NormalizedTransaction, enrich it from
     demo-session history, score it with classify(), print the result

A real COMPLETED capture needs buyer approval first, so a plain
run with no --mock will come back as an unapproved-order failure
and score as an "other Sandbox failure" (+30) — that is the
honest result, not a bug. The --mock path is the reproducible
demo for the two named failure codes.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from backend.history import TransactionHistory
from backend.models import NormalizedTransaction
from backend.paypal_client import (
    amount_from_response,
    capture_order,
    create_order,
    get_access_token,
    payee_id_from_response,
    sandbox_status_from_response,
)
from backend.risk.classifier import classify


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score one Sandbox transaction.")
    parser.add_argument("--amount", type=float, default=100.0)
    parser.add_argument(
        "--mock",
        choices=["INSTRUMENT_DECLINED", "TRANSACTION_REFUSED"],
        default=None,
        help="PayPal negative-testing code to force on capture.",
    )
    args = parser.parse_args(argv)

    client_id = os.environ.get("PAYPAL_CLIENT_ID")
    client_secret = os.environ.get("PAYPAL_CLIENT_SECRET")
    if not client_id or not client_secret:
        print(
            "Missing Sandbox credentials.\n"
            "  1. Go to https://developer.paypal.com/dashboard/applications/sandbox\n"
            "  2. Create/open a Sandbox app, copy its Client ID and Secret.\n"
            "  3. Run again with PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET set.\n"
            "Never commit those values — .env only, never in the repo."
        )
        return 2

    token = get_access_token(client_id, client_secret)
    order = create_order(token, args.amount)
    order_id = order.get("id")
    if not order_id:
        print(f"Order creation failed: {order}")
        return 1

    capture = capture_order(token, order_id, mock_code=args.mock)
    status = sandbox_status_from_response(capture)
    amount = amount_from_response(capture) or args.amount

    history = TransactionHistory()
    tx = NormalizedTransaction(
        transaction_id=order_id,
        amount=amount,
        payee_id=payee_id_from_response(capture),
        timestamp=datetime.now(timezone.utc),
        sandbox_status=status,
    )
    tx = history.enrich(tx)
    result = classify(tx)
    history.record(tx)

    print(f"order: {order_id}")
    print(f"sandbox_status: {status}")
    print(f"score: {result.score}  decision: {result.decision}")
    print(f"reason_codes: {', '.join(result.reason_codes) or '(none)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
