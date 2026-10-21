"""Tests for step 7: the dashboard template refers to the entity IDs that the fork creates."""
from pathlib import Path

import yaml
from homeassistant.util import slugify

DASHBOARD = Path(__file__).parent.parent / "dashboards" / "sat_xtreme.yaml"

# Names of the entities of the fork for a SAT named "SAT" (see xtreme_sensor.py, button.py, sensor.py)
EXPECTED = {
    "sensor": [
        "Xtreme fork: PWM Burn Time SAT",
        "Xtreme fork: Anti-cycling Remaining SAT",
        "Xtreme fork: Learned OPV SAT",
        "Xtreme fork: Calibration SAT",
        "Xtreme fork: PID Output SAT",
        "Current Power SAT (Boiler)",
        "Heating Curve SAT",
    ],
    "button": ["Xtreme fork: Start Calibration SAT", "Xtreme fork: Stop Calibration SAT"],
    "switch": ["Xtreme fork: Hot Water Keep Warm SAT"],
}


def _entity_ids(node) -> set[str]:
    found = set()

    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("entity", "entity_id") and isinstance(value, str):
                found.add(value)
            else:
                found |= _entity_ids(value)
    elif isinstance(node, list):
        for value in node:
            found |= _entity_ids(value)

    return found


def test_dashboard_is_valid_yaml():
    dashboard = yaml.safe_load(DASHBOARD.read_text())

    assert dashboard["views"][0]["cards"]


def test_dashboard_uses_the_entity_ids_of_the_fork():
    entity_ids = _entity_ids(yaml.safe_load(DASHBOARD.read_text()))

    for domain, names in EXPECTED.items():
        for name in names:
            assert f"{domain}.{slugify(name)}" in entity_ids, name
