"""Tests for step 6: reload after options changes without an update listener (Home Assistant 2026.12)."""
import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat.climate import SatClimate
from custom_components.sat.const import *
from custom_components.sat.fake import SatFakeCoordinator
from tests.xtreme_helpers import parameters


@pytest.mark.parametrize(*parameters())
async def test_options_change_reloads_without_update_listener(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await hass.async_block_till_done()
    assert entry.update_listeners == []

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "xtreme_profile"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_XTREME_PRIME_SETPOINT: True})
    await hass.async_block_till_done()

    assert result["type"] == "create_entry"

    # The entry was reloaded: a new coordinator with the new option
    new_coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    assert new_coordinator is not coordinator
    assert new_coordinator.xtreme_profile.prime_setpoint
