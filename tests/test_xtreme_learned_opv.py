"""Tests for the Xtreme profile, step 4: the self-learning OPV."""
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.boiler import BoilerState
from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from tests.fake_coordinator import SatFakeCoordinator
from custom_components.sat_xtreme.flame import FlameState
from custom_components.sat_xtreme.xtreme.opv import (
    MODULATION_MINIMUM_SAMPLES, REJECT_AT_SETPOINT, REJECT_MODULATION, SAMPLE_MAXIMUM_MODULATION, LearnedOpv, SAMPLE_PLATEAU,
    SAMPLE_SHUT_OFF,
)
from tests.xtreme_helpers import Clock, parameters, MINIMUM_SETPOINT_VALUE


def _opv(mode: str = "learn", configured: float = 46.0, maximum: float = 60.0, minimum: float = 40.0) -> LearnedOpv:
    return LearnedOpv(mode=mode, configured_value=configured, maximum_setpoint=maximum, storage_key="test_opv", minimum=minimum)


def _boiler(flow: float, flame: bool = True, modulation: float = 0.0, setpoint: float = 47.0, hot_water: bool = False) -> BoilerState:
    return BoilerState(
        is_active=flame,
        is_inactive=not flame,
        status=BoilerStatus.HEATING_UP,
        flame_active=flame,
        hot_water_active=hot_water,
        setpoint=setpoint,
        flow_temperature=flow,
        return_temperature=None,
        relative_modulation_level=modulation,
    )


def _flame(on_seconds: float | None) -> FlameState:
    active = on_seconds is not None
    return FlameState(active, not active, FlameStatus.HEALTHY, on_seconds, None, None, 0, 0.0, 0.0, None)


def _burn(opv: LearnedOpv, clock: Clock, flows: list[float], start_on_seconds: float = 200, step: float = 30, **kwargs) -> None:
    """Observe a burn: one observation per flow value, every `step` seconds."""
    on_seconds = start_on_seconds
    for flow in flows:
        opv.observe(boiler=_boiler(flow, **kwargs), flame=_flame(on_seconds), heating_demand=True, seconds_since_hot_water=None)
        clock.now += step
        on_seconds += step


def _heating_burn(opv: LearnedOpv, clock: Clock, wall: Clock, modulations: list[float], start_on_seconds: float = 0, **kwargs) -> None:
    """Observe a heating burn with the given modulation, one observation per minute."""
    on_seconds = start_on_seconds
    for modulation in modulations:
        opv.observe(boiler=_boiler(40.0, modulation=modulation, **kwargs), flame=_flame(on_seconds), heating_demand=True, seconds_since_hot_water=None)
        clock.now += 60
        wall.now += 60
        on_seconds += 60
    opv.observe(boiler=_boiler(40.0, flame=False, **kwargs), flame=_flame(None), heating_demand=True, seconds_since_hot_water=None)


@pytest.fixture
def clock():
    clock = Clock()

    with patch("custom_components.sat_xtreme.xtreme.opv.monotonic", clock):
        yield clock


@pytest.fixture
def wall():
    wall = Clock(1_800_000_000.0)

    with patch("custom_components.sat_xtreme.xtreme.opv._wall_time", wall):
        yield wall


def test_starts_at_the_configured_value():
    assert _opv(configured=46.0).value == 46.0
    assert _opv(configured=30.0).value == 40.0
    assert _opv(configured=58.0).value == 55.0
    assert _opv(configured=52.0, maximum=50.0).value == 50.0


def test_plateau_below_setpoint_is_a_sample(clock: Clock):
    opv = _opv()

    _burn(opv, clock, [44.0, 44.1, 44.0, 44.2, 44.1, 44.0, 44.1, 44.0])

    assert opv.sample_count == 1
    assert opv.attributes["last_sample_type"] == SAMPLE_PLATEAU
    assert opv.estimate == pytest.approx(45.0 + 0.1 * (44.1 - 45.0), abs=0.02)


def test_only_one_plateau_sample_per_burn(clock: Clock):
    opv = _opv()

    _burn(opv, clock, [44.0] * 30)

    assert opv.sample_count == 1


def test_plateau_at_the_setpoint_is_not_a_sample(clock: Clock):
    opv = _opv()

    _burn(opv, clock, [46.8] * 10, setpoint=47.0)

    assert opv.sample_count == 0


