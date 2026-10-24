"""Number entity of the Xtreme profile: the maximum setpoint, for dashboards and automations."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..const import (
    CONF_MAXIMUM_SETPOINT, CONF_NAME, HEATING_SYSTEM_HEAT_PUMP, HEATING_SYSTEM_RADIATORS, HEATING_SYSTEM_UNDERFLOOR,
)
from ..entity import SatClimateEntity
from ..helpers import calculate_default_maximum_setpoint
from .sensor import FORK_LABEL

_LOGGER = logging.getLogger(__name__)

# The lowest value the entity offers, unless the OPV in use is higher
MAXIMUM_SETPOINT_FLOOR = 30.0

# The highest value the entity offers per heating system; the boiler's own bound may make it lower
MAXIMUM_SETPOINT_CEILINGS = {
    HEATING_SYSTEM_RADIATORS: 75.0,
    HEATING_SYSTEM_UNDERFLOOR: 50.0,
    HEATING_SYSTEM_HEAT_PUMP: 55.0,
}


def maximum_setpoint_ceiling(heating_system: str) -> float:
    """The ceiling of the entity; an unknown heating system gets the default maximum setpoint of SAT."""
    return MAXIMUM_SETPOINT_CEILINGS.get(heating_system, float(calculate_default_maximum_setpoint(heating_system)))


def async_setup_xtreme_numbers(coordinator, config_entry: ConfigEntry, climate, async_add_entities: AddEntitiesCallback) -> None:
    """Add the number entities of the active Xtreme profile switches."""
    if coordinator.xtreme_profile.maximum_setpoint_entity and coordinator.supports_setpoint_management:
        async_add_entities([SatMaximumSetpointNumber(coordinator, config_entry, climate)])


class SatMaximumSetpointNumber(SatClimateEntity, NumberEntity):
    """The maximum setpoint. A change is stored as the option and used right away."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:thermometer-chevron-up"

    @property
    def name(self) -> str:
        return f"{FORK_LABEL} Maximum Setpoint {self._config_entry.data.get(CONF_NAME)}"

    @property
    def unique_id(self) -> str:
        return f"{self._config_entry.data.get(CONF_NAME).lower()}-xtreme-maximum-setpoint"

    @property
    def native_value(self) -> float:
        return self._coordinator.maximum_setpoint

    @property
    def opv(self) -> float:
        """The OPV that SAT uses: the learned one when it is applied, otherwise the configured one."""
        if self._climate.learned_opv.applied:
            return self._climate.learned_opv.value

        return self._coordinator.minimum_setpoint

    @property
    def native_max_value(self) -> float:
        ceiling = maximum_setpoint_ceiling(self._coordinator.heating_system)

        if (bound := self._coordinator.boiler_maximum_setpoint_bound) is not None:
            ceiling = min(ceiling, bound)

        return ceiling

    @property
    def native_min_value(self) -> float:
        return min(max(MAXIMUM_SETPOINT_FLOOR, self.opv), self.native_max_value)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "opv": self.opv,
            "ceiling": maximum_setpoint_ceiling(self._coordinator.heating_system),
            "boiler_bound": self._coordinator.boiler_maximum_setpoint_bound,
        }

    async def async_set_native_value(self, value: float) -> None:
        if self._climate.xtreme_calibration.active:
            raise HomeAssistantError("The maximum setpoint cannot be changed while the calibration is running.")

        if not self.native_min_value <= value <= self.native_max_value:
            raise HomeAssistantError(f"The maximum setpoint must be between {self.native_min_value} and {self.native_max_value} °C.")

        options = {**self._config_entry.options, CONF_MAXIMUM_SETPOINT: float(value)}
        self.hass.config_entries.async_update_entry(self._config_entry, options=options)

        await self._coordinator.async_set_maximum_setpoint(value)
        _LOGGER.info("Xtreme fork: maximum setpoint set to %.0f°C with the number entity.", value)

        self.async_write_ha_state()
