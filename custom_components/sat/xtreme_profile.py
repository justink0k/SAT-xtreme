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

    @staticmethod
    def from_options(options: Mapping[str, Any] | None) -> XtremeProfile:
        values = OPTIONS_DEFAULTS.copy()
        values.update(options or {})

        profile = XtremeProfile(
            prime_setpoint=bool(values.get(CONF_XTREME_PRIME_SETPOINT)),
            ignore_modulation_limit=bool(values.get(CONF_XTREME_IGNORE_MODULATION_LIMIT)),
            boiler_maximum_power=float(values.get(CONF_XTREME_BOILER_MAXIMUM_POWER)),
            boiler_minimum_power=float(values.get(CONF_XTREME_BOILER_MINIMUM_POWER)),
        )

        if profile.enabled:
            _LOGGER.info("Xtreme profile: active switches: %s", ", ".join(profile.active_switches))

        return profile

    @property
    def active_switches(self) -> list[str]:
        switches = (
            ("prime_setpoint", self.prime_setpoint),
            ("ignore_modulation_limit", self.ignore_modulation_limit),
        )

        return [name for name, enabled in switches if enabled]

    @property
    def enabled(self) -> bool:
        return len(self.active_switches) > 0
