"""Burner cycle diagnostics: recognise every flame on/off cycle and record what happened in it.

Read only: nothing here changes the control. The idea of tracking cycles comes from the closed upstream pull
request Alexwijn/SAT#124 (GPL-3.0); this module is written for the fork and takes no code from it.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Optional

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ..const import CONF_NAME, PWMStatus
from ..coordinator import DeviceState

if TYPE_CHECKING:
    from ..climate import SatClimate
    from ..coordinator import SatDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

EVENT_CYCLE_STARTED = "sat_xtreme_cycle_started"
EVENT_CYCLE_ENDED = "sat_xtreme_cycle_ended"

STORE_PREFIX = "sat_xtreme_cycles_"
STORE_VERSION = 1
STORE_SAVE_DELAY = 30

# How many completed cycles are kept (also across restarts); enough for the 24 hour counters even when the
# boiler cycles 20 times per hour
CYCLE_HISTORY_SIZE = 500

# The flow temperature counts as "setpoint reached" from this margin below the setpoint
SETPOINT_REACHED_MARGIN = 2.0

KIND_HEATING = "heating"
KIND_HOT_WATER = "hot_water"
KIND_MIXED = "mixed"

REASON_HOT_WATER = "hot_water"
REASON_PWM_BLOCK_ENDED = "pwm_block_ended"
REASON_NO_HEATING_DEMAND = "no_heating_demand"
REASON_SETPOINT_REACHED = "setpoint_reached"
REASON_UNKNOWN = "unknown"


def _now() -> datetime:
    return dt_util.utcnow()


def _round(value: Optional[float], digits: int = 1) -> Optional[float]:
    return round(value, digits) if value is not None else None


@dataclass(frozen=True, slots=True)
class CycleSample:
    """What the boiler and SAT report at one moment."""
    time: datetime
    flame: bool
    hot_water: bool
    flow_temperature: Optional[float]
    return_temperature: Optional[float]
    setpoint: Optional[float]
    heating_demand_off: bool
    pwm_off: bool


class CycleTracker:
    """Follows the flame and records every completed burner cycle."""

    def __init__(self, coordinator: SatDataUpdateCoordinator, climate: SatClimate, entry_id: str, name: str) -> None:
        self._coordinator = coordinator
        self._climate = climate
        self._entry_id = entry_id
        self._name = name

        self._hass: Optional[HomeAssistant] = None
        self._store: Optional[Store] = None
        self._unsub: Optional[CALLBACK_TYPE] = None
        self._listeners: list[Callable[[], None]] = []

        self._history: list[dict[str, Any]] = []
        self._previous_flame: Optional[bool] = None
        self._last_end: Optional[datetime] = None
        self._current: Optional[dict[str, Any]] = None
        self._samples: list[tuple[datetime, Optional[float]]] = []
        self._kinds: set[str] = set()

    @property
    def history(self) -> list[dict[str, Any]]:
        return self._history

    @property
    def last_cycle(self) -> Optional[dict[str, Any]]:
        return self._history[-1] if self._history else None

    async def async_start(self, hass: HomeAssistant) -> None:
        """Load the history and start following the coordinator."""
        self._hass = hass
        self._store = Store(hass, STORE_VERSION, f"{STORE_PREFIX}{self._entry_id}")

        if (data := await self._store.async_load()) is not None:
            self._history = list(data.get("cycles", []))[-CYCLE_HISTORY_SIZE:]

        self._unsub = self._coordinator.async_add_listener(self._async_coordinator_updated)

    async def async_stop(self) -> None:
        """Stop following the coordinator and save the history right away."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

        if self._store is not None:
            await self._store.async_save(self._data_to_save())

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call the listener when a cycle starts or ends."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def counts(self, seconds: float, now: Optional[datetime] = None) -> dict[str, Any]:
        """Number of cycles and their average burn time that ended in the last seconds."""
        cutoff = (now or _now()) - timedelta(seconds=seconds)
        cycles = [cycle for cycle in self._history if (end := dt_util.parse_datetime(cycle["end"])) is not None and end >= cutoff]
        durations = [cycle["duration"] for cycle in cycles]

        return {
            "count": len(cycles),
            "average_duration": round(sum(durations) / len(durations)) if durations else None,
            "heating": sum(1 for cycle in cycles if cycle["kind"] == KIND_HEATING),
            "hot_water": sum(1 for cycle in cycles if cycle["kind"] == KIND_HOT_WATER),
            "mixed": sum(1 for cycle in cycles if cycle["kind"] == KIND_MIXED),
        }

    @callback
    def _async_coordinator_updated(self) -> None:
        coordinator = self._coordinator
        self.update(CycleSample(
            time=_now(),
            flame=bool(coordinator.flame_active),
            hot_water=bool(coordinator.hot_water_active),
            flow_temperature=coordinator.boiler_temperature,
            return_temperature=coordinator.return_temperature,
            setpoint=coordinator.setpoint,
            heating_demand_off=coordinator.heater_state_commanded == DeviceState.OFF,
            pwm_off=self._climate.pwm.status == PWMStatus.OFF,
        ))

    def update(self, sample: CycleSample) -> None:
        """Process one sample: start, follow or end a cycle."""
        previous, self._previous_flame = self._previous_flame, sample.flame

        # The first sample after a start-up: a cycle that is already running is not recorded
        if previous is None:
            return

        if sample.flame and not previous:
            self._start(sample)
        elif sample.flame and self._current is not None:
            self._follow(sample)
        elif not sample.flame and previous and self._current is not None:
            self._end(sample)

    def _start(self, sample: CycleSample) -> None:
        during_anti_cycling = None
        if self._last_end is not None:
            during_anti_cycling = (sample.time - self._last_end).total_seconds() < self._coordinator.xtreme_profile.anti_cycling_time

        self._current = {
            "start": sample.time.isoformat(),
            "flow_start": _round(sample.flow_temperature),
            "return_start": _round(sample.return_temperature),
            "setpoint_start": _round(sample.setpoint),
            "during_anti_cycling": during_anti_cycling,
        }
        self._samples = [(sample.time, sample.flow_temperature)]
        self._kinds = {KIND_HOT_WATER if sample.hot_water else KIND_HEATING}

        _LOGGER.debug("Xtreme cycles: cycle started (%s).", self._current)
        self._fire(EVENT_CYCLE_STARTED, {**self._current, "hot_water": sample.hot_water})

    def _follow(self, sample: CycleSample) -> None:
        self._samples.append((sample.time, sample.flow_temperature))
        self._kinds.add(KIND_HOT_WATER if sample.hot_water else KIND_HEATING)

    def _end(self, sample: CycleSample) -> None:
        start = dt_util.parse_datetime(self._current["start"])
        flows = [flow for _, flow in self._samples if flow is not None]
        kind = self._kind()

        cycle = {
            **self._current,
            "end": sample.time.isoformat(),
            "duration": round((sample.time - start).total_seconds()),
            "kind": kind,
            "end_reason": self._end_reason(sample, kind),
            "flow_min": _round(min(flows)) if flows else None,
            "flow_max": _round(max(flows)) if flows else None,
            "flow_average": _round(self._time_weighted_flow(sample.time)),
            "return_end": _round(sample.return_temperature),
            "setpoint_end": _round(sample.setpoint),
        }

        self._history = (self._history + [cycle])[-CYCLE_HISTORY_SIZE:]
        self._last_end = sample.time
        self._current = None
        self._samples = []

        if self._store is not None:
            self._store.async_delay_save(self._data_to_save, STORE_SAVE_DELAY)

        _LOGGER.debug("Xtreme cycles: cycle ended (%s).", cycle)
        self._fire(EVENT_CYCLE_ENDED, cycle)

    def _kind(self) -> str:
        if self._kinds == {KIND_HOT_WATER}:
            return KIND_HOT_WATER

        if self._kinds == {KIND_HEATING}:
            return KIND_HEATING

        return KIND_MIXED

    def _end_reason(self, sample: CycleSample, kind: str) -> str:
        if sample.hot_water or kind == KIND_HOT_WATER:
            return REASON_HOT_WATER

        if sample.heating_demand_off:
            return REASON_PWM_BLOCK_ENDED if sample.pwm_off else REASON_NO_HEATING_DEMAND

        flow = self._samples[-1][1] if sample.flow_temperature is None else sample.flow_temperature
        if flow is not None and sample.setpoint is not None and flow >= sample.setpoint - SETPOINT_REACHED_MARGIN:
            return REASON_SETPOINT_REACHED

        return REASON_UNKNOWN

    def _time_weighted_flow(self, end: datetime) -> Optional[float]:
        """The average flow temperature, each value weighted by how long it lasted."""
        points = [(time, flow) for time, flow in self._samples if flow is not None]
        if not points:
            return None

        total = weighted = 0.0
        for index, (time, flow) in enumerate(points):
            until = points[index + 1][0] if index + 1 < len(points) else end
            seconds = max(0.0, (until - time).total_seconds())
            total += seconds
            weighted += flow * seconds

        if total <= 0:
            return sum(flow for _, flow in points) / len(points)

        return weighted / total

    def _fire(self, event: str, data: dict[str, Any]) -> None:
        if self._hass is not None:
            self._hass.bus.async_fire(event, {"entry_id": self._entry_id, "name": self._name, **data})

        for listener in list(self._listeners):
            listener()

    def _data_to_save(self) -> dict[str, Any]:
        return {"cycles": self._history}


def create_cycle_tracker(coordinator: SatDataUpdateCoordinator, climate: SatClimate, config_entry) -> CycleTracker:
    return CycleTracker(coordinator, climate, config_entry.entry_id, config_entry.data.get(CONF_NAME))
