"""Tests for the AI explanation layer (backend/risk/explainer.py).

The contract under test:
  - The explanation cites exactly the reasons the classifier gave --
    never more, never fewer, never a different score or decision.
  - Same result -> same sentence (deterministic template).
  - An LLM rewrite may only reword; if it fails or returns nothing,
    the template sentence is used. The decision never changes.
"""

import unittest

from backend.models import NormalizedTransaction
from backend.risk.classifier import classify
from backend.risk.explainer import explain


def _tx(**kwargs):
    defaults = dict(
        transaction_id="t1",
        amount=50.0,
        payee_id="payee-known",
        sandbox_status="SUCCESS",
    )
    defaults.update(kwargs)
    return NormalizedTransaction(**defaults)


def _explained(**kwargs):
    tx = _tx(**kwargs)
    return tx, classify(tx), explain(classify(tx), tx)


class TestExplainer(unittest.TestCase):
    def test_clean_has_no_reasons(self):
        _, result, sentence = _explained()
        self.assertEqual(result.score, 0)
        self.assertEqual(result.decision, "RELEASE")
        self.assertIn("Released at 0/100", sentence)
        self.assertIn("no risk signals", sentence)

    def test_refused_alone_released_with_reason(self):
        _, result, sentence = _explained(sandbox_status="TRANSACTION_REFUSED")
        self.assertEqual((result.score, result.decision), (40, "RELEASE"))
        self.assertIn("transaction was refused (+40)", sentence)
        self.assertIn("Released at 40/100", sentence)

    def test_declined_held_with_reason(self):
        _, result, sentence = _explained(sandbox_status="INSTRUMENT_DECLINED")
        self.assertEqual((result.score, result.decision), (50, "HOLD"))
        self.assertIn("payment instrument was declined (+50)", sentence)
        self.assertIn("Held at 50/100", sentence)

    def test_pattern_lists_all_three_reasons(self):
        _, result, sentence = _explained(
            amount=400.0,
            payee_id="payee-new",
            account_median_amount=100.0,
            txns_last_60m=3,
            is_first_payee=True,
        )
        self.assertEqual((result.score, result.decision), (60, "HOLD"))
        for fragment in (
            "more than 3x the account median (+25)",
            "3 or more transactions arrived within 60 minutes (+20)",
            "first-time payee (+15)",
        ):
            self.assertIn(fragment, sentence)

    def test_capped_lists_every_reason(self):
        _, result, sentence = _explained(
            amount=600.0,
            payee_id="payee-new",
            sandbox_status="INSTRUMENT_DECLINED",
            account_median_amount=100.0,
            txns_last_60m=3,
            is_first_payee=True,
        )
        self.assertEqual((result.score, result.decision), (100, "HOLD"))
        self.assertIn("Held at 100/100", sentence)
        for code_word in ("declined", "3x", "60 minutes", "first-time", "$500"):
            self.assertIn(code_word, sentence)

    def test_unknown_payee_never_mentioned(self):
        _, result, sentence = _explained(
            amount=400.0,
            payee_id=None,
            account_median_amount=100.0,
            txns_last_60m=3,
            is_first_payee=True,  # must not count without a payee_id
        )
        self.assertEqual(result.score, 45)  # 25 + 20, no NEW_PAYEE points
        self.assertNotIn("first-time payee", sentence)

    def test_explainer_never_changes_result(self):
        tx = _tx(sandbox_status="INSTRUMENT_DECLINED")
        before = classify(tx)
        explain(before, tx)
        after = classify(tx)
        self.assertEqual(before, after)

    def test_deterministic(self):
        _, result, first = _explained(sandbox_status="INSTRUMENT_DECLINED")
        tx = _tx(sandbox_status="INSTRUMENT_DECLINED")
        self.assertEqual(first, explain(classify(tx), tx))

    def test_llm_rewrite_may_reword_only(self):
        tx = _tx(sandbox_status="INSTRUMENT_DECLINED")
        result = classify(tx)
        rewritten = explain(
            result, tx,
            llm_rewrite=lambda template, r: "The card was declined, so we held it.",
        )
        self.assertEqual(rewritten, "The card was declined, so we held it.")
        # The decision itself is untouched by the rewrite.
        self.assertEqual((result.score, result.decision), (50, "HOLD"))

    def test_llm_failure_falls_back_to_template(self):
        tx = _tx(sandbox_status="INSTRUMENT_DECLINED")
        result = classify(tx)
        template = explain(result, tx)
        self.assertEqual(
            explain(result, tx, llm_rewrite=lambda t, r: (_ for _ in ()).throw(RuntimeError("no key"))),
            template,
        )
        self.assertEqual(explain(result, tx, llm_rewrite=lambda t, r: "   "), template)
        self.assertEqual(explain(result, tx, llm_rewrite=lambda t, r: None), template)


if __name__ == "__main__":
    unittest.main()
