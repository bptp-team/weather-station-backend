from datetime import datetime, timedelta, timezone

import pytest

from app.core.settings import Settings
from app.main import create_app
from app.models.weather import WeatherSnapshot
from app.utils.precipitation import (
    PrecipitationTracker,
    adc_to_volume_ml,
    volume_to_precipitation_mm,
)


CALIBRATION = {"threshold": 400, "scale": 10.0}


def make_tracker(drain_rate_ml_s: float = 1.25) -> PrecipitationTracker:
    return PrecipitationTracker(
        drain_rate_ml_s=drain_rate_ml_s,
        funnel_ml_per_mm=4.42,
        adc_threshold=CALIBRATION["threshold"],
        adc_scale=CALIBRATION["scale"],
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


def test_settings_default_uses_updated_rain_adc_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEATHER_RAIN_ADC_THRESHOLD", raising=False)
    assert Settings(_env_file=None).rain_adc_threshold == 600


def test_dry_probe_reading_yields_no_volume() -> None:
    dry_probe_adc = 283
    assert adc_to_volume_ml(dry_probe_adc, **CALIBRATION) == 0.0


def test_settings_build_tracker_with_configured_calibration() -> None:
    settings = Settings(rain_adc_threshold=1000, rain_adc_scale=20.0, rain_funnel_ml_per_mm=2.0, rain_drain_rate_ml_s=0.0)
    tracker = settings.create_precipitation_tracker()
    t0 = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)

    tracker.update(make_snapshot(t0, water_level=900))
    reading = tracker.update(make_snapshot(t0 + timedelta(seconds=10), water_level=1200))

    # (1200 - 1000) / 20 = 10 mL; 10 / 2.0 = 5 mm
    assert reading.precipitation_interval == pytest.approx(5.0)


def test_app_exposes_tracker_factory_built_from_settings() -> None:
    app = create_app(settings=Settings(rain_adc_threshold=1000))
    tracker = app.state.precipitation_tracker_factory()
    t0 = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)

    tracker.update(make_snapshot(t0, water_level=0))
    reading = tracker.update(make_snapshot(t0 + timedelta(seconds=10), water_level=700))

    assert reading.precipitation_interval == 0.0


def test_adc_to_volume_ml_below_or_at_threshold() -> None:
    assert adc_to_volume_ml(0, **CALIBRATION) == 0.0
    assert adc_to_volume_ml(399, **CALIBRATION) == 0.0
    assert adc_to_volume_ml(400, **CALIBRATION) == 0.0


def test_adc_to_volume_ml_above_threshold() -> None:
    # (100 - 400) / 10 = 5.0 mL
    assert adc_to_volume_ml(450, **CALIBRATION) == pytest.approx(5.0)
    # (150 - 400) / 10 = 10.0 mL
    assert adc_to_volume_ml(500, **CALIBRATION) == pytest.approx(10.0)
    # (250 - 400) / 10 = 20.0 mL
    assert adc_to_volume_ml(600, **CALIBRATION) == pytest.approx(20.0)
    # (350 - 400) / 10 = 30.0 mL
    assert adc_to_volume_ml(700, **CALIBRATION) == pytest.approx((700 - 400) / 10.0)


def test_volume_to_precipitation_mm() -> None:
    assert volume_to_precipitation_mm(0.0, ml_per_mm=4.42) == 0.0
    # 4.42 mL -> 1.0 mm
    assert volume_to_precipitation_mm(4.42, ml_per_mm=4.42) == pytest.approx(1.0)
    # 44.2 mL -> 10.0 mm
    assert volume_to_precipitation_mm(44.2, ml_per_mm=4.42) == pytest.approx(10.0)


def test_tracker_first_reading_establishes_baseline() -> None:
    tracker = make_tracker()
    t0 = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
    reading = tracker.update(make_snapshot(t0, water_level=500))

    assert reading.precipitation_interval == 0.0


def test_tracker_computes_rain_with_drain_compensation() -> None:
    tracker = make_tracker(drain_rate_ml_s=1.25)
    t0 = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 6, 12, 0, 10, tzinfo=timezone.utc)  # 10 seconds later

    # t0: ADC = 500 -> V0 = 10.0 mL
    tracker.update(make_snapshot(t0, water_level=500))

    # t1: 10s elapsed. Drained = min(10.0, 1.25 * 10) = min(10.0, 12.5) = 10.0 mL
    # ADC = 600 -> V1 = 20.0 mL
    # V_rain = (V1 - V0) + V_drained = (20.0 - 10.0) + 10.0 = 20.0 mL
    # Rain mm = 20.0 / 4.42 ~= 4.5248868778 mm
    reading = tracker.update(make_snapshot(t1, water_level=600))

    expected_rain_mm = 20.0 / 4.42
    assert reading.precipitation_interval == pytest.approx(expected_rain_mm)


def test_tracker_pure_drainage_yields_zero_rain() -> None:
    tracker = make_tracker(drain_rate_ml_s=1.25)
    t0 = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 6, 12, 0, 2, tzinfo=timezone.utc)  # 2 seconds later

    # t0: ADC = 600 -> V0 = 20.0 mL
    tracker.update(make_snapshot(t0, water_level=600))

    # t1: 2s elapsed. Potential drain = 1.25 * 2 = 2.5 mL.
    # Suppose water drained by exactly 2.5 mL -> V1 = 17.5 mL -> ADC = 17.5 * 10 + 400 = 575
    # V_rain = (17.5 - 20.0) + 2.5 = 0.0 mL
    reading = tracker.update(make_snapshot(t1, water_level=575))

    assert reading.precipitation_interval == pytest.approx(0.0)


def test_tracker_computes_each_interval_independently() -> None:
    tracker = make_tracker(drain_rate_ml_s=0.0)
    t0 = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 6, 12, 0, 10, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 6, 12, 0, 20, tzinfo=timezone.utc)

    tracker.update(make_snapshot(t0, water_level=400))  # V0 = 0
    reading_1 = tracker.update(make_snapshot(t1, water_level=500))
    reading_2 = tracker.update(make_snapshot(t2, water_level=600))

    assert reading_1.precipitation_interval == pytest.approx(10.0 / 4.42)
    assert reading_2.precipitation_interval == pytest.approx(10.0 / 4.42)


def test_tracker_reset_clears_state() -> None:
    tracker = make_tracker()
    t0 = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 6, 12, 0, 10, tzinfo=timezone.utc)

    tracker.update(make_snapshot(t0, water_level=400))
    tracker.update(make_snapshot(t1, water_level=500))

    tracker.reset()
    assert tracker.update(make_snapshot(t1, water_level=500)).precipitation_interval == 0.0


def test_tracker_resets_baseline_on_new_utc_day() -> None:
    tracker = make_tracker(drain_rate_ml_s=0.0)
    before_midnight = datetime(2026, 9, 6, 23, 59, 50, tzinfo=timezone.utc)
    after_midnight = datetime(2026, 9, 7, 0, 0, 10, tzinfo=timezone.utc)

    tracker.update(make_snapshot(before_midnight, water_level=400))
    tracker.update(make_snapshot(before_midnight + timedelta(seconds=5), water_level=500))

    first_reading_of_day = tracker.update(make_snapshot(after_midnight, water_level=600))

    assert first_reading_of_day.precipitation_interval == 0.0
