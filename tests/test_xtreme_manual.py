"""The manual (docs/) must describe every option, entity and action of the fork, so it does not fall behind."""
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "docs"
PACKAGE = ROOT / "custom_components" / "sat"


def _manual() -> str:
    return "\n".join(path.read_text() for path in DOCS.glob("*.md"))


def _translations() -> dict:
    return json.loads((PACKAGE / "translations" / "en.json").read_text())


def test_every_xtreme_profile_option_is_in_the_manual():
    manual = _manual()
    sections = _translations()["options"]["step"]["xtreme_profile"]["sections"]

    for section in sections.values():
        for label in section["data"].values():
            assert label in manual, f"option '{label}' is not described in docs/"


def test_every_pid_setting_is_in_the_manual():
    manual = _manual()

    for label in _translations()["options"]["step"]["pid_settings"]["data"].values():
        assert label.lower() in manual.lower(), f"PID setting '{label}' is not described in docs/"


def test_every_fork_entity_is_in_the_manual():
    manual = _manual()
    labels = set()

    for path in (PACKAGE / "xtreme").glob("*.py"):
        labels |= set(re.findall(r'_label = "([^"]+)"', path.read_text()))

    for path in [PACKAGE / "button.py", PACKAGE / "xtreme" / "switch.py"]:
        labels |= set(re.findall(r'\{FORK_LABEL\} ([A-Z][A-Za-z ]+?) \{', path.read_text()))

    assert labels, "no fork entity labels found"

    for label in labels:
        assert label in manual, f"entity 'Xtreme fork: {label}' is not described in docs/"


def test_every_action_is_in_the_manual():
    manual = _manual()

    for action in yaml.safe_load((PACKAGE / "services.yaml").read_text()):
        assert f"sat.{action}" in manual, f"action sat.{action} is not described in docs/"


def test_every_repair_is_in_the_manual():
    manual = _manual()

    for issue in _translations()["issues"].values():
        assert issue["title"] in manual, f"repair '{issue['title']}' is not described in docs/"


def test_every_page_is_in_the_navigation():
    nav = (ROOT / "mkdocs.yml").read_text()

    for path in DOCS.glob("*.md"):
        assert f": {path.name}" in nav, f"{path.name} is not in the navigation of mkdocs.yml"
