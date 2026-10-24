"""Tests for 4.2.1+xtreme.9: boiler preset, handover to the thermostat, platform order and minimum setpoint storage."""
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from tests.fake_coordinator import SatFakeCoordinator
from custom_components.sat_xtreme.manufacturers.intergas import Intergas
from custom_components.sat_xtreme.manufacturers.remeha import Remeha
from custom_components.sat_xtreme.mqtt.opentherm import SatOpenThermMqttCoordinator
from custom_components.sat_xtreme.xtreme.profile import BOILER_PRESETS, apply_boiler_preset
from tests.const import DEFAULT_USER_DATA
from tests.xtreme_helpers import parameters, xtreme_profile_input

PRESET = "intergas_xtreme_30_2024"


def test_choosing_a_preset_fills_in_its_values():
    previous = {CONF_XTREME_BOILER_PRESET: BOILER_PRESET_CUSTOM}
    submitted = {CONF_XTREME_BOILER_PRESET: PRESET, CONF_XTREME_BOILER_MAXIMUM_POWER: 24.0, CONF_XTREME_BOILER_MINIMUM_POWER: 5.0, CONF_XTREME_ANTI_CYCLING_TIME: 600}

    result = apply_boiler_preset(previous, submitted)

    assert result[CONF_XTREME_BOILER_PRESET] == PRESET
    assert result[CONF_XTREME_BOILER_MAXIMUM_POWER] == 19.5
    assert result[CONF_XTREME_BOILER_MINIMUM_POWER] == 3.9
    assert result[CONF_XTREME_ANTI_CYCLING_TIME] == 300


def test_changing_a_value_by_hand_falls_back_to_custom():
    previous = {CONF_XTREME_BOILER_PRESET: PRESET}
    submitted = {CONF_XTREME_BOILER_PRESET: PRESET, CONF_XTREME_BOILER_MAXIMUM_POWER: 19.5, CONF_XTREME_BOILER_MINIMUM_POWER: 3.9, CONF_XTREME_ANTI_CYCLING_TIME: 420}

    result = apply_boiler_preset(previous, submitted)

    assert result[CONF_XTREME_BOILER_PRESET] == BOILER_PRESET_CUSTOM
    assert result[CONF_XTREME_ANTI_CYCLING_TIME] == 420


def test_unchanged_preset_keeps_its_values():
    previous = {CONF_XTREME_BOILER_PRESET: PRESET}
    submitted = {CONF_XTREME_BOILER_PRESET: PRESET, CONF_XTREME_BOILER_MAXIMUM_POWER: 19.5, CONF_XTREME_BOILER_MINIMUM_POWER: 3.9, CONF_XTREME_ANTI_CYCLING_TIME: 300.0}

    assert apply_boiler_preset(previous, submitted)[CONF_XTREME_BOILER_PRESET] == PRESET


def test_custom_and_unknown_presets_keep_the_values():
    submitted = {CONF_XTREME_BOILER_PRESET: "unknown", CONF_XTREME_BOILER_MAXIMUM_POWER: 24.0}

    result = apply_boiler_preset({}, submitted)

    assert result[CONF_XTREME_BOILER_PRESET] == BOILER_PRESET_CUSTOM
    assert result[CONF_XTREME_BOILER_MAXIMUM_POWER] == 24.0


def test_presets_only_contain_numbers():
    for preset in BOILER_PRESETS.values():
        assert preset.minimum_power < preset.maximum_power
        assert preset.anti_cycling_time > 0
        assert preset.source


