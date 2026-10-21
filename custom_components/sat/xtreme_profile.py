"""Xtreme profile: opt-in adjustments for an Intergas Xtreme 30 behind an OpenTherm Gateway.

Every adjustment has its own switch in the SAT options (menu "Xtreme profile"). With all switches
off, SAT behaves like upstream. See CHANGES_XTREME.md for details.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from .const import CONF_XTREME_PRIME_SETPOINT, OPTIONS_DEFAULTS

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

    @staticmethod
    def from_options(options: Mapping[str, Any] | None) -> XtremeProfile:
        values = OPTIONS_DEFAULTS.copy()
        values.update(options or {})

        profile = XtremeProfile(
            prime_setpoint=bool(values.get(CONF_XTREME_PRIME_SETPOINT)),
        )

        if profile.enabled:
            _LOGGER.info("Xtreme profile: active switches: %s", ", ".join(profile.active_switches))

        return profile

    @property
    def active_switches(self) -> list[str]:
        return [name for name, enabled in (("prime_setpoint", self.prime_setpoint),) if enabled]

    @property
    def enabled(self) -> bool:
        return len(self.active_switches) > 0
