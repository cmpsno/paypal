# Transaction-risk agent

A transaction-risk agent that evaluates PayPal Sandbox transactions,
calculates a risk score, explains its reasoning through reason codes,
and recommends HOLD or RELEASE.

One thing, done well. Not a banking app.

**Deadline:** Thu Nov 12, 2026, 3:00 PM EST — PayPal AI Hackathon.

## What is built so far

The classifier first, then the pieces around it — each tested on
its own before the next was added.

- `backend/models.py` — `NormalizedTransaction`, the one shape
  everything agrees on. `payee_id` is `Optional[str]`; if it is
  unknown, no first-time-payee points are awarded.
- `backend/risk/config.py` — all weights and the 50-point
  HOLD threshold, in one place.
- `backend/risk/classifier.py` — `classify(transaction)`, a pure
  function: same input, same output, no network, no randomness.
- `backend/tests/test_classifier.py` — 8 unit tests.
- `backend/paypal_client.py` + `backend/history.py` — PayPal
  Sandbox adapter and demo-session history (median, velocity,
  first payee), with a CLI demo. 17 more tests.
- `backend/app.py` + `frontend/` — dashboard: score form, 5 demo
  cases, history table. Served by the same server locally and on
  Render; the Pages copy calls the Render API.
- `backend/risk/explainer.py` — the AI explanation layer: turns a
  finished classification into one plain-English sentence. It
  never makes the decision and never changes the score; an LLM
  may only reword the template sentence, with fallback to the
  template if it fails. 10 tests.

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
- **The AI explains that decision.** `backend/risk/explainer.py`
  turns reason codes into a plain-English sentence. It never
  makes the decision and never changes the score. An LLM plugged
  in later may only reword that sentence; if it fails, the
  template sentence is used instead.

## Run the tests

No dependencies to install — Python 3.12 standard library only.

```bash
python3 -m unittest discover -s backend/tests -v
```

Expected: 35 tests, all passing (8 classifier, 17 Sandbox/history,
10 explainer).

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

1. Offline evaluation against the public dataset — see `docs/dataset.md`.
2. Demo video (under 3 minutes) + Devpost submission.

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
