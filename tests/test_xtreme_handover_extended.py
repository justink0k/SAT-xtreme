"""Hand over to the thermostat on stop, unload and startup, and the hand-over choice without an inside sensor (step 1C)."""
from datetime import timedelta
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.xtreme.profile import XtremeProfile
from tests.fake_coordinator import SatFakeCoordinator
from tests.xtreme_helpers import parameters

INSIDE = "sensor.test_inside_sensor"
HANDOVER = {CONF_XTREME_HANDOVER_ON_OFF: True}
HANDOVER_PUSH = {CONF_XTREME_HANDOVER_ON_OFF: True, CONF_PUSH_SETPOINT_TO_THERMOSTAT: True}
STALE_HAND_OVER = {CONF_XTREME_STALE_SENSORS: True, CONF_XTREME_STALE_ACTION: STALE_ACTION_HAND_OVER}


@pytest.fixture
def release():
    with patch.object(SatFakeCoordinator, "supports_setpoint_release", new_callable=PropertyMock, return_value=True), \
            patch.object(SatFakeCoordinator, "async_release_control_setpoint", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def thermostat():
    with patch.object(SatFakeCoordinator, "async_set_control_thermostat_setpoint", new_callable=AsyncMock) as mock:
        yield mock


def _set(hass: HomeAssistant, value: str, minutes_ago: float = 0) -> None:
    timestamp = (dt_util.utcnow() - timedelta(minutes=minutes_ago)).timestamp()
    hass.states.async_set(INSIDE, value, {"unit_of_measurement": "°C", "device_class": "temperature"}, timestamp=timestamp)


def _later(minutes: float):
    moment = dt_util.utcnow() + timedelta(minutes=minutes)
    return patch("custom_components.sat_xtreme.xtreme.stale._now", return_value=moment)


async def _heat(climate: SatClimate) -> None:
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)


# Hand over to the thermostat when SAT is turned off: the extension

@pytest.mark.parametrize(*parameters(**HANDOVER_PUSH))
async def test_turning_off_also_releases_the_pushed_thermostat_setpoint(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, release, thermostat) -> None:
    await climate.async_set_hvac_mode(HVACMode.OFF)

    release.assert_called_once()
    thermostat.assert_called_with(0)


@pytest.mark.parametrize(*parameters(**HANDOVER))
async def test_no_thermostat_release_without_pushing_the_setpoint(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, release, thermostat) -> None:
    await climate.async_set_hvac_mode(HVACMode.OFF)

    release.assert_called_once()
    thermostat.assert_not_called()


@pytest.mark.parametrize(*parameters(**HANDOVER))
async def test_stopping_home_assistant_hands_over(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, release) -> None:
    jobs = [job for job in hass._shutdown_jobs if job.job.target == climate._async_handover_on_shutdown]
    assert len(jobs) == 1

    await climate._async_handover_on_shutdown()
    release.assert_called_once()


