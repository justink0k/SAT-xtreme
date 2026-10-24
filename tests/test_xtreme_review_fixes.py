"""Fixes of 4.2.1-xtreme.30: no deprecated advanced-options check, no fixed area, no test code in the integration."""
from pathlib import Path

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import DOMAIN
from tests.xtreme_helpers import parameters

PACKAGE = Path(__file__).parent.parent / "custom_components" / "sat_xtreme"


def test_integration_does_not_use_show_advanced_options():
    for path in PACKAGE.rglob("*.py"):
        assert ".show_advanced_options" not in path.read_text(), f"{path.name} uses the deprecated show_advanced_options"


@pytest.mark.parametrize(*parameters())
async def test_advanced_page_is_always_offered(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert "advanced" in result["menu_options"]


async def test_simulator_is_not_in_the_user_menu(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER, "show_advanced_options": True})

    assert "simulator" not in result["menu_options"]


async def test_simulator_can_still_be_started_for_development(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "simulator"})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "simulator"


@pytest.mark.parametrize(*parameters())
async def test_device_gets_no_fixed_area(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    assert "suggested_area" not in climate.device_info


def test_no_test_code_in_the_integration():
    assert not (PACKAGE / "fake").exists()

    for path in PACKAGE.rglob("*.py"):
        text = path.read_text()
        assert "MODE_FAKE" not in text and "SatFakeCoordinator" not in text, f"{path.name} still refers to the test coordinator"
