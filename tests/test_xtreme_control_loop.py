"""What a whole control loop sends, recorded with the loop harness."""
from datetime import timedelta
from unittest.mock import PropertyMock, patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.coordinator import DeviceState
from tests.fake_coordinator import SatFakeCoordinator
from tests.loop_harness import CommandLog, run_loops
from tests.xtreme_helpers import parameters

INSIDE = "sensor.test_inside_sensor"


async def _heat(climate: SatClimate) -> None:
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)


@pytest.mark.parametrize(*parameters())
async def test_heating_sends_a_setpoint_every_loop(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _heat(climate)

    with CommandLog(coordinator) as log:
        await run_loops(climate, 3)

    assert len(log.of("setpoint")) == 3


@pytest.mark.parametrize(*parameters())
async def test_turning_off_sends_heater_off_once_and_then_nothing(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _heat(climate)
    await coordinator.async_set_heater_state(DeviceState.ON)

    with CommandLog(coordinator) as log:
        await climate.async_set_hvac_mode(HVACMode.OFF)
        assert log.of("heater") == [DeviceState.OFF]

        log.clear()
        await run_loops(climate, 3)

    assert log.sent == []


@pytest.mark.parametrize(*parameters(force_pwm=False))
async def test_the_setpoint_never_exceeds_the_maximum(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _heat(climate)

    with patch.object(SatClimate, "requested_setpoint", new_callable=PropertyMock, return_value=95.0), CommandLog(coordinator) as log:
        await run_loops(climate, 5)

    assert log.of("setpoint")
    assert max(log.of("setpoint")) <= coordinator.maximum_setpoint


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_STALE_SENSORS: True}))
async def test_the_safe_mode_keeps_sending_a_setpoint(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _heat(climate)
    old = (dt_util.utcnow() - timedelta(hours=4)).timestamp()
    hass.states.async_set(INSIDE, "19.0", {"unit_of_measurement": "°C"}, timestamp=old)
    await climate._async_check_stale_sensors()
    assert climate.stale_sensors.safe_mode

    with CommandLog(coordinator) as log:
        await run_loops(climate, 3)

    assert len(log.of("setpoint")) == 3
