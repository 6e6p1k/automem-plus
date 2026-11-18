"""Canary: does built-in auto memory, with automem-plus switched off, already do what the plugin adds?

Runs six short claude -p calls on Haiku in throwaway repos (about $0.07 in total) and
records pass or fail per scenario in the state folder's canary.json. A pass means built-in covers
that feature now, and the review suggests retiring the plugin's version. It deletes its repos and
their memory folders afterwards.

  outside_notes         a note written from outside (with its MEMORY.md line) is used
                        (if this ever fails, the import half of sync is broken)
  passing_facts         facts mentioned in passing during a task get saved without the plugin's rule
  handoff_without_rule  "I'm done for today" leaves a usable handoff without the plugin's rule
  cross_clone           a second clone of the same remote at another path sees the first clone's notes
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time

from automem import claudecode, constants, gitrepo, jsonfile, state

FAKE_REMOTE = "https://github.com/automem-canary/tally.git"
THROWAWAY_PREFIX = "automem-canary-"
SESSION_TIMEOUT = 300
SETTLE_SECONDS = 20  # built-in memory may still be writing notes in the background after a turn ends
TALLY = """import sys
from collections import Counter

def top_words(text, n=5):
    return Counter(text.lower().split()).most_common(n)

if __name__ == "__main__":
    print(top_words(open(sys.argv[1]).read()))
"""


def parse_result(stdout):
    """(answer, session id, cost in dollars) from claude -p --output-format json.

    That prints one result object, or, with the verbose setting on, the list of every event
    with the result last. Anything else counts as no answer."""
    try:
        data = json.loads(stdout)
    except ValueError:
        return "", None, 0.0
    events = data if isinstance(data, list) else [data]
    results = [e for e in events if isinstance(e, dict) and e.get("type") == "result"]
    if not results:
        return "", None, 0.0
    result = results[-1]
    return result.get("result") or "", result.get("session_id"), result.get("total_cost_usd") or 0.0


class Runner:
    """Runs headless Haiku sessions with the plugin switched off, and adds up what they cost."""

    def __init__(self):
        self.cost = 0.0
        self.env = dict(os.environ, **{constants.DISABLE_ENV: "1"})

    def claude(self, cwd, prompt, resume=None, edits=False):
        command = ["claude", "-p", "--model", "haiku", "--output-format", "json"]
        if edits:
            command += ["--permission-mode", "acceptEdits"]
        if resume:
            command += ["--resume", resume]
        proc = subprocess.run(
            command + [prompt], cwd=cwd, capture_output=True, text=True, timeout=SESSION_TIMEOUT, env=self.env
        )
        answer, session_id, cost = parse_result(proc.stdout)
        self.cost += cost
        return answer, session_id


def make_repo(base, name):
    path = os.path.realpath(os.path.join(base, name))
    os.makedirs(path)
    with open(os.path.join(path, "tally.py"), "w") as f:
        f.write(TALLY)
    with open(os.path.join(path, "README.md"), "w") as f:
        f.write("# tally\n")
    for args in (
        ["init", "-q"],
        ["add", "-A"],
        ["-c", "user.name=canary", "-c", "user.email=canary@example.invalid", "commit", "-qm", "init"],
        ["remote", "add", "origin", FAKE_REMOTE],
    ):
        gitrepo.git(*args, cwd=path)
    return path


def memory_text(root):
    """Everything built-in memory wrote for a repo, lower-cased."""
    text = ""
    for base, _, names in os.walk(claudecode.memory_dir(root)):
        for name in names:
            with open(os.path.join(base, name), errors="replace") as f:
                text += f.read().lower()
    return text


def unsafe_reason():
    """Settings under which throwaway repos would share a real memory folder. Then the canary doesn't run."""
    if os.environ.get("CLAUDE_CODE_PROJECT_DIR_NAME"):
        return "CLAUDE_CODE_PROJECT_DIR_NAME is set, so every repo shares one project folder"
    user = jsonfile.read_json(os.path.join(claudecode.config_dir(), "settings.json"), {}) or {}
    if isinstance(user.get("autoMemoryDirectory"), str) and user["autoMemoryDirectory"].strip():
        return "autoMemoryDirectory is set in your user settings, so every repo shares one memory folder"
    return None


def remove_throwaway_project(root):
    """Delete the transcripts and memory Claude Code kept for a throwaway repo, and nothing else."""
    project = os.path.dirname(claudecode.memory_dir(root))
    name = os.path.basename(project)
    if name == claudecode.project_dir_name(root) and THROWAWAY_PREFIX in name and os.path.isdir(project):
        shutil.rmtree(project, ignore_errors=True)


def outside_notes(runner, repo):
    folder = claudecode.memory_dir(repo)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "deploy-target.md"), "w") as f:
        f.write(
            '---\nname: deploy-target\ndescription: "Tally deploys to the orchid server"\n'
            "metadata:\n  type: project\n---\n\nTally deploys to the `orchid` server, never `lotus`.\n"
        )
    with open(os.path.join(folder, constants.INDEX_FILE), "a") as f:
        f.write("- [Deploy target](deploy-target.md) — deploys go to the orchid server, never lotus\n")
    answer, _ = runner.claude(repo, "Which server do we deploy tally to? One line.")
    return "orchid" in answer.lower()


def passing_facts(runner, repo):
    runner.claude(
        repo,
        "Add one paragraph describing tally to README.md. FYI, our CI only runs on Fridays, "
        "and Marta reviews every PR.",
        edits=True,
    )
    time.sleep(SETTLE_SECONDS)
    text = memory_text(repo)
    return "friday" in text or "marta" in text


def handoff_without_rule(runner, repo):
    _, session_id = runner.claude(
        repo, "Add a --n option to tally.py (argparse) for how many words to print. Just edit.", edits=True
    )
    runner.claude(
        repo,
        "Looks good. I tried reading stdin too but it broke on Windows line endings, so we skip "
        "stdin. Next time: a --json flag. I'm done for today.",
        resume=session_id,
        edits=True,
    )
    time.sleep(SETTLE_SECONDS)
    text = memory_text(repo)
    return ("crlf" in text or "line ending" in text) and "json" in text


def cross_clone(runner, repo, second_clone):
    runner.claude(
        repo, "Remember for future sessions: in this project we always run Python through uv. Confirm briefly."
    )
    answer, _ = runner.claude(second_clone, "How do we run Python in this project? One line, from what you know.")
    return bool(re.search(r"\buv\b", answer.lower()))


def run():
    problem = unsafe_reason()
    if problem:
        raise SystemExit(f"canary not run: {problem}")
    runner, results, repos = Runner(), {}, []
    base = tempfile.mkdtemp(prefix=THROWAWAY_PREFIX)

    def new_repo(name):
        repos.append(make_repo(base, name))
        return repos[-1]

    try:
        results["outside_notes"] = outside_notes(runner, new_repo("a"))
        results["passing_facts"] = passing_facts(runner, new_repo("b"))
        results["handoff_without_rule"] = handoff_without_rule(runner, new_repo("c"))
        results["cross_clone"] = cross_clone(runner, new_repo("d"), new_repo("e"))
    finally:
        for repo in repos:
            remove_throwaway_project(repo)
        shutil.rmtree(base, ignore_errors=True)
    version = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.split()[:1]
    record = {
        "ts": round(time.time()),
        "version": version[0] if version else None,
        "cost": round(runner.cost, 4),
        "results": results,
    }
    jsonfile.write_json(os.path.join(state.state_dir(), "canary.json"), record)
    return record
