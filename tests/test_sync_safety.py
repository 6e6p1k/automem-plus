import os
import shutil

from automem import store, sync
from helpers import FAKE_API_KEY_LINE, read, write


def test_same_note_edited_on_both_with_unpushed_work_keeps_everything(machines):
    a, b = machines("a"), machines("b")
    a.use().write("handoff.md", "v1\n")
    a.sync()
    b.sync()
    # B commits locally without pushing (as SessionStart does), including a brand-new note
    b.use().write("handoff.md", "B's v2\n")
    b.write("new.md", "only on B\n")
    sync.run(b.repo, push_now=False, lock_wait=1)
    a.use().write("handoff.md", "A's v2\n")
    assert a.sync().push == "pushed"
    report = b.sync()  # the push is rejected and merged; the handoff conflicts inside git
    assert report.push == "pushed after merge", report
    assert b.use().read("handoff.md") == "B's v2\n" and b.read("new.md") == "only on B\n"
    assert any(p and read(p) == "A's v2\n" for p in report.backups)
    report_a = a.sync()
    assert a.use().read("handoff.md") == "B's v2\n" and a.read("new.md") == "only on B\n"
    assert any(p and read(p) == "A's v2\n" for p in report_a.backups)  # A's own copy, before import


def test_purged_local_folder_is_not_pushed_as_mass_deletion(machines):

    a, b = machines("a"), machines("b")
    a.use().write("ci.md", "CI on Fridays\n")
    a.write("MEMORY.md", "- [CI](ci.md) — Fridays\n")
    a.sync()
    shutil.rmtree(a.mem)  # the folder is wiped while the base in the state folder survives
    os.makedirs(a.mem)
    a.sync()
    assert a.read("ci.md") == "CI on Fridays\n"  # brought back, not deleted everywhere
    b.sync()
    assert b.use().read("ci.md") == "CI on Fridays\n"


def test_recreated_store_doesnt_delete_local_notes(machines, env):

    a = machines("a")
    a.use().write("ci.md", "CI on Fridays\n")
    a.sync()
    shutil.rmtree(a.store)
    store.create_store("init")
    store.add_owner("me")
    report = sync.run(a.repo, lock_wait=1)
    assert a.read("ci.md") == "CI on Fridays\n" and not report.deleted_here
    assert os.path.exists(os.path.join(store.store_folder("github.com/me/tally"), "ci.md"))


def test_local_only_index_lines_survive_a_store_index_change(machines):
    a, b = machines("a"), machines("b")
    a.use().write("leak.md", FAKE_API_KEY_LINE + "\n")
    a.write("ci.md", "CI on Fridays\n")
    a.write("MEMORY.md", "- [Leak](leak.md) — the key\n- [CI](ci.md) — Fridays\n")
    a.sync()
    b.sync()
    b.use().write("uv.md", "use uv\n")
    b.write("MEMORY.md", b.read("MEMORY.md") + "- [Uv](uv.md) — uv\n")
    b.sync()
    a.sync()
    index = a.use().read("MEMORY.md")
    assert "leak.md" in index and "uv.md" in index and "ci.md" in index


def test_reworded_and_removed_index_lines_stay_that_way(machines):
    a, b = machines("a"), machines("b")
    a.use().write("ci.md", "CI\n")
    a.write("MEMORY.md", "- [CI](ci.md) — Fridays\n- a loose line without a link\n")
    a.sync()
    b.sync()
    a.use().write("MEMORY.md", "- [CI](ci.md) — Fridays only, reworded\n")  # reworded one, removed the other
    a.sync()
    b.use().write("uv.md", "uv\n")
    b.write("MEMORY.md", b.read("MEMORY.md") + "- [Uv](uv.md) — uv\n")
    b.sync()
    a.sync()
    for m in (a, b):
        index = m.use().read("MEMORY.md")
        assert "reworded" in index and "loose line" not in index and "uv.md" in index
        assert index.count("ci.md") == 1


def test_failed_commit_is_reported_not_called_pushed(machines):
    a = machines("a")
    a.use().write("ci.md", "CI\n")
    lock = os.path.join(a.store, ".git", "index.lock")
    write(lock, "")  # fresh, so it isn't cleared as stale
    try:
        assert a.sync().push == "commit failed"
    finally:
        os.remove(lock)
    assert a.sync().push == "pushed"
