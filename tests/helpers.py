"""Plain helpers shared by the tests: run a hook, write a transcript, simulate a second machine."""

import json
import os
import subprocess
import sys
import time

from automem import claudecode, sync

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")


# Made-up credentials for the secret-scan tests. They are put together here so that no file in the
# repo holds a string that looks like a real key.
FAKE_API_KEY_LINE = "api_key = " + "sk-" + "ant-" + "abcdefghijklmnopqrstuvwxyz123"
FAKE_PASSWORD_LINE = "pass" + "word: " + "hunter2" * 3


def read(path):
    with open(path) as f:
        return f.read()


def write(path, text):
    with open(path, "w") as f:
        f.write(text)


def git(*args, cwd):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def run_hook(script, payload, env_overrides=None):
    env = dict(os.environ, **(env_overrides or {}))
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def write_transcript(path, entries):
    with open(path, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def tool_call(name, file_path):
    return {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": name, "input": {"file_path": file_path}}]},
    }


def user_prompt(text):
    return {"type": "user", "message": {"content": text}}


class Machine:
    """One machine: its own Claude config folder, state folder, store clone and repo clone at its own path."""

    def __init__(self, tmp, name, monkeypatch, bare_store, upstream):
        self.dir, self.mp = tmp / name, monkeypatch
        self.config, self.state, self.store = self.dir / "config", self.dir / "state", self.dir / "store"
        self.config.mkdir(parents=True)
        subprocess.run(["git", "clone", "-q", str(bare_store), str(self.store)], check=True)
        clone = self.dir / "code" / f"tally-{name}"
        subprocess.run(["git", "clone", "-q", str(upstream), str(clone)], check=True)
        git("remote", "set-url", "origin", "git@github.com:me/tally.git", cwd=clone)
        self.repo = os.path.realpath(clone)
        self.use()
        os.makedirs(claudecode.memory_dir(self.repo))

    def use(self):
        self.mp.setenv("CLAUDE_CONFIG_DIR", str(self.config))
        self.mp.setenv("AUTOMEM_STATE", str(self.state))
        self.mp.setenv("AUTOMEM_STORE", str(self.store))
        return self

    @property
    def mem(self):
        return claudecode.memory_dir(self.repo)

    def write(self, rel, text):
        path = os.path.join(self.mem, rel)
        with open(path, "w") as f:
            f.write(text)

    def read(self, rel):
        path = os.path.join(self.mem, rel)
        return read(path) if os.path.exists(path) else None

    def sync(self):
        self.use()
        return sync.run(self.repo, push_now=True, lock_wait=1)


def two_machines_that_wrote_the_same_note(machines):
    """A synced first; B joins with its own copy of ci.md (older than A's push) and a note of its own."""
    a, b = machines("a"), machines("b")
    a.use().write("ci.md", "CI runs on Fridays\n")
    a.write("budget.md", "One subagent at most\n")
    a.write("MEMORY.md", "- [CI](ci.md) — Fridays\n- [Budget](budget.md) — one subagent\n")
    b.use().write("ci.md", "CI runs on Mondays\n")
    b.write("agents.md", "Never run two subagents at once\n")
    b.write("MEMORY.md", "- [CI](ci.md) — Mondays\n- [Agents](agents.md) — never two at once\n")
    past = time.time() - 3600
    os.utime(os.path.join(b.mem, "ci.md"), (past, past))
    a.sync()
    return a, b, b.sync()


def assert_plain(text):
    """No markdown: Claude Code shows a hook's answer as plain text."""
    for mark in ("`", "**", "###"):
        assert mark not in text, (mark, text)
    assert not any(line.lstrip().startswith("|") for line in text.splitlines()), text  # a table row
