"""One-line notices for the Stop line. They cost no tokens: the user sees them, Claude doesn't."""

import os
import time

from automem import constants, gitrepo, handoff, jsonfile, plugin, reconcile, state, usage


def staleness_line(root, folder, session_state):
    """Once per new commit: the session committed, and the handoff note is older than that commit."""
    top = session_state.get("top")
    if not plugin.feature_on("staleness_nudge") or not top or not session_state.get("head"):
        return None
    current, committed = gitrepo.head(top), gitrepo.last_commit_time(top)
    no_new_commit = not current or current == session_state["head"]
    if no_new_commit or not committed or committed < session_state.get("started", 0):
        return None
    if not session_state.get("committed_logged"):
        session_state["committed_logged"] = True
        usage.log_usage("session", "committed", repo=gitrepo.repo_hash(root), session=session_state.get("session", ""))
    if session_state.get("nudged_for") == current:
        return None
    handoff_path = os.path.join(folder, handoff.handoff_name(gitrepo.branch(top)))
    if os.path.exists(handoff_path) and os.path.getmtime(handoff_path) >= committed:
        return None
    session_state["nudged_for"] = current
    usage.log_usage("staleness_nudge", "shown", repo=gitrepo.repo_hash(root), session=session_state.get("session", ""))
    return (
        "📝 New commits since this session started, but the handoff note is older than the latest one. "
        "Say /automem-plus:handoff to update it."
    )


def version_line(session_state):
    """When the Claude Code version in the transcript changes, offer the canary."""
    version = session_state.get("version")
    if not version:
        return None
    path = os.path.join(state.state_dir(), "version.json")
    previous = (jsonfile.read_json(path, {}) or {}).get("version")
    if previous == version:
        return None
    jsonfile.write_json(path, {"version": version, "seen": round(time.time())})
    if not previous:
        return None  # the first version this machine has seen: nothing changed
    return (
        f"🔬 Claude Code updated ({previous} → {version}). /automem-plus:canary checks whether built-in "
        f"auto memory now covers what automem-plus adds ({constants.CANARY_COST})."
    )


def review_line():
    """Once a month, when there is enough in the usage log to judge by."""
    events = usage.read_usage()
    if len(events) < constants.REVIEW_NUDGE_MIN_EVENTS:
        return None
    path = os.path.join(state.state_dir(), "review.json")
    seen = jsonfile.read_json(path, {}) or {}
    since = max(seen.get("reviewed", 0), seen.get("nudged", 0)) or events[0].get("ts", time.time())
    if time.time() - since < constants.REVIEW_NUDGE_AFTER_DAYS * constants.DAY:
        return None
    seen["nudged"] = round(time.time())
    jsonfile.write_json(path, seen)
    return "📊 A month of memory usage is logged: /automem-plus:review shows what's worth keeping."


def reconcile_line(root):
    """Once per batch of file conflicts that nobody has reconciled yet."""
    try:
        return reconcile.nudge_line(root)
    except Exception:  # a broken conflict log must never cost the Stop line
        return None
