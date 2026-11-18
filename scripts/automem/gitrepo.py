"""Git, and how a folder maps to a repo: its main checkout, its branch, and the origin URL that
names it across machines.
"""

import hashlib
import os
import re
import subprocess


def git(*args, cwd=None, timeout=20):
    """Run git; never raises (check .returncode). Prompts for credentials are turned off."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args, 1, "", str(exc))


def project_root(cwd):
    """(root, is_git): the folder Claude Code keys auto memory on. In a git repo that's the main
    checkout (worktrees share it); elsewhere it's the folder itself."""
    root = repo_root(cwd)
    if root:
        return root, True
    return (os.path.realpath(cwd), False) if cwd and os.path.isdir(cwd) else (None, False)


def worktree_top(cwd):
    """The checkout the session works in (a worktree's own folder), for HEAD and commit times."""
    top = git("rev-parse", "--show-toplevel", cwd=cwd, timeout=5).stdout.strip()
    return os.path.realpath(top) if top else None


def repo_root(cwd):
    """The main checkout of the git repo containing cwd (worktrees resolve to it), or None."""
    if not cwd or git("rev-parse", "--is-inside-work-tree", cwd=cwd, timeout=5).stdout.strip() != "true":
        return None
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=cwd, timeout=5).stdout.strip()
    if common.endswith(os.sep + ".git"):
        return os.path.realpath(os.path.dirname(common))
    top = git("rev-parse", "--show-toplevel", cwd=cwd, timeout=5).stdout.strip()
    return os.path.realpath(top) if top else None


def branch(cwd):
    """The branch checked out in this worktree, or None (detached HEAD, not a repo)."""
    name = git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd, timeout=5).stdout.strip()
    return name if name and name != "HEAD" else None


def local_branches(cwd):
    out = git("for-each-ref", "--format=%(refname:short)", "refs/heads", cwd=cwd, timeout=5).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def head(root):
    return git("rev-parse", "HEAD", cwd=root, timeout=5).stdout.strip() or None


def last_commit_time(root):
    out = git("log", "-1", "--format=%ct", cwd=root, timeout=5).stdout.strip()
    return int(out) if out.isdigit() else None


def remote_url(root):
    return git("remote", "get-url", "origin", cwd=root, timeout=5).stdout.strip() or None


def normalise_remote(url):
    """'git@github.com:Owner/Repo.git' and 'https://github.com/Owner/Repo' -> 'github.com/owner/repo'."""
    if not url:
        return None
    url = url.strip()
    match = re.match(r"^[\w.-]+@([^:/]+):(.+)$", url)  # scp-like ssh form
    if match:
        host, path = match.groups()
    else:
        match = re.match(r"^[a-z+]+://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+)$", url)
        if not match:
            return None
        host, path = match.groups()
    path = re.sub(r"\.git/?$", "", path.strip("/"))
    if not path:
        return None
    return f"{host.lower()}/{path.lower()}"


def remote_key(root):
    return normalise_remote(remote_url(root))


def repo_hash(root):
    """A short id for the usage log: from the remote when there is one, else the path. Never the name itself."""
    return hashlib.sha1((remote_key(root) or root).encode()).hexdigest()[:10]
