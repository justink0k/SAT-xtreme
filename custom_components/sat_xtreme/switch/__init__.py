from __future__ import annotations

from typing import Mapping, Any

from homeassistant.components.input_boolean import DOMAIN as INPUT_BOOLEAN_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.valve import DOMAIN as VALVE_DOMAIN, ValveState
from homeassistant.const import SERVICE_CLOSE_VALVE, SERVICE_OPEN_VALVE, SERVICE_TURN_ON, SERVICE_TURN_OFF, ATTR_ENTITY_ID, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity_registry import RegistryEntry

from ..coordinator import DeviceState, SatDataUpdateCoordinator

# This package is also the switch platform of the integration; the fork's switch lives in xtreme/switch.py
from ..xtreme.switch import async_setup_entry  # noqa: F401

# Per domain: the service to turn the entity on and off (Xtreme fork: the wizard also offers valves, which got no command)
DOMAIN_SERVICES = {
    SWITCH_DOMAIN: (SERVICE_TURN_ON, SERVICE_TURN_OFF),
    INPUT_BOOLEAN_DOMAIN: (SERVICE_TURN_ON, SERVICE_TURN_OFF),
    VALVE_DOMAIN: (SERVICE_OPEN_VALVE, SERVICE_CLOSE_VALVE),
}

STATES_ON = (STATE_ON, ValveState.OPEN, ValveState.OPENING)


class SatSwitchCoordinator(SatDataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entity_id: str, config_data: Mapping[str, Any], options: Mapping[str, Any] | None = None) -> None:
        """Initialize."""
        super().__init__(hass, config_data, options)

        # Xtreme fork: keep the entity ID itself; the registry entry is optional (an input_boolean from YAML has none)
        self._entity_id: str = entity_id
        self._entity: RegistryEntry | None = entity_registry.async_get(hass).async_get(entity_id)

    @property
    def device_id(self) -> str:
        if self._entity is not None and self._entity.name:
            return self._entity.name

        return self._entity_id

    @property
    def device_type(self) -> str:
        return "Switch"

    @property
    def setpoint(self) -> float:
        return self.minimum_setpoint

    @property
    def maximum_setpoint(self) -> float:
        return self.minimum_setpoint

    @property
    def device_active(self) -> bool:
        # Xtreme fork: read the state by entity ID; the registry ID found no state, so SAT never saw the switch on
        if (state := self.hass.states.get(self._entity_id)) is None:
            return False

        return state.state in STATES_ON

    @property
    def member_id(self) -> int | None:
        return -1

    async def async_set_heater_state(self, state: DeviceState) -> None:
        if not self._simulation:
            domain = self._entity_id.split(".", 1)[0]

            if services := DOMAIN_SERVICES.get(domain):
                service = services[0] if state == DeviceState.ON else services[1]
                await self.hass.services.async_call(domain, service, {ATTR_ENTITY_ID: self._entity_id}, blocking=True)

        await super().async_set_heater_state(state)
