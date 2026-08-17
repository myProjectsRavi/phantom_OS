"""Release-gate coverage for smaller runtime subsystems."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

import phantom.automation.recipes as recipes_module
import phantom.integrations.neurovault_bridge as neuro_module
import phantom.perception.engine as perception_module
from phantom.automation.recipes import RecipeLibrary
from phantom.config import PhantomConfig
from phantom.events import EventBus
from phantom.integrations.neurovault_bridge import NeurovaultBridge
from phantom.models import (
    AppInfo,
    CaptureMode,
    CaptureResult,
    PerceptionFrame,
    Recipe,
    RecipeStep,
    RecipeTrigger,
)
from phantom.perception.engine import PerceptionEngine


def test_event_bus_handler_error_and_off(monkeypatch):
    bus = EventBus()
    calls = []
    warnings = []

    def good(data):
        calls.append(data)

    def bad(_data):
        raise RuntimeError("handler failed")

    monkeypatch.setattr(bus._logger, "warning", lambda *args, **_kwargs: warnings.append(args))
    bus.on("event", good)
    bus.on("event", bad)
    bus.emit("event", {"x": 1})
    assert calls == [{"x": 1}]
    assert warnings

    bus.off("event", bad)
    bus.emit("event")
    assert calls[-1] == {}
    bus.off("event")
    assert bus._handlers["event"] == []


def test_perception_returns_previous_frame_when_capture_missing(monkeypatch):
    config = PhantomConfig(capture_fps=2.0)
    engine = PerceptionEngine(config)
    engine._initialized = True
    engine._capture = SimpleNamespace(capture=lambda: None, frame_interval=0.5)
    engine._last_frame = PerceptionFrame(app_name="Code")
    engine._idle_start = 10.0
    monkeypatch.setattr(perception_module.time, "time", lambda: 15.5)

    frame = engine.perceive()
    assert frame is engine._last_frame
    assert frame.idle_seconds == 5.5
    assert engine.frame_interval == 0.5


def test_perception_full_optional_pipeline_and_typing(monkeypatch):
    config = PhantomConfig(capture_fps=4.0, ocr_enabled=True, element_detection=True)
    engine = PerceptionEngine(config)
    engine._initialized = True
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    capture = CaptureResult(image=image, timestamp=7.0)
    engine._capture = SimpleNamespace(
        capture=lambda: capture,
        frame_interval=0.25,
        set_mode=lambda mode: setattr(engine, "_mode_seen", mode),
    )
    engine._app = SimpleNamespace(
        detect=lambda: AppInfo(name="Code", bundle_id="code", window_title="main.py")
    )
    engine._ocr = SimpleNamespace(
        extract=lambda _image: {"body": "hello world and more"},
        extract_with_positions=lambda _image: [{"text": "hello"}],
    )
    engine._elements = SimpleNamespace(detect=lambda _image, _positions: [SimpleNamespace(id="e")])
    engine._state = SimpleNamespace(classify=lambda _app, _text: "editor")
    engine._last_frame = PerceptionFrame(app_name="Terminal", text_content={"body": "hi"})
    monkeypatch.setattr(perception_module.time, "time", lambda: 20.0)

    frame = engine.perceive()
    assert frame.app_name == "Code"
    assert frame.app_bundle_id == "code"
    assert frame.screen_type == "editor"
    assert frame.is_typing is True
    assert frame.is_navigating is True
    assert len(frame.elements) == 1

    engine.set_mode(CaptureMode.IDLE)
    assert engine._mode_seen == CaptureMode.IDLE
    assert (
        engine._detect_typing(
            PerceptionFrame(text_content={"x": "short"}),
            PerceptionFrame(text_content={"x": "much longer previous text"}),
        )
        is False
    )


def test_perception_initial_frame_interval_before_initialization():
    engine = PerceptionEngine(
        SimpleNamespace(capture_fps=5.0, ocr_enabled=False, element_detection=False)
    )
    assert engine.frame_interval == 0.2


def test_recipe_library_loads_single_step_dict_and_logs_bad_file(tmp_path, monkeypatch):
    recipe_dir = tmp_path / "recipes"
    recipe_dir.mkdir()
    (recipe_dir / "single.toml").write_text(
        """
