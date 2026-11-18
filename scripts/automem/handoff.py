"""The handoff note: what it's called for a branch, and what Claude is told when the user runs ::handoff."""

import os
import re

from automem import constants, gitrepo

HANDOFF_CONTEXT = (
    "The user ran ::handoff. Update the handoff note `{name}` in your auto-memory folder now, following "
    "the handoff rule (Goal, Where we are, Tried and failed, Open decisions, Next steps), keep its "
    "MEMORY.md line, then confirm in one short line."
)


def handoff_name(branch_name):
    """One handoff note per branch, because worktrees share one memory folder and run in parallel."""
    if not branch_name:
        return constants.HANDOFF_FILE
    slug = re.sub(r"[^a-z0-9]+", "-", branch_name.lower()).strip("-")[:50] or "branch"
    return f"handoff-{slug}.md"


def is_handoff(name):
    return name == constants.HANDOFF_FILE or (name.startswith("handoff-") and name.endswith(".md"))


def orphaned_handoffs(folder, cwd):
    """Handoff notes whose branch no longer exists here (merged or deleted)."""
    if not os.path.isdir(folder):
        return []
    live = {handoff_name(b) for b in gitrepo.local_branches(cwd)}
    return sorted(n for n in os.listdir(folder) if n.startswith("handoff-") and n.endswith(".md") and n not in live)
