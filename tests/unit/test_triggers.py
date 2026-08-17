"""Targeted tests for trigger evaluation branches."""

from __future__ import annotations

from phantom.automation.triggers import TriggerEngine
from phantom.models import Recipe, RecipeTrigger, TriggerEvent, TriggerType


class _Library:
    def __init__(self, recipes):
        self._recipes = recipes

    def list_recipes(self):
        return list(self._recipes)


def _recipe(trigger_type: str, config: dict, *, enabled: bool = True):
    return Recipe(
        name=f"r-{trigger_type}",
        trigger=RecipeTrigger(type=trigger_type, config=config),
        enabled=enabled,
    )


def test_trigger_app_switch_matches_target():
    recipes = [
        _recipe(TriggerType.APP_SWITCH.value, {"app": "Notes"}),
        _recipe(TriggerType.APP_SWITCH.value, {"app": "Slack"}),
    ]
    engine = TriggerEngine(_Library(recipes))
    event = TriggerEvent(type=TriggerType.APP_SWITCH, data={"app_name": "Slack"})
    matches = engine.check(event)
    assert [r.name for r in matches] == ["r-app_switch"]


def test_trigger_app_switch_no_target_matches_any():
    recipes = [_recipe(TriggerType.APP_SWITCH.value, {})]
    engine = TriggerEngine(_Library(recipes))
    event = TriggerEvent(type="app_switch", data={"app_name": "Anything"})
    matches = engine.check(event)
    assert len(matches) == 1


def test_trigger_content_match_with_app_filter(monkeypatch):
    recipes = [
        _recipe(TriggerType.CONTENT_MATCH.value, {"pattern": "error", "app": "Terminal"}),
        _recipe(TriggerType.CONTENT_MATCH.value, {"pattern": "warning", "app": "Browser"}),
    ]
    engine = TriggerEngine(_Library(recipes))
    event = TriggerEvent(
        type="content_match", data={"app_name": "Terminal", "text": "error: disk full"}
    )
    matches = engine.check(event)
    assert len(matches) == 1
    assert matches[0].trigger.config["pattern"] == "error"


def test_trigger_content_match_regex_respects_text():
    recipes = [_recipe(TriggerType.CONTENT_MATCH.value, {"pattern": r"(?i)timeout\s+\d+"})]
    engine = TriggerEngine(_Library(recipes))
    event = TriggerEvent(type="content_match", data={"text": "Timeout 503 from upstream"})
    matches = engine.check(event)
    assert len(matches) == 1


def test_trigger_schedule_requires_time(monkeypatch):
    recipes = [_recipe(TriggerType.SCHEDULE.value, {})]
    engine = TriggerEngine(_Library(recipes))
    matches = engine.check(TriggerEvent(type="schedule", data={}))
    assert matches == []


def test_trigger_schedule_day_filter(monkeypatch):
    recipes = [_recipe(TriggerType.SCHEDULE.value, {"time": "09:00", "days": ["mon", "tue"]})]
    engine = TriggerEngine(_Library(recipes))

    def fake_strftime(fmt):
        if fmt == "%H:%M":
            return "09:00"
        if fmt == "%a":
            return "Wed"
        return ""

    monkeypatch.setattr("phantom.automation.triggers.time.strftime", fake_strftime)
    matches = engine.check(TriggerEvent(type="schedule", data={}))
    assert matches == []


def test_trigger_schedule_match(monkeypatch):
    recipes = [_recipe(TriggerType.SCHEDULE.value, {"time": "09:00", "days": ["mon", "wed"]})]
    engine = TriggerEngine(_Library(recipes))

    def fake_strftime(fmt):
        if fmt == "%H:%M":
            return "09:00"
        if fmt == "%a":
            return "Wed"
        return ""

    monkeypatch.setattr("phantom.automation.triggers.time.strftime", fake_strftime)
    matches = engine.check(TriggerEvent(type="schedule", data={}))
    assert len(matches) == 1


def test_trigger_idle_threshold():
    recipes = [_recipe(TriggerType.IDLE.value, {"seconds": 120})]
    engine = TriggerEngine(_Library(recipes))
    event = TriggerEvent(type="idle", data={"idle_seconds": 130})
    assert engine.check(event)
    event = TriggerEvent(type="idle", data={"idle_seconds": 60})
    assert engine.check(event) == []


def test_trigger_hotkey_matches_modifiers():
    recipes = [_recipe(TriggerType.HOTKEY.value, {"key": "k", "modifiers": ["cmd", "shift"]})]
    engine = TriggerEngine(_Library(recipes))
    event = TriggerEvent(type="hotkey", data={"key": "k", "modifiers": ["shift", "cmd"]})
    assert engine.check(event)
    event = TriggerEvent(type="hotkey", data={"key": "k", "modifiers": ["cmd"]})
    assert engine.check(event) == []


def test_trigger_pattern_match():
    recipes = [_recipe(TriggerType.PATTERN_MATCH.value, {"pattern_id": "p1"})]
    engine = TriggerEngine(_Library(recipes))
    event = TriggerEvent(type="pattern_match", data={"pattern_id": "p1"})
    assert engine.check(event)
    event = TriggerEvent(type="pattern_match", data={"pattern_id": "p2"})
    assert engine.check(event) == []


def test_trigger_ignores_disabled_and_unmatched():
    recipes = [
        _recipe(TriggerType.APP_SWITCH.value, {"app": "Notes"}, enabled=False),
        _recipe(TriggerType.APP_SWITCH.value, {"app": "Slack"}, enabled=True),
    ]
    engine = TriggerEngine(_Library(recipes))
    matches = engine.check(TriggerEvent(type="app_switch", data={"app_name": "Slack"}))
    assert [r.name for r in matches] == ["r-app_switch"]


def test_trigger_unknown_type_returns_false():
    recipes = [_recipe("custom", {})]
    engine = TriggerEngine(_Library(recipes))
    matches = engine.check(TriggerEvent(type="custom", data={}))
    assert matches == []
