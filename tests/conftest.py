"""Fixtures. Everything runs in temp dirs: CLAUDE_CONFIG_DIR, AUTOMEM_STATE and AUTOMEM_STORE point
there, so the real ~/.claude, store and memory are never touched."""

import json
import os
import subprocess

import pytest
from helpers import Machine, git


@pytest.fixture
def env(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    monkeypatch.setenv("AUTOMEM_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("AUTOMEM_STORE", str(tmp_path / "store"))
    for name in (
        "AUTOMEM_DISABLE",
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY",
        "CLAUDE_CODE_PROJECT_DIR_NAME",
        "CLAUDE_PROJECT_DIR",
    ):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


@pytest.fixture
def repo(env):
    path = env / "work" / "my_repo.v2"  # a dot and an underscore, to exercise how Claude Code names the project folder
    path.mkdir(parents=True)
    git("init", "-q", cwd=path)
    (path / "a.txt").write_text("a")
    git("add", "-A", cwd=path)
    git("commit", "-qm", "init", cwd=path)
    git("remote", "add", "origin", "git@github.com:Me/Tally.git", cwd=path)
    return os.path.realpath(path)


@pytest.fixture
def machines(env, monkeypatch):
    bare = env / "store-remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    seed = env / "seed"
    seed.mkdir()
    git("init", "-q", cwd=seed)
    (seed / "automem.json").write_text(json.dumps({"owners": ["me"]}))
    git("add", "-A", cwd=seed)
    git("commit", "-qm", "init", cwd=seed)
    git("remote", "add", "origin", str(bare), cwd=seed)
    git("push", "-q", "-u", "origin", "HEAD", cwd=seed)
    upstream = env / "upstream"
    upstream.mkdir()
    git("init", "-q", cwd=upstream)
    (upstream / "tally.py").write_text("print(1)\n")
    git("add", "-A", cwd=upstream)
    git("commit", "-qm", "init", cwd=upstream)

    def make(name):
        return Machine(env, name, monkeypatch, bare, upstream)

    return make
