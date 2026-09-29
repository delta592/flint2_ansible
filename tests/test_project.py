"""Project-level tests for flint2_ansible."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "roles/flint2"


def _tasks(items: list[dict[str, Any]] | None) -> Iterator[dict[str, Any]]:
    """Yield every task, descending into block/rescue/always."""
    for task in items or []:
        yield task
        for section in ("block", "rescue", "always"):
            yield from _tasks(task.get(section))


def _task_tags(tasks: list[dict[str, Any]] | None) -> set[str]:
    """Tags set on tasks directly or through include_tasks apply."""
    tags: set[str] = set()
    for task in _tasks(tasks):
        tags.update(task.get("tags") or [])
        for key, value in task.items():
            if key.endswith("include_tasks") and isinstance(value, dict):
                tags.update(value.get("apply", {}).get("tags") or [])
    return tags


def _declared_tags() -> set[str]:
    tags = _task_tags(yaml.safe_load((ROLE / "tasks/main.yml").read_text()))
    for path in sorted((ROOT / "playbooks").glob("*.yml")):
        for play in yaml.safe_load(path.read_text()) or []:
            tags.update(play.get("tags") or [])
            tags |= _task_tags(play.get("tasks"))
            for role in play.get("roles") or []:
                if isinstance(role, dict):
                    tags.update(role.get("tags") or [])
    return tags


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


def test_makefile_tags_exist_in_role_or_playbooks() -> None:
    declared = _declared_tags()
    used = {
        tag
        for match in re.finditer(r"--tags ([\w,]+)", (ROOT / "Makefile").read_text())
        for tag in match.group(1).split(",")
    }
    assert used, "No literal --tags found in the Makefile"
    unknown = sorted(used - declared)
    assert not unknown, f"Makefile --tags not declared in tasks/main.yml or playbooks: {unknown}"


def test_role_templates_exist() -> None:
    sources = {
        task[module]["src"]
        for path in sorted(ROLE.glob("tasks/*.yml"))
        for task in _tasks(yaml.safe_load(path.read_text()))
        for module in task
        if module.endswith(".template") and isinstance(task[module], dict) and "{{" not in task[module].get("src", "{{")
    }
    assert sources, "No literal template sources found in role tasks"
    missing = sorted(src for src in sources if not (ROLE / "templates" / src).is_file())
    assert not missing, f"Role tasks reference missing templates: {missing}"
