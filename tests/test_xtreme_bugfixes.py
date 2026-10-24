"""Tests for the bug fixes of 4.2.1+xtreme.10."""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.boiler import BoilerState
from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.coordinator import DeviceState
from tests.fake_coordinator import SatFakeCoordinator
from custom_components.sat_xtreme.flame import Flame, FlameState
from custom_components.sat_xtreme.overshoot_protection import OvershootProtection
from custom_components.sat_xtreme.pwm import PWM, CycleConfig
from tests.xtreme_helpers import Clock, parameters


@pytest.mark.parametrize(*parameters())
async def test_reset_integral_accepts_a_single_entity_id(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    climate.pid._integral = 5.0

    await hass.services.async_call(DOMAIN, SERVICE_RESET_INTEGRAL, {"entity_id": climate.entity_id}, blocking=True)

    assert climate.pid.integral == 0.0


@pytest.mark.parametrize(*parameters(force_pwm=False, overshoot_protection=False))
async def test_pulse_width_modulation_accepts_a_single_entity_id(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    assert not climate.pwm.enabled

    await hass.services.async_call(DOMAIN, SERVICE_PULSE_WIDTH_MODULATION, {"entity_id": climate.entity_id, "enabled": True}, blocking=True)

    assert climate.pwm.enabled


async def test_old_calibration_does_not_block_without_boiler_temperature():
    coordinator = SimpleNamespace(boiler_temperature=None, maximum_setpoint_value=60, maximum_setpoint=60)
    protection = OvershootProtection(coordinator, HEATING_SYSTEM_RADIATORS)

    # Before the fix this loop never yielded, so the timeout could not even fire
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(protection._wait_for_stable_temperature(), timeout=0.1)


def _boiler_state(flame: bool) -> BoilerState:
    return BoilerState(
        is_active=flame, is_inactive=not flame, status=BoilerStatus.IDLE,
        flame_active=flame, hot_water_active=False, setpoint=46.0,
        flow_temperature=40.0, return_temperature=None, relative_modulation_level=0.0,
    )


def test_flame_off_at_start_up_is_not_a_flame_off():
    clock = Clock()
    flame = Flame()

    with patch("custom_components.sat_xtreme.flame.monotonic", clock):
        flame.update(boiler_state=_boiler_state(False))
        clock.now += 60
        flame.update(boiler_state=_boiler_state(False))
        assert flame.went_off_since is None

        flame.update(boiler_state=_boiler_state(True))
        assert flame.went_off_since is None

        clock.now += 300
        flame.update(boiler_state=_boiler_state(False))
        assert flame.went_off_since == clock.now


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_BOILER_TIMING: True}))
async def test_no_anti_cycling_wait_after_a_restart(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await coordinator.async_set_heater_state(DeviceState.OFF)
    coordinator._flame.update(boiler_state=coordinator.boiler)

    assert coordinator.flame.is_inactive
    assert coordinator.flame.off_since is None


def _pwm() -> PWM:
    pwm = PWM(
        cycles=CycleConfig(maximum_count=3, maximum_time=1200),
        heating_curve=SimpleNamespace(value=35.0, base_offset=20.0),
        supports_relative_modulation_management=False,
        automatic_duty_cycle=True,
    )
    pwm.enable()
    return pwm


async def test_maximum_cycles_count_over_the_last_hour():
    clock = Clock(10000.0)
    pwm = _pwm()
    boiler = _boiler_state(False)
    flame = FlameState(False, True, FlameStatus.IDLE_OK, None, None, None, 0, 0.0, 0.0, None)
    setpoint = 20.0 + 0.5 * (46.0 - 20.0)

    with patch("custom_components.sat_xtreme.pwm.monotonic", clock):
        # Three duty cycles started in the last 50 minutes
        pwm._cycle_starts.extend([clock.now - 3000, clock.now - 1500, clock.now - 100])
        pwm._status = PWMStatus.OFF
        pwm._last_update = clock.now - 2000

        await pwm.update(boiler=boiler, flame=flame, requested_setpoint=setpoint)
        assert pwm.status == PWMStatus.OFF

        # Ten minutes later the oldest start is more than an hour ago: a new cycle may start
        clock.now += 700
        await pwm.update(boiler=boiler, flame=flame, requested_setpoint=setpoint)
        assert pwm.status == PWMStatus.ON
        assert len(pwm._cycle_starts) == 3
