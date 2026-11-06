"""Normalized transaction model.

This is the one shape every part of the product agrees on.
The classifier only ever sees this shape -- never a raw PayPal
response, never a row from the offline dataset.

Later, the PayPal Sandbox adapter will build a
NormalizedTransaction from a Sandbox order/capture response.
The offline evaluation code will build a *different*, smaller
shape for the Zenodo CSV. The two sources stay separate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class NormalizedTransaction:
    """One transaction, cleaned up for scoring.

    Fields the classifier actually uses:
      amount, payee_id, sandbox_status, account_median_amount,
      txns_last_60m, is_first_payee.

    Fields carried along for display / debugging:
      transaction_id, currency, timestamp.
    """

    transaction_id: str
    amount: float  # USD

    currency: str = "USD"

    # Who got paid. Optional on purpose: if PayPal / the feed does
    # not give us a payee, this is None -- and the classifier must
    # NOT award first-time-payee points (see classifier.py).
    payee_id: Optional[str] = None

    timestamp: Optional[datetime] = None

    # SUCCESS, INSTRUMENT_DECLINED, TRANSACTION_REFUSED, or any
    # other failure string. Anything that is not SUCCESS and not
    # one of the two named codes counts as "other Sandbox failure".
    sandbox_status: str = "SUCCESS"

    # History, computed by the backend from transactions it has
    # already seen in this demo session -- NOT handed to us by PayPal.
    # None means "we don't know yet", which scores 0 for that signal.
    account_median_amount: Optional[float] = None

    # How many transactions this account made in the last 60 minutes.
    txns_last_60m: int = 0

    # True only if this is the first transaction to this payee.
    # Only counts when payee_id is set (see above).
    is_first_payee: bool = False
