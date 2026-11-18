from automem import gitrepo, handoff, sync
from helpers import read, run_hook, two_machines_that_wrote_the_same_note


def test_sync_records_which_copy_lost_a_conflict(machines):
    a, b, report = two_machines_that_wrote_the_same_note(machines)
    assert b.use().read("ci.md") == "CI runs on Fridays\n" and "ci.md" in report.conflicts
    lost = sync.lost_copies(b.repo)
    assert [(x["file"], x["kept"]) for x in lost] == [("ci.md", "store")]
    assert read(lost[0]["backup"]) == "CI runs on Mondays\n"  # B's own copy, still on B
    assert sync.lost_copies(a.use().repo) == []  # A saw no conflict: its copy was the one kept


def test_reconcile_command_hands_claude_the_lost_copies_and_the_rules(machines):
    a, b, _ = two_machines_that_wrote_the_same_note(machines)
    b.use()
    payload = {"session_id": "r1", "cwd": b.repo, "prompt": "::automem reconcile"}
    context = run_hook("prompt.py", payload)["hookSpecificOutput"]["additionalContext"]
    backup = sync.lost_copies(b.repo)[0]["backup"]
    assert b.mem in context and backup in context and "`ci.md`" in context
    # the copy itself is quoted, since a session may not be allowed to read the state folder
    assert "CI runs on Mondays" in context
    assert "`budget.md`" in context  # arrived from the other machine: compare it with what was here
    assert "`agents.md`" not in context.split("arrived from")[1].split("\n\n")[0]  # B's own note didn't arrive
    assert "Change nothing until" in context and handoff.handoff_name(gitrepo.branch(b.repo)) in context
    # a second run doesn't repeat what was already handed over, but says how to get it back
    again = run_hook("prompt.py", payload)["hookSpecificOutput"]["additionalContext"]
    assert backup not in again and "/automem-plus:reconcile all" in again
    everything = run_hook("prompt.py", dict(payload, prompt="::automem reconcile all"))
    assert backup in everything["hookSpecificOutput"]["additionalContext"]
    # the other commands still answer directly instead of reaching Claude
    assert run_hook("prompt.py", dict(payload, prompt="::automem status"))["decision"] == "block"


def test_reconcile_works_without_any_recorded_conflict(repo, env):
    out = run_hook("prompt.py", {"session_id": "r2", "cwd": repo, "prompt": "::automem reconcile"})
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "No copy lost a file conflict" in context and "Change nothing until" in context


def test_a_conflict_git_found_between_two_pushes_is_recorded_too(machines):
    a, b = machines("a"), machines("b")
    a.use().write("handoff.md", "v1\n")
    a.sync()
    b.sync()
    b.use().write("handoff.md", "B's v2\n")
    sync.run(b.repo, push_now=False, lock_wait=1)  # committed on B, not pushed
    a.use().write("handoff.md", "A's v2\n")
    a.sync()
    assert b.sync().push == "pushed after merge"
    lost = sync.lost_copies(b.use().repo)
    assert [(x["file"], x["kept"]) for x in lost] == [("handoff.md", "local")]
    assert read(lost[0]["backup"]) == "A's v2\n"
