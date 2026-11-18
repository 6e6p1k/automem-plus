#!/usr/bin/env python3
"""SessionStart hook: inject the rules wherever auto memory is on; in git repos also run a quick sync.

The rules are worked out before the sync, and the sync is bounded (a short lock wait and fetch
timeout), so a slow store can't make this hook time out and lose the rules. It also remembers the
checkout's HEAD, so the Stop hook can tell whether commits happened during the session.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from automem import claudecode, gitrepo, handoff, jsonfile, plugin, rules, session, state, sync, usage  # noqa: E402

LOCK_WAIT, FETCH_TIMEOUT = 3, 6  # seconds; together well under the hook's own timeout


def main():
    if state.disabled():
        return
    data = claudecode.hook_input()
    session_id, source = data.get("session_id", ""), data.get("source", "startup")
    cwd = session.start_dir(data)
    root, is_git = gitrepo.project_root(cwd)
    if not root or not claudecode.auto_memory_on(root):
        return
    branch_name = gitrepo.branch(cwd) if is_git else None
    handoff_file = handoff.handoff_name(branch_name)
    parts = rules.rules_text(handoff_file, branch_name)
    rid = usage.remember_repo(root)
    if is_git and plugin.feature_on("handoff_rule"):
        stale = handoff.orphaned_handoffs(claudecode.memory_dir(root), cwd)
        if stale:
            parts.append(
                "These handoff notes belong to branches that no longer exist here (probably merged): "
                + ", ".join(stale)
                + ". When it fits, move anything lasting from them into its own note "
                "and delete them with their MEMORY.md lines."
            )

    state_path = session.session_state_path(session_id)
    if not jsonfile.read_json(state_path, {}):
        top = gitrepo.worktree_top(cwd) if is_git else None
        jsonfile.write_json(
            state_path,
            {
                "root": root,
                "top": top,
                "head": gitrepo.head(top) if top else None,
                "handoff": handoff_file,
                "started": round(time.time()),
                "offset": 0,
                "prompts": 0,
            },
        )

    if source in ("startup", "resume", "clear"):
        has_handoff = os.path.exists(os.path.join(claudecode.memory_dir(root), handoff_file))
        usage.log_usage(
            "session", "start", repo=rid, session=session_id[:8], has_handoff=has_handoff, handoff=handoff_file
        )
        if is_git:
            arrived = synced_index_lines(root, rid, data.get("transcript_path") or "")
            if arrived:
                # Claude Code loaded MEMORY.md before this hook ran, so pass on what just arrived.
                parts.append(
                    "These auto-memory index lines just arrived from the user's other machines (synced by "
                    "automem-plus). The notes are in your auto-memory folder; read one when it's relevant:\n"
                    + "\n".join(arrived)
                )

    jsonfile.write_json(
        os.path.join(state.state_dir(), "last_session.json"),
        {
            "ts": round(time.time()),
            "repo": rid,
            "rules": [name for name in rules.RULE_FILES if plugin.feature_on(name)],
        },
    )
    if parts:
        print(
            json.dumps(
                {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n\n".join(parts)}}
            )
        )


def synced_index_lines(root, rid, transcript_path):
    """Sync without pushing, and return the MEMORY.md lines that are new to this machine."""
    try:
        transcript_dir = os.path.dirname(transcript_path)
        confirmed = (
            os.path.basename(transcript_dir) == claudecode.project_dir_name(root)
            and os.path.dirname(claudecode.memory_dir(root)) == transcript_dir
        )
        report = sync.run(
            root, push_now=False, lock_wait=LOCK_WAIT, fetch_timeout=FETCH_TIMEOUT, naming_confirmed=confirmed
        )
    except Exception as exc:  # sync must never cost a session its rules
        usage.log_usage("sync", "error", repo=rid, error=type(exc).__name__)
        return []
    return report.index_lines if report else []


if __name__ == "__main__":
    main()
