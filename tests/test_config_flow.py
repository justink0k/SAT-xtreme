from custom_components.sat_xtreme.config_flow import SatFlowHandler
from tests.fake_coordinator import MODE_FAKE


async def test_create_coordinator(hass):
    flow_handler = SatFlowHandler()
    flow_handler.data = {
        "name": "Test",
        "mode": MODE_FAKE,
        "device": "test_device",
    }

    await flow_handler.async_create_coordinator()
