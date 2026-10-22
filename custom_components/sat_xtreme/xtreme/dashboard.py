"""SAT-xtreme dashboard: built from the entities of this SAT entry, looked up in the entity registry.

The entity IDs are resolved from the unique IDs, so the dashboard works whatever the entities are called,
and cards of features that are off are left out. Creating a dashboard from an integration is not an
official Home Assistant API; when it fails, the configuration is shown in a notification to paste by hand.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import logging
from typing import Any, Optional

import yaml
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry, issue_registry
from homeassistant.helpers.storage import Store

from ..const import CONF_DEVICE, CONF_MODE, CONF_NAME, DOMAIN, MODE_MQTT_OPENTHERM

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


# Sensors of the OpenTherm Gateway itself (MQTT discovery of the OTGW firmware). They usually have a long
# history and the real burner start counter of the boiler, so they are preferred over SAT's own sensors.
# key -> (domain, label); the unique ID is "<device>-pic_<label>" (firmware 2.x) or "<device>-<label>" (older).
GATEWAY_ENTITIES: dict[str, tuple[str, str]] = {
    "setpoint": ("sensor", "TSet"),
    "flow": ("sensor", "Tboiler"),
    "modulation": ("sensor", "RelModLevel"),
    "burner_starts": ("sensor", "BurnerStarts"),
    "flame": ("binary_sensor", "flame"),
    "heating_demand": ("binary_sensor", "ch_enable"),
    "hot_water": ("binary_sensor", "domestichotwater"),
}


def _gateway_entities(hass: HomeAssistant, config_entry: ConfigEntry) -> dict[str, str]:
    """Return the entity IDs of the OpenTherm Gateway's own sensors that exist, by key."""
    if config_entry.data.get(CONF_MODE) != MODE_MQTT_OPENTHERM or not (device := config_entry.data.get(CONF_DEVICE)):
        return {}

    registry = entity_registry.async_get(hass)
    found = {}

    for key, (domain, label) in GATEWAY_ENTITIES.items():
        for unique_id in (f"{device}-pic_{label}", f"{device}-{label}", f"{device}_{label}"):
            if (entity_id := registry.async_get_entity_id(domain, "mqtt", unique_id)) is not None:
                found[key] = entity_id
                break

    return found


def resolve_entities(hass: HomeAssistant, config_entry: ConfigEntry) -> dict[str, str]:
    """Return the entity IDs to use, by key: the gateway's own sensors where they exist, otherwise SAT's."""
    registry = entity_registry.async_get(hass)
    name = str(config_entry.data.get(CONF_NAME)).lower()
    found = {}

    for key, (domain, suffix) in ENTITIES.items():
        unique_id = name if suffix is None else f"{name}-{suffix}"
        if (entity_id := registry.async_get_entity_id(domain, DOMAIN, unique_id)) is not None:
            found[key] = entity_id

    found.update(_gateway_entities(hass, config_entry))
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


def _fingerprint(config: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def _store(hass: HomeAssistant, config_entry: ConfigEntry) -> Store:
    # Remembers the fingerprint of the dashboard SAT-xtreme built, to tell whether the user changed it
    return Store(hass, 1, f"sat_xtreme_dashboard_{config_entry.entry_id}")


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

    await _store(hass, config_entry).async_save({"fingerprint": _fingerprint(config)})
    issue_registry.async_delete_issue(hass, DOMAIN, f"create_dashboard_{config_entry.entry_id}")
    issue_registry.async_delete_issue(hass, DOMAIN, f"update_dashboard_{config_entry.entry_id}")
    _LOGGER.info("SAT-xtreme: dashboard '%s' created or updated with %d cards.", TITLE, len(config["views"][0]["cards"]))
    return True


async def async_maintain_dashboard(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Offer the dashboard when it does not exist, and keep it up to date when it does.

    The dashboard is rebuilt automatically only when it is still exactly as SAT-xtreme built it; when the
    user changed it, a repair offers the rebuild instead, so their changes are never lost silently.
    """
    entry_id = config_entry.entry_id

    try:
        if not dashboard_exists(hass):
            issue_registry.async_create_issue(
                hass, DOMAIN, f"create_dashboard_{entry_id}", is_fixable=True, severity=issue_registry.IssueSeverity.WARNING,
                translation_key="create_dashboard", data={"entry_id": entry_id},
            )
            return

        issue_registry.async_delete_issue(hass, DOMAIN, f"create_dashboard_{entry_id}")

        from homeassistant.components.lovelace.const import LOVELACE_DATA

        current = await hass.data[LOVELACE_DATA].dashboards[URL_PATH].async_load(False)
        wanted = build_dashboard(resolve_entities(hass, config_entry))

        if _fingerprint(current) == _fingerprint(wanted):
            issue_registry.async_delete_issue(hass, DOMAIN, f"update_dashboard_{entry_id}")
            return

        stored = await _store(hass, config_entry).async_load() or {}
        if stored.get("fingerprint") == _fingerprint(current):
            _LOGGER.info("SAT-xtreme: the dashboard is unchanged since it was built, updating it to the current features.")
            await async_create_dashboard(hass, config_entry)
            return

        issue_registry.async_create_issue(
            hass, DOMAIN, f"update_dashboard_{entry_id}", is_fixable=True, severity=issue_registry.IssueSeverity.WARNING,
            translation_key="update_dashboard", data={"entry_id": entry_id},
        )
    except Exception as exception:
        _LOGGER.debug("SAT-xtreme: could not check the dashboard (%s).", exception)
