"""Switch mode: SAT turns a switch or input_boolean on and off (audit finding H1)."""
import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.components.input_boolean import DOMAIN as INPUT_BOOLEAN_DOMAIN
from homeassistant.components.template import DOMAIN as TEMPLATE_DOMAIN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.coordinator import DeviceState
from custom_components.sat_xtreme.switch import SatSwitchCoordinator
from tests.loop_harness import ServiceCallLog, run_loops
from tests.xtreme_helpers import TEMPLATE_CONFIG

RELAY = "input_boolean.boiler"

SWITCH_PARAMETERS = [
    "domains, data, options, config",
    [(
        [(TEMPLATE_DOMAIN, 1), (INPUT_BOOLEAN_DOMAIN, 1)],
        {CONF_MODE: MODE_SWITCH, CONF_DEVICE: RELAY, CONF_HEATING_SYSTEM: HEATING_SYSTEM_RADIATORS, CONF_MINIMUM_SETPOINT: 46},
        {CONF_MAXIMUM_SETPOINT: 60, CONF_HEATING_CURVE_COEFFICIENT: 2.0},
        # An input_boolean from YAML has no registry entry
        {**TEMPLATE_CONFIG, INPUT_BOOLEAN_DOMAIN: {"boiler": {"name": "Boiler"}}},
    )],
]


@pytest.mark.parametrize(*SWITCH_PARAMETERS)
async def test_the_switch_coordinator_reads_the_relay(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    coordinator = climate._coordinator
    assert isinstance(coordinator, SatSwitchCoordinator)
    assert coordinator.device_id == RELAY
    assert not coordinator.device_active

    hass.states.async_set(RELAY, "on")

    # Before, the coordinator looked up the registry ID and never saw the relay on
    assert coordinator.device_active


@pytest.mark.parametrize(*SWITCH_PARAMETERS)
async def test_the_relay_turns_on_and_off_again(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    await climate.async_set_target_temperature(23.0)

    with ServiceCallLog(hass) as log:
        await climate.async_set_hvac_mode(HVACMode.HEAT)
        await run_loops(climate, 3)
        await hass.async_block_till_done()

        assert hass.states.get(RELAY).state == "on"
        # Turned on once, not again while it is on
        assert log.services(RELAY) == ["turn_on"]

        await climate.async_set_hvac_mode(HVACMode.OFF)
        await hass.async_block_till_done()

    # Before, SAT thought the relay was already off and never turned it off
    assert hass.states.get(RELAY).state == "off"
    assert log.services(RELAY) == ["turn_on", "turn_off"]


VALVE = "valve.boiler"


async def test_a_valve_opens_and_closes(hass: HomeAssistant) -> None:
    opened = async_mock_service(hass, "valve", "open_valve")
    closed = async_mock_service(hass, "valve", "close_valve")
    coordinator = SatSwitchCoordinator(hass, entity_id=VALVE, config_data={CONF_MINIMUM_SETPOINT: 46})

    await coordinator.async_set_heater_state(DeviceState.ON)
    await coordinator.async_set_heater_state(DeviceState.OFF)

    assert [call.data["entity_id"] for call in opened] == [VALVE]
    assert [call.data["entity_id"] for call in closed] == [VALVE]


@pytest.mark.parametrize("state, active", [("open", True), ("opening", True), ("closed", False), ("closing", False)])
async def test_a_valve_counts_as_on_when_open(hass: HomeAssistant, state: str, active: bool) -> None:
    coordinator = SatSwitchCoordinator(hass, entity_id=VALVE, config_data={CONF_MINIMUM_SETPOINT: 46})
    hass.states.async_set(VALVE, state)

    assert coordinator.device_active is active
