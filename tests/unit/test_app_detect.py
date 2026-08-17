"""Test active app detection abstraction."""

from phantom.models import AppInfo
from phantom.perception.app_detect import AppDetector


def test_app_detector_uses_applescript_helper(monkeypatch):
    monkeypatch.setattr("phantom.perception.app_detect.read_active_app_info", lambda: ("Safari", "com.apple.Safari", "Inbox"))
    detector = AppDetector(); app = detector.detect()
    assert isinstance(app, AppInfo)
    assert app.name == "Safari"
    assert app.bundle_id == "com.apple.Safari"
    assert app.window_title == "Inbox"


def test_app_detector_falls_back_on_error(monkeypatch):
    def _boom(): raise RuntimeError("failure")
    monkeypatch.setattr("phantom.perception.app_detect.read_active_app_info", _boom)
    assert AppDetector().detect().name == "Unknown"
