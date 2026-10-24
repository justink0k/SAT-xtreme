"""Tests for the burner cycle diagnostics (read only)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.coordinator import DeviceState
from custom_components.sat_xtreme.xtreme.cycles import (
    CYCLE_HISTORY_SIZE, EVENT_CYCLE_ENDED, EVENT_CYCLE_STARTED, STORE_PREFIX, CycleSample, CycleTracker,
)
from custom_components.sat_xtreme.xtreme.profile import XtremeProfile
from tests.fake_coordinator import SatFakeCoordinator
from tests.xtreme_helpers import parameters

T0 = datetime(2026, 10, 24, 12, 0, 0, tzinfo=timezone.utc)


def _tracker(anti_cycling_time: int = 300) -> CycleTracker:
    coordinator = SimpleNamespace(xtreme_profile=XtremeProfile(anti_cycling_time=anti_cycling_time))
    return CycleTracker(coordinator, SimpleNamespace(), "entry", "Test")


def _sample(seconds: float, flame: bool, flow: float | None = 40.0, hot_water: bool = False, return_temperature: float | None = 30.0,
            setpoint: float | None = 50.0, demand_off: bool = False, pwm_off: bool = False) -> CycleSample:
    return CycleSample(
        time=T0 + timedelta(seconds=seconds), flame=flame, hot_water=hot_water, flow_temperature=flow,
        return_temperature=return_temperature, setpoint=setpoint, heating_demand_off=demand_off, pwm_off=pwm_off,
    )


def _run(tracker: CycleTracker, *samples: CycleSample) -> None:
    for sample in samples:
        tracker.update(sample)


def test_profile_defaults_to_off():
    assert XtremeProfile.from_options({}).cycle_tracking is False
    assert XtremeProfile.from_options({CONF_XTREME_CYCLE_TRACKING: True}).cycle_tracking is True


def test_a_cycle_is_recorded_with_its_values():
    tracker = _tracker()
    _run(
        tracker,
        _sample(0, False),
        _sample(10, True, flow=35.0, return_temperature=30.0, setpoint=50.0),
        _sample(70, True, flow=45.0),
        _sample(130, True, flow=55.0),
        _sample(190, False, flow=52.0, return_temperature=38.0, setpoint=50.0, demand_off=True, pwm_off=True),
    )

    cycle = tracker.last_cycle
    assert cycle["start"] == (T0 + timedelta(seconds=10)).isoformat()
    assert cycle["end"] == (T0 + timedelta(seconds=190)).isoformat()
    assert cycle["duration"] == 180
    assert cycle["kind"] == "heating"
    assert cycle["end_reason"] == "pwm_block_ended"
    assert cycle["flow_start"] == 35.0
    assert (cycle["flow_min"], cycle["flow_max"]) == (35.0, 55.0)
    assert cycle["flow_average"] == 45.0
    assert (cycle["return_start"], cycle["return_end"]) == (30.0, 38.0)
    assert (cycle["setpoint_start"], cycle["setpoint_end"]) == (50.0, 50.0)
    assert cycle["during_anti_cycling"] is None


def test_the_average_flow_is_weighted_by_time():
    tracker = _tracker()
    # 40 °C for 30 seconds, then 60 °C for 90 seconds
    _run(tracker, _sample(0, False), _sample(0.1, True, flow=40.0), _sample(30.1, True, flow=60.0), _sample(120.1, False, demand_off=True))

    assert tracker.last_cycle["flow_average"] == 55.0


def test_a_cycle_running_at_start_up_is_not_recorded():
    tracker = _tracker()
    _run(tracker, _sample(0, True), _sample(60, True), _sample(120, False))

    assert tracker.last_cycle is None


def test_short_cycles_are_recorded():
    tracker = _tracker()
    _run(tracker, _sample(0, False), _sample(10, True), _sample(14, False))

    assert tracker.last_cycle["duration"] == 4


@pytest.mark.parametrize("end, kind, reason", [
    (dict(hot_water=True), "heating", "hot_water"),
    (dict(demand_off=True, pwm_off=True), "heating", "pwm_block_ended"),
    (dict(demand_off=True, pwm_off=False), "heating", "no_heating_demand"),
    (dict(flow=48.0, setpoint=50.0), "heating", "setpoint_reached"),
    (dict(flow=52.0, setpoint=50.0), "heating", "setpoint_reached"),
    (dict(flow=47.9, setpoint=50.0), "heating", "unknown"),
    (dict(flow=None, setpoint=None), "heating", "unknown"),
])
def test_end_reason(end, kind, reason):
    tracker = _tracker()
    _run(tracker, _sample(0, False), _sample(10, True), _sample(60, True), _sample(120, False, **end))

    assert tracker.last_cycle["kind"] == kind
    assert tracker.last_cycle["end_reason"] == reason


def test_hot_water_cycle():
    tracker = _tracker()
    _run(tracker, _sample(0, False), _sample(10, True, hot_water=True), _sample(40, True, hot_water=True), _sample(60, False, hot_water=False))

    assert tracker.last_cycle["kind"] == "hot_water"
    assert tracker.last_cycle["end_reason"] == "hot_water"


def test_start_within_the_anti_cycling_time():
    tracker = _tracker(anti_cycling_time=300)
    _run(
        tracker,
        _sample(0, False), _sample(10, True), _sample(100, False),
        _sample(399, True), _sample(500, False),
        _sample(800, True), _sample(900, False),
    )

    assert [cycle["during_anti_cycling"] for cycle in tracker.history] == [None, True, False]


def test_counts_over_the_last_hour_and_day():
    tracker = _tracker()
    _run(tracker, _sample(0, False))
    for start, duration, hot_water in ((0, 300, False), (3600, 120, True), (20000, 600, False), (21000, 240, False)):
        _run(tracker, _sample(start + 1, True, hot_water=hot_water), _sample(start + 1 + duration, False, hot_water=hot_water, demand_off=True))

    now = T0 + timedelta(seconds=22000)
    assert tracker.counts(3600, now) == {"count": 2, "average_duration": 420, "heating": 2, "hot_water": 0, "mixed": 0}
    assert tracker.counts(86400, now) == {"count": 4, "average_duration": 315, "heating": 3, "hot_water": 1, "mixed": 0}
    assert tracker.counts(60, now)["average_duration"] is None


def test_the_history_is_limited():
    tracker = _tracker(anti_cycling_time=0)
    _run(tracker, _sample(0, False))
    for index in range(CYCLE_HISTORY_SIZE + 5):
        _run(tracker, _sample(index * 10 + 1, True), _sample(index * 10 + 5, False))

    assert len(tracker.history) == CYCLE_HISTORY_SIZE
    assert tracker.history[0]["start"] == (T0 + timedelta(seconds=51)).isoformat()


def _unique_ids(hass: HomeAssistant) -> set[str]:
    return {entry.unique_id for entry in er.async_get(hass).entities.values() if entry.platform == DOMAIN}


@pytest.mark.parametrize(*parameters())
async def test_nothing_when_off(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, hass_storage) -> None:
    assert not any("cycle" in unique_id for unique_id in _unique_ids(hass))
    assert not any(key.startswith(STORE_PREFIX) for key in hass_storage)


async def _flame(hass: HomeAssistant, coordinator: SatFakeCoordinator, flame: bool, seconds: float, flow: float = 45.0) -> None:
    with patch.object(SatFakeCoordinator, "flame_active", new_callable=PropertyMock, return_value=flame), \
            patch.object(SatFakeCoordinator, "boiler_temperature", new_callable=PropertyMock, return_value=flow), \
            patch("custom_components.sat_xtreme.xtreme.cycles._now", return_value=T0 + timedelta(seconds=seconds)):
        coordinator.async_update_listeners()
        await hass.async_block_till_done()


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_CYCLE_TRACKING: True}))
async def test_events_sensors_and_history(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, hass_storage) -> None:
    assert {
        "test-xtreme-last-cycle", "test-xtreme-cycles-last-hour", "test-xtreme-cycles-last-24h",
        "test-xtreme-average-burn-time-last-hour", "test-xtreme-average-burn-time-last-24h",
    } <= _unique_ids(hass)

    started = async_capture_events(hass, EVENT_CYCLE_STARTED)
    ended = async_capture_events(hass, EVENT_CYCLE_ENDED)

    await coordinator.async_set_heater_state(DeviceState.ON)
    await _flame(hass, coordinator, False, 0)
    await _flame(hass, coordinator, True, 10, flow=40.0)
    await _flame(hass, coordinator, True, 130, flow=50.0)
    await coordinator.async_set_heater_state(DeviceState.OFF)
    await _flame(hass, coordinator, False, 250, flow=50.0)

    assert len(started) == 1 and len(ended) == 1
    assert started[0].data["entry_id"] == entry.entry_id
    assert started[0].data["flow_start"] == 40.0
    assert ended[0].data["duration"] == 240
    assert ended[0].data["end_reason"] == "no_heating_demand"

    registry = er.async_get(hass)
    last_cycle = hass.states.get(registry.async_get_entity_id("sensor", DOMAIN, "test-xtreme-last-cycle"))
    assert last_cycle.state == "240"
    assert last_cycle.attributes["flow_average"] == 45.0

    with patch("custom_components.sat_xtreme.xtreme.cycles._now", return_value=T0 + timedelta(seconds=300)):
        count = registry.async_get_entity_id("sensor", DOMAIN, "test-xtreme-cycles-last-hour")
        entity = hass.data["sensor"].get_entity(count)
        entity.async_write_ha_state()
        await hass.async_block_till_done()
        assert hass.states.get(count).state == "1"
        assert hass.states.get(count).attributes["heating"] == 1

    # The history is saved when SAT is unloaded and loaded again afterwards
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(hass_storage[f"{STORE_PREFIX}{entry.entry_id}"]["data"]["cycles"]) == 1

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    last_cycle = hass.states.get(registry.async_get_entity_id("sensor", DOMAIN, "test-xtreme-last-cycle"))
    assert last_cycle.state == "240"
