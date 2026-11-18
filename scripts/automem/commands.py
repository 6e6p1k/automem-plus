"""The plugin's commands, and the ones the hook answers itself without reaching Claude.

Each command can be typed two ways: /automem-plus:<name> (a real slash command, so it shows in the
/ menu) or ::automem <name>. Either way the prompt hook sees the text first. For every command but
handoff and reconcile it answers and blocks the prompt, which costs no tokens and leaves nothing
in Claude's context.

Claude Code shows a hook's answer as plain text (no markdown, and maybe no fixed-width font), so
answers are laid out with line breaks, short labels and a few marks, never with columns or markup.
"""

import os
import subprocess
import sys
from typing import NamedTuple

from automem import canary, constants, gitrepo, handoff, plugin, promote, review, status, store


class Command(NamedTuple):
    name: str
    args: str  # the argument hint, as the skill's frontmatter shows it
    what: str


GROUPS = [
    ("Every day", [
        Command("handoff", "", "Claude updates the handoff note now"),
        Command("status", "", "is it working here: rules, handoff, sync, anything waiting"),
        Command("review", "", "which features and notes earn their keep (no model call)"),
    ]),
    ("Several machines", [
        Command("reconcile", "[all]", 'Claude unites memory merged from several machines; "all" repeats old copies'),
        Command("sync", "[on|off]", 'this repo\'s sync; "on" opts it in, "off" keeps it local-only'),
    ]),
    ("Setup", [
        Command("store", "<git-url>|init", 'clone your private store repo; "init" makes a local one'),
        Command("owner", "<github-name>", "repos owned by this account sync automatically"),
    ]),
    ("Tuning", [
        Command("promote", "[<note>]", "list preference notes, or move one into ~/.claude/rules/ for every project"),
        Command("retire", "<feature>", "turn a feature off"),
        Command("enable", "<feature>", "turn a feature back on"),
        Command("canary", "", f"check whether built-in memory now covers these features ({constants.CANARY_COST})"),
    ]),
    ("Help", [
        Command("help", "", "this list"),
    ]),
]  # fmt: skip


def spelled(name, args=""):
    """A command the way the user types it."""
    return f"/{constants.PLUGIN_NAME}:{name}" + (f" {args}" if args else "")


def overview(unknown=""):
    lines = [f"{spelled(unknown)} isn't a command here, or it's missing an argument.", ""] if unknown else []
    lines.append(f"automem-plus {plugin.version()} · a thin layer on Claude Code's built-in auto memory")
    for title, commands in GROUPS:
        lines += ["", title] + [f"  {spelled(c.name, c.args)}  →  {c.what}" for c in commands]
    lines += ["", "Each one also works as ::automem <name>, and the handoff as ::handoff."]
    lines += ["", "Features: " + " · ".join(f"{name} {'on' if entry.get('enabled') else 'OFF'}"
                                            for name, entry in plugin.features().items())]  # fmt: skip
    return "\n".join(lines)


def _review(args, cwd):
    return review.report()


def _status(args, cwd):
    root, is_git = gitrepo.project_root(cwd)
    return status.describe(root, handoff.handoff_name(gitrepo.branch(cwd) if is_git else None))


def _retire(args, cwd):
    return plugin.set_feature(args[0], False)


def _enable(args, cwd):
    return plugin.set_feature(args[0], True)


def _store(args, cwd):
    return store.create_store(args[0])


def _owner(args, cwd):
    return store.add_owner(args[0])


def _promote(args, cwd):
    root, _ = gitrepo.project_root(cwd)
    if not root:
        return "Not in a project folder."
    return promote.promote(root, args[0]) if args else promote.list_text(root)


def _sync(args, cwd):
    root = gitrepo.repo_root(cwd)
    if not root:
        return "This folder isn't a git repo, so there's nothing to sync."
    if args and args[0].lower() in ("on", "off"):
        return store.set_repo(root, args[0].lower() == "on")
    on, why = store.sync_status(root)
    return f"Sync for this repo is {'on' if on else 'off'}: {why}."


def _canary(args, cwd):
    problem = canary.unsafe_reason()
    if problem:
        return f"Canary not started: {problem}"
    subprocess.Popen(
        [sys.executable, os.path.join(constants.SCRIPTS_DIR, "run_canary.py")],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return (
        f"Canary started in the background (six short calls, {constants.CANARY_COST}). "
        "/automem-plus:review shows the result."
    )


ANY = None  # extra words after the command are ignored
COMMANDS = {  # name: (handler, how many arguments it takes)
    "review": (_review, ANY),
    "status": (_status, ANY),
    "canary": (_canary, ANY),
    "retire": (_retire, (1,)),
    "enable": (_enable, (1,)),
    "store": (_store, (1,)),
    "owner": (_owner, (1,)),
    "promote": (_promote, (0, 1)),
    "sync": (_sync, (0, 1)),
}


def run(name, args, cwd):
    """The answer to one of the commands the hook answers. Anything that isn't a complete command
    gets the overview."""
    handler, arity = COMMANDS.get(name, (None, ()))
    if handler and (arity is ANY or len(args) in arity):
        return handler(args, cwd)
    return overview("" if name == "help" else " ".join([name, *args]))