def test_rising_flow_is_not_a_plateau(clock: Clock):
    opv = _opv()

    _burn(opv, clock, [42.0, 42.4, 42.8, 43.2, 43.6, 44.0, 44.4, 44.8])

    assert opv.sample_count == 0


def test_modulating_boiler_is_not_a_sample(clock: Clock):
    opv = _opv()

    _burn(opv, clock, [44.0] * 10, modulation=15.0)

    assert opv.sample_count == 0


def test_recent_hot_water_is_not_a_sample(clock: Clock):
    opv = _opv()

    for _ in range(10):
        opv.observe(boiler=_boiler(44.0), flame=_flame(300), heating_demand=True, seconds_since_hot_water=120)
        clock.now += 30

    assert opv.sample_count == 0


def test_self_shut_off_raises_the_estimate(clock: Clock):
    opv = _opv()

    # The boiler switches itself off well below the setpoint
    _burn(opv, clock, [46.0, 46.5, 47.0, 47.5], setpoint=50.0)
    opv.observe(boiler=_boiler(48.0, flame=False, setpoint=50.0), flame=_flame(None), heating_demand=True, seconds_since_hot_water=None)

    assert opv.sample_count == 1
    assert opv.attributes["last_sample_type"] == SAMPLE_SHUT_OFF
    assert opv.estimate == pytest.approx(45.0 + 0.1 * (47.5 - 45.0), abs=0.02)


def test_shut_off_by_sat_is_not_a_sample(clock: Clock):
    opv = _opv()

    _burn(opv, clock, [46.0, 46.5, 47.0, 47.5])

    # The PWM on phase ended: SAT turned the heating demand off
    opv.observe(boiler=_boiler(47.5, flame=False), flame=_flame(None), heating_demand=False, seconds_since_hot_water=None)

    assert opv.sample_count == 0


def test_shut_off_below_the_estimate_does_not_lower_it(clock: Clock):
    opv = _opv(configured=50.0)

    _burn(opv, clock, [44.0, 44.5, 45.0])
    opv.observe(boiler=_boiler(45.0, flame=False), flame=_flame(None), heating_demand=True, seconds_since_hot_water=None)

    assert opv.sample_count == 0
    assert opv.estimate == 49.0


def test_steps_are_limited(clock: Clock):
    opv = _opv(configured=55.0)

    _burn(opv, clock, [30.0] * 10, setpoint=55.0)

    assert opv.estimate == 53.0


def test_off_mode_does_not_learn(clock: Clock):
    opv = _opv(mode="off")

    _burn(opv, clock, [44.0] * 10)

    assert opv.sample_count == 0
    assert not opv.enabled


def test_seed_from_calibration():
    opv = _opv()
    opv.seed(48.3)

    assert opv.estimate == 48.3
    assert opv.value == 49.3
    assert opv.attributes["source"] == "calibration"
    assert opv.sample_count == 0


