"""What the plugin needs to know about Claude Code itself: its config folder, its settings
files, where it keeps a project's auto memory, and the input it hands a hook.
"""

import json
import os
import re
import sys

from automem import jsonfile


def config_dir():
    return os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude")


SCOPES = ("user", "project", "local")  # in the order Claude Code applies them: the last one that sets a key wins


def _settings_files(root):
    return [
        os.path.join(config_dir(), "settings.json"),
        os.path.join(root, ".claude", "settings.json"),
        os.path.join(root, ".claude", "settings.local.json"),
    ]


def _setting_with_scope(root, key):
    value, scope = None, None
    for name, path in zip(SCOPES, _settings_files(root)):
        data = jsonfile.read_json(path, {}) or {}
        if isinstance(data, dict) and key in data:
            value, scope = data[key], name
    return value, scope


def setting(root, key):
    """The effective value of a settings key: local beats project beats user. None when unset."""
    return _setting_with_scope(root, key)[0]


def setting_scope(root, key):
    """Which settings file the effective value comes from ('user', 'project', 'local'), or None."""
    value, scope = _setting_with_scope(root, key)
    return scope if isinstance(value, str) and value.strip() else None


def auto_memory_on(root):
    """Is built-in auto memory on for this project? The plugin does nothing where it's off."""
    if os.environ.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY", "").lower() in ("1", "true", "yes"):
        return False
    return setting(root, "autoMemoryEnabled") is not False


def project_dir_name(root):
    """Claude Code's folder name for a project: every non-alphanumeric character becomes '-'.
    Claude Code doesn't document this, so sync never trusts it alone: it only writes into a
    project folder that already exists or that the session's transcript path confirms."""
    return os.environ.get("CLAUDE_CODE_PROJECT_DIR_NAME") or re.sub(r"[^A-Za-z0-9]", "-", root)


def memory_dir(root):
    custom = setting(root, "autoMemoryDirectory")
    if isinstance(custom, str) and custom.strip():
        return os.path.expanduser(custom.strip())
    return os.path.join(config_dir(), "projects", project_dir_name(root), "memory")


def hook_input():
    """The JSON Claude Code passes a hook on stdin, or {} when there is none."""
    try:
        return json.load(sys.stdin)
    except ValueError:
        return {}
