"""
Ring Twin Simulator for local testing and CI/CD.
Generates realistic, Gaussian-jittered Ring v1.1 webhook event streams
without requiring physical Ring devices.
"""
import json
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
import requests
from .models import DeviceInfo, RingWebhookEnvelope, WebhookData, WebhookMeta, EventAttributes, DeviceState
from .verifier import RingWebhookVerifier


DEFAULT_DEVICES = [
    DeviceInfo(device_id="ring-doorbell-01", description="Front Door Doorbell", kind="doorbell", location_id="loc-home", battery_life=92),
    DeviceInfo(device_id="ring-motion-hall", description="Hallway Motion", kind="motion_sensor", location_id="loc-home", battery_life=85),
    DeviceInfo(device_id="ring-motion-kitch", description="Kitchen Motion", kind="motion_sensor", location_id="loc-home", battery_life=88),
    DeviceInfo(device_id="ring-contact-meds", description="Medicine Cabinet", kind="contact_sensor", location_id="loc-home", battery_life=90),
    DeviceInfo(device_id="ring-contact-front", description="Front Door Contact", kind="contact_sensor", location_id="loc-home", battery_life=95),
]


class RingTwinSimulator:
    """
    Simulates a household of Ring devices emitting v1.1 Webhooks.
    """
    def __init__(
        self,
        account_id: str = "ring-acct-demo",
        location_id: str = "ring-loc-home",
        webhook_secret: str = "default_twin_secret_32bytes_hex!!",
        devices: Optional[List[DeviceInfo]] = None,
    ):
        self.account_id = account_id
        self.location_id = location_id
        self.secret = webhook_secret
        self.verifier = RingWebhookVerifier(secret=webhook_secret)
        self.devices = devices or list(DEFAULT_DEVICES)

    def create_event(
        self,
        device_id: str,
        event_type: str,
        timestamp_dt: datetime,
        sub_type: Optional[str] = None,
    ) -> RingWebhookEnvelope:
        epoch_ms = int(timestamp_dt.timestamp() * 1000)
        req_id = f"req-{uuid.uuid4().hex[:12]}"
        event_id = f"evt-{uuid.uuid4().hex[:12]}"

        # Look up device battery
        dev = next((d for d in self.devices if d.device_id == device_id), None)
        battery = dev.battery_life if dev else 90

        return RingWebhookEnvelope(
            meta=WebhookMeta(request_id=req_id, timestamp=epoch_ms),
            data=WebhookData(
                id=event_id,
                device_id=device_id,
                account_id=self.account_id,
                location_id=self.location_id,
                type=event_type,
                sub_type=sub_type or ("human" if event_type in ("motion", "ding") else None),
                attributes=EventAttributes(
                    timestamp=epoch_ms,
                    state=DeviceState(battery_level=battery, connection_status="online"),
                ),
            ),
        )

    def generate_day_routine(
        self,
        day_date: datetime,
        skip_wake: bool = False,
        skip_lunch: bool = False,
        extra_night_wandering: bool = False,
    ) -> List[RingWebhookEnvelope]:
        """
        Generates a 24-hour sequence of realistic elder routine events with Gaussian jitter.
        """
        events: List[RingWebhookEnvelope] = []
        base = day_date.replace(hour=0, minute=0, second=0, microsecond=0)

        # 1. Morning wake routine (~07:15)
        if not skip_wake:
            wake_jitter = random.gauss(0, 14)  # std dev 14 minutes
            wake_time = base + timedelta(hours=7, minutes=15 + wake_jitter)
            events.append(self.create_event("ring-motion-hall", "motion", wake_time, "human"))
            events.append(self.create_event("ring-motion-kitch", "motion", wake_time + timedelta(minutes=random.uniform(5, 12)), "human"))

            # Morning meds (~08:00)
            med_time = base + timedelta(hours=8, minutes=random.gauss(0, 10))
            events.append(self.create_event("ring-contact-meds", "contact_sensor_faulted", med_time))
            events.append(self.create_event("ring-contact-meds", "contact_sensor_cleared", med_time + timedelta(seconds=random.uniform(10, 45))))

        # 2. Lunch routine (~12:30)
        if not skip_lunch:
            lunch_time = base + timedelta(hours=12, minutes=30 + random.gauss(0, 15))
            events.append(self.create_event("ring-motion-kitch", "motion", lunch_time, "human"))
            events.append(self.create_event("ring-motion-hall", "motion", lunch_time + timedelta(minutes=random.uniform(20, 35)), "human"))

        # 3. Afternoon mail / front door (~15:30)
        door_time = base + timedelta(hours=15, minutes=30 + random.gauss(0, 20))
        events.append(self.create_event("ring-contact-front", "contact_sensor_faulted", door_time))
        events.append(self.create_event("ring-doorbell-01", "motion", door_time + timedelta(seconds=random.uniform(5, 15)), "human"))
        events.append(self.create_event("ring-contact-front", "contact_sensor_cleared", door_time + timedelta(minutes=random.uniform(1, 3))))

        # 4. Dinner routine (~18:45)
        dinner_time = base + timedelta(hours=18, minutes=45 + random.gauss(0, 15))
        events.append(self.create_event("ring-motion-kitch", "motion", dinner_time, "human"))

        # 5. Night Wandering Anomaly (if enabled, between 02:00 and 04:00 AM)
        if extra_night_wandering:
            night_time = base + timedelta(hours=2, minutes=45 + random.uniform(0, 30))
            events.append(self.create_event("ring-motion-hall", "motion", night_time, "human"))
            events.append(self.create_event("ring-contact-front", "contact_sensor_faulted", night_time + timedelta(minutes=8)))

        # Sort chronologically
        events.sort(key=lambda e: e.data.attributes.timestamp)
        return events

    def backfill_history(self, days: int = 21, end_date: Optional[datetime] = None) -> List[RingWebhookEnvelope]:
        """
        Generates continuous synthetic history over N days for cold-start training.
        """
        end = end_date or datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        all_events: List[RingWebhookEnvelope] = []

        for d in range(days):
            current_day = start + timedelta(days=d)
            daily = self.generate_day_routine(current_day)
            all_events.extend(daily)

        all_events.sort(key=lambda e: e.data.attributes.timestamp)
        return all_events

    def emit_webhook(self, target_url: str, envelope: RingWebhookEnvelope, timeout: float = 5.0) -> requests.Response:
        """
        Serializes and signs the envelope, sending an HTTP POST to target_url.
        """
        payload_bytes = json.dumps(envelope.model_dump()).encode("utf-8")
        sig_header, _ = self.verifier.sign(payload_bytes, timestamp=envelope.meta.timestamp)

        headers = {
            "Content-Type": "application/json",
            "X-Signature": sig_header,
            "X-Ring-Signature": sig_header,
            "User-Agent": "RingTwinSimulator/1.0",
        }
        return requests.post(target_url, data=payload_bytes, headers=headers, timeout=timeout)
