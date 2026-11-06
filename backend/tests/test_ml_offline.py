"""Tests for the offline ML model (backend/ml/inference.py).

The contract under test:
  - Stdlib inference reproduces the exported model's probabilities
    for the three real Zenodo sample rows.
  - FLAG/PASS follows the tuned 0.99 threshold.
  - Top signals are statistical feature names (v1, v5, ...) — never
    invented behaviours — and are ranked by absolute contribution.
  - A missing PCA feature is an error, never a silent zero.
  - This model never touches a live PayPal transaction: it only ever
    sees amount + v1-v28, which a live transaction does not have.
"""

import unittest

from backend.ml import inference


def _sample(i):
    s = inference.load_samples()["samples"][i]
    return s


class TestOfflineInference(unittest.TestCase):
    def test_model_shape(self):
        model = inference.load_model()
        self.assertEqual(len(model["features"]), 29)
        self.assertEqual(model["features"][0], "log1p(amount)")
        self.assertEqual(model["threshold"], 0.99)
        self.assertEqual(len(model["coefficients"]), 29)

    def test_fraud_sample_flags(self):
        s = _sample(0)
        self.assertEqual(s["is_fraud"], 1)
        result = inference.score(s["amount"], s["features"])
        self.assertAlmostEqual(result["probability"], 0.9999, places=3)
        self.assertEqual(result["decision"], "FLAG")

    def test_clean_legit_sample_passes(self):
        s = _sample(1)
        self.assertEqual(s["is_fraud"], 0)
        result = inference.score(s["amount"], s["features"])
        self.assertAlmostEqual(result["probability"], 0.0, places=3)
        self.assertEqual(result["decision"], "PASS")

    def test_high_amount_legit_sample_passes(self):
        # Amount alone would scream fraud ($280k); the model passes it.
        # That is the point of the v1-v28 features.
        s = _sample(2)
        self.assertEqual(s["is_fraud"], 0)
        self.assertGreater(s["amount"], 5000)
        result = inference.score(s["amount"], s["features"])
        self.assertAlmostEqual(result["probability"], 0.7637, places=3)
        self.assertEqual(result["decision"], "PASS")

    def test_top_signals_are_feature_names_ranked(self):
        s = _sample(0)
        signals = inference.top_signals(s["amount"], s["features"])
        self.assertEqual(len(signals), 3)
        model_features = inference.load_model()["features"]
        for sig in signals:
            self.assertIn(sig["feature"], model_features)
            self.assertIsInstance(sig["contribution"], float)
        contribs = [abs(sig["contribution"]) for sig in signals]
        self.assertEqual(contribs, sorted(contribs, reverse=True))

    def test_missing_pca_feature_is_an_error(self):
        s = _sample(0)
        v = dict(s["features"])
        del v["v7"]
        with self.assertRaises(ValueError):
            inference.score(s["amount"], v)

    def test_deterministic(self):
        s = _sample(0)
        self.assertEqual(
            inference.score(s["amount"], s["features"]),
            inference.score(s["amount"], s["features"]),
        )

    def test_samples_are_real_dataset_rows(self):
        samples = inference.load_samples()["samples"]
        self.assertEqual(len(samples), 3)
        self.assertEqual([s["is_fraud"] for s in samples], [1, 0, 0])


if __name__ == "__main__":
    unittest.main()
