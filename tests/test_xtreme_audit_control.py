"""The wizard calibration resets the boiler, the hvac cascade goes on, and the control loop has a lock (audit findings H3, M7, M8)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.coordinator import DeviceState
from custom_components.sat_xtreme.overshoot_protection import OvershootProtection
from tests.fake_coordinator import SatFakeCoordinator
from tests.loop_harness import CommandLog
from tests.xtreme_helpers import parameters


# H3: the wizard calibration

def _protection(modulation: float = 0.0) -> tuple[OvershootProtection, MagicMock]:
    coordinator = MagicMock(relative_modulation_value=modulation, maximum_setpoint_value=60.0, maximum_setpoint=60.0)
    coordinator.async_set_heater_state = AsyncMock()
    coordinator.async_set_control_setpoint = AsyncMock()
    return OvershootProtection(coordinator, HEATING_SYSTEM_RADIATORS), coordinator


def _assert_reset(coordinator: MagicMock) -> None:
    coordinator.async_set_heater_state.assert_awaited_once_with(DeviceState.OFF)
    coordinator.async_set_control_setpoint.assert_awaited_once_with(MINIMUM_SETPOINT)


async def test_the_boiler_is_reset_after_a_successful_calibration() -> None:
    protection, coordinator = _protection()
    protection._stable_temperature = 47.0

    with patch.object(OvershootProtection, "_wait_for_flame", new_callable=AsyncMock), patch.object(OvershootProtection, "_wait_for_stable_temperature", new_callable=AsyncMock):
        assert await protection.calculate() == 47.0

    _assert_reset(coordinator)


@pytest.mark.parametrize("error", [asyncio.TimeoutError, asyncio.CancelledError, ValueError])
async def test_the_boiler_is_reset_after_a_failed_calibration(error: type[BaseException]) -> None:
    protection, coordinator = _protection()

    with patch.object(OvershootProtection, "_wait_for_flame", new=AsyncMock(side_effect=error)), pytest.raises(error):
        await protection.calculate()

    _assert_reset(coordinator)


async def test_a_failing_reset_does_not_hide_the_outcome() -> None:
    protection, coordinator = _protection()
    coordinator.async_set_heater_state.side_effect = ConnectionError
    protection._stable_temperature = 47.0

    with patch.object(OvershootProtection, "_wait_for_flame", new_callable=AsyncMock), patch.object(OvershootProtection, "_wait_for_stable_temperature", new_callable=AsyncMock):
        assert await protection.calculate() == 47.0


# M7: the hvac cascade

@pytest.mark.parametrize(*parameters())
async def test_a_climate_without_the_mode_does_not_stop_the_others(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    calls = async_mock_service(hass, "climate", "set_hvac_mode")
    climate._radiators = ["climate.no_modes", "climate.only_off", "climate.missing", "climate.good"]
    hass.states.async_set("climate.no_modes", "off")
    hass.states.async_set("climate.only_off", "off", {"hvac_modes": ["off"]})
    hass.states.async_set("climate.good", "off", {"hvac_modes": ["off", "heat"]})

    with patch.object(SatClimate, "schedule_control_heating_loop") as schedule:
        await climate.async_set_hvac_mode(HVACMode.HEAT)

    assert [call.data["entity_id"] for call in calls] == ["climate.good"]
    assert hass.states.get(climate.entity_id).state == HVACMode.HEAT
    schedule.assert_called()


# M8: force and the lock

@pytest.mark.parametrize(*parameters())
async def test_force_runs_when_nothing_is_scheduled(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    climate._control_heating_loop_unsub = None

    with patch.object(SatClimate, "async_control_heating_loop", new_callable=AsyncMock) as loop:
        climate.schedule_control_heating_loop(force=True)
        await hass.async_block_till_done()

    loop.assert_awaited_once()
    assert climate._control_heating_loop_unsub is None


@pytest.mark.parametrize(*parameters())
async def test_two_loops_do_not_run_at_the_same_time(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    running = highest = 0

    async def slow_loop() -> None:
        nonlocal running, highest
        running += 1
        highest = max(highest, running)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        running -= 1

    with patch.object(SatClimate, "_async_control_heating_loop", new=lambda _self: slow_loop()):
        await asyncio.gather(climate.async_control_heating_loop(), climate.async_control_heating_loop())

    assert highest == 1


@pytest.mark.parametrize(*parameters())
async def test_nothing_is_sent_after_turning_off_during_a_loop(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    await hass.async_block_till_done()
    await coordinator.async_set_heater_state(DeviceState.ON)

    gate = asyncio.Event()
    entered = asyncio.Event()
    original = coordinator.async_set_control_setpoint

    async def slow_setpoint(value: float) -> None:
        # A command to the gateway takes a second
        entered.set()
        await gate.wait()
        await original(value)

    with CommandLog(coordinator) as log, patch.object(coordinator, "async_set_control_setpoint", slow_setpoint):
        loop = hass.async_create_task(climate.async_control_heating_loop())
        await entered.wait()

        turning_off = hass.async_create_task(climate.async_set_hvac_mode(HVACMode.OFF))
        await asyncio.sleep(0)

        # It waits for the running loop, and is not stuck
        assert not turning_off.done()
        gate.set()
        await asyncio.wait_for(asyncio.gather(loop, turning_off), timeout=5)

    # The last command is heater off, nothing of the loop comes after it
    heater = [value for kind, value in log.sent if kind == "heater"]
    assert heater[-1] == DeviceState.OFF
    assert log.sent[-1][0] in ("heater", "release_modulation")
