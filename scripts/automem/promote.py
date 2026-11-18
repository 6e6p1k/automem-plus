"""::automem promote: move a preference that isn't about this project into the user-level rules.

Auto memory is per repo, so "one subagent at most" saved in one project's memory never reaches
the others. Promoting copies the note's text to ~/.claude/rules/automem-<name>.md, which Claude
Code loads in every project, and removes the note from this repo's memory (a backup is kept).
"""

import os
import re
import time

from automem import claudecode, constants, gitrepo, handoff, state, usage


def _read(path):
    with open(path, errors="replace") as f:
        return f.read()


def split_note(text):
    """(frontmatter fields, body). Only reads the simple 'key: value' lines it needs."""
    fields, body = {}, text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].splitlines():
                match = re.match(r"\s*(name|description|type):\s*(.*)", line)
                if match:
                    fields[match.group(1)] = match.group(2).strip().strip('"')
            body = text[end + 4 :].lstrip("\n")
    return fields, body


def candidates(root):
    """Notes that read like preferences about the user rather than facts about this project."""
    folder = claudecode.memory_dir(root)
    found = []
    if not os.path.isdir(folder):
        return found
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".md") or name == constants.INDEX_FILE or handoff.is_handoff(name):
            continue
        fields, _ = split_note(_read(os.path.join(folder, name)))
        if fields.get("type") in ("feedback", "user"):
            found.append((name, fields.get("description", "")))
    return found


def list_text(root):
    found = candidates(root)
    if not found:
        return "No preference-type notes (feedback or user) in this project's memory."
    lines = ["Preference notes in this project's memory. Promote the ones that are about you, not this project:", ""]
    lines += [f"  {name}  →  {desc[:110]}" for name, desc in found]
    lines += ["", "::automem promote <file> moves one into ~/.claude/rules/, so every project gets it."]
    return "\n".join(lines)


def promote(root, name):
    folder = claudecode.memory_dir(root)
    name = os.path.basename(name if name.endswith(".md") else name + ".md")
    path = os.path.join(folder, name)
    if not os.path.isfile(path) or name == constants.INDEX_FILE:
        return f"No note {name} in this project's memory. ::automem promote lists the candidates."
    text = _read(path)
    fields, body = split_note(text)
    rules = os.path.join(claudecode.config_dir(), "rules")
    target = os.path.join(rules, "automem-" + name)
    if os.path.exists(target):
        return f"{target} already exists, so nothing changed."
    title = fields.get("description") or fields.get("name") or name[:-3]
    os.makedirs(rules, exist_ok=True)
    with open(target, "w") as f:
        f.write(
            f"# {title}\n\n<!-- moved by automem-plus from {os.path.basename(root)}'s auto memory, "
            f"{time.strftime('%Y-%m-%d')} -->\n\n{body.strip()}\n"
        )
    backup = os.path.join(state.state_dir(), "backups", time.strftime("%Y%m%d-%H%M%S"), "promoted", name)
    os.makedirs(os.path.dirname(backup), exist_ok=True)
    with open(backup, "w") as f:
        f.write(text)
    os.remove(path)
    index = os.path.join(folder, constants.INDEX_FILE)
    if os.path.exists(index):
        lines = _read(index).splitlines()
        kept = [line for line in lines if f"]({name})" not in line]
        if kept != lines:
            with open(index, "w") as f:
                f.write("\n".join(kept) + ("\n" if kept else ""))
    usage.log_usage("promote", "moved", repo=gitrepo.repo_hash(root), file=name)
    return f"Moved to {target}; every project now loads it. The old note is backed up at {backup}."
