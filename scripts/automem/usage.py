"""The usage log: one line per event, with file names and a repo hash but never any content.
It is what ::automem review judges features by. Machine-local, never synced.
"""

import json
import os
import time

from automem import claudecode, gitrepo, jsonfile, state


def log_usage(feature, event, **fields):
    record = {"ts": round(time.time()), "feature": feature, "event": event, **fields}
    with open(os.path.join(state.state_dir(), "usage.jsonl"), "a") as f:
        f.write(json.dumps(record) + "\n")


def read_usage():
    records = []
    try:
        with open(os.path.join(state.state_dir(), "usage.jsonl")) as f:
            for line in f:
                try:
                    records.append(json.loads(line))
                except ValueError:
                    continue  # a half-written line from a killed hook
    except OSError:
        pass
    return records


def remember_repo(root):
    """Map the usage log's repo hash to its memory folder (machine-local), so the review can list notes."""
    path = os.path.join(state.state_dir(), "repos.json")
    repos = jsonfile.read_json(path, {}) or {}
    rid = gitrepo.repo_hash(root)
    if repos.get(rid) != claudecode.memory_dir(root):
        repos[rid] = claudecode.memory_dir(root)
        jsonfile.write_json(path, repos)
    return rid
