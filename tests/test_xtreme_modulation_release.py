"""The modulation limit of SAT has no expiry on the gateway, so it is cleared when SAT stops controlling."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.coordinator import DeviceState
from custom_components.sat_xtreme.mqtt.opentherm import SatOpenThermMqttCoordinator
from tests.fake_coordinator import SatFakeCoordinator
from tests.loop_harness import CommandLog
from tests.xtreme_helpers import parameters


@pytest.fixture
def gateway(hass: HomeAssistant):
    coordinator = SatOpenThermMqttCoordinator(hass, device_id="otgw", config_data={CONF_MQTT_TOPIC: "OTGW"})

    with patch.object(SatOpenThermMqttCoordinator, "_publish_command", new_callable=AsyncMock) as publish:
        coordinator.publish = publish
        yield coordinator


def _sent(gateway) -> list[str]:
    return [call.args[0] for call in gateway.publish.call_args_list]


@pytest.mark.parametrize(*parameters())
async def test_turning_off_clears_the_limit_without_the_option(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await climate.async_set_hvac_mode(HVACMode.HEAT)

    with CommandLog(coordinator) as log:
        await climate.async_set_hvac_mode(HVACMode.OFF)

    assert log.sent.count(("release_modulation", None)) == 1
    assert log.of("release") == []


@pytest.mark.parametrize(*parameters())
async def test_stopping_and_unloading_clear_the_limit(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    with CommandLog(coordinator) as log:
        await climate._async_handover_on_shutdown()
        await climate.async_will_remove_from_hass()

    assert len(log.of("release_modulation")) == 2


@pytest.mark.parametrize("mode, cleared", [(HVACMode.OFF, 1), (HVACMode.HEAT, 0)])
@pytest.mark.parametrize(*parameters())
async def test_only_starting_turned_off_clears_the_limit(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, mode: HVACMode, cleared: int) -> None:
    climate._hvac_mode = mode

    with CommandLog(coordinator) as log:
        await climate._async_handover_on_startup()

    assert len(log.of("release_modulation")) == cleared


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_HANDOVER_ON_OFF: True}))
async def test_the_hand_over_clears_the_limit_once(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    with patch.object(SatFakeCoordinator, "supports_setpoint_release", True), CommandLog(coordinator) as log:
        await climate._async_handover_on_shutdown()

    assert len(log.of("release")) == 1
    assert len(log.of("release_modulation")) == 1


async def test_the_gateway_clears_the_limit_with_mm_t(gateway) -> None:
    await gateway.async_release_modulation_limit()

    assert _sent(gateway) == ["MM=T"]


async def test_a_gateway_restart_sends_no_setpoint_while_sat_is_off(hass: HomeAssistant, gateway) -> None:
    await gateway.async_set_control_max_setpoint(65)
    await gateway.async_set_heater_state(DeviceState.ON)
    await gateway.async_set_control_setpoint(46.0)
    await gateway.async_release_modulation_limit()
    gateway.forget_control_overrides()
    gateway.publish.reset_mock()

    gateway._availability_changed(SimpleNamespace(payload="online", retain=False))
    await hass.async_block_till_done()

    # Before, CS=46 and CH=1 came back, and the boiler could heat for the minute until the gateway drops the setpoint
    assert _sent(gateway) == ["PM=3", "PM=15", "PM=48", "SH=65", "MM=T"]


async def test_other_gateways_send_nothing(hass: HomeAssistant) -> None:
    coordinator = SatFakeCoordinator(hass, {CONF_MINIMUM_SETPOINT: 46})

    with CommandLog(coordinator) as log:
        await coordinator.async_release_modulation_limit()
        coordinator.forget_control_overrides()

    assert log.of("modulation") == []
