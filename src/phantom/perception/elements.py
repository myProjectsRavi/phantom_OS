"""UI element detection from OCR and simple layout heuristics."""

from __future__ import annotations

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]

from phantom.models import UIElement, UIElementType


class UIElementDetector:
    """Detect UI elements from screen captures using heuristics."""

    ELEMENT_PATTERNS = {
        UIElementType.BUTTON: {
            "min_width": 40,
            "max_width": 300,
            "min_height": 20,
            "max_height": 60,
            "aspect_ratio_range": (1.5, 8.0),
            "has_text": True,
        },
        UIElementType.TEXT_FIELD: {
            "min_width": 100,
            "max_width": 800,
            "min_height": 20,
            "max_height": 40,
            "aspect_ratio_range": (3.0, 30.0),
            "has_border": True,
        },
        UIElementType.CODE_BLOCK: {
            "min_width": 400,
            "min_height": 200,
            "has_monospace": True,
        },
        UIElementType.TERMINAL: {
            "min_width": 300,
            "min_height": 100,
            "dark_background": True,
            "has_monospace": True,
        },
    }

    def detect(self, image: np.ndarray, ocr_data: list[dict]) -> list[UIElement]:
        """Detect UI elements combining visual and text analysis."""
        if np is None:  # pragma: no cover
            raise RuntimeError("numpy is required for UI element detection")
        elements: list[UIElement] = []

        for item in ocr_data:
            element_type = self._classify_text_element(item)
            elements.append(
                UIElement(
                    type=element_type,
                    bounds=(
                        item.get("x", 0),
                        item.get("y", 0),
                        item.get("w", 0),
                        item.get("h", 0),
                    ),
                    text=item.get("text", ""),
                    confidence=float(item.get("confidence", 0.0)),
                    interactive=element_type
                    in (UIElementType.BUTTON, UIElementType.TEXT_FIELD, UIElementType.LINK),
                )
            )

        h, w = image.shape[:2]
        elements.append(
            UIElement(type=UIElementType.TITLE_BAR, bounds=(0, 0, w, 40), confidence=0.9)
        )
        elements.append(
            UIElement(
                type=UIElementType.STATUS_BAR,
                bounds=(0, max(0, h - 25), w, 25),
                confidence=0.8,
            )
        )

        return self._deduplicate(elements)

    def _classify_text_element(self, item: dict) -> UIElementType:
        text = str(item.get("text", ""))
        w = int(item.get("w", 0))
        h = int(item.get("h", 0))

        if any(text.startswith(prefix) for prefix in ("http://", "https://", "www.")):
            return UIElementType.LINK
        if w < 200 and h < 50 and len(text) < 20:
            return UIElementType.BUTTON
        return UIElementType.UNKNOWN

    def _deduplicate(self, elements: list[UIElement]) -> list[UIElement]:
        seen: set[tuple[UIElementType, tuple]] = set()
        unique: list[UIElement] = []
        for element in elements:
            key = (element.type, element.bounds)
            if key in seen:
                continue
            seen.add(key)
            unique.append(element)
        return unique
