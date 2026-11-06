"""Scoring rules -- the ONLY place weights and thresholds live.

If a judge (or you) wants to change a weight, change it here
and re-run the tests. Nothing in classifier.py hard-codes a number.

These weights are heuristics for the demo, stated as such.
They are not a trained fraud model.
"""

# Decision threshold: score >= this means HOLD, below means RELEASE.
HOLD_THRESHOLD = 50

# Scores never go above this, no matter how many signals fire.
MAX_SCORE = 100

# Points per signal. Keys are reason codes -- the same strings
# the classifier returns, so the dashboard can show "why".
POINTS = {
    "INSTRUMENT_DECLINED": 50,
    "TRANSACTION_REFUSED": 40,
    "SANDBOX_FAILURE": 30,  # any other Sandbox failure / error result
    "AMOUNT_SPIKE": 25,  # amount > 3x the account's median
    "VELOCITY_BURST": 20,  # 3+ transactions in the last 60 minutes
    "NEW_PAYEE": 15,  # first transaction to this payee
    "HIGH_AMOUNT": 10,  # amount > $500
}

# Cut-offs for the amount-based signals.
AMOUNT_SPIKE_MULTIPLIER = 3.0
VELOCITY_MIN_TXNS = 3
HIGH_AMOUNT_THRESHOLD = 500.0
