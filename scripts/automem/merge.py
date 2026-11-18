"""Three-way merge between a repo's auto memory folder and its folder in the store.

Notes are opaque files: they are compared by content hash and never parsed. The base is, for
every note, the hashes of the local copy and the store copy as of the last sync, kept in the
state folder per (repo, local memory folder) together with the store's root commit and the last
synced MEMORY.md lines. Git doesn't keep file times, so the merge doesn't rely on them:

- only the local copy changed -> export it (or delete it in the store)
- only the store copy changed -> import it (or delete it here); the local copy is backed up first
- both changed                -> the local copy wins; the store's version is backed up
- no base for a note (first contact, or a base that can't be trusted) -> the newer one wins
  (local file time against the store's last commit of it); the other is backed up
- MEMORY.md: its lines are merged three-way. Lines either side removed stay removed, new lines
  from both sides are kept (one per note), and links to notes that no longer exist are dropped
- a note that looks like it holds a secret is never exported, and neither is its index line

The base isn't trusted when the store was re-created (a different root commit) or when one side
has no notes at all while the base lists some: an emptied folder is never read as "delete all".
Backups go to the state folder's backups/.
"""

import copy
import hashlib
import os
import re

from automem import claudecode, constants, gitrepo, jsonfile, notefiles, secret_scan, state, store, syncreport

LINK_RE = re.compile(r"\]\(([^)]+\.md)\)")


def link_target(line):
    match = LINK_RE.search(line)
    return match.group(1) if match else None


def union_index(primary, secondary):
    """primary's lines in order, then secondary's lines that primary doesn't already have (one per note)."""
    have_lines = {line.strip() for line in primary}
    have_links = {link_target(line) for line in primary} - {None}
    merged = list(primary)
    for line in secondary:
        target = link_target(line)
        if not line.strip() or line.strip() in have_lines or (target and target in have_links):
            continue
        merged.append(line)
        have_lines.add(line.strip())
        if target:
            have_links.add(target)
    return merged


def secret_note(data):
    return data is not None and secret_scan.has_secret(data.decode("utf-8", "replace"))


def store_commit_time(key, rel):
    path = os.path.join("automem", key.replace("/", "__"), rel)
    out = gitrepo.git("log", "-1", "--format=%ct", "--", path, cwd=state.store_dir(), timeout=10).stdout.strip()
    return int(out) if out.isdigit() else 0


def base_path(key, local):
    # Per folder, not just per repo: a second clone at another path has its own (empty) folder
    # and must not read as "every note was deleted here".
    base_id = hashlib.sha1(f"{key}\n{os.path.realpath(local)}".encode()).hexdigest()[:12]
    return os.path.join(state.state_dir(), "synced", base_id + ".json")


def load_base(key, local):
    data = jsonfile.read_json(base_path(key, local), None)
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        return {"root": None, "index": None, "files": {}}
    return data


def trusted(base, local_notes, store_notes, root_commit):
    """Drop a base that would turn an emptied folder or a re-created store into mass deletions."""
    entries = base["files"].values()
    lost_local = any(e.get("l") for e in entries) and not local_notes
    lost_store = any(e.get("s") for e in entries) and not store_notes
    new_store = base.get("root") not in (None, root_commit)
    if lost_local or lost_store or new_store:
        return {"root": root_commit, "index": None, "files": {}}
    return base


