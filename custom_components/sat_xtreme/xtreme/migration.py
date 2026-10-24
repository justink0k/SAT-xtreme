"""Move a configuration of the domain `sat` (the official SAT) to `sat_xtreme`.

The move happens in two steps:

1. The config flow step "move_from_sat" unloads the old entry and creates a new entry with the same data and
   options, marked with the ID of the old entry.
2. When the new entry is set up, before its platforms load, the entities and then the device of the old entry
   are moved to the new entry with Home Assistant's own migration helpers. Entity IDs, unique IDs, history and
   restored states stay the same. The stored data of the fork is copied, and the old entry is removed.

The entities move before the device: when a config entry is removed from a device, Home Assistant removes the
entities of that config entry on that device right away.

Every step can run again, so an interrupted move continues on the next start.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import SOURCE_IGNORE, ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry, entity_registry, issue_registry
from homeassistant.helpers.storage import Store

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)

LEGACY_DOMAIN = "sat"
CONF_MIGRATED_FROM = "xtreme_migrated_from"

# Stored data of the fork, keyed by the config entry (all at storage version 1)
STORE_PREFIXES = ("sat_xtreme_opv_", "sat_xtreme_calibration_", "sat_xtreme_dashboard_", "sat_xtreme_hot_water_", "sat_xtreme_cycles_")
STORE_VERSION = 1

# Repairs of the old entry that no longer apply after the move
LEGACY_ISSUES = ("create_dashboard_", "update_dashboard_", "ignores_modulation_limit_")


def legacy_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    """Return the configurations of the domain `sat` that can be moved (not ignored discoveries)."""
    return [entry for entry in hass.config_entries.async_entries(LEGACY_DOMAIN) if entry.source != SOURCE_IGNORE]


async def async_unload_legacy_entry(hass: HomeAssistant, legacy_entry: ConfigEntry) -> None:
    """Unload the old entry, so it stops controlling the boiler and its entities can be moved.

    Unloading (not disabling) keeps the entities enabled, so moving them does not trigger a reload.
    """
    if legacy_entry.state is ConfigEntryState.LOADED:
        _LOGGER.info("SAT-xtreme: unloading the SAT configuration '%s' before moving it.", legacy_entry.title)
        await hass.config_entries.async_unload(legacy_entry.entry_id)


async def async_migrate_legacy_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Move the entities, device and stored data of the old entry to this entry, then remove the old entry."""
    if (legacy_entry_id := entry.data.get(CONF_MIGRATED_FROM)) is None:
        return

    _LOGGER.info("SAT-xtreme: moving the SAT configuration '%s' to SAT-xtreme.", entry.title)

    if (legacy_entry := hass.config_entries.async_get_entry(legacy_entry_id)) is not None:
        await async_unload_legacy_entry(hass, legacy_entry)

    # Entities first: moving the device away from the old entry removes the entities that still belong to it
    _move_entities(hass, legacy_entry_id, entry.entry_id)
    _move_devices(hass, legacy_entry_id, entry.entry_id)
    await _move_stores(hass, legacy_entry_id, entry.entry_id)

    for issue in LEGACY_ISSUES:
        issue_registry.async_delete_issue(hass, LEGACY_DOMAIN, f"{issue}{legacy_entry_id}")

    if legacy_entry is not None:
        await hass.config_entries.async_remove(legacy_entry_id)

    hass.config_entries.async_update_entry(entry, data={key: value for key, value in entry.data.items() if key != CONF_MIGRATED_FROM})
    _LOGGER.info("SAT-xtreme: the SAT configuration '%s' was moved to SAT-xtreme.", entry.title)


def _move_entities(hass: HomeAssistant, legacy_entry_id: str, entry_id: str) -> None:
    registry = entity_registry.async_get(hass)

    for entity in entity_registry.async_entries_for_config_entry(registry, legacy_entry_id):
        # An unloaded entity can still have a placeholder state ("unavailable", restored), which blocks the move
        if (state := hass.states.get(entity.entity_id)) is not None and state.attributes.get("restored"):
            hass.states.async_remove(entity.entity_id)

        registry.async_update_entity_platform(entity.entity_id, DOMAIN, new_config_entry_id=entry_id)

        # Entities of an old entry that the user had disabled were disabled with it; enable them again
        if entity.disabled_by == entity_registry.RegistryEntryDisabler.CONFIG_ENTRY:
            registry.async_update_entity(entity.entity_id, disabled_by=None)


def _move_devices(hass: HomeAssistant, legacy_entry_id: str, entry_id: str) -> None:
    registry = device_registry.async_get(hass)

    for device in device_registry.async_entries_for_config_entry(registry, legacy_entry_id):
        identifiers = {(DOMAIN, value) if domain == LEGACY_DOMAIN else (domain, value) for domain, value in device.identifiers}

        # Add the new entry first: removing the last entry of a device would delete the device
        registry.async_update_device(device.id, add_config_entry_id=entry_id, new_identifiers=identifiers)
        registry.async_update_device(device.id, remove_config_entry_id=legacy_entry_id)


async def _move_stores(hass: HomeAssistant, legacy_entry_id: str, entry_id: str) -> None:
    for prefix in STORE_PREFIXES:
        legacy_store = Store(hass, STORE_VERSION, f"{prefix}{legacy_entry_id}")

        if (data := await legacy_store.async_load()) is None:
            continue

        await Store(hass, STORE_VERSION, f"{prefix}{entry_id}").async_save(data)
        await legacy_store.async_remove()
