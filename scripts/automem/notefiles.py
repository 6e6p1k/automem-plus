"""Notes as opaque files: listing, reading, writing and backing up. Nothing here looks inside a note."""

import hashlib
import os
import time

from automem import constants, state


def read_bytes(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def lines_of(data):
    return data.decode("utf-8", "replace").splitlines() if data is not None else []


def digest(data):
    return hashlib.sha1(data).hexdigest() if data is not None else None


def files(folder):
    """Relative paths of the regular .md notes in a folder (symlinks and MEMORY.md excluded)."""
    found = set()
    for base, _dirs, names in os.walk(folder):
        for name in names:
            path = os.path.join(base, name)
            if name.endswith(".md") and not os.path.islink(path):
                found.add(os.path.relpath(path, folder))
    return found - {constants.INDEX_FILE}


def put(path, data):
    if data is None:
        if os.path.exists(path):
            os.remove(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def backup(key, rel, data, side):
    if data is None:
        return None
    folder = os.path.join(state.state_dir(), "backups", time.strftime("%Y%m%d-%H%M%S"), key.replace("/", "__"), side)
    path = os.path.join(folder, rel)
    put(path, data)
    return path
