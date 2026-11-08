"""The heating system comes from the entry data, where the setup wizard stores it (audit finding H2)."""
import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from tests.xtreme_helpers import parameters


async def _reload_as(hass: HomeAssistant, entry: MockConfigEntry, heating_system: str) -> SatClimate:
    """Store the heating system in the data, as the wizard does, with PID version 3, and reload SAT.

    The test entry starts at config version 1, so its migration rewrites the heating system once; set it afterwards.
    """
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_HEATING_SYSTEM: heating_system}, options={**entry.options, CONF_PID_CONTROLLER_VERSION: 3}
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    return hass.data[DOMAIN][entry.entry_id][CLIMATE]


@pytest.mark.parametrize(*parameters(force_pwm=False))
async def test_underfloor_heating_gets_its_own_gains(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    climate = await _reload_as(hass, entry, HEATING_SYSTEM_UNDERFLOOR)
    assert entry.options.get(CONF_HEATING_SYSTEM) is None
    climate.pid._last_heating_curve_value = 30.0
    coefficient = climate.pid._heating_curve_coefficient

    # Before, the PID read the heating system from the options, which only had the default "radiators" (divisor 3)
    assert climate.pid._heating_system == HEATING_SYSTEM_UNDERFLOOR
    assert climate.pid.kp == round(coefficient * 30.0 / 4, 6)


@pytest.mark.parametrize(*parameters(force_pwm=False))
async def test_radiators_stay_the_same(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    climate = await _reload_as(hass, entry, HEATING_SYSTEM_RADIATORS)
    climate.pid._last_heating_curve_value = 30.0
    coefficient = climate.pid._heating_curve_coefficient

    assert climate.pid.kp == round(coefficient * 30.0 / 3, 6)


@pytest.mark.parametrize(*parameters(force_pwm=False))
async def test_the_rooms_use_the_same_heating_system(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    from custom_components.sat_xtreme.area import Area

    area = Area({**entry.data, CONF_HEATING_SYSTEM: HEATING_SYSTEM_UNDERFLOOR}, {**OPTIONS_DEFAULTS, **entry.options}, "climate.room")
    assert area.pid._heating_system == HEATING_SYSTEM_UNDERFLOOR


@pytest.mark.parametrize("heating_system, choices", [(HEATING_SYSTEM_HEAT_PUMP, ["2", "3"]), (HEATING_SYSTEM_RADIATORS, ["3", "4"])])
@pytest.mark.parametrize(*parameters())
async def test_the_cycles_per_hour_follow_the_heating_system(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, heating_system: str, choices: list) -> None:
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_HEATING_SYSTEM: heating_system})

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "system_configuration"})

    field = next(key for key in result["data_schema"].schema if str(key) == CONF_CYCLES_PER_HOUR)
    selector = result["data_schema"].schema[field]
    assert [option["value"] for option in selector.config["options"]] == choices
