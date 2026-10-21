"""Xtreme profile, step 5: a slow calibration of the overshoot protection value (OPV).

The calibration does not rely on the maximum modulation (MM=), which boilers like the Intergas Xtreme
ignore. It starts high and lowers the setpoint step by step, waiting each time until the flow
temperature is stable. A round ends when the boiler stays at its minimum modulation with a stable flow
below the setpoint (plateau), or switches itself off at minimum modulation (shut-off). Several rounds
are measured and the median is the result. The result seeds the self-learning OPV of step 4.

While the calibration runs, SAT's normal control loop does not send setpoints or heater commands. The
calibration refreshes the control setpoint at least every 30 seconds, so the gateway keeps the override
(and drops it as usual when Home Assistant stops).
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field, asdict
from enum import Enum
from statistics import median
from time import monotonic
from typing import Any, Deque, Optional, Tuple, TYPE_CHECKING

from homeassistant.components import persistent_notification
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .coordinator import DeviceState, SatDataUpdateCoordinator
from .xtreme_opv import LearnedOpv

if TYPE_CHECKING:
    from .climate import SatClimate

_LOGGER = logging.getLogger(__name__)

STEP_INTERVAL_SECONDS = 15

START_SETPOINT = 55.0
LOWEST_SETPOINT = 35.0
LARGE_STEP = 2.0
SMALL_STEP = 1.0
LARGE_STEP_MODULATION = 20.0

MINIMUM_MODULATION = 2.0
STABLE_WINDOW_SECONDS = 300
STABLE_MAXIMUM_RANGE = 0.5
STABLE_MINIMUM_FLAME_SECONDS = 180
PLATEAU_BELOW_SETPOINT = 0.5
STEP_TIMEOUT_SECONDS = 30 * 60
FLAME_TIMEOUT_SECONDS = 15 * 60
COOLDOWN_SECONDS = 20 * 60
COMFORT_MARGIN = 1.0

ROUNDS_TARGET = 5
ROUNDS_MAXIMUM = 8
ROUNDS_MINIMUM_VALID = 3
MAXIMUM_SPREAD = 6.0
MINIMUM_RESULT = 35.0
MAXIMUM_DURATION_SECONDS = 10 * 3600


class CalibrationPhase(str, Enum):
    IDLE = "idle"
    WAITING = "waiting"
    HEATING = "heating"
    PAUSED_HOT_WATER = "paused_hot_water"
    PAUSED_COMFORT = "paused_comfort"
    COOLDOWN = "cooldown"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_PHASES = (
    CalibrationPhase.WAITING,
    CalibrationPhase.HEATING,
    CalibrationPhase.PAUSED_HOT_WATER,
    CalibrationPhase.PAUSED_COMFORT,
    CalibrationPhase.COOLDOWN,
)


@dataclass(slots=True)
class CalibrationStep:
    setpoint: float
    flow: Optional[float]
    modulation: Optional[float]
    minutes: float
    outcome: str


@dataclass(slots=True)
class CalibrationRound:
    number: int
    started: str
    ended: Optional[str] = None
    result: Optional[str] = None
    value: Optional[float] = None
    steps: list[CalibrationStep] = field(default_factory=list)


class XtremeCalibration:
    """Runs the calibration as a background task, one step every 15 seconds."""

    _STORAGE_VERSION = 1

    def __init__(self, climate: SatClimate, coordinator: SatDataUpdateCoordinator, learned_opv: LearnedOpv, storage_key: str):
        self._hass: Optional[HomeAssistant] = None
        self._store: Optional[Store] = None
        self._storage_key = storage_key
        self._climate = climate
        self._coordinator = coordinator
        self._learned_opv = learned_opv
        self._task: Optional[asyncio.Task] = None

        self._phase: CalibrationPhase = CalibrationPhase.IDLE
        self._message: str = "Not started"
        self._report: Optional[dict[str, Any]] = None
        self._reset()

    def _reset(self) -> None:
        self._started_at: Optional[float] = None
        self._started: Optional[str] = None
        self._rounds: list[CalibrationRound] = []
        self._setpoint: float = START_SETPOINT
        self._phase_since: float = monotonic()
        self._step_started_at: float = monotonic()
        self._flame_seen: bool = False
        self._last_flow: Optional[float] = None
        self._last_modulation: Optional[float] = None
        self._window: Deque[Tuple[float, float]] = deque()

    @property
    def active(self) -> bool:
        return self._phase in ACTIVE_PHASES

    @property
    def phase(self) -> CalibrationPhase:
        return self._phase

    @property
    def attributes(self) -> dict[str, Any]:
        valid = self._valid_values()

        return {
            "message": self._message,
            "round": len(self._rounds),
            "rounds_target": ROUNDS_TARGET,
            "valid_rounds": len(valid),
            "setpoint": self._setpoint if self.active else None,
            "measurements": valid,
            "started": self._started,
            "elapsed_minutes": round((monotonic() - self._started_at) / 60, 1) if self._started_at is not None and self.active else None,
            "report": self._report,
        }

    async def async_initialize(self, hass: HomeAssistant) -> None:
        """Load the report of the last calibration."""
        self._hass = hass
        self._store = Store(hass, self._STORAGE_VERSION, self._storage_key)

        if data := await self._store.async_load():
            self._report = data.get("report")

    @callback
    def cancel(self) -> None:
        """Cancel a running calibration, for example when SAT is unloaded."""
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def async_start(self) -> bool:
        """Start the calibration in the background."""
        if self.active:
            _LOGGER.warning("Xtreme calibration: already running.")
            return False

        if self._climate.hvac_mode != HVACMode.HEAT:
            _LOGGER.warning("Xtreme calibration: the thermostat must be in heat mode to calibrate.")
            self._message = "The thermostat must be in heat mode"
            self._climate.async_write_ha_state()
            return False

        self._reset()
        self._started_at = monotonic()
        self._started = dt_util.utcnow().isoformat()
        self._setpoint = min(START_SETPOINT, self._coordinator.maximum_setpoint)
        self._set_phase(CalibrationPhase.WAITING, "Waiting until the boiler may start")
        self._start_round()

        _LOGGER.info("Xtreme calibration: started, first setpoint %.1f°C.", self._setpoint)

        self._task = self._hass.async_create_background_task(self._async_run(), "sat_xtreme_calibration")
        return True

    async def async_stop(self, reason: str = "Stopped by the user") -> None:
        """Stop the calibration and hand control back to SAT."""
        if not self.active:
            return

        _LOGGER.info("Xtreme calibration: stopping (%s).", reason)
        await self._async_finish(CalibrationPhase.CANCELLED, reason)

        if self._task is not None and self._task is not asyncio.current_task():
            self._task.cancel()

        self._task = None

    async def _async_run(self) -> None:
        try:
            while self.active:
                await self.async_step()
                await asyncio.sleep(STEP_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            if self.active:
                await self._async_finish(CalibrationPhase.CANCELLED, "Home Assistant stopped or SAT was reloaded")
            raise
        except Exception as exception:
            _LOGGER.exception("Xtreme calibration: unexpected error.")
            await self._async_finish(CalibrationPhase.FAILED, f"Unexpected error: {exception}")

    async def async_step(self) -> None:
        """Run one step of the calibration."""
        if not self.active:
            return

        now = monotonic()

        if now - self._started_at > MAXIMUM_DURATION_SECONDS:
            await self._async_conclude("Maximum duration of 10 hours reached")
            return

        if self._climate.hvac_mode != HVACMode.HEAT:
            await self._async_finish(CalibrationPhase.CANCELLED, "The thermostat left heat mode")
            return

        flow = self._coordinator.boiler_temperature
        modulation = self._coordinator.relative_modulation_value
        flame = self._coordinator.flame_active
        hot_water = self._coordinator.hot_water_active

        if self._phase == CalibrationPhase.COOLDOWN:
            await self._async_command(DeviceState.OFF)
            if now - self._phase_since >= COOLDOWN_SECONDS:
                self._start_round()
                self._set_phase(CalibrationPhase.WAITING, "Waiting until the boiler may start")
            return

        if self._too_warm():
            if self._phase != CalibrationPhase.PAUSED_COMFORT:
                self._discard_step("room too warm")
                self._set_phase(CalibrationPhase.PAUSED_COMFORT, "Paused until the room has cooled down")
            await self._async_command(DeviceState.OFF)
            return

        if self._phase == CalibrationPhase.PAUSED_COMFORT:
            if self._climate.current_temperature is not None and self._climate.target_temperature is not None and self._climate.current_temperature <= self._climate.target_temperature:
                self._set_phase(CalibrationPhase.WAITING, "Waiting until the boiler may start")
            await self._async_command(DeviceState.OFF)
            return

        if hot_water:
            if self._phase != CalibrationPhase.PAUSED_HOT_WATER:
                self._discard_step("hot water")
                self._set_phase(CalibrationPhase.PAUSED_HOT_WATER, "Paused while hot water is active")
            await self._async_command(DeviceState.OFF, refresh_only=True)
            return

        if self._phase == CalibrationPhase.PAUSED_HOT_WATER:
            self._set_phase(CalibrationPhase.WAITING, "Waiting until the boiler may start after hot water")

        if self._phase == CalibrationPhase.WAITING:
            await self._async_command(DeviceState.OFF)
            if self._anti_cycling_remaining() > 0:
                return

            self._flame_seen = False
            self._window.clear()
            self._step_started_at = now
            self._set_phase(CalibrationPhase.HEATING, f"Heating at setpoint {self._setpoint:.1f}°C")
            await self._async_command(DeviceState.ON)
            return

        # Heating
        await self._async_command(DeviceState.ON)

        if not flame:
            if self._flame_seen and self._last_modulation is not None and self._last_modulation <= MINIMUM_MODULATION and self._last_flow is not None:
                self._record_step(self._last_flow, self._last_modulation, "shut_off")
                await self._async_end_round("shut_off", self._last_flow)
                return

            if self._flame_seen:
                # Switched off while still modulating: try again after the anti-cycling time
                self._record_step(self._last_flow, self._last_modulation, "switched off while modulating")
                self._set_phase(CalibrationPhase.WAITING, "Boiler switched off while modulating, waiting")
                return

            if now - self._step_started_at > FLAME_TIMEOUT_SECONDS:
                self._record_step(None, None, "no flame")
                await self._async_end_round("failed", None)
            return

        if flow is None:
            return

        self._flame_seen = True
        self._last_flow = flow
        self._last_modulation = modulation

        self._window.append((now, flow))
        while self._window and now - self._window[0][0] > STABLE_WINDOW_SECONDS:
            self._window.popleft()

        flame_seconds = self._coordinator.flame.latest_on_time_seconds or 0
        window_full = now - self._window[0][0] >= STABLE_WINDOW_SECONDS * 0.9
        flows = [value for _, value in self._window]

        if window_full and flame_seconds >= STABLE_MINIMUM_FLAME_SECONDS and max(flows) - min(flows) <= STABLE_MAXIMUM_RANGE:
            stable_flow = round(median(flows), 2)

            if modulation is not None and modulation <= MINIMUM_MODULATION and stable_flow <= self._setpoint - PLATEAU_BELOW_SETPOINT:
                self._record_step(stable_flow, modulation, "plateau")
                await self._async_end_round("plateau", stable_flow)
                return

            self._record_step(stable_flow, modulation, "stable")
            await self._async_lower_setpoint(modulation)
            return

        if now - self._step_started_at > STEP_TIMEOUT_SECONDS:
            self._record_step(flow, modulation, "not stable within 30 minutes")
            await self._async_lower_setpoint(modulation)

    async def _async_lower_setpoint(self, modulation: Optional[float]) -> None:
        step = LARGE_STEP if modulation is not None and modulation > LARGE_STEP_MODULATION else SMALL_STEP
        self._setpoint = round(self._setpoint - step, 1)
        self._window.clear()
        self._step_started_at = monotonic()

        if self._setpoint < LOWEST_SETPOINT:
            _LOGGER.info("Xtreme calibration: still modulating at the lowest setpoint, the round failed.")
            self._setpoint = LOWEST_SETPOINT
            await self._async_end_round("failed", None)
            return

        _LOGGER.debug("Xtreme calibration: lowering the setpoint to %.1f°C.", self._setpoint)
        self._message = f"Heating at setpoint {self._setpoint:.1f}°C"

    def _start_round(self) -> None:
        self._rounds.append(CalibrationRound(number=len(self._rounds) + 1, started=dt_util.utcnow().isoformat()))
        self._setpoint = min(START_SETPOINT, self._coordinator.maximum_setpoint)
        self._window.clear()
        self._flame_seen = False
        self._last_flow = None
        self._last_modulation = None
        self._step_started_at = monotonic()

        _LOGGER.info("Xtreme calibration: starting round %d.", len(self._rounds))

    async def _async_end_round(self, result: str, value: Optional[float]) -> None:
        current = self._rounds[-1]
        current.ended = dt_util.utcnow().isoformat()
        current.result = result
        current.value = value

        if value is not None and value < MINIMUM_RESULT:
            current.result = "rejected"
            _LOGGER.info("Xtreme calibration: round %d measured %.1f°C, below %.0f°C, rejected.", current.number, value, MINIMUM_RESULT)
        else:
            _LOGGER.info("Xtreme calibration: round %d ended with %s (%s).", current.number, result, value)

        await self._async_command(DeviceState.OFF)

        if len(self._valid_values()) >= ROUNDS_TARGET or len(self._rounds) >= ROUNDS_MAXIMUM:
            await self._async_conclude("All rounds done")
            return

        self._set_phase(CalibrationPhase.COOLDOWN, "Cooling down before the next round")

    async def _async_conclude(self, reason: str) -> None:
        values = self._valid_values()

        if len(values) < ROUNDS_MINIMUM_VALID:
            await self._async_finish(CalibrationPhase.FAILED, f"{reason}: only {len(values)} valid rounds, at least {ROUNDS_MINIMUM_VALID} needed")
            return

        result = round(median(values), 1)
        spread = round(max(values) - min(values), 1)

        if result < MINIMUM_RESULT:
            await self._async_finish(CalibrationPhase.FAILED, f"{reason}: unrealistic result {result}°C")
            return

        if spread > MAXIMUM_SPREAD:
            await self._async_finish(CalibrationPhase.FAILED, f"{reason}: spread of {spread}°C is too large to be reliable")
            return

        self._learned_opv.seed(result)
        await self._async_finish(CalibrationPhase.SUCCEEDED, f"{reason}: OPV {result}°C (spread {spread}°C)", result=result, spread=spread)

    async def _async_finish(self, phase: CalibrationPhase, message: str, result: Optional[float] = None, spread: Optional[float] = None) -> None:
        self._set_phase(phase, message)

        values = self._valid_values()
        self._report = {
            "outcome": phase.value,
            "message": message,
            "result": result,
            "spread": spread,
            "minimum": min(values) if values else None,
            "maximum": max(values) if values else None,
            "started": self._started,
            "ended": dt_util.utcnow().isoformat(),
            "duration_minutes": round((monotonic() - self._started_at) / 60, 1) if self._started_at is not None else None,
            "rounds": [asdict(calibration_round) for calibration_round in self._rounds],
        }

        _LOGGER.info("Xtreme calibration: %s - %s", phase.value, message)

        # Hand control back to SAT: turn the demand off, the next control loop takes over
        try:
            await self._coordinator.async_set_heater_state(DeviceState.OFF)
        except Exception:
            _LOGGER.exception("Xtreme calibration: could not turn the heater off.")

        if self._store is not None:
            await self._store.async_save({"report": self._report})

        if self._hass is None:
            return

        persistent_notification.async_create(
            self._hass,
            self._notification_text(),
            title=f"SAT (Xtreme fork) calibration {phase.value}",
            notification_id="sat_xtreme_calibration",
        )

        self._climate.schedule_control_heating_loop(force=True)
        self._climate.async_write_ha_state()

    async def _async_command(self, state: DeviceState, refresh_only: bool = False) -> None:
        """Refresh the setpoint (heartbeat) and send the heater state when it changed."""
        await self._coordinator.async_set_control_setpoint(min(self._setpoint, self._coordinator.maximum_setpoint))

        if refresh_only:
            return

        if self._coordinator.heater_state_commanded != state:
            await self._coordinator.async_set_heater_state(state)

    def _anti_cycling_remaining(self) -> float:
        if self._coordinator.flame_active:
            return 0

        off_since = self._coordinator.flame.off_since
        if off_since is None:
            return 0

        return max(0.0, self._coordinator.xtreme_profile.anti_cycling_wait - (monotonic() - off_since))

    def _too_warm(self) -> bool:
        current = self._climate.current_temperature
        target = self._climate.target_temperature

        return current is not None and target is not None and current > target + COMFORT_MARGIN

    def _discard_step(self, reason: str) -> None:
        if self._phase == CalibrationPhase.HEATING:
            self._record_step(self._last_flow, self._last_modulation, f"discarded ({reason})")

        self._window.clear()
        self._step_started_at = monotonic()

    def _record_step(self, flow: Optional[float], modulation: Optional[float], outcome: str) -> None:
        if not self._rounds:
            return

        self._rounds[-1].steps.append(CalibrationStep(
            setpoint=self._setpoint,
            flow=flow,
            modulation=modulation,
            minutes=round((monotonic() - self._step_started_at) / 60, 1),
            outcome=outcome,
        ))

        _LOGGER.debug("Xtreme calibration: step at setpoint %.1f°C: flow %s, modulation %s, %s.", self._setpoint, flow, modulation, outcome)

    def _set_phase(self, phase: CalibrationPhase, message: str) -> None:
        self._phase = phase
        self._message = message
        self._phase_since = monotonic()

    def _valid_values(self) -> list[float]:
        return [calibration_round.value for calibration_round in self._rounds if calibration_round.result in ("plateau", "shut_off") and calibration_round.value is not None]

    def _notification_text(self) -> str:
        report = self._report or {}
        lines = [f"**{report.get('message')}**", ""]

        if report.get("result") is not None:
            lines.append(f"Result: {report['result']} °C, spread {report['spread']} °C (minimum {report['minimum']} °C, maximum {report['maximum']} °C).")

        lines.append(f"Duration: {report.get('duration_minutes')} minutes.")
        lines.append("")

        for calibration_round in report.get("rounds", []):
            lines.append(f"- Round {calibration_round['number']}: {calibration_round['result']} {calibration_round['value'] if calibration_round['value'] is not None else ''}")

        return "\n".join(lines)
