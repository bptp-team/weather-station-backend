from dataclasses import replace
from datetime import datetime, timezone

from app.models.weather import WeatherSnapshot


DEFAULT_DRAIN_RATE_ML_S = 1.25
DEFAULT_FUNNEL_ML_PER_MM = 4.42
DEFAULT_ADC_THRESHOLD = 50
DEFAULT_ADC_SCALE = 10.0


def adc_to_volume_ml(
    adc: int | float,
    *,
    threshold: int | float = DEFAULT_ADC_THRESHOLD,
    scale: float = DEFAULT_ADC_SCALE,
) -> float:
    """Convert raw water level sensor ADC to volume in mL based on calibration."""
    if adc <= threshold:
        return 0.0
    return max(0.0, float(adc - threshold) / scale)


def volume_to_precipitation_mm(
    volume_ml: float,
    *,
    ml_per_mm: float = DEFAULT_FUNNEL_ML_PER_MM,
) -> float:
    """Convert collected water volume in mL to precipitation depth in mm."""
    if volume_ml <= 0.0 or ml_per_mm <= 0.0:
        return 0.0
    return volume_ml / ml_per_mm


class PrecipitationTracker:
    """Track interval precipitation with drainage compensation."""

    def __init__(
        self,
        *,
        drain_rate_ml_s: float = DEFAULT_DRAIN_RATE_ML_S,
        funnel_ml_per_mm: float = DEFAULT_FUNNEL_ML_PER_MM,
        adc_threshold: int | float = DEFAULT_ADC_THRESHOLD,
        adc_scale: float = DEFAULT_ADC_SCALE,
    ) -> None:
        self._drain_rate_ml_s = drain_rate_ml_s
        self._funnel_ml_per_mm = funnel_ml_per_mm
        self._adc_threshold = adc_threshold
        self._adc_scale = adc_scale

        self._prev_time: datetime | None = None
        self._prev_volume_ml: float = 0.0

    def reset(self) -> None:
        """Reset the internal tracking state."""
        self._prev_time = None
        self._prev_volume_ml = 0.0

    def update(
        self,
        snapshot: WeatherSnapshot,
    ) -> WeatherSnapshot:
        """Return a snapshot enriched with calculated precipitation values."""
        if self._prev_time is not None and self._is_new_utc_day(snapshot.received_at):
            self.reset()

        current_volume_ml = adc_to_volume_ml(
            snapshot.water_level,
            threshold=self._adc_threshold,
            scale=self._adc_scale,
        )

        if self._prev_time is None:
            self._prev_time = snapshot.received_at
            self._prev_volume_ml = current_volume_ml
            return replace(
                snapshot,
                precipitation_interval=0.0,
            )

        delta_seconds = (snapshot.received_at - self._prev_time).total_seconds()
        if delta_seconds < 0:
            delta_seconds = 0.0

        if self._prev_volume_ml > 0.0 and self._drain_rate_ml_s > 0.0:
            potential_drain = self._drain_rate_ml_s * delta_seconds
            volume_drained = min(self._prev_volume_ml, potential_drain)
        else:
            volume_drained = 0.0

        volume_rain = (current_volume_ml - self._prev_volume_ml) + volume_drained
        if volume_rain < 0.0:
            volume_rain = 0.0

        interval_mm = volume_to_precipitation_mm(
            volume_rain,
            ml_per_mm=self._funnel_ml_per_mm,
        )

        self._prev_time = snapshot.received_at
        self._prev_volume_ml = current_volume_ml

        return replace(
            snapshot,
            precipitation_interval=interval_mm,
        )

    def _is_new_utc_day(self, received_at: datetime) -> bool:
        assert self._prev_time is not None
        return received_at.astimezone(timezone.utc).date() != self._prev_time.astimezone(timezone.utc).date()
