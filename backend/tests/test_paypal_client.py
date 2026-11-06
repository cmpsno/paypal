"""Tests for the Sandbox response mapping — no network calls.

These test the pure functions in paypal_client.py only:
  sandbox_status_from_response, payee_id_from_response,
  amount_from_response, mock_header.
The live OAuth / create / capture calls are exercised by
backend/demo_sandbox.py with real Sandbox credentials, not here.
"""

import unittest

from backend.paypal_client import (
    amount_from_response,
    mock_header,
    payee_id_from_response,
    sandbox_status_from_response,
)


class TestMockHeader(unittest.TestCase):
    def test_no_mock_no_header(self):
        self.assertEqual(mock_header(None), {})

    def test_mock_header_is_json(self):
        import json

        header = mock_header("INSTRUMENT_DECLINED")
        self.assertEqual(
            json.loads(header["PayPal-Mock-Response"]),
            {"mock_application_codes": "INSTRUMENT_DECLINED"},
        )


class TestSandboxStatus(unittest.TestCase):
    def test_completed_is_success(self):
        self.assertEqual(
            sandbox_status_from_response({"status": "COMPLETED"}), "SUCCESS"
        )

    def test_instrument_declined_from_error_details(self):
        resp = {
            "name": "UNPROCESSABLE_ENTITY",
            "details": [{"issue": "INSTRUMENT_DECLINED"}],
        }
        self.assertEqual(
            sandbox_status_from_response(resp), "INSTRUMENT_DECLINED"
        )

    def test_transaction_refused_from_error_details(self):
        resp = {
            "name": "UNPROCESSABLE_ENTITY",
            "details": [{"issue": "TRANSACTION_REFUSED"}],
        }
        self.assertEqual(
            sandbox_status_from_response(resp), "TRANSACTION_REFUSED"
        )

    def test_unknown_error_is_not_success(self):
        # Never invent SUCCESS: an unapproved order / bad token /
        # unknown error must come back as a failure status.
        resp = {
            "name": "ORDER_NOT_APPROVED",
            "details": [{"issue": "ORDER_NOT_APPROVED"}],
        }
        status = sandbox_status_from_response(resp)
        self.assertNotEqual(status, "SUCCESS")
        self.assertEqual(status, "ORDER_NOT_APPROVED")

    def test_empty_response_is_failure(self):
        self.assertEqual(
            sandbox_status_from_response({}), "SANDBOX_FAILURE"
        )


class TestPayeeAndAmount(unittest.TestCase):
    def test_payee_missing_is_none(self):
        self.assertIsNone(payee_id_from_response({"status": "COMPLETED"}))

    def test_amount_from_capture(self):
        resp = {
            "purchase_units": [
                {
                    "payments": {
                        "captures": [{"amount": {"value": "620.00"}}]
                    }
                }
            ]
        }
        self.assertEqual(amount_from_response(resp), 620.0)

    def test_amount_missing_is_none(self):
        self.assertIsNone(amount_from_response({"status": "COMPLETED"}))


if __name__ == "__main__":
    unittest.main()
