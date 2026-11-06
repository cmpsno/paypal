"""Unit tests for the classifier -- stdlib unittest only, no pytest needed.

Run from the repo root:
    python3 -m unittest discover -s backend/tests -v

Each test builds its own transaction with a small helper, so a
failing test tells you exactly which rule broke.
"""

import unittest

from backend.models import NormalizedTransaction
from backend.risk.classifier import classify


def tx(tx_id="tx-1", **overrides):
    """A clean baseline transaction; override only what the test needs."""
    base = {
        "transaction_id": tx_id,
        "amount": 50.0,
        "payee_id": "payee-known",
        "sandbox_status": "SUCCESS",
        "account_median_amount": 50.0,
        "txns_last_60m": 1,
        "is_first_payee": False,
    }
    base.update(overrides)
    return NormalizedTransaction(**base)


class TestClassifier(unittest.TestCase):
    def test_no_signals_scores_zero_and_releases(self):
        result = classify(tx())
        self.assertEqual(result.score, 0)
        self.assertEqual(result.decision, "RELEASE")
        self.assertEqual(result.reason_codes, [])
        self.assertIsNone(result.top_reason)

    def test_transaction_refused_alone_is_40_and_releases(self):
        # 40 alone is below the 50 bar -- intentional. One bad event
        # does not hold a payment; a pattern does.
        result = classify(tx(sandbox_status="TRANSACTION_REFUSED"))
        self.assertEqual(result.score, 40)
        self.assertEqual(result.decision, "RELEASE")
        self.assertEqual(result.reason_codes, ["TRANSACTION_REFUSED"])

    def test_other_sandbox_failure_alone_is_30_and_releases(self):
        result = classify(tx(sandbox_status="ORDER_ALREADY_CAPTURED"))
        self.assertEqual(result.score, 30)
        self.assertEqual(result.decision, "RELEASE")
        self.assertEqual(result.reason_codes, ["SANDBOX_FAILURE"])

    def test_instrument_declined_alone_is_50_and_holds(self):
        result = classify(tx(sandbox_status="INSTRUMENT_DECLINED"))
        self.assertEqual(result.score, 50)
        self.assertEqual(result.decision, "HOLD")
        self.assertEqual(result.reason_codes, ["INSTRUMENT_DECLINED"])
        self.assertEqual(result.top_reason, "INSTRUMENT_DECLINED")

    def test_pattern_new_payee_spike_velocity_is_60_and_holds(self):
        # 15 (new payee) + 25 (amount $400 > 3x median $100)
        # + 20 (3 txns in 60 min) = 60. No Sandbox failure needed.
        # Amount is $400 on purpose: over $500 would add +10 and
        # break the exact 60.
        result = classify(
            tx(
                amount=400.0,
                account_median_amount=100.0,
                txns_last_60m=3,
                is_first_payee=True,
            )
        )
        self.assertEqual(result.score, 60)
        self.assertEqual(result.decision, "HOLD")
        self.assertEqual(
            result.reason_codes, ["AMOUNT_SPIKE", "VELOCITY_BURST", "NEW_PAYEE"]
        )

    def test_score_is_capped_at_100(self):
        # Raw total would be 50 + 25 + 20 + 15 + 10 = 120.
        result = classify(
            tx(
                amount=600.0,
                account_median_amount=100.0,
                txns_last_60m=3,
                is_first_payee=True,
                sandbox_status="INSTRUMENT_DECLINED",
            )
        )
        self.assertEqual(result.score, 100)
        self.assertEqual(result.decision, "HOLD")
        self.assertIn("HIGH_AMOUNT", result.reason_codes)

    def test_same_transaction_scored_twice_is_identical(self):
        # Determinism: no randomness, no timestamps in the score.
        first = classify(tx(amount=400.0, txns_last_60m=3, is_first_payee=True))
        second = classify(tx(amount=400.0, txns_last_60m=3, is_first_payee=True))
        self.assertEqual(first, second)

    def test_structuring_fifth_small_txn_holds_at_50(self):
        # The Q1 gap: five $20 payments to the same payee in 10 min.
        # Each is under every amount threshold, so without this rule
        # the score would be 20 (velocity only) and RELEASE.
        # With it: 20 (velocity, 4 prior in 60 min) + 30 = 50 HOLD.
        result = classify(
            tx(
                amount=20.0,
                account_median_amount=50.0,
                txns_last_60m=4,
                same_payee_small_txns_last_10m=4,
            )
        )
        self.assertEqual(result.score, 50)
        self.assertEqual(result.decision, "HOLD")
        self.assertEqual(
            result.reason_codes, ["VELOCITY_BURST", "STRUCTURING"]
        )

    def test_structuring_needs_four_prior_small(self):
        # The 4th $20 (only 3 prior small same-payee) is not a
        # pattern yet: velocity only, 20, RELEASE.
        result = classify(
            tx(
                amount=20.0,
                account_median_amount=50.0,
                txns_last_60m=3,
                same_payee_small_txns_last_10m=3,
            )
        )
        self.assertEqual(result.score, 20)
        self.assertEqual(result.decision, "RELEASE")
        self.assertNotIn("STRUCTURING", result.reason_codes)

    def test_structuring_does_not_fire_on_large_amounts(self):
        # 5 x $100 to the same payee: velocity fires, but the
        # transactions are not small, so STRUCTURING does not.
        result = classify(
            tx(
                amount=100.0,
                account_median_amount=50.0,
                txns_last_60m=4,
                same_payee_small_txns_last_10m=4,
            )
        )
        self.assertEqual(result.score, 20)
        self.assertEqual(result.decision, "RELEASE")
        self.assertNotIn("STRUCTURING", result.reason_codes)

    def test_structuring_needs_known_payee(self):
        # Unknown payee (None) never fires STRUCTURING, same guard
        # as NEW_PAYEE -- even with 4 prior small transactions.
        result = classify(
            tx(
                amount=20.0,
                payee_id=None,
                account_median_amount=50.0,
                txns_last_60m=4,
                same_payee_small_txns_last_10m=4,
            )
        )
        self.assertEqual(result.score, 20)
        self.assertEqual(result.decision, "RELEASE")
        self.assertNotIn("STRUCTURING", result.reason_codes)

    def test_unknown_payee_gets_no_first_payee_points(self):
        # payee_id is Optional. If it is None, NEW_PAYEE (+15)
        # must NOT fire, even if is_first_payee was passed as True.
        # Without that guard this would score 15; with it, 0.
        result = classify(tx(payee_id=None, is_first_payee=True))
        self.assertEqual(result.score, 0)
        self.assertEqual(result.decision, "RELEASE")
        self.assertNotIn("NEW_PAYEE", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
