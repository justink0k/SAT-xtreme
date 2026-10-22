"""Tests for the Xtreme profile, step 4: the self-learning OPV."""
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat.boiler import BoilerState
from custom_components.sat.climate import SatClimate
from custom_components.sat.const import *
from custom_components.sat.fake import SatFakeCoordinator
from custom_components.sat.flame import FlameState
from custom_components.sat.xtreme.opv import LearnedOpv, SAMPLE_PLATEAU, SAMPLE_SHUT_OFF
from tests.xtreme_helpers import Clock, parameters, MINIMUM_SETPOINT_VALUE


def _opv(mode: str = "learn", configured: float = 46.0, maximum: float = 60.0) -> LearnedOpv:
    return LearnedOpv(mode=mode, configured_value=configured, maximum_setpoint=maximum, storage_key="test_opv")


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


@pytest.fixture
def clock():
    clock = Clock()

    with patch("custom_components.sat.xtreme.opv.monotonic", clock):
        yield clock


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

    _burn(opv, clock, [46.0, 46.5, 47.0, 47.5])
    opv.observe(boiler=_boiler(48.0, flame=False), flame=_flame(None), heating_demand=True, seconds_since_hot_water=None)

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
