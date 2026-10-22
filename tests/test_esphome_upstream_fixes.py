"""ESPHome fixes from upstream develop (a590150, 6ae78b4), merged in 4.2.1-xtreme.18."""
import sys
import types

from homeassistant.components import binary_sensor

# The ESPHome component needs aioesphomeapi, which the test environment does not install; the coordinator
# only uses the module name, so a stand-in is enough here.
sys.modules.setdefault("homeassistant.components.esphome", types.ModuleType("homeassistant.components.esphome"))

from custom_components.sat_xtreme.coordinator import DeviceState  # noqa: E402
from custom_components.sat_xtreme.esphome import DATA_DHW_ACTIVE, DATA_DHW_ENABLE, SatEspHomeCoordinator  # noqa: E402


def test_hot_water_active_reads_the_dhw_active_sensor():
    coordinator = object.__new__(SatEspHomeCoordinator)
    states = {(binary_sensor.DOMAIN, DATA_DHW_ACTIVE): DeviceState.ON, (binary_sensor.DOMAIN, DATA_DHW_ENABLE): DeviceState.OFF}
    coordinator.get = lambda domain, key: states.get((domain, key))

    # Hot water is active when the boiler reports it, not when hot water is merely enabled
    assert coordinator.hot_water_active is True
