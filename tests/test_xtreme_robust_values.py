"""Invalid sensor values and a missing target temperature do not stop the control (audit findings M1 and M2)."""
import pytest
from homeassistant.components.climate import ATTR_PRESET_MODE, HVACMode
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from tests.fake_coordinator import SatFakeCoordinator
from tests.loop_harness import CommandLog, run_loops
from tests.xtreme_helpers import parameters

INSIDE = "sensor.test_inside_sensor"
OUTSIDE = "sensor.test_outside_sensor"
THERMOSTAT = "climate.thermostat"


async def _heat(climate: SatClimate) -> None:
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)


# M2: invalid sensor values

@pytest.mark.parametrize("value", ["none", "", "nan", "inf"])
@pytest.mark.parametrize(*parameters())
async def test_an_invalid_inside_value_skips_the_loop(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, value: str) -> None:
    await _heat(climate)
    hass.states.async_set(INSIDE, value)

    with CommandLog(coordinator) as log:
        # Before, this raised a ValueError in every control loop
        await run_loops(climate, 2)

    assert climate.current_temperature is None
    assert log.sent == []


@pytest.mark.parametrize(*parameters())
async def test_an_invalid_outside_value_moves_to_the_next_entity(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    climate.outside_sensor_entities = ["weather.home", OUTSIDE]
    hass.states.async_set(OUTSIDE, "none")
    hass.states.async_set("weather.home", "cloudy", {"temperature": 7.5})

    assert climate.current_outside_temperature == 7.5
    # The configured order stays as it is
    assert climate.outside_sensor_entities == ["weather.home", OUTSIDE]


@pytest.mark.parametrize(*parameters())
async def test_a_weather_entity_without_a_temperature_gives_no_value(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    climate.outside_sensor_entities = ["weather.home"]
    hass.states.async_set("weather.home", "cloudy")

    assert climate.current_outside_temperature is None


@pytest.mark.parametrize(*parameters())
async def test_a_weather_entity_with_sensor_in_its_name_is_a_weather_entity(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    climate.outside_sensor_entities = ["weather.sensor_home"]
    hass.states.async_set("weather.sensor_home", "cloudy", {"temperature": 4.0})

    # Before, the name made it a sensor, and float("cloudy") raised
    assert climate.current_outside_temperature == 4.0


@pytest.mark.parametrize(*parameters())
async def test_a_thermostat_without_a_target_does_not_break_the_valve_check(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    climate._radiators = [THERMOSTAT]
    hass.states.async_set(THERMOSTAT, HVACMode.HEAT, {"current_temperature": 20.0})

    assert climate.valves_open is False


# M1: a missing target temperature

@pytest.mark.parametrize(*parameters(**{CONF_PUSH_SETPOINT_TO_THERMOSTAT: True}))
async def test_no_target_temperature_keeps_the_last_one(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _heat(climate)

    with CommandLog(coordinator) as log:
        await climate.async_set_target_temperature(None)
        await run_loops(climate, 2)

    assert climate.target_temperature == 21.0
    # No TC=None, and the control goes on
    assert log.of("thermostat_setpoint") == []
    assert len(log.of("setpoint")) == 2


@pytest.mark.parametrize(*parameters())
async def test_a_thermostat_that_turns_off_keeps_the_target(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _heat(climate)
    old = hass.states.async_set(THERMOSTAT, HVACMode.HEAT, {"temperature": 21.0}) or hass.states.get(THERMOSTAT)
    hass.states.async_set(THERMOSTAT, HVACMode.OFF, {})
    event = type("Event", (), {"data": {"old_state": old, "new_state": hass.states.get(THERMOSTAT)}})()

    await climate._async_thermostat_changed(event)

    with CommandLog(coordinator) as log:
        await run_loops(climate, 1)

    assert climate.target_temperature == 21.0
    assert len(log.of("setpoint")) == 1


@pytest.mark.parametrize(*parameters())
async def test_clearing_a_preset_without_a_saved_temperature_keeps_the_target(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    await _heat(climate)
    climate._attr_preset_mode = "home"
    climate._pre_custom_temperature = None

    await climate.async_set_preset_mode("none")

    assert climate.target_temperature == 21.0
    assert hass.states.get(climate.entity_id).attributes[ATTR_PRESET_MODE] == "none"


@pytest.mark.parametrize(*parameters())
async def test_a_preset_with_the_same_temperature_still_shows(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    await climate.async_set_target_temperature(float(climate._presets["home"]))
    await hass.async_block_till_done()

    await climate.async_set_preset_mode("home")

    # Before, the target did not change, so the new preset was not written
    assert hass.states.get(climate.entity_id).attributes[ATTR_PRESET_MODE] == "home"
