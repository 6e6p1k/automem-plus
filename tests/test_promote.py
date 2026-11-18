import os

from automem import claudecode, promote
from helpers import read, run_hook


def test_promote_lists_preferences_and_moves_one_to_user_rules(repo, env):
    folder = claudecode.memory_dir(repo)
    os.makedirs(folder)
    with open(os.path.join(folder, "subagent-budget.md"), "w") as f:
        f.write(
            '---\nname: subagent-budget\ndescription: "One subagent at most"\nmetadata:\n  type: feedback\n---\n\n'
            "Use at most one subagent.\n\n**Why:** cost.\n"
        )
    with open(os.path.join(folder, "deploy.md"), "w") as f:
        f.write("---\nname: deploy\ndescription: deploys to Vercel\nmetadata:\n  type: project\n---\n\nVercel.\n")
    with open(os.path.join(folder, "MEMORY.md"), "w") as f:
        f.write("- [Subagent budget](subagent-budget.md) — one at most\n- [Deploy](deploy.md) — Vercel\n")
    listing = promote.list_text(repo)
    assert "subagent-budget.md" in listing and "deploy.md" not in listing
    out = run_hook("prompt.py", {"session_id": "s", "cwd": repo, "prompt": "::automem promote subagent-budget"})
    rule = os.path.join(str(env / "config"), "rules", "automem-subagent-budget.md")
    assert "Moved to" in out["reason"] and os.path.exists(rule)
    text = read(rule)
    assert text.startswith("# One subagent at most") and "Use at most one subagent." in text and "type:" not in text
    assert not os.path.exists(os.path.join(folder, "subagent-budget.md"))
    assert read(os.path.join(folder, "MEMORY.md")) == "- [Deploy](deploy.md) — Vercel\n"
    again = run_hook("prompt.py", {"session_id": "s", "cwd": repo, "prompt": "::automem promote subagent-budget"})
    assert "No note" in again["reason"]
