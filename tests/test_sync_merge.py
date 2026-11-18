import json
import os
import shutil
import subprocess
import time

from automem import claudecode, locks, merge, store, sync
from helpers import FAKE_API_KEY_LINE, FAKE_PASSWORD_LINE, git, read, run_hook, write


def test_union_index_dedupes_by_link():
    a = ["- [Uv](use-uv.md) — run with uv", "- [Deploy](deploy.md) — orchid"]
    b = ["- [Uv](use-uv.md) — run Python with uv (reworded)", "- [CI](ci.md) — Fridays", ""]
    assert merge.union_index(a, b) == a + ["- [CI](ci.md) — Fridays"]


def test_both_machines_add_notes_and_converge(machines):
    a, b = machines("a"), machines("b")
    a.use().write("ci.md", "CI on Fridays\n")
    a.write("MEMORY.md", "- [CI](ci.md) — Fridays\n")
    b.use().write("deploy.md", "Deploy to orchid\n")
    b.write("MEMORY.md", "- [Deploy](deploy.md) — orchid\n")
    assert a.sync().push == "pushed"
    assert b.sync().push == "pushed"  # B was behind: its first fetch fast-forwards, then it merges
    a.sync()
    for m in (a, b):
        m.use()
        assert m.read("ci.md") == "CI on Fridays\n" and m.read("deploy.md") == "Deploy to orchid\n"
        assert "Fridays" in m.read("MEMORY.md") and "orchid" in m.read("MEMORY.md")


def test_concurrent_pushes_still_converge(machines):
    a, b = machines("a"), machines("b")
    a.use().write("ci.md", "CI on Fridays\n")
    a.write("MEMORY.md", "- [CI](ci.md) — Fridays\n")
    b.use().write("deploy.md", "Deploy to orchid\n")
    b.write("MEMORY.md", "- [Deploy](deploy.md) — orchid\n")
    # B commits before seeing A's push: simulate by syncing B without pushing first
    b.use()
    sync.run(b.repo, push_now=False, lock_wait=1)
    assert a.sync().push == "pushed"
    report = b.sync()  # B is now ahead and behind: merge, with MEMORY.md as a union
    assert report.push == "pushed after merge", report
    a.sync()
    for m in (a, b):
        m.use()
        index = m.read("MEMORY.md")
        assert "Fridays" in index and "orchid" in index
        assert m.read("ci.md") and m.read("deploy.md")


def test_both_edit_handoff_local_wins_and_other_version_is_kept(machines):
    a, b = machines("a"), machines("b")
    a.use().write("handoff.md", "v1\n")
    a.sync()
    b.sync()
    assert b.use().read("handoff.md") == "v1\n"
    a.use().write("handoff.md", "A's v2\n")
    a.sync()
    b.use().write("handoff.md", "B's v2\n")
    report = b.sync()
    assert b.read("handoff.md") == "B's v2\n" and "handoff.md" in report.conflicts
    saved = [p for p in report.backups if p]
    assert saved and read(saved[0]) == "A's v2\n"  # nothing lost
    a.sync()
    assert a.use().read("handoff.md") == "B's v2\n"  # A hadn't changed it since, so it takes B's


def test_fresh_store_clone_never_overwrites_a_newer_local_note(machines):
    a, b = machines("a"), machines("b")
    a.use().write("ci.md", "old fact\n")
    a.sync()
    b.use().write("ci.md", "newer fact written here\n")  # B has never synced: no base
    report = b.sync()
    assert b.read("ci.md") == "newer fact written here\n"
    assert any(p and read(p) == "old fact\n" for p in report.backups)


def test_deletion_propagates_with_a_backup(machines):
    a, b = machines("a"), machines("b")
    a.use().write("ci.md", "CI on Fridays\n")
    a.write("MEMORY.md", "- [CI](ci.md) — Fridays\n- [Uv](uv.md) — uv\n")
    a.write("uv.md", "use uv\n")
    a.sync()
    b.sync()
    assert b.use().read("ci.md")
    os.remove(os.path.join(a.use().mem, "ci.md"))
    a.write("MEMORY.md", "- [Uv](uv.md) — uv\n")
    a.sync()
    report = b.sync()
    assert b.use().read("ci.md") is None and "ci.md" in report.deleted_here
    assert "Fridays" not in b.read("MEMORY.md") and "uv" in b.read("MEMORY.md")
    assert any(p and read(p) == "CI on Fridays\n" for p in report.backups)


