"""Names and tunables shared across the plugin. What belongs to one algorithm stays in its module."""

import os

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PLUGIN_ROOT, "scripts")
RULES_DIR = os.path.join(PLUGIN_ROOT, "rules")
FEATURES_FILE = os.path.join(PLUGIN_ROOT, "features.json")
MANIFEST_FILE = os.path.join(PLUGIN_ROOT, ".claude-plugin", "plugin.json")

DISABLE_ENV = "AUTOMEM_DISABLE"  # any value switches every hook off
STATE_ENV = "AUTOMEM_STATE"  # overrides DEFAULT_STATE_DIR
STORE_ENV = "AUTOMEM_STORE"  # overrides DEFAULT_STORE_DIR
PROJECT_DIR_ENV = "CLAUDE_PROJECT_DIR"  # set by Claude Code for hooks: the folder the session started in
DEFAULT_STATE_DIR = "~/.claude/memory-state/automem"
DEFAULT_STORE_DIR = "~/.claude/memory-store"

HANDOFF_FILE = "handoff.md"
INDEX_FILE = "MEMORY.md"

CANARY_COST = "about $0.07 on Haiku"  # six short calls; what the user is told before it runs

DAY = 86400
ENGAGED_PROMPTS = 3  # a session with this many typed prompts counts as a working session
EARLY_READ_PROMPTS = 3  # the handoff counts as "opened early" when it's read within this many prompts
STALE_DAYS = 60  # the review lists notes nobody opened for this long
REVIEW_NUDGE_MIN_EVENTS = 50  # below this the usage log says too little to suggest a review
REVIEW_NUDGE_AFTER_DAYS = 30  # how long after the last review (or nudge) the Stop line suggests one
SYNC_JUDGED_AFTER_DAYS = 30  # sync gets a keep-or-retire verdict only after running this long
