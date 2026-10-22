"""Tests for the SAT Xtreme dashboard that SAT-xtreme builds from its own entities (4.2.1-xtreme.15)."""
from unittest.mock import patch

import pytest
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.sat_xtreme.xtreme.dashboard as dashboard
from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.fake import SatFakeCoordinator
from tests.xtreme_helpers import parameters


def _entity_ids(node) -> set[str]:
    found = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("entity", "entity_id") and isinstance(value, str):
                found.add(value)
            else:
                found |= _entity_ids(value)
    elif isinstance(node, list):
        for value in node:
            found |= _entity_ids(value)
    return found


def test_builder_leaves_out_cards_without_entities():
    config = dashboard.build_dashboard({"climate": "climate.home", "flow": "sensor.flow"})
    cards = config["views"][0]["cards"]

    assert config["title"] == "SAT Xtreme"
    assert _entity_ids(config) == {"climate.home", "sensor.flow"}
    assert not any(card.get("title") == "Learned OPV" for stack in cards for card in stack.get("cards", []))


def test_builder_uses_the_given_entity_ids():
    entities = {key: f"{domain}.custom_{key}" for key, (domain, _suffix) in dashboard.ENTITIES.items()}

    config = dashboard.build_dashboard(entities)

    assert _entity_ids(config) == set(entities.values())


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_LEARNED_OPV: "learn", CONF_XTREME_CALIBRATION: True}))
async def test_entities_are_found_in_the_registry(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await hass.async_block_till_done()

    entities = dashboard.resolve_entities(hass, entry)

    assert entities["climate"] == climate.entity_id
    for key in ("flow", "setpoint", "modulation", "burner_starts", "pid", "learned_opv", "calibration", "flame", "hot_water", "heating_demand", "calibration_start", "calibration_stop"):
        assert key in entities, key

    # Features that are off have no entities and no cards
    assert "burn_time" not in entities


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_LEARNED_OPV: "learn"}))
async def test_dashboard_is_created_in_the_sidebar(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    assert await async_setup_component(hass, "lovelace", {})
    await hass.async_block_till_done()

    assert await dashboard.async_create_dashboard(hass, entry)

    store = hass.data[LOVELACE_DATA].dashboards[dashboard.URL_PATH]
    config = await store.async_load(False)
    assert config["title"] == "SAT Xtreme"
    assert climate.entity_id in _entity_ids(config)

    # Rebuilding keeps one dashboard
    assert await dashboard.async_create_dashboard(hass, entry)
    assert dashboard.URL_PATH in hass.data[LOVELACE_DATA].dashboards


@pytest.mark.parametrize(*parameters())
async def test_falls_back_to_a_notification(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    with patch.object(dashboard, "_dashboards_collection", side_effect=RuntimeError("no access")), \
            patch.object(dashboard.persistent_notification, "async_create") as notification:
        assert not await dashboard.async_create_dashboard(hass, entry)

    notification.assert_called_once()
    assert "Raw configuration editor" in notification.call_args.args[1]


@pytest.mark.parametrize(*parameters())
async def test_dashboard_is_offered_as_a_repair(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await hass.async_block_till_done()

    issue = issue_registry.async_get(hass).async_get_issue(DOMAIN, f"create_dashboard_{entry.entry_id}")
    assert issue is not None and issue.is_fixable

    assert await async_setup_component(hass, "lovelace", {})
    from custom_components.sat_xtreme.repairs import async_create_fix_flow

    flow = await async_create_fix_flow(hass, issue.issue_id, issue.data)
    flow.hass = hass
    flow.handler = DOMAIN
    flow.issue_id = issue.issue_id
    result = await flow.async_step_confirm({})

    assert result["type"] == "create_entry"
    assert dashboard.URL_PATH in hass.data[LOVELACE_DATA].dashboards
    assert issue_registry.async_get(hass).async_get_issue(DOMAIN, issue.issue_id) is None


@pytest.mark.parametrize(*parameters())
async def test_burner_starts_are_counted(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    from custom_components.sat_xtreme.coordinator import DeviceState

    before = coordinator.flame_start_count
    for _ in range(3):
        await coordinator.async_set_heater_state(DeviceState.ON)
        coordinator._flame.update(boiler_state=coordinator.boiler)
        await coordinator.async_set_heater_state(DeviceState.OFF)
        coordinator._flame.update(boiler_state=coordinator.boiler)

    assert coordinator.flame_start_count == before + 3


async def test_gateway_sensors_are_preferred(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry

    gateway_entry = MockConfigEntry(domain=DOMAIN, data={CONF_MODE: MODE_MQTT_OPENTHERM, CONF_DEVICE: "otgw-ABC123", CONF_NAME: "Home"})
    registry = entity_registry.async_get(hass)
    registry.async_get_or_create("sensor", "mqtt", "otgw-ABC123-pic_TSet", suggested_object_id="gateway_tset")
    registry.async_get_or_create("sensor", "mqtt", "otgw-ABC123-BurnerStarts", suggested_object_id="gateway_starts")
    registry.async_get_or_create("binary_sensor", "mqtt", "otgw-ABC123-pic_flame", suggested_object_id="gateway_flame")
    registry.async_get_or_create("sensor", DOMAIN, "home-xtreme-boiler-flow", suggested_object_id="sat_flow")
    registry.async_get_or_create("sensor", DOMAIN, "home-xtreme-control-setpoint", suggested_object_id="sat_setpoint")

    entities = dashboard.resolve_entities(hass, gateway_entry)

    assert entities["setpoint"] == "sensor.gateway_tset"
    assert entities["burner_starts"] == "sensor.gateway_starts"
    assert entities["flame"] == "binary_sensor.gateway_flame"
    # No gateway sensor for the flow: SAT's own sensor is used
    assert entities["flow"] == "sensor.sat_flow"


@pytest.mark.parametrize(*parameters())
async def test_no_gateway_sensors_for_other_gateways(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    assert dashboard._gateway_entities(hass, entry) == {}


async def _setup_dashboard(hass, entry):
    assert await async_setup_component(hass, "lovelace", {})
    await hass.async_block_till_done()
    assert await dashboard.async_create_dashboard(hass, entry)
    return hass.data[LOVELACE_DATA].dashboards[dashboard.URL_PATH]


@pytest.mark.parametrize(*parameters())
async def test_unchanged_dashboard_follows_the_features(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    store = await _setup_dashboard(hass, entry)

    # A feature was turned on: a new entity exists
    extra = {**dashboard.resolve_entities(hass, entry), "learned_opv": "sensor.new_learned_opv"}
    with patch.object(dashboard, "resolve_entities", return_value=extra):
        await dashboard.async_maintain_dashboard(hass, entry)

    assert "sensor.new_learned_opv" in _entity_ids(await store.async_load(False))
    assert issue_registry.async_get(hass).async_get_issue(DOMAIN, f"update_dashboard_{entry.entry_id}") is None


@pytest.mark.parametrize(*parameters())
async def test_edited_dashboard_is_not_overwritten(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    store = await _setup_dashboard(hass, entry)

    # The user changed the dashboard
    edited = await store.async_load(False)
    edited = {**edited, "title": "My heating"}
    await store.async_save(edited)

    extra = {**dashboard.resolve_entities(hass, entry), "learned_opv": "sensor.new_learned_opv"}
    with patch.object(dashboard, "resolve_entities", return_value=extra):
        await dashboard.async_maintain_dashboard(hass, entry)

        assert (await store.async_load(False))["title"] == "My heating"
        issue = issue_registry.async_get(hass).async_get_issue(DOMAIN, f"update_dashboard_{entry.entry_id}")
        assert issue is not None and issue.is_fixable

        # The repair rebuilds it after a click
        from custom_components.sat_xtreme.repairs import async_create_fix_flow

        flow = await async_create_fix_flow(hass, issue.issue_id, issue.data)
        flow.hass = hass
        flow.handler = DOMAIN
        flow.issue_id = issue.issue_id
        await flow.async_step_confirm({})

    assert (await store.async_load(False))["title"] == "SAT Xtreme"
    assert issue_registry.async_get(hass).async_get_issue(DOMAIN, f"update_dashboard_{entry.entry_id}") is None


@pytest.mark.parametrize(*parameters())
async def test_up_to_date_dashboard_is_left_alone(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    store = await _setup_dashboard(hass, entry)
    before = await store.async_load(False)

    with patch.object(dashboard, "async_create_dashboard") as rebuild:
        await dashboard.async_maintain_dashboard(hass, entry)

    rebuild.assert_not_called()
    assert await store.async_load(False) == before
