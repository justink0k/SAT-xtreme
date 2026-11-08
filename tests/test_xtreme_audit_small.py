"""The small fixes of the code audit of 2026-11-08 (findings L1 to L15)."""
import asyncio
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme import async_migrate_entry
from custom_components.sat_xtreme.binary_sensor import SatControlSetpointSynchroSensor
from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.helpers import convert_time_str_to_seconds
from custom_components.sat_xtreme.minimum_setpoint import MinimumSetpoint
from custom_components.sat_xtreme.overshoot_protection import OvershootProtection
from custom_components.sat_xtreme.xtreme.cycles import create_cycle_tracker
from custom_components.sat_xtreme.xtreme.opv import LearnedOpv
from custom_components.sat_xtreme.xtreme.opv_model import Curve
from tests.fake_coordinator import SatFakeCoordinator
from tests.loop_harness import CommandLog, run_loops
from tests.xtreme_helpers import parameters

sys.modules.setdefault("homeassistant.components.esphome", types.ModuleType("homeassistant.components.esphome"))
from custom_components.sat_xtreme.esphome import SatEspHomeCoordinator  # noqa: E402


# L1

@pytest.mark.parametrize(*parameters())
async def test_reset_integral_comes_from_the_services_module(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    climate.pid._integral = 1.5

    await hass.services.async_call(DOMAIN, SERVICE_RESET_INTEGRAL, {"entity_id": climate.entity_id}, blocking=True)

    assert climate.pid._integral == 0.0
    assert not hasattr(climate, "_register_services")


# L3

@pytest.mark.parametrize(*parameters())
async def test_the_synchro_sensor_compares_with_the_limited_setpoint(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    sensor = SatControlSetpointSynchroSensor(coordinator, entry, climate)
    climate._setpoint = coordinator.maximum_setpoint + 10
    coordinator._setpoint = coordinator.maximum_setpoint

    assert not sensor.is_on
    assert sensor._last_mismatch is None


# L4

async def test_the_minimum_setpoint_has_a_store_per_installation(hass: HomeAssistant, hass_storage: dict) -> None:
    hass_storage["minimum_setpoint"] = {"version": 1, "key": "minimum_setpoint", "data": {"base_return_temperature": 41.0}}
    hass_storage["minimum_setpoint_second"] = {"version": 1, "key": "minimum_setpoint_second", "data": {"base_return_temperature": 35.0}}

    first, second = MinimumSetpoint(0.2, 46), MinimumSetpoint(0.2, 46)
    await first.async_initialize(hass, "first")
    await second.async_initialize(hass, "second")

    # No store of its own yet: the value of the store that was shared
    assert first._base_return_temperature.value == 41.0
    assert second._base_return_temperature.value == 35.0
    assert first._store.key == "minimum_setpoint_first"


# L5 and L6

def test_an_unknown_heating_system_gives_the_intended_error() -> None:
    coordinator = SimpleNamespace(maximum_setpoint_value=60.0, maximum_setpoint=60.0)

    with pytest.raises(ValueError, match="Invalid heating system"):
        OvershootProtection(coordinator, "unknown")


def test_an_invalid_time_gives_the_intended_error() -> None:
    assert convert_time_str_to_seconds("00:01:30") == 90

    with pytest.raises(ValueError, match="Invalid time format"):
        convert_time_str_to_seconds("nonsense")


# L7

async def test_a_missing_esphome_entity_skips_the_command_and_warns_once(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    coordinator = object.__new__(SatEspHomeCoordinator)
    coordinator.hass = hass
    coordinator._simulation = False
    coordinator._missing_commands = set()
    coordinator._get_entity_id = lambda _domain, _key: None

    await coordinator._send_command_value("t_set", 40.0)
    await coordinator._send_command_value("t_set", 41.0)
    await coordinator._send_command_state("ch_enable", True)

    warnings = [record for record in caplog.records if "SAT skips this command" in record.getMessage()]
    assert len(warnings) == 2


# L8

@pytest.mark.parametrize(*parameters())
async def test_the_modulation_limit_is_sent_once_when_the_boiler_does_not_report_it(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    coordinator.config.supports_relative_modulation_management = True
    assert coordinator.maximum_relative_modulation_value is None
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)

    with CommandLog(coordinator) as log:
        await run_loops(climate, 3)
        assert len(log.of("modulation")) == 1

        # SAT cleared the limit when it turned off, so it is sent again
        await climate.async_set_hvac_mode(HVACMode.OFF)
        await climate.async_set_hvac_mode(HVACMode.HEAT)
        await run_loops(climate, 2)

    assert len(log.of("modulation")) == 2


# L9

@pytest.mark.parametrize(*parameters())
async def test_closing_the_window_cancels_the_only_wait(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    climate._window_minimum_open_time = 3600
    climate._target_temperature = 21.0

    def event(state: str):
        return SimpleNamespace(data={"new_state": SimpleNamespace(state=state, entity_id="binary_sensor.window")})

    with patch.object(SatClimate, "async_set_preset_mode", new_callable=AsyncMock) as preset:
        first = asyncio.ensure_future(climate._async_window_sensor_changed(event("on")))
        await asyncio.sleep(0)
        waiting = climate._window_sensor_handle
        climate._target_temperature = 15.0

        # A second report while the window is open starts no second wait and keeps the old target
        await climate._async_window_sensor_changed(event("on"))
        assert climate._window_sensor_handle is waiting
        assert climate._pre_activity_temperature == 21.0

        await climate._async_window_sensor_changed(event("off"))
        await first

    preset.assert_not_called()
    assert climate._window_sensor_handle is None


# L10

@pytest.mark.parametrize(*parameters())
async def test_a_burn_during_an_offline_gateway_is_dropped(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    tracker = create_cycle_tracker(coordinator, climate, entry)

    with patch.object(SatFakeCoordinator, "online", new_callable=PropertyMock) as online, \
            patch.object(SatFakeCoordinator, "flame_active", new_callable=PropertyMock) as flame:
        online.return_value, flame.return_value = True, False
        tracker._async_coordinator_updated()

        flame.return_value = True
        tracker._async_coordinator_updated()
        assert tracker._current is not None

        online.return_value = False
        tracker._async_coordinator_updated()
        assert tracker._current is None

        # Back online with the flame off: no cycle with the time offline in it
        online.return_value, flame.return_value = True, False
        tracker._async_coordinator_updated()

    assert tracker.history == []


# L11

def test_a_test_step_does_not_lift_the_opv_to_the_lowest_learned_opv() -> None:
    opv = LearnedOpv(mode="learn", configured_value=35.0, maximum_setpoint=60.0, storage_key="test", minimum=40.0)

    opv.model.test_offset = 1.0
    assert opv.with_test(35.0) == 36.0

    # It can't go below what is configured
    opv.model.test_offset = -1.0
    assert opv.with_test(35.0) == 35.0

    # A value above the lowest learned OPV still stops at it
    assert opv.with_test(40.5) == 40.0


# L12

def test_the_burn_curve_handles_a_gap_in_the_levels() -> None:
    curve = object.__new__(Curve)
    curve.levels = {40: 100.0, 41: 110.0, 43: 150.0}
    curve._k = None
    curve._rate = None
    curve.balance = None

    assert curve.seconds_to(40.5) == 105.0
    assert curve.seconds_to(42.0) == 130.0
    assert curve.seconds_to(43.0) == 150.0


# L15

async def test_an_old_window_sensor_in_the_data_migrates(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, version=3, data={"window_sensor": "binary_sensor.window"}, options={})
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.data["window_sensors"] == ["binary_sensor.window"]
