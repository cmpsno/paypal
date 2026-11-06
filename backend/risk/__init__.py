"""Risk scoring package: config + classifier. No I/O, no PayPal, no AI."""
from backend.risk.classifier import ClassificationResult, classify

__all__ = ["ClassificationResult", "classify"]
