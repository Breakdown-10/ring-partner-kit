import pytest
import time
from ring_partner_kit.verifier import RingWebhookVerifier


def test_verifier_direct_hmac():
    secret = "my_secret_key_12345"
    verifier = RingWebhookVerifier(secret=secret)
    body = b'{"hello": "world"}'

    # Compute expected signature
    import hmac
    import hashlib
    expected_hex = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verifier.verify(body, expected_hex) is True
    assert verifier.verify(body, f"sha256={expected_hex}") is True
    assert verifier.verify(body, "invalid_sig") is False
    assert verifier.verify(b'{"modified": true}', expected_hex) is False


def test_verifier_timestamped_header():
    secret = "top_secret_ring_key"
    verifier = RingWebhookVerifier(secret=secret, max_drift_seconds=300)
    body = b'{"event": "motion", "device": "doorbell"}'

    header, hex_digest = verifier.sign(body)
    assert header.startswith("t=")
    assert ",v1=" in header

    # Verify matching header
    assert verifier.verify(body, header) is True

    # Tampered body should fail
    assert verifier.verify(b'{"tampered": true}', header) is False

    # Stale timestamp beyond drift window
    old_time_ms = int((time.time() - 400) * 1000)
    old_header, _ = verifier.sign(body, timestamp=old_time_ms)
    assert verifier.verify(body, old_header) is False
