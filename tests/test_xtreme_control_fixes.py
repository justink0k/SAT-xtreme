"""Fixes in the PID controller and the heating curve, ideas from bellini666/SAT (4.2.1-xtreme.39, step 1A)."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.errors import Error
from custom_components.sat_xtreme.heating_curve import HeatingCurve
from custom_components.sat_xtreme.helpers import is_state_stale
from custom_components.sat_xtreme.pid import PID
from tests.xtreme_helpers import Clock, parameters

SENSOR = "sensor.test_inside_sensor"


@pytest.fixture
def clock():
    clock = Clock()
    with patch("custom_components.sat_xtreme.pid.monotonic", clock), patch("custom_components.sat_xtreme.helpers.monotonic", clock):
        yield clock


def _pid(kd: float = 1000.0, sample_time: float = 10) -> PID:
    return PID(heating_system=HEATING_SYSTEM_RADIATORS, automatic_gain_value=1.0, heating_curve_coefficient=1.0,
               derivative_time_weight=1.0, kp=0.0, ki=0.0, kd=kd, sample_time_limit=sample_time)


def _step(pid: PID, clock: Clock, error: float, seconds: float = 30) -> None:
    clock.now += seconds
    pid.update(Error(SENSOR, error), heating_curve_value=40.0, boiler_temperature=50.0)


def test_the_derivative_decays_inside_the_deadband(clock: Clock):
    pid = _pid()
    for error in (1.0, 0.6, 0.3, 0.05):
        _step(pid, clock, error)
    entry = abs(pid.derivative)
    assert entry > 0

    # Inside the deadband the error moves a little; before, the derivative stayed frozen at its last value
    for error in (0.0, 0.05, 0.0, 0.05, 0.0, 0.05):
        _step(pid, clock, error)

    assert abs(pid.derivative) < entry * 0.1


def test_the_derivative_decays_with_a_steady_error_inside_the_deadband(clock: Clock):
    pid = _pid()
    for error in (1.0, 0.6, 0.3, 0.05):
        _step(pid, clock, error)
    entry = abs(pid.derivative)

    for _ in range(8):
        _step(pid, clock, 0.05)

    assert abs(pid.derivative) < entry * 0.1


def test_a_held_derivative_fades_while_the_error_holds(clock: Clock):
    pid = _pid()
    for error in (1.0, 0.9, 0.8):
        _step(pid, clock, error, seconds=60)
    held = abs(pid.derivative)

    # The error stays at 0.8 for 40 minutes: it can't have changed faster than 0.1 per 40 minutes
    _step(pid, clock, 0.8, seconds=2400)

    assert abs(pid.derivative) < held
    assert abs(pid.raw_derivative) <= 0.1 / 2400 + 1e-9


def test_after_a_restore_the_slope_starts_again(clock: Clock):
    pid = _pid()
    pid.restore(State("climate.test", "heat", {"error": 0.3, "derivative_raw": 0.002}))

    # Five minutes later the error is 0; before, the slope ran across the downtime and the restored derivative
    clock.now += 300
    pid.update(Error(SENSOR, 0.25), heating_curve_value=40.0, boiler_temperature=50.0)

    assert pid.derivative == 0.0


def test_the_sensor_age_counts_from_the_last_report(hass: HomeAssistant):
    old = (dt_util.utcnow() - timedelta(hours=7)).timestamp()
    hass.states.async_set(SENSOR, "20.1", timestamp=old)
    assert is_state_stale(hass.states.get(SENSOR), 6 * 3600)

    # The sensor reports the same value again
    hass.states.async_set(SENSOR, "20.1")
    assert not is_state_stale(hass.states.get(SENSOR), 6 * 3600)


@pytest.mark.parametrize(*parameters())
async def test_a_steady_error_does_not_reset_the_pid(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    await climate.async_set_target_temperature(20.5)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    climate.pid._integral = 1.5

    # The PID was last updated 7 hours ago, but the sensor keeps reporting the same value
    climate.pid._last_updated -= 7 * 3600
    hass.states.async_set(SENSOR, "20.0", force_update=True)
    climate._async_control_pid()

    assert climate.pid._integral == 1.5


@pytest.mark.parametrize(*parameters())
async def test_a_silent_sensor_resets_the_pid_from_the_control_loop(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    await climate.async_set_target_temperature(20.5)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    climate.pid._integral = 1.5

    hass.states.async_set(SENSOR, "20.0", timestamp=(dt_util.utcnow() - timedelta(hours=7)).timestamp())
    await climate.async_control_heating_loop()

    assert climate.pid._integral == 0.0


def test_the_heating_curve_stays_flat_above_the_target():
    curve = HeatingCurve(heating_system=HEATING_SYSTEM_RADIATORS, coefficient=1.8)

    curve.update(target_temperature=21.0, outside_temperature=21.0)
    at_target = curve.value
    curve.update(target_temperature=21.0, outside_temperature=35.0)

    assert curve.value == at_target


def test_autotune_does_nothing_without_a_heating_demand():
    curve = HeatingCurve(heating_system=HEATING_SYSTEM_RADIATORS, coefficient=1.8)

    curve.autotune(setpoint=40.0, target_temperature=20.0, outside_temperature=20.0)

    assert curve.optimal_coefficient is None


@pytest.mark.parametrize("setpoint, direction", [(45.2, -1), (35.2, 1), (41.7, -1), (38.7, 1)])
def test_autotune_steps_against_the_derivative(setpoint: float, direction: int):
    curve = HeatingCurve(heating_system=HEATING_SYSTEM_RADIATORS, coefficient=1.8)
    curve.autotune(setpoint=40.0, target_temperature=20.0, outside_temperature=0.0)
    first = curve.optimal_coefficient

    curve.autotune(setpoint=setpoint, target_temperature=20.0, outside_temperature=0.0)
    raw = curve.calculate_coefficient(setpoint, 20.0, 0.0)

    # The stored value moves from the measured coefficient against the sign of the derivative
    stored_step = curve._optimal_coefficients[-1] - raw
    assert (stored_step > 0) == (direction > 0)
    assert curve.optimal_coefficient != first
