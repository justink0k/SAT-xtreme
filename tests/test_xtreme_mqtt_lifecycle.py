"""Subscriptions end at the unload, and values from storage don't count as live (audit findings M3 and M4)."""
from itertools import product
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.boiler import BoilerState
from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.minimum_setpoint import MinimumSetpoint
from custom_components.sat_xtreme.mqtt.ems import SatEmsMqttCoordinator
from custom_components.sat_xtreme.mqtt.opentherm import SatOpenThermMqttCoordinator
from custom_components.sat_xtreme.overshoot_protection import OvershootProtection
from custom_components.sat_xtreme.state import State, update_state
from custom_components.sat_xtreme.xtreme.cycles import create_cycle_tracker
from tests.fake_coordinator import SatFakeCoordinator
from tests.loop_harness import CommandLog, run_loops
from tests.xtreme_helpers import parameters

STORED = {
    "flame": "ON", "centralheating": "ON", "domestichotwater": "ON", "TSet": "50.0", "Tboiler": "60.0", "Tret": "40.0",
    "RelModLevel": "30.0", "MaxRelModLevelSetting": "100.0",
    "TdhwSet": "55.0", "MaxCapacityMinModLevel_hb_u8": "30", "MaxCapacityMinModLevel_lb_u8": "20", "slave_memberid_code": "173",
}


def _otgw(hass: HomeAssistant) -> SatOpenThermMqttCoordinator:
    return SatOpenThermMqttCoordinator(hass, device_id="otgw", config_data={CONF_MQTT_TOPIC: "OTGW"})


async def _restored(coordinator, stored: dict):
    coordinator._store.async_load = AsyncMock(return_value=stored)
    await coordinator.async_setup()
    return coordinator


# M3: the subscriptions end at the unload

async def test_all_subscriptions_end_at_the_unload(hass: HomeAssistant) -> None:
    coordinator = _otgw(hass)
    subscriptions = []

    def subscribe(*_args, **_kwargs):
        subscriptions.append(MagicMock())
        return subscriptions[-1]

    with patch("homeassistant.components.mqtt.async_wait_for_mqtt_client", new_callable=AsyncMock), \
            patch("homeassistant.components.mqtt.async_subscribe", new=AsyncMock(side_effect=subscribe)), \
            patch.object(SatOpenThermMqttCoordinator, "_publish_command", new_callable=AsyncMock):
        await coordinator.async_added_to_hass()
        assert len(subscriptions) == len(coordinator.get_tracked_entities()) + 1

        await coordinator.async_will_remove_from_hass()

    for unsubscribe in subscriptions:
        unsubscribe.assert_called_once()


async def test_a_planned_notification_is_cancelled_at_the_unload(hass: HomeAssistant) -> None:
    coordinator = _otgw(hass)
    coordinator.async_set_updated_data({"flame": "ON"})
    assert coordinator._listeners_unsub is not None

    await coordinator.async_will_remove_from_hass()

    assert coordinator._listeners_unsub is None


# M4: values from storage are not live

async def test_restored_values_are_not_live(hass: HomeAssistant) -> None:
    coordinator = await _restored(_otgw(hass), STORED)

    assert not coordinator.flame_known
    assert not coordinator.flame_active
    assert not coordinator.device_active
    assert not coordinator.hot_water_active
    assert coordinator.setpoint is None
    assert coordinator.boiler_temperature is None
    assert coordinator.return_temperature is None
    assert coordinator.relative_modulation_value is None
    assert coordinator.maximum_relative_modulation_value is None


async def test_fixed_boiler_values_stay_from_storage(hass: HomeAssistant) -> None:
    coordinator = await _restored(_otgw(hass), STORED)

    assert coordinator.boiler_capacity == 30
    assert coordinator.minimum_relative_modulation_value == 20
    assert coordinator.member_id == 173
    assert coordinator.hot_water_setpoint == 55


async def test_a_live_message_makes_a_value_live_also_when_it_is_the_same(hass: HomeAssistant) -> None:
    coordinator = await _restored(_otgw(hass), STORED)
    coordinator._listeners_unsub()
    coordinator._listeners_unsub = None
    coordinator.data.reset_dirty()

    coordinator._process_message_payload("flame", "ON")

    assert coordinator.flame_known
    assert coordinator.flame_active
    # The value did not change, but the listeners must see that it is live now
    assert coordinator._listeners_unsub is not None
    # The other values wait for their own message
    assert coordinator.boiler_temperature is None

    coordinator._listeners_unsub()


