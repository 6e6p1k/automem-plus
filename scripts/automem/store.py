"""The store: the git repo that carries notes between machines, its config, and which repos sync.

The store lives at ~/.claude/memory-store/ (or $AUTOMEM_STORE). Each repo's notes sit in
automem/<host>__<owner>__<repo>/, named after the repo's origin URL so every clone of it maps to
the same folder. Which repos sync is the store's automem.json:
{"owners": [...], "include": [...], "exclude": [...]}.
"""

import os

from automem import claudecode, gitrepo, jsonfile, plugin, state

CONFIG_NAME = "automem.json"
ATTRIBUTES = "automem/** -merge\nautomem/**/MEMORY.md merge=union\n"
GIT_ID = ("-c", "user.name=automem", "-c", "user.email=automem@localhost", "-c", "commit.gpgsign=false")


def store_ready():
    return os.path.isdir(os.path.join(state.store_dir(), ".git"))


def has_remote():
    return bool(gitrepo.git("remote", cwd=state.store_dir(), timeout=5).stdout.strip())


def has_upstream():
    return gitrepo.git("rev-parse", "--abbrev-ref", "@{u}", cwd=state.store_dir(), timeout=5).returncode == 0


def config():
    data = jsonfile.read_json(os.path.join(state.store_dir(), CONFIG_NAME), {}) or {}
    return {key: [str(v).lower() for v in data.get(key, [])] for key in ("owners", "include", "exclude")}


def save_config(cfg, message):
    jsonfile.write_json(os.path.join(state.store_dir(), CONFIG_NAME), cfg)
    gitrepo.git("add", CONFIG_NAME, cwd=state.store_dir())
    gitrepo.git(*GIT_ID, "commit", "-q", "-m", message, cwd=state.store_dir())


def sync_status(root):
    """(on, why) for this repo."""
    if not plugin.feature_on("sync"):
        return False, "sync is retired (::automem enable sync turns it back on)"
    if not store_ready():
        return False, (
            f"there's no store at {state.store_dir()} yet (::automem store <git-url> clones one, "
            f"::automem store init makes a local one)"
        )
    custom_scope = claudecode.setting_scope(root, "autoMemoryDirectory")
    if custom_scope in ("user", "project"):
        return False, f"autoMemoryDirectory is set in {custom_scope} settings, so the folder isn't this repo's alone"
    key = gitrepo.remote_key(root)
    if not key:
        return False, "this repo has no origin remote"
    cfg = config()
    if key in cfg["exclude"]:
        return False, "this repo is local-only"
    if key in cfg["include"]:
        return True, "this repo is opted in"
    owner = key.split("/")[1] if key.count("/") >= 2 else ""
    if owner in cfg["owners"]:
        return True, f"the repo owner {owner} is yours"
    return False, "not your repo (::automem sync on opts it in)"


def folder_name(key):
    return key.replace("/", "__")


def store_folder(key):
    return os.path.join(state.store_dir(), "automem", folder_name(key))


def store_root_commit():
    out = gitrepo.git("rev-list", "--max-parents=0", "HEAD", cwd=state.store_dir(), timeout=10).stdout.split()
    return out[0] if out else None


def ensure_attributes():
    path = os.path.join(state.store_dir(), ".gitattributes")
    current = ""
    if os.path.exists(path):
        with open(path) as f:
            current = f.read()
    if current != ATTRIBUTES:
        with open(path, "w") as f:
            f.write(ATTRIBUTES)


def set_repo(root, on):
    key = gitrepo.remote_key(root)
    if not store_ready():
        return (
            f"No store at {state.store_dir()} yet: ::automem store <git-url> clones one, "
            "::automem store init makes a local one."
        )
    if not key:
        return "This repo has no origin remote, so it can't be matched across machines."
    cfg = config()
    for name in ("include", "exclude"):
        cfg[name] = [k for k in cfg[name] if k != key]
    cfg["include" if on else "exclude"].append(key)
    save_config(cfg, f"automem: {'sync' if on else 'local-only'} {key}")
    return f"{key} is now {'synced through the store' if on else 'local-only, never pushed'}."


def add_owner(name):
    if not store_ready():
        return "No store yet: ::automem store <git-url> clones one, ::automem store init makes a local one."
    cfg = config()
    if name.lower() not in cfg["owners"]:
        cfg["owners"].append(name.lower())
        save_config(cfg, f"automem: owner {name.lower()}")
    return f"Repos owned by {name.lower()} now sync. Owners: {', '.join(cfg['owners'])}."


def create_store(source):
    path = state.store_dir()
    if os.path.exists(path) and os.listdir(path):
        return f"{path} already exists and isn't empty, so nothing changed."
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if source == "init":
        os.makedirs(path, exist_ok=True)
        res = gitrepo.git("init", "-q", path)
    else:
        res = gitrepo.git("clone", "-q", "--", source, path, timeout=120)
    if res.returncode != 0:
        return f"Couldn't create the path: {res.stderr.strip()[:300]}"
    if not os.path.exists(os.path.join(path, CONFIG_NAME)):
        save_config({"owners": [], "include": [], "exclude": []}, "automem: config")
    return (
        f"Store ready at {path}. Next: ::automem owner <your-github-name>, so your own repos sync"
        + ("" if source != "init" else ", and add a private remote there to sync between machines")
        + "."
    )
