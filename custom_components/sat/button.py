"""Buttons of the Xtreme profile: start and stop the calibration."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_NAME, DOMAIN, COORDINATOR, CLIMATE
from .entity import SatClimateEntity
from .xtreme_sensor import FORK_LABEL


async def async_setup_entry(_hass: HomeAssistant, _config_entry: ConfigEntry, _async_add_entities: AddEntitiesCallback):
    """Add the calibration buttons when the Xtreme calibration is enabled."""
    if any(key not in _hass.data[DOMAIN][_config_entry.entry_id] for key in (CLIMATE, COORDINATOR)):
        return

    climate = _hass.data[DOMAIN][_config_entry.entry_id][CLIMATE]
    coordinator = _hass.data[DOMAIN][_config_entry.entry_id][COORDINATOR]

    if not coordinator.xtreme_profile.calibration:
        return

    _async_add_entities([
        SatStartCalibrationButton(coordinator, _config_entry, climate),
        SatStopCalibrationButton(coordinator, _config_entry, climate),
    ])


class SatStartCalibrationButton(SatClimateEntity, ButtonEntity):
    _attr_icon = "mdi:play"

    @property
    def name(self) -> str:
        return f"{FORK_LABEL} Start Calibration {self._config_entry.data.get(CONF_NAME)}"

    @property
    def unique_id(self) -> str:
        return f"{self._config_entry.data.get(CONF_NAME).lower()}-xtreme-calibration-start"

    async def async_press(self) -> None:
        await self._climate.xtreme_calibration.async_start()


class SatStopCalibrationButton(SatClimateEntity, ButtonEntity):
    _attr_icon = "mdi:stop"

    @property
    def name(self) -> str:
        return f"{FORK_LABEL} Stop Calibration {self._config_entry.data.get(CONF_NAME)}"

    @property
    def unique_id(self) -> str:
        return f"{self._config_entry.data.get(CONF_NAME).lower()}-xtreme-calibration-stop"

    async def async_press(self) -> None:
        await self._climate.xtreme_calibration.async_stop()
