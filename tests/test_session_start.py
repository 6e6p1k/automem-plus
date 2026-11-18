import json

from automem import plugin, usage
from helpers import git, run_hook


def test_session_start_injects_rules_wherever_auto_memory_is_on(repo, env):
    out = run_hook("session_start.py", {"session_id": "s1", "cwd": repo, "source": "startup"})
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "handoff.md" in context and "in passing" in context
    plain = env / "notes-folder"
    plain.mkdir()
    out = run_hook("session_start.py", {"session_id": "s2", "cwd": str(plain), "source": "startup"})
    assert "handoff.md" in out["hookSpecificOutput"]["additionalContext"]  # rules don't need git
    (plain / ".claude").mkdir()
    (plain / ".claude" / "settings.json").write_text(json.dumps({"autoMemoryEnabled": False}))
    assert run_hook("session_start.py", {"session_id": "s3", "cwd": str(plain), "source": "startup"}) is None
    starts = [u for u in usage.read_usage() if u["event"] == "start"]
    assert starts and starts[0]["has_handoff"] is False and "tally" not in json.dumps(starts)


def test_session_start_respects_disable_and_retired_rules(repo, env):
    assert run_hook("session_start.py", {"session_id": "s1", "cwd": repo}, {"AUTOMEM_DISABLE": "1"}) is None
    plugin.set_feature("passing_facts_rule", False)
    out = run_hook("session_start.py", {"session_id": "s3", "cwd": repo, "source": "startup"})
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "handoff.md" in context and "in passing" not in context


def test_session_start_after_compaction_keeps_the_start_project(repo, env):
    git("checkout", "-qb", "feature/x", cwd=repo)
    elsewhere = env / "another-project"
    elsewhere.mkdir()
    out = run_hook(
        "session_start.py",
        {"session_id": "s1", "cwd": str(elsewhere), "source": "compact"},
        {"CLAUDE_PROJECT_DIR": repo},
    )
    assert "handoff-feature-x.md" in out["hookSpecificOutput"]["additionalContext"]
