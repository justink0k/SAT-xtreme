"""Binary sensors of SAT-xtreme: boiler state as SAT sees it, for any gateway."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from ..const import CONF_NAME
from ..coordinator import DeviceState
from ..entity import SatClimateEntity, SatEntity
from .sensor import FORK_LABEL


def async_setup_xtreme_binary_sensors(coordinator, config_entry: ConfigEntry, climate, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([
        SatFlameBinarySensor(coordinator, config_entry),
        SatHotWaterBinarySensor(coordinator, config_entry),
        SatHeatingDemandBinarySensor(coordinator, config_entry, climate),
    ])

    if coordinator.xtreme_profile.stale_sensors:
        async_add_entities([SatStaleSensorBinarySensor(coordinator, config_entry, climate)])


class _XtremeName:
    _key: str = ""
    _label: str = ""

    @property
    def name(self) -> str:
        return f"{FORK_LABEL} {self._label} {self._config_entry.data.get(CONF_NAME)}"

    @property
    def unique_id(self) -> str:
        return f"{self._config_entry.data.get(CONF_NAME).lower()}-xtreme-{self._key}"


class SatFlameBinarySensor(_XtremeName, SatEntity, BinarySensorEntity):
    _key = "flame"
    _label = "Flame"
    _attr_icon = "mdi:fire"

    @property
    def is_on(self) -> bool:
        return bool(self._coordinator.flame_active)


class SatHotWaterBinarySensor(_XtremeName, SatEntity, BinarySensorEntity):
    _key = "hot-water"
    _label = "Hot Water Active"
    _attr_icon = "mdi:water-boiler"

    @property
    def is_on(self) -> bool:
        return bool(self._coordinator.hot_water_active)


class SatHeatingDemandBinarySensor(_XtremeName, SatClimateEntity, BinarySensorEntity):
    """The heating demand that SAT sends to the boiler (central heating enable)."""

    _key = "heating-demand"
    _label = "Heating Demand"
    _attr_device_class = BinarySensorDeviceClass.HEAT

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        async def on_state_change(_event: Event[EventStateChangedData]):
            self.async_write_ha_state()

        self.async_on_remove(async_track_state_change_event(self.hass, [self._climate.entity_id], on_state_change))

    @property
    def is_on(self) -> bool:
        return self._coordinator.heater_state_commanded == DeviceState.ON


class SatStaleSensorBinarySensor(_XtremeName, SatClimateEntity, BinarySensorEntity):
    """On while the inside or outside temperature is stale; the attributes show the ages and the sensor in use."""

    _key = "stale-sensor"
    _label = "Stale Sensor"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._climate.stale_sensors.add_listener(self.async_write_ha_state))

    @property
    def is_on(self) -> bool:
        return self._climate.stale_sensors.stale

    @property
    def extra_state_attributes(self) -> dict:
        return self._climate.stale_sensors.attributes
