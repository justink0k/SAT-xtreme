"""Transition notice: SAT-xtreme moves to its own domain, `sat_xtreme`, in 4.2.1-xtreme.26.

Only in the last versions with the domain `sat`. The notice has no fix: it explains the move, and the move
itself happens in the new version (Add integration -> SAT-xtreme -> Move a configuration from SAT).
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry

from ..const import DOMAIN

ISSUE_ID = "moving_to_sat_xtreme"
LEARN_MORE_URL = "https://justink0k.github.io/SAT-xtreme/installation/#moving-from-sat"


@callback
def async_show_moving_notice(hass: HomeAssistant) -> None:
    """Show the notice under Settings -> System -> Repairs (once, not per configuration)."""
    issue_registry.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_ID,
        is_fixable=False,
        is_persistent=False,
        severity=issue_registry.IssueSeverity.WARNING,
        translation_key=ISSUE_ID,
        learn_more_url=LEARN_MORE_URL,
    )
