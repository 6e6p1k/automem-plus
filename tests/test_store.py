import json
import os
import subprocess

from automem import claudecode, state, store, sync
from helpers import git, write


def test_sync_status_rules(repo, env):
    assert not store.sync_status(repo)[0]  # no store
    assert "Store ready" in store.create_store("init")
    assert store.sync_status(repo) == (False, "not your repo (::automem sync on opts it in)")
    assert "now sync" in store.add_owner("Me")
    assert store.sync_status(repo)[0]
    store.set_repo(repo, False)
    assert store.sync_status(repo) == (False, "this repo is local-only")
    (env / "config" / "settings.json").write_text(json.dumps({"autoMemoryDirectory": "~/one-folder"}))
    assert not store.sync_status(repo)[0]  # every repo would share that folder


def test_no_import_until_claude_code_created_the_project_folder(repo, env):
    store.create_store("init")
    store.add_owner("me")
    assert not os.path.isdir(os.path.dirname(claudecode.memory_dir(repo)))
    assert sync.run(repo) is None
    assert not os.path.isdir(os.path.dirname(claudecode.memory_dir(repo)))


def test_store_made_with_init_then_given_a_remote_starts_pushing(env, repo):
    store.create_store("init")
    store.add_owner("me")
    bare = env / "later-remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git("remote", "add", "origin", str(bare), cwd=state.store_dir())
    os.makedirs(claudecode.memory_dir(repo))
    write(os.path.join(claudecode.memory_dir(repo), "ci.md"), "CI\n")
    assert sync.run(repo, push_now=True, lock_wait=1).push == "pushed"
    assert (
        "ci.md"
        in subprocess.run(
            ["git", "--git-dir", str(bare), "ls-tree", "-r", "--name-only", "HEAD"], capture_output=True, text=True
        ).stdout
    )
