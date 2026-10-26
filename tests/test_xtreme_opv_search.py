"""Tests for the search for the best OPV in steps."""
from math import sin, pi, sqrt
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.xtreme.opv import LearnedOpv
from custom_components.sat_xtreme.xtreme.opv_search import (
    NO_PLATEAU_SECONDS, PHASE_BASELINE, PHASE_DOWN, PHASE_REST, PHASE_UP, PHASE_WAITING, OpvSearch, SearchSample,
)
from tests.xtreme_helpers import parameters

T0 = 1_800_000_000.0
HOUR = 3600
DAY = 24 * HOUR


def day_night(t: float) -> float:
    """20 °C from 7 to 23 h, 16 °C at night."""
    hour = ((t - T0) / HOUR) % 24
    return 20.0 if 7 <= hour < 23 else 16.0


class House:
    """A house whose starts per hour and temperature swing can depend on the OPV step."""

    def __init__(self, starts=lambda offset: 1.0, swing=lambda offset: 0.2, cold=lambda offset: 0.0):
        self.starts, self.swing, self.cold = starts, swing, cold
        self.t = T0

    def run(self, search: OpvSearch, hours: float, outside: float = 10.0) -> None:
        for _ in range(int(hours * 60)):
            offset = search.offset
            interval = HOUR / self.starts(offset)
            flame = (self.t - T0) % interval < 60
            target = day_night(self.t)
            # A sine with amplitude a has a standard deviation of a / sqrt(2)
            current = target + self.swing(offset) * sqrt(2) * sin(2 * pi * (self.t - T0) / (2 * HOUR)) - self.cold(offset)
            search.update(SearchSample(self.t, True, flame, False, target, current, outside))
            self.t += 60


def _search(applied: bool = True, low: float = -5, high: float = 5) -> OpvSearch:
    return OpvSearch(enabled=True, applied=applied, allowed=lambda offset: low <= offset <= high)


def test_waits_three_days_without_plateau():
    search, house = _search(), House()

    house.run(search, 71)
    assert search.phase == PHASE_WAITING

    house.run(search, 2)
    assert search.phase == PHASE_BASELINE
    assert search.offset == 0


def test_learn_mode_only_shows_the_step():
    search, house = _search(applied=False), House()

    house.run(search, 72 + 50)

    assert search.phase == PHASE_BASELINE
    assert search.applied_offset == 0
    assert search.would_try == -1
    assert search.attributes(lambda offset: 46 + offset)["search_value"] == 45


def test_a_step_down_with_the_same_starts_is_kept():
    search, house = _search(low=-2), House()

    house.run(search, 72 + 49)
    assert search.phase == PHASE_DOWN and search.offset == -1

    house.run(search, 49)
    assert search.phase == PHASE_DOWN and search.offset == -2

    # The floor is reached after the next period
    house.run(search, 49)
    assert search.phase == PHASE_REST
    assert search.offset == -2
    assert search.applied_offset == -2


def test_more_starts_after_a_step_down_goes_back_and_tries_up():
    search = _search()
    house = House(starts=lambda offset: 1.0 if offset >= 0 else 1.5)

    house.run(search, 72 + 49 + 49)

    assert search.phase == PHASE_UP and search.offset == 1

    # The step up gives no clear gain: back to the start, and rest
    house.run(search, 49)
    assert search.phase == PHASE_REST
    assert search.offset == 0


def test_a_step_up_with_clearly_fewer_starts_is_kept():
    search = _search(high=1)
    house = House(starts=lambda offset: {-1: 1.5, 0: 1.0, 1: 0.7}[offset])

    house.run(search, 72 + 49 + 49 + 49)

    assert search.offset == 1
    assert search.phase == PHASE_REST


def test_too_cold_during_a_trial_stops_it_right_away():
    search = _search()
    house = House(cold=lambda offset: 0.8 if offset < 0 else 0.0)

    house.run(search, 72 + 49)
    assert search.phase == PHASE_DOWN

    # Within a day the room is too cold in the stable hours
    house.run(search, 20)
    assert search.offset >= 0
    assert search.phase in (PHASE_UP, PHASE_REST)


def test_a_less_steady_temperature_goes_back_even_with_a_better_score():
    search = _search()
    house = House(starts=lambda offset: 1.0 if offset >= 0 else 0.8, swing=lambda offset: 0.1 if offset >= 0 else 0.3)

    house.run(search, 72 + 49 + 49)

    # Back from the step down, now trying one step up
    assert search.phase == PHASE_UP and search.offset == 1