class _NoteMerge:
    """Settles one note at a time between a memory folder and its folder in the store."""

    def __init__(self, key, local, store_folder, report):
        self.key, self.local, self.store_folder, self.report = key, local, store_folder, report

    def paths(self, rel):
        return os.path.join(self.local, rel), os.path.join(self.store_folder, rel)

    def digests(self, rel):
        local_path, store_path = self.paths(rel)
        return notefiles.digest(notefiles.read_bytes(local_path)), notefiles.digest(notefiles.read_bytes(store_path))

    def settle(self, rel, was):
        """Bring one note to the same content on both sides. was holds both digests as of the last sync."""
        local_path, store_path = self.paths(rel)
        local_data, store_data = notefiles.read_bytes(local_path), notefiles.read_bytes(store_path)
        local_sum, store_sum = notefiles.digest(local_data), notefiles.digest(store_data)
        if local_sum == store_sum:
            return
        if was is None:
            self._first_contact(rel, local_data, store_data)
            return
        local_changed, store_changed = local_sum != was.get("l"), store_sum != was.get("s")
        if local_changed and store_changed:
            self._both_changed(rel, local_data, store_data)
        elif local_changed:
            self._export(rel, local_data)
        elif store_changed:
            self._import(rel, store_data, local_data)

    def _first_contact(self, rel, local_data, store_data):
        """No base for this note: the two sides have never been compared."""
        if local_data is None:
            self._import(rel, store_data, None)
        elif store_data is None:
            self._export(rel, local_data)
        elif os.path.getmtime(self.paths(rel)[0]) >= store_commit_time(self.key, rel):
            self.report.conflicts.append(rel)
            self._keep_local(rel, local_data, store_data)
        else:
            self.report.conflicts.append(rel)
            self._lost(rel, "store", self._import(rel, store_data, local_data))

    def _both_changed(self, rel, local_data, store_data):
        self.report.conflicts.append(rel)
        if local_data is None:
            self._import(rel, store_data, None)  # deleted here, edited there: keep the content
        else:
            self._keep_local(rel, local_data, store_data)

    def _export(self, rel, local_data):
        """Copy the local note into the store; None deletes the store's copy."""
        if secret_note(local_data):
            self.report.skipped.append(rel)
            return
        notefiles.put(self.paths(rel)[1], local_data)
        self.report.exported.append(rel)

    def _import(self, rel, store_data, local_data):
        """Copy the store's note into the folder (None deletes it), saving the local copy first."""
        saved = notefiles.backup(self.key, rel, local_data, "local-before-import")
        self.report.backups.append(saved)
        notefiles.put(self.paths(rel)[0], store_data)
        (self.report.deleted_here if store_data is None else self.report.imported).append(rel)
        return saved

    def _keep_local(self, rel, local_data, store_data):
        saved = notefiles.backup(self.key, rel, store_data, "store")
        self.report.backups.append(saved)
        self._lost(rel, "local", saved)
        self._export(rel, local_data)

    def _lost(self, rel, kept, saved):
        """Both copies had content and one lost: remember where it went, for /automem-plus:reconcile."""
        if saved:
            self.report.lost.append(syncreport.LostCopy(rel, kept, saved))


def merge_folders(root, key, base):
    """Three-way merge between the auto memory folder and the store folder. Returns (report, new base)."""
    local, store_folder = claudecode.memory_dir(root), store.store_folder(key)
    report = syncreport.SyncReport()
    local_notes, store_notes = notefiles.files(local), notefiles.files(store_folder)
    root_commit = store.store_root_commit()
    base = trusted(copy.deepcopy(base), local_notes, store_notes, root_commit)
    base["root"] = root_commit
    known = base["files"]
    notes = _NoteMerge(key, local, store_folder, report)
    for rel in sorted(local_notes | store_notes | set(known)):
        notes.settle(rel, known.get(rel))
        local_sum, store_sum = notes.digests(rel)
        if local_sum is None and store_sum is None:
            known.pop(rel, None)
        else:
            known[rel] = {"l": local_sum, "s": store_sum}
    report.index_lines, base["index"] = merge_index(key, local, store_folder, base.get("index"), known, report)
    report.backups = [path for path in report.backups if path]
    return report, base


def merge_index(key, local, store_folder, base_lines, known, report):
    """Three-way merge of MEMORY.md lines. Returns (lines new to this session, the merged lines)."""
    lp, sp = os.path.join(local, constants.INDEX_FILE), os.path.join(store_folder, constants.INDEX_FILE)
    ldata, sdata = notefiles.read_bytes(lp), notefiles.read_bytes(sp)
    if ldata is None and sdata is None:
        return [], None
    mine, theirs = notefiles.lines_of(ldata), notefiles.lines_of(sdata)
    skipped = {rel for rel, v in known.items() if v.get("l") and not v.get("s")}

    def private(line):  # never in the store copy, so its absence there means nothing
        return secret_scan.has_secret(line) or link_target(line) in skipped

    was = set(base_lines) if base_lines is not None else None
    theirs_set = set(theirs)
    merged = [
        line
        for line in mine
        if line.strip() and not (was is not None and line in was and line not in theirs_set and not private(line))
    ]
    have, links = set(merged), {link_target(line) for line in merged} - {None}
    for line in theirs:
        target = link_target(line)
        if not line.strip() or line in have or (was is not None and line in was) or (target and target in links):
            continue
        merged.append(line)
        have.add(line)
        if target:
            links.add(target)
    existing = notefiles.files(local)
    merged = [line for line in merged if not link_target(line) or link_target(line) in existing]

    if merged != mine:
        if set(mine) - set(merged):
            report.backups.append(notefiles.backup(key, constants.INDEX_FILE, ldata, "local-before-import"))
        notefiles.put(lp, ("\n".join(merged) + "\n").encode())
        report.imported.append(constants.INDEX_FILE)
    public = [line for line in merged if not private(line)]
    if public != theirs:
        notefiles.put(sp, ("\n".join(public) + ("\n" if public else "")).encode())
        report.exported.append(constants.INDEX_FILE)
    already_here = set(mine)
    return [line for line in merged if line not in already_here], merged
