"""An entry of an old config version is still migrated (the other tests start at the current version)."""
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.config_flow import SatFlowHandler
from custom_components.sat_xtreme.const import *
from tests.const import DEFAULT_USER_DATA
from tests.xtreme_helpers import TEMPLATE_CONFIG


async def test_an_old_entry_is_migrated_to_the_current_version(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "template", TEMPLATE_CONFIG)
    await hass.async_block_till_done()

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        data={**DEFAULT_USER_DATA, CONF_MINIMUM_SETPOINT: 46},
        options={CONF_HEATING_SYSTEM: HEATING_SYSTEM_UNDERFLOOR},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == SatFlowHandler.VERSION
    assert entry.data[CONF_HEATING_SYSTEM] == HEATING_SYSTEM_UNDERFLOOR
    assert entry.options[CONF_PID_CONTROLLER_VERSION] == 1
