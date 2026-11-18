from automem import commands, plugin
from helpers import assert_plain, git, run_hook


def test_prompt_commands(repo, env):
    out = run_hook("prompt.py", {"session_id": "s1", "cwd": repo, "prompt": "::handoff"})
    assert "handoff note" in out["hookSpecificOutput"]["additionalContext"]
    out = run_hook("prompt.py", {"session_id": "s1", "cwd": repo, "prompt": "::automem retire staleness_nudge"})
    assert out["decision"] == "block" and "off" in out["reason"]
    assert not plugin.feature_on("staleness_nudge")
    out = run_hook("prompt.py", {"session_id": "s1", "cwd": repo, "prompt": "::automem sync"})
    assert "Sync for this repo is off" in out["reason"]
    assert run_hook("prompt.py", {"session_id": "s1", "cwd": repo, "prompt": "hello"}) is None


def test_commands_use_the_start_project_after_a_cd(repo, env):
    git("checkout", "-qb", "feature/x", cwd=repo)
    run_hook("session_start.py", {"session_id": "s1", "cwd": repo, "source": "startup"})
    elsewhere = env / "another-project"
    elsewhere.mkdir()
    out = run_hook("prompt.py", {"session_id": "s1", "cwd": str(elsewhere), "prompt": "::handoff"})
    assert "`handoff-feature-x.md`" in out["hookSpecificOutput"]["additionalContext"]
    out = run_hook("prompt.py", {"session_id": "s1", "cwd": str(elsewhere), "prompt": "::automem sync"})
    assert "Sync for this repo is off" in out["reason"]  # the repo the session started in, not "isn't a git repo"
    # a session the plugin never saw start: Claude Code's own CLAUDE_PROJECT_DIR says where it started
    payload = {"session_id": "unseen", "cwd": str(elsewhere), "prompt": "::handoff"}
    out = run_hook("prompt.py", payload, {"CLAUDE_PROJECT_DIR": repo})
    assert "`handoff-feature-x.md`" in out["hookSpecificOutput"]["additionalContext"]
    # with neither, the hook's cwd is all there is
    out = run_hook("prompt.py", payload)
    assert "`handoff.md`" in out["hookSpecificOutput"]["additionalContext"]


def test_overview_groups_every_command_one_per_line(repo, env):
    out = run_hook("prompt.py", {"session_id": "h1", "cwd": repo, "prompt": "::automem"})
    text = out["reason"]
    assert out["decision"] == "block" and text.startswith(f"automem-plus {plugin.version()} · ")
    assert_plain(text)
    lines = text.splitlines()
    for title, entries in commands.GROUPS:
        assert title in lines
        for command, what in entries:
            assert f"  {command}  →  {what}" in lines
    for word in ("::handoff", "status", "reconcile", "review", "promote", "sync", "store", "owner", "retire", "canary"):
        assert word in text
    assert lines[-1].startswith("Features: handoff_rule on · ")
    assert run_hook("prompt.py", {"session_id": "h1", "cwd": repo, "prompt": "::automem help"})["reason"] == text
    wrong = run_hook("prompt.py", {"session_id": "h1", "cwd": repo, "prompt": "::automem owner"})["reason"]
    assert wrong.startswith("::automem owner isn't a command here, or it's missing an argument.") and text in wrong
    run_hook("prompt.py", {"session_id": "h1", "cwd": repo, "prompt": "::automem retire sync"})
    assert "sync OFF" in run_hook("prompt.py", {"session_id": "h1", "cwd": repo, "prompt": "::automem"})["reason"]
