import os

from automem import claudecode, gitrepo, handoff
from helpers import git, run_hook, write


def test_handoff_names_per_branch():
    assert handoff.handoff_name("feature/Add search") == "handoff-feature-add-search.md"
    assert handoff.handoff_name(None) == "handoff.md"
    assert (
        handoff.is_handoff("handoff-main.md")
        and handoff.is_handoff("handoff.md")
        and not handoff.is_handoff("handoffs.md")
    )


def test_parallel_worktrees_get_their_own_handoff_and_merged_ones_are_pointed_out(repo, env):
    wt = env / "wt-search"
    git("worktree", "add", "-q", "-b", "search-index", str(wt), cwd=repo)
    main_ctx = run_hook("session_start.py", {"session_id": "m", "cwd": repo, "source": "startup"})
    wt_ctx = run_hook("session_start.py", {"session_id": "w", "cwd": os.path.realpath(wt), "source": "startup"})
    main_name = handoff.handoff_name(gitrepo.branch(repo))
    assert f"`{main_name}`" in main_ctx["hookSpecificOutput"]["additionalContext"]
    assert "`handoff-search-index.md`" in wt_ctx["hookSpecificOutput"]["additionalContext"]
    folder = claudecode.memory_dir(repo)
    os.makedirs(folder, exist_ok=True)
    write(os.path.join(folder, "handoff-old-branch.md"), "x")
    out = run_hook("session_start.py", {"session_id": "m2", "cwd": repo, "source": "startup"})
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "handoff-old-branch.md" in context and "no longer exist" in context
    assert "handoff-search-index.md" not in context.split("no longer exist")[0].split("These handoff")[-1]


def test_handoff_command_names_this_branch(repo, env):
    out = run_hook("prompt.py", {"session_id": "s", "cwd": repo, "prompt": "::handoff"})
    assert handoff.handoff_name(gitrepo.branch(repo)) in out["hookSpecificOutput"]["additionalContext"]
