"""PWM hysteresis, an opt-in idea from bellini666/SAT (step 2B)."""
import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.xtreme.profile import XtremeProfile
from tests.xtreme_helpers import parameters, xtreme_profile_input


def _enabled(climate: SatClimate, setpoint: float, status: PWMStatus) -> bool:
    climate._calculated_setpoint = setpoint
    climate.pwm._status = status
    return climate.pulse_width_modulation_enabled


def test_the_hysteresis_is_off_by_default():
    assert XtremeProfile.from_options({}).pwm_hysteresis == 0.0
    assert "pwm_hysteresis (2.0)" in XtremeProfile.from_options({CONF_XTREME_PWM_HYSTERESIS: 2.0}).active_switches


@pytest.mark.parametrize(*parameters(force_pwm=False))
async def test_without_the_hysteresis_pwm_turns_off_right_above_the_minimum(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    minimum = climate._coordinator.minimum_setpoint

    assert _enabled(climate, minimum - 1, PWMStatus.ON)
    assert not _enabled(climate, minimum + 1, PWMStatus.ON)


@pytest.mark.parametrize(*parameters(force_pwm=False, **{CONF_XTREME_PWM_HYSTERESIS: 2.0}))
async def test_running_pwm_stays_on_within_the_hysteresis(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    minimum = climate._coordinator.minimum_setpoint

    # Running (on or off phase): it only turns off once the setpoint clears the minimum by 2 °C
    assert _enabled(climate, minimum + 1, PWMStatus.ON)
    assert _enabled(climate, minimum + 1, PWMStatus.OFF)
    assert not _enabled(climate, minimum + 3, PWMStatus.ON)


@pytest.mark.parametrize(*parameters(force_pwm=False, **{CONF_XTREME_PWM_HYSTERESIS: 2.0}))
async def test_idle_pwm_starts_at_the_minimum_as_before(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    minimum = climate._coordinator.minimum_setpoint

    assert not _enabled(climate, minimum + 1, PWMStatus.IDLE)
    assert _enabled(climate, minimum - 1, PWMStatus.IDLE)


@pytest.mark.parametrize(*parameters())
async def test_the_option_is_stored(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "xtreme_profile"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], xtreme_profile_input(**{CONF_XTREME_PWM_HYSTERESIS: 2.5}))

    assert result["type"] == "create_entry"
    assert entry.options[CONF_XTREME_PWM_HYSTERESIS] == 2.5
