"""The OpenTherm Gateway going offline and restarting, idea from bellini666/SAT (step 1B)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.coordinator import DeviceState
from custom_components.sat_xtreme.mqtt.opentherm import SatOpenThermMqttCoordinator
from custom_components.sat_xtreme.xtreme.binary_sensor import SatGatewayOnlineBinarySensor
from tests.fake_coordinator import SatFakeCoordinator
from tests.xtreme_helpers import parameters


def _message(payload: str, retain: bool = False) -> SimpleNamespace:
    return SimpleNamespace(payload=payload, retain=retain)


@pytest.fixture
def gateway(hass: HomeAssistant):
    coordinator = SatOpenThermMqttCoordinator(hass, device_id="otgw", config_data={CONF_MQTT_TOPIC: "OTGW"})

    with patch.object(SatOpenThermMqttCoordinator, "_publish_command", new_callable=AsyncMock) as publish:
        coordinator.publish = publish
        yield coordinator


def _sent(gateway) -> list[str]:
    return [call.args[0] for call in gateway.publish.call_args_list]


async def _set_overrides(gateway) -> None:
    await gateway.async_set_control_max_setpoint(65)
    await gateway.async_set_control_hot_water_setpoint(55)
    await gateway.async_set_hot_water_keep_warm(False)
    await gateway.async_set_control_max_relative_modulation(40)
    await gateway.async_set_control_thermostat_setpoint(20.5)
    await gateway.async_set_heater_state(DeviceState.ON)
    await gateway.async_set_control_setpoint(42.0)
    gateway.publish.reset_mock()


async def test_a_gateway_without_a_will_message_counts_as_online(gateway) -> None:
    assert gateway.supports_online_status
    assert gateway.online


async def test_the_will_message_sets_the_online_state(hass: HomeAssistant, gateway) -> None:
    gateway._availability_changed(_message("offline", retain=True))
    assert not gateway.online

    gateway._availability_changed(_message(b"online", retain=True))
    await hass.async_block_till_done()
    assert gateway.online

    # The broker replays the last state: that is no restart, so nothing is sent
    assert _sent(gateway) == []


async def test_a_restart_restores_every_override(hass: HomeAssistant, gateway) -> None:
    await _set_overrides(gateway)

    gateway._availability_changed(_message("offline"))
    gateway._availability_changed(_message("online"))
    await hass.async_block_till_done()

    assert _sent(gateway) == ["PM=3", "PM=15", "PM=48", "SH=65", "SW=55", "HW=0", "MM=40", "TC=20.5", "CH=1", "CS=42.0", "PM=25"]


async def test_a_clean_restart_without_offline_also_restores(hass: HomeAssistant, gateway) -> None:
    await _set_overrides(gateway)
    gateway._availability_changed(_message("online", retain=True))

    # A planned restart disconnects cleanly, so no "offline" comes before the new "online"
    gateway._availability_changed(_message("online"))
    await hass.async_block_till_done()

    assert "CS=42.0" in _sent(gateway)


async def test_a_restart_repeats_the_release(hass: HomeAssistant, gateway) -> None:
    await gateway.async_set_control_setpoint(42.0)
    await gateway.async_release_control_setpoint()
    gateway.publish.reset_mock()

    gateway._availability_changed(_message("online"))
    await hass.async_block_till_done()

    assert _sent(gateway) == ["PM=3", "PM=15", "PM=48", "CS=0"]


async def test_only_what_sat_set_is_sent_again(hass: HomeAssistant, gateway) -> None:
    gateway._availability_changed(_message("online"))
    await hass.async_block_till_done()

    # No hot water, thermostat or setpoint commands that SAT never sent
    assert _sent(gateway) == ["PM=3", "PM=15", "PM=48"]


async def test_the_will_topic_is_subscribed_and_released(hass: HomeAssistant, gateway) -> None:
    unsubscribe = MagicMock()

    with patch("homeassistant.components.mqtt.async_wait_for_mqtt_client", new_callable=AsyncMock), \
            patch("homeassistant.components.mqtt.async_subscribe", new_callable=AsyncMock, return_value=unsubscribe) as subscribe:
        await gateway.async_added_to_hass()
        await gateway.async_will_remove_from_hass()

    topics = [call.args[1] for call in subscribe.call_args_list]
    assert "OTGW/value/otgw" in topics
    unsubscribe.assert_called()


async def test_the_binary_sensor_follows_the_gateway(hass: HomeAssistant, gateway) -> None:
    sensor = SatGatewayOnlineBinarySensor(gateway, MockConfigEntry(domain=DOMAIN, data={CONF_NAME: "Test"}))
    assert sensor.is_on

    gateway._availability_changed(_message("offline"))
    assert not sensor.is_on


@pytest.mark.parametrize(*parameters())
async def test_an_offline_gateway_pauses_the_control_loop(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)

    with patch.object(SatFakeCoordinator, "online", new_callable=PropertyMock, return_value=False), \
            patch.object(SatFakeCoordinator, "async_control_heating_loop", new_callable=AsyncMock) as loop:
        await climate.async_control_heating_loop()

    loop.assert_not_called()


@pytest.mark.parametrize(*parameters())
async def test_an_online_gateway_keeps_the_control_loop(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)

    with patch.object(SatFakeCoordinator, "async_control_heating_loop", new_callable=AsyncMock) as loop:
        await climate.async_control_heating_loop()

    loop.assert_called_once()