[recipe]
name = "single"
description = "one"
enabled = false

[recipe.variables]
name = "value"

[trigger]
type = "hotkey"
key = "k"

[steps]
type = "wait"
seconds = 2
delay_after = 0.5
condition = "name == 'value'"
on_error = "abort"
max_retries = 3
""".strip()
    )
    (recipe_dir / "bad.toml").write_text("[")
    warnings = []
    monkeypatch.setattr(
        recipes_module.logger, "warning", lambda *args, **_kwargs: warnings.append(args)
    )

    library = RecipeLibrary(str(recipe_dir))
    library.load_from_disk()
    recipe = library.get("single")

    assert recipe is not None
    assert recipe.enabled is False
    assert recipe.variables == {"name": "value"}
    assert recipe.trigger.config == {"key": "k"}
    assert recipe.steps[0].params == {"seconds": 2}
    assert recipe.steps[0].delay_after == 0.5
    assert recipe.steps[0].condition == "name == 'value'"
    assert recipe.steps[0].on_error == "abort"
    assert recipe.steps[0].max_retries == 3
    assert warnings


def test_recipe_save_serializes_all_optional_step_fields(tmp_path):
    library = RecipeLibrary(str(tmp_path / "recipes"))
    recipe = Recipe(
        name="all-fields",
        description="demo",
        enabled=False,
        variables={"x": "y"},
        trigger=RecipeTrigger(type="schedule", config={"time": "10:00"}),
        steps=[
            RecipeStep(
                type="wait",
                params={"seconds": 1},
                delay_after=0.2,
                condition="x == 'y'",
                on_error="abort",
                max_retries=4,
            )
        ],
        source="user",
    )
    library.add(recipe)
    assert library.get("all-fields") is recipe
    assert recipe in library.list_recipes(source="user")
    library.save(recipe)
    text = (tmp_path / "recipes" / "all-fields.toml").read_text()
    assert 'type = "schedule"' in text
    assert "delay_after = 0.2" in text
    assert 'on_error = "abort"' in text
    assert "max_retries = 4" in text


def test_neurovault_init_success_via_init_and_final_failure(monkeypatch):
    vault = SimpleNamespace()

    class _Engine:
        @classmethod
        def open(cls, *_args, **_kwargs):
            raise RuntimeError("open failed")

        @classmethod
        def init(cls, *_args, **kwargs):
            if kwargs.get("base_dir"):
                return vault
            raise RuntimeError("init failed")

    monkeypatch.setattr(neuro_module, "HAS_NEUROVAULT", True)
    monkeypatch.setattr(neuro_module, "NeurovaultEngine", _Engine, raising=False)
    bridge = NeurovaultBridge("demo", base_dir="/tmp/vault")
    assert bridge.available is True
    assert bridge._vault is vault

    class _Broken:
        @classmethod
        def open(cls, *_args, **_kwargs):
            raise RuntimeError("no")

        @classmethod
        def init(cls, *_args, **_kwargs):
            raise RuntimeError("no")

    warnings = []
    monkeypatch.setattr(neuro_module, "NeurovaultEngine", _Broken, raising=False)
    monkeypatch.setattr(
        neuro_module.logger, "warning", lambda *args, **_kwargs: warnings.append(args)
    )
    broken = NeurovaultBridge("broken")
    assert broken.available is False
    assert warnings


def test_neurovault_enrich_ignores_empty_memories(monkeypatch):
    class _Vault:
        def recall(self, **_kwargs):
            return [
                SimpleNamespace(memory=SimpleNamespace(content="")),
                SimpleNamespace(content="known"),
            ]

    bridge = object.__new__(NeurovaultBridge)
    bridge._vault_name = "demo"
    bridge._base_dir = None
    bridge._vault = _Vault()
    result = bridge.enrich_intent("Code", "x" * 200)
    assert result == {"related_patterns": ["known"], "context": "Known activity in Code"}
