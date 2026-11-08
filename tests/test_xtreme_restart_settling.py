"""A restart: no burn before the flow temperature is known, and sensors coming online don't kick the derivative."""
from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.sat_xtreme as sat_xtreme
from custom_components.sat_xtreme.climate import SatClimate
from custom_components.sat_xtreme.const import *
from custom_components.sat_xtreme.coordinator import DeviceState, SatDataUpdateCoordinator
from custom_components.sat_xtreme.errors import Error
from custom_components.sat_xtreme.mqtt.ems import SatEmsMqttCoordinator
from custom_components.sat_xtreme.mqtt.opentherm import SatOpenThermMqttCoordinator
from custom_components.sat_xtreme.pid import PID
from tests.fake_coordinator import SatFakeCoordinator
from tests.loop_harness import CommandLog, run_loops
from tests.xtreme_helpers import MINIMUM_SETPOINT_VALUE, Clock, parameters

SENSOR = "sensor.test_inside_sensor"


@pytest.fixture
def awaiting():
    with patch.object(SatFakeCoordinator, "awaits_boiler_temperature", new_callable=PropertyMock, return_value=True, create=True):
        yield


async def _heat(climate: SatClimate) -> None:
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)


# Waiting for the flow temperature

@pytest.mark.parametrize("coordinator_class", [SatOpenThermMqttCoordinator, SatEmsMqttCoordinator])
def test_gateways_over_mqtt_wait_for_the_flow(coordinator_class: type) -> None:
    assert coordinator_class.awaits_boiler_temperature.fget(None) is True


@pytest.mark.parametrize("module", ["serial", "esphome"])
def test_the_other_gateways_with_a_live_flow_wait_for_it(module: str) -> None:
    # Their libraries are not always installed in the tests, so read the source
    source = (Path(sat_xtreme.__file__).parent / module / "__init__.py").read_text()

    assert "def awaits_boiler_temperature(self) -> bool:\n        return True" in source


def test_other_coordinators_do_not_wait() -> None:
    assert SatDataUpdateCoordinator.awaits_boiler_temperature.fget(None) is False


@pytest.mark.parametrize(*parameters())
async def test_no_heating_demand_while_the_flow_is_unknown(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, awaiting) -> None:
    await _heat(climate)

    with CommandLog(coordinator) as log:
        await run_loops(climate, 3)

    # The setpoint keeps going out, so SAT stays in control and the gateway is asked for the flow
    assert log.of("setpoint") == [MINIMUM_SETPOINT] * 3
    assert DeviceState.ON not in log.of("heater")
    assert climate.setpoint == MINIMUM_SETPOINT


@pytest.mark.parametrize(*parameters())
async def test_the_control_starts_when_the_flow_arrives(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, awaiting) -> None:
    await _heat(climate)
    await run_loops(climate, 2)

    await coordinator.async_set_boiler_temperature(33.0)

    with CommandLog(coordinator) as log:
        await run_loops(climate, 1)

    # The first run with a flow is a PWM block on the OPV, not a setpoint below it
    assert log.of("setpoint") == [MINIMUM_SETPOINT_VALUE]
    assert log.of("heater") == [DeviceState.ON]


@pytest.mark.parametrize(*parameters())
async def test_the_wait_ends_when_the_flow_never_arrives(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, awaiting) -> None:
    await _heat(climate)
    climate._started_at -= BOILER_TEMPERATURE_WAIT_SECONDS + 1

    with CommandLog(coordinator) as log:
        await run_loops(climate, 1)

    assert log.of("setpoint") != [MINIMUM_SETPOINT]


@pytest.mark.parametrize(*parameters())
async def test_without_a_flow_to_wait_for_nothing_changes(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator) -> None:
    await _heat(climate)

    with CommandLog(coordinator) as log:
        await run_loops(climate, 1)

    assert log.of("setpoint") != [MINIMUM_SETPOINT]


# The derivative while sensors come online

@pytest.fixture
def clock():
    clock = Clock()
    with patch("custom_components.sat_xtreme.pid.monotonic", clock), patch("custom_components.sat_xtreme.helpers.monotonic", clock):
        yield clock


def _pid() -> PID:
    # The gains and sample time of the measured restart
    return PID(heating_system=HEATING_SYSTEM_RADIATORS, automatic_gain_value=1.0, heating_curve_coefficient=1.0,
               derivative_time_weight=1.0, kp=20.9, ki=0.0, kd=12308.8, automatic_gains=False, sample_time_limit=60)


def _sensors_come_online(pid: PID, clock: Clock) -> None:
    """The median of several sensors: the error moves from -0.45 to 0.1 in the minute after the restart."""
    clock.now += 61
    pid.update(Error(SENSOR, -0.45), heating_curve_value=31.4, boiler_temperature=40.0)
    clock.now += 67
    pid.update(Error(SENSOR, 0.1), heating_curve_value=31.4, boiler_temperature=40.0)


def test_sensors_coming_online_kick_the_derivative_without_the_hold(clock: Clock) -> None:
    pid = _pid()

    _sensors_come_online(pid, clock)

    assert pid.derivative == pytest.approx(48.5, abs=0.5)


def test_sensors_coming_online_do_not_kick_the_derivative_during_the_hold(clock: Clock) -> None:
    pid = _pid()
    pid.hold_derivative(PID_SETTLE_SECONDS)

    _sensors_come_online(pid, clock)

    assert pid.derivative == 0


def test_the_proportional_keeps_working_during_the_hold(clock: Clock) -> None:
    pid = _pid()
    pid.hold_derivative(PID_SETTLE_SECONDS)

    _sensors_come_online(pid, clock)

    assert pid.proportional == pytest.approx(2.09, abs=0.01)


def test_the_derivative_works_again_after_the_hold(clock: Clock) -> None:
    pid = _pid()
    pid.hold_derivative(PID_SETTLE_SECONDS)
    _sensors_come_online(pid, clock)

    # The first step leaves the deadband, the second counts for the derivative
    clock.now += PID_SETTLE_SECONDS
    pid.update(Error(SENSOR, 0.5), heating_curve_value=31.4, boiler_temperature=40.0)
    clock.now += 61
    pid.update(Error(SENSOR, 1.0), heating_curve_value=31.4, boiler_temperature=40.0)

    assert pid.derivative > 0


def test_a_reset_does_not_end_the_hold(clock: Clock) -> None:
    pid = _pid()
    pid.hold_derivative(PID_SETTLE_SECONDS)

    pid.reset()
    _sensors_come_online(pid, clock)

    assert pid.derivative == 0


@pytest.mark.parametrize(*parameters())
async def test_the_climate_holds_the_derivative_at_the_start(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate) -> None:
    assert climate.pid._derivative_hold_until is not None
