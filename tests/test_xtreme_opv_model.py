"""Tests for the model of the burn that chooses the OPV, with a simulated boiler in a house with known properties."""
import json
from math import exp, log
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.xtreme.opv import LearnedOpv
from custom_components.sat_xtreme.xtreme.opv_model import (
    MINIMUM_BURNS, STATUS_ACTIVE, STATUS_COLLECTING, STATUS_CONTINUOUS, STATUS_HEAT_PUMP, STATUS_NO_FLOW,
    STATUS_NO_SELF_SHUT_OFF, STATUS_POOR_FIT, ModelSample, OpvModel,
)
from tests.xtreme_helpers import parameters

T0 = 1_800_000_000.0
HOUR = 3600
DAY = 24 * HOUR


class Boiler:
    """A boiler at minimum power: the flow approaches the balance temperature, and the boiler switches itself off
    at the setpoint plus its hysteresis. An optional start peak makes the first minutes faster."""

    def __init__(self, balance=52.0, start=32.0, k=0.004, hysteresis=1.0, peak_seconds=0.0, peak_rate=0.0,
                 self_shut_off=True, pwm=True, flow=True, target=lambda t: 20.0, current=lambda t, target: target):
        self.balance, self.start, self.k, self.hysteresis = balance, start, k, hysteresis
        self.peak_seconds, self.peak_rate = peak_seconds, peak_rate
        self.self_shut_off, self.pwm, self.flow = self_shut_off, pwm, flow
        self.target, self.current = target, current
        self.t = T0

    def true_seconds(self, opv: float) -> float:
        """The burn time the boiler really has at this OPV (without a start peak)."""
        stop = opv + self.hysteresis
        return log((self.balance - self.start) / (self.balance - stop)) / self.k

    def _flow_at(self, seconds: float) -> float:
        if seconds <= self.peak_seconds:
            return self.start + self.peak_rate * seconds
        begin = self.start + self.peak_rate * self.peak_seconds
        return self.balance - (self.balance - begin) * exp(-self.k * (seconds - self.peak_seconds))

    def burn(self, model: OpvModel, opv: float, hot_water: bool = False, step: float = 30, pause: float = 20 * 60) -> None:
        stop = opv + self.hysteresis
        seconds = 0.0
        self._sample(model, opv, flame=False, flow=self.start)
        while True:
            flow = self._flow_at(seconds)
            if self.self_shut_off and flow >= stop:
                break
            if not self.self_shut_off and seconds >= 300:
                break
            self._sample(model, opv, flame=True, flow=flow, hot_water=hot_water)
            seconds += step
            self.t += step
        # The flame goes out; the heating demand is still on when the boiler ends the burn itself
        self._sample(model, opv, flame=False, flow=flow, demand=self.self_shut_off, hot_water=hot_water)
        end = self.t + pause
        while self.t < end:
            self.t += 60
            self._sample(model, opv, flame=False, flow=self.start)

    def _sample(self, model, opv, flame, flow, demand=True, hot_water=False):
        target = self.target(self.t)
        model.update(ModelSample(
            time=self.t, heating=True, flame=flame, hot_water=hot_water, seconds_since_hot_water=0 if hot_water else None,
            heating_demand=demand, flow=flow if self.flow else None, setpoint=opv, pwm=self.pwm, target=target,
            current=self.current(self.t, target), outside=10.0,
        ), opv)


def _model(applied: bool = False, minimum_burn: float = 360, heat_pump: bool = False, limits=(40.0, 55.0)) -> OpvModel:
    return OpvModel(enabled=True, applied=applied, heat_pump=heat_pump, minimum_burn_seconds=minimum_burn, limits=lambda: limits)


def _run(boiler: Boiler, model: OpvModel, burns: int, opv=None) -> None:
    for _ in range(burns):
        boiler.burn(model, opv if opv is not None else (model.applied_value or 46.0))


@pytest.fixture(autouse=True)
def clock():
    """The model reads the time for its attributes; follow the simulated boiler."""
    with patch("custom_components.sat_xtreme.xtreme.opv_model._now", side_effect=lambda: _CLOCK[0]):
        yield


_CLOCK = [T0]


def _now(boiler: Boiler) -> float:
    _CLOCK[0] = boiler.t
    return boiler.t