def test_secrets_and_their_index_lines_stay_local(machines):
    a, b = machines("a"), machines("b")
    a.use().write("leak.md", FAKE_API_KEY_LINE + "\n")
    a.write("ok.md", "token: refresh it every hour\n")  # prose, not a secret
    a.write("MEMORY.md", f"- [Leak](leak.md) — the key\n- [Ok](ok.md) — tokens\n- {FAKE_PASSWORD_LINE}\n")
    report = a.sync()
    assert report.skipped == ["leak.md"]
    b.sync()
    assert b.use().read("leak.md") is None and b.read("ok.md")
    index = b.read("MEMORY.md")
    assert "leak.md" not in index and "hunter2" not in index and "ok.md" in index
    assert a.use().read("leak.md")  # still there locally


def test_new_index_lines_are_reported_for_the_session(machines):
    a, b = machines("a"), machines("b")
    a.use().write("ci.md", "CI on Fridays\n")
    a.write("MEMORY.md", "- [CI](ci.md) — Fridays only\n")
    a.sync()
    b.use().write("MEMORY.md", "- [Uv](uv.md) — use uv\n")
    b.write("uv.md", "use uv\n")
    out = run_hook("session_start.py", {"session_id": "b1", "cwd": b.repo, "source": "startup"})
    assert "Fridays only" in out["hookSpecificOutput"]["additionalContext"]


def test_busy_lock_skips_instead_of_waiting(machines):
    a = machines("a")
    a.use()
    lock = locks.Lock("sync", wait=0)
    assert lock.acquire()
    try:
        started = time.time()
        assert sync.run(a.repo, push_now=False, lock_wait=0.5) is None
        assert time.time() - started < 3
    finally:
        lock.release()


def test_first_session_on_a_new_clone_imports_when_the_transcript_confirms_the_folder(machines):
    a, b = machines("a"), machines("b")
    a.use().write("ci.md", "CI on Fridays\n")
    a.write("MEMORY.md", "- [CI](ci.md) — Fridays only\n")
    a.sync()
    b.use()
    project = os.path.dirname(b.mem)

    shutil.rmtree(project)  # brand-new clone: Claude Code hasn't made the folder yet
    wrong = {
        "session_id": "b1",
        "cwd": b.repo,
        "source": "startup",
        "transcript_path": os.path.join(str(b.config), "projects", "something-else", "b1.jsonl"),
    }
    out = run_hook("session_start.py", wrong)
    assert "Fridays" not in json.dumps(out) and not os.path.isdir(project)
    right = dict(wrong, session_id="b2", transcript_path=os.path.join(project, "b2.jsonl"))
    out = run_hook("session_start.py", right)
    assert "Fridays only" in out["hookSpecificOutput"]["additionalContext"]
    assert b.read("ci.md") == "CI on Fridays\n"


def test_second_clone_on_the_same_machine_imports_instead_of_deleting(machines, env):
    a = machines("a")
    a.use().write("ci.md", "CI on Fridays\n")
    a.write("MEMORY.md", "- [CI](ci.md) — Fridays\n")
    a.sync()
    second = env / "a" / "code" / "tally-second"
    subprocess.run(["git", "clone", "-q", a.repo, str(second)], check=True)
    git("remote", "set-url", "origin", "https://github.com/me/tally", cwd=second)
    root = os.path.realpath(second)
    os.makedirs(claudecode.memory_dir(root))
    report = sync.run(root, push_now=True, lock_wait=1)
    assert report.imported and not report.exported
    assert read(os.path.join(claudecode.memory_dir(root), "ci.md")) == "CI on Fridays\n"
    assert os.path.exists(os.path.join(store.store_folder("github.com/me/tally"), "ci.md"))


def test_lock_works_without_fcntl(env, monkeypatch):
    monkeypatch.setattr(locks, "fcntl", None)  # as on Windows
    first, second = locks.Lock("sync", wait=0.3), locks.Lock("sync", wait=0.3)
    assert first.acquire() and not second.acquire()
    first.release()
    assert second.acquire()
    second.release()
    assert not os.path.exists(first.path)
    write(first.path, "")  # left behind by a process that died long ago
    old = time.time() - locks.STALE_LOCK_SECONDS - 1
    os.utime(first.path, (old, old))
    assert first.acquire()
    first.release()
