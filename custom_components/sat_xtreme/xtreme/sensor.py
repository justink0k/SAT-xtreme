"""Sensors of the Xtreme profile, for following the profile on a dashboard."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfTime
from homeassistant.core import Event, EventStateChangedData
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from ..const import CONF_NAME
from ..entity import SatClimateEntity, SatEntity

FORK_LABEL = "Xtreme fork:"


def async_setup_xtreme_sensors(coordinator, config_entry: ConfigEntry, climate, async_add_entities: AddEntitiesCallback) -> None:
    """Add the sensors of the active Xtreme profile switches."""
    profile = coordinator.xtreme_profile
    entities = [
        SatPidOutputSensor(coordinator, config_entry, climate),
        SatBoilerFlowSensor(coordinator, config_entry),
        SatControlSetpointSensor(coordinator, config_entry),
        SatModulationSensor(coordinator, config_entry),
        SatBurnerStartsSensor(coordinator, config_entry),
    ]

    if profile.boiler_timing:
        entities += [
            SatPwmBurnTimeSensor(coordinator, config_entry, climate),
            SatAntiCyclingRemainingSensor(coordinator, config_entry, climate),
        ]

    if profile.learned_opv != "off":
        entities.append(SatLearnedOpvSensor(coordinator, config_entry, climate))

    if profile.calibration:
        entities.append(SatCalibrationSensor(coordinator, config_entry, climate))

    if profile.setpoint_chain:
        entities.append(SatSetpointChainSensor(coordinator, config_entry, climate))

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
        # Make clear in the user interface that the entity belongs to the fork
        return f"{FORK_LABEL} {self._label} {self._config_entry.data.get(CONF_NAME)}"

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


class SatLearnedOpvSensor(SatXtremeSensor):
    """The learned overshoot protection value, with the learning details as attributes."""

    _key = "learned-opv"
    _label = "Learned OPV"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float:
        return self._climate.learned_opv.value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._climate.learned_opv.attributes


class SatCalibrationSensor(SatXtremeSensor):
    """Phase and progress of the Xtreme calibration, with the last report as an attribute."""

    _key = "calibration"
    _label = "Calibration"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["idle", "waiting", "testing_modulation", "heating", "paused_hot_water", "paused_comfort", "cooldown", "succeeded", "failed", "cancelled"]

    @property
    def native_value(self) -> str:
        return self._climate.xtreme_calibration.phase.value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._climate.xtreme_calibration.attributes


class SatPidOutputSensor(SatXtremeSensor):
    """The correction of the PID controller on top of the heating curve, with its parts and gains."""

    _key = "pid-output"
    _label = "PID Output"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float:
        return round(self._climate.pid.output, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        pid = self._climate.pid

        return {
            "heating_curve": self._climate.heating_curve.value,
            "requested_setpoint": self._climate.requested_setpoint,
            "proportional": pid.proportional,
            "integral": pid.integral,
            "derivative": pid.derivative,
            "kp": pid.kp,
            "ki": pid.ki,
            "kd": pid.kd,
            "automatic_gains": pid.automatic_gains,
            "gain_factor": pid.gain_factor,
            "maximum_setpoint_rise": self._coordinator.xtreme_profile.maximum_setpoint_rise,
        }


class SatSetpointChainSensor(SatXtremeSensor):
    """The setpoint SAT calculates, the one it sends to the gateway and the one the gateway reports for the boiler."""

    _key = "setpoint-chain"
    _label = "Setpoint Chain"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        return self._climate.requested_setpoint

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        sent = self._coordinator.control_setpoint_sent
        received = self._coordinator.setpoint
        sent_at = self._coordinator.control_setpoint_sent_at
        heater_state = self._coordinator.heater_state_commanded

        return {
            "filtered_setpoint": self._climate.calculated_setpoint,
            "sent_setpoint": sent,
            "sent_at": sent_at.isoformat() if sent_at is not None else None,
            "heating_demand_sent": heater_state.value if heater_state is not None else None,
            "received_setpoint": received,
            "difference": round(received - sent, 1) if sent is not None and received is not None else None,
            "pwm_status": self._climate.pwm.status.value,
        }


class SatXtremeBoilerSensor(SatEntity, SensorEntity):
    """Base class for sensors that show boiler data as SAT sees it, for any gateway."""

    _key: str = ""
    _label: str = ""

    @property
    def name(self) -> str:
        return f"{FORK_LABEL} {self._label} {self._config_entry.data.get(CONF_NAME)}"

    @property
    def unique_id(self) -> str:
        return f"{self._config_entry.data.get(CONF_NAME).lower()}-xtreme-{self._key}"


class SatBoilerFlowSensor(SatXtremeBoilerSensor):
    _key = "boiler-flow"
    _label = "Boiler Flow"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        return self._coordinator.boiler_temperature


class SatControlSetpointSensor(SatXtremeBoilerSensor):
    _key = "control-setpoint"
    _label = "Control Setpoint"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        return self._coordinator.setpoint


class SatModulationSensor(SatXtremeBoilerSensor):
    _key = "modulation"
    _label = "Boiler Modulation"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:fire"

    @property
    def native_value(self) -> float | None:
        return self._coordinator.relative_modulation_value


class SatBurnerStartsSensor(SatXtremeBoilerSensor, RestoreEntity):
    """Burner starts counted by SAT (heating and hot water), kept across restarts."""

    _key = "burner-starts"
    _label = "Burner Starts"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator, config_entry: ConfigEntry):
        super().__init__(coordinator, config_entry)
        self._restored: int = 0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            try:
                self._restored = int(float(last_state.state))
            except (TypeError, ValueError):
                self._restored = 0

    @property
    def native_value(self) -> int:
        return self._restored + self._coordinator.flame_start_count
