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
    assert "enable_dropbear_rpc.yml" in names
    assert "post_upgrade.yml" in names


def test_post_upgrade_script_exists() -> None:
    script = ROOT / "scripts/glinet_enable_dropbear.py"
    assert script.is_file(), "Missing scripts/glinet_enable_dropbear.py"
    assert "local-access" in script.read_text(encoding="utf-8")


def test_makefile_post_upgrade_targets() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^enable-dropbear-rpc:", text, re.MULTILINE)
    assert re.search(r"^post-upgrade:", text, re.MULTILINE)
    assert "SITE_TAGS ?= ssh,always" in text
    assert "playbooks/enable_dropbear_rpc.yml" in text
    # Default SITE_TAGS must resolve to tags declared on the flint2 role / playbooks.
    declared = _declared_tags()
    unknown = sorted({"ssh", "always"} - declared)
    assert not unknown, f"SITE_TAGS default references undeclared tags: {unknown}"


def test_post_upgrade_playbook_imports_enable_and_site() -> None:
    docs = list(yaml.safe_load_all((ROOT / "playbooks/post_upgrade.yml").read_text(encoding="utf-8")))
    # import_playbook documents are a YAML sequence of mapping nodes.
    plays = docs[0] if docs else []
    assert isinstance(plays, list)
    imports = [
        item.get("ansible.builtin.import_playbook") or item.get("import_playbook")
        for item in plays
        if isinstance(item, dict)
    ]
    assert "enable_dropbear_rpc.yml" in imports
    assert "site.yml" in imports


def test_enable_dropbear_rpc_playbook_uses_helper_script() -> None:
    plays = yaml.safe_load((ROOT / "playbooks/enable_dropbear_rpc.yml").read_text(encoding="utf-8"))
    assert isinstance(plays, list) and plays
    play = plays[0]
    vars_ = play.get("vars") or {}
    assert "glinet_enable_dropbear.py" in str(vars_.get("flint2_post_upgrade_script", ""))
    assert vars_.get("flint2_glinet_admin_password_filename") == "real_root_password"
    assert play.get("vars", {}).get("ansible_connection") == "local"
    task_names = {task.get("name") for task in _tasks(play.get("tasks"))}
    assert "Enable Dropbear and seed authorized_keys over HTTPS" in task_names
    assert "Skip Dropbear enable when SSH already answers on the management IP" in task_names


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
