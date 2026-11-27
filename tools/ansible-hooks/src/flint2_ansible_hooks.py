"""Skip config-dump notices for callbacks this project does not enable.

ansible-core 2.22 deprecates the builtin ``oneline`` and ``tree`` callbacks.
``ansible-lint`` learns its settings by running ``ansible-config dump``, and
that command loads every callback plugin, including those two. The project
never selects them (stdout stays on ``ansible.builtin.default``), so the
notice is from enumeration, not from use.

Deprecation warnings stay on. Selecting either callback in a playbook still
warns, because that path does not go through ``ansible-config``.
"""

from __future__ import annotations

import sys
import traceback
from collections.abc import Iterable
from typing import Any

_UNUSED_CALLBACKS = frozenset(
    {
        "oneline",
        "tree",
        "ansible.builtin.oneline",
        "ansible.builtin.tree",
    }
)
_CONFIG_DUMP = "ansible/cli/config.py"


def enumerating_unused_callback(name: str, stack: Iterable[traceback.FrameSummary] | None = None) -> bool:
    """True when config dump is merely listing an unused deprecated callback."""
    if name not in _UNUSED_CALLBACKS:
        return False
    frames = traceback.extract_stack() if stack is None else stack
    return any(str(frame.filename).replace("\\", "/").endswith(_CONFIG_DUMP) for frame in frames)


def install() -> None:
    """Wrap plugin deprecation recording. Safe to call more than once."""
    if not _ansible_process():
        return
    from ansible.plugins.loader import PluginLoadContext

    current = PluginLoadContext.record_deprecation
    if getattr(current, "_flint2_wrapped", False):
        return

    def record_deprecation(self: Any, name: str, deprecation: dict[str, Any] | None, collection_name: str) -> Any:
        if enumerating_unused_callback(name):
            return self
        return current(self, name, deprecation, collection_name)

    record_deprecation._flint2_wrapped = True  # type: ignore[attr-defined]
    PluginLoadContext.record_deprecation = record_deprecation  # type: ignore[method-assign]


def _ansible_process() -> bool:
    command = sys.argv[0].replace("\\", "/")
    return command.endswith(
        (
            "/ansible",
            "/ansible-config",
            "/ansible-playbook",
            "/ansible-lint",
            "/ansible-galaxy",
            "/ansible-doc",
            "/molecule",
        )
    ) or command in {
        "ansible",
        "ansible-config",
        "ansible-playbook",
        "ansible-lint",
        "ansible-galaxy",
        "ansible-doc",
        "molecule",
    }


install()
