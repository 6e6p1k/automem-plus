#!/usr/bin/env python3
"""Run the canary now and print its result. ::automem canary runs this in the background."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from automem import canary  # noqa: E402

if __name__ == "__main__":
    print(json.dumps(canary.run(), indent=1))
