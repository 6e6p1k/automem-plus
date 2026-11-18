"""Moving the store's commits: fetch, commit, push, and settling a rejected push.

Git never merges inside a note (.gitattributes marks notes -merge). When a push is rejected,
the remote is merged in and each note both machines changed is settled here: this machine's copy
wins and the other is backed up; a note deleted here but edited there keeps its content. There
is no reset, so nothing unpushed is ever dropped.
"""

import glob
import os
import time

from automem import constants, gitrepo, merge, notefiles, state, store, syncreport


def clear_stale_git_locks():
    """Locks left by a git process that was killed (index.lock, ref locks)."""
    for lock in glob.glob(os.path.join(state.store_dir(), ".git", "**", "*.lock"), recursive=True):
        try:
            if time.time() - os.path.getmtime(lock) > 120:
                os.remove(lock)
        except OSError:
            pass


def fetch_and_fast_forward(timeout):
    """Bring the store up to date when that's a fast-forward. Never merges here."""
    if not store.has_remote() or not store.has_upstream():
        return True
    store_path = state.store_dir()
    if gitrepo.git("fetch", "-q", "origin", cwd=store_path, timeout=timeout).returncode != 0:
        return False
    behind = gitrepo.git("rev-list", "--count", "HEAD..@{u}", cwd=store_path, timeout=5).stdout.strip()
    ahead = gitrepo.git("rev-list", "--count", "@{u}..HEAD", cwd=store_path, timeout=5).stdout.strip()
    if behind not in ("", "0") and ahead in ("", "0"):
        return gitrepo.git("merge", "-q", "--ff-only", "@{u}", cwd=store_path, timeout=10).returncode == 0
    return True


def commit(key):
    store_path = state.store_dir()
    store.ensure_attributes()
    if gitrepo.git("add", "-A", "--", "automem", ".gitattributes", cwd=store_path).returncode != 0:
        return False
    staged = gitrepo.git("diff", "--cached", "--quiet", cwd=store_path).returncode != 0
    if staged and gitrepo.git(*store.GIT_ID, "commit", "-q", "-m", f"automem: {key}", cwd=store_path).returncode != 0:
        return False
    # committed only if nothing under automem/ is left uncommitted
    return not gitrepo.git("status", "--porcelain", "--", "automem", ".gitattributes", cwd=store_path).stdout.strip()


def show(stage, path):
    res = gitrepo.git("show", f":{stage}:{path}", cwd=state.store_dir(), timeout=10)
    return res.stdout.encode() if res.returncode == 0 else None


def merge_upstream(report):
    """Merge the remote into the store, settling each note both machines changed ourselves:
    our copy wins and theirs is backed up; deleted here but edited there keeps their content.
    No reset, so nothing unpushed is ever dropped. Returns True when the merge was committed."""
    store_path = state.store_dir()
    res = gitrepo.git(
        *store.GIT_ID, "merge", "-q", "--no-ff", "--no-commit", "--autostash", "@{u}", cwd=store_path, timeout=30
    )
    conflicted = gitrepo.git("diff", "--name-only", "--diff-filter=U", cwd=store_path).stdout.split()
    if res.returncode != 0 and not conflicted:
        gitrepo.git("merge", "--abort", cwd=store_path)
        return False
    for path in conflicted:
        ours, theirs = show(2, path), show(3, path)
        full = os.path.join(store_path, path)
        parts = path.split("/", 2)  # automem/<repo folder or _rules>/<file>
        about = report.rules if report.rules is not None and parts[1:2] == [constants.RULES_STORE_FOLDER] else report
        if path.endswith(constants.INDEX_FILE) and ours is not None and theirs is not None:
            notefiles.put(
                full,
                ("\n".join(merge.union_index(notefiles.lines_of(ours), notefiles.lines_of(theirs))) + "\n").encode(),
            )
        elif ours is not None:
            notefiles.put(full, ours)
            saved = notefiles.backup("conflict", path, theirs, "store")
            about.backups.append(saved)
            if saved and len(parts) == 3:
                about.lost.append(syncreport.LostCopy(parts[2], "local", saved, folder=parts[1]))
        else:
            notefiles.put(full, theirs)
        about.conflicts.append(os.path.basename(path))
        gitrepo.git("add", "-A", "--", path, cwd=store_path)
    if gitrepo.git(*store.GIT_ID, "commit", "-q", "--no-edit", cwd=store_path).returncode != 0:
        gitrepo.git("merge", "--abort", cwd=store_path)
        return False
    return True


def push(report):
    """'pushed', 'pushed after merge', 'conflict' (the merge couldn't be settled), or 'push failed'."""
    store_path = state.store_dir()
    if not store.has_upstream():
        ok = gitrepo.git("push", "-q", "-u", "origin", "HEAD", cwd=store_path, timeout=30).returncode == 0
        return "pushed" if ok else "push failed"
    if gitrepo.git("push", "-q", cwd=store_path, timeout=30).returncode == 0:
        return "pushed"
    if gitrepo.git("fetch", "-q", "origin", cwd=store_path, timeout=30).returncode != 0:
        return "push failed"
    if not merge_upstream(report):
        return "conflict"
    return (
        "pushed after merge" if gitrepo.git("push", "-q", cwd=store_path, timeout=30).returncode == 0 else "push failed"
    )
