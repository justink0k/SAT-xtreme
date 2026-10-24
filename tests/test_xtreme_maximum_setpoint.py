"""Tests for the maximum setpoint number entity of the Xtreme profile."""
from unittest.mock import PropertyMock, patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.components.number import ATTR_VALUE, DOMAIN as NUMBER_DOMAIN, SERVICE_SET_VALUE
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.mqtt.opentherm import DATA_MAXIMUM_CONTROL_SETPOINT_UPPER_BOUND, SatOpenThermMqttCoordinator
from custom_components.sat_xtreme.xtreme.number import maximum_setpoint_ceiling
from custom_components.sat_xtreme.xtreme.profile import XtremeProfile
from tests.fake_coordinator import SatFakeCoordinator
from tests.xtreme_helpers import MINIMUM_SETPOINT_VALUE, parameters

ENABLED = {CONF_XTREME_MAXIMUM_SETPOINT_ENTITY: True}


def _entity_id(hass: HomeAssistant) -> str | None:
    return er.async_get(hass).async_get_entity_id("number", DOMAIN, "test-xtreme-maximum-setpoint")


async def _set(hass: HomeAssistant, value: float) -> None:
    await hass.services.async_call(NUMBER_DOMAIN, SERVICE_SET_VALUE, {ATTR_ENTITY_ID: _entity_id(hass), ATTR_VALUE: value}, blocking=True)


def test_profile_defaults_to_off():
    assert XtremeProfile.from_options({}).maximum_setpoint_entity is False
    assert XtremeProfile.from_options(ENABLED).maximum_setpoint_entity is True


def test_ceilings_per_heating_system():
    assert maximum_setpoint_ceiling(HEATING_SYSTEM_RADIATORS) == 75
    assert maximum_setpoint_ceiling(HEATING_SYSTEM_UNDERFLOOR) == 50
    assert maximum_setpoint_ceiling(HEATING_SYSTEM_HEAT_PUMP) == 55
    assert maximum_setpoint_ceiling(HEATING_SYSTEM_UNKNOWN) == 55


@pytest.mark.parametrize(*parameters())
async def test_no_entity_when_off(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    assert _entity_id(hass) is None


@pytest.mark.parametrize(*parameters(**ENABLED))
async def test_entity_shows_the_option_with_its_bounds(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    state = hass.states.get(_entity_id(hass))

    assert float(state.state) == 60
    assert state.attributes["min"] == MINIMUM_SETPOINT_VALUE
    assert state.attributes["max"] == 75
    assert state.attributes["opv"] == MINIMUM_SETPOINT_VALUE


@pytest.mark.parametrize(*parameters(**ENABLED))
async def test_change_is_stored_and_used_right_away(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _set(hass, 52)

    assert entry.options[CONF_MAXIMUM_SETPOINT] == 52
    assert coordinator.maximum_setpoint == 52
    assert coordinator._maximum_setpoint == 52
    assert float(hass.states.get(_entity_id(hass)).state) == 52


@pytest.mark.parametrize(*parameters(force_pwm=False, overshoot_protection=False, **ENABLED))
async def test_the_sent_setpoint_never_goes_above_the_new_maximum(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _set(hass, 52)

    await climate.async_set_target_temperature(20.5)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    climate._calculated_setpoint = 70.0
    await climate._async_control_setpoint(climate.pwm.state)

    assert coordinator.setpoint == 52


@pytest.mark.parametrize(*parameters(**ENABLED))
async def test_value_is_kept_after_a_reload(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    await _set(hass, 52)

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.data[DOMAIN][entry.entry_id][COORDINATOR].maximum_setpoint == 52
    assert float(hass.states.get(_entity_id(hass)).state) == 52


@pytest.mark.parametrize(*parameters(**ENABLED))
async def test_values_outside_the_bounds_are_refused(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    for value in (MINIMUM_SETPOINT_VALUE - 1, 76):
        with pytest.raises((HomeAssistantError, ValueError)):
            await _set(hass, value)

    assert coordinator.maximum_setpoint == 60
    assert entry.options[CONF_MAXIMUM_SETPOINT] == 60


@pytest.mark.parametrize(*parameters(**ENABLED))
async def test_the_boiler_bound_lowers_the_ceiling(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    with patch.object(SatFakeCoordinator, "boiler_maximum_setpoint_bound", new_callable=PropertyMock, return_value=65.0):
        climate.async_write_ha_state()
        entity = hass.data["number"].get_entity(_entity_id(hass))
        entity.async_write_ha_state()

        assert hass.states.get(_entity_id(hass)).attributes["max"] == 65

        with pytest.raises((HomeAssistantError, ValueError)):
            await _set(hass, 70)


@pytest.mark.parametrize(*parameters(**ENABLED))
async def test_the_learned_opv_raises_the_floor(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    with patch.object(type(climate.learned_opv), "applied", new_callable=PropertyMock, return_value=True), \
            patch.object(type(climate.learned_opv), "value", new_callable=PropertyMock, return_value=58.0):
        entity = hass.data["number"].get_entity(_entity_id(hass))
        assert entity.native_min_value == 58

        with pytest.raises((HomeAssistantError, ValueError)):
            await _set(hass, 57)


@pytest.mark.parametrize(*parameters(**ENABLED))
async def test_no_change_during_the_calibration(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    with patch.object(type(climate.xtreme_calibration), "active", new_callable=PropertyMock, return_value=True):
        with pytest.raises(HomeAssistantError, match="calibration"):
            await _set(hass, 52)

    assert coordinator.maximum_setpoint == 60


def test_opentherm_gateway_reads_the_boiler_bound():
    coordinator = SatOpenThermMqttCoordinator.__new__(SatOpenThermMqttCoordinator)
    coordinator.data = {DATA_MAXIMUM_CONTROL_SETPOINT_UPPER_BOUND: "80"}

    assert coordinator.boiler_maximum_setpoint_bound == 80.0
    assert DATA_MAXIMUM_CONTROL_SETPOINT_UPPER_BOUND in coordinator.get_tracked_entities()
