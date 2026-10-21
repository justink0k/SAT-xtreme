"""Tests for the Xtreme profile, step 2: do not manage the modulation limit."""
from unittest.mock import PropertyMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.sat.sensor as sat_sensor
from custom_components.sat.climate import SatClimate
from custom_components.sat.const import *
from custom_components.sat.coordinator import DeviceState
from custom_components.sat.fake import SatFakeCoordinator
from tests.xtreme_helpers import parameters


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_IGNORE_MODULATION_LIMIT: True}))
async def test_modulation_limit_is_not_managed(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    coordinator.config.supports_relative_modulation_management = True

    assert not coordinator.supports_relative_modulation_management
    assert coordinator.supports_relative_modulation


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_IGNORE_MODULATION_LIMIT: False}))
async def test_modulation_limit_without_profile_is_upstream(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    coordinator.config.supports_relative_modulation_management = True

    assert coordinator.supports_relative_modulation_management


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_IGNORE_MODULATION_LIMIT: True}))
async def test_neutral_modulation_limit_is_sent_once(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    with patch.object(SatFakeCoordinator, "async_set_control_max_relative_modulation", wraps=coordinator.async_set_control_max_relative_modulation) as spy:
        await climate._async_control_relative_modulation()
        await climate._async_control_relative_modulation()
        await climate._async_control_relative_modulation()

    spy.assert_called_once_with(MAXIMUM_RELATIVE_MODULATION)


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_IGNORE_MODULATION_LIMIT: True}))
async def test_power_falls_back_to_rated_power(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await coordinator.async_set_heater_state(DeviceState.ON)

    with patch.object(SatFakeCoordinator, "relative_modulation_value", new_callable=PropertyMock, return_value=50.0):
        assert coordinator.effective_boiler_capacity == 19.5
        assert coordinator.effective_minimum_relative_modulation_value == pytest.approx(20.0)
        assert coordinator.minimum_boiler_capacity == pytest.approx(3.9)
        assert coordinator.boiler_power == pytest.approx(11.7)

        await coordinator.async_set_heater_state(DeviceState.OFF)
        assert coordinator.boiler_power == 0


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_IGNORE_MODULATION_LIMIT: True}))
async def test_reported_capacity_wins_over_rated_power(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    with patch.object(SatFakeCoordinator, "boiler_capacity", new_callable=PropertyMock, return_value=24.0), \
            patch.object(SatFakeCoordinator, "minimum_relative_modulation_value", new_callable=PropertyMock, return_value=10.0):
        assert coordinator.effective_boiler_capacity == 24.0
        assert coordinator.effective_minimum_relative_modulation_value == 10.0


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_IGNORE_MODULATION_LIMIT: False}))
async def test_power_without_profile_is_upstream(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    with patch.object(SatFakeCoordinator, "relative_modulation_value", new_callable=PropertyMock, return_value=50.0):
        assert coordinator.effective_boiler_capacity is None
        assert coordinator.boiler_power is None


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_IGNORE_MODULATION_LIMIT: True}))
async def test_power_sensor_is_created(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    entities = []
    await sat_sensor.async_setup_entry(hass, entry, lambda new_entities: entities.extend(new_entities))

    assert any(isinstance(entity, sat_sensor.SatCurrentPowerSensor) for entity in entities)
