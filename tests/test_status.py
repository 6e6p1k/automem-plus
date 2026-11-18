import os

from automem import claudecode, gitrepo, handoff, jsonfile, plugin, promote, review, state, status, store, sync
from helpers import assert_plain, run_hook, two_machines_that_wrote_the_same_note, write


def test_status_is_about_this_project_not_the_last_sync_anywhere(repo, env):
    store.create_store("init")
    store.add_owner("me")
    plain = env / "notes-folder"
    plain.mkdir()
    before = status.describe(repo)
    assert "✅ Sync here: on" in before and "hasn't synced yet" in before
    os.makedirs(claudecode.memory_dir(repo))
    write(os.path.join(claudecode.memory_dir(repo), "ci.md"), "CI\n")
    sync.run(repo, lock_wait=1)
    here = status.describe(repo)
    assert "✅ Last sync of this project:" in here and "another project" not in here
    assert "saved in the local store (it has no remote)" in here  # not "not pushed yet": there's nowhere to push
    os.remove(
        sync.status_path(gitrepo.repo_hash(repo))
    )  # a project that last synced before per-project records existed
    jsonfile.write_json(
        os.path.join(state.state_dir(), "sync_status.json"), {"ts": 1, "repo": "someone-else", "push": "pushed"}
    )
    older = status.describe(repo)
    assert "✅ Last sync of this project:" in older and "hasn't synced yet" not in older
    there = status.describe(str(plain))
    assert "⚪ Sync here: off, this folder isn't a git repo" in there
    assert "Last sync of this project" not in there and "another project" in there
    out = run_hook("prompt.py", {"session_id": "s9", "cwd": str(plain), "prompt": "::automem status"})
    assert "this folder isn't a git repo" in out["reason"]


def test_status_shows_version_handoff_and_what_waits(machines):
    a, b, _ = two_machines_that_wrote_the_same_note(machines)
    b.use()
    name = handoff.handoff_name(gitrepo.branch(b.repo))
    text = status.describe(b.repo, name)
    assert text.startswith(f"automem-plus {plugin.version()} · {os.path.basename(b.repo)}\n\n")
    assert f"⚪ Handoff: none yet (/automem-plus:handoff writes {name})" in text
    assert "⚠️ Waiting for reconcile: 1 note differed" in text and "both machines changed ci.md" in text
    assert all(line[:1] in ("✅", "⚠", "⚪", " ") for line in text.splitlines()[2:])  # every line starts with a mark
    b.write(name, "state\n")
    run_hook("prompt.py", {"session_id": "s", "cwd": b.repo, "prompt": "::automem reconcile"})  # handed to Claude
    after = status.describe(b.repo, name)
    assert f"✅ Handoff: {name}, updated just now" in after and "Waiting for reconcile" not in after
    for answer in (text, after, review.report(), promote.list_text(b.repo), plugin.set_feature("sync", False)):
        assert_plain(answer)


def test_ago():
    now = 1_000_000
    assert [status.ago(now - s, now) for s in (5, 120, 7200, 86400, 3 * 86400)] == [
        "just now",
        "2 min ago",
        "2 h ago",
        "1 day ago",
        "3 days ago",
    ]
