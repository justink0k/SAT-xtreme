"""Tests for the Xtreme profile, step 1: prime the setpoint during the PWM off phase."""
from unittest.mock import patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.template import DOMAIN as TEMPLATE_DOMAIN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.coordinator import DeviceState
from tests.fake_coordinator import MODE_FAKE, SatFakeCoordinator
from custom_components.sat_xtreme.flame import Flame
from custom_components.sat_xtreme.xtreme.profile import XtremeProfile
from tests.xtreme_helpers import xtreme_profile_input

MINIMUM_SETPOINT_VALUE = 46

TEMPLATE_CONFIG = {
    TEMPLATE_DOMAIN: [
        {
            SENSOR_DOMAIN: [
                {"name": "test_inside_sensor", "state": "{{ 20.0 | float }}"},
                {"name": "test_outside_sensor", "state": "{{ 12.0 | float }}"},
            ]
        },
    ],
}


def _parameters(prime_setpoint: bool, force_pwm: bool = True, overshoot_protection: bool = True):
    return [
        "domains, data, options, config",
        [(
            [(TEMPLATE_DOMAIN, 1)],
            {
                CONF_MODE: MODE_FAKE,
                CONF_HEATING_SYSTEM: HEATING_SYSTEM_RADIATORS,
                CONF_MINIMUM_SETPOINT: MINIMUM_SETPOINT_VALUE,
                CONF_OVERSHOOT_PROTECTION: overshoot_protection,
            },
            {
                CONF_MAXIMUM_SETPOINT: 60,
                CONF_HEATING_CURVE_COEFFICIENT: 2.0,
                CONF_FORCE_PULSE_WIDTH_MODULATION: force_pwm,
                CONF_XTREME_PRIME_SETPOINT: prime_setpoint,
            },
            TEMPLATE_CONFIG,
        )],
    ]


async def _start_heating(climate: SatClimate) -> None:
    await climate.async_set_target_temperature(20.5)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    climate._calculated_setpoint = 40.0


class _Clock:
    """A controllable monotonic clock."""

    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_profile_defaults_to_off():
    assert XtremeProfile.from_options({}).prime_setpoint is False
    assert XtremeProfile.from_options(None).enabled is False
    assert XtremeProfile.from_options({CONF_XTREME_PRIME_SETPOINT: True}).prime_setpoint is True


