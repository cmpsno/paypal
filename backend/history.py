"""Demo-session history — the fields PayPal does NOT hand us.

The classifier needs three history-derived fields:
  - account_median_amount (for the >3x median spike signal)
  - txns_last_60m (for the velocity signal)
  - is_first_payee (for the new-payee signal)

PayPal does not return any of those. This module computes them
from the transactions already seen in this demo session, in
memory only — no database, nothing persisted.

``enrich()`` fills those fields on a NormalizedTransaction
*before* it is scored, then records the transaction so the next
one sees it. Call it once per transaction, in order.
"""

from __future__ import annotations

import statistics
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from backend.models import NormalizedTransaction


class TransactionHistory:
    """In-memory list of transactions seen so far this session."""

    def __init__(self) -> None:
        self._txns: list[NormalizedTransaction] = []

    def __len__(self) -> int:
        return len(self._txns)

    def record(self, tx: NormalizedTransaction) -> None:
        self._txns.append(tx)

    def median_amount(self) -> float | None:
        """Median amount of prior transactions, or None if none yet."""
        if not self._txns:
            return None
        return statistics.median(tx.amount for tx in self._txns)

    def txns_last_60m(self, now: datetime | None = None) -> int:
        """Prior transactions in the last 60 minutes.

        Transactions without a timestamp are ignored here — they
        cannot be placed in a time window, so they score 0 for
        velocity rather than being guessed at.
        """
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=60)
        return sum(
            1
            for tx in self._txns
            if tx.timestamp is not None and tx.timestamp >= cutoff
        )

    def is_first_payee(self, payee_id: str | None) -> bool:
        """True if no prior transaction went to this payee.

        Unknown payee (None) is never a "first" payee — the
        classifier already refuses NEW_PAYEE points for None, and
        this keeps that rule in one place.
        """
        if payee_id is None:
            return False
        return all(tx.payee_id != payee_id for tx in self._txns)

    def enrich(
        self, tx: NormalizedTransaction, now: datetime | None = None
    ) -> NormalizedTransaction:
        """Fill the history fields on ``tx`` from prior transactions.

        Does not record ``tx`` itself — the caller records it after
        scoring, so a transaction never counts toward its own median
        or velocity.
        """
        return replace(
            tx,
            account_median_amount=self.median_amount(),
            txns_last_60m=self.txns_last_60m(now),
            is_first_payee=self.is_first_payee(tx.payee_id),
        )
