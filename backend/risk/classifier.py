"""The risk classifier -- the part that makes the decision.

One job, one function: ``classify(transaction)``.

It takes a NormalizedTransaction and returns a score (0-100),
a decision (HOLD or RELEASE), and the reason codes that explain it.

Separation of responsibilities, on purpose:
  - This module MAKES the financial risk decision.
  - It does NOT talk to PayPal, read files, or call any AI.
  - A separate explainer module (built later) will turn the
    reason codes into a plain-English sentence. The AI explains
    the decision; it never makes it, and it never changes the score.

Pure function: same input -> same output, every time.
No randomness, no timestamps in the score, no network calls.
That is what makes it unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.models import NormalizedTransaction
from backend.risk import config


@dataclass
class ClassificationResult:
    transaction_id: str
    score: int
    decision: str  # "HOLD" or "RELEASE"
    reason_codes: list[str] = field(default_factory=list)

    @property
    def top_reason(self) -> str | None:
        """The first (highest-priority) reason, or None if clean."""
        return self.reason_codes[0] if self.reason_codes else None


def classify(tx: NormalizedTransaction) -> ClassificationResult:
    """Score one transaction. Start at 0, add points, cap at 100."""
    score = 0
    reason_codes: list[str] = []

    # --- 1. Sandbox failure (at most one of these fires) ---
    # The order matters: the two named codes beat the generic one.
    if tx.sandbox_status == "INSTRUMENT_DECLINED":
        score += config.POINTS["INSTRUMENT_DECLINED"]
        reason_codes.append("INSTRUMENT_DECLINED")
    elif tx.sandbox_status == "TRANSACTION_REFUSED":
        score += config.POINTS["TRANSACTION_REFUSED"]
        reason_codes.append("TRANSACTION_REFUSED")
    elif tx.sandbox_status not in ("SUCCESS", "", None):
        # Any other failure / error result from the Sandbox.
        score += config.POINTS["SANDBOX_FAILURE"]
        reason_codes.append("SANDBOX_FAILURE")

    # --- 2. Amount spike: more than 3x the account's median ---
    # Only if we actually know the median. Unknown median = 0 points.
    if (
        tx.account_median_amount is not None
        and tx.account_median_amount > 0
        and tx.amount > config.AMOUNT_SPIKE_MULTIPLIER * tx.account_median_amount
    ):
        score += config.POINTS["AMOUNT_SPIKE"]
        reason_codes.append("AMOUNT_SPIKE")

    # --- 3. Velocity burst: 3+ transactions in the last 60 minutes ---
    if tx.txns_last_60m >= config.VELOCITY_MIN_TXNS:
        score += config.POINTS["VELOCITY_BURST"]
        reason_codes.append("VELOCITY_BURST")

    # --- 4. First-time payee ---
    # Correction carried into the build: payee_id is Optional.
    # If we don't know who the payee is, we do NOT award these
    # points, even if is_first_payee was passed in as True.
    if tx.payee_id is not None and tx.is_first_payee:
        score += config.POINTS["NEW_PAYEE"]
        reason_codes.append("NEW_PAYEE")

    # --- 5. High absolute amount: over $500 ---
    if tx.amount > config.HIGH_AMOUNT_THRESHOLD:
        score += config.POINTS["HIGH_AMOUNT"]
        reason_codes.append("HIGH_AMOUNT")

    # Cap, then decide. One rule, no hidden branch.
    score = min(score, config.MAX_SCORE)
    decision = "HOLD" if score >= config.HOLD_THRESHOLD else "RELEASE"

    return ClassificationResult(
        transaction_id=tx.transaction_id,
        score=score,
        decision=decision,
        reason_codes=reason_codes,
    )
