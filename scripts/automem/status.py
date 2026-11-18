"""The text of ::automem status: is it working here? Everything that otherwise fails silently."""

import os
import time

from automem import claudecode, gitrepo, jsonfile, merge, plugin, reconcile, state, store, sync


def ago(ts, now=None):
    seconds = max(0, (now or time.time()) - ts)
    for size, unit in ((86400, "day"), (3600, "h"), (60, "min")):
        if seconds >= size:
            count = int(seconds // size)
            return f"{count} {unit}{'s' if unit == 'day' and count != 1 else ''} ago"
    return "just now"


OK, WARN, IDLE = "✅", "⚠️", "⚪"  # each status line starts with one: fine, needs a look, nothing there yet
PUSH_TEXT = {
    None: (IDLE, "committed here, not pushed yet"),
    "pushed": (OK, "pushed"),
    "pushed after merge": (OK, "pushed after merging another machine's changes"),
    "push failed": (WARN, "push failed"),
    "conflict": (WARN, "the remote couldn't be merged"),
    "commit failed": (WARN, "commit failed"),
}


def sync_lines(label, record):
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(record.get("ts", 0)))
    mark, result = PUSH_TEXT.get(record.get("push"), (WARN, str(record.get("push"))))
    if record.get("push") is None and not store.has_remote():
        # nothing to push to: the commit in the local store is the whole job
        mark, result = OK, "saved in the local store (it has no remote)"
    if record.get("fetched") is False:
        mark, result = WARN, result + "; the remote couldn't be reached"
    lines = [f"{mark} {label}: {when}, {result}"]
    if record.get("conflicts"):
        lines.append(
            f"      both machines changed {', '.join(record['conflicts'])}; one copy was kept, the other saved"
        )
    if record.get("skipped"):
        lines.append(f"      not synced, looked like a secret: {', '.join(record['skipped'])}")
    return lines


def describe(root=None, handoff_file=None):
    """::automem status: is it working here? Everything that otherwise fails silently. One line per
    thing, each starting with a mark, so it reads at a glance without markup or columns.
    With a project root, sync is reported for that project; the machine's latest sync of another
    project is shown as exactly that, so it can't pass for this one's."""
    latest = jsonfile.read_json(os.path.join(state.state_dir(), "sync_status.json"), {}) or {}
    last = jsonfile.read_json(os.path.join(state.state_dir(), "last_session.json"), {}) or {}
    rules = ", ".join(name.replace("_rule", "").replace("_", " ") for name in last.get("rules") or [])
    lines = [
        f"automem-plus {plugin.version()}" + (f" · {os.path.basename(root)}" if root else ""),
        "",
        f"{OK if rules else WARN} Rules: {rules or 'none'}"
        + (
            f" (injected at the last session start, {time.strftime('%Y-%m-%d %H:%M', time.localtime(last['ts']))})"
            if last.get("ts")
            else ""
        ),
    ]
    rid, own = (gitrepo.repo_hash(root) if root else None), False
    if root:
        if handoff_file:
            path = os.path.join(claudecode.memory_dir(root), handoff_file)
            lines.append(
                f"{OK} Handoff: {handoff_file}, updated {ago(os.path.getmtime(path))}"
                if os.path.exists(path)
                else f"{IDLE} Handoff: none yet (::handoff writes {handoff_file})"
            )
        on, why = store.sync_status(root) if gitrepo.repo_root(root) else (False, "this folder isn't a git repo")
        lines.append(f"{OK if on else IDLE} Sync here: {'on' if on else 'off'}, {why}")
        mine = jsonfile.read_json(sync.status_path(rid), {}) or (latest if latest.get("repo") == rid else {})
        key = gitrepo.remote_key(root)
        base_file = merge.base_path(key, claudecode.memory_dir(root)) if key else ""
        own = bool(mine) or os.path.exists(base_file)
        if mine:
            lines += sync_lines("Last sync of this project", mine)
        elif os.path.exists(
            base_file
        ):  # synced before per-project records existed: the merge base_file is rewritten every sync
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(base_file)))
            lines.append(f"{OK} Last sync of this project: {when}")
        elif on:
            lines.append(f"{IDLE} This project hasn't synced yet; it does at the next session start.")
        waiting = len({entry["file"] for entry in reconcile.unreconciled(root)})
        if waiting:
            lines.append(
                f"{WARN} Waiting for reconcile: {waiting} note{'' if waiting == 1 else 's'} differed between "
                f"machines (::automem reconcile has Claude unite them)"
            )
    if not latest:
        lines.append(f"{IDLE} Sync hasn't run on this machine.")
    elif not root:
        lines += sync_lines("Last sync on this machine", latest)
    elif latest.get("repo") != rid and not own:  # proof the store works, when this project has no sync of its own
        lines += sync_lines("Last sync on this machine (another project)", latest)
    return "\n".join(lines)
