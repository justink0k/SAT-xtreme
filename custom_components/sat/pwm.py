import logging
import math
from collections import deque
from dataclasses import dataclass
from time import monotonic
from typing import Optional, Tuple, TYPE_CHECKING

from homeassistant.core import State

from .const import HEATER_STARTUP_TIMEFRAME, MINIMUM_SETPOINT, BoilerStatus, PWMStatus
from .heating_curve import HeatingCurve
from .setpoint_adjuster import SetpointAdjuster
from .xtreme_profile import XtremeProfile

if TYPE_CHECKING:
    from .flame import FlameState
    from .boiler import BoilerState

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class CycleConfig:
    """
    Encapsulates settings related to cycle time and maximum cycles.
    """
    maximum_time: int
    maximum_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class PWMState:
    """
    Encapsulates the state of the PWM control.
    """
    enabled: bool
    status: PWMStatus
    duty_cycle: Optional[Tuple[int, int]]


class PWM:
    """Implements Pulse Width Modulation (PWM) control for managing boiler operations."""

    def __init__(self, cycles: CycleConfig, heating_curve: HeatingCurve, supports_relative_modulation_management: bool, automatic_duty_cycle: bool, force: bool = False, xtreme_profile: XtremeProfile | None = None):
        """Initialize the PWM control."""
        self._alpha: float = 0.2
        self._force: bool = force
        self._last_boiler_temperature: float | None = None
        self._xtreme_profile: XtremeProfile = xtreme_profile or XtremeProfile()

        self._cycles: CycleConfig = cycles
        self._heating_curve: HeatingCurve = heating_curve
        self._automatic_duty_cycle: bool = automatic_duty_cycle

        # Timing thresholds for duty cycle management
        self._on_time_lower_threshold: float = 180

        # Xtreme profile: every burn lasts at least the minimum burn time
        if self._xtreme_profile.boiler_timing:
            self._on_time_lower_threshold = float(self._xtreme_profile.minimum_burn_time)

        self._on_time_upper_threshold: float = 3600 / max(1, self._cycles.maximum_count)
        self._on_time_max_threshold: float = self._on_time_upper_threshold * 2

        # Duty cycle percentage thresholds
        self._duty_cycle_lower_threshold: float = self._on_time_lower_threshold / self._on_time_upper_threshold
        self._duty_cycle_upper_threshold: float = 1 - self._duty_cycle_lower_threshold
        self._min_duty_cycle_percentage: float = self._duty_cycle_lower_threshold / 2

        # Xtreme profile: keep the threshold below which SAT does not burn independent of the minimum burn time
        if self._xtreme_profile.boiler_timing:
            self._min_duty_cycle_percentage = min(self._xtreme_profile.minimum_duty_cycle / 100, self._duty_cycle_lower_threshold)

        self._max_duty_cycle_percentage: float = 1 - self._min_duty_cycle_percentage

        # Initialize some helpers
        self._setpoint: Optional[float] = None
        self._setpoint_adjuster = SetpointAdjuster()
        self._setpoint_offset: int = 0.5 if supports_relative_modulation_management else 1

        # Xtreme profile: values that survive a reset, for the dashboard
        self._anti_cycling_remaining: float = 0
        self._last_block_burn_seconds: float | None = None
        self._last_block_target_seconds: float | None = None

        _LOGGER.debug(
            "Initialized PWM control with duty cycle thresholds - Lower: %.2f%%, Upper: %.2f%%, Offset: %d°C",
            self._duty_cycle_lower_threshold * 100, self._duty_cycle_upper_threshold * 100, self._setpoint_offset
        )

        self.reset()

    def reset(self) -> None:
        """Reset the PWM control."""
        self._enabled = False
        self._current_cycle: int = 0
        self._status: PWMStatus = PWMStatus.IDLE
        self._last_update: float = monotonic()
        self._duty_cycle: Tuple[int, int] | None = None

        self._last_duty_cycle_percentage: float | None = None

        # Start times of the duty cycles of the last hour (rolling window)
        self._cycle_starts: deque[float] = deque()

        # Xtreme profile: burn time bookkeeping of the current on phase
        self._on_started_at: float | None = None
        self._last_tick: float | None = None
        self._burn_seconds: float = 0
        self._flame_seen: bool = False
        self._flame_wait_expired: bool = False

    def restore(self, state: State) -> None:
        """Restore the PWM controller from a saved state."""
        if enabled := state.attributes.get("pulse_width_modulation_enabled"):
            self._enabled = bool(enabled)

    def enable(self) -> None:
        """Enable the PWM control."""
        self._enabled = True

    def disable(self) -> None:
        """Disable the PWM control."""
        self.reset()
        self._enabled = False
        self._setpoint_adjuster.reset()

    async def update(self, boiler: "BoilerState", flame: "FlameState", requested_setpoint: float) -> None:
        """Update the PWM state based on the output of a PID controller."""
        if not self._heating_curve.value or requested_setpoint is None or boiler.flow_temperature is None:
            self._status = PWMStatus.IDLE
            self._last_update = monotonic()
            self._last_boiler_temperature = boiler.flow_temperature

            _LOGGER.warning("PWM turned off due missing values.")

            return

        if self._last_boiler_temperature is None:
            self._last_boiler_temperature = boiler.flow_temperature
            _LOGGER.debug("Initialized last boiler temperature to %.1f°C", boiler.flow_temperature)

        # Count the duty cycles that started in the last 60 minutes (a rolling hour, not a fixed one)
        while self._cycle_starts and monotonic() - self._cycle_starts[0] > 3600:
            self._cycle_starts.popleft()

        self._current_cycle = len(self._cycle_starts)

        elapsed = monotonic() - self._last_update
        self._duty_cycle = self._calculate_duty_cycle(requested_setpoint, boiler)

        # Update boiler temperature if heater has just started up
        if self._status == PWMStatus.ON:
            if elapsed <= HEATER_STARTUP_TIMEFRAME:
                self._last_boiler_temperature = (self._alpha * boiler.flow_temperature + (1 - self._alpha) * self._last_boiler_temperature)

                _LOGGER.debug("Updated last boiler temperature with weighted average during startup phase.")
            else:
                self._last_boiler_temperature = boiler.flow_temperature
                _LOGGER.debug("Updated last boiler temperature to %.1f°C", boiler.flow_temperature)

        # Control the adjusted setpoint
        if flame.is_active and boiler.status not in (BoilerStatus.PUMP_STARTING, BoilerStatus.OVERSHOOT_HANDLING) and flame.latest_on_time_seconds is not None and flame.latest_on_time_seconds > 6:
            target = boiler.flow_temperature - 3
            self._setpoint = self._setpoint_adjuster.adjust(target_setpoint=target)
            _LOGGER.debug("Adjusting setpoint for active flame - Flow temp: %.1f°C, Target: %.1f°C, New setpoint: %.1f°C", boiler.flow_temperature, target, self._setpoint)
        elif flame.is_inactive and (flame.average_on_time_seconds is None or flame.average_on_time_seconds < 60):
            target = boiler.flow_temperature + 10
            self._setpoint = self._setpoint_adjuster.force(target_setpoint=target)
            _LOGGER.debug("Forcing setpoint up due to short flame cycles - Flow temp: %.1f°C, Target: %.1f°C, New setpoint: %.1f°C", boiler.flow_temperature, target, self._setpoint)
        elif self._setpoint_adjuster.current is not None:
            self._setpoint = self._setpoint_adjuster.current
            _LOGGER.debug("Maintaining current setpoint at %.1f°C", self._setpoint)

        if (
                # Check if we are above the overshoot temperature
                boiler.status == BoilerStatus.COOLING_DOWN and
                self._setpoint_adjuster.current is not None and math.floor(requested_setpoint) > math.floor(self._setpoint)
        ):
            _LOGGER.info("Setpoint stabilization detected, disabling Pulse Width Modulation.")
            self.disable()
            return

        if self._xtreme_profile.boiler_timing:
            self._update_burn_time(boiler, flame)

        # State transitions for PWM
        if self._status != PWMStatus.ON and self._duty_cycle[0] >= HEATER_STARTUP_TIMEFRAME and (elapsed >= self._duty_cycle[1] or self._status == PWMStatus.IDLE):
            if self._current_cycle >= self._cycles.maximum_count:
                _LOGGER.info("Reached max cycles per hour, preventing new duty cycle.")
                return

            if self._xtreme_profile.boiler_timing and not self._boiler_may_start(boiler, flame):
                return

            self._cycle_starts.append(monotonic())
            self._current_cycle = len(self._cycle_starts)
            self._status = PWMStatus.ON
            self._last_update = monotonic()
            self._last_boiler_temperature = boiler.flow_temperature
            self._start_burn_time()
            _LOGGER.info("Starting new duty cycle (ON state). Current CYCLES count: %d", self._current_cycle)
            return

        if self._status != PWMStatus.OFF and (self._duty_cycle[0] < HEATER_STARTUP_TIMEFRAME or self._on_phase_completed(elapsed) or self._status == PWMStatus.IDLE):
            if self._status == PWMStatus.ON and self._xtreme_profile.boiler_timing:
                self._last_block_burn_seconds = round(self._burn_seconds)
                self._last_block_target_seconds = self._duty_cycle[0]
                _LOGGER.info("Xtreme profile: on phase completed after %.0f seconds of burn time (target %d seconds, %.0f seconds wall time).", self._burn_seconds, self._duty_cycle[0], elapsed)

            self._status = PWMStatus.OFF
            self._last_update = monotonic()
            _LOGGER.info("Duty cycle completed. Switching to OFF state.")
            return

        _LOGGER.debug("Cycle time elapsed: %.0f seconds in state: %s", elapsed, self._status)

    def _start_burn_time(self) -> None:
        """Xtreme profile: start the burn time bookkeeping of a new on phase."""
        now = monotonic()

        self._burn_seconds = 0
        self._last_tick = now
        self._on_started_at = now
        self._flame_seen = False
        self._flame_wait_expired = False

    def _update_burn_time(self, boiler: "BoilerState", flame: "FlameState") -> None:
        """Xtreme profile: count the burn time of the on phase (flame on for heating) and the remaining anti-cycling time."""
        now = monotonic()

        # Remaining anti-cycling time after the last flame, for heating or hot water
        if flame.is_inactive and flame.off_since is not None:
            self._anti_cycling_remaining = max(0.0, self._xtreme_profile.anti_cycling_wait - (now - flame.off_since))
        else:
            self._anti_cycling_remaining = 0

        if self._status != PWMStatus.ON or self._last_tick is None or self._on_started_at is None:
            self._last_tick = now
            return

        delta = max(0.0, now - self._last_tick)
        self._last_tick = now

        if boiler.flame_active and not boiler.hot_water_active:
            # Do not count the part of the interval before the flame ignited
            if flame.latest_on_time_seconds is not None:
                delta = min(delta, flame.latest_on_time_seconds)

            self._flame_seen = True
            self._burn_seconds += delta
            _LOGGER.debug("Xtreme profile: burn time %.0f of %d seconds.", self._burn_seconds, self._duty_cycle[0])
            return

        if boiler.hot_water_active:
            _LOGGER.debug("Xtreme profile: hot water active during the on phase, burn time paused at %.0f seconds.", self._burn_seconds)
            return

        if not self._flame_seen and not self._flame_wait_expired and (now - self._on_started_at) >= self._xtreme_profile.flame_wait_timeout:
            self._flame_wait_expired = True
            _LOGGER.warning("Xtreme profile: no flame within %d seconds of the on phase, counting the on time anyway.", self._xtreme_profile.flame_wait_timeout)

        if self._flame_wait_expired:
            self._burn_seconds += delta

    def _boiler_may_start(self, boiler: "BoilerState", flame: "FlameState") -> bool:
        """Xtreme profile: check whether the boiler may start a new on phase (no hot water, anti-cycling time passed)."""
        if boiler.hot_water_active:
            _LOGGER.debug("Xtreme profile: hot water active, postponing the on phase.")
            return False

        if self._anti_cycling_remaining > 0:
            _LOGGER.debug("Xtreme profile: anti-cycling time after the last flame, postponing the on phase for %.0f seconds.", self._anti_cycling_remaining)
            return False

        return True

    def _on_phase_completed(self, elapsed: float) -> bool:
        """Check whether the on phase is completed."""
        if not self._xtreme_profile.boiler_timing:
            return elapsed >= self._duty_cycle[0]

        if self._burn_seconds >= self._duty_cycle[0]:
            return True

        # Safety net: never stay in the on phase much longer than planned
        maximum_seconds = 2 * self._duty_cycle[0] + self._xtreme_profile.flame_wait_timeout
        if elapsed >= maximum_seconds:
            _LOGGER.warning("Xtreme profile: on phase took %.0f seconds with only %.0f seconds of burn time, ending it.", elapsed, self._burn_seconds)
            return True

        return False

    def _calculate_duty_cycle(self, requested_setpoint: float, boiler: "BoilerState") -> Tuple[int, int]:
        """Calculate the duty cycle in seconds based on the output of a PID controller and a heating curve value."""
        base_offset = self._heating_curve.base_offset
        boiler_temperature = self._last_boiler_temperature

        # Ensure the boiler temperature is above the base offset
        boiler_temperature = max(boiler_temperature, base_offset + 1)

        # Calculate duty cycle percentage
        self._last_duty_cycle_percentage = (requested_setpoint - base_offset) / (boiler_temperature - base_offset)
        self._last_duty_cycle_percentage = min(max(self._last_duty_cycle_percentage, 0), 1)

        _LOGGER.debug(
            "Duty cycle calculation - Requested setpoint: %.1f°C, Boiler temperature: %.1f°C, Duty cycle percentage: %.2f%%",
            requested_setpoint, boiler_temperature, self._last_duty_cycle_percentage * 100
        )

        # If automatic duty cycle control is disabled
        if not self._automatic_duty_cycle:
            on_time = self._last_duty_cycle_percentage * self._cycles.maximum_time
            off_time = (1 - self._last_duty_cycle_percentage) * self._cycles.maximum_time

            _LOGGER.debug(
                "Calculated on_time: %.0f seconds, off_time: %.0f seconds.",
                on_time, off_time
            )

            return int(on_time), int(off_time)

        # Handle special low-duty cycle cases
        if self._last_duty_cycle_percentage < self._min_duty_cycle_percentage:
            if boiler.flame_active and not boiler.hot_water_active:
                on_time = self._on_time_lower_threshold
                off_time = self._on_time_max_threshold - self._on_time_lower_threshold

                _LOGGER.debug(
                    "Special low-duty case with flame active. Setting on_time: %d seconds, off_time: %d seconds.",
                    on_time, off_time
                )

                return int(on_time), int(off_time)

            _LOGGER.debug("Special low-duty case without flame. Setting on_time: 0 seconds, off_time: %d seconds.", self._on_time_max_threshold)
            return 0, int(self._on_time_max_threshold)

        # Mapping duty cycle ranges to on/off times
        if self._last_duty_cycle_percentage <= self._duty_cycle_lower_threshold:
            on_time = self._on_time_lower_threshold
            off_time = (self._on_time_lower_threshold / self._last_duty_cycle_percentage) - self._on_time_lower_threshold

            _LOGGER.debug(
                "Low duty cycle range, cycles this hour: %d. Calculated on_time: %d seconds, off_time: %d seconds.",
                self._current_cycle, on_time, off_time
            )

            return int(on_time), int(off_time)

        if self._last_duty_cycle_percentage <= self._duty_cycle_upper_threshold:
            on_time = self._on_time_upper_threshold * self._last_duty_cycle_percentage
            off_time = self._on_time_upper_threshold * (1 - self._last_duty_cycle_percentage)

            _LOGGER.debug(
                "Mid-range duty cycle, cycles this hour: %d. Calculated on_time: %d seconds, off_time: %d seconds.",
                self._current_cycle, on_time, off_time
            )

            return int(on_time), int(off_time)

        if self._last_duty_cycle_percentage <= self._max_duty_cycle_percentage:
            on_time = self._on_time_lower_threshold / (1 - self._last_duty_cycle_percentage) - self._on_time_lower_threshold
            off_time = self._on_time_lower_threshold

            _LOGGER.debug(
                "High duty cycle range, cycles this hour: %d. Calculated on_time: %d seconds, off_time: %d seconds.",
                self._current_cycle, on_time, off_time
            )

            return int(on_time), int(off_time)

        # Handle cases where the duty cycle exceeds the maximum allowed percentage
        on_time = self._on_time_max_threshold
        off_time = 0

        _LOGGER.debug("Maximum duty cycle exceeded. Setting on_time: %d seconds, off_time: %d seconds.", on_time, off_time)
        return int(on_time), int(off_time)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def burn_seconds(self) -> Optional[float]:
        """Xtreme profile: burn time of the current on phase."""
        return round(self._burn_seconds) if self._status == PWMStatus.ON else None

    @property
    def anti_cycling_remaining(self) -> float:
        """Xtreme profile: seconds until the boiler may start again after the last flame."""
        return round(self._anti_cycling_remaining)

    @property
    def last_block_burn_seconds(self) -> Optional[float]:
        """Xtreme profile: burn time of the last completed on phase."""
        return self._last_block_burn_seconds

    @property
    def last_block_target_seconds(self) -> Optional[float]:
        """Xtreme profile: planned on time of the last completed on phase."""
        return self._last_block_target_seconds

    @property
    def status(self) -> PWMStatus:
        return self._status

    @property
    def state(self):
        return PWMState(
            status=self._status,
            enabled=self._enabled,
            duty_cycle=self._duty_cycle
        )

    @property
    def duty_cycle(self) -> Optional[Tuple[int, int]]:
        """Current duty cycle as a tuple of (on_time, off_time) in seconds, or None if inactive."""
        return self._duty_cycle

    @property
    def last_duty_cycle_percentage(self) -> Optional[float]:
        """Returns the last calculated duty cycle percentage."""
        return round(self._last_duty_cycle_percentage * 100, 2) if self._last_duty_cycle_percentage is not None else None

    @property
    def setpoint(self) -> float:
        """Returns the adjusted setpoint when running an ON duty cycle."""
        return self._setpoint or MINIMUM_SETPOINT
