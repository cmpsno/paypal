# Monitoring — the feedback loop

## What it is

The process that tells you when a model is no longer trustworthy.
Three pieces, all in `backend/monitoring.py` (stdlib only):

1. **Log every prediction** — model version, timestamp, decision,
   score / probability, reason codes, amount. Logging never changes
   a score. Both models log, each under its own version
   (`rules-1.0`, `ml-lr-1.0`), so their records never mix.
2. **Outcomes arrive later.** Somebody confirms a transaction was
   fraud or legitimate — days or weeks later in real life — and
   records it. Until then, true precision/recall cannot be measured,
   and the API says so instead of inventing them.
3. **Monitor what can be measured now** — volumes, hold rate,
   reason-code counts, drift signals — and precision/recall only on
   the confirmed subset, when one exists.

## API

- `GET /api/predictions` — logged predictions, newest first (last 50).
- `POST /api/outcomes` — body `{"transaction_id": "...",
  "outcome": "fraud" | "legitimate"}`. Attaches to the most recent
  un-outcomed prediction for that transaction. Errors (400) on an
  unknown transaction, an invalid outcome, or a double-recording.
- `GET /api/monitoring` — summary (see below).

## What /api/monitoring returns

- `total_predictions`, `by_model`, `hold_or_flag_rate`,
  `reason_code_counts`.
- `confirmed_outcomes`: `null` until the first outcome is recorded,
  then `{n, fraud, legitimate, tp, fp, fn, precision, recall, f1}`.
  Precision/recall exist **only** on the confirmed subset.
- `drift`: median amount and hold/flag rate, all-time vs last 20.
  A large move is a signal to investigate, not a verdict — and it can
  be watched before any outcomes arrive.

## Retraining criteria (the policy, not an automation)

- Investigate when: recall on confirmed outcomes deteriorates, or the
  drift signals move a lot (recent median amount / hold rate far from
  all-time).
- Never retrain just because a calendar date arrives.
- A replacement model is promoted only after it beats the current one
  on confirmed outcomes — with the old model kept for rollback.
- These are criteria for a human to apply. Nothing here retrains or
  redeploys automatically.

## Limits — state these whenever the loop is described

- Storage is **in-memory** and resets when the server restarts, like
  the demo-session history. A production log would be a database.
- There are no confirmed outcomes flowing in yet. The loop as shipped
  is a working mechanism (log → record outcome → measure), not a
  running measurement. The dashboard says "no confirmed outcomes yet"
  until one is recorded.
- The Sandbox transactions and the Zenodo dataset do not share a
  feature space, so outcomes for one model say nothing about the
  other. That is why the log is split by model version.
