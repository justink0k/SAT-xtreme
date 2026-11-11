"""The OpenTherm Gateway repeats "online" every few minutes; only a real restart restores the overrides."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.coordinator import DeviceState
from custom_components.sat_xtreme.mqtt.opentherm import SatOpenThermMqttCoordinator


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
    await gateway.async_set_heater_state(DeviceState.ON)
    await gateway.async_set_control_setpoint(46.0)
    gateway.publish.reset_mock()


async def test_the_measured_heartbeat_sends_nothing(hass: HomeAssistant, gateway) -> None:
    await _set_overrides(gateway)
    gateway._availability_changed(_message("online", retain=True))

    # Measured on OTGW firmware 2.0.0-alpha.416: a live "online" every 5 minutes, then the uptime 300 seconds higher
    gateway._uptime_changed(_message("2406425"))
    gateway._availability_changed(_message("online"))
    gateway._uptime_changed(_message("2406725"))
    await hass.async_block_till_done()

    assert _sent(gateway) == []


async def test_a_lower_uptime_is_a_restart(hass: HomeAssistant, gateway) -> None:
    await _set_overrides(gateway)
    gateway._uptime_changed(_message("2406725"))

    # A restart without "offline" first: the new "online" alone is not enough, the uptime that starts again is
    gateway._availability_changed(_message("online"))
    gateway._uptime_changed(_message("12"))
    await hass.async_block_till_done()

    assert _sent(gateway) == ["PM=3", "PM=15", "PM=48", "CH=1", "CS=46.0", "PM=25"]


async def test_offline_then_online_is_a_restart(hass: HomeAssistant, gateway) -> None:
    await _set_overrides(gateway)
    gateway._uptime_changed(_message("2406725"))

    gateway._availability_changed(_message("offline"))
    gateway._availability_changed(_message("online"))
    await hass.async_block_till_done()

    assert "CS=46.0" in _sent(gateway)


async def test_a_restart_is_restored_once(hass: HomeAssistant, gateway) -> None:
    await _set_overrides(gateway)
    gateway._uptime_changed(_message("2406725"))

    gateway._availability_changed(_message("offline"))
    gateway._availability_changed(_message("online"))
    gateway._uptime_changed(_message("12"))
    await hass.async_block_till_done()

    assert _sent(gateway).count("CS=46.0") == 1


async def test_firmware_without_an_uptime_keeps_the_old_behaviour(hass: HomeAssistant, gateway) -> None:
    await _set_overrides(gateway)
    gateway._availability_changed(_message("online", retain=True))

    gateway._availability_changed(_message("online"))
    await hass.async_block_till_done()

    assert "CS=46.0" in _sent(gateway)


async def test_an_invalid_uptime_is_ignored(hass: HomeAssistant, gateway) -> None:
    await _set_overrides(gateway)
    gateway._uptime_changed(_message("2406725"))

    gateway._uptime_changed(_message("unknown"))
    gateway._uptime_changed(_message("2407025"))
    await hass.async_block_till_done()

    assert _sent(gateway) == []


async def test_the_uptime_topic_is_subscribed(hass: HomeAssistant, gateway) -> None:
    with patch("homeassistant.components.mqtt.async_wait_for_mqtt_client", new_callable=AsyncMock), \
            patch("homeassistant.components.mqtt.async_subscribe", new_callable=AsyncMock, return_value=MagicMock()) as subscribe:
        await gateway.async_added_to_hass()
        await gateway.async_will_remove_from_hass()

    assert "OTGW/value/otgw/otgw-firmware/uptime" in [call.args[1] for call in subscribe.call_args_list]
