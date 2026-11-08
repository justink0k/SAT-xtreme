from __future__ import annotations

import logging
from typing import Callable, Optional

from homeassistant.components import mqtt
from homeassistant.core import callback

from . import SatMqttCoordinator
from ..coordinator import DeviceState
from ..manufacturers.ideal import Ideal
from ..manufacturers.immergas import Immergas
from ..manufacturers.intergas import Intergas
from ..manufacturers.nefit import Nefit

STATE_ON = "ON"

DATA_FLAME_ACTIVE = "flame"
DATA_DHW_SETPOINT = "TdhwSet"
DATA_CONTROL_SETPOINT = "TSet"
DATA_MAXIMUM_CONTROL_SETPOINT = "MaxTSet"
DATA_MAXIMUM_CONTROL_SETPOINT_UPPER_BOUND = "MaxTSetUBMaxTSetLB_value_hb"
DATA_REL_MOD_LEVEL = "RelModLevel"
DATA_BOILER_TEMPERATURE = "Tboiler"
DATA_RETURN_TEMPERATURE = "Tret"
DATA_DHW_ENABLE = "domestichotwater"
DATA_CENTRAL_HEATING = "centralheating"
DATA_SLAVE_MEMBERID = "slave_memberid_code"
DATA_BOILER_CAPACITY = "MaxCapacityMinModLevel_hb_u8"
DATA_REL_MIN_MOD_LEVEL = "MaxCapacityMinModLevel_lb_u8"
DATA_REL_MIN_MOD_LEVEL_LEGACY = "MaxCapacityMinModLevell_lb_u8"
DATA_MAX_REL_MOD_LEVEL_SETTING = "MaxRelModLevelSetting"
DATA_DHW_SETPOINT_MINIMUM = "TdhwSetUBTdhwSetLB_value_lb"
DATA_DHW_SETPOINT_MAXIMUM = "TdhwSetUBTdhwSetLB_value_hb"

# Xtreme fork: the overrides SAT sets on the gateway, in the order they are sent again after a gateway restart
OVERRIDE_ORDER = ("SH", "SW", "HW", "MM", "TC", "CH", "CS")

_LOGGER: logging.Logger = logging.getLogger(__name__)


