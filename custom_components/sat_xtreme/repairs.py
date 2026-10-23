"""Repairs of SAT-xtreme: fixes that are offered to the user, never applied without a click."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_XTREME_IGNORE_MODULATION_LIMIT
from .xtreme.dashboard import async_create_dashboard
from .xtreme.migration import LEGACY_FILES_ISSUE, async_remove_legacy_files


class IgnoreModulationLimitRepairFlow(ConfirmRepairFlow):
    """Turn on 'the boiler ignores the modulation limit' after the calibration found that it does."""

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            if (entry := self.hass.config_entries.async_get_entry(self._entry_id)) is not None:
                self.hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_XTREME_IGNORE_MODULATION_LIMIT: True})
                self.hass.config_entries.async_schedule_reload(entry.entry_id)

            return self.async_create_entry(data={})

        return await super().async_step_confirm(user_input)


class CreateDashboardRepairFlow(ConfirmRepairFlow):
    """Create the SAT Xtreme dashboard after a click."""

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            if (entry := self.hass.config_entries.async_get_entry(self._entry_id)) is not None:
                await async_create_dashboard(self.hass, entry)

            return self.async_create_entry(data={})

        return await super().async_step_confirm(user_input)


class RemoveLegacyFilesRepairFlow(ConfirmRepairFlow):
    """Remove the files of SAT-xtreme 4.2.1-xtreme.25 or older after a click, once they are no longer used."""

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            if not await async_remove_legacy_files(self.hass):
                return self.async_abort(reason="legacy_files_in_use")

            return self.async_create_entry(data={})

        return await super().async_step_confirm(user_input)


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None) -> RepairsFlow:
    """Create the fix flow for an issue of this integration."""
    entry_id = (data or {}).get("entry_id", "")

    if issue_id == LEGACY_FILES_ISSUE:
        return RemoveLegacyFilesRepairFlow()

    if issue_id.startswith(("create_dashboard", "update_dashboard")):
        return CreateDashboardRepairFlow(entry_id)

    return IgnoreModulationLimitRepairFlow(entry_id)
