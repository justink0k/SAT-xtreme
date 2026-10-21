"""Tests for the Xtreme profile, step 5: the slow calibration of the OPV."""
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sat.climate import SatClimate
from custom_components.sat.const import *
from custom_components.sat.coordinator import DeviceState
from custom_components.sat.fake import SatFakeCoordinator
from custom_components.sat.xtreme_calibration import CalibrationPhase, XtremeCalibration, STEP_INTERVAL_SECONDS
from tests.xtreme_helpers import Clock, parameters

OPTIONS = {CONF_XTREME_CALIBRATION: True, CONF_XTREME_LEARNED_OPV: "learn"}


class _Boiler:
    """A simple boiler model: modulates down to its minimum power and plateaus at its OPV."""

    def __init__(self, coordinator: SatFakeCoordinator, opv: float):
        self.coordinator = coordinator
        self.opv = opv
        self.modulation = 0.0
        self.hot_water = False
        self.shut_off = False

    async def update(self) -> None:
        coordinator = self.coordinator
        setpoint = coordinator.setpoint or MINIMUM_SETPOINT
        demand = coordinator.heater_state_commanded == DeviceState.ON

        if not demand:
            self.shut_off = False

        if not demand or self.shut_off:
            coordinator._device_state = DeviceState.OFF
            self.modulation = 0.0
            await coordinator.async_set_boiler_temperature(35.0)
        elif setpoint >= self.opv + 2:
            coordinator._device_state = DeviceState.ON
            self.modulation = (setpoint - self.opv - 1) * 10
            await coordinator.async_set_boiler_temperature(setpoint)
        elif setpoint > self.opv + 0.5:
            coordinator._device_state = DeviceState.ON
            self.modulation = 0.0
            await coordinator.async_set_boiler_temperature(self.opv)
        else:
            # Minimum power is more than the house takes: the boiler overshoots and switches off
            coordinator._device_state = DeviceState.OFF
            self.modulation = 0.0
            self.shut_off = True

        coordinator._flame.update(boiler_state=coordinator.boiler)


@pytest.fixture
def clock():
    clock = Clock()

    with patch("custom_components.sat.xtreme_calibration.monotonic", clock), \
            patch("custom_components.sat.flame.monotonic", clock), \
            patch("custom_components.sat.coordinator.monotonic", clock), \
            patch.object(XtremeCalibration, "_async_run", new=AsyncMock()):
        yield clock


