"""Fixtures for testing."""
import pytest
from _pytest.logging import LogCaptureFixture
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import assert_setup_component, MockConfigEntry

from custom_components.sat_xtreme.const import DOMAIN, CLIMATE, COORDINATOR
from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.coordinator import SatDataUpdateCoordinatorFactory
from tests.fake_coordinator import MODE_FAKE, SatFakeCoordinator
from tests.const import DEFAULT_USER_DATA


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def fake_coordinator(monkeypatch):
    """Let the coordinator factory create the test coordinator for the mode "fake" (not part of the integration)."""
    original = SatDataUpdateCoordinatorFactory.resolve

    def resolve(hass, mode, device, data, options=None):
        if mode == MODE_FAKE:
            return SatFakeCoordinator(hass=hass, config_data=data, options=options)
        return original(hass=hass, mode=mode, device=device, data=data, options=options)

    monkeypatch.setattr(SatDataUpdateCoordinatorFactory, "resolve", staticmethod(resolve))


@pytest.fixture
async def entry(hass: HomeAssistant, domains: list, data: dict, options: dict, config: dict, caplog: LogCaptureFixture) -> MockConfigEntry:
    """Setup any given integration."""
    for domain, count in domains:
        with assert_setup_component(count, domain):
            assert await async_setup_component(hass, domain, config)

        await hass.async_block_till_done()

    await hass.async_start()
    await hass.async_block_till_done()

    user_data = DEFAULT_USER_DATA.copy()
    user_data.update(data)

    config_entry = MockConfigEntry(domain=DOMAIN, data=user_data, options=options)
    await hass.config_entries.async_add(config_entry)

    return config_entry


@pytest.fixture
async def climate(hass, entry: MockConfigEntry) -> SatClimate:
    return hass.data[DOMAIN][entry.entry_id][CLIMATE]


@pytest.fixture
async def coordinator(hass, entry: MockConfigEntry) -> SatFakeCoordinator:
    return hass.data[DOMAIN][entry.entry_id][COORDINATOR]
