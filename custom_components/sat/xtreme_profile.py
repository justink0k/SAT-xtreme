"""Xtreme profile: opt-in adjustments for an Intergas Xtreme 30 behind an OpenTherm Gateway.

Every adjustment has its own switch in the SAT options (menu "Xtreme profile"). With all switches
off, SAT behaves like upstream. See CHANGES_XTREME.md for details.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from .const import (
    OPTIONS_DEFAULTS,
    CONF_XTREME_PRIME_SETPOINT,
    CONF_XTREME_BOILER_MAXIMUM_POWER,
    CONF_XTREME_BOILER_MINIMUM_POWER,
    CONF_XTREME_IGNORE_MODULATION_LIMIT,
    CONF_XTREME_BOILER_TIMING,
    CONF_XTREME_ANTI_CYCLING_TIME,
    CONF_XTREME_ANTI_CYCLING_MARGIN,
    CONF_XTREME_MINIMUM_BURN_TIME,
    CONF_XTREME_MINIMUM_DUTY_CYCLE,
    CONF_XTREME_LEARNED_OPV,
    CONF_XTREME_CALIBRATION,
    CONF_XTREME_PID_GAIN_FACTOR,
    CONF_XTREME_MAXIMUM_SETPOINT_RISE,
)

_LOGGER = logging.getLogger(__name__)

# Do not resend the same heater state (CH=0 / CH=1) within this window while the
# status bit on the bus has not caught up yet (MsgID 0 every few seconds plus the
# coordinator debounce of 5 seconds).
HEATER_COMMAND_REPEAT_SECONDS = 30


@dataclass(frozen=True, slots=True, kw_only=True)
class XtremeProfile:
    """The switches of the Xtreme profile."""

    # Step 1: keep the minimum setpoint on the bus during the PWM off phase and turn the
    # central heating demand off explicitly, so the boiler already has the setpoint when
    # the next on phase starts.
    prime_setpoint: bool = False

    # Step 2: the boiler ignores the maximum relative modulation (MM=), but reports its modulation.
    # Stop managing the modulation limit and fall back to the rated power when the boiler does not
    # report its capacity (MsgID 15).
    ignore_modulation_limit: bool = False
    boiler_maximum_power: float = 19.5
    boiler_minimum_power: float = 3.9

    # Step 3: align PWM with the boiler. The on time counts burn time (flame on, no hot water), a new
    # on phase waits until the anti-cycling time after the last flame (heating or hot water) has passed,
    # and every burn lasts at least the minimum burn time.
    boiler_timing: bool = False
    anti_cycling_time: int = 300
    anti_cycling_margin: int = 15
    minimum_burn_time: int = 360
    minimum_duty_cycle: float = 7.5

    # Step 4: learn the OPV during normal operation: "off", "learn" (only show it) or "apply" (use it)
    learned_opv: str = "off"

    # Step 5: a slow calibration of the OPV that does not rely on MM=, started with a button or service
    calibration: bool = False

    # PID settings: a factor on the automatically calculated gains, and a limit on how far the
    # requested setpoint may rise above the heating curve (0 = no limit)
    pid_gain_factor: float = 1.0
    maximum_setpoint_rise: float = 0

    @property
    def anti_cycling_wait(self) -> int:
        """Seconds to wait after the last flame before a new on phase may start."""
        return self.anti_cycling_time + self.anti_cycling_margin

    @property
    def flame_wait_timeout(self) -> int:
        """Seconds to wait for the flame in an on phase before the on time counts anyway."""
        return self.anti_cycling_wait + 15

    @staticmethod
    def from_options(options: Mapping[str, Any] | None) -> XtremeProfile:
        values = OPTIONS_DEFAULTS.copy()
        values.update(options or {})

        profile = XtremeProfile(
            prime_setpoint=bool(values.get(CONF_XTREME_PRIME_SETPOINT)),
            ignore_modulation_limit=bool(values.get(CONF_XTREME_IGNORE_MODULATION_LIMIT)),
            boiler_maximum_power=float(values.get(CONF_XTREME_BOILER_MAXIMUM_POWER)),
            boiler_minimum_power=float(values.get(CONF_XTREME_BOILER_MINIMUM_POWER)),
            boiler_timing=bool(values.get(CONF_XTREME_BOILER_TIMING)),
            anti_cycling_time=int(values.get(CONF_XTREME_ANTI_CYCLING_TIME)),
            anti_cycling_margin=int(values.get(CONF_XTREME_ANTI_CYCLING_MARGIN)),
            minimum_burn_time=int(values.get(CONF_XTREME_MINIMUM_BURN_TIME)),
            minimum_duty_cycle=float(values.get(CONF_XTREME_MINIMUM_DUTY_CYCLE)),
            learned_opv=str(values.get(CONF_XTREME_LEARNED_OPV)),
            calibration=bool(values.get(CONF_XTREME_CALIBRATION)),
            pid_gain_factor=float(values.get(CONF_XTREME_PID_GAIN_FACTOR)),
            maximum_setpoint_rise=float(values.get(CONF_XTREME_MAXIMUM_SETPOINT_RISE)),
        )

        if profile.enabled:
            _LOGGER.info("Xtreme profile: active switches: %s", ", ".join(profile.active_switches))

        return profile

    @property
    def active_switches(self) -> list[str]:
        switches = (
            ("prime_setpoint", self.prime_setpoint),
            ("ignore_modulation_limit", self.ignore_modulation_limit),
            ("boiler_timing", self.boiler_timing),
            (f"learned_opv ({self.learned_opv})", self.learned_opv != "off"),
            ("calibration", self.calibration),
            (f"pid_gain_factor ({self.pid_gain_factor})", self.pid_gain_factor != 1.0),
            (f"maximum_setpoint_rise ({self.maximum_setpoint_rise})", self.maximum_setpoint_rise > 0),
        )

        return [name for name, enabled in switches if enabled]

    @property
    def enabled(self) -> bool:
        return len(self.active_switches) > 0
