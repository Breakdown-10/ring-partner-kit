"""
Constant-time HMAC-SHA256 signature verification for Ring webhooks.
Protects partner endpoints from forgery, replay attacks, and tampering.
"""
import hmac
import hashlib
import time
from typing import Optional, Tuple


class SignatureVerificationError(Exception):
    """Raised when webhook signature verification fails."""
    pass


class RingWebhookVerifier:
    def __init__(self, secret: str, max_drift_seconds: int = 300):
        """
        :param secret: Webhook signing secret provisioned in the Ring Developer Portal.
        :param max_drift_seconds: Maximum allowable clock skew / replay window (default 5 minutes).
        """
        self.secret = secret.encode("utf-8") if isinstance(secret, str) else secret
        self.max_drift_seconds = max_drift_seconds

    def sign(self, raw_body: bytes, timestamp: Optional[int] = None) -> Tuple[str, str]:
        """
        Signs a payload returning (signature_header, raw_hex).
        Signature format: t=<epoch_ms>,v1=<hex_hmac>
        """
        ts = timestamp if timestamp is not None else int(time.time() * 1000)
        # Message format: t.<timestamp>.<raw_body>
        message = f"t.{ts}.".encode("utf-8") + raw_body
        digest = hmac.new(self.secret, message, hashlib.sha256).hexdigest()
        header = f"t={ts},v1={digest}"
        return header, digest

    def verify(self, raw_body: bytes, signature_header: str, current_time_ms: Optional[int] = None) -> bool:
        """
        Verifies the Ring webhook signature against the raw body bytes.
        Supports both v1 key-value format (t=...,v1=...) and direct sha256 hex string.
        """
        if not signature_header or not raw_body:
            return False

        current_ms = current_time_ms if current_time_ms is not None else int(time.time() * 1000)

        # Check for structured format: t=12345678,v1=abcdef...
        if "t=" in signature_header and "v1=" in signature_header:
            parts = dict(p.strip().split("=", 1) for p in signature_header.split(",") if "=" in p)
            ts_str = parts.get("t")
            v1_sig = parts.get("v1")

            if not ts_str or not v1_sig:
                return False

            try:
                ts = int(ts_str)
            except ValueError:
                return False

            # Check timestamp drift to prevent replay attacks
            drift_seconds = abs(current_ms - ts) / 1000.0
            if drift_seconds > self.max_drift_seconds:
                return False

            # Compute expected signature
            message = f"t.{ts}.".encode("utf-8") + raw_body
            expected_sig = hmac.new(self.secret, message, hashlib.sha256).hexdigest()
            return hmac.compare_digest(v1_sig.lower(), expected_sig.lower())

        # Direct HMAC-SHA256 of raw body
        clean_sig = signature_header.replace("sha256=", "").strip()
        expected = hmac.new(self.secret, raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(clean_sig.lower(), expected.lower())
