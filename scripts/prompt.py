#!/usr/bin/env python3
"""UserPromptSubmit hook: the :: commands of automem-plus.

::handoff and ::automem reconcile reach Claude with extra context. Every other ::automem command
is answered here (see automem/commands.py) and never reaches Claude.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from automem import claudecode, commands, gitrepo, handoff, reconcile, session, state, usage  # noqa: E402


def block(text):
    """Answer the user directly; the prompt doesn't reach Claude."""
    print(json.dumps({"decision": "block", "reason": text}))


def add_context(text):
    """Let the prompt through to Claude with extra instructions."""
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}))


def main():
    if state.disabled():
        return
    data = claudecode.hook_input()
    prompt = (data.get("prompt") or "").strip()
    if not prompt.startswith("::"):
        return
    name, _, rest = prompt[2:].partition(" ")
    name, words = name.lower(), rest.split()
    if name not in ("handoff", "automem"):
        return
    cwd = session.start_dir(data)
    root, is_git = gitrepo.project_root(cwd)
    handoff_file = handoff.handoff_name(gitrepo.branch(cwd) if is_git else None)
    if name == "handoff":
        if root:
            usage.log_usage(
                "handoff_rule", "command", repo=gitrepo.repo_hash(root), session=data.get("session_id", "")[:8]
            )
        add_context(handoff.HANDOFF_CONTEXT.format(name=handoff_file))
    elif words and words[0].lower() == "reconcile":
        if not root or not claudecode.auto_memory_on(root):
            return block("Auto memory is off here, so there's nothing to reconcile.")
        add_context(reconcile.context(root, handoff_file, show_all=[w.lower() for w in words[1:2]] == ["all"]))
    else:
        block(commands.run(rest.strip(), cwd))


if __name__ == "__main__":
    main()
