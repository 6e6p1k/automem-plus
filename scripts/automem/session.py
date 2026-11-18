"""What the plugin remembers about one Claude Code session, and where that session started."""

import os
import re

from automem import constants, jsonfile, state


def session_state_path(session_id):
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", session_id or "none")
    return os.path.join(state.state_dir(), "sessions", safe_id + ".json")


def start_dir(data):
    """The folder the session started in.

    Claude Code keeps auto memory under that project for the whole session, while the cwd a
    hook receives follows every cd Claude runs. CLAUDE_PROJECT_DIR names the start folder
    directly; the checkout saved at SessionStart is the fallback, then cwd."""
    project = os.environ.get(constants.PROJECT_DIR_ENV)
    if project and os.path.isdir(project):
        return project
    session_state = jsonfile.read_json(session_state_path(data.get("session_id", "")), {}) or {}
    saved = session_state.get("top") or session_state.get("root")
    if saved and os.path.isdir(saved):
        return saved
    return data.get("cwd") or os.getcwd()
