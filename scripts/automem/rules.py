"""The rule texts injected at session start (the files in rules/)."""

import os

from automem import constants, plugin

RULE_FILES = {"handoff_rule": "handoff.md", "passing_facts_rule": "passing-facts.md"}


def rules_text(handoff_file, branch_name):
    parts = []
    for feature, name in RULE_FILES.items():
        if plugin.feature_on(feature):
            with open(os.path.join(constants.RULES_DIR, name)) as f:
                text = f.read().strip()
            clause = f", for branch `{branch_name}`" if branch_name else ""
            parts.append(text.replace("{handoff_file}", handoff_file).replace("{branch_clause}", clause))
    return parts
