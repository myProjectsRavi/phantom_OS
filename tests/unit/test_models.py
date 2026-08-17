"""Test data models."""

from phantom.models import (
    ActionRequest,
    PerceptionFrame,
    PhantomActionType,
    Recipe,
    RecipeStep,
    TrustLevel,
)


def test_perception_frame_defaults():
    f = PerceptionFrame()
    assert f.app_name == ""
    assert f.screen_type == "unknown"
    assert f.idle_seconds == 0.0
    assert not f.is_typing


def test_action_request():
    r = ActionRequest(type=PhantomActionType.TYPE_TEXT, params={"text": "hello"})
    assert r.type == PhantomActionType.TYPE_TEXT
    assert r.params["text"] == "hello"
    assert not r.requires_approval


def test_recipe():
    r = Recipe(name="test", steps=[RecipeStep(type="notification")])
    assert r.name == "test"
    assert len(r.steps) == 1
    assert r.enabled


def test_trust_levels():
    assert TrustLevel.SUGGEST_ONLY.value == "suggest_only"
    assert TrustLevel.AUTO_EXECUTE.value == "auto_execute"
