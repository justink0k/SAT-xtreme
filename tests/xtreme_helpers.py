"""Shared helpers for the Xtreme profile tests."""
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.template import DOMAIN as TEMPLATE_DOMAIN

from custom_components.sat.const import *

MINIMUM_SETPOINT_VALUE = 46

TEMPLATE_CONFIG = {
    TEMPLATE_DOMAIN: [
        {
            SENSOR_DOMAIN: [
                {"name": "test_inside_sensor", "state": "{{ 20.0 | float }}"},
                {"name": "test_outside_sensor", "state": "{{ 12.0 | float }}"},
            ]
        },
    ],
}


def parameters(force_pwm: bool = True, overshoot_protection: bool = True, **options):
    """Build the pytest parameters for a SAT entry with the given (Xtreme) options."""
    return [
        "domains, data, options, config",
        [(
            [(TEMPLATE_DOMAIN, 1)],
            {
                CONF_MODE: MODE_FAKE,
                CONF_HEATING_SYSTEM: HEATING_SYSTEM_RADIATORS,
                CONF_MINIMUM_SETPOINT: MINIMUM_SETPOINT_VALUE,
                CONF_OVERSHOOT_PROTECTION: overshoot_protection,
            },
            {
                CONF_MAXIMUM_SETPOINT: 60,
                CONF_HEATING_CURVE_COEFFICIENT: 2.0,
                CONF_FORCE_PULSE_WIDTH_MODULATION: force_pwm,
                **options,
            },
            TEMPLATE_CONFIG,
        )],
    ]


class Clock:
    """A controllable monotonic clock."""

    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def xtreme_profile_input(**fields) -> dict:
    """Build the input of the sectioned Xtreme profile page from flat option values."""
    from custom_components.sat.config_flow import XTREME_SECTION_BOILER, XTREME_SECTION_LEARNING, XTREME_SECTION_THERMOSTAT

    sections = {
        XTREME_SECTION_THERMOSTAT: (CONF_XTREME_PRIME_SETPOINT, CONF_XTREME_HANDOVER_ON_OFF),
        XTREME_SECTION_LEARNING: (CONF_XTREME_LEARNED_OPV, CONF_XTREME_CALIBRATION),
    }

    result = {XTREME_SECTION_THERMOSTAT: {}, XTREME_SECTION_BOILER: {}, XTREME_SECTION_LEARNING: {}}
    for key, value in fields.items():
        name = next((section for section, keys in sections.items() if key in keys), XTREME_SECTION_BOILER)
        result[name][key] = value

    return result
