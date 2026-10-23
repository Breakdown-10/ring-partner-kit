import pytest
from ring_partner_kit.models import (
    RingWebhookEnvelope,
    WebhookMeta,
    WebhookData,
    EventAttributes,
    DeviceState,
    NormalizedSignal,
)


def test_models_parse_ring_envelope():
    raw_payload = {
        "meta": {
            "request_id": "req-12345",
            "timestamp": 1720000000000
        },
        "data": {
            "id": "evt-999",
            "device_id": "dev-motion-1",
            "account_id": "acct-test",
            "location_id": "loc-test",
            "type": "motion",
            "sub_type": "human",
            "attributes": {
                "timestamp": 1720000000000,
                "state": {
                    "battery_level": 88,
                    "connection_status": "online"
                }
            }
        }
    }

    envelope = RingWebhookEnvelope.model_validate(raw_payload)
    assert envelope.meta.request_id == "req-12345"
    assert envelope.data.type == "motion"
    assert envelope.data.sub_type == "human"
    assert envelope.data.attributes.state.battery_level == 88

    signal = NormalizedSignal.from_webhook(envelope, circle_id="circle-1", device_label="Front Hallway")
    assert signal.signal_id == "evt-999"
    assert signal.device_label == "Front Hallway"
    assert signal.event_type == "motion"
