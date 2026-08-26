from __future__ import annotations

from simulator.cli import _select_channel, main


def test_both_alternates_human_and_agent():
    assert _select_channel("both", 0) == "human"
    assert _select_channel("both", 1) == "agent"
    assert _select_channel("human", 9) == "human"


def test_agent_channel_requires_keys_dir():
    assert main(["--channel", "agent", "--count", "1"]) == 2
