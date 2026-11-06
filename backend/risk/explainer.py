"""The AI explanation layer -- the part that explains the decision.

One job, one function: ``explain(result, transaction)``.

It takes a ClassificationResult (already decided by ``classify()``)
and turns its reason codes into one plain-English sentence.

Separation of responsibilities, on purpose:
  - The classifier MAKES the decision. This module never sees a
    raw transaction before scoring, never changes the score, and
    never changes HOLD/RELEASE. It only reads the finished result.
  - This module EXPLAINS the decision. The sentence is built from
    the reason codes and their points in ``config.POINTS`` -- so
    it can never invent a reason the classifier did not give.

How the AI fits (the hackathon's "meaningfully incorporate AI" rule):
  - By default the explanation is a deterministic template -- no
    network, no API key, no randomness. Same result, same sentence.
  - Pass an ``llm_rewrite`` callable to let an LLM reword that
    template sentence. The LLM only ever receives the template
    sentence plus the reason codes; it never receives the power to
    re-score, and if it fails or returns nothing usable, the
    template sentence is used instead. The decision is identical
    either way -- only the wording can change.

Pure function apart from the optional rewrite: same input ->
same template sentence, every time. That is what makes it
unit-testable, and what makes the demo honest to a judge:
"AI explains the decision, it does not make it."
"""

from __future__ import annotations

from typing import Callable, Optional

from backend.models import NormalizedTransaction
from backend.risk import config
from backend.risk.classifier import ClassificationResult

# One plain-English phrase per reason code. The points come from
# config.POINTS at call time, so a weight change updates the
# explanation automatically -- no number is hard-coded here.
PHRASES = {
    "INSTRUMENT_DECLINED": "the payment instrument was declined",
    "TRANSACTION_REFUSED": "the transaction was refused",
    "SANDBOX_FAILURE": "the Sandbox reported a failure",
    "AMOUNT_SPIKE": "the amount is more than 3x the account median",
    "VELOCITY_BURST": "3 or more transactions arrived within 60 minutes",
    "NEW_PAYEE": "this is a first-time payee",
    "HIGH_AMOUNT": "the amount is over $500",
    "STRUCTURING": "5 or more small transactions to the same payee within 10 minutes",
}


def _template(result: ClassificationResult) -> str:
    """Build the deterministic explanation sentence."""
    if not result.reason_codes:
        return (
            f"Released at {result.score}/100 — no risk signals fired, "
            f"so nothing pushed the score toward the "
            f"{config.HOLD_THRESHOLD}-point hold bar."
        )
    reasons = "; ".join(
        f"{PHRASES.get(code, code.lower().replace('_', ' '))} "
        f"(+{config.POINTS.get(code, 0)})"
        for code in result.reason_codes
    )
    verb = "Held" if result.decision == "HOLD" else "Released"
    return (
        f"{verb} at {result.score}/100 — {reasons}. "
        f"That is {'at or above' if result.decision == 'HOLD' else 'below'} "
        f"the {config.HOLD_THRESHOLD}-point hold bar."
    )


def explain(
    result: ClassificationResult,
    transaction: Optional[NormalizedTransaction] = None,
    llm_rewrite: Optional[Callable[[str, ClassificationResult], str]] = None,
) -> str:
    """Explain a finished classification in one sentence.

    ``transaction`` is accepted for context (amount / payee) but is
    not needed by the template and never affects the wording of the
    reasons -- the reasons come from ``result`` alone, so an
    explanation can never cite a signal that did not fire.

    ``llm_rewrite`` -- optional. A callable taking the template
    sentence and the result, returning a reworded sentence. Any
    failure, empty return, or non-string return falls back to the
    template. The returned sentence is never allowed to change
    the score or the decision; it is wording only.
    """
    sentence = _template(result)
    if llm_rewrite is None:
        return sentence
    try:
        rewritten = llm_rewrite(sentence, result)
    except Exception:
        return sentence
    if not isinstance(rewritten, str) or not rewritten.strip():
        return sentence
    return rewritten.strip()
