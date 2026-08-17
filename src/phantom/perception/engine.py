"""Perception Engine orchestrator."""

from __future__ import annotations

import time
from typing import Optional

from phantom.models import CaptureMode, PerceptionFrame


class PerceptionEngine:
    """Compose capture, OCR, element detection, and app-state classification.

    Heavy dependencies (mss, numpy, Pillow, pytesseract) are imported lazily
    on the first call to ``perceive()`` so that CLI commands like ``phantom --help``
    and ``phantom doctor`` stay fast and lightweight.
    """

    def __init__(self, config=None):
        """Initialize perception configuration — heavy deps loaded on first use."""
        self._config = config
        self._capture_fps = float(getattr(config, "capture_fps", 1.0) or 1.0)
        self._ocr_enabled = bool(getattr(config, "ocr_enabled", True))
        self._element_detection = bool(getattr(config, "element_detection", True))
        self._last_frame: Optional[PerceptionFrame] = None
        self._idle_start = time.time()
        self._capture = None
        self._app = None
        self._ocr = None
        self._elements = None
        self._state = None
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return
        from phantom.perception.app_detect import AppDetector
        from phantom.perception.capture import ScreenCapture
        from phantom.perception.elements import UIElementDetector
        from phantom.perception.ocr import OCRPipeline
        from phantom.perception.state import AppStateClassifier

        active_interval = 1.0 / self._capture_fps if self._capture_fps > 0 else 1.0
        self._capture = ScreenCapture(active_interval=active_interval)
        self._app = AppDetector()
        self._ocr = OCRPipeline()
        self._elements = UIElementDetector()
        self._state = AppStateClassifier()
        self._initialized = True

    def perceive(self) -> Optional[PerceptionFrame]:
        self._ensure_initialized()
        capture = self._capture.capture()
        if capture is None:
            if self._last_frame:
                self._last_frame.idle_seconds = time.time() - self._idle_start
            return self._last_frame

        self._idle_start = time.time()
        app_info = self._app.detect()
        text_content = self._ocr.extract(capture.image) if self._ocr_enabled else {}
        ocr_positions = self._ocr.extract_with_positions(capture.image) if self._ocr_enabled else []
        if self._element_detection:
            elements = self._elements.detect(capture.image, ocr_positions)
        else:
            elements = []
        screen_type = self._state.classify(app_info, text_content)

        frame = PerceptionFrame(
            timestamp=capture.timestamp,
            app_name=app_info.name,
            app_bundle_id=app_info.bundle_id,
            window_title=app_info.window_title,
            screen_type=screen_type,
            elements=elements,
            text_content=text_content,
        )

        if self._last_frame:
            frame.is_typing = self._detect_typing(frame, self._last_frame)
            frame.is_navigating = frame.app_name != self._last_frame.app_name

        self._last_frame = frame
        del capture.image
        return frame

    def _detect_typing(self, current, previous):
        curr = " ".join(current.text_content.values())
        prev = " ".join(previous.text_content.values())
        return len(curr) > len(prev) + 5

    def set_mode(self, mode: CaptureMode):
        self._ensure_initialized()
        self._capture.set_mode(mode)

    @property
    def frame_interval(self):
        if self._capture is None:
            return 1.0 / self._capture_fps if self._capture_fps > 0 else 1.0
        return self._capture.frame_interval
