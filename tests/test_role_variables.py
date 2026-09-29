"""Keep role defaults, argument specs, and inventory overrides consistent."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "roles/flint2"

# Molecule playbooks read these outside the role, where role defaults are not visible.
MOLECULE_VARS_READ_OUTSIDE_ROLE = {
    "flint2_bridge",
    "flint2_firmware_auto_update_check",
    "flint2_wireless_device_option_keys",
}


# A top-level role variable (not an attribute or subscript) followed by a fallback or definedness test.
REDUNDANT_GUARD = re.compile(r"(?<![\w.\[])(flint2_[a-z0-9_]+)\s*(?:\|\s*default\(|is\s+(?:not\s+)?defined)")


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text()) or {}


def _defaults() -> dict[str, Any]:
    return _load(ROLE / "defaults/main.yml")


def _spec_options() -> dict[str, dict[str, Any]]:
    return _load(ROLE / "meta/argument_specs.yml")["argument_specs"]["main"]["options"]


def test_every_role_default_is_in_argument_specs() -> None:
    missing = sorted(set(_defaults()) - set(_spec_options()))
    assert not missing, f"Role defaults missing from meta/argument_specs.yml: {missing}"


def test_argument_spec_defaults_match_role_defaults() -> None:
    defaults = _defaults()
    mismatched = sorted(
        name
        for name, option in _spec_options().items()
        if "default" in option and name in defaults and option["default"] != defaults[name]
    )
    assert not mismatched, f"argument_specs default differs from defaults/main.yml: {mismatched}"


def test_group_vars_do_not_repeat_role_defaults() -> None:
    defaults = _defaults()
    group_vars = _load(ROOT / "inventory/group_vars/flint2/main.yml")
    repeated = sorted(name for name, value in group_vars.items() if name in defaults and value == defaults[name])
    assert not repeated, f"group_vars repeat role defaults verbatim; remove them: {repeated}"


def test_molecule_vars_only_repeat_defaults_read_outside_role() -> None:
    defaults = _defaults()
    molecule_vars = _load(ROLE / "molecule/default/molecule_vars.yml")
    repeated = {name for name, value in molecule_vars.items() if name in defaults and value == defaults[name]}
    unexpected = sorted(repeated - MOLECULE_VARS_READ_OUTSIDE_ROLE)
    assert not unexpected, f"molecule_vars repeat role defaults verbatim; remove them: {unexpected}"


def test_role_code_does_not_guard_variables_that_have_defaults() -> None:
    defaults = _defaults()
    files = [*ROLE.glob("tasks/*.yml"), *ROLE.glob("handlers/*.yml"), *ROLE.glob("templates/*.j2")]
    redundant = sorted(
        f"{path.relative_to(ROLE)}: {match.group(0)}"
        for path in files
        for match in REDUNDANT_GUARD.finditer(path.read_text())
        if match.group(1) in defaults
    )
    assert not redundant, f"default()/is defined on variables that always have a role default: {redundant}"
