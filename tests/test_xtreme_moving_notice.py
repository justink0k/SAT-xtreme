"""The transition notice of 4.2.1-xtreme.25: SAT-xtreme moves to its own domain in the next version."""
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat.climate import SatClimate
from custom_components.sat.const import DOMAIN
from custom_components.sat.xtreme.moving_notice import ISSUE_ID, LEARN_MORE_URL
from tests.xtreme_helpers import parameters


@pytest.mark.parametrize(*parameters())
async def test_moving_notice_is_shown(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    issue = issue_registry.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID)

    assert issue is not None
    assert not issue.is_fixable
    assert issue.severity == issue_registry.IssueSeverity.WARNING
    assert issue.learn_more_url == LEARN_MORE_URL
