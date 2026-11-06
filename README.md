# Transaction-risk agent

A transaction-risk agent that evaluates PayPal Sandbox transactions,
calculates a risk score, explains its reasoning through reason codes,
and recommends HOLD or RELEASE.

One thing, done well. Not a banking app.

**Deadline:** Thu Nov 12, 2026, 3:00 PM EST — PayPal AI Hackathon.

## What is built so far

Only the classifier. Nothing else yet — no PayPal integration,
no dashboard, no AI explainer. That is on purpose: the classifier
is the most important part, and it works and is tested on its own
before any external dependency is introduced.

- `backend/models.py` — `NormalizedTransaction`, the one shape
  everything agrees on. `payee_id` is `Optional[str]`; if it is
  unknown, no first-time-payee points are awarded.
- `backend/risk/config.py` — all weights and the 50-point
  HOLD threshold, in one place.
- `backend/risk/classifier.py` — `classify(transaction)`, a pure
  function: same input, same output, no network, no randomness.
- `backend/tests/test_classifier.py` — 8 unit tests.

## The decision, in one paragraph

Score starts at 0, points add up, score caps at 100.
Under 50 → RELEASE. 50 or above → HOLD.
Reason codes are always returned, so the decision can be explained.

| Signal | Points |
|---|---:|
| INSTRUMENT_DECLINED | +50 |
| TRANSACTION_REFUSED | +40 |
| Other Sandbox failure | +30 |
| Amount > 3x account median | +25 |
| 3+ transactions in 60 minutes | +20 |
| First-time payee | +15 |
| Amount > $500 | +10 |

Full spec: `docs/scoring-spec.md`.

## Separation of responsibilities

- **The scoring engine makes the financial risk decision.**
  That is `classify()`, and only that.
- **The AI explains that decision.** A separate explainer module
  (not built yet) will turn reason codes into a plain-English
  sentence. It never makes the decision and never changes the score.

## Run the tests

No dependencies to install — Python 3.12 standard library only.

```bash
python3 -m unittest discover -s backend/tests -v
```

Expected: 8 tests, all passing.

## Run the dashboard

```bash
python3 -m backend.app
```

Then open http://localhost:8000

One page, no build step, no extra dependencies. Score a transaction
with the form, or click a demo case — clean (0, RELEASE),
TRANSACTION_REFUSED alone (40, RELEASE), INSTRUMENT_DECLINED
(50, HOLD), new payee + spike + velocity (60, HOLD), everything
at once (capped at 100, HOLD). History shows every transaction
scored this session, newest first. History resets on restart.

The dashboard is real, not a mockup: it calls `POST /api/score`,
which runs the same `classify()` the tests cover.

## Try the classifier

```bash
python3 -c "
from backend.models import NormalizedTransaction
from backend.risk.classifier import classify

tx = NormalizedTransaction(
    transaction_id='demo-1',
    amount=400.0,
    payee_id='payee-new',
    account_median_amount=100.0,
    txns_last_60m=3,
    is_first_payee=True,
)
print(classify(tx))
"
```

Expected: score 60, HOLD, codes
`AMOUNT_SPIKE, VELOCITY_BURST, NEW_PAYEE`.

## What comes next (in order)

1. Connect the PayPal Sandbox.
2. Build the dashboard around the classifier's output.
3. Integrate the AI explanation layer.
4. Offline evaluation against the public dataset — see `docs/dataset.md`.

## Dataset attribution

Offline validation uses a public dataset, kept completely separate
from the live Sandbox feed. Full details in `docs/dataset.md`.

Fatah, H.H. and Rashid, Z.N. (2026). *A Deployment-Derived Online
Banking Fraud Detection Inference-Log Dataset from a Live
Cloud-Based Deep Learning System* [Dataset]. Zenodo.
DOI: https://doi.org/10.5281/zenodo.20030064
(Zenodo record: https://zenodo.org/records/20777880).
Licence: CC BY 4.0.

## Licence

MIT — see `LICENSE`. That covers this project's code only, not the
dataset above, which is CC BY 4.0.
