"""I/O and filtering coverage tests for RecipeLibrary."""

from __future__ import annotations

from phantom.automation.recipes import RecipeLibrary
from phantom.models import Recipe, RecipeStep, RecipeTrigger


def test_load_from_disk_and_source_filtering(tmp_path):
    recipe_dir = tmp_path / "recipes"
    recipe_dir.mkdir(parents=True)
    (recipe_dir / "custom.toml").write_text(
        """
[recipe]
name = "custom_recipe"
description = "From disk"

[trigger]
type = "hotkey"
key = "r"

[[steps]]
type = "app_activate"
app = "Safari"
delay_after = 0.5
""".strip()
    )

    library = RecipeLibrary(recipe_dir=str(recipe_dir))
    library.load_from_disk()

    loaded = library.get("custom_recipe")
    assert loaded is not None
    assert loaded.source == "user"
    assert loaded.trigger.type == "hotkey"
    assert loaded.steps[0].type == "app_activate"
    assert library.list_recipes(source="user")
    assert library.list_recipes(source="builtin")


def test_save_add_and_get_round_trip(tmp_path):
    recipe_dir = tmp_path / "recipes"
    library = RecipeLibrary(recipe_dir=str(recipe_dir))
    recipe = Recipe(
        name="saved_recipe",
        description="Persist me",
        trigger=RecipeTrigger(type="schedule", config={"time": "09:00"}),
        steps=[RecipeStep(type="wait", params={"seconds": 1}, delay_after=0.2)],
        source="user",
    )
    library.add(recipe)
    library.save(recipe)

    content = (recipe_dir / "saved_recipe.toml").read_text()
    assert 'name = "saved_recipe"' in content
    assert 'type = "wait"' in content
    assert "delay_after = 0.2" in content
