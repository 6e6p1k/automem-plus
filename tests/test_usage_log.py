import json
import os

import pytest
from automem import claudecode, gitrepo, transcript, usage
from helpers import run_hook, tool_call, user_prompt, write, write_transcript


def test_stop_logs_memory_reads_and_writes_once(repo, env):
    folder = claudecode.memory_dir(repo)
    tpath = env / "t.jsonl"
    entries = [
        user_prompt("hi"),
        tool_call("Read", os.path.join(folder, "handoff.md")),
        tool_call("Read", os.path.join(repo, "a.txt")),
        user_prompt("next"),
        tool_call("Write", os.path.join(folder, "ci.md")),
    ]
    write_transcript(tpath, entries)
    run_hook("session_start.py", {"session_id": "s1", "cwd": repo, "source": "startup"})
    payload = {"session_id": "s1", "cwd": repo, "transcript_path": str(tpath)}
    run_hook("stop.py", payload)
    run_hook("stop.py", payload)  # second Stop with no new lines logs nothing new
    notes = [u for u in usage.read_usage() if u["feature"] == "note"]
    assert [(u["event"], u["file"], u["prompt"]) for u in notes] == [("read", "handoff.md", 1), ("write", "ci.md", 2)]


def test_rewritten_transcript_is_read_again_from_the_start(repo, env):
    folder = claudecode.memory_dir(repo)
    tpath = env / "t.jsonl"
    write_transcript(
        tpath, [user_prompt("a"), user_prompt("b"), tool_call("Read", os.path.join(folder, "x.md")), user_prompt("c")]
    )
    payload = {"session_id": "r1", "cwd": repo, "transcript_path": str(tpath)}
    run_hook("stop.py", payload)
    # compaction rewrote the transcript, so it is shorter than the saved offset
    write_transcript(tpath, [user_prompt("summary"), tool_call("Read", os.path.join(folder, "y.md"))])
    run_hook("stop.py", payload)
    files = [u["file"] for u in usage.read_usage() if u["feature"] == "note"]
    assert files == ["x.md", "y.md"]


@pytest.mark.parametrize(
    "command,expected",
    [
        ("cat > {m}/ci.md <<'EOF'\nCI on Fridays\nEOF", [("write", "ci.md")]),
        ("cat {m}/ci.md", [("read", "ci.md")]),
        ("sed -n '1,5p' {m}/ci.md && echo done", [("read", "ci.md")]),
        ("sed -i '' 's/a/b/' {m}/ci.md", [("write", "ci.md")]),
        ("rm {m}/old.md", [("write", "old.md")]),
        ("printf x | tee -a {m}/MEMORY.md", [("write", "MEMORY.md")]),
        ("cp /tmp/x.md {m}/new.md", [("write", "new.md")]),
        ("cp {m}/ci.md /tmp/backup.md", [("read", "ci.md")]),
        ("ls {m}", []),
        ("cat ~{tail}/ci.md", [("read", "ci.md")]),
    ],
)
def test_bash_commands_on_memory_notes_are_counted(env, command, expected):
    folder = os.path.join(os.path.expanduser("~"), ".claude", "projects", "-x", "memory")
    tail = folder[len(os.path.expanduser("~")) :]
    assert transcript.bash_memory_events(command.format(m=folder, tail=tail), folder) == expected


def test_stop_counts_bash_heredoc_writes(repo, env):
    folder = claudecode.memory_dir(repo)
    tpath = env / "t.jsonl"
    bash = {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "Bash",
                    "id": "toolu_1",
                    "input": {"command": f"cat > {folder}/where-we-are.md <<'EOF'\nstate\nEOF"},
                }
            ]
        },
    }
    write_transcript(tpath, [user_prompt("hi"), bash])
    run_hook("stop.py", {"session_id": "b1", "cwd": repo, "transcript_path": str(tpath)})
    notes = [(u["event"], u["file"]) for u in usage.read_usage() if u["feature"] == "note"]
    assert notes == [("write", "where-we-are.md")]


