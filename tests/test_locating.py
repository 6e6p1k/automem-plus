import json
import os

import pytest
from automem import claudecode, gitrepo
from helpers import git


@pytest.mark.parametrize(
    "url,key",
    [
        ("git@github.com:Me/Tally.git", "github.com/me/tally"),
        ("https://github.com/Me/Tally", "github.com/me/tally"),
        ("https://user@github.com/Me/Tally.git/", "github.com/me/tally"),
        ("ssh://git@gitlab.example.com:2222/group/sub/proj.git", "gitlab.example.com/group/sub/proj"),
        ("", None),
        ("not a url", None),
    ],
)
def test_normalise_remote(url, key):
    assert gitrepo.normalise_remote(url) == key


def test_memory_dir_follows_claude_code_naming(repo, env):
    expected = os.path.join(
        str(env / "config"), "projects", "".join(ch if ch.isalnum() else "-" for ch in repo), "memory"
    )
    assert claudecode.memory_dir(repo) == expected


def test_worktree_resolves_to_main_checkout(repo, env):
    wt = env / "wt"
    git("worktree", "add", "-q", str(wt), cwd=repo)
    assert gitrepo.repo_root(str(wt / ".")) == repo
    assert gitrepo.repo_root(str(env)) is None  # not a git repo


def test_settings_precedence_and_disable(repo, env, monkeypatch):
    assert claudecode.auto_memory_on(repo)
    (env / "config" / "settings.json").write_text(json.dumps({"autoMemoryEnabled": False}))
    assert not claudecode.auto_memory_on(repo)
    os.makedirs(os.path.join(repo, ".claude"))
    with open(os.path.join(repo, ".claude", "settings.local.json"), "w") as f:
        json.dump({"autoMemoryEnabled": True, "autoMemoryDirectory": "~/custom-mem"}, f)
    assert claudecode.auto_memory_on(repo)
    assert claudecode.memory_dir(repo) == os.path.expanduser("~/custom-mem")
    monkeypatch.setenv("CLAUDE_CODE_DISABLE_AUTO_MEMORY", "1")
    assert not claudecode.auto_memory_on(repo)