@pytest.mark.parametrize(*_parameters(prime_setpoint=True))
async def test_off_phase_primes_setpoint_with_heating_demand_off(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _start_heating(climate)
    climate.pwm._status = PWMStatus.OFF

    await climate._async_control_setpoint(climate.pwm.state)

    assert climate.pulse_width_modulation_enabled
    assert climate.setpoint == MINIMUM_SETPOINT_VALUE
    assert coordinator.setpoint == MINIMUM_SETPOINT_VALUE
    assert climate._desired_heater_state() == DeviceState.OFF


@pytest.mark.parametrize(*_parameters(prime_setpoint=True))
async def test_on_phase_is_unchanged(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _start_heating(climate)
    climate.pwm._status = PWMStatus.ON

    await climate._async_control_setpoint(climate.pwm.state)

    assert coordinator.setpoint == MINIMUM_SETPOINT_VALUE
    assert climate._desired_heater_state() == DeviceState.ON


@pytest.mark.parametrize(*_parameters(prime_setpoint=False))
async def test_off_phase_without_profile_is_upstream(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _start_heating(climate)
    climate.pwm._status = PWMStatus.OFF

    await climate._async_control_setpoint(climate.pwm.state)

    assert coordinator.setpoint == MINIMUM_SETPOINT
    assert climate._desired_heater_state() == DeviceState.OFF


@pytest.mark.parametrize(*_parameters(prime_setpoint=True))
async def test_hvac_off_uses_minimum_setpoint_and_heater_off(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _start_heating(climate)
    await coordinator.async_set_heater_state(DeviceState.ON)

    await climate.async_set_hvac_mode(HVACMode.OFF)
    await climate._async_control_setpoint(climate.pwm.state)

    assert coordinator.setpoint == MINIMUM_SETPOINT
    assert coordinator.heater_state_commanded == DeviceState.OFF
    assert not coordinator.device_active
    assert climate._desired_heater_state() == DeviceState.OFF


@pytest.mark.parametrize(*_parameters(prime_setpoint=True, force_pwm=False, overshoot_protection=False))
async def test_continuous_operation_is_unchanged(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _start_heating(climate)
    climate._calculated_setpoint = 52.0

    await climate._async_control_setpoint(climate.pwm.state)

    assert not climate.pulse_width_modulation_enabled
    assert coordinator.setpoint == 52.0
    assert climate._desired_heater_state() == DeviceState.ON


@pytest.mark.parametrize(*_parameters(prime_setpoint=True))
async def test_heater_off_is_not_resent(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    clock = _Clock()

    with patch("custom_components.sat_xtreme.coordinator.monotonic", clock), \
            patch.object(SatFakeCoordinator, "async_set_heater_state", wraps=coordinator.async_set_heater_state, autospec=False) as spy:
        await climate.async_set_heater_state(DeviceState.OFF)
        await climate.async_set_heater_state(DeviceState.OFF)
        assert spy.call_count == 1

        # Later on, the boiler confirms the state, so there is still nothing to send
        clock.now += 120
        await climate.async_set_heater_state(DeviceState.OFF)
        assert spy.call_count == 1


@pytest.mark.parametrize(*_parameters(prime_setpoint=True))
async def test_heater_off_is_sent_while_boiler_has_not_started(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    # The on phase asked for heat, but the boiler is still anti-cycling: the status bit stays off.
    await coordinator.async_set_heater_state(DeviceState.ON)
    coordinator._device_state = DeviceState.OFF
    assert not coordinator.device_active

    # Upstream would skip this ("already off"), leaving the demand on with a primed setpoint.
    await climate.async_set_heater_state(DeviceState.OFF)

    assert coordinator.heater_state_commanded == DeviceState.OFF


@pytest.mark.parametrize(*_parameters(prime_setpoint=True))
async def test_heater_off_is_resent_when_boiler_does_not_confirm(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    clock = _Clock()

    with patch("custom_components.sat_xtreme.coordinator.monotonic", clock):
        await coordinator.async_set_heater_state(DeviceState.OFF)

        # The command got lost: the boiler still reports central heating after the repeat window
        coordinator._device_state = DeviceState.ON
        clock.now += 60

        with patch.object(SatFakeCoordinator, "async_set_heater_state", wraps=coordinator.async_set_heater_state, autospec=False) as spy:
            await climate.async_set_heater_state(DeviceState.OFF)
            assert spy.call_count == 1


@pytest.mark.parametrize(*_parameters(prime_setpoint=True))
async def test_primed_setpoint_without_demand_is_idle(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await coordinator.async_set_boiler_temperature(46)
    await coordinator.async_set_control_setpoint(MINIMUM_SETPOINT_VALUE)
    await coordinator.async_set_heater_state(DeviceState.OFF)

    assert coordinator.heater_primed_idle
    assert coordinator.device_status == BoilerStatus.IDLE


@pytest.mark.parametrize(*_parameters(prime_setpoint=False))
async def test_primed_setpoint_without_profile_is_not_idle(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await coordinator.async_set_boiler_temperature(46)
    await coordinator.async_set_control_setpoint(MINIMUM_SETPOINT_VALUE)
    await coordinator.async_set_heater_state(DeviceState.OFF)

    assert not coordinator.heater_primed_idle
    assert coordinator.device_status == BoilerStatus.AT_SETPOINT


@pytest.mark.parametrize(*_parameters(prime_setpoint=True))
async def test_long_off_phase_is_not_stuck_off(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    clock = _Clock()
    flame = Flame()

    await coordinator.async_set_boiler_temperature(46)
    await coordinator.async_set_control_setpoint(MINIMUM_SETPOINT_VALUE)

    with patch("custom_components.sat_xtreme.flame.monotonic", clock):
        # A burn, followed by a primed off phase of 15 minutes
        await coordinator.async_set_heater_state(DeviceState.ON)
        flame.update(boiler_state=coordinator.boiler)
        clock.now += 300
        flame.update(boiler_state=coordinator.boiler)

        await coordinator.async_set_heater_state(DeviceState.OFF)
        for _ in range(15):
            clock.now += 60
            flame.update(boiler_state=coordinator.boiler)

    assert flame.health_status != FlameStatus.STUCK_OFF


@pytest.mark.parametrize(*_parameters(prime_setpoint=True))
async def test_heating_loop_keeps_demand_off_in_off_phase(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await coordinator.async_set_boiler_temperature(46)
    await climate.async_set_target_temperature(20.5)
    await climate.async_set_hvac_mode(HVACMode.HEAT)

    async def _keep_off(*_args, **_kwargs):
        climate.pwm._status = PWMStatus.OFF

    with patch.object(climate.pwm, "update", side_effect=_keep_off):
        await climate.async_control_heating_loop()

    assert climate.pwm.status == PWMStatus.OFF
    assert coordinator.setpoint == MINIMUM_SETPOINT_VALUE
    assert not coordinator.device_active
    assert coordinator.heater_state_commanded == DeviceState.OFF


@pytest.mark.parametrize(*_parameters(prime_setpoint=True))
async def test_maximum_setpoint_is_never_exceeded(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _start_heating(climate)
    climate.pwm._status = PWMStatus.OFF

    with patch.object(SatClimate, "minimum_setpoint_value", new=70.0):
        await climate._async_control_setpoint(climate.pwm.state)

    assert coordinator.setpoint == 60


@pytest.mark.parametrize(*_parameters(prime_setpoint=False))
async def test_options_flow_has_xtreme_profile_switch(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "xtreme_profile" in result["menu_options"]

    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "xtreme_profile"})
    assert result["step_id"] == "xtreme_profile"

    result = await hass.config_entries.options.async_configure(result["flow_id"], xtreme_profile_input(**{CONF_XTREME_PRIME_SETPOINT: True}))
    assert result["type"] == "create_entry"
    assert entry.options[CONF_XTREME_PRIME_SETPOINT] is True
