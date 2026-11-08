"""The last step of the setup wizard: the choice of the fork options."""
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.config_flow import SatFlowHandler
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.xtreme.profile import XtremeProfile, recommended_options


def _flow(hass: HomeAssistant, mode: str = MODE_MQTT_OPENTHERM) -> SatFlowHandler:
    flow = SatFlowHandler()
    flow.hass = hass
    flow.handler = DOMAIN
    flow.flow_id = "test"
    flow.context = {"source": "user"}
    flow.data = {CONF_NAME: "Test", CONF_MODE: mode, CONF_DEVICE: "otgw"}
    return flow


async def test_a_new_installation_chooses_the_fork_options(hass: HomeAssistant) -> None:
    result = await _flow(hass).async_step_finish()

    assert result["type"] == "menu"
    assert result["step_id"] == "xtreme_start"
    assert result["menu_options"] == ["xtreme_recommended", "xtreme_official", "xtreme_choose"]


async def test_like_the_official_sat_adds_no_options(hass: HomeAssistant) -> None:
    flow = _flow(hass)
    flow.data[CONF_AUTOMATIC_GAINS] = True

    result = await flow.async_step_xtreme_official()

    assert result["type"] == "create_entry"
    assert result["options"] == {CONF_AUTOMATIC_GAINS: True}
    assert not XtremeProfile.from_options(result["options"]).enabled


async def test_recommended_turns_on_the_safe_options(hass: HomeAssistant) -> None:
    result = await _flow(hass).async_step_xtreme_recommended()

    assert result["type"] == "create_entry"
    profile = XtremeProfile.from_options(result["options"])
    assert profile.cycle_tracking and profile.setpoint_chain and profile.stale_sensors and profile.handover_on_off

    # Options that change how the boiler runs, or need its values, stay off
    assert not profile.boiler_timing and not profile.prime_setpoint and not profile.ignore_modulation_limit
    assert profile.learned_opv == "off" and profile.pwm_hysteresis == 0


@pytest.mark.parametrize("mode, handover, chain", [
    (MODE_MQTT_OPENTHERM, True, True),
    (MODE_MQTT_EMS, False, True),
    (MODE_ESPHOME, False, True),
    (MODE_SERIAL, False, True),
    (MODE_SWITCH, False, False),
])
def test_the_recommended_options_follow_the_gateway(mode: str, handover: bool, chain: bool) -> None:
    options = recommended_options(mode)

    assert (CONF_XTREME_HANDOVER_ON_OFF in options) is handover
    assert (CONF_XTREME_SETPOINT_CHAIN in options) is chain
    assert options[CONF_XTREME_CYCLE_TRACKING] and options[CONF_XTREME_STALE_SENSORS]


async def test_choose_myself_offers_the_same_options_all_off(hass: HomeAssistant) -> None:
    flow = _flow(hass, MODE_SWITCH)

    result = await flow.async_step_xtreme_choose()

    assert result["step_id"] == "xtreme_choose"
    assert {str(key) for key in result["data_schema"].schema} == set(recommended_options(MODE_SWITCH))
    assert all(key.default() is False for key in result["data_schema"].schema)

    result = await flow.async_step_xtreme_choose({CONF_XTREME_CYCLE_TRACKING: True, CONF_XTREME_STALE_SENSORS: False})

    assert result["type"] == "create_entry"
    assert result["options"] == {CONF_XTREME_CYCLE_TRACKING: True, CONF_XTREME_STALE_SENSORS: False}


async def test_the_step_is_not_shown_again_after_the_choice(hass: HomeAssistant) -> None:
    flow = _flow(hass)
    flow.xtreme_options = {}

    assert (await flow.async_step_finish())["type"] == "create_entry"


async def test_reconfigure_skips_the_step_and_keeps_the_options(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_NAME: "Test", CONF_MODE: MODE_MQTT_OPENTHERM}, options={CONF_XTREME_CYCLE_TRACKING: True})
    entry.add_to_hass(hass)
    flow = _flow(hass)
    flow.context = {"source": "reconfigure", "entry_id": entry.entry_id}
    flow.config_entry = entry

    result = await flow.async_step_finish()

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert entry.options[CONF_XTREME_CYCLE_TRACKING] is True


async def test_the_route_through_the_calibration_reaches_the_step(hass: HomeAssistant) -> None:
    flow = _flow(hass)
    flow.data[CONF_MODE] = MODE_SIMULATOR

    result = await flow.async_step_overshoot_protection({CONF_MINIMUM_SETPOINT: 46})

    assert result["type"] == "menu"
    assert result["step_id"] == "xtreme_start"


@pytest.mark.parametrize("next_step, stale", [("xtreme_recommended", True), ("xtreme_official", None)])
async def test_the_menu_works_through_home_assistant(hass: HomeAssistant, next_step: str, stale) -> None:
    async def jump_to_the_end(flow, _user_input=None):
        flow.data = {CONF_NAME: "Test", CONF_MODE: MODE_SIMULATOR, CONF_DEVICE: "simulator"}
        return await flow.async_step_finish()

    with patch.object(SatFlowHandler, "async_step_user", jump_to_the_end), \
            patch("custom_components.sat_xtreme.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        assert result["step_id"] == "xtreme_start"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": next_step})
        await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert result["result"].options.get(CONF_XTREME_STALE_SENSORS) is stale
