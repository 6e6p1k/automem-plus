import os
import re

import helpers
import pytest
from automem import commands, constants, plugin
from helpers import assert_plain, git, read, run_hook


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


def ask(repo, prompt):
    return run_hook("prompt.py", {"session_id": "h1", "cwd": repo, "prompt": prompt})


def test_overview_groups_every_command_one_per_line(repo, env):
    out = ask(repo, "::automem")
    text = out["reason"]
    assert out["decision"] == "block" and text.startswith(f"automem-plus {plugin.version()} · ")
    assert_plain(text)
    lines = text.splitlines()
    for title, entries in commands.GROUPS:
        assert title in lines
        for command in entries:
            assert f"  {commands.spelled(command.name, command.args)}  →  {command.what}" in lines
    assert "  /automem-plus:sync [on|off]  →  " in text and "::automem <name>" in text and "::handoff" in text
    assert lines[-1].startswith("Features: handoff_rule on · ")
    ask(repo, "::automem retire sync")
    assert "sync OFF" in ask(repo, "::automem")["reason"]


@pytest.mark.parametrize("slash,colons", [
    ("/automem-plus:help", "::automem help"),
    ("/automem-plus:", "::automem"),
    ("/automem-plus:status", "::automem status"),
    ("/automem-plus:sync", "::automem sync"),
    ("/automem-plus:Review", "::automem review"),
    ("/automem-plus:owner", "::automem owner"),
    ("/automem-plus:retire nothing-like-this", "::automem retire nothing-like-this"),
])  # fmt: skip
def test_both_spellings_get_the_same_answer_from_the_hook(repo, env, slash, colons):
    first, second = ask(repo, slash), ask(repo, colons)
    assert first["decision"] == "block" and first == second


def test_an_incomplete_command_says_so_before_the_overview(repo, env):
    overview = ask(repo, "/automem-plus:help")["reason"]
    wrong = ask(repo, "/automem-plus:owner")["reason"]
    assert (
        wrong.startswith("/automem-plus:owner isn't a command here, or it's missing an argument.") and overview in wrong
    )
    assert ask(repo, "/automem-plus:nonsense now")["reason"].startswith("/automem-plus:nonsense now isn't a command")


def test_handoff_and_reconcile_reach_claude_under_both_spellings(repo, env):
    for spelling in ("/automem-plus:handoff", "::handoff", "::automem handoff"):
        out = ask(repo, spelling)
        assert "handoff note" in out["hookSpecificOutput"]["additionalContext"] and "decision" not in out
    for spelling in ("/automem-plus:reconcile", "::automem reconcile", "/automem-plus:reconcile all"):
        assert "Change nothing until" in ask(repo, spelling)["hookSpecificOutput"]["additionalContext"]


OTHER_PROMPTS = ["/automem-plus", "/other-plugin:status", "/status", "::memory status", "automem status"]


@pytest.mark.parametrize("prompt", [*OTHER_PROMPTS, "what does ::automem status do?"])
def test_other_prompts_are_left_alone(repo, env, prompt):
    assert ask(repo, prompt) is None


def test_every_command_is_a_skill_and_every_skill_a_command():
    """The skills are what puts the commands in the / menu; the hook answers by the same names."""
    root = os.path.dirname(helpers.SCRIPTS)
    listed = {c.name: c for _title, group in commands.GROUPS for c in group}
    assert set(os.listdir(os.path.join(root, "skills"))) == set(listed)
    assert set(commands.COMMANDS) | {"handoff", "reconcile", "help"} == set(listed)
    assert read(os.path.join(root, ".claude-plugin", "plugin.json")).count(f'"name": "{constants.PLUGIN_NAME}"') == 1
    for name, command in listed.items():
        front = read(os.path.join(root, "skills", name, "SKILL.md")).split("---")[1]
        assert f"\nname: {name}\n" in front
        description = next(line for line in front.splitlines() if line.startswith("description: "))
        assert re.fullmatch(r'description: "[^"\\]+"', description)  # quoted, so a ": " inside is not read as a key
        assert "\ndisable-model-invocation: true\n" in front  # never loaded into context unless the user runs it
        assert (f'\nargument-hint: "{command.args}"\n' in front) == bool(command.args)
