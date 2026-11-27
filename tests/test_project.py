"""Project-level tests for flint2_ansible."""

from __future__ import annotations

import re
import traceback
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


def test_optional_service_handlers_skip_missing_init_scripts() -> None:
    """Optional packages may be absent in check mode or after a firmware wipe."""
    handlers = yaml.safe_load((ROLE / "handlers/main.yml").read_text())
    by_name = {handler.get("name"): handler for handler in handlers}
    for name, listen, init_script in (
        ("Restart LuCI Statistics", "flint2 statistics changed", "/etc/init.d/luci_statistics"),
        ("Restart collectd", "flint2 statistics changed", "/etc/init.d/collectd"),
        ("Restart usteer", "flint2 usteer changed", "/etc/init.d/usteer"),
    ):
        handler = by_name[name]
        assert handler["listen"] == listen
        command = handler["community.openwrt.command"]
        assert command["cmd"] == f"{init_script} restart"
        assert command["removes"] == init_script


def test_system_sets_log_size() -> None:
    """system.@system[0].log_size is set from flint2_log_size and restarts logd."""
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    assert defaults["flint2_log_size"] == 8192

    spec = yaml.safe_load((ROLE / "meta/argument_specs.yml").read_text())
    option = spec["argument_specs"]["main"]["options"]["flint2_log_size"]
    assert option["type"] == "int"
    assert option["default"] == 8192
    assert "system.@system[0].log_size" in option["description"]

    tasks = {task.get("name"): task for task in _tasks(yaml.safe_load((ROLE / "tasks/system.yml").read_text()))}
    task = tasks["Set system log buffer size"]
    uci = task["community.openwrt.uci"]
    assert uci["command"] == "set"
    assert uci["key"] == "system.@system[0].log_size"
    assert uci["value"] == "{{ flint2_log_size }}"
    assert task["notify"] == "flint2 log changed"

    handlers = yaml.safe_load((ROLE / "handlers/main.yml").read_text())
    handler = next(item for item in handlers if item.get("name") == "Restart system log")
    assert handler["listen"] == "flint2 log changed"
    assert handler["community.openwrt.service"]["name"] == "log"
    assert handler["community.openwrt.service"]["state"] == "restarted"


def test_verify_asserts_log_size() -> None:
    tasks = {task.get("name"): task for task in _tasks(yaml.safe_load((ROLE / "tasks/verify.yml").read_text()))}
    read = tasks["Read configured system log buffer size"]
    assert read["community.openwrt.uci"]["key"] == "system.@system[0].log_size"
    assert read["register"] == "flint2_verify_log_size"

    assert_task = tasks["Assert system log buffer size matches desired value"]
    that = "\n".join(assert_task["ansible.builtin.assert"]["that"])
    assert "flint2_verify_log_size.result | int == flint2_log_size | int" in that


def test_makefile_log_size_target() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^log-size: system$", text, re.MULTILINE)
    assert re.search(r"^system: install$", text, re.MULTILINE)
    assert "--tags system,always" in text


def test_deprecation_warnings_stay_enabled() -> None:
    """Unused callback notices are fixed without turning deprecation warnings off."""
    cfg = (ROOT / "ansible.cfg").read_text(encoding="utf-8")
    assert "deprecation_warnings" not in cfg
    assert "stdout_callback = ansible.builtin.default" in cfg
    assert "oneline" not in cfg.split("stdout_callback", 1)[1].splitlines()[0]
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^lint: install$", makefile, re.MULTILINE)
    assert "-p .ansible/collections" in makefile
    assert "collections_path = ./.ansible/collections" in cfg


def test_config_dump_skips_only_unused_callback_notices() -> None:
    import flint2_ansible_hooks as hook

    config_dump = traceback.FrameSummary("ansible/cli/config.py", 1, "execute_dump")
    playbook = traceback.FrameSummary("ansible/executor/task_queue_manager.py", 1, "load_callbacks")
    assert hook.enumerating_unused_callback("oneline", [config_dump])
    assert hook.enumerating_unused_callback("ansible.builtin.tree", [config_dump])
    assert not hook.enumerating_unused_callback("oneline", [playbook])
    assert not hook.enumerating_unused_callback("default", [config_dump])


def test_access_control_sets_oui_httpd_allowed_host() -> None:
    """OP25 4.11+ Host allowlist is managed via community.openwrt.uci, not shell uci."""
    tasks = {task.get("name"): task for task in _tasks(yaml.safe_load((ROLE / "tasks/access_control.yml").read_text()))}
    task = tasks["Configure GL.iNet admin panel allowed hosts"]
    uci = task["community.openwrt.uci"]
    assert uci["command"] == "set"
    assert uci["key"] == "oui-httpd.main.allowed_host"
    assert uci["value"] == "{{ flint2_access_control.admin.allowed_hosts }}"
    assert task["notify"] == "flint2 nginx changed"
    assert "flint2_access_control_enabled | bool" in task["when"]
    assert "flint2_access_control.admin.allowed_hosts | length > 0" in task["when"]


def test_verify_asserts_oui_httpd_allowed_host() -> None:
    tasks = {task.get("name"): task for task in _tasks(yaml.safe_load((ROLE / "tasks/verify.yml").read_text()))}
    read = tasks["Read GL.iNet admin panel allowed hosts"]
    assert read["community.openwrt.uci"]["key"] == "oui-httpd.main.allowed_host"
    assert read["register"] == "flint2_verify_admin_allowed_hosts"
    assert "flint2_verify_glinet_settings | bool" in read["when"]
    assert "flint2_access_control.admin.allowed_hosts | length > 0" in read["when"]

    assert_task = tasks["Assert GL.iNet admin panel allowed hosts match desired values"]
    that = "\n".join(assert_task["ansible.builtin.assert"]["that"])
    assert "flint2_verify_admin_allowed_hosts.result_list" in that
    assert "flint2_access_control.admin.allowed_hosts" in that


def test_molecule_covers_oui_httpd_allowed_host() -> None:
    molecule_vars = yaml.safe_load((ROLE / "molecule/default/molecule_vars.yml").read_text())
    assert molecule_vars["flint2_fqdn"] == "molecule-flint2.example.test"

    verify_tasks = {
        task.get("name"): task
        for play in yaml.safe_load((ROLE / "molecule/default/verify.yml").read_text())
        for task in _tasks(play.get("tasks"))
    }
    read = verify_tasks["Read GL.iNet admin panel allowed hosts"]
    assert read["community.openwrt.uci"]["key"] == "oui-httpd.main.allowed_host"

    assert_task = verify_tasks["Assert GL.iNet admin panel allowed hosts include the Molecule FQDN"]
    that = "\n".join(assert_task["ansible.builtin.assert"]["that"])
    assert "flint2_molecule_verify_allowed_hosts.result_list" in that
    assert "flint2_fqdn" in that
