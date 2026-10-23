from unittest.mock import MagicMock, patch
import pytest
import requests
from ring_partner_kit.client import RingApiClient, RingRateLimitError, RingApiError


def test_client_token_expiration():
    client = RingApiClient(access_token="valid_token", token_expires_at=9999999999.0)
    assert client.is_token_expired() is False

    expired_client = RingApiClient(access_token="old_token", token_expires_at=100.0)
    assert expired_client.is_token_expired() is True


def test_client_refresh_token():
    client = RingApiClient(
        base_url="https://api.test.ring",
        client_id="test_client",
        refresh_token="ref_123",
        token_expires_at=0.0
    )

    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new_access_token_xyz",
            "refresh_token": "new_refresh_token_abc",
            "expires_in": 3600
        }
        mock_post.return_value = mock_resp

        client.refresh_access_token_if_needed()
        assert client.access_token == "new_access_token_xyz"
        assert client.refresh_token == "new_refresh_token_abc"
        assert client.is_token_expired() is False


def test_client_get_devices():
    client = RingApiClient(access_token="tok_123")

    with patch("requests.request") as mock_req:
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.headers = {"X-RateLimit-Remaining": "95"}
        mock_resp.json.return_value = {
            "doorbots": [{"id": 1, "description": "Front Door"}],
            "stickup_cams": []
        }
        mock_req.return_value = mock_resp

        devices = client.get_devices()
        assert len(devices) == 1
        assert devices[0]["description"] == "Front Door"
        assert client.rate_limit_remaining == 95
