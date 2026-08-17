"""Screen capture with adaptive frame rate."""

from __future__ import annotations

import time
from typing import Optional

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]

from phantom.models import CaptureMode, CaptureResult


class ScreenCapture:
    INTERVALS = {
        CaptureMode.IDLE: 5.0,
        CaptureMode.ACTIVE: 1.0,
        CaptureMode.FOCUSED: 0.5,
        CaptureMode.RECORDING: 0.2,
    }

    def __init__(self, active_interval: float | None = None):
        self._mode = CaptureMode.ACTIVE
        self._last_frame: Optional[np.ndarray] = None
        self._change_threshold = 0.05
        if active_interval and active_interval > 0:
            self.INTERVALS[CaptureMode.ACTIVE] = active_interval

    def capture(self) -> Optional[CaptureResult]:
        if np is None:  # pragma: no cover
            raise RuntimeError("numpy is required for screen capture")
        import mss

        with mss.mss() as sct:
            raw = np.array(sct.grab(sct.monitors[1]))

        if self._last_frame is not None:
            diff = np.mean(np.abs(raw.astype(int) - self._last_frame.astype(int)))
            if diff < self._change_threshold * 255:
                return None

        self._last_frame = raw.copy()
        return CaptureResult(
            image=raw,
            timestamp=time.time(),
            monitor_info={"width": raw.shape[1], "height": raw.shape[0]},
        )

    def set_mode(self, mode: CaptureMode):
        self._mode = mode

    @property
    def frame_interval(self) -> float:
        return self.INTERVALS[self._mode]
