"""Tests for the Xtreme profile, step 3: align PWM with the boiler timing."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from custom_components.sat.boiler import BoilerState
from custom_components.sat.const import BoilerStatus, FlameStatus, PWMStatus
from custom_components.sat.flame import FlameState
from custom_components.sat.pwm import PWM, CycleConfig
from custom_components.sat.xtreme_profile import XtremeProfile
from tests.xtreme_helpers import Clock

BASE_OFFSET = 20.0
FLOW_TEMPERATURE = 46.0


def _setpoint_for_duty_cycle(duty_cycle: float) -> float:
    return BASE_OFFSET + duty_cycle * (FLOW_TEMPERATURE - BASE_OFFSET)


def _close(actual, expected) -> bool:
    return all(abs(a - e) <= 1 for a, e in zip(actual, expected))


def _pwm(boiler_timing: bool = True) -> PWM:
    heating_curve = SimpleNamespace(value=35.0, base_offset=BASE_OFFSET)
    profile = XtremeProfile(boiler_timing=boiler_timing)

    pwm = PWM(
        cycles=CycleConfig(maximum_count=3, maximum_time=1200),
        heating_curve=heating_curve,
        supports_relative_modulation_management=False,
        automatic_duty_cycle=True,
        xtreme_profile=profile,
    )
    pwm.enable()

    return pwm


class _Boiler:
    """Simulated boiler and flame state on a controllable clock."""

    def __init__(self, clock: Clock):
        self.clock = clock
        self.flame = False
        self.hot_water = False
        self.flame_on_at: float | None = None
        self.flame_off_at: float | None = None

    def set_flame(self, active: bool) -> None:
        if active and not self.flame:
            self.flame_on_at = self.clock.now
        if not active and self.flame:
            self.flame_off_at = self.clock.now

        self.flame = active

    @property
    def boiler_state(self) -> BoilerState:
        return BoilerState(
            is_active=self.flame,
            is_inactive=not self.flame,
            status=BoilerStatus.HEATING_UP if self.flame else BoilerStatus.IDLE,
            flame_active=self.flame,
            hot_water_active=self.hot_water,
            setpoint=46.0,
            flow_temperature=FLOW_TEMPERATURE,
            return_temperature=None,
            relative_modulation_level=0.0,
        )

    @property
    def flame_state(self) -> FlameState:
        return FlameState(
            self.flame,
            not self.flame,
            FlameStatus.HEALTHY,
            (self.clock.now - self.flame_on_at) if self.flame else None,
            None,
            None,
            0,
            0.0,
            0.0,
            None,
            off_since=None if self.flame else self.flame_off_at,
        )


async def _tick(pwm: PWM, boiler: _Boiler, clock: Clock, seconds: float, setpoint: float) -> None:
    clock.now += seconds
    await pwm.update(boiler=boiler.boiler_state, flame=boiler.flame_state, requested_setpoint=setpoint)


@pytest.fixture
def clock():
    clock = Clock()

    with patch("custom_components.sat.pwm.monotonic", clock):
        yield clock


def test_duty_cycle_uses_minimum_burn_time():
    pwm = _pwm()
    boiler = _Boiler(Clock())
    pwm._last_boiler_temperature = FLOW_TEMPERATURE

    assert _close(pwm._calculate_duty_cycle(_setpoint_for_duty_cycle(0.20), boiler.boiler_state), (360, 1440))
    assert _close(pwm._calculate_duty_cycle(_setpoint_for_duty_cycle(0.10), boiler.boiler_state), (360, 3240))
    assert _close(pwm._calculate_duty_cycle(_setpoint_for_duty_cycle(0.05), boiler.boiler_state), (0, 2400))
    assert _close(pwm._calculate_duty_cycle(_setpoint_for_duty_cycle(0.50), boiler.boiler_state), (600, 600))

    # The off phase is never shorter than the anti-cycling wait
    on_time, off_time = pwm._calculate_duty_cycle(_setpoint_for_duty_cycle(0.90), boiler.boiler_state)
    assert off_time >= 315


def test_duty_cycle_without_profile_is_upstream():
    pwm = _pwm(boiler_timing=False)
    boiler = _Boiler(Clock())
    pwm._last_boiler_temperature = FLOW_TEMPERATURE

    assert _close(pwm._calculate_duty_cycle(_setpoint_for_duty_cycle(0.20), boiler.boiler_state), (240, 960))
    assert _close(pwm._calculate_duty_cycle(_setpoint_for_duty_cycle(0.10), boiler.boiler_state), (180, 1620))


async def test_on_time_counts_burn_time(clock: Clock):
    pwm = _pwm()
    boiler = _Boiler(clock)
    setpoint = _setpoint_for_duty_cycle(0.20)

    await _tick(pwm, boiler, clock, 0, setpoint)
    assert pwm.status == PWMStatus.ON

    # The boiler is still anti-cycling for two minutes: no burn time
    for _ in range(4):
        await _tick(pwm, boiler, clock, 30, setpoint)
    assert pwm.status == PWMStatus.ON
    assert pwm.burn_seconds == 0

    # Five minutes of flame is not enough
    boiler.set_flame(True)
    for _ in range(10):
        await _tick(pwm, boiler, clock, 30, setpoint)
    assert pwm.status == PWMStatus.ON
    assert pwm.burn_seconds == 300

    # After six minutes of flame the on phase ends
    await _tick(pwm, boiler, clock, 30, setpoint)
    await _tick(pwm, boiler, clock, 30, setpoint)
    assert pwm.status == PWMStatus.OFF
    assert pwm.last_block_burn_seconds == 360
    assert pwm.last_block_target_seconds == 360


async def test_hot_water_pauses_burn_time(clock: Clock):
    pwm = _pwm()
    boiler = _Boiler(clock)
    setpoint = _setpoint_for_duty_cycle(0.20)

    await _tick(pwm, boiler, clock, 0, setpoint)
    boiler.set_flame(True)
    await _tick(pwm, boiler, clock, 60, setpoint)

    boiler.hot_water = True
    for _ in range(4):
        await _tick(pwm, boiler, clock, 30, setpoint)

    assert pwm.burn_seconds == 60
    assert pwm.status == PWMStatus.ON


async def test_flame_wait_timeout_counts_on_time_anyway(clock: Clock):
    pwm = _pwm()
    boiler = _Boiler(clock)
    setpoint = _setpoint_for_duty_cycle(0.20)

    await _tick(pwm, boiler, clock, 0, setpoint)

    # No flame at all: after 330 seconds the wall time counts
    for _ in range(10):
        await _tick(pwm, boiler, clock, 30, setpoint)
    assert pwm.burn_seconds == 0

    for _ in range(13):
        await _tick(pwm, boiler, clock, 30, setpoint)

    assert pwm.status == PWMStatus.OFF


async def test_on_phase_has_a_hard_maximum(clock: Clock):
    pwm = _pwm()
    boiler = _Boiler(clock)
    setpoint = _setpoint_for_duty_cycle(0.20)

    await _tick(pwm, boiler, clock, 0, setpoint)

    # Only hot water: no burn time at all, but the on phase ends after 2 x 360 + 330 seconds
    boiler.hot_water = True
    boiler.set_flame(True)
    for _ in range(34):
        await _tick(pwm, boiler, clock, 30, setpoint)
    assert pwm.status == PWMStatus.ON

    await _tick(pwm, boiler, clock, 30, setpoint)
    assert pwm.status == PWMStatus.OFF


async def test_new_on_phase_waits_for_anti_cycling_after_hot_water(clock: Clock):
    pwm = _pwm()
    boiler = _Boiler(clock)
    setpoint = _setpoint_for_duty_cycle(0.20)

    # Run one block, then end the off phase timer
    await _tick(pwm, boiler, clock, 0, setpoint)
    boiler.set_flame(True)
    for _ in range(13):
        await _tick(pwm, boiler, clock, 30, setpoint)
    boiler.set_flame(False)
    assert pwm.status == PWMStatus.OFF

    # A short comfort flame for hot water just before the off phase ends
    clock.now += 1400
    boiler.hot_water = True
    boiler.set_flame(True)
    await _tick(pwm, boiler, clock, 0, setpoint)
    assert pwm.status == PWMStatus.OFF

    clock.now += 10
    boiler.set_flame(False)
    boiler.hot_water = False

    # The off phase timer has passed, but the anti-cycling time has not
    await _tick(pwm, boiler, clock, 60, setpoint)
    assert pwm.status == PWMStatus.OFF
    assert 0 < pwm.anti_cycling_remaining <= 255

    await _tick(pwm, boiler, clock, 260, setpoint)
    assert pwm.status == PWMStatus.ON


async def test_without_profile_the_on_time_is_wall_time(clock: Clock):
    pwm = _pwm(boiler_timing=False)
    boiler = _Boiler(clock)
    setpoint = _setpoint_for_duty_cycle(0.20)

    await _tick(pwm, boiler, clock, 0, setpoint)
    assert pwm.status == PWMStatus.ON

    # No flame at all, but upstream ends the on phase after the on time (240 s)
    for _ in range(9):
        await _tick(pwm, boiler, clock, 30, setpoint)

    assert pwm.status == PWMStatus.OFF
