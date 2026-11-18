#!/usr/bin/env python3
"""Sync one repo's notes with the store now. The Stop hook runs this in the background.

Usage: sync_repo.py <repo-root> [--push]
"""

import dataclasses
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from automem import sync  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    report = sync.run(sys.argv[1], push_now="--push" in sys.argv)
    print(
        json.dumps(dataclasses.asdict(report), indent=1)
        if report
        else "Sync is off for this repo, or another sync is running."
    )
