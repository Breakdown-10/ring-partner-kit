from datetime import datetime, timezone
import pytest
from ring_partner_kit.twin import RingTwinSimulator


def test_twin_generate_daily_routine():
    twin = RingTwinSimulator()
    now = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    events = twin.generate_day_routine(now)

    assert len(events) >= 5
    # Confirm morning motion exists
    wake_events = [e for e in events if e.data.device_id in ("ring-motion-hall", "ring-motion-kitch")]
    assert len(wake_events) > 0


def test_twin_anomalies_and_backfill():
    twin = RingTwinSimulator()
    now = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)

    # Missed wake routine
    skipped_events = twin.generate_day_routine(now, skip_wake=True)
    morning_hours = [
        datetime.fromtimestamp(e.data.attributes.timestamp / 1000.0, tz=timezone.utc).hour
        for e in skipped_events
    ]
    assert 7 not in morning_hours

    # 3-day history backfill
    history = twin.backfill_history(days=3, end_date=now)
    assert len(history) >= 15
