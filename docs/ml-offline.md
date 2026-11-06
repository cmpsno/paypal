# Offline ML model — Zenodo data only

## What it is

A logistic regression trained offline on the Zenodo dataset (Fatah &
Rashid, CC BY 4.0; 57,394 rows, 111 fraud). It scores **dataset rows**
— amount plus 28 PCA signals (v1–v28) — in the dashboard's "Offline ML
model" panel.

It **never scores a live PayPal transaction**. A live transaction has no
v1–v28 features, so there is nothing to feed it. The deterministic rules
engine (`backend/risk/classifier.py`) is the live decision-maker; this
model is the evaluated offline baseline that answers one research
question: do v1–v28 add predictive value beyond amount alone?

Answer: yes, on this dataset. See the numbers below.

## How it was built (Option C)

1. Training ran offline in `~/workspace/paypal-ml-baseline/`
   (`train_baseline.py`, scikit-learn 1.5.2, seed 42) — never in this
   repo, never on Render.
2. The trained weights were exported to `backend/ml/model.json`:
   scaler means/scales, 29 coefficients (log-amount + v1–v28),
   intercept, and the decision threshold (0.99).
3. Runtime inference is `backend/ml/inference.py` — a dot product +
   sigmoid in the standard library. The training script verified it
   reproduces sklearn's probabilities to within 7.9e-07.
4. Sample rows are real Zenodo rows in `backend/ml/samples.json`
   (one fraud caught, one clean legitimate, one high-amount legitimate
   the model passes). Their dataset labels are shown as recorded, not
   as independently verified ground truth.

## Results (from the Step 1 evaluation)

Method: stratified 5-fold cross-validation, out-of-fold probabilities;
threshold tuned on the precision–recall curve (max F1), then frozen for
the held-out test (11,479 rows, 22 fraud). Full write-up:
`~/workspace/paypal-ml-baseline/evaluation.md`.

| Model | PR-AUC | F1 | Precision | Recall |
|---|---:|---:|---:|---:|
| Predict all legitimate | 0.002 | 0.000 | 0.000 | 0.000 |
| Amount-only logistic regression | 0.213 | 0.354 | 0.263 | 0.541 |
| **Amount + v1–v28 logistic regression** | **0.742** | **0.824** | **0.787** | **0.865** |

Held-out test (frozen threshold): amount+v PR-AUC 0.785, precision
0.84, recall 0.955 (21/22, 4 false positives).

Baselines on the same rows: amount rules catch all 111 fraud but flag
27.5% of traffic (15,758 transactions); the ML model catches 96 of 111
while flagging 0.21% (122). Predicting everything legitimate scores
99.81% accuracy and catches zero fraud.

## API

- `GET /api/offline-model` — model card: features, threshold, metrics,
  limits.
- `GET /api/offline-samples` — the three real dataset rows.
- `POST /api/offline-score` — body `{"amount": ..., "features": {"v1": ..., ...}}`.
  All 28 PCA features are required; a missing one is a 400 error, never
  a silent zero. Returns probability, FLAG/PASS at the 0.99 threshold,
  and the top 3 contributing statistical signals (feature names only in
  the UI — PCA components, not behaviours).

## Limits — state these whenever the numbers are quoted

- Only 111 fraud rows: recall is roughly 0.79–0.92, not a point.
- Labels come from the original system's decisions; missed fraud is
  plausibly recorded as not-fraud.
- This is not PayPal data and not real customer banking data.
- The 0.99 threshold is a calibration artifact of balanced class
  weights — at that threshold 79% of flagged rows are fraud, not 99%.
- Top coefficients are suspiciously large (v5 +17.8, v1 −13.3): the model
  may be reproducing the original system's labeling boundary rather than
  detecting fraud in the wild.
- The CSV does not match its README (57,394 / 111 / $33.75 median vs
  56,962 / 98 / $49.88). All numbers above are from the CSV itself.
