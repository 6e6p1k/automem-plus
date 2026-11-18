#!/usr/bin/env python3
"""UserPromptSubmit hook: the plugin's commands, typed as /automem-plus:<name> or ::automem <name>.

handoff and reconcile reach Claude with extra context. Every other command is answered here
(see automem/commands.py) and never reaches Claude.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from automem import claudecode, commands, constants, gitrepo, handoff, reconcile, session, state, usage  # noqa: E402


def block(text):
    """Answer the user directly; the prompt doesn't reach Claude."""
    print(json.dumps({"decision": "block", "reason": text, "suppressOriginalPrompt": True}))


def add_context(text):
    """Let the prompt through to Claude with extra instructions."""
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}))


def parse(prompt):
    """(command, arguments) when the prompt is one of the plugin's commands, else None."""
    slash = f"/{constants.PLUGIN_NAME}:"
    if prompt.startswith(slash):
        words = prompt[len(slash) :].split()
    elif prompt.startswith("::"):
        words = prompt[2:].split()
        first = words[0].lower() if words else ""
        if first == "automem":
            words = words[1:]
        elif first == "handoff":
            words = ["handoff"]
        else:
            return None
    else:
        return None
    return (words[0].lower(), words[1:]) if words else ("help", [])


def main():
    if state.disabled():
        return
    data = claudecode.hook_input()
    parsed = parse((data.get("prompt") or "").strip())
    if not parsed:
        return
    command, args = parsed
    cwd = session.start_dir(data)
    root, is_git = gitrepo.project_root(cwd)
    handoff_file = handoff.handoff_name(gitrepo.branch(cwd) if is_git else None)
    if command == "handoff":
        if root:
            usage.log_usage(
                "handoff_rule", "command", repo=gitrepo.repo_hash(root), session=data.get("session_id", "")[:8]
            )
        add_context(handoff.HANDOFF_CONTEXT.format(name=handoff_file))
    elif command == "reconcile":
        if not root or not claudecode.auto_memory_on(root):
            return block("Auto memory is off here, so there's nothing to reconcile.")
        add_context(reconcile.context(root, handoff_file, show_all=[a.lower() for a in args[:1]] == ["all"]))
    else:
        block(commands.run(command, args, cwd))


if __name__ == "__main__":
    main()
