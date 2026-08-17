"""Tests for pattern persistence in PhantomAgent."""

from __future__ import annotations

import json

from phantom.agent import PhantomAgent
from phantom.config import PhantomConfig
from phantom.models import LearnedPattern


def _config(tmp_path) -> PhantomConfig:
    return PhantomConfig(
        local_llm_helpers_enabled=False,
        neurovault_enabled=False,
        recipe_dir=str(tmp_path / "recipes"),
        pattern_store=str(tmp_path / "patterns.json"),
    )


def test_pattern_store_roundtrip(tmp_path):
    config = _config(tmp_path)
    agent = PhantomAgent(config)
    pattern = LearnedPattern(
        id="p1",
        name="daily_flow",
        signature="copy@Chrome|paste@Slack",
        steps=[{"type": "clipboard_copy", "app": "Chrome"}],
        frequency=3,
        confidence=0.75,
        approved=True,
        tags=["work"],
    )
    agent._patterns[pattern.signature] = pattern
    agent._save_patterns()

    agent2 = PhantomAgent(config)
    loaded = agent2.learned_patterns()
    assert len(loaded) == 1
    assert loaded[0].signature == pattern.signature
    assert loaded[0].approved is True
    assert loaded[0].tags == ["work"]


def test_pattern_store_handles_invalid_json(tmp_path):
    config = _config(tmp_path)
    store_path = tmp_path / "patterns.json"
    store_path.write_text("{", encoding="utf-8")

    agent = PhantomAgent(config)
    assert agent.learned_patterns() == []


def test_pattern_store_loads_legacy_list_format(tmp_path):
    config = _config(tmp_path)
    store_path = tmp_path / "patterns.json"
    store_path.write_text(
        json.dumps(
            [
                {
                    "id": "p2",
                    "name": "quick",
                    "signature": "app_switch@Code|app_switch@Terminal",
                    "steps": [],
                    "frequency": 4,
                }
            ]
        ),
        encoding="utf-8",
    )

    agent = PhantomAgent(config)
    patterns = agent.learned_patterns()
    assert len(patterns) == 1
    assert patterns[0].signature == "app_switch@Code|app_switch@Terminal"
