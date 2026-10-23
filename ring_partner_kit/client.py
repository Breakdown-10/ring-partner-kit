"""
Production-grade Ring API client with OAuth2 token lifecycle,
rate limit tracking, and exponential backoff retry.
"""
import logging
import random
import time
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger("ring_partner_kit.client")


class RingApiError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class RingRateLimitError(RingApiError):
    def __init__(self, message: str, retry_after: int = 5):
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class RingApiClient:
    """
    Client for interacting with the Ring Partner / Amazon Vision API.
    """
    def __init__(
        self,
        base_url: str = "https://api.amazonvision.com",
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        token_expires_at: Optional[float] = None,
        max_retries: int = 3,
        timeout: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_expires_at = token_expires_at or (time.time() + 3600 if access_token else 0)
        self.max_retries = max_retries
        self.timeout = timeout

        # Rate limit tracking
        self.rate_limit_remaining: Optional[int] = None
        self.rate_limit_reset: Optional[int] = None

    def is_token_expired(self, buffer_seconds: int = 60) -> bool:
        if not self.access_token:
            return True
        return time.time() + buffer_seconds >= self.token_expires_at

    def refresh_access_token_if_needed(self) -> None:
        """
        Refreshes access token if within buffer or expired, and refresh_token is configured.
        """
        if not self.is_token_expired():
            return

        if not self.refresh_token or not self.client_id:
            logger.debug("Cannot auto-refresh token: refresh_token or client_id not set.")
            return

        logger.info("Refreshing Ring OAuth2 access token...")
        token_url = f"{self.base_url}/oauth/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret

        try:
            resp = requests.post(token_url, data=data, timeout=self.timeout)
            if resp.status_code == 200:
                payload = resp.json()
                self.access_token = payload["access_token"]
                self.refresh_token = payload.get("refresh_token", self.refresh_token)
                expires_in = payload.get("expires_in", 3600)
                self.token_expires_at = time.time() + expires_in
                logger.info("Successfully refreshed Ring access token.")
            else:
                logger.warning(f"Failed to refresh token: status {resp.status_code}")
        except Exception as e:
            logger.error(f"Token refresh request failed: {e}")

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        self.refresh_access_token_if_needed()

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Accept": "application/json",
            "User-Agent": "RingPartnerKit/1.0",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    headers=headers,
                    timeout=self.timeout,
                )

                # Track rate limits
                if "X-RateLimit-Remaining" in resp.headers:
                    self.rate_limit_remaining = int(resp.headers["X-RateLimit-Remaining"])
                if "X-RateLimit-Reset" in resp.headers:
                    self.rate_limit_reset = int(resp.headers["X-RateLimit-Reset"])

                # Handle 429
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                    if attempt < self.max_retries:
                        sleep_time = retry_after + random.uniform(0.1, 0.5)
                        logger.warning(f"Rate limited by Ring API. Backing off for {sleep_time:.2f}s (attempt {attempt + 1})")
                        time.sleep(sleep_time)
                        continue
                    raise RingRateLimitError(f"Rate limit exceeded on {url}", retry_after=retry_after)

                # Retry on 5xx
                if resp.status_code >= 500 and attempt < self.max_retries:
                    sleep_time = (2 ** attempt) + random.uniform(0.1, 0.5)
                    logger.warning(f"Ring API returned {resp.status_code}. Retrying in {sleep_time:.2f}s...")
                    time.sleep(sleep_time)
                    continue

                if not resp.ok:
                    raise RingApiError(
                        f"Ring API request {method} {url} failed with {resp.status_code}: {resp.text}",
                        status_code=resp.status_code,
                        response_data=resp.text,
                    )

                return resp

            except requests.RequestException as exc:
                if attempt < self.max_retries:
                    sleep_time = (2 ** attempt) + random.uniform(0.1, 0.5)
                    time.sleep(sleep_time)
                    continue
                raise RingApiError(f"Network error calling {url}: {exc}") from exc

        raise RingApiError(f"Failed after {self.max_retries} attempts.")

    def get_devices(self) -> List[Dict[str, Any]]:
        """
        Lists all devices associated with authorized location.
        """
        resp = self._request("GET", "/clients_api/ring/devices")
        data = resp.json()
        if isinstance(data, dict):
            # Ring API typically returns dict with doorbots, stickup_cams, authorized_doorbots, etc.
            all_devices = []
            for category in ["doorbots", "stickup_cams", "authorized_doorbots", "chimes", "base_stations"]:
                all_devices.extend(data.get(category, []))
            return all_devices
        return data if isinstance(data, list) else []

    def get_device_health(self, device_id: str) -> Dict[str, Any]:
        """
        Gets battery and connection health for a specific device.
        """
        resp = self._request("GET", f"/clients_api/ring/doorbots/{device_id}/health")
        return resp.json()

    def register_webhook_subscription(self, target_url: str, events: List[str]) -> Dict[str, Any]:
        """
        Registers a webhook delivery endpoint with Ring.
        """
        payload = {
            "endpoint_url": target_url,
            "subscribed_events": events,
            "version": "v1.1",
        }
        resp = self._request("POST", "/v1/partner/webhooks", json_data=payload)
        return resp.json()
