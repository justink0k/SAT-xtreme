"""The climate uses the native temperature names of Home Assistant 2026.11, and shows the same values as before."""
import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.sat_xtreme.climate import SatClimate
from tests.xtreme_helpers import parameters


def test_the_deprecated_names_are_not_provided() -> None:
    # Home Assistant 2026.11 warns about these, and they stop working in 2027.11
    for name in ("current_temperature", "target_temperature", "temperature_unit", "_attr_temperature_unit"):
        assert name not in SatClimate.__dict__


@pytest.mark.parametrize(*parameters())
async def test_the_state_shows_the_inside_temperature_and_the_target(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    await hass.async_block_till_done()

    state = hass.states.get(climate.entity_id)

    # The inside sensor of the tests reports 20.0 °C
    assert state.attributes["current_temperature"] == climate.native_current_temperature == 20.0
    assert state.attributes["temperature"] == climate.native_target_temperature == 21.0
    assert climate.native_temperature_unit == "°C"
