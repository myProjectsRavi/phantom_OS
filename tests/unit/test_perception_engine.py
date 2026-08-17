"""Test perception engine configuration wiring."""

import numpy as np

from phantom.config import PhantomConfig
from phantom.models import AppInfo, CaptureResult
from phantom.perception.engine import PerceptionEngine


def test_perception_engine_respects_config_flags(monkeypatch):
    config = PhantomConfig(capture_fps=2.0, ocr_enabled=False, element_detection=False)
    engine = PerceptionEngine(config)
    engine._ensure_initialized()

    capture = CaptureResult(image=np.zeros((20, 20, 3), dtype=np.uint8), timestamp=1.0)
    monkeypatch.setattr(engine._capture, "capture", lambda: capture)
    monkeypatch.setattr(engine._app, "detect", lambda: AppInfo(name="Code"))
    monkeypatch.setattr(engine._state, "classify", lambda _app, _text: "editor")

    frame = engine.perceive()

    assert frame is not None
    assert frame.app_name == "Code"
    assert frame.screen_type == "editor"
    assert frame.text_content == {}
    assert frame.elements == []
    assert abs(engine.frame_interval - 0.5) < 1e-6
