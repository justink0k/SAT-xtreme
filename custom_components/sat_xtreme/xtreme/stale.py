"""Stale sensors: what SAT does when the inside or outside temperature is no longer updated.

With the option on, this replaces the "maximum value age" check of SAT 4.2.1 for the inside and outside
sensor. The age is measured from the last report of the sensor (`last_reported`), so a sensor that keeps
reporting the same value is not seen as stale. When no inside sensor is usable, SAT heats on the heating curve
only, and never above the setpoint it requested when the sensor was lost.

The idea of handling stale sensors comes from the closed upstream pull request Alexwijn/SAT#124 (GPL-3.0);
this module is written for the fork and takes no code from it.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any, Optional

from homeassistant.components import sensor, weather
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import issue_registry
from homeassistant.util import dt as dt_util

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SOURCE_MAIN = "main"
SOURCE_BACKUP = "backup"

ISSUE_INSIDE = "stale_inside_sensor"
ISSUE_OUTSIDE = "stale_outside_sensor"


def _now() -> datetime:
    return dt_util.utcnow()


def state_age_seconds(state: State) -> float:
    """Seconds since the sensor last reported, also when it reported the same value."""
    last = getattr(state, "last_reported", None) or state.last_updated
    return (_now() - last).total_seconds()


def state_temperature(entity_id: str, state: Optional[State]) -> Optional[float]:
    """The temperature of a sensor or weather entity, or None when it has none."""
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None

    try:
        if entity_id.startswith(f"{weather.DOMAIN}."):
            return float(state.attributes.get("temperature"))

        return float(state.state)
    except (TypeError, ValueError):
        return None


class StaleSensorGuard:
    """Decides which inside and outside temperature SAT may use."""

    def __init__(self, entry_id: str, name: str, enabled: bool, inside_sensor: str, backup_sensor: Optional[str],
                 outside_sensors: list[str], inside_max_age_minutes: float, outside_max_age_minutes: float) -> None:
        self._entry_id = entry_id
        self._name = name
        self.enabled = enabled

        self._inside_sensor = inside_sensor
        self._backup_sensor = backup_sensor or None
        self._outside_sensors = sorted(outside_sensors or [], key=lambda entity_id: not entity_id.startswith(f"{sensor.DOMAIN}."))
        self._inside_max_age = float(inside_max_age_minutes) * 60
        self._outside_max_age = float(outside_max_age_minutes) * 60

        self._hass: Optional[HomeAssistant] = None
        self._listeners: list[Callable[[], None]] = []

        self._inside_source: Optional[str] = SOURCE_MAIN
        self._outside_stale: bool = False
        self._last_outside: Optional[float] = None
        self._setpoint_cap: Optional[float] = None

    @property
    def backup_sensor(self) -> Optional[str]:
        return self._backup_sensor

    @property
    def inside_source(self) -> Optional[str]:
        """The inside sensor in use: "main", "backup", or None when none is usable."""
        return self._inside_source

    @property
    def safe_mode(self) -> bool:
        """No usable inside sensor: heat on the heating curve only, capped at the setpoint from that moment."""
        return self.enabled and self._inside_source is None

    @property
    def setpoint_cap(self) -> Optional[float]:
        return self._setpoint_cap if self.safe_mode else None

    @property
    def inside_stale(self) -> bool:
        return self.enabled and self._inside_source != SOURCE_MAIN

    @property
    def outside_stale(self) -> bool:
        return self.enabled and self._outside_stale

    @property
    def stale(self) -> bool:
        return self.inside_stale or self.outside_stale

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _usable(self, entity_id: Optional[str], max_age: float) -> Optional[float]:
        if entity_id is None or self._hass is None:
            return None

        state = self._hass.states.get(entity_id)
        if (value := state_temperature(entity_id, state)) is None:
            return None

        if state_age_seconds(state) > max_age:
            return None

        return value

    def inside_temperature(self, hass: HomeAssistant) -> Optional[float]:
        """The inside temperature of the sensor in use, or None in the safe mode."""
        self._hass = hass

        if self._inside_source is None:
            return None

        entity_id = self._inside_sensor if self._inside_source == SOURCE_MAIN else self._backup_sensor
        return state_temperature(entity_id, hass.states.get(entity_id))

    def outside_temperature(self, hass: HomeAssistant) -> Optional[float]:
        """The outside temperature of the first fresh sensor, or the last known value when all are stale."""
        self._hass = hass

        for entity_id in self._outside_sensors:
            if (value := self._usable(entity_id, self._outside_max_age)) is not None:
                self._last_outside = value
                return value

        return self._last_outside

    def ages(self) -> dict[str, Optional[float]]:
        """The age in seconds of every sensor, for the binary sensor."""
        def age(entity_id: Optional[str]) -> Optional[float]:
            if entity_id is None or self._hass is None or (state := self._hass.states.get(entity_id)) is None:
                return None

            return round(state_age_seconds(state))

        return {
            "inside_age": age(self._inside_sensor),
            "backup_age": age(self._backup_sensor),
            "outside_age": min((value for entity_id in self._outside_sensors if (value := age(entity_id)) is not None), default=None),
        }

    def check(self, hass: HomeAssistant, requested_setpoint: Callable[[], float]) -> bool:
        """Update which sensors are usable; returns True when something changed.

        The requested setpoint is only read when the last usable inside sensor is lost, to cap the safe mode.
        """
        self._hass = hass

        if not self.enabled:
            return False

        if self._usable(self._inside_sensor, self._inside_max_age) is not None:
            source = SOURCE_MAIN
        elif self._usable(self._backup_sensor, self._inside_max_age) is not None:
            source = SOURCE_BACKUP
        else:
            source = None

        outside_stale = all(self._usable(entity_id, self._outside_max_age) is None for entity_id in self._outside_sensors)

        changed = source != self._inside_source or outside_stale != self._outside_stale
        if not changed:
            return False

        if source is None and self._inside_source is not None:
            self._setpoint_cap = requested_setpoint()
            _LOGGER.warning("SAT-xtreme: no usable inside temperature sensor, heating on the heating curve only (at most %.1f°C).", self._setpoint_cap)
        elif source is not None and self._inside_source is None:
            _LOGGER.info("SAT-xtreme: the %s inside sensor reports again, back to normal control.", source)
        elif source == SOURCE_BACKUP:
            _LOGGER.warning("SAT-xtreme: the inside sensor %s is stale, using the backup sensor %s.", self._inside_sensor, self._backup_sensor)

        if outside_stale != self._outside_stale:
            if outside_stale:
                _LOGGER.warning("SAT-xtreme: the outside temperature is stale, using the last known value %s.", self._last_outside)
            else:
                _LOGGER.info("SAT-xtreme: the outside temperature reports again.")

        self._inside_source = source
        self._outside_stale = outside_stale

        self._update_issues(hass)

        for listener in list(self._listeners):
            listener()

        return True

    def _update_issues(self, hass: HomeAssistant) -> None:
        issues = {
            ISSUE_INSIDE: (self.inside_stale, {"name": self._name, "sensor": self._inside_sensor}),
            ISSUE_OUTSIDE: (self.outside_stale, {"name": self._name, "sensor": ", ".join(self._outside_sensors)}),
        }

        for key, (active, placeholders) in issues.items():
            issue_id = f"{key}_{self._entry_id}"

            if active:
                issue_registry.async_create_issue(
                    hass, DOMAIN, issue_id,
                    is_fixable=False,
                    severity=issue_registry.IssueSeverity.WARNING,
                    translation_key=key,
                    translation_placeholders=placeholders,
                )
            else:
                issue_registry.async_delete_issue(hass, DOMAIN, issue_id)

    def remove_issues(self, hass: HomeAssistant) -> None:
        for key in (ISSUE_INSIDE, ISSUE_OUTSIDE):
            issue_registry.async_delete_issue(hass, DOMAIN, f"{key}_{self._entry_id}")

    @property
    def attributes(self) -> dict[str, Any]:
        return {
            **self.ages(),
            "inside_source": self._inside_source,
            "safe_mode": self.safe_mode,
            "setpoint_cap": self.setpoint_cap,
            "outside_stale": self.outside_stale,
            "outside_last_known": self._last_outside,
        }
