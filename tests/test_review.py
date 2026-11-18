import os
import time

from automem import jsonfile, plugin, review, state, status, usage


def test_review_verdicts(env):
    now = time.time()
    for i in range(20):
        usage.log_usage("session", "start", repo="r", session=f"s{i}", has_handoff=True)
        usage.log_usage("session", "engaged", repo="r", session=f"s{i}")
    usage.log_usage("session", "start", repo="r", session="short", has_handoff=True)  # 1-prompt session: not counted
    for i in range(3):
        usage.log_usage("note", "read", repo="r", session=f"s{i}", file="handoff.md", prompt=1)
    usage.log_usage("note", "read", repo="r", session="s5", file="handoff.md", prompt=7)  # too late to count
    found = review.metrics(usage.read_usage(), now)
    value, sample, detail = found["handoff_rule"]
    assert (round(value, 2), sample) == (0.15, 20)
    assert review.verdict(plugin.features()["handoff_rule"], value, sample).startswith("retire?")
    assert review.verdict(plugin.features()["handoff_rule"], 0.5, 3) == "collecting data (3/20)"
    assert "\nhandoff_rule (on)\n  3 of 20 working sessions" in review.report(now)


def test_review_points_at_a_feature_the_canary_says_built_in_covers(env):
    record = {"ts": 1, "version": "9.9.9", "cost": 0.07, "results": {"passing_facts": True, "outside_notes": False}}
    jsonfile.write_json(os.path.join(state.state_dir(), "canary.json"), record)
    text = review.report()
    covered = [line for line in text.splitlines() if "built-in covers this now" in line]
    assert len(covered) == 1 and "passing_facts" in covered[0]  # only the feature that scenario judges
    assert text.index("passing_facts_rule") < text.index(covered[0]) < text.index("staleness_nudge")
    assert "note written from outside failed" in text and "passing_facts passes, outside_notes fails" in text


def test_sync_verdict_needs_30_days_then_judges_arrivals(env):
    now = time.time()
    entry = plugin.features()["sync"]
    value, sample, _ = review.metrics(usage.read_usage(), now)["sync"]
    assert review.verdict(entry, value, sample).startswith("collecting data")  # sync never ran
    jsonfile.write_json(os.path.join(state.state_dir(), "sync_first.json"), {"ts": now - 31 * 86400})
    value, sample, _ = review.metrics(usage.read_usage(), now)["sync"]
    assert review.verdict(entry, value, sample).startswith("retire?")  # a month, nothing arrived: one machine
    usage.log_usage("sync", "imported", repo="r", file="ci.md")
    value, sample, _ = review.metrics(usage.read_usage(), time.time())["sync"]
    assert review.verdict(entry, value, sample) == "keep"


def test_review_status_and_dedupe(env):
    for _ in range(2):  # the same tool call logged twice (a forked transcript)
        usage.log_usage("note", "read", repo="r", session="s1", file="handoff.md", prompt=1, id="toolu_x")
    assert len(review.dedupe([u for u in usage.read_usage() if u["feature"] == "note"])) == 1
    with open(os.path.join(state.state_dir(), "usage.jsonl"), "a") as f:
        f.write('{"broken\n')
    assert len(usage.read_usage()) == 2  # a corrupt line is skipped, not fatal
    assert "Sync hasn't run" in status.describe()
