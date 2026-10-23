"""
Data models and Pydantic schemas for the Ring Partner Kit.
Implements the official Ring Developer API v1.1 Webhook and Device schemas.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class WebhookMeta(BaseModel):
    request_id: str
    timestamp: int  # Epoch millisecond timestamp


class DeviceState(BaseModel):
    battery_level: Optional[int] = None
    tamper_status: Optional[str] = None
    firmware_version: Optional[str] = None
    connection_status: Optional[Literal["online", "offline"]] = "online"


class EventAttributes(BaseModel):
    timestamp: int  # Milliseconds since epoch
    state: Optional[DeviceState] = None
    extra: Optional[Dict[str, Any]] = Field(default_factory=dict)


class WebhookData(BaseModel):
    id: str  # Event ID
    device_id: str
    account_id: str
    location_id: str
    type: Literal["motion", "ding", "contact_sensor_faulted", "contact_sensor_cleared", "device_health"]
    sub_type: Optional[Literal["human", "general", "vehicle", "package", "none"]] = None
    attributes: EventAttributes


class RingWebhookEnvelope(BaseModel):
    meta: WebhookMeta
    data: WebhookData


class DeviceInfo(BaseModel):
    device_id: str
    description: str
    kind: str  # doorbell, motion_sensor, contact_sensor, camera
    location_id: str
    battery_life: Optional[int] = None
    status: str = "online"


class NormalizedSignal(BaseModel):
    signal_id: str
    circle_id: str
    timestamp_utc: str
    device_id: str
    device_label: str
    event_type: str
    sub_type: Optional[str] = None
    confidence: float = 1.0

    @classmethod
    def from_webhook(
        cls,
        payload: RingWebhookEnvelope,
        circle_id: str,
        device_label: Optional[str] = None,
    ) -> "NormalizedSignal":
        ts_sec = payload.data.attributes.timestamp / 1000.0
        dt = datetime.fromtimestamp(ts_sec, tz=timezone.utc)
        label = device_label or f"device-{payload.data.device_id[:6]}"
        return cls(
            signal_id=payload.data.id,
            circle_id=circle_id,
            timestamp_utc=dt.isoformat(),
            device_id=payload.data.device_id,
            device_label=label,
            event_type=payload.data.type,
            sub_type=payload.data.sub_type,
            confidence=1.0,
        )
