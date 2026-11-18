"""The ::automem commands that are answered by the hook itself and never reach Claude.

Claude Code shows a hook's answer as plain text (no markdown, and maybe no fixed-width font), so
answers are laid out with line breaks, short labels and a few marks, never with columns or markup.
"""

import os
import subprocess
import sys

from automem import canary, constants, gitrepo, handoff, plugin, promote, review, status, store

GROUPS = [
    (
        "Every day",
        [
            ("::handoff", "Claude updates the handoff note now"),
            ("::automem status", "is it working here: rules, handoff, sync, anything waiting"),
            ("::automem review", "which features and notes earn their keep (no model call)"),
        ],
    ),
    (
        "Several machines",
        [
            (
                "::automem reconcile",
                'Claude unites memory merged from several machines; "reconcile all" repeats earlier copies',
            ),
            ("::automem sync", 'this repo\'s sync; "sync on" opts it in, "sync off" keeps it local-only'),
        ],
    ),
    (
        "Setup",
        [
            ("::automem store <git-url>", 'clone your private store repo; "store init" makes a local one'),
            ("::automem owner <github-name>", "repos owned by this account sync automatically"),
        ],
    ),
    (
        "Tuning",
        [
            (
                "::automem promote",
                'list preference notes; "promote <note>" moves one into ~/.claude/rules/ for every project',
            ),
            ("::automem retire <feature>", 'turn a feature off; "enable <feature>" turns it back on'),
            (
                "::automem canary",
                f"check whether built-in auto memory now covers these features ({constants.CANARY_COST})",
            ),
        ],
    ),
]


def overview(unknown=""):
    lines = [f"::automem {unknown} isn't a command here, or it's missing an argument.", ""] if unknown else []
    lines.append(f"automem-plus {plugin.version()} · a thin layer on Claude Code's built-in auto memory")
    for title, commands in GROUPS:
        lines += ["", title] + [f"  {command}  →  {what}" for command, what in commands]
    lines += [
        "",
        "Features: "
        + " · ".join(f"{name} {'on' if entry.get('enabled') else 'OFF'}" for name, entry in plugin.features().items()),
    ]
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
        "::automem review shows the result."
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


def run(text, cwd):
    """The answer to ::automem <text>. Anything that isn't a complete command gets the overview."""
    words = text.split()
    name = words[0].lower() if words else ""
    handler, arity = COMMANDS.get(name, (None, ()))
    if handler and (arity is ANY or len(words) - 1 in arity):
        return handler(words[1:], cwd)
    return overview("" if name in ("", "help") else text)
