"""Tests for the hot water keep-warm switch (4.2.1-xtreme.13)."""
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.sat_xtreme.xtreme.switch as xtreme_switch
from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from tests.fake_coordinator import SatFakeCoordinator
from custom_components.sat_xtreme.mqtt.opentherm import SatOpenThermMqttCoordinator
from custom_components.sat_xtreme.xtreme.switch import SatHotWaterKeepWarmSwitch
from tests.xtreme_helpers import parameters


async def _setup(hass, entry):
    entities = []
    await xtreme_switch.async_setup_entry(hass, entry, lambda new: entities.extend(new))
    return entities


@pytest.fixture
def keep_warm():
    with patch.object(SatFakeCoordinator, "supports_hot_water_keep_warm_control", new_callable=PropertyMock, return_value=True), \
            patch.object(SatFakeCoordinator, "async_set_hot_water_keep_warm", new_callable=AsyncMock) as command:
        yield command


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_HOT_WATER_SWITCH: True}))
async def test_switch_is_created_with_the_option(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, keep_warm) -> None:
    entities = await _setup(hass, entry)

    assert len(entities) == 1
    assert entities[0].name.startswith("Xtreme fork:")


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_HOT_WATER_SWITCH: False}))
async def test_no_switch_and_no_commands_without_the_option(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, keep_warm) -> None:
    assert await _setup(hass, entry) == []
    keep_warm.assert_not_called()


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_HOT_WATER_SWITCH: True}))
async def test_no_switch_on_devices_without_control(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    assert await _setup(hass, entry) == []


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_HOT_WATER_SWITCH: True}))
async def test_switch_sends_off_and_on(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, keep_warm) -> None:
    switch = SatHotWaterKeepWarmSwitch(coordinator, entry, climate, xtreme_switch._store(hass, entry))
    switch.hass = hass
    switch.async_write_ha_state = lambda: None

    await switch.async_turn_off()
    assert not switch.is_on
    keep_warm.assert_called_with(False)
    assert (await xtreme_switch._store(hass, entry).async_load())["keep_warm_off"] is True

    await switch.async_turn_on()
    assert switch.is_on
    keep_warm.assert_called_with(True)
    assert (await xtreme_switch._store(hass, entry).async_load())["keep_warm_off"] is False


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_HOT_WATER_SWITCH: False}))
async def test_turning_the_option_off_gives_keep_warm_back(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, keep_warm) -> None:
    await xtreme_switch._store(hass, entry).async_save({"keep_warm_off": True})

    await _setup(hass, entry)
    keep_warm.assert_called_once_with(True)

    # Only once: afterwards nothing is sent anymore
    keep_warm.reset_mock()
    await _setup(hass, entry)
    keep_warm.assert_not_called()


async def test_opentherm_gateway_commands(hass: HomeAssistant) -> None:
    coordinator = SatOpenThermMqttCoordinator(hass, device_id="otgw", config_data={CONF_MQTT_TOPIC: "OTGW"})

    with patch.object(SatOpenThermMqttCoordinator, "_publish_command", new_callable=AsyncMock) as publish:
        await coordinator.async_set_hot_water_keep_warm(False)
        await coordinator.async_set_hot_water_keep_warm(True)

    assert coordinator.supports_hot_water_keep_warm_control
    assert [call.args[0] for call in publish.call_args_list] == ["HW=0", "HW=A"]
