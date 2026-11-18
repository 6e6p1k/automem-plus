import os

from automem import constants, status, store, sync
from helpers import FAKE_API_KEY_LINE, read, write


def rule(machine, name):
    return os.path.join(str(machine.config), "rules", name)


def write_rule(machine, name, text):
    os.makedirs(os.path.dirname(rule(machine, name)), exist_ok=True)
    write(rule(machine, name), text)


def in_store(machine, name):
    return os.path.join(str(machine.store), "automem", constants.RULES_STORE_FOLDER, name)


def two_machines_sharing_a_rule(machines, name="automem-budget.md", text="One subagent at most\n"):
    a, b = machines("a"), machines("b")
    write_rule(a.use(), name, text)
    a.sync()
    b.sync()
    assert read(rule(b, name)) == text
    return a, b


def test_only_promoted_rules_travel_and_the_users_own_stay_put(machines):
    a, b = machines("a"), machines("b")
    write_rule(a.use(), "automem-budget.md", "One subagent at most\n")
    write_rule(a, "mine.md", "A's own rule\n")
    write_rule(a, os.path.join("team", "automem-nested.md"), "only the top of the folder counts\n")
    os.makedirs(os.path.dirname(in_store(a, "x")))
    write(in_store(a, "stray.md"), "put in the store by hand\n")
    a.sync()
    assert not os.path.exists(in_store(a, "mine.md")) and not os.path.exists(in_store(a, "automem-nested.md"))
    write_rule(b.use(), "theirs.md", "B's own rule\n")
    b.sync()
    assert read(rule(b, "automem-budget.md")) == "One subagent at most\n"
    assert read(rule(b, "theirs.md")) == "B's own rule\n"
    for name in ("mine.md", "stray.md", os.path.join("team", "automem-nested.md")):
        assert not os.path.exists(rule(b, name))
    assert not os.path.exists(in_store(b, "theirs.md"))


def test_deleting_a_promoted_rule_deletes_it_on_every_machine_with_a_backup(machines):
    a, b = two_machines_sharing_a_rule(machines)
    os.remove(rule(a.use(), "automem-budget.md"))  # the only one: unlike notes, an emptied rules folder still counts
    a.sync()
    report = b.sync()
    assert not os.path.exists(rule(b, "automem-budget.md"))
    assert report.rules.deleted_here == ["automem-budget.md"]
    assert any(read(p) == "One subagent at most\n" for p in report.rules.backups)
    assert not a.sync().rules.imported  # nothing comes back to the machine that deleted it


def test_a_rule_both_machines_changed_keeps_one_copy_and_saves_the_other(machines):
    a, b = two_machines_sharing_a_rule(machines)
    write_rule(a.use(), "automem-budget.md", "A: two subagents\n")
    a.sync()
    write_rule(b.use(), "automem-budget.md", "B: none at all\n")
    report = b.sync()
    assert read(rule(b, "automem-budget.md")) == "B: none at all\n"
    assert report.rules.conflicts == ["automem-budget.md"] and not report.conflicts
    assert [read(p) for p in report.rules.backups] == ["A: two subagents\n"]
    assert sync.lost_copies(b.repo) == []  # a rule isn't this project's note to reconcile
    assert "both machines changed automem-budget.md, one copy was kept" in status.describe(b.repo)
    a.sync()
    assert read(rule(a.use(), "automem-budget.md")) == "B: none at all\n"


def test_a_rule_changed_on_both_sides_of_a_push_race_is_settled_like_a_note(machines):
    a, b = two_machines_sharing_a_rule(machines)
    write_rule(b.use(), "automem-budget.md", "B: none at all\n")
    sync.run(b.repo, push_now=False, lock_wait=1)  # committed on B, not pushed
    write_rule(a.use(), "automem-budget.md", "A: two subagents\n")
    a.sync()
    report = b.sync()
    assert report.push == "pushed after merge"
    assert report.rules.conflicts == ["automem-budget.md"]
    assert [read(c.backup) for c in report.rules.lost] == ["A: two subagents\n"]
    a.sync()
    assert read(rule(a.use(), "automem-budget.md")) == "B: none at all\n"


def test_a_rule_that_looks_like_a_secret_never_enters_the_store(machines):
    a, b = machines("a"), machines("b")
    write_rule(a.use(), "automem-deploy.md", FAKE_API_KEY_LINE + "\n")
    report = a.sync()
    assert report.rules.skipped == ["automem-deploy.md"] and not os.path.exists(in_store(a, "automem-deploy.md"))
    assert "⚠️ Promoted rules: 1 in" in status.describe(a.repo)
    b.sync()
    assert not os.path.exists(rule(b.use(), "automem-deploy.md"))
    assert os.path.exists(rule(a.use(), "automem-deploy.md"))  # still there locally


def test_status_says_whether_promoted_rules_travel(machines):
    a = machines("a")
    assert "⚪ Promoted rules: none yet" in status.describe(a.use().repo)
    write_rule(a, "automem-budget.md", "One subagent at most\n")
    a.sync()
    assert "✅ Promoted rules: 1 in" in status.describe(a.repo)
    os.rename(str(a.store), str(a.store) + "-gone")
    assert not store.store_ready()
    assert "⚪ Promoted rules: 1 in" in status.describe(a.repo) and "this machine only" in status.describe(a.repo)
