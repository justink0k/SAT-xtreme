"""Switch of the Xtreme profile: keep hot water warm (the boiler's comfort function) or not."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.storage import Store

from .const import CONF_NAME, DOMAIN, COORDINATOR, CLIMATE
from .entity import SatClimateEntity
from .xtreme_sensor import FORK_LABEL

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1


def _store(hass: HomeAssistant, config_entry: ConfigEntry) -> Store:
    # Remembers whether SAT turned keep-warm off, so it can be given back when the option is turned off
    return Store(hass, STORAGE_VERSION, f"sat_xtreme_hot_water_{config_entry.entry_id}")


async def async_setup_entry(_hass: HomeAssistant, _config_entry: ConfigEntry, _async_add_entities: AddEntitiesCallback):
    """Add the hot water keep-warm switch when the option is on; give keep-warm back to the boiler when it is off."""
    if any(key not in _hass.data[DOMAIN][_config_entry.entry_id] for key in (CLIMATE, COORDINATOR)):
        return

    climate = _hass.data[DOMAIN][_config_entry.entry_id][CLIMATE]
    coordinator = _hass.data[DOMAIN][_config_entry.entry_id][COORDINATOR]

    if not coordinator.supports_hot_water_keep_warm_control:
        return

    store = _store(_hass, _config_entry)

    if not coordinator.xtreme_profile.hot_water_switch:
        # The option was turned off while keep-warm was off: hand hot water back to the boiler
        if (data := await store.async_load()) and data.get("keep_warm_off"):
            _LOGGER.info("Xtreme profile: hot water switch removed, giving keep-warm back to the boiler (HW=A).")
            await coordinator.async_set_hot_water_keep_warm(True)
            await store.async_save({"keep_warm_off": False})

        return

    _async_add_entities([SatHotWaterKeepWarmSwitch(coordinator, _config_entry, climate, store)])


class SatHotWaterKeepWarmSwitch(SatClimateEntity, SwitchEntity, RestoreEntity):
    """On: the boiler keeps hot water warm as set on the boiler (HW=A). Off: no keep-warm (HW=0)."""

    _attr_icon = "mdi:water-boiler"

    def __init__(self, coordinator, config_entry: ConfigEntry, climate, store: Store):
        super().__init__(coordinator, config_entry, climate)

        self._store = store
        self._attr_is_on = True

    @property
    def name(self) -> str:
        return f"{FORK_LABEL} Hot Water Keep Warm {self._config_entry.data.get(CONF_NAME)}"

    @property
    def unique_id(self) -> str:
        return f"{self._config_entry.data.get(CONF_NAME).lower()}-xtreme-hot-water-keep-warm"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        # Restore the last state and send it again, so the gateway always matches the switch
        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_is_on = last_state.state != STATE_OFF

        await self._async_apply()

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        await self._async_apply()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        await self._async_apply()
        self.async_write_ha_state()

    async def _async_apply(self) -> None:
        _LOGGER.info("Xtreme profile: hot water keep-warm %s.", "on (boiler setting, HW=A)" if self._attr_is_on else "off (HW=0)")
        await self._coordinator.async_set_hot_water_keep_warm(self._attr_is_on)
        await self._store.async_save({"keep_warm_off": not self._attr_is_on})
