"""The feedback loop — prediction log, confirmed outcomes, monitoring.

This is the process that tells you when a model is no longer
trustworthy. It is deliberately small and honest:

  - Log every prediction: model version, timestamp, decision, score /
    probability, reason codes, amount. Logging never changes a score.
  - Outcomes arrive later. Somebody confirms a transaction was fraud
    or legitimate — days or weeks later in real life — and records it
    with POST /api/outcomes. Until then, true precision/recall cannot
    be measured, and this module says so instead of inventing them.
  - Monitoring reports what can be measured now (volumes, hold rate,
    reason-code counts, drift signals) and precision/recall only on
    the confirmed subset, when one exists.

Storage is in-memory, like the demo-session history: it resets when
the server restarts. That is a stated demo limit, not a hidden one —
a production log would be a database. Nothing here is a database.

Drift: the module compares recent predictions (last 20) against all
predictions so far — median amount, mean score, hold rate. A
difference is a signal to investigate, not a verdict. Drift can be
watched before any outcomes arrive, which is exactly why it is the
early warning.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone

# Model versions, recorded on every prediction. Bump the rules version
# in backend/risk/config.py when weights, thresholds, or rules change;
# the offline model version lives with its exported weights.
OFFLINE_MODEL_VERSION = "ml-lr-1.0"

VALID_OUTCOMES = ("fraud", "legitimate")

# A prediction is "positive" (flagged) when its decision is HOLD or FLAG.
POSITIVE_DECISIONS = ("HOLD", "FLAG")


class PredictionLog:
    """In-memory, append-only log of predictions and their outcomes."""

    def __init__(self) -> None:
        self._entries: list[dict] = []

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()

    def log(
        self,
        model: str,
        transaction_id: str,
        decision: str,
        amount: float | None = None,
        score: int | None = None,
        probability: float | None = None,
        reason_codes: list[str] | None = None,
    ) -> dict:
        """Record one prediction. Returns the entry."""
        entry = {
            "transaction_id": transaction_id,
            "model": model,
            "decision": decision,
            "score": score,
            "probability": probability,
            "reason_codes": list(reason_codes or []),
            "amount": amount,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "outcome": None,  # filled in later, when confirmed
            "outcome_recorded_at": None,
        }
        self._entries.append(entry)
        return entry

    def record_outcome(self, transaction_id: str, outcome: str) -> dict:
        """Attach a confirmed outcome to the most recent prediction
        for this transaction that has none yet.

        Raises ValueError for an unknown transaction, an invalid
        outcome, or a transaction whose outcome is already recorded.
        """
        if outcome not in VALID_OUTCOMES:
            raise ValueError(f"outcome must be one of {VALID_OUTCOMES}")
        for entry in reversed(self._entries):
            if entry["transaction_id"] == transaction_id:
                if entry["outcome"] is not None:
                    raise ValueError(
                        f"outcome already recorded for {transaction_id}"
                    )
                entry["outcome"] = outcome
                entry["outcome_recorded_at"] = datetime.now(timezone.utc).isoformat()
                return entry
        raise ValueError(f"unknown transaction_id: {transaction_id}")

    def recent(self, n: int = 10) -> list[dict]:
        """Newest first."""
        return list(reversed(self._entries[-n:]))

    def summary(self) -> dict:
        """What can be measured now — and what cannot, yet."""
        total = len(self._entries)
        confirmed = [e for e in self._entries if e["outcome"] is not None]

        # Precision/recall only on the confirmed subset. With zero
        # confirmed outcomes there is nothing to measure, and the
        # fields say so (None) instead of reporting 0 or 1.
        confirmed_metrics = None
        if confirmed:
            tp = sum(1 for e in confirmed if e["decision"] in POSITIVE_DECISIONS and e["outcome"] == "fraud")
            fp = sum(1 for e in confirmed if e["decision"] in POSITIVE_DECISIONS and e["outcome"] == "legitimate")
            fn = sum(1 for e in confirmed if e["decision"] not in POSITIVE_DECISIONS and e["outcome"] == "fraud")
            precision = tp / (tp + fp) if (tp + fp) else None
            recall = tp / (tp + fn) if (tp + fn) else None
            f1 = (
                2 * precision * recall / (precision + recall)
                if precision is not None and recall is not None and (precision + recall)
                else None
            )
            confirmed_metrics = {
                "n": len(confirmed),
                "fraud": sum(1 for e in confirmed if e["outcome"] == "fraud"),
                "legitimate": sum(1 for e in confirmed if e["outcome"] == "legitimate"),
                "tp": tp, "fp": fp, "fn": fn,
                "precision": round(precision, 4) if precision is not None else None,
                "recall": round(recall, 4) if recall is not None else None,
                "f1": round(f1, 4) if f1 is not None else None,
            }

        def _median_amount(entries: list[dict]) -> float | None:
            amounts = [e["amount"] for e in entries if e["amount"] is not None]
            return round(statistics.median(amounts), 2) if amounts else None

        def _hold_rate(entries: list[dict]) -> float | None:
            if not entries:
                return None
            return round(
                sum(1 for e in entries if e["decision"] in POSITIVE_DECISIONS) / len(entries), 4
            )

        recent = self._entries[-20:]
        return {
            "storage": "in-memory — resets when the server restarts",
            "total_predictions": total,
            "by_model": {
                model: sum(1 for e in self._entries if e["model"] == model)
                for model in sorted({e["model"] for e in self._entries})
            },
            "hold_or_flag_rate": _hold_rate(self._entries),
            "reason_code_counts": {
                code: sum(1 for e in self._entries if code in e["reason_codes"])
                for code in sorted({c for e in self._entries for c in e["reason_codes"]})
            },
            "confirmed_outcomes": confirmed_metrics,
            "confirmed_note": (
                "No confirmed outcomes yet — true precision/recall cannot "
                "be measured until outcomes arrive. Record one with "
                "POST /api/outcomes."
                if not confirmed
                else f"{len(confirmed)} confirmed outcome(s) recorded."
            ),
            "drift": {
                "median_amount_all": _median_amount(self._entries),
                "median_amount_last_20": _median_amount(recent),
                "hold_or_flag_rate_all": _hold_rate(self._entries),
                "hold_or_flag_rate_last_20": _hold_rate(recent),
                "note": "Compare last-20 against all-time. A large move is a "
                        "signal to investigate, not a verdict — and it can be "
                        "watched before any outcomes arrive.",
            },
        }


# One log for the whole server process.
LOG = PredictionLog()
