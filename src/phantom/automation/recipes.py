"""Recipe library management."""

from __future__ import annotations

import logging
from pathlib import Path
from types import ModuleType

import tomli_w

from phantom.models import Recipe, RecipeStep, RecipeTrigger

logger = logging.getLogger("phantom.recipes")

tomllib: ModuleType | None = None
try:
    import tomllib as _tomllib

    tomllib = _tomllib
except ImportError:  # pragma: no cover
    import tomli as _tomllib

    tomllib = _tomllib

BUILTINS = {
    "morning_opener": Recipe(
        name="morning_opener",
        description="Open morning apps at 9 AM",
        trigger=RecipeTrigger(
            type="schedule",
            config={"time": "09:00", "days": ["mon", "tue", "wed", "thu", "fri"]},
        ),
        steps=[
            RecipeStep(type="app_activate", params={"app": "Safari"}, delay_after=1),
            RecipeStep(type="url_open", params={"url": "https://gmail.com"}, delay_after=0.5),
            RecipeStep(type="app_activate", params={"app": "Slack"}),
            RecipeStep(type="app_activate", params={"app": "Code"}),
        ],
        source="builtin",
    ),
    "error_auto_search": Recipe(
        name="error_auto_search",
        description="Auto-search terminal errors",
        trigger=RecipeTrigger(
            type="content_match",
            config={"pattern": r"(Error|Exception|Traceback)", "app": "Terminal"},
        ),
        steps=[
            RecipeStep(type="clipboard_copy"),
            RecipeStep(type="app_activate", params={"app": "Safari"}, delay_after=0.5),
            RecipeStep(type="url_open", params={"url": "https://google.com/search?q={clipboard}"}),
        ],
        source="builtin",
    ),
    "focus_mode": Recipe(
        name="focus_mode",
        description="Close distractions for deep work (manual in v0.1)",
        trigger=None,
        steps=[
            RecipeStep(type="run_command", params={"command": ["killall", "Slack"]}),
            RecipeStep(type="run_command", params={"command": ["killall", "Discord"]}),
            RecipeStep(
                type="notification",
                params={"title": "🎯 Focus Mode", "message": "Distractions closed."},
            ),
        ],
        source="builtin",
    ),
}


class RecipeLibrary:
    def __init__(self, recipe_dir: str | None = None):
        self._dir = Path(recipe_dir or Path.home() / ".phantom" / "recipes")
        self._recipes: dict[str, Recipe] = dict(BUILTINS)

    def load_from_disk(self):
        if not self._dir.exists():
            return
        for file_path in self._dir.glob("*.toml"):
            try:
                data = tomllib.loads(file_path.read_text())
                recipe_data = data.get("recipe", {})
                trigger_data = data.get("trigger")
                steps_data = data.get("steps", [])
                if isinstance(steps_data, dict):
                    steps_data = [steps_data]
                self._recipes[recipe_data.get("name", file_path.stem)] = Recipe(
                    name=recipe_data.get("name", file_path.stem),
                    description=recipe_data.get("description", ""),
                    trigger=RecipeTrigger(
                        type=trigger_data["type"],
                        config={key: value for key, value in trigger_data.items() if key != "type"},
                    )
                    if trigger_data
                    else None,
                    steps=[self._deserialize_step(step) for step in steps_data],
                    variables=dict(recipe_data.get("variables", {})),
                    enabled=bool(recipe_data.get("enabled", True)),
                    source="user",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load %s: %s", file_path, exc)

    @staticmethod
    def _deserialize_step(data: dict) -> RecipeStep:
        reserved = {"type", "delay_after", "condition", "on_error", "max_retries"}
        return RecipeStep(
            type=data["type"],
            params={key: value for key, value in data.items() if key not in reserved},
            delay_after=float(data.get("delay_after", 0)),
            condition=data.get("condition"),
            on_error=str(data.get("on_error", "continue")),
            max_retries=int(data.get("max_retries", 1)),
        )

    def get(self, name):
        return self._recipes.get(name)

    def list_recipes(self, source=None):
        recipes = list(self._recipes.values())
        return [recipe for recipe in recipes if recipe.source == source] if source else recipes

    def add(self, recipe):
        self._recipes[recipe.name] = recipe

    def save(self, recipe: Recipe):
        """Persist a recipe with a real TOML serializer to preserve arbitrary text safely."""
        self._dir.mkdir(parents=True, exist_ok=True)
        payload: dict = {
            "recipe": {
                "name": recipe.name,
                "description": recipe.description,
                "enabled": recipe.enabled,
                "variables": recipe.variables,
            },
            "steps": [],
        }
        if recipe.trigger:
            payload["trigger"] = {"type": recipe.trigger.type, **recipe.trigger.config}
        for step in recipe.steps:
            row = {"type": step.type, **step.params}
            if step.delay_after:
                row["delay_after"] = step.delay_after
            if step.condition:
                row["condition"] = step.condition
            if step.on_error != "continue":
                row["on_error"] = step.on_error
            if step.max_retries != 1:
                row["max_retries"] = step.max_retries
            payload["steps"].append(row)
        (self._dir / f"{recipe.name}.toml").write_bytes(tomli_w.dumps(payload).encode("utf-8"))
