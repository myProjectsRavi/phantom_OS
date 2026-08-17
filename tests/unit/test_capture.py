"""Targeted tests for ScreenCapture behavior."""

from __future__ import annotations

import types

import pytest

import phantom.perception.capture as capture_module
from phantom.models import CaptureMode
from phantom.perception.capture import ScreenCapture


class _FakeArray:
    def __init__(self, data, shape):
        self._data = data
        self.shape = shape

    def astype(self, _dtype):
        return self

    def copy(self):
        return _FakeArray(list(self._data), self.shape)

    def __sub__(self, other):
        return _FakeArray([a - b for a, b in zip(self._data, other._data)], self.shape)


class _FakeNumpy:
    uint8 = "uint8"

    @staticmethod
    def array(frame):
        return frame

    @staticmethod
    def abs(arr):
        return _FakeArray([abs(v) for v in arr._data], arr.shape)

    @staticmethod
    def mean(arr):
        return sum(arr._data) / max(len(arr._data), 1)


def _frame(shape, value):
    size = shape[0] * shape[1] * shape[2]
    return _FakeArray([value] * size, shape)


def _install_fake_mss(monkeypatch, frame):
    class _MSS:
        def __init__(self):
            self.monitors = [
                None,
                {"left": 0, "top": 0, "width": frame.shape[1], "height": frame.shape[0]},
            ]

        def grab(self, _monitor):
            return frame

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setitem(__import__("sys").modules, "mss", types.SimpleNamespace(mss=_MSS))


def test_capture_requires_numpy(monkeypatch):
    monkeypatch.setattr(capture_module, "np", None)
    cap = ScreenCapture()
    with pytest.raises(RuntimeError, match="numpy is required"):
        cap.capture()


def test_capture_returns_none_when_no_change(monkeypatch):
    monkeypatch.setattr(capture_module, "np", _FakeNumpy())
    frame = _frame((8, 8, 3), 0)
    _install_fake_mss(monkeypatch, frame)
    cap = ScreenCapture()
    assert cap.capture() is not None
    assert cap.capture() is None


def test_capture_returns_result_on_change(monkeypatch):
    monkeypatch.setattr(capture_module, "np", _FakeNumpy())
    frame = _frame((6, 10, 3), 255)
    _install_fake_mss(monkeypatch, frame)
    cap = ScreenCapture()
    cap._last_frame = _frame((6, 10, 3), 0)
    result = cap.capture()
    assert result is not None
    assert result.monitor_info["width"] == 10 and result.monitor_info["height"] == 6


def test_frame_interval_respects_mode_and_override():
    cap = ScreenCapture(active_interval=2.5)
    assert cap.frame_interval == 2.5
    cap.set_mode(CaptureMode.FOCUSED)
    assert cap.frame_interval == ScreenCapture.INTERVALS[CaptureMode.FOCUSED]