def test_collecting_until_enough_burns():
    boiler, model = Boiler(), _model()

    _run(boiler, model, MINIMUM_BURNS - 1)

    assert model.status(_now(boiler)) == STATUS_COLLECTING


def test_the_burn_time_is_predicted():
    boiler, model = Boiler(), _model()
    _run(boiler, model, 40)
    now = _now(boiler)

    assert model.status(now) == STATUS_ACTIVE
    assert model.predict(46.0, now) == pytest.approx(boiler.true_seconds(46.0), rel=0.10)
    assert model.shut_off_offset(now) == pytest.approx(1.0, abs=0.5)


def test_above_the_measured_curve_it_is_extended():
    boiler, model = Boiler(), _model()
    _run(boiler, model, 40)
    now = _now(boiler)

    for opv in (47.0, 48.0):
        assert model.predict(opv, now) == pytest.approx(boiler.true_seconds(opv), rel=0.20)
    assert model.curve(now).balance == pytest.approx(52.0, abs=2.5)

    # More than 3 °C above the measured curve is not predicted
    assert model.predict(52.0, now) is None


def test_a_start_peak_is_part_of_the_curve():
    boiler = Boiler(peak_seconds=90, peak_rate=0.05)
    model = _model()
    _run(boiler, model, 40)
    now = _now(boiler)

    real = 90 + log((52.0 - (32.0 + 4.5)) / (52.0 - 47.0)) / 0.004
    assert model.predict(46.0, now) == pytest.approx(real, rel=0.10)


def test_short_and_long_burns():
    for k, opv in ((0.008, 46.0), (0.0015, 46.0)):
        boiler, model = Boiler(k=k), _model()
        _run(boiler, model, 40)
        now = _now(boiler)
        assert model.predict(opv, now) == pytest.approx(boiler.true_seconds(opv), rel=0.10)


def test_the_choice_is_the_lowest_opv_with_long_enough_burns():
    boiler, model = Boiler(k=0.004), _model(minimum_burn=360)
    _run(boiler, model, 40)
    now = _now(boiler)

    wanted = next(opv for opv in range(40, 56) if boiler.true_seconds(opv) >= 360)
    assert model.choice(now) == pytest.approx(wanted, abs=1)
    assert 40 <= model.choice(now) <= 55


def test_learn_mode_changes_nothing():
    boiler, model = Boiler(k=0.006), _model(applied=False, minimum_burn=600)
    _run(boiler, model, 60)

    assert model.applied_value is None
    assert model.choice(_now(boiler)) is not None


def test_apply_mode_changes_at_most_one_degree_per_day():
    boiler, model = Boiler(k=0.004), _model(applied=True, minimum_burn=600)
    _run(boiler, model, 40, opv=46.0)

    first = model.applied_value
    assert first in (46.0, 47.0)

    # Within a day no second step
    _run(boiler, model, 10)
    assert abs(model.applied_value - 46.0) <= 1


def test_the_model_does_not_apply_without_self_shut_off():
    boiler, model = Boiler(self_shut_off=False), _model()
    _run(boiler, model, 40)

    assert model.status(_now(boiler)) == STATUS_NO_SELF_SHUT_OFF


def test_the_model_does_not_apply_when_the_boiler_burns_continuously():
    boiler, model = Boiler(pwm=False), _model()
    _run(boiler, model, 40)

    assert model.status(_now(boiler)) == STATUS_CONTINUOUS


def test_the_model_does_not_apply_without_flow_temperature_or_for_a_heat_pump():
    boiler, model = Boiler(flow=False), _model()
    _run(boiler, model, 5)
    assert model.status(_now(boiler)) == STATUS_NO_FLOW

    assert _model(heat_pump=True).status(T0) == STATUS_HEAT_PUMP


def test_a_poor_fit_changes_nothing():
    boiler, model = Boiler(k=0.004), _model(applied=True, minimum_burn=600)
    _run(boiler, model, 40, opv=46.0)
    now = _now(boiler)
    model.applied_value, model._next_change = 46.0, None
    model._errors = [(now, 0.5)] * 10

    assert model.status(now) == STATUS_POOR_FIT
    model._control(now, 46.0)
    assert model.applied_value == 46.0


def test_hot_water_and_very_short_burns_are_not_used():
    boiler, model = Boiler(), _model()

    for _ in range(5):
        boiler.burn(model, 46.0, hot_water=True)
    assert model.attributes(46.0)["model_burns"] == 0

    short = Boiler(start=46.5)
    short.t = boiler.t
    for _ in range(5):
        short.burn(model, 46.0)
    assert model.attributes(46.0)["model_burns"] == 0


