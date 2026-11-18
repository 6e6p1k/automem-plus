"""/automem-plus:reconcile: have Claude unite memory that was merged from more than one machine.

Sync merges file by file and never looks inside a note, so two machines can leave the same fact
under two names, notes that disagree, or a copy that lost a same-name conflict sitting in the
backups. This command costs no model call of its own: it hands the session's Claude the copies
that lost, the notes that arrived from elsewhere, and the rules (rules/reconcile.md). Claude
proposes, the user agrees, Claude edits; the result syncs like any other change.
"""

import os
import time

from automem import claudecode, constants, gitrepo, jsonfile, state, store, sync, usage

STATE_FILE = "reconcile.json"  # {store folder name: {"offered": ts, "nudged": ts}}
MAX_ARRIVED = 60
MAX_QUOTED, MAX_COPY_CHARS = 20, 6000  # the copies are quoted in full: a session often can't read the state folder


def _state():
    return jsonfile.read_json(os.path.join(state.state_dir(), STATE_FILE), {}) or {}


def _mark(root, field):
    key = gitrepo.remote_key(root)
    if not key:
        return
    seen = _state()
    seen.setdefault(store.folder_name(key), {})[field] = round(time.time())
    jsonfile.write_json(os.path.join(state.state_dir(), STATE_FILE), seen)


def _seen(root):
    key = gitrepo.remote_key(root)
    return (_state().get(store.folder_name(key)) or {}) if key else {}


def unreconciled(root):
    """Lost copies nobody has handed to Claude yet."""
    return sync.lost_copies(root, _seen(root).get("offered", 0))


def arrived(root, since):
    """Notes that came from another machine after since and are still in the folder."""
    rid, folder = gitrepo.repo_hash(root), claudecode.memory_dir(root)
    names = {
        u.get("file")
        for u in usage.read_usage()
        if u.get("feature") == "sync"
        and u.get("event") == "imported"
        and u.get("repo") == rid
        and u.get("ts", 0) > since
    }
    return sorted(n for n in names if n and os.path.exists(os.path.join(folder, n)))


def context(root, handoff_file, show_all=False):
    """The text Claude gets. Marks what it lists as handed over, so the next run starts after it."""
    offered = _seen(root).get("offered", 0)
    since = 0 if show_all else offered
    lost = sync.lost_copies(root, since)
    if lost:
        lines = [
            "Copies that lost a file conflict (the same file name was written on two machines; one copy was "
            "kept in the folder, the other was saved):"
        ]
        for number, entry in enumerate(lost):
            kept = (
                "this machine's copy was kept; the other machine's copy"
                if entry["kept"] == "local"
                else "the other machine's copy was kept; this machine's copy"
            )
            line = f"- `{entry['file']}`: {kept} is saved at `{entry['backup']}`"
            if number < MAX_QUOTED:
                try:
                    with open(entry["backup"], errors="replace") as f:
                        copy = f.read()
                except OSError:
                    copy = None
                if copy is not None:
                    cut = " (cut here; the rest is in the file)" if len(copy) > MAX_COPY_CHARS else ""
                    line += f" and reads:\n````\n{copy[:MAX_COPY_CHARS].rstrip()}\n````{cut}"
            lines.append(line)
        conflicts_text = "\n".join(lines)
    else:
        conflicts_text = "No copy lost a file conflict" + (
            " since the last reconcile." if since else " on this machine."
        )
    earlier = len(sync.lost_copies(root, 0)) - len(lost)
    if earlier:
        conflicts_text += (
            f"\n{earlier} saved cop{'y was' if earlier == 1 else 'ies were'} handed over in an earlier "
            f"run; `/automem-plus:reconcile all` lists them again."
        )
    names = arrived(root, since)
    if names:
        shown = ", ".join(f"`{n}`" for n in names[:MAX_ARRIVED]) + (" and more" if len(names) > MAX_ARRIVED else "")
        arrived_text = (
            f"Notes that arrived from another machine: {shown}. Compare them with the notes that were already here."
        )
    else:
        arrived_text = "No notes arrived from another machine" + (" since the last reconcile." if since else ".")
    with open(os.path.join(constants.RULES_DIR, "reconcile.md")) as f:
        text = f.read().strip()
    _mark(root, "offered")
    usage.log_usage("reconcile", "command", repo=gitrepo.repo_hash(root), conflicts=len(lost), arrived=len(names))
    return (
        text.replace("{folder}", claudecode.memory_dir(root))
        .replace("{handoff_file}", handoff_file)
        .replace("{arrived}", arrived_text)
        .replace("{conflicts}", conflicts_text)  # last: it quotes notes, whose text must not be substituted into
    )


def nudge_line(root):
    """Stop line, once per batch of conflicts: copies lost a conflict and nobody has looked yet."""
    seen = _seen(root)
    waiting = sync.lost_copies(root, max(seen.get("offered", 0), seen.get("nudged", 0)))
    if not waiting:
        return None
    _mark(root, "nudged")
    count = len({entry["file"] for entry in waiting})
    return (
        f"🔀 {count} note{'' if count == 1 else 's'} differed between this machine and the memory store; both "
        f"copies are kept. /automem-plus:reconcile has Claude unite them."
    )