async def _run(calibration: XtremeCalibration, boiler: _Boiler, clock: Clock, seconds: float) -> None:
    with patch.object(SatFakeCoordinator, "relative_modulation_value", new_callable=PropertyMock, side_effect=lambda: boiler.modulation), \
            patch.object(SatFakeCoordinator, "hot_water_active", new_callable=PropertyMock, side_effect=lambda: boiler.hot_water):
        for _ in range(int(seconds // STEP_INTERVAL_SECONDS)):
            if not calibration.active:
                return

            await calibration.async_step()
            await boiler.update()
            clock.now += STEP_INTERVAL_SECONDS


async def _start(climate: SatClimate, target: float = 20.5) -> XtremeCalibration:
    await climate.async_set_target_temperature(target)
    await climate.async_set_hvac_mode(HVACMode.HEAT)

    assert await climate.xtreme_calibration.async_start()
    return climate.xtreme_calibration


@pytest.mark.parametrize(*parameters(**OPTIONS))
async def test_calibration_finds_the_opv(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, clock: Clock) -> None:
    boiler = _Boiler(coordinator, opv=45.3)
    calibration = await _start(climate)

    await _run(calibration, boiler, clock, 10 * 3600)

    assert calibration.phase == CalibrationPhase.SUCCEEDED
    report = calibration.attributes["report"]
    assert report["result"] == 45.3
    assert report["spread"] == 0
    assert len(report["rounds"]) == 5
    assert all(calibration_round["result"] == "plateau" for calibration_round in report["rounds"])

    # The result seeds the self-learning OPV
    assert climate.learned_opv.estimate == 45.3
    assert climate.learned_opv.attributes["source"] == "calibration"

    # Control is handed back to SAT
    assert not calibration.active


@pytest.mark.parametrize(*parameters(**OPTIONS))
async def test_shut_off_at_minimum_modulation_is_a_measurement(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, clock: Clock) -> None:
    # The OPV lies between two setpoint steps: the boiler shuts off at minimum modulation
    boiler = _Boiler(coordinator, opv=46.0)
    calibration = await _start(climate)

    await _run(calibration, boiler, clock, 10 * 3600)

    assert calibration.phase == CalibrationPhase.SUCCEEDED
    results = {calibration_round["result"] for calibration_round in calibration.attributes["report"]["rounds"]}
    assert results <= {"plateau", "shut_off"}


@pytest.mark.parametrize(*parameters(**OPTIONS))
async def test_setpoints_never_exceed_the_maximum(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, clock: Clock) -> None:
    boiler = _Boiler(coordinator, opv=45.3)
    calibration = await _start(climate)
    sent = []

    original = coordinator.async_set_control_setpoint

    async def record(value: float) -> None:
        sent.append(value)
        await original(value)

    with patch.object(coordinator, "async_set_control_setpoint", side_effect=record):
        await _run(calibration, boiler, clock, 2 * 3600)

    assert sent and max(sent) <= 60


@pytest.mark.parametrize(*parameters(**OPTIONS))
async def test_hot_water_discards_the_step(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, clock: Clock) -> None:
    boiler = _Boiler(coordinator, opv=45.3)
    calibration = await _start(climate)

    await _run(calibration, boiler, clock, 600)
    assert calibration.phase == CalibrationPhase.HEATING

    boiler.hot_water = True
    await _run(calibration, boiler, clock, 30)
    assert calibration.phase == CalibrationPhase.PAUSED_HOT_WATER
    assert any("discarded" in step["outcome"] for step in _steps(calibration))

    boiler.hot_water = False
    await _run(calibration, boiler, clock, 30)
    assert calibration.phase in (CalibrationPhase.WAITING, CalibrationPhase.HEATING)


@pytest.mark.parametrize(*parameters(**OPTIONS))
async def test_comfort_limit_pauses_the_calibration(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, clock: Clock) -> None:
    boiler = _Boiler(coordinator, opv=45.3)

    # The room (20.0 °C) is more than 1 °C above the target
    calibration = await _start(climate, target=18.5)
    await _run(calibration, boiler, clock, 60)

    assert calibration.phase == CalibrationPhase.PAUSED_COMFORT
    assert coordinator.heater_state_commanded == DeviceState.OFF

    climate._target_temperature = 20.0
    await _run(calibration, boiler, clock, 30)
    assert calibration.phase in (CalibrationPhase.WAITING, CalibrationPhase.HEATING)


@pytest.mark.parametrize(*parameters(**OPTIONS))
async def test_stop_returns_to_normal_operation(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, clock: Clock) -> None:
    boiler = _Boiler(coordinator, opv=45.3)
    calibration = await _start(climate)
    await _run(calibration, boiler, clock, 600)

    await calibration.async_stop()

    assert calibration.phase == CalibrationPhase.CANCELLED
    assert not calibration.active
    assert calibration.attributes["report"]["outcome"] == "cancelled"
    assert climate.learned_opv.attributes["source"] == "configured"


@pytest.mark.parametrize(*parameters(**OPTIONS))
async def test_turning_the_thermostat_off_stops_the_calibration(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, clock: Clock) -> None:
    boiler = _Boiler(coordinator, opv=45.3)
    calibration = await _start(climate)
    await _run(calibration, boiler, clock, 300)

    await climate.async_set_hvac_mode(HVACMode.OFF)

    assert calibration.phase == CalibrationPhase.CANCELLED


@pytest.mark.parametrize(*parameters(**OPTIONS))
async def test_always_modulating_boiler_fails(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, clock: Clock) -> None:
    boiler = _Boiler(coordinator, opv=30.0)
    calibration = await _start(climate)

    await _run(calibration, boiler, clock, 11 * 3600)

    assert calibration.phase == CalibrationPhase.FAILED
    assert climate.learned_opv.attributes["source"] == "configured"


@pytest.mark.parametrize(*parameters(**OPTIONS))
async def test_unrealistic_round_is_rejected(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, clock: Clock) -> None:
    calibration = await _start(climate)

    await calibration._async_end_round("plateau", 30.0)

    assert calibration.attributes["report"] is None
    assert calibration._rounds[-1].result == "rejected"
    assert calibration.attributes["valid_rounds"] == 0


@pytest.mark.parametrize(*parameters(**OPTIONS))
async def test_normal_control_is_paused_during_calibration(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, clock: Clock) -> None:
    await coordinator.async_set_boiler_temperature(40.0)
    calibration = await _start(climate)
    await coordinator.async_set_control_setpoint(53.0)

    await climate.async_control_heating_loop()

    assert calibration.active
    assert coordinator.setpoint == 53.0


@pytest.mark.parametrize(*parameters(**{CONF_XTREME_CALIBRATION: False}))
async def test_service_requires_the_switch(hass: HomeAssistant, entry: MockConfigEntry, climate: SatClimate, coordinator: SatFakeCoordinator, clock: Clock) -> None:
    await climate.async_set_hvac_mode(HVACMode.HEAT)

    await hass.services.async_call(DOMAIN, SERVICE_START_XTREME_CALIBRATION, {"entity_id": climate.entity_id}, blocking=True)

    assert not climate.xtreme_calibration.active


def _steps(calibration: XtremeCalibration) -> list[dict]:
    return [step.__dict__ if hasattr(step, "__dict__") else {"outcome": step.outcome} for calibration_round in calibration._rounds for step in calibration_round.steps]
