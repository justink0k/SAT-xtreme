"""Moving a configuration of the domain `sat` to `sat_xtreme`: entity IDs, device, options and stored data are kept."""
from homeassistant import config_entries
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.template import DOMAIN as TEMPLATE_DOMAIN
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry, entity_registry, issue_registry
from homeassistant.helpers.storage import Store
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.xtreme.migration import CONF_MIGRATED_FROM, LEGACY_DOMAIN, LEGACY_MOVING_NOTICE
from tests.const import DEFAULT_USER_DATA

LEGACY_OPTIONS = {
    CONF_HEATING_CURVE_COEFFICIENT: 1.6,
    CONF_XTREME_PRIME_SETPOINT: True,
    CONF_XTREME_LEARNED_OPV: "learn",
}


async def _setup_sensors(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, TEMPLATE_DOMAIN, {TEMPLATE_DOMAIN: [{SENSOR_DOMAIN: [
        {"name": "test_inside_sensor", "state": "{{ 20.0 | float }}"},
        {"name": "test_outside_sensor", "state": "{{ 12.0 | float }}"},
    ]}]})
    await hass.async_block_till_done()


def _legacy_entry(hass: HomeAssistant) -> tuple[MockConfigEntry, str, str]:
    """A configuration of the domain `sat` as an older SAT-xtreme left it: entities, a device and stored data."""
    legacy = MockConfigEntry(domain=LEGACY_DOMAIN, title="Test", unique_id="test-device",
                             data={**DEFAULT_USER_DATA, CONF_MINIMUM_SETPOINT: 47}, options=LEGACY_OPTIONS)
    legacy.add_to_hass(hass)

    device = device_registry.async_get(hass).async_get_or_create(config_entry_id=legacy.entry_id, identifiers={(LEGACY_DOMAIN, "Test")})
    registry = entity_registry.async_get(hass)
    climate = registry.async_get_or_create("climate", LEGACY_DOMAIN, "test", config_entry=legacy, device_id=device.id, suggested_object_id="test")
    sensor = registry.async_get_or_create("sensor", LEGACY_DOMAIN, "test-xtreme-learned-opv", config_entry=legacy, device_id=device.id,
                                          suggested_object_id="xtreme_fork_learned_opv_test")

    # What Home Assistant leaves behind for an entity that is not loaded
    hass.states.async_set(climate.entity_id, STATE_UNAVAILABLE, {"restored": True})

    return legacy, climate.entity_id, sensor.entity_id


async def _move(hass: HomeAssistant, legacy: MockConfigEntry):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] == FlowResultType.MENU
    assert result["menu_options"][0] == "move_from_sat"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "move_from_sat"})
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"entry": legacy.entry_id})
    await hass.async_block_till_done()

    return result


async def test_move_keeps_entities_device_options_and_stored_data(hass: HomeAssistant) -> None:
    await _setup_sensors(hass)
    legacy, climate_id, sensor_id = _legacy_entry(hass)
    await Store(hass, 1, f"sat_xtreme_opv_{legacy.entry_id}").async_save({"estimate": 44.5, "source": "plateau"})
    device_id = entity_registry.async_get(hass).async_get(climate_id).device_id
    issue_registry.async_create_issue(hass, LEGACY_DOMAIN, LEGACY_MOVING_NOTICE, is_fixable=False,
                                      severity=issue_registry.IssueSeverity.WARNING, translation_key=LEGACY_MOVING_NOTICE)

    result = await _move(hass, legacy)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry = result["result"]

    # The old configuration is gone, the new one carries its settings and no longer the move marker
    assert hass.config_entries.async_get_entry(legacy.entry_id) is None
    assert entry.unique_id == "test-device"
    assert entry.data[CONF_MINIMUM_SETPOINT] == 47
    assert CONF_MIGRATED_FROM not in entry.data
    assert entry.options[CONF_HEATING_CURVE_COEFFICIENT] == 1.6
    assert entry.options[CONF_XTREME_PRIME_SETPOINT] is True

    # The entities kept their entity IDs and moved to the new domain and entry
    registry = entity_registry.async_get(hass)
    for entity_id in (climate_id, sensor_id):
        moved = registry.async_get(entity_id)
        assert moved.platform == DOMAIN
        assert moved.config_entry_id == entry.entry_id

    assert registry.async_get_entity_id("climate", DOMAIN, "test") == "climate.test"
    assert registry.async_get_entity_id("climate", DOMAIN, "test_2") is None
    assert hass.states.get("climate.test") is not None
    assert hass.states.get("climate.test_2") is None

    # The device was moved, not recreated
    device = device_registry.async_get(hass).async_get(device_id)
    assert device.identifiers == {(DOMAIN, "Test")}
    assert device.config_entries == {entry.entry_id}

    # The stored data of the fork moved with it
    assert await Store(hass, 1, f"sat_xtreme_opv_{entry.entry_id}").async_load() == {"estimate": 44.5, "source": "plateau"}
    assert await Store(hass, 1, f"sat_xtreme_opv_{legacy.entry_id}").async_load() is None

    # The notice of 4.2.1-xtreme.25 that announced the move is gone
    assert issue_registry.async_get(hass).async_get_issue(LEGACY_DOMAIN, LEGACY_MOVING_NOTICE) is None


async def test_no_move_offered_without_a_sat_configuration(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    assert "move_from_sat" not in result["menu_options"]


async def test_move_aborts_when_nothing_is_left_to_move(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "move_from_sat"})

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "nothing_to_move"


async def test_interrupted_move_continues_on_the_next_setup(hass: HomeAssistant) -> None:
    """When Home Assistant stops between creating the new entry and moving, the next setup finishes the move."""
    await _setup_sensors(hass)
    legacy, climate_id, _sensor_id = _legacy_entry(hass)

    entry = MockConfigEntry(domain=DOMAIN, title="Test", unique_id="test-device",
                            data={**legacy.data, CONF_MIGRATED_FROM: legacy.entry_id}, options=dict(legacy.options))
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.config_entries.async_get_entry(legacy.entry_id) is None
    assert entity_registry.async_get(hass).async_get(climate_id).platform == DOMAIN
    assert CONF_MIGRATED_FROM not in entry.data