@pytest.mark.parametrize(*parameters())
async def test_preset_in_the_options_flow(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "xtreme_profile"})

    boiler = result["data_schema"].schema["boiler"].schema
    defaults = {str(key): key.default() for key in boiler.schema}
    assert defaults[CONF_XTREME_BOILER_PRESET] == BOILER_PRESET_CUSTOM

    result = await hass.config_entries.options.async_configure(result["flow_id"], xtreme_profile_input(**{
        CONF_XTREME_BOILER_PRESET: PRESET,
        CONF_XTREME_BOILER_MAXIMUM_POWER: 30.0,
    }))
    await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert entry.options[CONF_XTREME_BOILER_PRESET] == PRESET
    assert entry.options[CONF_XTREME_BOILER_MAXIMUM_POWER] == 19.5


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_BOILER_PRESET: PRESET}))
async def test_preset_for_another_manufacturer_is_reported(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, caplog) -> None:
    with patch.object(SatFakeCoordinator, "manufacturer", new_callable=PropertyMock, return_value=Remeha()):
        climate._check_boiler_preset()
        climate._check_boiler_preset()

    warnings = [record for record in caplog.records if "boiler preset" in record.getMessage() and record.levelname == "WARNING"]
    assert len(warnings) == 1


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_BOILER_PRESET: PRESET}))
async def test_preset_for_the_detected_manufacturer_is_fine(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, caplog) -> None:
    with patch.object(SatFakeCoordinator, "manufacturer", new_callable=PropertyMock, return_value=Intergas()):
        climate._check_boiler_preset()

    assert not [record for record in caplog.records if "boiler preset" in record.getMessage() and record.levelname == "WARNING"]


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_HANDOVER_ON_OFF: True}))
async def test_turning_off_hands_over_to_the_thermostat(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    with patch.object(SatFakeCoordinator, "supports_setpoint_release", new_callable=PropertyMock, return_value=True), \
            patch.object(SatFakeCoordinator, "async_release_control_setpoint", new_callable=AsyncMock) as release:
        await climate.async_set_hvac_mode(HVACMode.HEAT)
        release.assert_not_called()

        await climate.async_set_hvac_mode(HVACMode.OFF)
        release.assert_called_once()


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_HANDOVER_ON_OFF: False}))
async def test_no_handover_without_the_switch(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    with patch.object(SatFakeCoordinator, "supports_setpoint_release", new_callable=PropertyMock, return_value=True), \
            patch.object(SatFakeCoordinator, "async_release_control_setpoint", new_callable=AsyncMock) as release:
        await climate.async_set_hvac_mode(HVACMode.OFF)

    release.assert_not_called()


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_HANDOVER_ON_OFF: True}))
async def test_no_handover_on_devices_without_release(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    with patch.object(SatFakeCoordinator, "async_release_control_setpoint", new_callable=AsyncMock) as release:
        await climate.async_set_hvac_mode(HVACMode.OFF)

    assert not coordinator.supports_setpoint_release
    release.assert_not_called()


async def test_opentherm_gateway_releases_with_cs_0(hass: HomeAssistant) -> None:
    coordinator = SatOpenThermMqttCoordinator(hass, device_id="otgw", config_data={CONF_MQTT_TOPIC: "OTGW"})

    with patch.object(SatOpenThermMqttCoordinator, "_publish_command", new_callable=AsyncMock) as publish:
        await coordinator.async_release_control_setpoint()

    assert coordinator.supports_setpoint_release
    publish.assert_called_once_with("CS=0")


@pytest.mark.parametrize(*parameters())
async def test_all_platforms_get_their_entities(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await hass.async_block_till_done()
    registry = entity_registry.async_get(hass)

    assert registry.async_get_entity_id("sensor", DOMAIN, "test-heating-curve") is not None
    assert registry.async_get_entity_id("binary_sensor", DOMAIN, "test-flame-health") is not None


async def test_minimum_setpoint_storage_is_loaded(hass: HomeAssistant, hass_storage) -> None:
    hass_storage["minimum_setpoint"] = {"version": 1, "key": "minimum_setpoint", "data": {"base_return_temperature": 33.5}}

    sat_entry = MockConfigEntry(domain=DOMAIN, data=DEFAULT_USER_DATA)
    await hass.config_entries.async_add(sat_entry)
    await hass.async_block_till_done()

    climate = hass.data[DOMAIN][sat_entry.entry_id][CLIMATE]
    assert climate.minimum_setpoint._base_return_temperature.value == 33.5


@pytest.mark.parametrize(*parameters())
async def test_xtreme_profile_page_has_three_sections(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "xtreme_profile"})

    assert [str(key) for key in result["data_schema"].schema] == ["thermostat", "boiler", "learning"]

    # The sections are stored as flat options
    result = await hass.config_entries.options.async_configure(result["flow_id"], xtreme_profile_input(**{CONF_XTREME_HANDOVER_ON_OFF: True, CONF_XTREME_LEARNED_OPV: "learn"}))
    assert result["type"] == "create_entry"
    assert entry.options[CONF_XTREME_HANDOVER_ON_OFF] is True
    assert entry.options[CONF_XTREME_LEARNED_OPV] == "learn"
    assert "thermostat" not in entry.options


def test_every_fork_option_is_explained_in_english_and_dutch():
    import json
    from pathlib import Path

    folder = Path(__file__).parent.parent / "custom_components" / "sat_xtreme" / "translations"
    for language in ("en", "nl"):
        steps = json.loads((folder / f"{language}.json").read_text())["options"]["step"]

        for section in steps["xtreme_profile"]["sections"].values():
            assert section["name"] and section["description"]
            assert set(section["data"]) == set(section["data_description"]), (language, section["name"])

        for step in ("pid_settings", "manual_gains"):
            assert set(steps[step]["data"]) == set(steps[step]["data_description"]), (language, step)

        assert "Intergas Xtreme boiler" not in steps["xtreme_profile"]["description"]
