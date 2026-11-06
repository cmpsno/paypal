"""PayPal Sandbox client — the live box, and only the live box.

Talk to the PayPal Sandbox, nothing else. It never scores a
transaction (that is ``backend/risk/classifier.py``) and never
touches the offline dataset.

Flow, per PayPal's Orders v2 docs:
  1. OAuth client-credentials token:
     POST https://api-m.sandbox.paypal.com/v1/oauth2/token
  2. Create an order (intent CAPTURE):
     POST https://api-m.sandbox.paypal.com/v2/checkout/orders
  3. Capture it:
     POST https://api-m.sandbox.paypal.com/v2/checkout/orders/{id}/capture

Credentials come from the environment, never from code:
  PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET
(Sandbox app credentials from developer.paypal.com.)

Negative testing — the deterministic demo path:
  PayPal-Mock-Response: {"mock_application_codes": "INSTRUMENT_DECLINED"}
  PayPal also documents TRANSACTION_REFUSED for Orders v2 capture.
  Pass ``mock_code="INSTRUMENT_DECLINED"`` (or "TRANSACTION_REFUSED")
  to ``create_order`` / ``capture_order`` and PayPal simulates that
  failure instead of a real charge. No real money moves in Sandbox.

Honest limit: a real COMPLETED capture needs a buyer to approve
the order first (the approval URL PayPal returns on create). The
mock-failure path is what makes the classifier's failure cases
reproducible on demand; a success capture in a server-only script
will come back as an unapproved-order error, which this module
surfaces as-is instead of faking a SUCCESS.

Standard library only — urllib, json, base64. No new dependency.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

SANDBOX_BASE_URL = "https://api-m.sandbox.paypal.com"

# Failure codes the classifier already understands. Anything else
# PayPal returns is passed through as-is; the classifier treats an
# unknown non-SUCCESS status as "other Sandbox failure" (+30).
KNOWN_FAILURE_CODES = ("INSTRUMENT_DECLINED", "TRANSACTION_REFUSED")


def mock_header(mock_code: str | None) -> dict[str, str]:
    """Build the PayPal-Mock-Response header, or no header."""
    if not mock_code:
        return {}
    return {
        "PayPal-Mock-Response": json.dumps(
            {"mock_application_codes": mock_code}
        )
    }


def _request(
    method: str,
    url: str,
    headers: dict[str, str],
    body: dict | None = None,
) -> dict:
    """One HTTPS call. Returns the parsed JSON body.

    PayPal error responses (e.g. 422 for a mocked decline) still
    carry a JSON body with a ``details`` list — return that body
    instead of raising, so the caller can read the failure code.
    """
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read() or b"{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"name": "HTTP_ERROR", "message": raw.decode(errors="replace")}


def get_access_token(
    client_id: str, client_secret: str, base_url: str = SANDBOX_BASE_URL
) -> str:
    """OAuth client-credentials token for the Sandbox.

    This endpoint takes form data (grant_type=client_credentials),
    not JSON, so it posts directly instead of via _request.
    """
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req = urllib.request.Request(
        f"{base_url}/v1/oauth2/token",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read() or b"{}")
    return body["access_token"]


def create_order(
    access_token: str,
    amount: float,
    currency: str = "USD",
    mock_code: str | None = None,
    base_url: str = SANDBOX_BASE_URL,
) -> dict:
    """Create a CAPTURE-intent order. Returns the raw order dict."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        **mock_header(mock_code),
    }
    return _request(
        "POST",
        f"{base_url}/v2/checkout/orders",
        headers,
        body={
            "intent": "CAPTURE",
            "purchase_units": [
                {"amount": {"currency_code": currency, "value": f"{amount:.2f}"}}
            ],
        },
    )


def capture_order(
    access_token: str,
    order_id: str,
    mock_code: str | None = None,
    base_url: str = SANDBOX_BASE_URL,
) -> dict:
    """Capture an order. Returns the raw capture dict (or error body)."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        **mock_header(mock_code),
    }
    return _request(
        "POST",
        f"{base_url}/v2/checkout/orders/{order_id}/capture",
        headers,
        body={},
    )


def sandbox_status_from_response(resp: dict) -> str:
    """Map a PayPal create/capture response to a classifier status.

    - Capture status COMPLETED -> "SUCCESS"
    - Error body with details[0].issue -> that issue code
      (e.g. "INSTRUMENT_DECLINED", "TRANSACTION_REFUSED")
    - Anything else -> the issue/name if present, else "SANDBOX_FAILURE"

    Never invents SUCCESS: an unapproved order, a bad token, or any
    other error comes back as a failure status, and the classifier
    scores it (+30 for an unknown failure) instead of 0.
    """
    status = resp.get("status")
    if status == "COMPLETED":
        return "SUCCESS"
    details = resp.get("details") or []
    if details and isinstance(details, list):
        issue = details[0].get("issue")
        if issue:
            return issue
    if resp.get("name"):
        return resp["name"]
    if status:
        return status
    return "SANDBOX_FAILURE"


def payee_id_from_response(resp: dict) -> str | None:
    """Best-effort payee id from a capture response, else None.

    Sandbox captures do not reliably carry a merchant/payee id in
    the demo flow, so None is the normal case — and the classifier
    correctly awards no NEW_PAYEE points when it is None.
    """
    units = resp.get("purchase_units") or []
    if units:
        payee = units[0].get("payee") or {}
        merchant_id = payee.get("merchant_id")
        if merchant_id:
            return merchant_id
    return None


def amount_from_response(resp: dict) -> float | None:
    """Best-effort amount from a capture response, else None."""
    units = resp.get("purchase_units") or []
    if units:
        payments = units[0].get("payments") or {}
        captures = payments.get("captures") or []
        if captures:
            amount = captures[0].get("amount") or {}
            try:
                return float(amount["value"])
            except (KeyError, TypeError, ValueError):
                return None
    return None
