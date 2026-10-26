"""Xtreme profile, step 4: learn the overshoot protection value (OPV) during normal operation.

The OPV is the flow temperature at which the boiler, burning at its minimum power, is in balance with
the heat the house takes. Two signals are used:

- Plateau: the boiler burns at about 0 % modulation for a few minutes (heating, no hot water) and the
  flow temperature stays stable below the setpoint. The boiler cannot go lower, so this flow
  temperature is a direct measurement of the OPV. It can move the estimate up and down.
- Self shut-off: the boiler burns at about 0 % modulation and switches itself off while the heating
  demand is still on and the flow is clearly below the setpoint. The flow kept rising at minimum power,
  so the balance lies above this flow temperature. This is only a lower bound, so it can only move the
  estimate up.

A shut-off at or above the setpoint says nothing about the OPV: in PWM mode the setpoint is the OPV
itself, so that shut-off flow is the setpoint plus the boiler's hysteresis. Counting it would raise the
OPV, then the setpoint, then the shut-off flow, until the maximum.

"Minimum modulation" is learned per boiler: every heating burn gives one value, the lowest modulation it
reported (after the first minute, and only when two readings in a row agree). The limit is a low percentile of
those values plus a margin, and never below the minimum the boiler reports itself. Every burn counts once,
short or long; the start peak needs no special handling, because it is high. Until there are enough burns, the
fixed limit of 2 % is used.
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, asdict
from statistics import median
from time import monotonic
from typing import Any, Deque, Optional, Tuple, TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .opv_model import ModelSample, OpvModel

if TYPE_CHECKING:
    from ..boiler import BoilerState
    from ..flame import FlameState

_LOGGER = logging.getLogger(__name__)

OPV_MODE_OFF = "off"
OPV_MODE_LEARN = "learn"
OPV_MODE_APPLY = "apply"
OPV_MODES = [OPV_MODE_OFF, OPV_MODE_LEARN, OPV_MODE_APPLY]

# The default lowest OPV; it can be changed with the option "Lowest learned OPV"
OPV_MINIMUM = 40.0
OPV_MAXIMUM = 55.0
OPV_MARGIN = 1.0
OPV_ALPHA = 0.1
OPV_MAXIMUM_STEP = 1.0

# The fixed modulation limit, used until enough modulation data has been collected
SAMPLE_MAXIMUM_MODULATION = 2.0

# The adaptive modulation limit: a low percentile of the lowest modulation of each heating burn plus a margin
MODULATION_PERCENTILE = 0.10
MODULATION_MARGIN = 5.0
MODULATION_WINDOW_SECONDS = 7 * 24 * 3600
MODULATION_IGNITION_SECONDS = 60.0
MODULATION_MINIMUM_BURNS = 30
MODULATION_MAXIMUM_BURNS = 2000
# The learned limit never goes above this, unless the boiler reports a higher minimum itself
MODULATION_CEILING = 30.0

# Where the boiler normally switches itself off, relative to the setpoint, is learned from its recent shut-offs;
# a shut-off only counts as an OPV sample when the flow stayed more than the margin below that point
SHUT_OFF_MARGIN = 2.0
SHUT_OFF_SAMPLES = 20
SHUT_OFF_MINIMUM_SAMPLES = 5
SAMPLE_MINIMUM_FLAME_SECONDS = 180.0
SAMPLE_HOT_WATER_QUIET_SECONDS = 300.0
PLATEAU_WINDOW_SECONDS = 180.0
PLATEAU_MAXIMUM_RANGE = 0.5
PLATEAU_BELOW_SETPOINT = 0.5

SAMPLE_PLATEAU = "plateau"
SAMPLE_SHUT_OFF = "shut_off"
SAMPLE_CALIBRATION = "calibration"

# Why the last burn did not give a sample
REJECT_MODULATION = "modulation_too_high"
REJECT_TOO_SHORT = "burn_too_short"
REJECT_HOT_WATER = "hot_water"
REJECT_NO_PLATEAU = "no_plateau"
REJECT_AT_SETPOINT = "at_setpoint"

RECENT_SAMPLES = 20


def _wall_time() -> float:
    return dt_util.utcnow().timestamp()


def _percentile(values: list[float], quantile: float) -> float:
    """The quantile of sorted values, interpolated between the two nearest values."""
    position = (len(values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


@dataclass(frozen=True, slots=True)
class OpvSample:
    time: str
    type: str
    value: float
    estimate: float


class LearnedOpv:
    """Learns the OPV from the data the boiler reports and stores it across restarts."""

    _STORAGE_VERSION = 1

    def __init__(self, mode: str, configured_value: float, maximum_setpoint: float, storage_key: str, minimum: float = OPV_MINIMUM,
                 model: bool = False, heat_pump: bool = False, minimum_burn_seconds: float = 360):
        self._mode: str = mode if mode in OPV_MODES else OPV_MODE_OFF
        self._maximum_setpoint: float = maximum_setpoint
        self._minimum: float = float(minimum)

        # The model of the burn that chooses the OPV; its value only counts when the learned OPV is applied
        self.model = OpvModel(
            enabled=model and self._mode != OPV_MODE_OFF,
            applied=self._mode == OPV_MODE_APPLY,
            heat_pump=heat_pump,
            minimum_burn_seconds=minimum_burn_seconds,
            limits=lambda: (self._minimum, min(OPV_MAXIMUM, self._maximum_setpoint)),
        )
        self._model_saved_at: Optional[float] = None
        self._storage_key: str = storage_key
        self._store: Optional[Store] = None

        # The estimate starts so that the applied value equals the configured OPV
        self._estimate: float = configured_value - OPV_MARGIN
        self._source: str = "configured"
        self._sample_count: int = 0
        self._last_update: Optional[str] = None
        self._samples: Deque[OpvSample] = deque(maxlen=RECENT_SAMPLES)

        # Observation state
        self._window: Deque[Tuple[float, float]] = deque()
        self._plateau_sampled: bool = False
        self._last_eligible_flow: Optional[float] = None
        self._last_eligible_setpoint: Optional[float] = None
        self._previous_flame_active: bool = False

        # Modulation reported during heating burns, as (time, modulation), for the adaptive limit
        self._modulation_burns: Deque[Tuple[float, float]] = deque(maxlen=MODULATION_MAXIMUM_BURNS)
        self._burn_modulation_previous: Optional[float] = None
        self._burn_modulation_lowest: Optional[float] = None
        self._burn_heating_only: bool = True
        self._boiler_minimum_modulation: Optional[float] = None

        # Flow minus setpoint at the recent self shut-offs, and the flow and setpoint of the current burn
        self._shut_off_offsets: Deque[float] = deque(maxlen=SHUT_OFF_SAMPLES)
        self._burn_flow: Optional[float] = None
        self._burn_setpoint: Optional[float] = None

        # Why the current and the last burn did not give a sample
        self._burn_reason: Optional[str] = None
        self._burn_sampled: bool = False
        self._last_burn_result: Optional[str] = None

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def enabled(self) -> bool:
        return self._mode != OPV_MODE_OFF

    @property
    def applied(self) -> bool:
        return self._mode == OPV_MODE_APPLY

    @property
    def estimate(self) -> float:
        return round(self._estimate, 2)

    @property
    def value(self) -> float:
        """The OPV to use: the value of the model when it has chosen one, otherwise the estimate plus a safety
        margin, plus a running test step, within the limits."""
        base = self.model.applied_value if self.applied and self.model.enabled and self.model.applied_value is not None else self.base_value
        return self.limit(base + self.model.test_offset)

    @property
    def base_value(self) -> float:
        """The learned OPV without the model: the estimate plus a safety margin, within the limits."""
        return self.limit(self._estimate + OPV_MARGIN)

    def limit(self, value: float) -> float:
        return round(min(max(value, self._minimum), OPV_MAXIMUM, self._maximum_setpoint), 1)

    def with_test(self, value: float) -> float:
        """Add a running test step to an OPV that does not come from the learned value (with "learn")."""
        return self.limit(value + self.model.test_offset) if self.model.test_offset else value

    @property
    def minimum(self) -> float:
        return self._minimum

    @property
    def modulation_limit(self) -> float:
        """The highest modulation that counts as burning at the minimum."""
        cutoff = _wall_time() - MODULATION_WINDOW_SECONDS
        values = sorted(value for time, value in self._modulation_burns if time >= cutoff)

        if len(values) < MODULATION_MINIMUM_BURNS:
            limit = SAMPLE_MAXIMUM_MODULATION
        else:
            limit = min(_percentile(values, MODULATION_PERCENTILE) + MODULATION_MARGIN, MODULATION_CEILING)

        if self._boiler_minimum_modulation is not None:
            limit = max(limit, self._boiler_minimum_modulation)

        return round(limit, 1)

    @property
    def shut_off_offset(self) -> Optional[float]:
        """Where the boiler normally switches itself off: the median flow minus setpoint, once there are enough shut-offs."""
        if len(self._shut_off_offsets) < SHUT_OFF_MINIMUM_SAMPLES:
            return None

        return round(median(self._shut_off_offsets), 1)

    @property
    def modulation_burn_count(self) -> int:
        cutoff = _wall_time() - MODULATION_WINDOW_SECONDS
        return sum(1 for time, _ in self._modulation_burns if time >= cutoff)

    @property
    def sample_count(self) -> int:
        return self._sample_count

    @property
    def last_update(self) -> Optional[str]:
        return self._last_update

    @property
    def attributes(self) -> dict[str, Any]:
        last = self._samples[-1] if self._samples else None

        return {
            "mode": self._mode,
            "estimate": self.estimate,
            "margin": OPV_MARGIN,
            "source": self._source,
            "sample_count": self._sample_count,
            "last_update": self._last_update,
            "last_sample_type": last.type if last else None,
            "last_sample_value": last.value if last else None,
            "minimum": self._minimum,
            "modulation_limit": self.modulation_limit,
            "modulation_burns": self.modulation_burn_count,
            "shut_off_offset": self.shut_off_offset,
            "shut_off_offset_samples": len(self._shut_off_offsets),
            "last_burn_result": self._last_burn_result,
            **self.model.attributes(self.value),
            "recent_samples": [asdict(sample) for sample in self._samples],
        }

    async def async_initialize(self, hass: HomeAssistant) -> None:
        """Load the learned value from storage (also when learning is off, so a calibration result is kept)."""
        self._store = Store(hass, self._STORAGE_VERSION, self._storage_key)

        if not (data := await self._store.async_load()):
            _LOGGER.debug("Xtreme profile: no learned OPV stored yet, starting from %.1f°C.", self.value)
            return

        self._estimate = float(data.get("estimate", self._estimate))
        self._source = str(data.get("source", self._source))
        self._sample_count = int(data.get("sample_count", 0))
        self._last_update = data.get("last_update")
        self._samples = deque((OpvSample(**sample) for sample in data.get("samples", [])), maxlen=RECENT_SAMPLES)
        # Version 36 keeps one value per burn; the values per minute of versions 34 and 35 ("modulation") are dropped
        self._modulation_burns = deque(((float(time), float(value)) for time, value in data.get("modulation_burns", [])), maxlen=MODULATION_MAXIMUM_BURNS)
        self._shut_off_offsets = deque((float(value) for value in data.get("shut_off_offsets", [])), maxlen=SHUT_OFF_SAMPLES)
        # The search of versions 34 and 35 ("search") is replaced by the model and not read
        self.model.load(data.get("model"))

        _LOGGER.debug("Xtreme profile: loaded learned OPV %.1f°C (estimate %.2f°C, %d samples).", self.value, self._estimate, self._sample_count)

    def seed(self, value: float, source: str = SAMPLE_CALIBRATION) -> None:
        """Start learning from a new value, for example the result of a calibration."""
        self._estimate = min(max(value, self._minimum - OPV_MARGIN), OPV_MAXIMUM)
        self._source = source
        self._sample_count = 0
        self._record(source, value)

        _LOGGER.info("Xtreme profile: learned OPV seeded from %s with %.1f°C.", source, value)

    def observe(self, boiler: BoilerState, flame: FlameState, heating_demand: bool, seconds_since_hot_water: Optional[float],
                boiler_minimum_modulation: Optional[float] = None) -> None:
        """Observe one control loop and update the estimate when a valid sample is found."""
        if not self.enabled or boiler.flow_temperature is None:
            return

        now = monotonic()
        self._boiler_minimum_modulation = boiler_minimum_modulation
        flame_active = bool(boiler.flame_active)
        hot_water_quiet = not boiler.hot_water_active and (seconds_since_hot_water is None or seconds_since_hot_water >= SAMPLE_HOT_WATER_QUIET_SECONDS)
        on_seconds = flame.latest_on_time_seconds

        # Self shut-off: the flame went out at minimum modulation while the heating demand is still on
        if self._previous_flame_active and not flame_active:
            if heating_demand and hot_water_quiet and self._last_eligible_flow is not None:
                self._on_shut_off(self._last_eligible_flow, self._last_eligible_setpoint)

            # Learn where the boiler normally switches itself off, from every heating shut-off
            if heating_demand and hot_water_quiet and self._burn_flow is not None and self._burn_setpoint is not None:
                self._shut_off_offsets.append(round(self._burn_flow - self._burn_setpoint, 1))
                if self._store is not None:
                    self._store.async_delay_save(self._data_to_save, 60)

            self._burn_flow = None
            self._burn_setpoint = None

            # One value per heating burn for the adaptive modulation limit
            if self._burn_heating_only and self._burn_modulation_lowest is not None:
                self._modulation_burns.append((_wall_time(), self._burn_modulation_lowest))
                if self._store is not None:
                    self._store.async_delay_save(self._data_to_save, 60)

            self._last_burn_result = self._last_burn_result if self._burn_sampled else self._burn_reason

        if flame_active and not self._previous_flame_active:
            self._burn_reason = None
            self._burn_sampled = False
            self._burn_modulation_previous = None
            self._burn_modulation_lowest = None
            self._burn_heating_only = True

        self._previous_flame_active = flame_active

        if flame_active and heating_demand:
            self._burn_flow = boiler.flow_temperature
            self._burn_setpoint = boiler.setpoint

        # The lowest modulation of this burn, from two readings in a row, after the ignition
        if flame_active:
            if not hot_water_quiet:
                self._burn_heating_only = False
            elif heating_demand and on_seconds is not None and on_seconds >= MODULATION_IGNITION_SECONDS:
                self._track_burn_modulation(boiler.relative_modulation_level)

        minimum_modulation = boiler.relative_modulation_level is not None and boiler.relative_modulation_level <= self.modulation_limit
        long_enough = on_seconds is not None and on_seconds >= SAMPLE_MINIMUM_FLAME_SECONDS
        eligible = heating_demand and flame_active and hot_water_quiet and minimum_modulation and long_enough

        if not eligible:
            if flame_active and heating_demand:
                if not hot_water_quiet:
                    self._burn_reason = REJECT_HOT_WATER
                elif not long_enough:
                    self._burn_reason = self._burn_reason or REJECT_TOO_SHORT
                elif not minimum_modulation:
                    self._burn_reason = REJECT_MODULATION

            if not flame_active:
                self._plateau_sampled = False
                self._last_eligible_flow = None
                self._last_eligible_setpoint = None

            if self._window:
                self._window.clear()

            return

        self._burn_reason = REJECT_NO_PLATEAU if self._burn_reason in (None, REJECT_TOO_SHORT) else self._burn_reason
        self._last_eligible_flow = boiler.flow_temperature
        self._last_eligible_setpoint = boiler.setpoint
        self._window.append((now, boiler.flow_temperature))

        while self._window and now - self._window[0][0] > PLATEAU_WINDOW_SECONDS:
            self._window.popleft()

        if self._plateau_sampled or len(self._window) < 3 or now - self._window[0][0] < PLATEAU_WINDOW_SECONDS * 0.9:
            return

        flows = [flow for _, flow in self._window]
        if max(flows) - min(flows) > PLATEAU_MAXIMUM_RANGE:
            return

        plateau = median(flows)
        if boiler.setpoint is None or plateau > boiler.setpoint - PLATEAU_BELOW_SETPOINT:
            self._burn_reason = REJECT_AT_SETPOINT
            _LOGGER.debug("Xtreme profile: stable flow %.1f°C at minimum modulation, but not below the setpoint, no OPV sample.", plateau)
            return

        self._plateau_sampled = True
        self._burn_sampled = True
        self._last_burn_result = SAMPLE_PLATEAU
        self._on_plateau(plateau)

    def _track_burn_modulation(self, modulation: Optional[float]) -> None:
        if modulation is None:
            return

        modulation = float(modulation)
        if self._burn_modulation_previous is not None:
            # A value only counts when two readings in a row reach it, so one odd reading does not
            agreed = max(self._burn_modulation_previous, modulation)
            if self._burn_modulation_lowest is None or agreed < self._burn_modulation_lowest:
                self._burn_modulation_lowest = agreed

        self._burn_modulation_previous = modulation

    def update_model(self, sample: ModelSample) -> None:
        """Feed one control loop to the model of the burn and save its state now and then."""
        if not self.model.enabled:
            return

        self.model.update(sample, self.base_value)

        saved_long_ago = self._model_saved_at is None or sample.time - self._model_saved_at >= 600
        if self._store is not None and (self.model.changed or saved_long_ago):
            self.model.changed = False
            self._model_saved_at = sample.time
            self._store.async_delay_save(self._data_to_save, 10)

    def _on_plateau(self, flow: float) -> None:
        step = max(-OPV_MAXIMUM_STEP, min(OPV_MAXIMUM_STEP, OPV_ALPHA * (flow - self._estimate)))
        self._estimate += step
        self.model.on_plateau()
        self._record(SAMPLE_PLATEAU, flow)

        _LOGGER.info("Xtreme profile: OPV plateau sample %.1f°C, estimate now %.2f°C (OPV %.1f°C).", flow, self._estimate, self.value)

    def _on_shut_off(self, flow: float, setpoint: Optional[float]) -> None:
        # At or above the setpoint the boiler just reached it: in PWM that is the OPV itself plus hysteresis
        if setpoint is None or flow > setpoint - PLATEAU_BELOW_SETPOINT:
            self._burn_reason = REJECT_AT_SETPOINT
            _LOGGER.debug("Xtreme profile: boiler shut off at %.1f°C, at the setpoint %s°C, no OPV update.", flow, setpoint)
            return

        # Not clearly below where this boiler normally switches itself off
        if (offset := self.shut_off_offset) is not None and flow - setpoint > offset - SHUT_OFF_MARGIN:
            self._burn_reason = REJECT_AT_SETPOINT
            _LOGGER.debug("Xtreme profile: boiler shut off at %.1f°C, near its usual point (%+.1f°C from the setpoint), no OPV update.", flow, offset)
            return

        if flow <= self._estimate:
            _LOGGER.debug("Xtreme profile: boiler shut off at %.1f°C, not above the estimate %.2f°C, no OPV update.", flow, self._estimate)
            return

        step = min(OPV_MAXIMUM_STEP, OPV_ALPHA * (flow - self._estimate))
        self._estimate += step
        self._burn_sampled = True
        self._last_burn_result = SAMPLE_SHUT_OFF
        self._record(SAMPLE_SHUT_OFF, flow)

        _LOGGER.info("Xtreme profile: boiler shut off at minimum modulation at %.1f°C, estimate raised to %.2f°C (OPV %.1f°C).", flow, self._estimate, self.value)

    def _record(self, sample_type: str, value: float) -> None:
        self._last_update = dt_util.utcnow().isoformat()

        if sample_type != SAMPLE_CALIBRATION:
            self._sample_count += 1

        self._samples.append(OpvSample(time=self._last_update, type=sample_type, value=round(value, 2), estimate=round(self._estimate, 2)))

        if self._store is not None:
            self._store.async_delay_save(self._data_to_save, 10)

    def _data_to_save(self) -> dict[str, Any]:
        return {
            "estimate": self._estimate,
            "source": self._source,
            "sample_count": self._sample_count,
            "last_update": self._last_update,
            "samples": [asdict(sample) for sample in self._samples],
            "modulation_burns": [[round(time), value] for time, value in self._modulation_burns],
            "shut_off_offsets": list(self._shut_off_offsets),
            "model": self.model.to_dict(),
        }
