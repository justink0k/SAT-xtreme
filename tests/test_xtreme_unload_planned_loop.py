"""A control loop planned 10 seconds ahead never runs after SAT is unloaded."""
from datetime import timedelta

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.sat_xtreme.climate import SatClimate
from tests.fake_coordinator import SatFakeCoordinator
from tests.loop_harness import CommandLog
from tests.xtreme_helpers import parameters


async def _heat(climate: SatClimate) -> None:
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    await climate.hass.async_block_till_done()


@pytest.mark.parametrize(*parameters())
async def test_a_planned_loop_does_not_run_after_the_unload(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _heat(climate)
    climate.schedule_control_heating_loop()
    assert climate._control_heating_loop_unsub is not None

    with CommandLog(coordinator) as log:
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        # What the unload itself sends (the hand-over) is fine; nothing may follow it
        log.clear()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=15))
        await hass.async_block_till_done()

    assert log.sent == []


@pytest.mark.parametrize(*parameters())
async def test_a_direct_run_cancels_the_planned_one(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _heat(climate)
    climate.schedule_control_heating_loop()

    with CommandLog(coordinator) as log:
        await climate.async_control_heating_loop()
        assert len(log.of("setpoint")) == 1

        # Before, the planned run was only forgotten, so it ran as well
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=15))
        await hass.async_block_till_done()

    assert len(log.of("setpoint")) == 1
