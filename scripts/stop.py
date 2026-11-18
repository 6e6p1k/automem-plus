#!/usr/bin/env python3
"""Stop hook: log which memory notes were read or written, show nudges, start a sync.

Costs no tokens and runs no model: everything comes from the transcript and git. Whatever it
says goes to the Stop line (systemMessage), never to Claude.
"""

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from automem import (  # noqa: E402
    claudecode,
    constants,
    gitrepo,
    jsonfile,
    notefiles,
    nudges,
    session,
    state,
    store,
    transcript,
    usage,
)


def start_sync(root, folder, session_state):
    """Sync in the background when a note or a promoted rule changed since this session last synced."""
    if not os.path.isdir(folder):
        return
    rules = claudecode.rules_dir()
    changed = [os.path.join(base, name) for base, _, names in os.walk(folder) for name in names]
    changed += [os.path.join(rules, name) for name in notefiles.rule_files(rules)]
    if os.path.isdir(rules):
        changed.append(rules)  # a deleted rule only shows in the folder's own time
    newest = max((os.path.getmtime(path) for path in changed), default=0)
    if newest <= session_state.get("synced", 0):
        return
    try:
        if not store.sync_status(root)[0]:
            return
    except Exception:
        return
    session_state["synced"] = newest
    subprocess.Popen(
        [sys.executable, os.path.join(constants.SCRIPTS_DIR, "sync_repo.py"), root, "--push"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def main():
    if state.disabled():
        return
    data = claudecode.hook_input()
    session_id = data.get("session_id", "")
    cwd = session.start_dir(data)
    root, is_git = gitrepo.project_root(cwd)
    if not root or not claudecode.auto_memory_on(root):
        return
    state_path = session.session_state_path(session_id)
    session_state = jsonfile.read_json(state_path, {}) or {
        "root": root,
        "started": round(time.time()),
        "offset": 0,
        "prompts": 0,
    }
    session_state["session"] = session_id[:8]
    folder = claudecode.memory_dir(root)
    rid = usage.remember_repo(root)

    before = session_state.get("prompts", 0)
    for event, rel, prompt_no, tool_id in transcript.scan_transcript(
        data.get("transcript_path") or "", session_state, folder
    ):
        usage.log_usage("note", event, repo=rid, session=session_id[:8], file=rel, prompt=prompt_no, id=tool_id)
    if before < constants.ENGAGED_PROMPTS <= session_state.get("prompts", 0):
        usage.log_usage("session", "engaged", repo=rid, session=session_id[:8])

    lines = [
        line
        for line in (
            nudges.staleness_line(root, folder, session_state) if is_git else None,
            nudges.reconcile_line(root) if is_git else None,
            nudges.version_line(session_state),
            nudges.review_line(),
        )
        if line
    ]
    if is_git:
        start_sync(root, folder, session_state)
    jsonfile.write_json(state_path, session_state)
    if lines:
        print(json.dumps({"systemMessage": "\n".join(lines)}))


if __name__ == "__main__":
    main()