def test_a_small_change_in_spread_is_accepted():
    # From 0.06 to 0.15 °C is more than 50 % but less than 0.1 °C more: not a reason to go back
    search = _search(low=-1)
    house = House(swing=lambda offset: 0.06 if offset >= 0 else 0.15)

    house.run(search, 72 + 49 + 49)

    assert search.offset == -1


def test_the_night_setback_is_not_counted_as_discomfort():
    search, house = _search(), House()

    house.run(search, 72 + 49)

    # The night target is 4 °C lower; only stable hours count, so the mean error stays close to zero
    assert search._baseline is not None
    assert abs(search._baseline["mean_error"]) < 0.05
    assert search._baseline["spread"] == pytest.approx(0.2, abs=0.03)


def test_a_period_is_extended_with_too_few_starts():
    search = _search()
    house = House(starts=lambda offset: 0.3)

    house.run(search, 72 + 49)

    assert search.phase == PHASE_BASELINE
    assert search._baseline is None

    house.run(search, 24)
    assert search.phase == PHASE_DOWN


def test_no_step_down_below_the_limit():
    search = _search(low=0)
    house = House()

    house.run(search, 72 + 49)

    assert search.phase == PHASE_UP and search.offset == 1


def test_a_plateau_sample_resets_the_search():
    search, house = _search(), House()

    house.run(search, 72 + 49)
    assert search.offset == -1

    search.on_plateau(house.t)

    assert search.phase == PHASE_WAITING
    assert search.offset == 0
    assert search.applied_offset == 0


def test_the_state_survives_a_restart():
    search, house = _search(), House()
    house.run(search, 72 + 60)

    restored = _search()
    restored.load(search.to_dict())

    assert restored.phase == search.phase
    assert restored.offset == search.offset
    assert restored._period.starts == search._period.starts
    house.run(restored, 1)


def test_learned_opv_applies_the_step_only_in_apply_mode():
    with patch("custom_components.sat_xtreme.xtreme.opv._wall_time", return_value=T0):
        for mode, expected in (("apply", 45.0), ("learn", 46.0)):
            opv = LearnedOpv(mode=mode, configured_value=46.0, maximum_setpoint=60.0, storage_key="test", search=True)
            opv.search.offset = -1.0

            assert opv.value == expected


def test_learned_opv_keeps_the_step_within_the_floor():
    opv = LearnedOpv(mode="apply", configured_value=41.0, maximum_setpoint=60.0, storage_key="test", minimum=40.0, search=True)

    # From 41 °C one step down to the floor of 40 °C is possible, a second one is not
    assert opv.search._allowed(-1.0)
    opv.search.offset = -1.0
    assert not opv.search._allowed(-2.0)
    assert opv._value_with(-5.0) == 40.0


def test_a_plateau_sample_in_the_learned_opv_resets_the_search():
    opv = LearnedOpv(mode="apply", configured_value=46.0, maximum_setpoint=60.0, storage_key="test", search=True)
    opv.search.offset = -1.0
    opv.search.phase = PHASE_DOWN

    opv._on_plateau(44.0)

    assert opv.search.phase == PHASE_WAITING
    assert opv.search.offset == 0


async def test_the_search_is_stored_with_the_learned_opv(hass: HomeAssistant):
    opv = LearnedOpv(mode="apply", configured_value=46.0, maximum_setpoint=60.0, storage_key="test_search", search=True)
    await opv.async_initialize(hass)
    house = House()

    for _ in range(int((72 + 50) * 60)):
        target = day_night(house.t)
        opv.update_search(SearchSample(house.t, True, (house.t - T0) % HOUR < 60, False, target, target, 10.0))
        house.t += 60
    await opv._store.async_save(opv._data_to_save())

    restored = LearnedOpv(mode="apply", configured_value=46.0, maximum_setpoint=60.0, storage_key="test_search", search=True)
    await restored.async_initialize(hass)

    assert restored.search.phase == PHASE_DOWN
    assert restored.value == 45.0


def test_off_when_the_option_is_off():
    opv = LearnedOpv(mode="apply", configured_value=46.0, maximum_setpoint=60.0, storage_key="test")

    assert not opv.search.enabled
    assert opv.attributes["search_phase"] is None


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_LEARNED_OPV: "apply", CONF_XTREME_OPV_SEARCH: True}))
async def test_the_option_turns_the_search_on(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    assert climate.learned_opv.search.enabled

    await climate.async_control_heating_loop()

    assert climate.learned_opv.attributes["search_phase"] == PHASE_WAITING
