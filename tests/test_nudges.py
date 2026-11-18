import json
import os
import time

from automem import claudecode, gitrepo, handoff
from helpers import git, run_hook, two_machines_that_wrote_the_same_note, user_prompt, write, write_transcript


def test_staleness_nudge_after_commit_without_handoff(repo, env):
    run_hook("session_start.py", {"session_id": "s1", "cwd": repo, "source": "startup"})
    tpath = env / "t.jsonl"
    write_transcript(tpath, [user_prompt("hi")])
    payload = {"session_id": "s1", "cwd": repo, "transcript_path": str(tpath)}
    out = run_hook("stop.py", payload)
    assert not out or "handoff" not in out.get("systemMessage", "")
    time.sleep(1.1)
    write(os.path.join(repo, "b.txt"), "b")
    git("add", "-A", cwd=repo)
    git("commit", "-qm", "work", cwd=repo)
    out = run_hook("stop.py", payload)
    assert "handoff note is older" in out["systemMessage"]
    again = run_hook("stop.py", payload)  # shown once per commit
    assert not again or "handoff" not in again.get("systemMessage", "")


def test_no_nudge_when_handoff_is_fresh(repo, env):
    run_hook("session_start.py", {"session_id": "s1", "cwd": repo, "source": "startup"})
    time.sleep(1.1)
    write(os.path.join(repo, "b.txt"), "b")
    git("add", "-A", cwd=repo)
    git("commit", "-qm", "work", cwd=repo)
    folder = claudecode.memory_dir(repo)
    os.makedirs(folder)
    time.sleep(1.1)
    write(os.path.join(folder, handoff.handoff_name(gitrepo.branch(repo))), "x")
    tpath = env / "t.jsonl"
    write_transcript(tpath, [user_prompt("hi")])
    out = run_hook("stop.py", {"session_id": "s1", "cwd": repo, "transcript_path": str(tpath)})
    assert not out or "handoff" not in out.get("systemMessage", "")


def test_commit_in_a_worktree_triggers_the_nudge_there(repo, env):
    wt = env / "wt"
    git("worktree", "add", "-q", str(wt), cwd=repo)
    wt_path = os.path.realpath(wt)
    run_hook("session_start.py", {"session_id": "w1", "cwd": wt_path, "source": "startup"})
    run_hook("session_start.py", {"session_id": "m1", "cwd": repo, "source": "startup"})
    time.sleep(1.1)
    (wt / "c.txt").write_text("c")
    git("add", "-A", cwd=wt)
    git("commit", "-qm", "in worktree", cwd=wt)
    tpath = env / "t.jsonl"
    write_transcript(tpath, [user_prompt("hi")])
    out = run_hook("stop.py", {"session_id": "w1", "cwd": wt_path, "transcript_path": str(tpath)})
    assert out and "handoff note is older" in out["systemMessage"]
    main = run_hook("stop.py", {"session_id": "m1", "cwd": repo, "transcript_path": str(tpath)})
    assert not main or "handoff" not in main.get("systemMessage", "")  # the main checkout didn't commit


def test_version_change_in_transcript_offers_the_canary(repo, env):
    tpath = env / "t.jsonl"
    write_transcript(tpath, [dict(user_prompt("hi"), version="2.1.323")])
    payload = {"session_id": "v1", "cwd": repo, "transcript_path": str(tpath)}
    first = run_hook("stop.py", payload)
    assert not first or "canary" not in first.get("systemMessage", "")  # first sighting just records it
    with open(tpath, "a") as f:
        f.write(json.dumps(dict(user_prompt("again"), version="2.1.330")) + "\n")
    out = run_hook("stop.py", payload)
    assert "2.1.323 → 2.1.330" in out["systemMessage"]


def test_stop_line_offers_reconcile_once_after_a_conflict(machines):
    a, b, _ = two_machines_that_wrote_the_same_note(machines)
    b.use()
    tpath = os.path.join(str(b.dir), "t.jsonl")
    write_transcript(tpath, [user_prompt("hi")])
    payload = {"session_id": "n1", "cwd": b.repo, "transcript_path": tpath}
    first = run_hook("stop.py", payload)
    assert "::automem reconcile" in first["systemMessage"] and "1 note" in first["systemMessage"]
    assert run_hook("stop.py", payload) is None
    a.use()
    write_transcript(os.path.join(str(a.dir), "t.jsonl"), [user_prompt("hi")])
    assert (
        run_hook("stop.py", {"session_id": "n2", "cwd": a.repo, "transcript_path": os.path.join(str(a.dir), "t.jsonl")})
        is None
    )
