"""Tests for the setpoint chain sensor: calculated, sent and received setpoint (diagnostics, read only)."""
import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.coordinator import DeviceState
from custom_components.sat_xtreme.xtreme.profile import XtremeProfile
from tests.fake_coordinator import SatFakeCoordinator
from tests.xtreme_helpers import MINIMUM_SETPOINT_VALUE, parameters, xtreme_profile_input

UNIQUE_ID = "test-xtreme-setpoint-chain"


def _entity_id(hass: HomeAssistant) -> str | None:
    return er.async_get(hass).async_get_entity_id("sensor", DOMAIN, UNIQUE_ID)


async def _start_heating(climate: SatClimate, calculated_setpoint: float) -> None:
    await climate.async_set_target_temperature(20.5)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    climate._calculated_setpoint = calculated_setpoint


async def _attributes(hass: HomeAssistant, climate: SatClimate) -> dict:
    climate.async_write_ha_state()
    await hass.async_block_till_done()

    return dict(hass.states.get(_entity_id(hass)).attributes)


def test_profile_defaults_to_off():
    assert XtremeProfile.from_options({}).setpoint_chain is False
    assert XtremeProfile.from_options({CONF_XTREME_SETPOINT_CHAIN: True}).setpoint_chain is True
    assert "setpoint_chain" in XtremeProfile.from_options({CONF_XTREME_SETPOINT_CHAIN: True}).active_switches


@pytest.mark.parametrize(*parameters())
async def test_option_on_the_xtreme_profile_page(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "xtreme_profile"})

    diagnostics = result["data_schema"].schema["diagnostics"].schema
    assert {str(key): key.default() for key in diagnostics.schema} == {CONF_XTREME_SETPOINT_CHAIN: False, CONF_XTREME_CYCLE_TRACKING: False}

    result = await hass.config_entries.options.async_configure(result["flow_id"], xtreme_profile_input(**{CONF_XTREME_SETPOINT_CHAIN: True}))
    await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert entry.options[CONF_XTREME_SETPOINT_CHAIN] is True
    assert _entity_id(hass) is not None


@pytest.mark.parametrize(*parameters())
async def test_no_sensor_when_off(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    assert _entity_id(hass) is None


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_SETPOINT_CHAIN: True}))
async def test_sensor_shows_the_calculated_setpoint(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    await _start_heating(climate, 40.0)
    climate.async_write_ha_state()
    await hass.async_block_till_done()

    state = hass.states.get(_entity_id(hass))
    assert float(state.state) == climate.requested_setpoint
    assert state.attributes["filtered_setpoint"] == 40.0
    assert state.attributes["unit_of_measurement"] == "°C"


@pytest.mark.parametrize(*parameters(force_pwm=False, overshoot_protection=False, **{CONF_XTREME_SETPOINT_CHAIN: True}))
async def test_sent_and_received_setpoint(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _start_heating(climate, 52.0)
    await climate._async_control_setpoint(climate.pwm.state)
    await coordinator.async_set_heater_state(DeviceState.ON)

    attributes = await _attributes(hass, climate)
    assert attributes["sent_setpoint"] == 52.0
    assert attributes["sent_at"] is not None
    assert attributes["heating_demand_sent"] == "on"
    assert attributes["received_setpoint"] == 52.0
    assert attributes["difference"] == 0.0
    assert attributes["pwm_status"] == "idle"


@pytest.mark.parametrize(*parameters(force_pwm=False, overshoot_protection=False, **{CONF_XTREME_SETPOINT_CHAIN: True}))
async def test_difference_when_the_boiler_has_another_setpoint(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _start_heating(climate, 52.0)
    await climate._async_control_setpoint(climate.pwm.state)

    # The gateway still reports the setpoint of the thermostat on the bus
    coordinator._setpoint = 35.0

    attributes = await _attributes(hass, climate)
    assert attributes["sent_setpoint"] == 52.0
    assert attributes["received_setpoint"] == 35.0
    assert attributes["difference"] == -17.0


@pytest.mark.parametrize(*parameters(force_pwm=False, overshoot_protection=False, **{CONF_XTREME_SETPOINT_CHAIN: True}))
async def test_sent_setpoint_is_limited_by_the_maximum(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _start_heating(climate, 70.0)
    await climate._async_control_setpoint(climate.pwm.state)

    attributes = await _attributes(hass, climate)
    assert attributes["filtered_setpoint"] == 70.0
    assert attributes["sent_setpoint"] == coordinator.maximum_setpoint == 60


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_SETPOINT_CHAIN: True, CONF_XTREME_PRIME_SETPOINT: True}))
async def test_primed_setpoint_in_the_pwm_off_phase(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _start_heating(climate, 40.0)
    climate.pwm._status = PWMStatus.OFF
    await climate._async_control_setpoint(climate.pwm.state)
    await coordinator.async_set_heater_state(DeviceState.OFF)

    attributes = await _attributes(hass, climate)
    assert attributes["sent_setpoint"] == MINIMUM_SETPOINT_VALUE
    assert attributes["heating_demand_sent"] == "off"
    assert attributes["pwm_status"] == "off"


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_SETPOINT_CHAIN: True}))
async def test_nothing_sent_yet(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    coordinator._control_setpoint_sent = None
    coordinator._control_setpoint_sent_at = None

    attributes = await _attributes(hass, climate)
    assert attributes["sent_setpoint"] is None
    assert attributes["sent_at"] is None
    assert attributes["difference"] is None