def test_too_cold_after_a_change_goes_back_and_blocks_the_value():
    cold = [False]
    boiler = Boiler(k=0.004, current=lambda t, target: target - (1.0 if cold[0] else 0.0))
    model = _model(applied=True, minimum_burn=600)
    for _ in range(80):
        boiler.burn(model, model.applied_value or 46.0)
        if model.applied_value not in (None, 46.0):
            break
    changed = model.applied_value
    assert changed != 46.0

    # Right after the change the room gets too cold
    cold[0] = True
    _run(boiler, model, 6)

    assert model.applied_value == 46.0
    assert "too cold" in model._last_decision
    assert str(int(changed)) in model._blocked


def test_a_test_step_is_applied_and_ends_by_itself():
    boiler, model = Boiler(k=0.004), _model()
    _run(boiler, model, 40)
    _now(boiler)

    model.start_test(-1, 2, 46.0)
    assert model.test_offset == -1
    test = model.attributes(46.0)["test"]
    assert test["predicted_seconds"] == pytest.approx(boiler.true_seconds(45.0), rel=0.15)

    _run(boiler, model, 6, opv=45.0)
    _now(boiler)
    assert model.test_offset == 0
    last = model.attributes(46.0)["last_test"]
    assert last["burns"] >= 2
    assert last["actual_seconds"] == pytest.approx(boiler.true_seconds(45.0), rel=0.15)


def test_the_test_step_is_limited():
    model = _model()
    model.start_test(-9, 500, 46.0)

    assert model.test_offset == -3
    assert model._test["until"] - _CLOCK[0] == pytest.approx(72 * HOUR)


def test_attributes_are_valid_json():
    boiler, model = Boiler(balance=47.5), _model()
    _run(boiler, model, 40)
    _now(boiler)

    json.dumps(model.attributes(46.0), allow_nan=False)


def test_learned_opv_uses_the_model_only_with_apply_and_the_test_always():
    for mode, expected in (("apply", 48.0), ("learn", 46.0)):
        opv = LearnedOpv(mode=mode, configured_value=46.0, maximum_setpoint=60.0, storage_key="test", model=True)
        opv.model.applied_value = 48.0
        assert opv.value == expected

    opv = LearnedOpv(mode="learn", configured_value=46.0, maximum_setpoint=60.0, storage_key="test", model=True)
    opv.model.start_test(-2, 24, 46.0)
    assert opv.with_test(46.0) == 44.0
    assert opv.with_test(41.0) == 40.0


async def test_the_model_is_stored_and_the_old_search_is_ignored(hass: HomeAssistant):
    from homeassistant.helpers.storage import Store

    await Store(hass, 1, "test_model").async_save({"estimate": 45.0, "search": {"phase": "down", "offset": -1.0}})
    opv = LearnedOpv(mode="apply", configured_value=46.0, maximum_setpoint=60.0, storage_key="test_model", model=True)
    await opv.async_initialize(hass)
    assert opv.model.applied_value is None
    assert opv.value == 46.0

    boiler = Boiler()
    _run(boiler, opv.model, 35)
    await opv._store.async_save(opv._data_to_save())

    restored = LearnedOpv(mode="apply", configured_value=46.0, maximum_setpoint=60.0, storage_key="test_model", model=True)
    await restored.async_initialize(hass)
    assert restored.model.attributes(46.0)["model_burns"] == 35


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_LEARNED_OPV: "learn", CONF_XTREME_OPV_SEARCH: True}))
async def test_the_action_lowers_the_opv_for_a_while_in_learn_mode(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    before = climate.minimum_setpoint_value

    await hass.services.async_call(DOMAIN, SERVICE_TRY_OPV_OFFSET, {"entity_id": climate.entity_id, "offset": -1, "hours": 24}, blocking=True)

    assert climate.learned_opv.model.test_offset == -1
    assert climate.minimum_setpoint_value == before - 1


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_LEARNED_OPV: "apply", CONF_XTREME_OPV_SEARCH: True}))
async def test_the_option_turns_the_model_on(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    assert climate.learned_opv.model.enabled

    await climate.async_control_heating_loop()

    assert climate.learned_opv.attributes["model_status"] == STATUS_COLLECTING
