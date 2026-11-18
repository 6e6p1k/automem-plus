import os

import pytest
from automem import canary, claudecode


def test_canary_refuses_shared_folders_and_only_deletes_its_own(repo, env, monkeypatch):
    assert canary.unsafe_reason() is None
    monkeypatch.setenv("CLAUDE_CODE_PROJECT_DIR_NAME", "shared")
    assert "CLAUDE_CODE_PROJECT_DIR_NAME" in canary.unsafe_reason()
    with pytest.raises(SystemExit):
        canary.run()
    monkeypatch.delenv("CLAUDE_CODE_PROJECT_DIR_NAME")
    real = os.path.dirname(claudecode.memory_dir(repo))
    os.makedirs(real)
    canary.remove_throwaway_project(repo)  # not a canary repo: must survive
    assert os.path.isdir(real)


@pytest.mark.parametrize(
    "stdout,expected",
    [
        ('{"type": "result", "result": "orchid", "session_id": "s1", "total_cost_usd": 0.01}', ("orchid", "s1", 0.01)),
        (
            '[{"type": "system"}, {"type": "assistant"}, {"type": "result", "result": "ok", "session_id": "s2", '
            '"total_cost_usd": 0.02}]',
            ("ok", "s2", 0.02),
        ),
        ('[{"type": "system"}]', ("", None, 0.0)),
        ("Error: not logged in", ("", None, 0.0)),
        ("", ("", None, 0.0)),
    ],
)
def test_canary_reads_both_output_shapes_and_survives_junk(stdout, expected):
    assert canary.parse_result(stdout) == expected
