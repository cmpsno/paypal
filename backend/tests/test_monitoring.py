"""Tests for the feedback loop (backend/monitoring.py + its wiring).

The contract under test:
  - Every prediction is logged with model version, decision, score,
    reasons, amount, and timestamp. Logging never changes a score.
  - Outcomes attach to the most recent un-outcomed prediction for a
    transaction; unknown ids, invalid outcomes, and double-recording
    are all errors.
  - Precision/recall exist ONLY on the confirmed subset. With zero
    confirmed outcomes they are None, not 0 or 1.
  - Drift compares recent predictions against all-time.
  - POST /api/score actually logs (wiring, not just the module).
"""

import unittest

from backend import monitoring
from backend.app import score_transaction


class TestPredictionLog(unittest.TestCase):
    def setUp(self):
        self.log = monitoring.PredictionLog()

    def test_log_records_prediction(self):
        e = self.log.log("rules-1.0", "tx-1", "HOLD", amount=400.0,
                         score=60, reason_codes=["AMOUNT_SPIKE"])
        self.assertEqual(e["model"], "rules-1.0")
        self.assertEqual(e["decision"], "HOLD")
        self.assertEqual(e["score"], 60)
        self.assertIsNone(e["outcome"])
        self.assertIsNotNone(e["timestamp"])
        self.assertEqual(len(self.log), 1)

    def test_recent_is_newest_first(self):
        self.log.log("rules-1.0", "tx-1", "RELEASE", amount=50.0, score=0)
        self.log.log("rules-1.0", "tx-2", "HOLD", amount=50.0, score=50)
        self.assertEqual(
            [e["transaction_id"] for e in self.log.recent(2)], ["tx-2", "tx-1"]
        )

    def test_outcome_attaches_to_most_recent(self):
        self.log.log("rules-1.0", "tx-1", "HOLD", amount=50.0, score=50)
        self.log.log("rules-1.0", "tx-1", "RELEASE", amount=50.0, score=0)
        out = self.log.record_outcome("tx-1", "fraud")
        self.assertEqual(out["decision"], "RELEASE")
        self.assertEqual(out["outcome"], "fraud")
        self.assertIsNotNone(out["outcome_recorded_at"])
        # The older prediction for the same id is still un-outcomed.
        self.assertIsNone(self.log._entries[0]["outcome"])

    def test_outcome_unknown_id_is_an_error(self):
        with self.assertRaises(ValueError):
            self.log.record_outcome("nope", "fraud")

    def test_outcome_invalid_value_is_an_error(self):
        self.log.log("rules-1.0", "tx-1", "HOLD", amount=50.0, score=50)
        with self.assertRaises(ValueError):
            self.log.record_outcome("tx-1", "maybe")

    def test_outcome_twice_is_an_error(self):
        self.log.log("rules-1.0", "tx-1", "HOLD", amount=50.0, score=50)
        self.log.record_outcome("tx-1", "fraud")
        with self.assertRaises(ValueError):
            self.log.record_outcome("tx-1", "legitimate")

    def test_no_confirmed_means_no_metrics(self):
        self.log.log("rules-1.0", "tx-1", "HOLD", amount=50.0, score=50)
        summary = self.log.summary()
        self.assertIsNone(summary["confirmed_outcomes"])
        self.assertIn("No confirmed outcomes yet", summary["confirmed_note"])
        self.assertEqual(summary["total_predictions"], 1)
        self.assertEqual(summary["hold_or_flag_rate"], 1.0)

    def test_confirmed_metrics_are_computed(self):
        # 2 HOLD + fraud (TP), 1 HOLD + legitimate (FP),
        # 1 RELEASE + fraud (FN) -> precision 2/3, recall 2/3.
        cases = [("HOLD", "fraud"), ("HOLD", "fraud"),
                 ("HOLD", "legitimate"), ("RELEASE", "fraud")]
        for i, (decision, outcome) in enumerate(cases):
            self.log.log("rules-1.0", f"tx-{i}", decision,
                         amount=50.0, score=50 if decision == "HOLD" else 0)
            self.log.record_outcome(f"tx-{i}", outcome)
        m = self.log.summary()["confirmed_outcomes"]
        self.assertEqual((m["tp"], m["fp"], m["fn"]), (2, 1, 1))
        self.assertAlmostEqual(m["precision"], 2 / 3, places=4)
        self.assertAlmostEqual(m["recall"], 2 / 3, places=4)

    def test_drift_compares_recent_to_all_time(self):
        for i in range(25):
            self.log.log("rules-1.0", f"tx-{i}", "RELEASE",
                         amount=50.0, score=0)
        self.log.log("rules-1.0", "tx-big", "HOLD", amount=5000.0, score=60)
        drift = self.log.summary()["drift"]
        self.assertEqual(drift["median_amount_all"], 50.0)
        self.assertEqual(drift["median_amount_last_20"], 50.0)
        self.assertIn("signal to investigate", drift["note"])

    def test_clear_empties_the_log(self):
        self.log.log("rules-1.0", "tx-1", "HOLD", amount=50.0, score=50)
        self.log.clear()
        self.assertEqual(len(self.log), 0)
        self.assertEqual(self.log.summary()["total_predictions"], 0)


class TestScoreLogsPredictions(unittest.TestCase):
    def test_api_score_writes_to_the_log(self):
        from backend.app import HISTORY
        from backend.models import NormalizedTransaction

        monitoring.LOG.clear()
        HISTORY._txns.clear()
        # Seed the shared demo history so payee-known is NOT a first
        # payee — otherwise the score would be 65 (50 + 15) instead
        # of 50, depending on test order. The point of this test is
        # the logging, not the scoring.
        HISTORY.record(NormalizedTransaction(
            transaction_id="seed", amount=50.0, payee_id="payee-known",
        ))
        record = score_transaction({
            "amount": 50, "payee_id": "payee-known",
            "sandbox_status": "INSTRUMENT_DECLINED",
        })
        self.assertEqual(len(monitoring.LOG), 1)
        entry = monitoring.LOG.recent(1)[0]
        self.assertEqual(entry["transaction_id"], record["transaction_id"])
        self.assertEqual(entry["model"], "rules-1.0")
        self.assertEqual(entry["decision"], "HOLD")
        self.assertEqual(entry["score"], 50)
        self.assertEqual(entry["reason_codes"], ["INSTRUMENT_DECLINED"])
        monitoring.LOG.clear()
        HISTORY._txns.clear()


if __name__ == "__main__":
    unittest.main()
