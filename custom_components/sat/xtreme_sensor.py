"""Sensors of the Xtreme profile, for following the profile on a dashboard."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import Event, EventStateChangedData
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_NAME
from .entity import SatClimateEntity


def async_setup_xtreme_sensors(coordinator, config_entry: ConfigEntry, climate, async_add_entities: AddEntitiesCallback) -> None:
    """Add the sensors of the active Xtreme profile switches."""
    profile = coordinator.xtreme_profile
    entities = []

    if profile.boiler_timing:
        entities += [
            SatPwmBurnTimeSensor(coordinator, config_entry, climate),
            SatAntiCyclingRemainingSensor(coordinator, config_entry, climate),
        ]

    if entities:
        async_add_entities(entities)


class SatXtremeSensor(SatClimateEntity, SensorEntity):
    """Base class for Xtreme profile sensors that follow the climate entity."""

    _key: str = ""
    _label: str = ""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        async def on_state_change(_event: Event[EventStateChangedData]):
            self.async_write_ha_state()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._climate.entity_id], on_state_change
            )
        )

    @property
    def name(self) -> str:
        return f"{self._label} {self._config_entry.data.get(CONF_NAME)}"

    @property
    def unique_id(self) -> str:
        return f"{self._config_entry.data.get(CONF_NAME).lower()}-xtreme-{self._key}"


class SatPwmBurnTimeSensor(SatXtremeSensor):
    """Burn time of the last completed PWM on phase, with the planned on time."""

    _key = "pwm-burn-time"
    _label = "PWM Burn Time"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        return self._climate.pwm.last_block_burn_seconds

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        pwm = self._climate.pwm

        return {
            "target_seconds": pwm.last_block_target_seconds,
            "current_burn_seconds": pwm.burn_seconds,
            "current_target_seconds": pwm.duty_cycle[0] if pwm.duty_cycle else None,
            "pwm_state": pwm.status.name,
        }


class SatAntiCyclingRemainingSensor(SatXtremeSensor):
    """Seconds until the boiler may start again after the last flame (heating or hot water)."""

    _key = "anti-cycling-remaining"
    _label = "Anti-cycling Remaining"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS

    @property
    def native_value(self) -> float:
        return self._climate.pwm.anti_cycling_remaining
