"""The fork must not send errors to the Sentry project of the official SAT."""
import json
from pathlib import Path

from custom_components.sat import const

ROOT = Path(__file__).parent.parent
PACKAGE = ROOT / "custom_components" / "sat"


def test_no_sentry_in_the_integration():
    for path in PACKAGE.rglob("*.py"):
        assert "sentry" not in path.read_text().lower(), f"{path.name} still refers to Sentry"


def test_sentry_is_not_a_requirement():
    requirements = json.loads((PACKAGE / "manifest.json").read_text())["requirements"]

    assert not any(requirement.startswith("sentry") for requirement in requirements)


def test_error_monitoring_option_is_gone():
    assert not hasattr(const, "CONF_ERROR_MONITORING")
    assert "error_monitoring" not in const.OPTIONS_DEFAULTS

    for path in (PACKAGE / "translations").glob("*.json"):
        assert "error_monitoring" not in path.read_text(), f"{path.name} still has the option"
