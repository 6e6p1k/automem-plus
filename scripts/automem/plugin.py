"""The plugin's own manifest and feature switches."""

import os

from automem import constants, jsonfile, state, usage


def features():
    """features.json, with the user's on/off overrides (/automem-plus:retire, /automem-plus:enable) applied."""
    registry = jsonfile.read_json(constants.FEATURES_FILE, {}) or {}
    overrides = jsonfile.read_json(os.path.join(state.state_dir(), "feature_flags.json"), {}) or {}
    for name, entry in registry.items():
        entry["enabled"] = overrides.get(name, entry.get("enabled", True))
    return registry


def feature_on(name):
    return bool(features().get(name, {}).get("enabled"))


def version():
    return (jsonfile.read_json(constants.MANIFEST_FILE, {}) or {}).get("version", "?")


def set_feature(name, enabled):
    """Switch a feature on or off for this machine (/automem-plus:enable, /automem-plus:retire)."""
    if name not in features():
        return f"No feature {name}. Features: {', '.join(features())}"
    path = os.path.join(state.state_dir(), "feature_flags.json")
    flags = jsonfile.read_json(path, {}) or {}
    flags[name] = enabled
    jsonfile.write_json(path, flags)
    usage.log_usage(name, "enabled" if enabled else "retired")
    return f"{name} is now {'on' if enabled else 'off'}."
