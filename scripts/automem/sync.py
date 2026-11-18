"""Sync one repo's auto memory folder with the store, and keep the records of what happened.

How the pieces fit: store.py says whether a repo syncs and where its folder in the store is,
merge.py does the three-way merge between the two folders, and transport.py moves commits to and
from the store's remote. Everything here runs under one lock, so two sessions never merge at once.
"""

import json
import os
import time

from automem import claudecode, constants, gitrepo, jsonfile, locks, merge, state, store, transport, usage

MERGED_FIELDS = ("imported", "exported", "deleted_here", "conflicts", "backups", "skipped", "index_lines", "lost")


def run(root, push_now=False, lock_wait=60, fetch_timeout=20, naming_confirmed=False):
    """One full sync of this repo's notes. Returns the report, or None when sync is off or busy.

    Notes are only written into a project folder Claude Code already made, or whose name the
    session's own transcript path confirms (naming_confirmed), so a wrong guess at the folder
    name never fills a folder nothing reads."""
    on, _why = store.sync_status(root)
    local = claudecode.memory_dir(root)
    if not on or not (os.path.isdir(os.path.dirname(local)) or naming_confirmed):
        return None
    key = gitrepo.remote_key(root)
    lock = locks.Lock("sync", wait=lock_wait)
    if not lock.acquire():
        return None
    try:
        transport.clear_stale_git_locks()
        fetched = transport.fetch_and_fast_forward(fetch_timeout)
        report, base = merge.merge_folders(root, key, merge.load_base(key, local))
        jsonfile.write_json(merge.base_path(key, local), base)
        report.fetched = fetched
        report.push = None if transport.commit(key) else "commit failed"
        if push_now and report.push is None and store.has_remote():
            report.push = transport.push(report)
            if report.push == "pushed after merge":
                merge_again(root, key, local, report)
    finally:
        lock.release()
    record(root, report)
    return report


def merge_again(root, key, local, report):
    """The store now holds the other machine's changes too: bring them into the local folder."""
    again, base = merge.merge_folders(root, key, merge.load_base(key, local))
    jsonfile.write_json(merge.base_path(key, local), base)
    for name in MERGED_FIELDS:
        getattr(report, name).extend(getattr(again, name))
    if transport.commit(key) and again.exported:
        transport.push(report)


def status_path(rid):
    return os.path.join(state.state_dir(), "sync_status", rid + ".json")


def lost_copy_log():
    return os.path.join(state.state_dir(), "lost_copies.jsonl")


def record(root, report):
    """Write down what this sync did: the status ::automem status reads, the copies that lost a
    conflict (for ::automem reconcile), and the usage log."""
    rid = gitrepo.repo_hash(root)
    status = {
        "ts": round(time.time()),
        "repo": rid,
        "push": report.push,
        "fetched": report.fetched,
        "conflicts": report.conflicts,
        "skipped": report.skipped,
        "backups": report.backups,
    }
    jsonfile.write_json(os.path.join(state.state_dir(), "sync_status.json"), status)  # the latest sync of any project
    jsonfile.write_json(status_path(rid), status)
    first = os.path.join(state.state_dir(), "sync_first.json")
    if not os.path.exists(first):
        jsonfile.write_json(first, {"ts": status["ts"]})
    if report.lost:
        own_folder = store.folder_name(gitrepo.remote_key(root))
        with open(lost_copy_log(), "a") as f:
            for copy in report.lost:
                f.write(
                    json.dumps(
                        {
                            "ts": status["ts"],
                            "folder": copy.folder or own_folder,
                            "file": copy.file,
                            "kept": copy.kept,
                            "backup": copy.backup,
                        }
                    )
                    + "\n"
                )
    for rel in report.imported:
        if rel != constants.INDEX_FILE:
            usage.log_usage("sync", "imported", repo=rid, file=rel)
    for rel in report.skipped:
        usage.log_usage("sync", "skipped_secret", repo=rid, file=rel)


def lost_copies(root, since=0):
    """The copies that lost a file conflict for this repo on this machine after since, as
    {ts, folder, file, kept: 'local' or 'store', backup: where the copy not kept was saved}.
    Machine-local: the copy that lost is only on the machine where the two met."""
    key = gitrepo.remote_key(root)
    if not key:
        return []
    found = []
    try:
        with open(lost_copy_log()) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue  # a half-written line from a killed sync
                if (
                    entry.get("folder") == store.folder_name(key)
                    and entry.get("ts", 0) > since
                    and os.path.exists(entry.get("backup") or "")
                ):
                    found.append(entry)
    except OSError:
        pass
    return found
