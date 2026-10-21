"""Tests for the PID settings of the fork: gain factor, maximum rise, options pages and labels."""
from unittest.mock import PropertyMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.sat.sensor as sat_sensor
from custom_components.sat.climate import SatClimate
from custom_components.sat.config_flow import SatFlowHandler
from custom_components.sat.const import *
from custom_components.sat.fake import SatFakeCoordinator
from custom_components.sat.pid import PID
from custom_components.sat.xtreme_sensor import FORK_LABEL, SatPidOutputSensor
from tests.xtreme_helpers import parameters


def _pid(gain_factor: float = 1.0, automatic_gains: bool = True, version: int = 3) -> PID:
    pid = PID(
        heating_system=HEATING_SYSTEM_RADIATORS,
        automatic_gain_value=2.0,
        heating_curve_coefficient=2.0,
        derivative_time_weight=2.5,
        kp=45, ki=0.01, kd=6000,
        automatic_gains=automatic_gains,
        version=version,
        gain_factor=gain_factor,
    )
    pid._last_heating_curve_value = 31.0
    return pid


@pytest.mark.parametrize("version", [1, 2, 3])
def test_gain_factor_scales_all_automatic_gains(version: int):
    base = _pid(version=version)
    calm = _pid(gain_factor=0.5, version=version)

    assert calm.kp == pytest.approx(0.5 * base.kp, rel=1e-4)
    assert calm.ki == pytest.approx(0.5 * base.ki, abs=1e-6)
    assert calm.kd == pytest.approx(0.5 * base.kd, rel=1e-4)


def test_gain_factor_one_is_upstream():
    pid = _pid()

    # Version 3 with radiators: kP = coefficient x heating curve / 3
    assert pid.kp == pytest.approx(2.0 * 31.0 / 3, rel=1e-6)
    assert pid.ki == pytest.approx(pid.kp / 8400, rel=1e-3)
    assert pid.kd == pytest.approx(0.07 * 8400 * pid.kp, rel=1e-6)


def test_gain_factor_does_not_touch_manual_gains():
    pid = _pid(gain_factor=0.5, automatic_gains=False)

    assert (pid.kp, pid.ki, pid.kd) == (45.0, 0.01, 6000.0)


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_MAXIMUM_SETPOINT_RISE: 15}))
async def test_maximum_rise_limits_the_requested_setpoint(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    climate.heating_curve._last_heating_curve_value = 31.0

    with patch.object(PID, "output", new_callable=PropertyMock, return_value=22.6):
        assert climate.requested_setpoint == 46.0

    with patch.object(PID, "output", new_callable=PropertyMock, return_value=5.0):
        assert climate.requested_setpoint == 36.0


@pytest.mark.parametrize(*parameters())
async def test_no_maximum_rise_by_default(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    climate.heating_curve._last_heating_curve_value = 31.0

    with patch.object(PID, "output", new_callable=PropertyMock, return_value=22.6):
        assert climate.requested_setpoint == 53.6


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_PID_GAIN_FACTOR: 0.5}))
async def test_gain_factor_reaches_the_climate(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    assert climate.pid.gain_factor == 0.5
    assert climate.extra_state_attributes["xtreme_pid_gain_factor"] == 0.5
    assert climate.extra_state_attributes["automatic_gains"] is True


@pytest.mark.parametrize(*parameters())
async def test_pid_settings_page_with_automatic_gains(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "pid_settings" in result["menu_options"]

    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "pid_settings"})
    assert result["step_id"] == "pid_settings"

    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        CONF_AUTOMATIC_GAINS: True,
        CONF_XTREME_PID_GAIN_FACTOR: 0.7,
        CONF_XTREME_MAXIMUM_SETPOINT_RISE: 12,
    })
    assert result["type"] == "create_entry"
    assert entry.options[CONF_XTREME_PID_GAIN_FACTOR] == 0.7
    assert entry.options[CONF_XTREME_MAXIMUM_SETPOINT_RISE] == 12


@pytest.mark.parametrize(*parameters())
async def test_manual_gains_are_prefilled_with_the_gains_in_use(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    climate.pid._last_heating_curve_value = 31.0
    kp = climate.pid.kp

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "pid_settings"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        CONF_AUTOMATIC_GAINS: False,
        CONF_XTREME_PID_GAIN_FACTOR: 1.0,
        CONF_XTREME_MAXIMUM_SETPOINT_RISE: 0,
    })
    assert result["step_id"] == "manual_gains"

    defaults = {str(key): key.default() for key in result["data_schema"].schema}
    assert float(defaults[CONF_PROPORTIONAL]) == pytest.approx(kp, rel=1e-4)

    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        CONF_PROPORTIONAL: "10", CONF_INTEGRAL: "0.001", CONF_DERIVATIVE: "5000",
    })
    await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert entry.options[CONF_AUTOMATIC_GAINS] is False
    assert entry.options[CONF_PROPORTIONAL] == "10"

    # After the reload SAT uses the manual gains
    new_climate = hass.data[DOMAIN][entry.entry_id][CLIMATE]
    assert new_climate.pid.kp == 10.0


async def test_wizard_choices_are_copied_to_the_options(hass: HomeAssistant) -> None:
    flow = SatFlowHandler()
    flow.hass = hass
    flow.context = {"source": "user"}
    flow.data = {CONF_NAME: "Test", CONF_MODE: MODE_FAKE, CONF_AUTOMATIC_GAINS: False, CONF_PROPORTIONAL: "30", CONF_INTEGRAL: "0", CONF_DERIVATIVE: "4000"}

    result = await flow.async_step_finish()

    assert result["options"][CONF_AUTOMATIC_GAINS] is False
    assert result["options"][CONF_PROPORTIONAL] == "30"


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_LEARNED_OPV: "learn"}))
async def test_fork_entities_are_labelled(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    entities = []
    await sat_sensor.async_setup_entry(hass, entry, lambda new_entities: entities.extend(new_entities))

    fork_entities = [entity for entity in entities if type(entity).__module__.endswith("xtreme_sensor")]
    assert len(fork_entities) == 6
    assert all(entity.name.startswith(FORK_LABEL) for entity in fork_entities)
    assert any(isinstance(entity, SatPidOutputSensor) for entity in fork_entities)