@pytest.mark.parametrize(*parameters())
async def test_no_shutdown_job_without_the_option(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    assert not [job for job in hass._shutdown_jobs if getattr(job.job.target, "__name__", "") == "_async_handover_on_shutdown"]


@pytest.mark.parametrize(*parameters(**HANDOVER))
async def test_unloading_hands_over(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, release) -> None:
    await climate.async_will_remove_from_hass()
    release.assert_called_once()


@pytest.mark.parametrize(*parameters())
async def test_unloading_without_the_option_keeps_the_gateway(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, release) -> None:
    await climate.async_will_remove_from_hass()
    release.assert_not_called()


@pytest.mark.parametrize(*parameters(**HANDOVER_PUSH))
async def test_starting_in_off_hands_over(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, release, thermostat) -> None:
    climate._hvac_mode = HVACMode.OFF
    await climate._async_handover_on_startup()

    release.assert_called_once()
    thermostat.assert_called_once_with(0)


@pytest.mark.parametrize(*parameters(**HANDOVER_PUSH))
async def test_starting_in_heat_pushes_the_thermostat_setpoint_again(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, release, thermostat) -> None:
    climate._hvac_mode = HVACMode.HEAT
    climate._target_temperature = 20.5
    await climate._async_handover_on_startup()

    release.assert_not_called()
    thermostat.assert_called_once_with(20.5)


# Without an inside sensor: hand over to the thermostat after 10 minutes

def test_the_heating_curve_stays_the_default():
    assert XtremeProfile.from_options({}).stale_action == STALE_ACTION_HEATING_CURVE
    assert XtremeProfile.from_options({CONF_XTREME_STALE_ACTION: STALE_ACTION_HAND_OVER}).stale_action == STALE_ACTION_HAND_OVER


@pytest.mark.parametrize(*parameters(**STALE_HAND_OVER, **{CONF_PUSH_SETPOINT_TO_THERMOSTAT: True}))
async def test_the_thermostat_takes_over_after_10_minutes(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, release, thermostat) -> None:
    await _heat(climate)
    thermostat.reset_mock()
    _set(hass, "19.0", minutes_ago=200)
    await climate._async_check_stale_sensors()
    assert climate.stale_sensors.safe_mode

    with patch.object(SatFakeCoordinator, "async_control_heating_loop", new_callable=AsyncMock) as loop:
        # The first 10 minutes on the heating curve
        with _later(9):
            await climate.async_control_heating_loop()
        release.assert_not_called()
        assert loop.call_count == 1

        # Then the thermostat on the bus, once, and SAT sends nothing
        with _later(11):
            await climate.async_control_heating_loop()
            await climate.async_control_heating_loop()
        release.assert_called_once()
        thermostat.assert_called_once_with(0)
        assert loop.call_count == 1
        assert climate.stale_sensors.attributes["handed_over"]

        # The sensor reports again: SAT takes the boiler back
        _set(hass, "19.5")
        await climate._async_check_stale_sensors()
        await climate.async_control_heating_loop()

    assert not climate.stale_sensors.handed_over
    thermostat.assert_called_with(21.0)
    assert loop.call_count == 2


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_STALE_SENSORS: True}))
async def test_the_default_keeps_the_heating_curve(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, release) -> None:
    await _heat(climate)
    _set(hass, "19.0", minutes_ago=200)
    await climate._async_check_stale_sensors()

    with _later(60), patch.object(SatFakeCoordinator, "async_control_heating_loop", new_callable=AsyncMock) as loop:
        await climate.async_control_heating_loop()

    release.assert_not_called()
    loop.assert_called_once()


@pytest.mark.parametrize(*parameters(**STALE_HAND_OVER))
async def test_gateways_without_release_keep_the_heating_curve(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    await _heat(climate)
    _set(hass, "19.0", minutes_ago=200)
    await climate._async_check_stale_sensors()

    with _later(60), patch.object(SatFakeCoordinator, "async_release_control_setpoint", new_callable=AsyncMock) as release, \
            patch.object(SatFakeCoordinator, "async_control_heating_loop", new_callable=AsyncMock) as loop:
        await climate.async_control_heating_loop()

    release.assert_not_called()
    loop.assert_called_once()
    assert not climate.stale_sensors.handed_over


# Bug fix: the safe mode of stale sensors really heats on the heating curve

@pytest.mark.parametrize(*parameters(**{CONF_XTREME_STALE_SENSORS: True}))
async def test_the_safe_mode_keeps_sending_the_setpoint(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    await _heat(climate)
    _set(hass, "19.0", minutes_ago=200)
    await climate._async_check_stale_sensors()
    integral = climate.pid.integral

    with patch.object(SatFakeCoordinator, "async_set_control_setpoint", new_callable=AsyncMock) as setpoint:
        await climate.async_control_heating_loop()

    # Before, the loop stopped at the missing inside temperature and sent nothing
    setpoint.assert_called_once()
    assert climate.pid.integral == integral
