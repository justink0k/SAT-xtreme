"""Fixes in pulse width modulation, ideas from bellini666/SAT (step 2A)."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.boiler import BoilerState
from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.flame import FlameState
from custom_components.sat_xtreme.pwm import PWM, CycleConfig
from custom_components.sat_xtreme.xtreme.profile import XtremeProfile
from tests.xtreme_helpers import Clock, parameters

INSIDE = "sensor.test_inside_sensor"


@pytest.fixture
def clock():
    clock = Clock()

    with patch("custom_components.sat_xtreme.pwm.monotonic", clock):
        yield clock


def _pwm(maximum_count: int = 3) -> PWM:
    pwm = PWM(
        cycles=CycleConfig(maximum_count=maximum_count, maximum_time=1200),
        heating_curve=SimpleNamespace(value=35.0, base_offset=20.0),
        supports_relative_modulation_management=False,
        automatic_duty_cycle=True,
        xtreme_profile=XtremeProfile(),
    )
    pwm.enable()
    return pwm


def _boiler(flow: float, hot_water: bool = False) -> BoilerState:
    return BoilerState(
        is_active=True, is_inactive=False, status=BoilerStatus.HEATING_UP, flame_active=True, hot_water_active=hot_water,
        setpoint=46.0, flow_temperature=flow, return_temperature=None, relative_modulation_level=0.0,
    )


def _flame() -> FlameState:
    return FlameState(True, False, FlameStatus.HEALTHY, 100.0, None, None, 0, 0.0, 0.0, None)


async def _update(pwm: PWM, clock: Clock, seconds: float, flow: float = 46.0, hot_water: bool = False) -> None:
    clock.now += seconds
    await pwm.update(boiler=_boiler(flow, hot_water), flame=_flame(), requested_setpoint=35.0)


async def test_the_cycles_per_hour_survive_a_reset(clock: Clock):
    pwm = _pwm()
    await _update(pwm, clock, 0)
    assert pwm.status == PWMStatus.ON

    # Before, a reset (a target change, or PWM turned off for a moment) forgot the starts of the last hour
    pwm.reset()
    pwm.enable()
    assert pwm._current_cycle == 1

    # After an hour the start no longer counts
    await _update(pwm, clock, 3601)
    assert len(pwm._cycle_starts) <= 1
    assert clock.now - pwm._cycle_starts[0] < 3600


async def test_the_limit_holds_after_a_reset(clock: Clock):
    pwm = _pwm(maximum_count=1)
    await _update(pwm, clock, 0)
    assert pwm.status == PWMStatus.ON

    pwm.reset()
    pwm.enable()
    await _update(pwm, clock, 60)

    # Waiting in the off phase: in IDLE the climate heated on the requested setpoint, below the OPV (seen on the
    # tested boiler after a preset change: burns of 29 to 88 seconds)
    assert pwm.status == PWMStatus.OFF


async def test_a_new_cycle_starts_once_the_limit_allows_it(clock: Clock):
    pwm = _pwm(maximum_count=1)
    await _update(pwm, clock, 0)
    pwm.reset()
    pwm.enable()
    await _update(pwm, clock, 60)
    assert pwm.status == PWMStatus.OFF

    # An hour after the first start the limit allows a new cycle
    await _update(pwm, clock, 3600)

    assert pwm.status == PWMStatus.ON


async def test_hot_water_flow_does_not_shape_the_duty_cycle(clock: Clock):
    pwm = _pwm()
    await _update(pwm, clock, 0)
    assert pwm.status == PWMStatus.ON
    duty_cycle = pwm.duty_cycle

    # A hot water burn heats the flow to 65 °C; the radiators never see that
    await _update(pwm, clock, 200, flow=65.0, hot_water=True)
    await _update(pwm, clock, 10)

    assert pwm._last_boiler_temperature == 46.0
    assert pwm.duty_cycle == duty_cycle


@pytest.mark.parametrize(*parameters())
async def test_a_room_target_change_keeps_the_pwm_phase(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    climate.pwm._status = PWMStatus.ON

    # The reset path runs when a room changes its target; the error moves, the PID resets
    hass.states.async_set(INSIDE, "19.4")
    climate._async_control_pid(True)

    assert climate.pid.last_error == climate.max_error.value
    assert climate.pwm.status == PWMStatus.ON


@pytest.mark.parametrize(*parameters())
async def test_a_change_of_the_sat_target_still_resets_the_pwm(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    climate.pwm._status = PWMStatus.ON

    await climate.async_set_target_temperature(19.0)

    assert climate.pwm.status == PWMStatus.IDLE
