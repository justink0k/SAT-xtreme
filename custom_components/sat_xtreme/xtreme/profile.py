"""Xtreme profile: opt-in adjustments for an Intergas Xtreme 30 behind an OpenTherm Gateway.

Every adjustment has its own switch in the SAT options (menu "Xtreme profile"). With all switches
off, SAT behaves like upstream. See CHANGES_XTREME.md for details.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from ..const import (
    OPTIONS_DEFAULTS,
    CONF_XTREME_PRIME_SETPOINT,
    CONF_XTREME_BOILER_MAXIMUM_POWER,
    CONF_XTREME_BOILER_MINIMUM_POWER,
    CONF_XTREME_IGNORE_MODULATION_LIMIT,
    CONF_XTREME_BOILER_TIMING,
    CONF_XTREME_ANTI_CYCLING_TIME,
    CONF_XTREME_ANTI_CYCLING_MARGIN,
    CONF_XTREME_MINIMUM_BURN_TIME,
    CONF_XTREME_MINIMUM_DUTY_CYCLE,
    CONF_XTREME_LEARNED_OPV,
    CONF_XTREME_CALIBRATION,
    CONF_XTREME_PID_GAIN_FACTOR,
    CONF_XTREME_MAXIMUM_SETPOINT_RISE,
    CONF_XTREME_BOILER_PRESET,
    CONF_XTREME_HANDOVER_ON_OFF,
    CONF_XTREME_HOT_WATER_SWITCH,
    CONF_XTREME_SETPOINT_CHAIN,
    CONF_XTREME_CYCLE_TRACKING,
    CONF_XTREME_MAXIMUM_SETPOINT_ENTITY,
    CONF_XTREME_STALE_SENSORS,
    CONF_XTREME_INSIDE_MAX_AGE,
    CONF_XTREME_BACKUP_INSIDE_SENSOR,
    CONF_XTREME_OUTSIDE_MAX_AGE,
    BOILER_PRESET_CUSTOM,
)

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True, slots=True, kw_only=True)
class BoilerPreset:
    """Default values for a boiler model. Only fills in numbers, never turns a switch on or off."""
    name: str
    manufacturer: str
    maximum_power: float
    minimum_power: float
    anti_cycling_time: int
    source: str


# Presets with a verified source. See docs/boiler_presets.md for how to add one.
BOILER_PRESETS: dict[str, BoilerPreset] = {
    "intergas_xtreme_30_2024": BoilerPreset(
        name="Intergas Xtreme 30 (2024)",
        manufacturer="Intergas",
        maximum_power=19.5,
        minimum_power=3.9,
        anti_cycling_time=300,
        source="Rating plate of a 2024 unit (G25.3, Pn 80/60) and the factory value of parameter P036",
    ),
}

# Options that a preset fills in
PRESET_OPTIONS = {
    CONF_XTREME_BOILER_MAXIMUM_POWER: "maximum_power",
    CONF_XTREME_BOILER_MINIMUM_POWER: "minimum_power",
    CONF_XTREME_ANTI_CYCLING_TIME: "anti_cycling_time",
}


def apply_boiler_preset(previous: dict[str, Any], submitted: dict[str, Any]) -> dict[str, Any]:
    """Apply the boiler preset to the submitted options.

    A newly chosen preset fills in its values. When the preset stays the same but one of its values was
    changed by hand, the preset falls back to custom, so it is always clear which values are in use.
    """
    result = dict(submitted)
    preset_key = result.get(CONF_XTREME_BOILER_PRESET, BOILER_PRESET_CUSTOM)

    if (preset := BOILER_PRESETS.get(preset_key)) is None:
        result[CONF_XTREME_BOILER_PRESET] = BOILER_PRESET_CUSTOM
        return result

    if previous.get(CONF_XTREME_BOILER_PRESET, BOILER_PRESET_CUSTOM) != preset_key:
        for option, attribute in PRESET_OPTIONS.items():
            result[option] = getattr(preset, attribute)

        _LOGGER.info("Xtreme profile: boiler preset '%s' applied.", preset.name)
        return result

    for option, attribute in PRESET_OPTIONS.items():
        if option in result and float(result[option]) != float(getattr(preset, attribute)):
            result[CONF_XTREME_BOILER_PRESET] = BOILER_PRESET_CUSTOM
            _LOGGER.info("Xtreme profile: '%s' was changed by hand, boiler preset set to custom.", option)
            break

    return result


# Do not resend the same heater state (CH=0 / CH=1) within this window while the
# status bit on the bus has not caught up yet (MsgID 0 every few seconds plus the
# coordinator debounce of 5 seconds).
HEATER_COMMAND_REPEAT_SECONDS = 30


@dataclass(frozen=True, slots=True, kw_only=True)
class XtremeProfile:
    """The switches of the Xtreme profile."""

    # Step 1: keep the minimum setpoint on the bus during the PWM off phase and turn the
    # central heating demand off explicitly, so the boiler already has the setpoint when
    # the next on phase starts.
    prime_setpoint: bool = False

    # Step 2: the boiler ignores the maximum relative modulation (MM=), but reports its modulation.
    # Stop managing the modulation limit and fall back to the rated power when the boiler does not
    # report its capacity (MsgID 15).
    ignore_modulation_limit: bool = False
    boiler_maximum_power: float = 19.5
    boiler_minimum_power: float = 3.9

    # Step 3: align PWM with the boiler. The on time counts burn time (flame on, no hot water), a new
    # on phase waits until the anti-cycling time after the last flame (heating or hot water) has passed,
    # and every burn lasts at least the minimum burn time.
    boiler_timing: bool = False
    anti_cycling_time: int = 300
    anti_cycling_margin: int = 15
    minimum_burn_time: int = 360
    minimum_duty_cycle: float = 7.5

    # Step 4: learn the OPV during normal operation: "off", "learn" (only show it) or "apply" (use it)
    learned_opv: str = "off"

    # Step 5: a slow calibration of the OPV that does not rely on MM=, started with a button or service
    calibration: bool = False

    # PID settings: a factor on the automatically calculated gains, and a limit on how far the
    # requested setpoint may rise above the heating curve (0 = no limit)
    pid_gain_factor: float = 1.0
    maximum_setpoint_rise: float = 0

    # The boiler preset that filled in the values above ("custom" when they were entered by hand)
    boiler_preset: str = BOILER_PRESET_CUSTOM

    # Hand the boiler back to the thermostat on the bus right away when SAT is turned off (CS=0),
    # instead of waiting for the heartbeat of the gateway to expire
    handover_on_off: bool = False

    # A switch to turn the keep-warm (comfort) function of the hot water off (HW=0) and back to the
    # boiler's own setting (HW=A), for example with an automation at night. Hot water itself is not
    # blocked on boilers that treat the DHW enable bit as "keep warm" (tested: Intergas Xtreme 30).
    hot_water_switch: bool = False

    # Diagnostics: a sensor that shows the setpoint SAT calculates, the one it sends to the gateway and the
    # one the gateway reports for the boiler. Read only, it changes nothing in the control.
    setpoint_chain: bool = False

    # Diagnostics: recognise every burner cycle and record its data (events, sensors and a history that
    # survives a restart). Read only, it changes nothing in the control.
    cycle_tracking: bool = False

    # A number entity for the maximum setpoint, for dashboards and automations. It stores the value as the
    # maximum setpoint option and applies it right away, between the OPV and a ceiling per heating system.
    maximum_setpoint_entity: bool = False

    # Stale sensors: a maximum age for the inside and outside temperature (in minutes, measured from the last
    # report), an optional backup inside sensor, and heating on the heating curve only when no inside sensor
    # is usable. Replaces the maximum value age check of SAT for these sensors.
    stale_sensors: bool = False
    inside_max_age: float = 90
    backup_inside_sensor: Optional[str] = None
    outside_max_age: float = 180

    @property
    def anti_cycling_wait(self) -> int:
        """Seconds to wait after the last flame before a new on phase may start."""
        return self.anti_cycling_time + self.anti_cycling_margin

    @property
    def flame_wait_timeout(self) -> int:
        """Seconds to wait for the flame in an on phase before the on time counts anyway."""
        return self.anti_cycling_wait + 15

    @staticmethod
    def from_options(options: Mapping[str, Any] | None) -> XtremeProfile:
        values = OPTIONS_DEFAULTS.copy()
        values.update(options or {})

        profile = XtremeProfile(
            prime_setpoint=bool(values.get(CONF_XTREME_PRIME_SETPOINT)),
            ignore_modulation_limit=bool(values.get(CONF_XTREME_IGNORE_MODULATION_LIMIT)),
            boiler_maximum_power=float(values.get(CONF_XTREME_BOILER_MAXIMUM_POWER)),
            boiler_minimum_power=float(values.get(CONF_XTREME_BOILER_MINIMUM_POWER)),
            boiler_timing=bool(values.get(CONF_XTREME_BOILER_TIMING)),
            anti_cycling_time=int(values.get(CONF_XTREME_ANTI_CYCLING_TIME)),
            anti_cycling_margin=int(values.get(CONF_XTREME_ANTI_CYCLING_MARGIN)),
            minimum_burn_time=int(values.get(CONF_XTREME_MINIMUM_BURN_TIME)),
            minimum_duty_cycle=float(values.get(CONF_XTREME_MINIMUM_DUTY_CYCLE)),
            learned_opv=str(values.get(CONF_XTREME_LEARNED_OPV)),
            calibration=bool(values.get(CONF_XTREME_CALIBRATION)),
            pid_gain_factor=float(values.get(CONF_XTREME_PID_GAIN_FACTOR)),
            maximum_setpoint_rise=float(values.get(CONF_XTREME_MAXIMUM_SETPOINT_RISE)),
            boiler_preset=str(values.get(CONF_XTREME_BOILER_PRESET)),
            handover_on_off=bool(values.get(CONF_XTREME_HANDOVER_ON_OFF)),
            hot_water_switch=bool(values.get(CONF_XTREME_HOT_WATER_SWITCH)),
            setpoint_chain=bool(values.get(CONF_XTREME_SETPOINT_CHAIN)),
            cycle_tracking=bool(values.get(CONF_XTREME_CYCLE_TRACKING)),
            maximum_setpoint_entity=bool(values.get(CONF_XTREME_MAXIMUM_SETPOINT_ENTITY)),
            stale_sensors=bool(values.get(CONF_XTREME_STALE_SENSORS)),
            inside_max_age=float(values.get(CONF_XTREME_INSIDE_MAX_AGE)),
            backup_inside_sensor=values.get(CONF_XTREME_BACKUP_INSIDE_SENSOR) or None,
            outside_max_age=float(values.get(CONF_XTREME_OUTSIDE_MAX_AGE)),
        )

        if profile.enabled:
            _LOGGER.info("Xtreme profile: active switches: %s", ", ".join(profile.active_switches))

        return profile

    @property
    def active_switches(self) -> list[str]:
        switches = (
            ("prime_setpoint", self.prime_setpoint),
            ("ignore_modulation_limit", self.ignore_modulation_limit),
            ("boiler_timing", self.boiler_timing),
            (f"learned_opv ({self.learned_opv})", self.learned_opv != "off"),
            ("calibration", self.calibration),
            (f"pid_gain_factor ({self.pid_gain_factor})", self.pid_gain_factor != 1.0),
            (f"maximum_setpoint_rise ({self.maximum_setpoint_rise})", self.maximum_setpoint_rise > 0),
            (f"boiler_preset ({self.boiler_preset})", self.boiler_preset != BOILER_PRESET_CUSTOM),
            ("handover_on_off", self.handover_on_off),
            ("hot_water_switch", self.hot_water_switch),
            ("setpoint_chain", self.setpoint_chain),
            ("cycle_tracking", self.cycle_tracking),
            ("maximum_setpoint_entity", self.maximum_setpoint_entity),
            ("stale_sensors", self.stale_sensors),
        )

        return [name for name, enabled in switches if enabled]

    @property
    def enabled(self) -> bool:
        return len(self.active_switches) > 0