async def test_ems_values_become_live_with_their_message(hass: HomeAssistant) -> None:
    coordinator = await _restored(
        SatEmsMqttCoordinator(hass, device_id="ems", config_data={CONF_MQTT_TOPIC: "ems-esp"}),
        {"burngas": "on", "curflowtemp": "60", "nompower": "30"},
    )

    assert not coordinator.flame_active
    assert coordinator.boiler_temperature is None
    assert coordinator.boiler_capacity == 30

    coordinator._process_message_payload("boiler_data", '{"burngas": "on", "curflowtemp": 61}')

    assert coordinator.flame_active
    assert coordinator.boiler_temperature == 61
    coordinator._listeners_unsub()


@pytest.mark.parametrize(*parameters())
async def test_a_running_burn_after_a_start_is_not_a_new_cycle(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    tracker = create_cycle_tracker(coordinator, climate, entry)

    with patch.object(SatFakeCoordinator, "flame_known", new_callable=PropertyMock) as known, \
            patch.object(SatFakeCoordinator, "flame_active", new_callable=PropertyMock) as flame:
        # After a start-up: the stored flame is not live, so it reads as off
        known.return_value, flame.return_value = False, False
        tracker._async_coordinator_updated()

        # The first live message: the flame is already burning
        known.return_value, flame.return_value = True, True
        tracker._async_coordinator_updated()
        assert tracker._current is None

        flame.return_value = False
        tracker._async_coordinator_updated()

        flame.return_value = True
        tracker._async_coordinator_updated()

    # Only the burn that really started is followed
    assert tracker.history == []
    assert tracker._current is not None


# The control keeps working while values have not arrived yet

MISSING = list(product([None, 60.0], [None, 50.0], [None, 40.0], [None, 30.0]))


@pytest.mark.parametrize("flow, setpoint, return_temperature, modulation", MISSING)
@pytest.mark.parametrize(*parameters(force_pwm=False, **{
    CONF_XTREME_LEARNED_OPV: "apply", CONF_XTREME_OPV_SEARCH: True, CONF_XTREME_BOILER_TIMING: True, CONF_XTREME_CYCLE_TRACKING: True, CONF_XTREME_SETPOINT_CHAIN: True,
}))
async def test_the_loop_runs_with_values_missing_while_the_flame_burns(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, flow, setpoint, return_temperature, modulation) -> None:
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)

    with patch.object(SatFakeCoordinator, "flame_active", new_callable=PropertyMock, return_value=True), \
            patch.object(SatFakeCoordinator, "device_active", new_callable=PropertyMock, return_value=True), \
            patch.object(SatFakeCoordinator, "boiler_temperature", new_callable=PropertyMock, return_value=flow), \
            patch.object(SatFakeCoordinator, "setpoint", new_callable=PropertyMock, return_value=setpoint), \
            patch.object(SatFakeCoordinator, "return_temperature", new_callable=PropertyMock, return_value=return_temperature), \
            patch.object(SatFakeCoordinator, "relative_modulation_value", new_callable=PropertyMock, return_value=modulation), \
            CommandLog(coordinator) as log:
        await run_loops(climate, 3)
        climate.extra_state_attributes

    assert len(log.of("setpoint")) == 3


def test_a_missing_value_keeps_the_previous_state():
    previous = State(40.0)

    assert update_state(previous=previous, new_value=None) is previous


def test_warming_up_waits_for_the_return_temperature():
    minimum_setpoint = MinimumSetpoint(adjustment_factor=0.2, configured_minimum_setpoint=46)
    minimum_setpoint._base_return_temperature = State(40.0)
    boiler = BoilerState(
        is_active=True, is_inactive=False, status=BoilerStatus.HEATING_UP, flame_active=True, hot_water_active=False,
        setpoint=50.0, flow_temperature=60.0, return_temperature=None, relative_modulation_level=None,
    )

    minimum_setpoint.warming_up(boiler)
    minimum_setpoint.calculate(boiler, PWMStatus.IDLE)

    assert minimum_setpoint._base_return_temperature.value == 40.0


def test_the_wizard_calibration_handles_an_unknown_modulation():
    coordinator = MagicMock(relative_modulation_value=None, maximum_setpoint_value=60.0, maximum_setpoint=60.0)
    protection = OvershootProtection(coordinator, HEATING_SYSTEM_RADIATORS)
    protection._stable_temperature = 47.0

    assert protection._calculate_overshoot_value() == 47.0
