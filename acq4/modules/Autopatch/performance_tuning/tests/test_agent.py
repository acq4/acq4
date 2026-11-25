"""Tests for launching an analysis agent or falling back to the editor."""

import time
from pathlib import Path

import pytest

from acq4.modules.Autopatch.performance_tuning import agent


def wait_for(path, timeout=10):
    deadline = time.monotonic() + timeout
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    return path.exists()


def test_agent_command_reads_misc():
    assert agent.agent_command({"misc": {"analysisAgent": "x {dir}"}}) == "x {dir}"
    assert agent.agent_command({}) is None
    assert agent.agent_command({"misc": {}}) is None


def test_launch_fills_quoted_dir(tmp_path):
    d = tmp_path / "with space"
    d.mkdir()
    config = {"misc": {"analysisAgent": "touch {dir}/launched"}}
    process = agent.launch(d, config, open_editor=lambda p: None)
    assert process == "agent"
    assert wait_for(d / "launched")


def test_question_never_reaches_shell(tmp_path):
    from acq4.modules.Autopatch.performance_tuning import brief
    from acq4.modules.Autopatch.performance_tuning.tests.test_record import (
        make_trial,
    )

    trial = make_trial(tmp_path)
    d = brief.next_analysis_dir(trial, "x")
    brief.write_brief(d, brief.build_brief(trial, "$(touch pwned)"))
    config = {
        "misc": {"analysisAgent": "cat {dir}/BRIEF.md > /dev/null && touch {dir}/done"}
    }
    agent.launch(d, config, open_editor=lambda p: None)
    assert wait_for(d / "done")
    assert list(tmp_path.rglob("pwned")) == []
    assert list(Path.cwd().glob("pwned")) == []


def test_stray_field_raises_before_launch(tmp_path):
    config = {"misc": {"analysisAgent": "touch {dir}/a && touch {other}"}}
    with pytest.raises(KeyError):
        agent.launch(tmp_path, config, open_editor=lambda p: None)
    assert not (tmp_path / "a").exists()


def test_no_command_opens_editor(tmp_path):
    calls = []
    assert agent.launch(tmp_path, {}, open_editor=calls.append) == "editor"
    assert calls == [str(tmp_path / "BRIEF.md")]
