"""Tests for the handling of stale inside and outside sensors."""
from datetime import timedelta

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.xtreme.profile import XtremeProfile
from custom_components.sat_xtreme.xtreme.stale import ISSUE_INSIDE, ISSUE_OUTSIDE, SOURCE_BACKUP, SOURCE_MAIN
from tests.fake_coordinator import SatFakeCoordinator
from tests.xtreme_helpers import parameters, xtreme_profile_input

INSIDE = "sensor.test_inside_sensor"
OUTSIDE = "sensor.test_outside_sensor"
BACKUP = "sensor.backup_inside"

ENABLED = {CONF_XTREME_STALE_SENSORS: True, CONF_XTREME_BACKUP_INSIDE_SENSOR: BACKUP}


def _set(hass: HomeAssistant, entity_id: str, value: str, minutes_ago: float = 0) -> None:
    timestamp = (dt_util.utcnow() - timedelta(minutes=minutes_ago)).timestamp()
    hass.states.async_set(entity_id, value, {"unit_of_measurement": "°C", "device_class": "temperature"}, timestamp=timestamp)


def _issue(hass: HomeAssistant, entry: MockConfigEntry, key: str):
    return ir.async_get(hass).async_get_issue(DOMAIN, f"{key}_{entry.entry_id}")


def _binary_sensor(hass: HomeAssistant):
    entity_id = er.async_get(hass).async_get_entity_id("binary_sensor", DOMAIN, "test-xtreme-stale-sensor")
    return hass.states.get(entity_id) if entity_id else None


async def _check(hass: HomeAssistant, climate: SatClimate) -> None:
    await climate._async_check_stale_sensors()
    await hass.async_block_till_done()


async def _heat(climate: SatClimate) -> None:
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)


def test_profile_defaults():
    profile = XtremeProfile.from_options({})
    assert profile.stale_sensors is False
    assert (profile.inside_max_age, profile.outside_max_age, profile.backup_inside_sensor) == (90, 180, None)


