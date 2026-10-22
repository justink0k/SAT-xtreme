"""Tests for the fixes of 4.2.1-xtreme.22 to .24: pyotgw version, no URLs in translations, push setpoint to thermostat, simulation option."""
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.fake import SatFakeCoordinator
from tests.xtreme_helpers import parameters

PACKAGE = Path(__file__).parent.parent / "custom_components" / "sat_xtreme"
URL = re.compile(r"[a-z][a-z0-9+.-]*://", re.IGNORECASE)


def test_pyotgw_follows_home_assistant():
    requirements = json.loads((PACKAGE / "manifest.json").read_text())["requirements"]

    # Home Assistant depends on pyotgw itself; hassfest wants a minimum version, not a pin
    assert "pyotgw>=2.2.3" in requirements
    assert not any(requirement.startswith("pyotgw==") for requirement in requirements)


def _strings(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{path}.{key}" if path else key)
    elif isinstance(node, str):
        yield path, node


def test_translations_contain_no_urls():
    for file in (PACKAGE / "translations").glob("*.json"):
        for path, text in _strings(json.loads(file.read_text())):
            assert not URL.search(text), f"{file.name}: URL in {path}"


@pytest.mark.parametrize(*parameters(**{CONF_PUSH_SETPOINT_TO_THERMOSTAT: True}))
async def test_push_setpoint_to_thermostat_is_read_from_the_options(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    with patch.object(coordinator, "async_set_control_thermostat_setpoint", AsyncMock()) as push:
        await climate.async_set_target_temperature(21.5)

    push.assert_awaited_once_with(21.5)


@pytest.mark.parametrize(*parameters())
async def test_push_setpoint_to_thermostat_is_off_by_default(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    with patch.object(coordinator, "async_set_control_thermostat_setpoint", AsyncMock()) as push:
        await climate.async_set_target_temperature(21.5)

    push.assert_not_awaited()


@pytest.mark.parametrize(*parameters(**{CONF_SIMULATION: True}))
async def test_simulation_is_read_from_the_options(caplog: pytest.LogCaptureFixture, hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    # The climate logs the warning while it is set up, which happens in the setup phase of the fixtures
    messages = [record.getMessage() for record in caplog.get_records("setup")]

    assert climate._simulation
    assert "Simulation mode!" in messages


@pytest.mark.parametrize(*parameters())
async def test_simulation_is_off_by_default(caplog: pytest.LogCaptureFixture, hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    messages = [record.getMessage() for record in caplog.get_records("setup")]

    assert not climate._simulation
    assert "Simulation mode!" not in messages
