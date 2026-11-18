# automem-plus

A thin layer on [Claude Code](https://claude.com/claude-code)'s built-in auto memory.

Built-in auto memory stores notes per project and loads them into each session. automem-plus doesn't replace it and keeps no notes of its own. It adds what built-in memory doesn't do: it keeps a handoff note current so the next session can continue, saves facts you mention in passing, carries notes between your machines through a git repo you own, and measures which of its own features are worth keeping.

It's three hooks and a dozen slash commands. It makes no model calls of its own unless you run the canary, and the notes stay ordinary auto-memory files that Claude Code reads without the plugin.

> **Status:** early (0.7). Written and used by one person, covered by tests, and tried in real sessions on macOS. Sync has not yet been run between two real machines over a long period. See [Limits](#limits).

## What it adds

| Built-in auto memory alone | With automem-plus |
|---|---|
| A "where we are" note gets written sometimes and then goes stale | **Handoff note:** one note per branch with Goal, Where we are, Tried and failed, Open decisions, Next steps. Claude rewrites it when you say you're done, after a push, or on `/automem-plus:handoff` |
| Facts mentioned while asking for something else aren't saved | **Passing facts:** "our CI only runs on Fridays" gets saved like an explicit "remember this" |
| Notes live on one machine, under one clone path | **Sync:** notes travel through a private git repo, matched by the project's origin URL |
| Two machines can leave the same fact under two names, or notes that disagree | **Reconcile:** `/automem-plus:reconcile` has Claude unite them. It proposes, you agree, it edits |
| Nothing tells you a status note is out of date | **Nudge:** a line after a turn when you committed and the handoff is older than the commit |
| No way to tell which memory habits pay off | **Review:** a local usage log, and a keep-or-retire suggestion per feature |

The first two rows describe built-in behaviour on Claude Code 2.1.323, checked with the plugin's own [canary](#review-and-the-canary). Built-in memory keeps improving, which is why every feature here can be measured and switched off.

## Requirements

- Claude Code with auto memory on (the plugin does nothing in projects where it's off).
- `python3` 3.9 or newer on your PATH. No packages to install.
- `git`, for sync and the commit nudge. The rules work without it.
- macOS or Linux, including WSL. Native Windows is untested.

## Install

```bash
claude plugin marketplace add 6e6p1k/automem-plus
```

```bash
claude plugin install automem-plus@automem-plus
```

Restart Claude Code. To try it for one session without installing, clone the repo and run `claude --plugin-dir /path/to/automem-plus`.

Then, in any project, type:

```text
/automem-plus:status
```

It shows whether the rules were injected, whether a handoff exists, and whether this project syncs. `/automem-plus:help` lists every command, and typing `/automem` brings them up in the menu.

## How it works

| Hook | What it does | Cost |
|---|---|---|
| Session start | Adds the two rules to Claude's context. In a git repo that syncs, it also pulls and merges notes from the store (bounded to a few seconds) | The rules' text, about 550 tokens |
| Your prompt | Sees the plugin's commands before Claude does. It answers most of them itself and blocks the prompt; `handoff` and `reconcile` pass through to Claude with extra instructions | None for the answered ones: no model turn, and nothing added to Claude's context |
| End of each turn | Reads the transcript for which notes were read or written, shows a notice if one applies, and pushes notes in the background if any changed | None |

The notices after a turn are one line each, shown to you and not to Claude:

- you committed and the handoff note is older than the commit;
- a sync found notes that differ between machines, so `/automem-plus:reconcile` has something to do;
- Claude Code was updated, so the canary may be worth running;
- a month of usage is logged, so a review is due.

The plugin never writes or edits a note. Claude does, following the rules, into the same folder built-in memory uses. Sync copies whole files and never looks inside them.

## The handoff note

The rule tells Claude to keep one note for the work in this session: `handoff-<branch>.md` in a git repo (worktrees share one memory folder, so each branch gets its own), plain `handoff.md` elsewhere.

- **Updated** when you say you're done for now, after a push, and on `/automem-plus:handoff`. It's rewritten in place.
- **Read** at the start of a session when your first message is about continuing, and checked against `git log`.
- **Folded:** an older status note about the same work is merged into it and removed. Handoffs of branches that no longer exist are pointed out at session start.

Nothing forces Claude to do this. It's an instruction, backed by the nudge and measured by the review. The rule texts are in [`rules/`](rules/).

## Sync between machines

Sync is off until you create the store, a git repo at `~/.claude/memory-store/`.

1. Create a **private** repo on your git host, then: `/automem-plus:store <git-url>`. Without a remote, `/automem-plus:store init` makes a local store.
2. Say whose repos sync: `/automem-plus:owner <your-github-name>`. Projects whose origin belongs to that account then sync automatically.
3. For any other project: `/automem-plus:sync on` opts it in, `/automem-plus:sync off` keeps it local-only.

On a second machine, install the plugin and run step 1 with the same URL. The owner list comes with the store.

**How the merge works.** It's a three-way merge per note, against what was last synced:

- **Changed on one side:** that side wins, and deletions propagate.
- **Changed on both sides:** the local copy wins and the other is saved.
- **First seen on both sides:** the newer copy wins and the other is saved.
- **`MEMORY.md`:** merged line by line. Lines either side removed stay removed, and new lines from both are kept.

**What keeps it safe:**

- Before a note is overwritten or deleted by an import, the local copy is saved under the state folder's `backups/`.
- There is no `git reset` anywhere. A rejected push is merged, never forced.
- An emptied memory folder or a re-created store is never read as "delete everything".
- A note that looks like it holds a credential is never pushed, and neither is its index line. This is pattern matching, so treat it as a safety net, not a guarantee.
- Sync turns itself off when `autoMemoryDirectory` is set at user or project level, because then the folder isn't one repo's alone.

## Uniting memory from two machines

A file merge can't see that two notes say the same thing, or that they disagree. After two machines' notes have been brought together, run this on the machine that joined second:

```text
/automem-plus:reconcile
```

Claude gets the copies that lost a file conflict (quoted, up to 20 copies of 6,000 characters each), the names of the notes that arrived from the other machine, and these rules:

- **The same thing in two notes:** merge into one.
- **A copy that lost a conflict:** carry over anything true that the kept note lacks.
- **Notes that disagree:** the newer one doesn't win by default. The state of the work is checked against `git log` and goes into the handoff. A preference of yours is shown both ways and you're asked. A fact is checked or asked about.

It lists every change with a reason first and changes nothing until you answer. The result syncs like any other edit, and earlier versions stay in the store's git history.

Run it where the two copies met: the copy that lost is saved only on that machine.

## Review and the canary

Each feature in [`features.json`](features.json) declares up front what "used" means and when it should be retired.

- **`/automem-plus:review`** reads the local usage log and gives each feature a verdict: collecting data, keep, or retire. You decide with `/automem-plus:retire <feature>` and `/automem-plus:enable <feature>`.
- **`/automem-plus:canary`** checks whether built-in memory now does a feature without the plugin. It makes six short Haiku calls in throwaway repos (about $0.07) with the plugin switched off, and deletes those repos and their memory afterwards. It runs only when you ask.

## Commands

| Command | What it does | Answered by |
|---|---|---|
| `/automem-plus:handoff` | Claude updates the handoff note now | Claude |
| `/automem-plus:status` | Is it working here: rules, handoff, sync, anything waiting | the hook |
| `/automem-plus:review` | Which features and notes earn their keep | the hook |
| `/automem-plus:reconcile [all]` | Claude unites memory merged from several machines. `all` repeats copies from earlier runs | Claude |
| `/automem-plus:sync [on\|off]` | This repo's sync. `on` opts it in, `off` keeps it local-only | the hook |
| `/automem-plus:store <git-url>\|init` | Clone your store repo. `init` makes a local one | the hook |
| `/automem-plus:owner <github-name>` | Repos owned by this account sync automatically | the hook |
| `/automem-plus:promote [<note>]` | List preference notes, or move one into `~/.claude/rules/` so every project gets it | the hook |
| `/automem-plus:retire <feature>` | Turn a feature off | the hook |
| `/automem-plus:enable <feature>` | Turn a feature back on | the hook |
| `/automem-plus:canary` | Check whether built-in memory now covers these features | the hook |
| `/automem-plus:help` | This list | the hook |

**Why two kinds.** A plugin's slash command is normally a prompt handed to Claude, which costs a model turn. For everything that is only a lookup or a setting, the prompt hook answers first and blocks the prompt, so the command costs no tokens and leaves nothing in Claude's context. The commands still exist as skills, which is what puts them in the `/` menu.

**Short form.** Every command also works as `::automem <name>`, and the handoff as `::handoff`. The hook treats both spellings the same.

Answers from the hook are plain text, because Claude Code shows them without rendering markdown. Claude Code frames them as a prompt "blocked by hook"; that wording is its own, not an error.

## Configuration

| Setting | Default | What it is |
|---|---|---|
| `AUTOMEM_DISABLE` | unset | Any non-empty value switches every hook off for that process |
| `AUTOMEM_STORE` | `~/.claude/memory-store` | The store repo |
| `AUTOMEM_STATE` | `~/.claude/memory-state/automem` | Machine-local state: usage log, sync bases, backups |
| `features.json` | all on | The features and their retire rules. The `retire` and `enable` commands keep your choice in the state folder |

Thresholds such as "a working session is three or more prompts" are named in [`scripts/automem/constants.py`](scripts/automem/constants.py).

## Privacy and security

- **Nothing is sent anywhere except your own store.** Notes go to the git remote you configured, and only for projects you opted in. There is no telemetry.
- **The usage log holds no note content.** It records timestamps, event names, note file names (a handoff's name includes the branch), a hash of the repo's origin, and the type of an error when a sync fails. It stays on the machine.
- **The transcript is read locally,** only to find tool calls that touched the memory folder.
- **Hooks run as you.** Like any Claude Code plugin with hooks, this one runs Python on your machine with your permissions on every session. The code is about 2,500 lines in [`scripts/`](scripts/); read it before installing.
- **Keep the store private.** Your notes can hold anything you've told Claude about a project.

## Limits

- **Cloud sessions:** Claude Code's cloud and mobile sessions don't load plugins installed on your machine, so the plugin doesn't run there.
- **Not yet proven over time:** two-machine sync and reconcile are covered by tests with two simulated machines and by one real trial each, not by months of use. Long sessions with compaction are untested.
- **Usage counting reads command text.** A note counts as read or written when a tool call names it: by full path, by a variable set in the same command, by a glob, or by a bare name after `cd` into the memory folder. A variable set in an earlier command, and edits made by a script inside a heredoc, aren't counted.
- **Facts used straight from their index line aren't counted,** because the note is never opened. The passing-facts rule therefore has no automatic verdict; the canary judges it.
- **The memory folder's name is inferred.** Claude Code doesn't document how it names project folders, so sync writes only into a folder that already exists or that the session's own transcript path confirms.
- **Deleting every note doesn't propagate.** It's indistinguishable from a wiped folder, so the notes come back. Delete them one at a time.
- **Index lines arriving at session start:** Claude Code loads `MEMORY.md` before hooks run, so lines that just arrived are passed to Claude in the session context instead.

## Troubleshooting

- **Nothing happens.** Run `/automem-plus:status`. If auto memory is off for the project, the plugin stays out of the way by design.
- **A hook error mentions `python3`.** It isn't on the PATH Claude Code sees.
- **Status says a push failed.** The commit is safe in the local store; the next sync retries. Check that `git push` works in `~/.claude/memory-store`.
- **You want it off for one command or script.** Set `AUTOMEM_DISABLE=1`. To turn it off everywhere, `claude plugin disable automem-plus@automem-plus`.
- **A note was overwritten and you want the old one.** Look in `~/.claude/memory-state/automem/backups/`, or in the store's git history.

## Development

```text
hooks/hooks.json        the three hooks
skills/                 one per command, so each shows in the / menu
rules/                  the texts Claude is given
features.json           each feature's "used" measure and retire rule
scripts/*.py            hook entry points and two background jobs
scripts/automem/        the package, one module per concern
tests/                  pytest, split by subject
```

Tests need only pytest and git. They run in temp dirs and never touch your real `~/.claude`, store or memory:

```bash
python3 -m pytest -q
```

```bash
ruff check . && ruff format --check .
```

Sync's merge rules are documented at the top of [`scripts/automem/merge.py`](scripts/automem/merge.py).

## License

[MIT](LICENSE)
