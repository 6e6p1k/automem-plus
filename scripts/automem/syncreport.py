"""What one sync did, as a value the merge, the transport and the records all share."""

from dataclasses import dataclass, field
from typing import NamedTuple, Optional


class LostCopy(NamedTuple):
    """A note two machines both wrote: one copy was kept, the other saved for /automem-plus:reconcile."""

    file: str  # the note, relative to the memory folder
    kept: str  # "local" or "store": whose copy stayed in the folder
    backup: str  # where the copy that lost was saved
    folder: Optional[str] = None  # the repo's folder in the store, when it isn't the repo being synced


@dataclass
class SyncReport:
    imported: list[str] = field(default_factory=list)  # notes written into the memory folder
    exported: list[str] = field(default_factory=list)  # notes written into the store
    deleted_here: list[str] = field(default_factory=list)  # deletions that arrived from another machine
    conflicts: list[str] = field(default_factory=list)  # notes both sides changed
    skipped: list[str] = field(default_factory=list)  # looked like a secret, so never exported
    backups: list[str] = field(default_factory=list)  # paths of the copies saved before an overwrite
    lost: list[LostCopy] = field(default_factory=list)
    index_lines: list[str] = field(default_factory=list)  # MEMORY.md lines that are new to this machine
    # None (nothing pushed), "pushed", "pushed after merge", "push failed", "conflict" or "commit failed"
    push: Optional[str] = None
    fetched: bool = True  # False when the store's remote couldn't be reached
