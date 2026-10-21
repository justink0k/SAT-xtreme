"""The version in manifest.json must sort correctly in HACS and match an entry in CHANGES_XTREME.md."""
import json
import re
from pathlib import Path

from awesomeversion import AwesomeVersion

ROOT = Path(__file__).parent.parent
VERSION_FORMAT = re.compile(r"^\d+\.\d+\.\d+-xtreme\.\d+$")


def _version() -> str:
    return json.loads((ROOT / "custom_components" / "sat" / "manifest.json").read_text())["version"]


def test_version_has_the_release_format():
    version = _version()

    assert VERSION_FORMAT.match(version), f"{version} does not match X.Y.Z-xtreme.N (see RELEASING.md)"


def test_version_is_not_a_beta_for_home_assistant():
    version = AwesomeVersion(_version())

    assert not (version.alpha or version.beta or version.release_candidate or version.dev)


def test_versions_sort_numerically():
    assert AwesomeVersion("4.2.1-xtreme.12") > AwesomeVersion("4.2.1-xtreme.11")
    assert AwesomeVersion("4.2.1-xtreme.10") > AwesomeVersion("4.2.1-xtreme.9")
    assert AwesomeVersion("4.3.0-xtreme.1") > AwesomeVersion("4.2.1-xtreme.12")


def test_changes_has_an_entry_for_the_version():
    changes = (ROOT / "CHANGES_XTREME.md").read_text()

    assert f"`{_version()}`" in changes, f"CHANGES_XTREME.md has no entry for {_version()}"
