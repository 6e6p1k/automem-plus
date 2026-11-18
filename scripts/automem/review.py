"""::automem review: which features and notes earn their keep. No model call; nothing changes by itself.

Each feature in features.json declares what "used" means and a kill rule, fixed up front.
The review measures that from the local usage log and suggests keep or retire; the user
decides (::automem retire <feature>, ::automem enable <feature>).
"""

import os
import time
from typing import NamedTuple

from automem import constants, handoff, jsonfile, plugin, state, usage


class Measure(NamedTuple):
    """How one feature did: the number its kill rule is judged on, out of how many cases, and the sentence shown."""

    value: float
    sample: int
    detail: str


def dedupe(notes):
    """A forked or continued session repeats the tool calls it inherited; tool-call ids are unique
    across sessions, so one id is one real event."""
    seen, out = set(), []
    for u in notes:
        key = (u.get("id"), u.get("file"), u.get("event")) if u.get("id") else id(u)
        if key not in seen:
            seen.add(key)
            out.append(u)
    return out


def metrics(events, now):
    starts = [u for u in events if u.get("feature") == "session" and u.get("event") == "start"]
    engaged = {u["session"] for u in events if u.get("feature") == "session" and u.get("event") == "engaged"}
    committed = {u["session"] for u in events if u.get("feature") == "session" and u.get("event") == "committed"}
    notes = dedupe([u for u in events if u.get("feature") == "note"])
    reads = [u for u in notes if u["event"] == "read"]
    writes = [u for u in notes if u["event"] == "write"]
    out = {}

    # Handoff: of the real working sessions (3+ prompts) that started with a handoff, how many opened it early.
    own = {u["session"]: u.get("handoff") or constants.HANDOFF_FILE for u in starts if u.get("has_handoff")}
    with_handoff = set(own) & engaged
    early = {
        u["session"]
        for u in reads
        if u["session"] in with_handoff
        and u.get("file") == own[u["session"]]
        and u.get("prompt", 99) <= constants.EARLY_READ_PROMPTS
    }
    wrote = {u["session"] for u in writes if handoff.is_handoff(u.get("file", ""))}
    out["handoff_rule"] = Measure(
        len(early) / len(with_handoff) if with_handoff else 0.0,
        len(with_handoff),
        f"{len(early)} of {len(with_handoff)} working sessions opened the handoff early; "
        f"{len(committed & wrote)} of {len(committed)} sessions with commits updated it",
    )

    nudges = [u for u in events if u.get("feature") == "staleness_nudge" and u.get("event") == "shown"]
    followed = sum(
        1
        for n in nudges
        if any(
            handoff.is_handoff(w.get("file", "")) and w["session"] == n.get("session") and w["ts"] >= n["ts"]
            for w in writes
        )
    )
    out["staleness_nudge"] = Measure(
        followed / len(nudges) if nudges else 0.0,
        len(nudges),
        f"{followed} of {len(nudges)} nudges were followed by a handoff update",
    )

    # Sync: notes that arrived with new content from another machine in the last 30 days.
    # Judged only once sync has run for 30 days; a one-machine user then sees "retire?".
    first = (jsonfile.read_json(os.path.join(state.state_dir(), "sync_first.json"), {}) or {}).get("ts")
    arrived = [
        u
        for u in events
        if u.get("feature") == "sync"
        and u.get("event") == "imported"
        and u["ts"] >= now - constants.SYNC_JUDGED_AFTER_DAYS * constants.DAY
    ]
    mature = 1 if first and now - first >= constants.SYNC_JUDGED_AFTER_DAYS * constants.DAY else 0
    out["sync"] = Measure(
        len(arrived),
        mature,
        f"{len(arrived)} notes arrived from other machines in 30 days"
        + ("" if first else " (sync hasn't run here)")
        + ("" if mature or not first else " (running < 30 days)"),
    )

    other = {
        u["file"] for u in writes if not handoff.is_handoff(u.get("file", "")) and u.get("file") != constants.INDEX_FILE
    }
    out["passing_facts_rule"] = Measure(
        0.0,
        0,
        f"{len(other)} notes written besides the handoff; judged by the canary, "
        f"not by reads (a fact in its index line is never Read)",
    )
    return out


def verdict(entry, value, sample):
    kill = entry.get("kill")
    if not kill:
        return "no automatic verdict"
    if sample < kill.get("min_sample", 1):
        return f"collecting data ({sample}/{kill.get('min_sample', 1)})"
    return f"retire? (below {kill['below']})" if value < kill["below"] else "keep"


def stale_notes(events, now):
    last_read = {}
    for r in dedupe([u for u in events if u.get("feature") == "note" and u.get("event") == "read"]):
        key = (r["repo"], r["file"])
        last_read[key] = max(last_read.get(key, 0), r["ts"])
    repos = jsonfile.read_json(os.path.join(state.state_dir(), "repos.json"), {}) or {}
    stale = []
    for rid, folder in repos.items():
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".md") or name == constants.INDEX_FILE or handoff.is_handoff(name):
                continue
            path = os.path.join(folder, name)
            if (
                now - os.path.getmtime(path) > constants.STALE_DAYS * constants.DAY
                and now - last_read.get((rid, name), 0) > constants.STALE_DAYS * constants.DAY
            ):
                stale.append(path)
    return stale


def report(now=None):
    now = now or time.time()
    events = usage.read_usage()
    feats = plugin.features()
    found = metrics(events, now)
    canary = jsonfile.read_json(os.path.join(state.state_dir(), "canary.json"), {}) or {}
    lines = [f"automem-plus review · {len(events)} events logged"]
    for name, entry in feats.items():
        switch = "on" if entry.get("enabled") else "OFF"
        if name in found:
            value, sample, detail = found[name]
            lines += ["", f"{name} ({switch})", f"  {detail}", f"  → {verdict(entry, value, sample)}"]
        else:
            lines += ["", f"{name} ({switch})"]
        for scenario, passed in (canary.get("results") or {}).items():
            if passed and scenario == entry.get("canary"):
                lines.append(
                    f"  built-in covers this now (canary {scenario}, Claude Code {canary.get('version')}): "
                    f"consider retiring"
                )
    stale = stale_notes(events, now)
    if stale:
        lines += [
            "",
            f"Notes nobody opened in {constants.STALE_DAYS} days (some may be answered from their MEMORY.md line "
            f"without being opened, so check before deleting):",
        ]
        lines += [f"  {p}" for p in stale[:20]]
    if (canary.get("results") or {}).get("outside_notes") is False:
        lines += [
            "",
            "⚠️ The canary's check that Claude uses a note written from outside failed. Sync relies on "
            "that to deliver notes from other machines, so check that imported notes still get used.",
        ]
    if canary:
        results = ", ".join(
            f"{name} {'passes' if passed else 'fails'}" for name, passed in (canary.get("results") or {}).items()
        )
        lines += [
            "",
            f"Last canary: {time.strftime('%Y-%m-%d', time.localtime(canary.get('ts', 0)))}, "
            f"Claude Code {canary.get('version')}, ${canary.get('cost', 0):.3f}: {results}",
        ]
    lines += ["", "Change a feature: ::automem retire <feature> or ::automem enable <feature>"]
    jsonfile.write_json(os.path.join(state.state_dir(), "review.json"), {"reviewed": round(now)})
    return "\n".join(lines)
