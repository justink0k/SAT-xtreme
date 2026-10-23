"""Moving a configuration of the official SAT (domain `sat`) to `sat_xtreme`: entities, device and options are kept."""
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.template import DOMAIN as TEMPLATE_DOMAIN
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.helpers.storage import Store
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.xtreme.migration import CONF_MIGRATED_FROM, LEGACY_DOMAIN
from tests.const import DEFAULT_USER_DATA

LEGACY_OPTIONS = {
    CONF_HEATING_CURVE_COEFFICIENT: 1.6,
    CONF_XTREME_PRIME_SETPOINT: True,
    CONF_XTREME_LEARNED_OPV: "learn",
}

# Entity IDs that a new entity would not get by itself (as after a rename, or with an area in the name), so a
# recreated entity would show up under another ID
CLIMATE_ID = "climate.living_room_heating"
SENSOR_ID = "sensor.living_room_heating_curve"


async def _setup_sensors(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, TEMPLATE_DOMAIN, {TEMPLATE_DOMAIN: [{SENSOR_DOMAIN: [
        {"name": "test_inside_sensor", "state": "{{ 20.0 | float }}"},
        {"name": "test_outside_sensor", "state": "{{ 12.0 | float }}"},
    ]}]})
    await hass.async_block_till_done()


def _legacy_entry(hass: HomeAssistant) -> MockConfigEntry:
    """A configuration of the official SAT: entities with their own IDs on a device."""
    legacy = MockConfigEntry(domain=LEGACY_DOMAIN, title="Test", unique_id="test-device",
                             data={**DEFAULT_USER_DATA, CONF_MINIMUM_SETPOINT: 47}, options=LEGACY_OPTIONS)
    legacy.add_to_hass(hass)

    device = device_registry.async_get(hass).async_get_or_create(config_entry_id=legacy.entry_id, identifiers={(LEGACY_DOMAIN, "Test")})
    registry = entity_registry.async_get(hass)
    climate = registry.async_get_or_create("climate", LEGACY_DOMAIN, "test", config_entry=legacy, device_id=device.id)
    registry.async_update_entity(climate.entity_id, new_entity_id=CLIMATE_ID)
    sensor = registry.async_get_or_create("sensor", LEGACY_DOMAIN, "test-heating-curve", config_entry=legacy, device_id=device.id)
    registry.async_update_entity(sensor.entity_id, new_entity_id=SENSOR_ID)

    # What Home Assistant leaves behind for an entity that is not loaded
    hass.states.async_set(CLIMATE_ID, STATE_UNAVAILABLE, {"restored": True})

    return legacy


async def _move(hass: HomeAssistant, legacy: MockConfigEntry):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] == FlowResultType.MENU
    assert result["menu_options"][0] == "move_from_sat"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "move_from_sat"})
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"entry": legacy.entry_id})
    await hass.async_block_till_done()

    return result


async def test_move_keeps_entities_device_and_options(hass: HomeAssistant) -> None:
    await _setup_sensors(hass)
    legacy = _legacy_entry(hass)
    registry = entity_registry.async_get(hass)
    registry_ids = {entity_id: registry.async_get(entity_id).id for entity_id in (CLIMATE_ID, SENSOR_ID)}
    device_id = registry.async_get(CLIMATE_ID).device_id
    await Store(hass, 1, f"sat_xtreme_opv_{legacy.entry_id}").async_save({"estimate": 44.5, "source": "plateau"})

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

    # The same registry entries moved (not recreated): same internal ID, same entity ID
    for entity_id, registry_id in registry_ids.items():
        moved = registry.async_get(entity_id)
        assert moved is not None, f"{entity_id} was removed instead of moved"
        assert moved.id == registry_id
        assert moved.platform == DOMAIN
        assert moved.config_entry_id == entry.entry_id

    assert registry.async_get_entity_id("climate", DOMAIN, "test") == CLIMATE_ID
    assert hass.states.get(CLIMATE_ID) is not None

    # The device was moved, not recreated
    device = device_registry.async_get(hass).async_get(device_id)
    assert device.identifiers == {(DOMAIN, "Test")}
    assert device.config_entries == {entry.entry_id}

    # Stored data keyed by the entry moved with it
    assert await Store(hass, 1, f"sat_xtreme_opv_{entry.entry_id}").async_load() == {"estimate": 44.5, "source": "plateau"}
    assert await Store(hass, 1, f"sat_xtreme_opv_{legacy.entry_id}").async_load() is None


async def test_entities_move_before_the_device_leaves_the_old_entry(hass: HomeAssistant) -> None:
    """Home Assistant removes the entities of a config entry that is removed from their device, so they must move first."""
    await _setup_sensors(hass)
    legacy = _legacy_entry(hass)
    registry = entity_registry.async_get(hass)
    original = device_registry.DeviceRegistry.async_update_device
    left_behind = []

    def update_device(self, device_id, **kwargs):
        if kwargs.get("remove_config_entry_id") == legacy.entry_id:
            left_behind.extend(entity.entity_id for entity in entity_registry.async_entries_for_config_entry(registry, legacy.entry_id))
        return original(self, device_id, **kwargs)

    with patch.object(device_registry.DeviceRegistry, "async_update_device", update_device):
        await _move(hass, legacy)

    assert left_behind == []


async def test_ignored_discoveries_are_not_offered(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=LEGACY_DOMAIN, title="Ignored gateway", source=config_entries.SOURCE_IGNORE, unique_id="ignored").add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    assert "move_from_sat" not in result["menu_options"]


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
    legacy = _legacy_entry(hass)

    entry = MockConfigEntry(domain=DOMAIN, title="Test", unique_id="test-device",
                            data={**legacy.data, CONF_MIGRATED_FROM: legacy.entry_id}, options=dict(legacy.options))
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.config_entries.async_get_entry(legacy.entry_id) is None
    assert entity_registry.async_get(hass).async_get(CLIMATE_ID).platform == DOMAIN
    assert CONF_MIGRATED_FROM not in entry.data
