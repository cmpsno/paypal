"""Tests for demo-session history — the fields PayPal doesn't give us."""

import unittest
from datetime import datetime, timedelta, timezone

from backend.history import TransactionHistory
from backend.models import NormalizedTransaction


def _tx(amount, payee=None, when=None):
    return NormalizedTransaction(
        transaction_id=f"tx-{amount}-{payee}",
        amount=amount,
        payee_id=payee,
        timestamp=when or datetime.now(timezone.utc),
    )


class TestHistory(unittest.TestCase):
    def test_empty_history_is_unknown(self):
        h = TransactionHistory()
        self.assertIsNone(h.median_amount())
        self.assertEqual(h.txns_last_60m(), 0)
        # Empty history: any named payee is a first payee.
        self.assertTrue(h.is_first_payee("anyone"))
        # Unknown payee (None) is never a first payee.
        self.assertFalse(h.is_first_payee(None))

    def test_median_of_prior_transactions(self):
        h = TransactionHistory()
        for amount in (50.0, 100.0, 150.0):
            h.record(_tx(amount))
        self.assertEqual(h.median_amount(), 100.0)

    def test_velocity_counts_only_last_60m(self):
        now = datetime.now(timezone.utc)
        h = TransactionHistory()
        h.record(_tx(10.0, when=now - timedelta(minutes=30)))
        h.record(_tx(10.0, when=now - timedelta(minutes=59)))
        h.record(_tx(10.0, when=now - timedelta(minutes=61)))
        self.assertEqual(h.txns_last_60m(now), 2)

    def test_first_payee_then_repeat(self):
        h = TransactionHistory()
        self.assertTrue(h.is_first_payee("payee-a"))
        h.record(_tx(10.0, payee="payee-a"))
        self.assertFalse(h.is_first_payee("payee-a"))
        self.assertTrue(h.is_first_payee("payee-b"))

    def test_structuring_counts_only_small_same_payee_recent(self):
        now = datetime.now(timezone.utc)
        h = TransactionHistory()
        # 4 small $20 to payee-a in the last 10 min -> counts.
        for minutes_ago in (1, 3, 5, 9):
            h.record(_tx(20.0, payee="payee-a", when=now - timedelta(minutes=minutes_ago)))
        # A $100 to payee-a: too big to count as small.
        h.record(_tx(100.0, payee="payee-a", when=now - timedelta(minutes=2)))
        # A $20 to a different payee: wrong payee.
        h.record(_tx(20.0, payee="payee-b", when=now - timedelta(minutes=2)))
        # A $20 to payee-a 11 minutes ago: outside the window.
        h.record(_tx(20.0, payee="payee-a", when=now - timedelta(minutes=11)))
        self.assertEqual(h.same_payee_small_txns_last_10m("payee-a", now), 4)
        self.assertEqual(h.same_payee_small_txns_last_10m("payee-b", now), 1)
        self.assertEqual(h.same_payee_small_txns_last_10m(None, now), 0)

    def test_enrich_fills_structuring_count(self):
        now = datetime.now(timezone.utc)
        h = TransactionHistory()
        for minutes_ago in (1, 4, 7, 9):
            h.record(_tx(20.0, payee="payee-a", when=now - timedelta(minutes=minutes_ago)))
        enriched = h.enrich(_tx(20.0, payee="payee-a", when=now), now)
        self.assertEqual(enriched.same_payee_small_txns_last_10m, 4)

    def test_unknown_payee_is_never_first(self):
        h = TransactionHistory()
        self.assertFalse(h.is_first_payee(None))

    def test_enrich_does_not_count_itself(self):
        h = TransactionHistory()
        h.record(_tx(100.0, payee="payee-a"))
        tx = _tx(400.0, payee="payee-b")
        enriched = h.enrich(tx)
        # Median is of the one prior txn only, not including this one.
        self.assertEqual(enriched.account_median_amount, 100.0)
        self.assertTrue(enriched.is_first_payee)
        self.assertEqual(len(h), 1)

    def test_enrich_then_record_feeds_next_transaction(self):
        h = TransactionHistory()
        tx1 = h.enrich(_tx(100.0, payee="payee-a"))
        h.record(tx1)
        tx2 = h.enrich(_tx(100.0, payee="payee-a"))
        self.assertFalse(tx2.is_first_payee)
        self.assertEqual(tx2.account_median_amount, 100.0)


if __name__ == "__main__":
    unittest.main()
