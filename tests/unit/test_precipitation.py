from datetime import datetime, timedelta, timezone

import pytest

from app.models.weather import WeatherSnapshot
from app.utils.precipitation import (
    DEFAULT_ADC_SCALE,
    DEFAULT_ADC_THRESHOLD,
    DEFAULT_DRAIN_RATE_ML_S,
    DEFAULT_FUNNEL_ML_PER_MM,
    PrecipitationTracker,
    adc_to_volume_ml,
    volume_to_precipitation_mm,
)


def make_snapshot(received_at: datetime, water_level: int) -> WeatherSnapshot:
    return WeatherSnapshot(
        device_id="station-01",
        air_temperature=20.0,
        air_pressure=101325.0,
        air_humidity=50.0,
        air_quality=1,
        daylight=1000,
        water_level=water_level,
        received_at=received_at,
    )


def test_adc_to_volume_ml_below_or_at_threshold() -> None:
    assert adc_to_volume_ml(0) == 0.0
    assert adc_to_volume_ml(49) == 0.0
    assert adc_to_volume_ml(50) == 0.0


def test_adc_to_volume_ml_above_threshold() -> None:
    # (100 - 50) / 10 = 5.0 mL
    assert adc_to_volume_ml(100) == pytest.approx(5.0)
    # (150 - 50) / 10 = 10.0 mL
    assert adc_to_volume_ml(150) == pytest.approx(10.0)
    # (250 - 50) / 10 = 20.0 mL
    assert adc_to_volume_ml(250) == pytest.approx(20.0)
    # (350 - 50) / 10 = 30.0 mL
    assert adc_to_volume_ml(350) == pytest.approx((350 - 50) / 10.0)


def test_volume_to_precipitation_mm() -> None:
    assert volume_to_precipitation_mm(0.0) == 0.0
    # 4.42 mL -> 1.0 mm
    assert volume_to_precipitation_mm(4.42) == pytest.approx(1.0)
    # 44.2 mL -> 10.0 mm
    assert volume_to_precipitation_mm(44.2) == pytest.approx(10.0)


def test_tracker_first_reading_establishes_baseline() -> None:
    tracker = PrecipitationTracker()
    t0 = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
    reading = tracker.update(make_snapshot(t0, water_level=150))

    assert reading.precipitation_interval == 0.0


def test_tracker_computes_rain_with_drain_compensation() -> None:
    tracker = PrecipitationTracker(drain_rate_ml_s=1.25, funnel_ml_per_mm=4.42)
    t0 = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 6, 12, 0, 10, tzinfo=timezone.utc)  # 10 seconds later

    # t0: ADC = 150 -> V0 = 10.0 mL
    tracker.update(make_snapshot(t0, water_level=150))

    # t1: 10s elapsed. Drained = min(10.0, 1.25 * 10) = min(10.0, 12.5) = 10.0 mL
    # ADC = 250 -> V1 = 20.0 mL
    # V_rain = (V1 - V0) + V_drained = (20.0 - 10.0) + 10.0 = 20.0 mL
    # Rain mm = 20.0 / 4.42 ~= 4.5248868778 mm
    reading = tracker.update(make_snapshot(t1, water_level=250))

    expected_rain_mm = 20.0 / 4.42
    assert reading.precipitation_interval == pytest.approx(expected_rain_mm)


def test_tracker_pure_drainage_yields_zero_rain() -> None:
    tracker = PrecipitationTracker(drain_rate_ml_s=1.25, funnel_ml_per_mm=4.42)
    t0 = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 6, 12, 0, 2, tzinfo=timezone.utc)  # 2 seconds later

    # t0: ADC = 250 -> V0 = 20.0 mL
    tracker.update(make_snapshot(t0, water_level=250))

    # t1: 2s elapsed. Potential drain = 1.25 * 2 = 2.5 mL.
    # Suppose water drained by exactly 2.5 mL -> V1 = 17.5 mL -> ADC = 17.5 * 10 + 50 = 225
    # V_rain = (17.5 - 20.0) + 2.5 = 0.0 mL
    reading = tracker.update(make_snapshot(t1, water_level=225))

    assert reading.precipitation_interval == pytest.approx(0.0)


def test_tracker_computes_each_interval_independently() -> None:
    tracker = PrecipitationTracker(drain_rate_ml_s=0.0, funnel_ml_per_mm=4.42)
    t0 = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 6, 12, 0, 10, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 6, 12, 0, 20, tzinfo=timezone.utc)

    tracker.update(make_snapshot(t0, water_level=50))  # V0 = 0
    reading_1 = tracker.update(make_snapshot(t1, water_level=150))
    reading_2 = tracker.update(make_snapshot(t2, water_level=250))

    assert reading_1.precipitation_interval == pytest.approx(10.0 / 4.42)
    assert reading_2.precipitation_interval == pytest.approx(10.0 / 4.42)


def test_tracker_reset_clears_state() -> None:
    tracker = PrecipitationTracker()
    t0 = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 6, 12, 0, 10, tzinfo=timezone.utc)

    tracker.update(make_snapshot(t0, water_level=50))
    tracker.update(make_snapshot(t1, water_level=150))

    tracker.reset()
    assert tracker.update(make_snapshot(t1, water_level=150)).precipitation_interval == 0.0


def test_tracker_resets_baseline_on_new_utc_day() -> None:
    tracker = PrecipitationTracker(drain_rate_ml_s=0.0)
    before_midnight = datetime(2026, 9, 6, 23, 59, 50, tzinfo=timezone.utc)
    after_midnight = datetime(2026, 9, 7, 0, 0, 10, tzinfo=timezone.utc)

    tracker.update(make_snapshot(before_midnight, water_level=50))
    tracker.update(make_snapshot(before_midnight + timedelta(seconds=5), water_level=150))

    first_reading_of_day = tracker.update(make_snapshot(after_midnight, water_level=250))

    assert first_reading_of_day.precipitation_interval == 0.0