@pytest.mark.parametrize(*parameters())
async def test_nothing_when_off(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    # Older than the 90 minutes of the fork, but within the 6 hours of SAT 4.2.1
    _set(hass, INSIDE, "19.0", minutes_ago=100)
    await _check(hass, climate)

    assert not climate.stale_sensors.enabled
    assert not climate.stale_sensors.safe_mode
    assert climate.current_temperature == 19.0
    assert _binary_sensor(hass) is None
    assert _issue(hass, entry, ISSUE_INSIDE) is None


@pytest.mark.parametrize(*parameters(**ENABLED))
async def test_fresh_sensors_are_used(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    _set(hass, INSIDE, "19.5", minutes_ago=10)
    _set(hass, OUTSIDE, "8.0", minutes_ago=10)
    await _check(hass, climate)

    assert climate.stale_sensors.inside_source == SOURCE_MAIN
    assert climate.current_temperature == 19.5
    assert climate.current_outside_temperature == 8.0
    assert _binary_sensor(hass).state == "off"


@pytest.mark.parametrize(*parameters(**ENABLED))
async def test_the_same_value_reported_again_is_not_stale(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    _set(hass, INSIDE, "19.5", minutes_ago=300)
    # The sensor reports the same value again: last_updated stays old, last_reported is new
    _set(hass, INSIDE, "19.5")
    await _check(hass, climate)

    assert hass.states.get(INSIDE).last_updated < dt_util.utcnow() - timedelta(minutes=200)
    assert climate.stale_sensors.inside_source == SOURCE_MAIN


@pytest.mark.parametrize(*parameters(**ENABLED))
async def test_backup_sensor_takes_over_and_main_comes_back(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    _set(hass, INSIDE, "19.0", minutes_ago=100)
    _set(hass, BACKUP, "20.2", minutes_ago=5)
    await _check(hass, climate)

    assert climate.stale_sensors.inside_source == SOURCE_BACKUP
    assert climate.current_temperature == 20.2
    assert not climate.stale_sensors.safe_mode
    assert _binary_sensor(hass).state == "on"
    assert _binary_sensor(hass).attributes["inside_source"] == SOURCE_BACKUP
    assert _issue(hass, entry, ISSUE_INSIDE) is not None

    _set(hass, INSIDE, "19.4")
    await hass.async_block_till_done()

    assert climate.stale_sensors.inside_source == SOURCE_MAIN
    assert climate.current_temperature == 19.4
    assert _binary_sensor(hass).state == "off"
    assert _issue(hass, entry, ISSUE_INSIDE) is None


@pytest.mark.parametrize(*parameters(**ENABLED))
async def test_unavailable_counts_as_stale(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    _set(hass, BACKUP, "20.0")
    _set(hass, INSIDE, "unavailable")
    await hass.async_block_till_done()

    assert climate.stale_sensors.inside_source == SOURCE_BACKUP


@pytest.mark.parametrize(*parameters(**ENABLED))
async def test_safe_mode_heats_on_the_heating_curve_and_never_higher(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _heat(climate)
    climate.pid._integral = 0.5
    before = climate.requested_setpoint
    assert before > climate.heating_curve.value

    _set(hass, INSIDE, "19.0", minutes_ago=100)
    _set(hass, BACKUP, "19.0", minutes_ago=100)
    await _check(hass, climate)

    assert climate.stale_sensors.safe_mode
    assert climate.stale_sensors.setpoint_cap == before
    assert climate.current_temperature is None
    assert climate.requested_setpoint == round(climate.heating_curve.value, 1)
    assert climate.requested_setpoint <= before

    # The PID controller is left as it is
    climate._async_control_pid()
    assert climate.pid._integral == 0.5

    # Colder outside: the heating curve rises, but the setpoint stays at most the value from the start
    _set(hass, OUTSIDE, "-15.0")
    await hass.async_block_till_done()
    assert climate.heating_curve.value > before
    assert climate.requested_setpoint == before

    # The sensor reports again: back to normal
    _set(hass, INSIDE, "19.2")
    await hass.async_block_till_done()
    assert not climate.stale_sensors.safe_mode
    assert climate.current_temperature == 19.2


@pytest.mark.parametrize(*parameters(**ENABLED))
async def test_stale_outside_temperature_uses_the_last_known_value(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    _set(hass, INSIDE, "19.5")
    _set(hass, OUTSIDE, "6.0", minutes_ago=10)
    await _check(hass, climate)
    assert climate.current_outside_temperature == 6.0

    _set(hass, OUTSIDE, "unavailable")
    await hass.async_block_till_done()

    assert climate.stale_sensors.outside_stale
    assert climate.current_outside_temperature == 6.0
    assert _issue(hass, entry, ISSUE_OUTSIDE) is not None
    assert _binary_sensor(hass).state == "on"

    _set(hass, OUTSIDE, "7.0")
    await hass.async_block_till_done()

    assert not climate.stale_sensors.outside_stale
    assert climate.current_outside_temperature == 7.0
    assert _issue(hass, entry, ISSUE_OUTSIDE) is None


@pytest.mark.parametrize(*parameters(**ENABLED))
async def test_issues_are_removed_on_unload(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    _set(hass, INSIDE, "19.0", minutes_ago=100)
    await _check(hass, climate)
    assert _issue(hass, entry, ISSUE_INSIDE) is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert _issue(hass, entry, ISSUE_INSIDE) is None


@pytest.mark.parametrize(*parameters(**ENABLED))
async def test_backup_sensor_can_be_removed_in_the_options(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "xtreme_profile"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], xtreme_profile_input(**{CONF_XTREME_STALE_SENSORS: True}))
    await hass.async_block_till_done()

    assert entry.options[CONF_XTREME_STALE_SENSORS] is True
    assert entry.options[CONF_XTREME_BACKUP_INSIDE_SENSOR] is None
