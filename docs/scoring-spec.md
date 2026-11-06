# Scoring spec — T3 classifier

## Rules

- Start at 0. Add points. Cap at 100.
- Score < 50 → RELEASE. Score >= 50 → HOLD.
- Always return reason codes. A HOLD must list at least one.
  A RELEASE with a non-zero score still lists its codes, so the
  dashboard can show "why it passed".
- All weights and the threshold live in `backend/risk/config.py`.
  Nothing in `classifier.py` hard-codes a number.

| Signal | Points | Reason code |
|---|---:|---|
| Sandbox failure: INSTRUMENT_DECLINED | +50 | INSTRUMENT_DECLINED |
| Sandbox failure: TRANSACTION_REFUSED | +40 | TRANSACTION_REFUSED |
| Any other Sandbox failure / error result | +30 | SANDBOX_FAILURE |
| Amount > 3x the account's median | +25 | AMOUNT_SPIKE |
| 3+ transactions in the last 60 minutes | +20 | VELOCITY_BURST |
| 5th+ small (≤$50) transaction to the same payee within 10 min | +30 | STRUCTURING |
| First transaction to this payee | +15 | NEW_PAYEE |
| Amount > $500 | +10 | HIGH_AMOUNT |

Weights are heuristics for the demo, stated as such — not a fraud model.

## Input

A `NormalizedTransaction` (`backend/models.py`):
`transaction_id`, `amount`, `currency`, `payee_id`,
`timestamp`, `sandbox_status`, `account_median_amount`,
`txns_last_60m`, `same_payee_small_txns_last_10m`, `is_first_payee`.

Notes:
- `payee_id` is `Optional[str]`. If it is `None`, NEW_PAYEE
  and STRUCTURING points are NOT awarded, even if
  `is_first_payee` is True or the structuring count is non-zero.
- `account_median_amount` is `None` when unknown. Unknown
  median = 0 points for AMOUNT_SPIKE, not a guess.
- Median, velocity, and the structuring count are computed by
  the backend from transactions already seen in the demo session.
  PayPal does not hand them to us.
- STRUCTURING: the 5th (or later) small transaction to the same
  payee within 10 minutes — 4+ prior small (≤$50) same-payee
  transactions in the window, and this transaction itself ≤$50.
  Five $20 payments score 20 (velocity) + 30 = 50 → HOLD; the
  4th $20 scores 20 → RELEASE. Large amounts never fire it.

## Output

`{ transaction_id, score, decision, reason_codes[], top_reason }`

`top_reason` is the first reason code, or `None` if the
transaction is clean.

## PayPal negative testing (for the Sandbox step, not built yet)

To force the two named failure codes deterministically in the
Sandbox, PayPal documents this JSON header format:

```
PayPal-Mock-Response: {"mock_application_codes": "INSTRUMENT_DECLINED"}
```

`TRANSACTION_REFUSED` is documented as a negative-testing
scenario for Orders v2 capture. Verify the exact header values
against the live PayPal Developer docs during the Sandbox build.

## Tests (12 classifier, all in `backend/tests/test_classifier.py`)

1. No signals = 0 → RELEASE.
2. TRANSACTION_REFUSED alone = 40 → RELEASE.
3. Other Sandbox failure alone = 30 → RELEASE.
4. INSTRUMENT_DECLINED alone = 50 → HOLD.
5. New payee + amount spike + velocity = 15+25+20 = 60 → HOLD.
6. All signals at once: raw 120, capped at 100 → HOLD.
7. Same transaction scored twice → identical result (determinism).
8. Unknown payee (`payee_id=None`, `is_first_payee=True`) = 0,
   no NEW_PAYEE points → RELEASE.
9. Structuring: 5th $20 to the same payee in 10 min =
   20 (velocity) + 30 = 50 → HOLD.
10. Structuring needs 4 prior small: 4th $20 = 20 → RELEASE.
11. Structuring does not fire on large amounts: 5 x $100 = 20
    → RELEASE.
12. Structuring needs a known payee: `payee_id=None` = 20
    → RELEASE.

## What HOLD means

HOLD is the agent's risk recommendation. It does not claim to
block or reverse a PayPal payment unless that functionality is
implemented and verified.