def test_stop_keeps_logging_for_the_start_project_after_a_cd(repo, env):
    folder = claudecode.memory_dir(repo)
    tpath = env / "t.jsonl"
    entries = [user_prompt("continue"), tool_call("Read", os.path.join(folder, "handoff.md"))]
    write_transcript(tpath, entries)
    run_hook("session_start.py", {"session_id": "s1", "cwd": repo, "source": "startup"})
    elsewhere = env / "another-project"  # auto memory on there too: its folder must not be the one scanned
    elsewhere.mkdir()
    run_hook("stop.py", {"session_id": "s1", "cwd": str(elsewhere), "transcript_path": str(tpath)})
    off = env / "memory-off-project"  # auto memory off there: the session's own project still has it on
    (off / ".claude").mkdir(parents=True)
    (off / ".claude" / "settings.json").write_text(json.dumps({"autoMemoryEnabled": False}))
    write_transcript(tpath, entries + [user_prompt("next"), tool_call("Write", os.path.join(folder, "ci.md"))])
    run_hook("stop.py", {"session_id": "s1", "cwd": str(off), "transcript_path": str(tpath)})
    notes = [(u["event"], u["file"], u["repo"]) for u in usage.read_usage() if u["feature"] == "note"]
    assert notes == [("read", "handoff.md", gitrepo.repo_hash(repo)), ("write", "ci.md", gitrepo.repo_hash(repo))]


ALL_READ = [("read", "MEMORY.md"), ("read", "ci.md"), ("read", "handoff.md")]


@pytest.mark.parametrize(
    "command,expected",
    [
        ("cd {m} && cat ci.md", [("read", "ci.md")]),
        ('cd {m}/ && ls -la && for f in *.md; do echo "=== $f ==="; cat "$f"; echo; done', ALL_READ),
        ("cd ~{tail}; head -5 ./handoff.md", [("read", "handoff.md")]),
        ('(cd "{m}" && grep -l uv *.md)', ALL_READ),
        ("cat {m}/*.md", ALL_READ),
        ("cd {m} && sed -i '' 's/a/b/' ci.md", [("write", "ci.md")]),
        ('cd {m} && rm ci.md && echo "removed ci.md from memory"', [("write", "ci.md")]),
        # a heredoc's body is text, not commands: only the file written counts
        ("cd {m} && cat > new.md <<'EOF'\n- see [CI](ci.md) and handoff.md\nEOF", [("write", "new.md")]),
        ("cd {m} && cat > new.md <<'EOF'\nbody\nEOF\ncat ci.md", [("write", "new.md"), ("read", "ci.md")]),
        ("cd {m} && ls *.md", []),  # listing isn't reading
        ("cd {m} && cat no-such-note.md", []),  # a relative name only counts when it is a note
        ("cd {m} && cd .. && cat ci.md", []),  # left the folder again
        ("cd /tmp && cat ci.md", []),
        ("cat ci.md", []),
        ("cd {m} && cat ci.md && tail -1 ci.md", [("read", "ci.md")]),  # once per note and event
        ("cd {m} && cat ci.md > ci.md.tmp && mv ci.md.tmp ci.md", [("read", "ci.md"), ("write", "ci.md")]),
        ('M={m}; cat $M/ci.md "$M"/handoff.md ${{M}}/MEMORY.md', ALL_READ),
        ('MEM="{m}" && cd "$MEM" && cat handoff.md > /tmp/copy.md', [("read", "handoff.md")]),
    ],
)
def test_bash_commands_through_cd_globs_and_variables(env, command, expected):
    folder = os.path.join(os.path.expanduser("~"), ".claude", "projects", "-x", "memory")
    tail = folder[len(os.path.expanduser("~")) :]
    found = transcript.bash_memory_events(
        command.format(m=folder, tail=tail), folder, existing={"MEMORY.md", "ci.md", "handoff.md"}
    )
    assert sorted(found) == sorted(expected)


def test_stop_counts_a_cd_and_cat_loop_over_the_memory_folder(repo, env):
    folder = claudecode.memory_dir(repo)
    os.makedirs(folder)
    for name in ("MEMORY.md", "handoff-main.md"):
        write(os.path.join(folder, name), "x\n")
    tpath = env / "t.jsonl"
    bash = {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "Bash",
                    "id": "toolu_2",
                    "input": {"command": f'cd {folder}/ && ls -la && for f in *.md; do cat "$f"; done'},
                }
            ]
        },
    }
    write_transcript(tpath, [user_prompt("continue"), bash])
    run_hook("stop.py", {"session_id": "b2", "cwd": repo, "transcript_path": str(tpath)})
    notes = [(u["event"], u["file"], u["prompt"]) for u in usage.read_usage() if u["feature"] == "note"]
    assert notes == [("read", "MEMORY.md", 1), ("read", "handoff-main.md", 1)]