async def test_learned_value_is_stored(hass: HomeAssistant, clock: Clock):
    opv = _opv()
    await opv.async_initialize(hass)
    opv.seed(47.0)
    await opv._store.async_save(opv._data_to_save())

    restored = _opv()
    await restored.async_initialize(hass)

    assert restored.estimate == 47.0
    assert restored.attributes["source"] == "calibration"


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_LEARNED_OPV: "apply"}))
async def test_apply_mode_uses_the_learned_value(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    climate.learned_opv.seed(48.0)

    assert climate.minimum_setpoint_value == 49.0


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_LEARNED_OPV: "learn"}))
async def test_learn_mode_keeps_the_configured_value(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    climate.learned_opv.seed(48.0)

    assert climate.minimum_setpoint_value == MINIMUM_SETPOINT_VALUE


def test_the_lowest_opv_can_be_changed():
    assert _opv(configured=30.0, minimum=35.0).value == 35.0
    assert _opv(configured=36.0, minimum=30.0).value == 36.0
    assert _opv(configured=46.0, minimum=48.0).value == 48.0


def test_shut_off_at_the_setpoint_does_not_raise_the_estimate(clock: Clock):
    # In PWM the setpoint is the OPV; the Intergas switches off just above it
    opv = _opv(configured=46.0)

    for _ in range(20):
        _burn(opv, clock, [45.0, 45.8, 46.5, 46.9], setpoint=46.0)
        opv.observe(boiler=_boiler(47.0, flame=False, setpoint=46.0), flame=_flame(None), heating_demand=True, seconds_since_hot_water=None)
        clock.now += 600

    assert opv.sample_count == 0
    assert opv.value == 46.0
    assert opv.attributes["last_burn_result"] == REJECT_AT_SETPOINT


def test_fixed_modulation_limit_until_there_is_enough_data(clock: Clock, wall: Clock):
    opv = _opv()

    assert opv.modulation_limit == SAMPLE_MAXIMUM_MODULATION
    _heating_burn(opv, clock, wall, [20.0] * 10)
    assert opv.modulation_limit == SAMPLE_MAXIMUM_MODULATION


def test_modulation_limit_follows_the_boiler(clock: Clock, wall: Clock):
    opv = _opv()

    # Burns at 10 to 30 %, with a long start peak at 90 % that must not count
    for _ in range(10):
        _heating_burn(opv, clock, wall, [90.0] * 5 + [10.0, 12.0, 15.0, 20.0, 30.0])

    assert opv.modulation_sample_count >= MODULATION_MINIMUM_SAMPLES
    assert opv.modulation_limit == pytest.approx(15.0, abs=0.5)
    assert opv.attributes["modulation_limit"] == opv.modulation_limit


def test_hot_water_is_not_used_for_the_modulation_limit(clock: Clock, wall: Clock):
    opv = _opv()

    for _ in range(10):
        on_seconds = 300
        for _ in range(5):
            opv.observe(boiler=_boiler(40.0, modulation=1.0, hot_water=True), flame=_flame(on_seconds), heating_demand=True, seconds_since_hot_water=0)
            clock.now += 60
            wall.now += 60
            on_seconds += 60

    assert opv.modulation_sample_count == 0


def test_old_modulation_data_expires(clock: Clock, wall: Clock):
    opv = _opv()

    for _ in range(10):
        _heating_burn(opv, clock, wall, [0.0] * 5 + [10.0] * 5)
    assert opv.modulation_limit > SAMPLE_MAXIMUM_MODULATION

    wall.now += 8 * 24 * 3600
    assert opv.modulation_sample_count == 0
    assert opv.modulation_limit == SAMPLE_MAXIMUM_MODULATION


def test_never_below_the_minimum_the_boiler_reports(clock: Clock, wall: Clock):
    opv = _opv()

    opv.observe(boiler=_boiler(40.0), flame=_flame(None), heating_demand=True, seconds_since_hot_water=None, boiler_minimum_modulation=20.0)

    assert opv.modulation_limit == 20.0


def test_plateau_at_the_learned_modulation_is_a_sample(clock: Clock, wall: Clock):
    opv = _opv()

    for _ in range(10):
        _heating_burn(opv, clock, wall, [90.0] * 5 + [12.0] * 5)

    before = opv.sample_count
    _burn(opv, clock, [44.0, 44.1, 44.0, 44.2, 44.1, 44.0, 44.1, 44.0], modulation=14.0)

    assert opv.sample_count == before + 1
    assert opv.attributes["last_sample_type"] == SAMPLE_PLATEAU


def test_last_burn_result_explains_a_rejection(clock: Clock):
    opv = _opv()

    _burn(opv, clock, [44.0] * 8, modulation=30.0)
    opv.observe(boiler=_boiler(44.0, flame=False), flame=_flame(None), heating_demand=False, seconds_since_hot_water=None)

    assert opv.attributes["last_burn_result"] == REJECT_MODULATION


async def test_modulation_data_is_stored(hass: HomeAssistant, clock: Clock, wall: Clock):
    opv = _opv()
    await opv.async_initialize(hass)

    for _ in range(10):
        _heating_burn(opv, clock, wall, [90.0] * 5 + [10.0] * 5)
    await opv._store.async_save(opv._data_to_save())

    restored = _opv()
    await restored.async_initialize(hass)

    assert restored.modulation_sample_count == opv.modulation_sample_count
    assert restored.modulation_limit == opv.modulation_limit


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_LEARNED_OPV: "apply", CONF_XTREME_OPV_MINIMUM: 35}))
async def test_the_option_sets_the_lowest_opv(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    assert climate.learned_opv.minimum == 35
