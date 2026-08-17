"""Test recipe system."""

from phantom.automation.recipes import RecipeLibrary
from phantom.automation.triggers import TriggerEngine
from phantom.models import Recipe, RecipeTrigger, TriggerEvent


def test_builtins_loaded():
    lib = RecipeLibrary()
    recipes = lib.list_recipes()
    assert len(recipes) >= 3
    names = {r.name for r in recipes}
    assert "morning_opener" in names
    assert "focus_mode" in names


def test_trigger_schedule(monkeypatch):
    lib = RecipeLibrary()
    engine = TriggerEngine(lib)

    def fake_strftime(fmt):
        if fmt == "%H:%M":
            return "09:00"
        if fmt == "%a":
            return "Mon"
        return ""

    monkeypatch.setattr("phantom.automation.triggers.time.strftime", fake_strftime)
    event = TriggerEvent(type="schedule", data={})
    matching = engine.check(event)
    assert any(recipe.name == "morning_opener" for recipe in matching)


def test_trigger_app_switch():
    lib = RecipeLibrary()
    lib.add(
        Recipe(
            name="switch_to_fakeapp",
            trigger=RecipeTrigger(type="app_switch", config={"app": "FakeApp"}),
            source="user",
        )
    )
    engine = TriggerEngine(lib)
    event = TriggerEvent(type="app_switch", data={"app_name": "FakeApp"})
    matching = engine.check(event)
    assert len(matching) == 1
    assert matching[0].name == "switch_to_fakeapp"
