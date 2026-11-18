"""Reads a session transcript for what touched the memory folder: Read, Write and Edit calls, and
Bash commands that name a note. This is where the usage log's note events come from.
"""

import fnmatch
import json
import os
import re
from typing import NamedTuple

MEMORY_TOOLS = {"Read": "read", "Write": "write", "Edit": "write", "MultiEdit": "write"}


class NoteEvent(NamedTuple):
    """One read or write of a memory note found in the transcript."""

    event: str  # "read" or "write"
    file: str  # the note, relative to the memory folder
    prompt: int  # how many prompts the user had typed by then
    tool_id: str  # the end of the tool call's id: the same call seen twice is one event


def is_typed_prompt(entry):
    if entry.get("type") != "user" or entry.get("isMeta"):
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return not content.startswith("<")  # command echoes and caveats are wrapped in tags
    if isinstance(content, list):
        kinds = {b.get("type") for b in content if isinstance(b, dict)}
        return "text" in kinds and "tool_result" not in kinds
    return False


NOTE_RE = r"[\w.\-/]*?([\w.\-*]+\.md)"
RELATIVE_NOTE = re.compile(r"(?<![\w/$~}{.*\-])(?:\./)?([\w.\-*]+\.md)(?![\w/*.])")
WRITE_BEFORE = re.compile(r"(>>?|\btee(\s+-a)?)\s*[\"']?$")
SEPARATORS = r"&&|\|\||;|\||\n"
CD_RE = re.compile(r"^\s*\(?\s*(?:cd|pushd)\s+[\"']?([^\s\"']+)[\"']?\s*\)?\s*$")
HEREDOC = re.compile(r"(<<-?\s*[\"']?(\w+)[\"']?[^\n]*)\n.*?^[ \t]*\2[ \t]*$", re.S | re.M)
QUOTED = re.compile(r"\"[^\"\n]*\"|'[^'\n]*'")
LISTING = {"ls", "find", "echo", "printf", "wc", "stat", "du"}  # naming every note with a glob isn't reading them


def folder_spellings(command, folder):
    """The ways a command can name the memory folder: its path, with ~ or $HOME, and any shell
    variable the command itself sets to one of those (M=<folder>; cat $M/note.md)."""
    spellings = {folder.rstrip(os.sep)}
    home = os.path.expanduser("~")
    if folder.startswith(home):
        tail = folder[len(home) :].rstrip(os.sep)
        spellings |= {"~" + tail, "$HOME" + tail, "${HOME}" + tail}
    for spelling in list(spellings):
        for match in re.finditer(r"\b(\w+)=[\"']?" + re.escape(spelling) + r"/?[\"']?(?=[\s;&]|$)", command):
            name = match.group(1)
            spellings |= {f"${name}", f"${{{name}}}", f'"${name}"', f'"${{{name}}}"'}
    return spellings


def note_event(command, start, end):
    """('read' or 'write', the command text before the note) for the note named at command[start:end]."""
    before = command[:start]
    segment = re.split(SEPARATORS, before)[-1]
    rest = re.split(SEPARATORS, command[end:])[0]
    is_destination = re.search(r"\b(cp|mv)\b", segment) and not rest.strip(" '\"")
    if WRITE_BEFORE.search(before) or re.search(r"\b(sed\s+-i|rm)\b", segment) or is_destination:
        return "write", segment
    return "read", segment


def expand(name, event, segment, existing):
    """A glob (*.md) stands for every note it matches, unless the command only lists them."""
    if "*" not in name:
        return [name]
    words = segment.strip(" (").split()
    if event == "read" and words and words[0] in LISTING:
        return []
    return sorted(n for n in existing if fnmatch.fnmatchcase(n, name))


def relative_events(command, spellings, existing):
    """Notes named without the folder, after the command cd'd into it: cd <folder> && cat note.md.
    Heredoc bodies and quoted prose are dropped first, since they mention notes without touching them."""
    plain = QUOTED.sub(lambda m: m.group(0) if not re.search(r"\s", m.group(0)) else '""', HEREDOC.sub(r"\1", command))
    found, inside, pos = [], False, 0
    for separator in [*re.finditer(SEPARATORS, plain), None]:
        stop_at = separator.start() if separator else len(plain)
        segment = plain[pos:stop_at]
        cd = CD_RE.match(segment)
        if cd:
            inside = cd.group(1).rstrip("/") in {spelling.strip('"') for spelling in spellings}
        elif inside:
            for match in RELATIVE_NOTE.finditer(segment):
                event, before = note_event(plain, pos + match.start(), pos + match.end())
                for name in expand(match.group(1), event, before, existing):
                    if event == "write" or name in existing:  # a bare name only counts when it is a note
                        found.append((event, name))
        pos = separator.end() if separator else stop_at
    return found


def bash_memory_events(command, folder, existing=None):
    """(event, note) for each memory note a Bash command touches: writes through >, >>, tee, cp, mv,
    sed -i or rm; anything else that names a note (cat, head, sed -n, grep) counts as a read.
    The note can be named by its full path, through a variable the command sets, by a glob, or by
    its bare name after a cd into the folder. existing is the folder's notes (for globs and bare names)."""
    if existing is None:
        existing = {n for n in os.listdir(folder) if n.endswith(".md")} if os.path.isdir(folder) else set()
    found = []
    spellings = folder_spellings(command, folder)
    for spelling in spellings:
        for match in re.finditer(re.escape(spelling) + r"/" + NOTE_RE, command):
            event, segment = note_event(command, match.start(), match.end())
            found += [(event, name) for name in expand(match.group(1), event, segment, existing)]
    return list(dict.fromkeys(found + relative_events(command, spellings, existing)))  # once per note and event


def scan_transcript(path, session_state, folder):
    """New tool calls on files in the memory folder since the last Stop: [(event, rel, prompt_no, tool_id)].
    Reads from a byte offset; a transcript that shrank (rewritten) is read again from the start."""
    events = []
    try:
        size = os.path.getsize(path)
    except OSError:
        return events
    offset = session_state.get("offset", 0)
    if size < offset:
        offset, session_state["prompts"] = 0, 0
    folder = os.path.realpath(folder) + os.sep
    prompts = session_state.get("prompts", 0)
    with open(path, "rb") as f:
        f.seek(offset)
        chunk = f.read()
    complete = chunk[: chunk.rfind(b"\n") + 1]  # leave a half-written last line for next time
    for raw in complete.splitlines():
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if entry.get("version"):
            session_state["version"] = entry["version"]
        if is_typed_prompt(entry):
            prompts += 1
            continue
        if entry.get("type") != "assistant":
            continue
        for block in (entry.get("message") or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            tool_id = (block.get("id") or "")[-12:]
            if block.get("name") == "Bash":
                command = (block.get("input") or {}).get("command") or ""
                for event, note in bash_memory_events(command, folder.rstrip(os.sep)):
                    events.append(NoteEvent(event, note, prompts, tool_id))
                continue
            event = MEMORY_TOOLS.get(block.get("name"))
            target = (block.get("input") or {}).get("file_path") or ""
            if not event or not target:
                continue
            real = os.path.realpath(os.path.expanduser(target))
            if real.startswith(folder):
                events.append(NoteEvent(event, os.path.relpath(real, folder.rstrip(os.sep)), prompts, tool_id))
    session_state["offset"], session_state["prompts"] = offset + len(complete), prompts
    return events
