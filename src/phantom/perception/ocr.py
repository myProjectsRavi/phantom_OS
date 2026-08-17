"""OCR pipeline."""

from __future__ import annotations

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]


class OCRPipeline:
    def __init__(self):
        self._available = np is not None and self._check()

    def extract(self, image: np.ndarray) -> dict[str, str]:
        if not self._available:
            return {}
        import pytesseract
        from PIL import Image

        pil = Image.fromarray(image)
        text = pytesseract.image_to_string(pil).strip()
        return {"full_screen": text} if text else {}

    def extract_with_positions(self, image: np.ndarray) -> list[dict]:
        if not self._available:
            return []
        import pytesseract
        from PIL import Image

        pil = Image.fromarray(image)
        data = pytesseract.image_to_data(pil, output_type=pytesseract.Output.DICT)
        results = []
        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            conf = int(data["conf"][i])
            if text and conf > 40:
                results.append(
                    {
                        "text": text,
                        "x": data["left"][i],
                        "y": data["top"][i],
                        "w": data["width"][i],
                        "h": data["height"][i],
                        "confidence": conf / 100.0,
                    }
                )
        return results

    def _check(self):
        try:
            import pytesseract

            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False
