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


def _coordinator_with_registry(legacy: dict, entries: list):
    """A coordinator with a stand-in entity registry: legacy maps (domain, unique_id) to an entity ID."""
    from types import SimpleNamespace

    esphome_module = sys.modules["homeassistant.components.esphome"]
    if not hasattr(esphome_module, "DOMAIN"):
        esphome_module.DOMAIN = "esphome"

    coordinator = object.__new__(SatEspHomeCoordinator)
    coordinator._mac_address = "aa:bb:cc:dd:ee:ff"
    coordinator._entity_registry = SimpleNamespace(async_get_entity_id=lambda domain, platform, unique_id: legacy.get((domain, unique_id)))
    coordinator._entities = [SimpleNamespace(domain=domain, unique_id=unique_id, entity_id=entity_id) for domain, unique_id, entity_id in entries]
    return coordinator


def test_entity_ids_are_found_with_the_legacy_unique_id_scheme():
    coordinator = _coordinator_with_registry({("sensor", "AA:BB:CC:DD:EE:FF-sensor-boiler_temperature"): "sensor.boiler_temperature"}, [])

    assert coordinator._get_entity_id("sensor", "boiler_temperature") == "sensor.boiler_temperature"


def test_entity_ids_are_found_with_the_current_unique_id_scheme():
    # 4.2.1-xtreme.37, pull request #1 by tbrasser: recent ESPHome versions use <MAC>/<device_id>/<domain>/<object_id>
    coordinator = _coordinator_with_registry({}, [
        ("sensor", "AA:BB:CC:DD:EE:FF/0/sensor/return_temperature", "sensor.return_temperature"),
        ("sensor", "AA:BB:CC:DD:EE:FF/0/sensor/boiler_temperature", "sensor.boiler_temperature"),
        ("binary_sensor", "AA:BB:CC:DD:EE:FF/0/binary_sensor/boiler_temperature", "binary_sensor.wrong_domain"),
    ])

    assert coordinator._get_entity_id("sensor", "boiler_temperature") == "sensor.boiler_temperature"
    assert coordinator._get_entity_id("number", "boiler_temperature") is None
