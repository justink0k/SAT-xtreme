import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, SERVICE_RESET_INTEGRAL, SERVICE_PULSE_WIDTH_MODULATION, SERVICE_START_XTREME_CALIBRATION, SERVICE_STOP_XTREME_CALIBRATION
from .util import get_climate_entities

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_register_services(hass: HomeAssistant) -> None:
    async def reset_integral(call: ServiceCall):
        """Service to reset the integral part of the PID controller."""
        target_entities = call.data.get("entity_id", [])

        for climate in get_climate_entities(hass, target_entities):
            _LOGGER.info("Reset Integral action called for %s", climate.entity_id)

            climate.pid.reset()
            climate.areas.pids.reset()

    hass.services.async_register(
        DOMAIN,
        service=SERVICE_RESET_INTEGRAL,
        service_func=reset_integral,
        schema=vol.Schema({vol.Required("entity_id"): list[str]})
    )

    async def pulse_width_modulation(call: ServiceCall):
        """Service to enable or disable Pulse Width Modulation."""
        enabled = call.data.get("enabled")
        target_entities = call.data.get("entity_id", [])

        for climate in get_climate_entities(hass, target_entities):
            _LOGGER.info("Pulse Width Modulation action called for %s with enabled=%s", climate.entity_id, enabled)

            if enabled:
                climate.pwm.enable()
            else:
                climate.pwm.disable()

    hass.services.async_register(
        DOMAIN,
        service=SERVICE_PULSE_WIDTH_MODULATION,
        service_func=pulse_width_modulation,
        schema=vol.Schema({vol.Required("entity_id"): list[str], vol.Required("enabled"): cv.boolean})
    )

    async def start_xtreme_calibration(call: ServiceCall):
        """Service to start the calibration of the Xtreme profile."""
        for climate in get_climate_entities(hass, call.data.get("entity_id", [])):
            if not climate.coordinator.xtreme_profile.calibration:
                _LOGGER.warning("Xtreme calibration is not enabled in the options of %s.", climate.entity_id)
                continue

            _LOGGER.info("Start Xtreme calibration action called for %s", climate.entity_id)
            await climate.xtreme_calibration.async_start()

    hass.services.async_register(
        DOMAIN,
        service=SERVICE_START_XTREME_CALIBRATION,
        service_func=start_xtreme_calibration,
        schema=vol.Schema({vol.Required("entity_id"): cv.entity_ids})
    )

    async def stop_xtreme_calibration(call: ServiceCall):
        """Service to stop the calibration of the Xtreme profile."""
        for climate in get_climate_entities(hass, call.data.get("entity_id", [])):
            _LOGGER.info("Stop Xtreme calibration action called for %s", climate.entity_id)
            await climate.xtreme_calibration.async_stop()

    hass.services.async_register(
        DOMAIN,
        service=SERVICE_STOP_XTREME_CALIBRATION,
        service_func=stop_xtreme_calibration,
        schema=vol.Schema({vol.Required("entity_id"): cv.entity_ids})
    )
