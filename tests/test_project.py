"""Project-level tests for flint2_ansible."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_required_project_files_exist() -> None:
    expected = [
        ROOT / "ansible.cfg",
        ROOT / "requirements.yml",
        ROOT / "execution-environment.yml",
        ROOT / "roles/flint2/meta/argument_specs.yml",
        ROOT / "roles/flint2/molecule/default/molecule.yml",
    ]
    missing = [path.relative_to(ROOT) for path in expected if not path.exists()]
    assert not missing, f"Missing required project files: {missing}"


def test_playbooks_are_present() -> None:
    playbooks = sorted((ROOT / "playbooks").glob("*.yml"))
    names = [path.name for path in playbooks]
    assert "site.yml" in names
    assert "ping.yml" in names