class SatOpenThermMqttCoordinator(SatMqttCoordinator):
    """Class to manage to fetch data from the OTGW Gateway using mqtt."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # Xtreme fork: the gateway's will message, None until the first one arrives
        self._online: Optional[bool] = None
        self._overrides: dict[str, str] = {}
        self._availability_unsub: Optional[Callable[[], None]] = None

    @property
    def supports_online_status(self) -> bool:
        return True

    @property
    def online(self) -> bool:
        # Firmware without a will message never reports offline
        return self._online is not False

    @property
    def device_type(self) -> str:
        return "OpenThermGateway (via mqtt)"

    @property
    def supports_setpoint_management(self):
        return True

    @property
    def supports_hot_water_setpoint_management(self):
        return True

    @property
    def supports_maximum_setpoint_management(self):
        return True

    @property
    def supports_relative_modulation(self):
        return True

    @property
    def device_active(self) -> bool:
        return self.data.get(DATA_CENTRAL_HEATING) == STATE_ON

    @property
    def flame_active(self) -> bool:
        return self.data.get(DATA_FLAME_ACTIVE) == STATE_ON

    @property
    def hot_water_active(self) -> bool:
        return self.data.get(DATA_DHW_ENABLE) == STATE_ON

    @property
    def setpoint(self) -> Optional[float]:
        if (setpoint := self.data.get(DATA_CONTROL_SETPOINT)) is not None:
            return float(setpoint)

        return None

    @property
    def maximum_setpoint_value(self) -> Optional[float]:
        if (setpoint := self.data.get(DATA_MAXIMUM_CONTROL_SETPOINT)) is not None:
            return float(setpoint)

        return super().maximum_setpoint_value

    @property
    def boiler_maximum_setpoint_bound(self) -> Optional[float]:
        if (value := self.data.get(DATA_MAXIMUM_CONTROL_SETPOINT_UPPER_BOUND)) is not None:
            return float(value)

        return super().boiler_maximum_setpoint_bound

    @property
    def hot_water_setpoint(self) -> Optional[float]:
        if (setpoint := self.data.get(DATA_DHW_SETPOINT)) is not None:
            return float(setpoint)

        return super().hot_water_setpoint

    @property
    def minimum_hot_water_setpoint(self) -> float:
        if (setpoint := self.data.get(DATA_DHW_SETPOINT_MINIMUM)) is not None:
            return float(setpoint)

        return super().minimum_hot_water_setpoint

    @property
    def maximum_hot_water_setpoint(self) -> float:
        if (setpoint := self.data.get(DATA_DHW_SETPOINT_MAXIMUM)) is not None:
            return float(setpoint)

        return super().maximum_hot_water_setpoint

    @property
    def boiler_temperature(self) -> Optional[float]:
        if (value := self.data.get(DATA_BOILER_TEMPERATURE)) is not None:
            return float(value)

        return super().boiler_temperature

    @property
    def return_temperature(self) -> Optional[float]:
        if (value := self.data.get(DATA_RETURN_TEMPERATURE)) is not None:
            return float(value)

        return super().return_temperature

    @property
    def relative_modulation_value(self) -> Optional[float]:
        if (value := self.data.get(DATA_REL_MOD_LEVEL)) is not None:
            return float(value)

        return super().relative_modulation_value

    @property
    def boiler_capacity(self) -> Optional[float]:
        if (value := self.data.get(DATA_BOILER_CAPACITY)) is not None:
            return float(value)

        return super().boiler_capacity

    @property
    def minimum_relative_modulation_value(self) -> Optional[float]:
        if (value := self.data.get(DATA_REL_MIN_MOD_LEVEL)) is not None:
            return float(value)

        # Legacy
        if (value := self.data.get(DATA_REL_MIN_MOD_LEVEL_LEGACY)) is not None:
            return float(value)

        return super().minimum_relative_modulation_value

    @property
    def maximum_relative_modulation_value(self) -> Optional[float]:
        if (value := self.data.get(DATA_MAX_REL_MOD_LEVEL_SETTING)) is not None:
            return float(value)

        return super().maximum_relative_modulation_value

    @property
    def member_id(self) -> Optional[int]:
        if (value := self.data.get(DATA_SLAVE_MEMBERID)) is not None:
            return int(value)

        return None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        # OTGW-firmware publishes its will message, "online" or "offline", retained on the bare value topic
        self._availability_unsub = await mqtt.async_subscribe(self.hass, f"{self._topic}/value/{self._device_id}", self._availability_changed)

    async def async_will_remove_from_hass(self) -> None:
        if self._availability_unsub is not None:
            self._availability_unsub()
            self._availability_unsub = None

        await super().async_will_remove_from_hass()

    @callback
    def _availability_changed(self, message) -> None:
        """Xtreme fork: track the gateway's will message, and restore the overrides after a restart (idea from bellini666/SAT)."""
        payload = message.payload.decode() if isinstance(message.payload, bytes) else str(message.payload)
        online = payload.strip().lower() == "online"

        if online != self._online:
            if not online:
                _LOGGER.warning("The OpenTherm Gateway went offline; SAT pauses its control until it is back.")
            elif self._online is False:
                _LOGGER.info("The OpenTherm Gateway is back online.")

            self._online = online
            self.async_update_listeners()

        # A retained "online" is the broker replaying the last state; a live one is a gateway that (re)started and
        # dropped every override, also after a clean restart without an "offline" before it
        if online and not message.retain:
            self.hass.async_create_task(self.async_restore_overrides())

    async def async_restore_overrides(self) -> None:
        """Xtreme fork: send the boot commands and the last value of every override SAT set again."""
        _LOGGER.info("The OpenTherm Gateway (re)started, sending the overrides of SAT again: %s", ", ".join(self._overrides.values()) or "none")

        await self.boot()

        for key in OVERRIDE_ORDER:
            if (payload := self._overrides.get(key)) is None:
                continue

            await self._publish_command(payload)

            if key == "CS" and payload != "CS=0":
                await self._publish_command("PM=25")

    async def _publish_override(self, key: str, payload: str) -> None:
        """Xtreme fork: publish an override and remember it, so it can be sent again after a gateway restart."""
        self._overrides[key] = payload
        await self._publish_command(payload)

    async def boot(self) -> None:
        await self._publish_command("PM=3")
        await self._publish_command("PM=15")
        await self._publish_command("PM=48")

        if isinstance(self.manufacturer, (Ideal, Intergas, Nefit)):
            await self._publish_command("MI=500")

    def get_tracked_entities(self) -> list[str]:
        return [
            DATA_SLAVE_MEMBERID,
            DATA_CENTRAL_HEATING,
            DATA_FLAME_ACTIVE,
            DATA_DHW_ENABLE,
            DATA_DHW_SETPOINT,
            DATA_CONTROL_SETPOINT,
            DATA_REL_MOD_LEVEL,
            DATA_BOILER_TEMPERATURE,
            DATA_RETURN_TEMPERATURE,
            DATA_BOILER_CAPACITY,
            DATA_REL_MIN_MOD_LEVEL,
            DATA_REL_MIN_MOD_LEVEL_LEGACY,
            DATA_MAX_REL_MOD_LEVEL_SETTING,
            DATA_DHW_SETPOINT_MINIMUM,
            DATA_DHW_SETPOINT_MAXIMUM,
            DATA_MAXIMUM_CONTROL_SETPOINT_UPPER_BOUND,
        ]

    async def async_set_control_setpoint(self, value: float) -> None:
        await self._publish_override("CS", f"CS={value}")
        await self._publish_command(f"PM=25")

        await super().async_set_control_setpoint(value)

    @property
    def supports_setpoint_release(self) -> bool:
        return True

    async def async_release_control_setpoint(self) -> None:
        # CS=0 hands the control setpoint (and the central heating enable bit) back to the thermostat
        await self._publish_override("CS", "CS=0")

        await super().async_release_control_setpoint()

    @property
    def supports_hot_water_keep_warm_control(self) -> bool:
        return True

    async def async_set_hot_water_keep_warm(self, enabled: bool) -> None:
        # HW=A leaves the DHW enable bit to the thermostat on the bus (normal operation), HW=0 clears it.
        # The gateway keeps this setting until it is changed again; it has no heartbeat.
        await self._publish_override("HW", "HW=A" if enabled else "HW=0")

        await super().async_set_hot_water_keep_warm(enabled)

    async def async_set_control_hot_water_setpoint(self, value: float) -> None:
        await self._publish_override("SW", f"SW={value}")

        await super().async_set_control_hot_water_setpoint(value)

    async def async_set_control_thermostat_setpoint(self, value: float) -> None:
        await self._publish_override("TC", f"TC={value}")

        await super().async_set_control_thermostat_setpoint(value)

    async def async_set_heater_state(self, state: DeviceState) -> None:
        await self._publish_override("CH", f"CH={1 if state == DeviceState.ON else 0}")

        await super().async_set_heater_state(state)

    async def async_set_control_max_relative_modulation(self, value: int) -> None:
        if isinstance(self.manufacturer, Immergas):
            await self._publish_command(f"TP=11:12={min(value, 80)}")

        await self._publish_override("MM", f"MM={value}")

        await super().async_set_control_max_relative_modulation(value)

    async def async_set_control_max_setpoint(self, value: float) -> None:
        await self._publish_override("SH", f"SH={value}")

        await super().async_set_control_max_setpoint(value)

    def _get_topic_for_subscription(self, key: str) -> str:
        return f"{self._topic}/value/{self._device_id}/{key}"

    def _get_topic_for_publishing(self) -> str:
        return f"{self._topic}/set/{self._device_id}/command"
