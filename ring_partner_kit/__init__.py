"""
Ring Partner Kit - Open Source Developer SDK for Ring App Store Integrations.
"""

from .models import (
    DeviceInfo,
    DeviceState,
    EventAttributes,
    NormalizedSignal,
    RingWebhookEnvelope,
    WebhookData,
    WebhookMeta,
)
from .verifier import RingWebhookVerifier, SignatureVerificationError
from .client import RingApiClient, RingApiError, RingRateLimitError
from .twin import RingTwinSimulator, DEFAULT_DEVICES

__version__ = "1.0.0"

__all__ = [
    "DeviceInfo",
    "DeviceState",
    "EventAttributes",
    "NormalizedSignal",
    "RingWebhookEnvelope",
    "WebhookData",
    "WebhookMeta",
    "RingWebhookVerifier",
    "SignatureVerificationError",
    "RingApiClient",
    "RingApiError",
    "RingRateLimitError",
    "RingTwinSimulator",
    "DEFAULT_DEVICES",
    "__version__",
]
