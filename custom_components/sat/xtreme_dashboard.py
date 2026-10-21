"""SAT-xtreme dashboard: built from the entities of this SAT entry, looked up in the entity registry.

The entity IDs are resolved from the unique IDs, so the dashboard works whatever the entities are called,
and cards of features that are off are left out. Creating a dashboard from an integration is not an
official Home Assistant API; when it fails, the configuration is shown in a notification to paste by hand.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any, Optional

import yaml
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry, issue_registry

from .const import CONF_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

URL_PATH = "sat-xtreme"
TITLE = "SAT Xtreme"
ICON = "mdi:home-thermometer-outline"

# key -> (domain, unique ID suffix); the unique ID is "<name>" for the climate and "<name>-<suffix>" otherwise
ENTITIES: dict[str, tuple[str, Optional[str]]] = {
    "climate": ("climate", None),
    "flame_status": ("sensor", "flame-status"),
    "power": ("sensor", "boiler-current-power"),
    "heating_curve": ("sensor", "heating-curve"),
    "flow": ("sensor", "xtreme-boiler-flow"),
    "setpoint": ("sensor", "xtreme-control-setpoint"),
    "modulation": ("sensor", "xtreme-modulation"),
    "burner_starts": ("sensor", "xtreme-burner-starts"),
    "pid": ("sensor", "xtreme-pid-output"),
    "burn_time": ("sensor", "xtreme-pwm-burn-time"),
    "anti_cycling": ("sensor", "xtreme-anti-cycling-remaining"),
    "learned_opv": ("sensor", "xtreme-learned-opv"),
    "calibration": ("sensor", "xtreme-calibration"),
    "flame": ("binary_sensor", "xtreme-flame"),
    "hot_water": ("binary_sensor", "xtreme-hot-water"),
    "heating_demand": ("binary_sensor", "xtreme-heating-demand"),
    "calibration_start": ("button", "xtreme-calibration-start"),
    "calibration_stop": ("button", "xtreme-calibration-stop"),
    "keep_warm": ("switch", "xtreme-hot-water-keep-warm"),
}


def resolve_entities(hass: HomeAssistant, config_entry: ConfigEntry) -> dict[str, str]:
    """Return the entity IDs of this SAT entry that exist, by key."""
    registry = entity_registry.async_get(hass)
    name = str(config_entry.data.get(CONF_NAME)).lower()
    found = {}

    for key, (domain, suffix) in ENTITIES.items():
        unique_id = name if suffix is None else f"{name}-{suffix}"
        if (entity_id := registry.async_get_entity_id(domain, DOMAIN, unique_id)) is not None:
            found[key] = entity_id

    return found


def build_dashboard(entities: dict[str, str]) -> dict[str, Any]:
    """Build the dashboard configuration; cards whose entities do not exist are left out."""
    e = entities
    cards: list[dict[str, Any]] = []

    def attribute(key: str, attr: str, name: str, suffix: Optional[str] = None) -> dict[str, Any]:
        row = {"type": "attribute", "entity": e[key], "attribute": attr, "name": name}
        if suffix:
            row["suffix"] = suffix
        return row

    def rows(*items: tuple[str, str]) -> list[dict[str, Any]]:
        return [{"entity": e[key], "name": name} for key, name in items if key in e]

    # Now
    now: list[dict[str, Any]] = []
    if "climate" in e:
        now += [
            attribute("climate", "pulse_width_modulation_state", "PWM phase"),
            attribute("climate", "pulse_width_modulation_duty_cycle", "PWM on / off time (s)"),
            attribute("climate", "minimum_setpoint", "OPV in use", "°C"),
        ]
    now += rows(("flame_status", "Flame status"), ("anti_cycling", "Anti-cycling remaining"), ("modulation", "Modulation"), ("power", "Power now"), ("keep_warm", "Hot water keep warm"))
    stack = [{"type": "thermostat", "entity": e["climate"]}] if "climate" in e else []
    if now:
        stack.append({"type": "entities", "title": "Now", "entities": now})
    if stack:
        cards.append({"type": "vertical-stack", "cards": stack})

    # Last 6 hours
    graphs = []
    if temperatures := rows(("setpoint", "Control setpoint"), ("flow", "Flow")):
        graphs.append({"type": "history-graph", "title": "Last 6 hours", "hours_to_show": 6, "entities": temperatures})
    if modulation := rows(("modulation", "Modulation")):
        graphs.append({"type": "history-graph", "hours_to_show": 6, "entities": modulation})
    if states := rows(("flame", "Flame"), ("heating_demand", "Heating demand"), ("hot_water", "Hot water")):
        graphs.append({"type": "history-graph", "hours_to_show": 6, "entities": states})
    if graphs:
        cards.append({"type": "vertical-stack", "cards": graphs})

    # PID
    if "pid" in e:
        pid_rows = rows(("heating_curve", "Heating curve"), ("pid", "PID correction")) + [
            attribute("pid", "requested_setpoint", "Requested setpoint (curve + correction)", "°C"),
            attribute("pid", "proportional", "P part", "°C"),
            attribute("pid", "integral", "I part", "°C"),
            attribute("pid", "derivative", "D part", "°C"),
            attribute("pid", "kp", "kP in use"),
            attribute("pid", "gain_factor", "Gain factor"),
            attribute("pid", "maximum_setpoint_rise", "Maximum rise (0 = off)", "°C"),
        ]
        cards.append({"type": "vertical-stack", "cards": [
            {"type": "entities", "title": "PID", "entities": pid_rows},
            {"type": "history-graph", "title": "Heating curve and PID correction (24 hours)", "hours_to_show": 24,
             "entities": rows(("heating_curve", "Heating curve"), ("pid", "PID correction"), ("setpoint", "Control setpoint"))},
        ]})

    # PWM blocks and starts
    blocks = []
    if "burn_time" in e:
        blocks += [
            {"type": "entities", "title": "PWM blocks", "entities": rows(("burn_time", "Burn time of the last block")) + [
                attribute("burn_time", "target_seconds", "Planned on time of the last block", "s"),
                attribute("burn_time", "current_burn_seconds", "Burn time of the current block", "s"),
            ]},
            {"type": "history-graph", "title": "Burn time per block (24 hours)", "hours_to_show": 24,
             "entities": rows(("burn_time", "Burn time"), ("anti_cycling", "Anti-cycling remaining"))},
        ]
    if "burner_starts" in e:
        blocks.append({"type": "statistics-graph", "title": "Burner starts per day", "chart_type": "bar", "period": "day",
                       "days_to_show": 14, "stat_types": ["change"], "entities": rows(("burner_starts", "Starts"))})
    if blocks:
        cards.append({"type": "vertical-stack", "cards": blocks})

    # Learned OPV
    if "learned_opv" in e:
        cards.append({"type": "vertical-stack", "cards": [
            {"type": "entities", "title": "Learned OPV", "entities": rows(("learned_opv", "Learned OPV")) + [
                attribute("learned_opv", "mode", "Mode"),
                attribute("learned_opv", "estimate", "Estimate (without margin)", "°C"),
                attribute("learned_opv", "sample_count", "Samples"),
                attribute("learned_opv", "last_sample_type", "Last sample type"),
                attribute("learned_opv", "last_sample_value", "Last sample", "°C"),
                attribute("learned_opv", "last_update", "Last update"),
                attribute("learned_opv", "source", "Started from"),
            ]},
            {"type": "history-graph", "title": "Learned OPV (7 days)", "hours_to_show": 168, "entities": rows(("learned_opv", "Learned OPV"))},
        ]})

    # Calibration
    if "calibration" in e:
        calibration: list[dict[str, Any]] = []
        buttons = []
        for key, name, icon, text in (
                ("calibration_start", "Start calibration", "mdi:play", "Start the calibration? It can take several hours. SAT pauses its normal control in the meantime."),
                ("calibration_stop", "Stop calibration", "mdi:stop", "Stop the calibration and return to normal operation?"),
        ):
            if key in e:
                buttons.append({"type": "button", "name": name, "icon": icon, "entity": e[key], "tap_action": {
                    "action": "perform-action", "perform_action": "button.press", "target": {"entity_id": e[key]}, "confirmation": {"text": text}}})
        if buttons:
            calibration.append({"type": "horizontal-stack", "cards": buttons})

        calibration.append({"type": "entities", "title": "Calibration", "entities": rows(("calibration", "Phase")) + [
            attribute("calibration", "message", "Status"),
            attribute("calibration", "round", "Round"),
            attribute("calibration", "valid_rounds", "Valid rounds"),
            attribute("calibration", "setpoint", "Current setpoint", "°C"),
            attribute("calibration", "elapsed_minutes", "Running for", "min"),
        ]})
        sensor = e["calibration"]
        calibration.append({"type": "markdown", "title": "Last calibration report", "content": (
            f"{{% set r = state_attr('{sensor}', 'report') %}}\n"
            "{% if r %}\n**{{ r.message }}**\n\n"
            "Outcome: {{ r.outcome }} · Duration: {{ r.duration_minutes }} min\n\n"
            "{% if r.modulation_test %}Boiler follows the modulation limit: {{ r.modulation_test.result }}\n\n{% endif %}"
            "{% if r.result is not none %}Result: **{{ r.result }} °C**, spread {{ r.spread }} °C (min {{ r.minimum }} °C, max {{ r.maximum }} °C){% endif %}\n\n"
            "| Round | Result | Value | Steps |\n|---|---|---|---|\n"
            "{% for x in r.rounds %}| {{ x.number }} | {{ x.result }} | {{ x.value if x.value is not none else '–' }} | {{ x.steps | length }} |\n{% endfor %}"
            "{% else %}No calibration has run yet.{% endif %}"
        )})
        cards.append({"type": "vertical-stack", "cards": calibration})

    return {"title": TITLE, "views": [{"title": TITLE, "path": URL_PATH, "icon": ICON, "cards": cards}]}


def dashboard_exists(hass: HomeAssistant) -> bool:
    try:
        from homeassistant.components.lovelace.const import LOVELACE_DATA
        return URL_PATH in hass.data[LOVELACE_DATA].dashboards
    except Exception:
        return False


def _dashboards_collection(hass: HomeAssistant):
    """The storage collection behind Settings → Dashboards (not a public API, hence the defensive lookup)."""
    from homeassistant.components.websocket_api.const import DOMAIN as WEBSOCKET_DOMAIN

    handler, _schema = hass.data[WEBSOCKET_DOMAIN]["lovelace/dashboards/create"]
    return inspect.unwrap(handler).__self__.storage_collection


async def async_create_dashboard(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Create the SAT-xtreme dashboard, or rebuild it when it exists. Returns False when it had to fall back."""
    config = build_dashboard(resolve_entities(hass, config_entry))

    try:
        from homeassistant.components.lovelace.const import LOVELACE_DATA

        dashboards = hass.data[LOVELACE_DATA].dashboards
        if URL_PATH not in dashboards:
            await _dashboards_collection(hass).async_create_item({
                "url_path": URL_PATH, "title": TITLE, "icon": ICON, "show_in_sidebar": True, "require_admin": False,
            })

        await dashboards[URL_PATH].async_save(config)
    except Exception as exception:
        _LOGGER.warning("SAT-xtreme: could not create the dashboard automatically (%s); showing the configuration instead.", exception)
        persistent_notification.async_create(
            hass,
            "Home Assistant did not allow SAT-xtreme to create the dashboard automatically. Create a new dashboard "
            "(Settings → Dashboards → Add dashboard), open it, choose Edit → Raw configuration editor, and paste:\n\n"
            f"```yaml\n{yaml.safe_dump(config, sort_keys=False, allow_unicode=True)}```",
            title="SAT-xtreme dashboard",
            notification_id="sat_xtreme_dashboard",
        )
        return False

    issue_registry.async_delete_issue(hass, DOMAIN, f"create_dashboard_{config_entry.entry_id}")
    _LOGGER.info("SAT-xtreme: dashboard '%s' created or updated with %d cards.", TITLE, len(config["views"][0]["cards"]))
    return True


def async_offer_dashboard(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Offer to create the dashboard as a repair, unless it already exists."""
    issue_id = f"create_dashboard_{config_entry.entry_id}"

    if dashboard_exists(hass):
        issue_registry.async_delete_issue(hass, DOMAIN, issue_id)
        return

    issue_registry.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=True,
        severity=issue_registry.IssueSeverity.WARNING,
        translation_key="create_dashboard",
        data={"entry_id": config_entry.entry_id},
    )
