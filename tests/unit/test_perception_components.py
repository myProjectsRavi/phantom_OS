"""Test OCR and UI element perception components."""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

import phantom.perception.elements as elements_module
from phantom.models import UIElementType
from phantom.perception.elements import UIElementDetector
from phantom.perception.ocr import OCRPipeline


def test_ui_element_detector_classifies_and_deduplicates_text_elements():
    detector = UIElementDetector()
    image = np.zeros((120, 200, 3), dtype=np.uint8)
    ocr_data = [
        {"text": "https://example.com", "x": 5, "y": 10, "w": 150, "h": 24, "confidence": 0.9},
        {"text": "Run", "x": 20, "y": 40, "w": 90, "h": 30, "confidence": 0.8},
        {"text": "Run", "x": 20, "y": 40, "w": 90, "h": 30, "confidence": 0.8},
    ]

    elements = detector.detect(image, ocr_data)
    kinds = {element.type for element in elements}
    run_buttons = [
        element
        for element in elements
        if element.type == UIElementType.BUTTON and element.bounds == (20, 40, 90, 30)
    ]

    assert UIElementType.LINK in kinds
    assert UIElementType.BUTTON in kinds
    assert UIElementType.TITLE_BAR in kinds
    assert UIElementType.STATUS_BAR in kinds
    assert len(run_buttons) == 1
    assert (
        detector._classify_text_element({"text": "very long label text", "w": 400, "h": 80})
        == UIElementType.UNKNOWN
    )


def test_ui_element_detector_requires_numpy(monkeypatch):
    detector = UIElementDetector()
    monkeypatch.setattr(elements_module, "np", None)

    with pytest.raises(RuntimeError, match="numpy is required"):
        detector.detect(image=np.zeros((10, 10, 3), dtype=np.uint8), ocr_data=[])


def _install_fake_ocr_modules(monkeypatch, *, text: str, data: dict):
    fake_output = types.SimpleNamespace(DICT="DICT")
    fake_pytesseract = types.SimpleNamespace(
        Output=fake_output,
        image_to_string=lambda _img: text,
        image_to_data=lambda _img, output_type=None: data,
        get_tesseract_version=lambda: "5.0.0",
    )
    fake_pil = types.SimpleNamespace(Image=types.SimpleNamespace(fromarray=lambda arr: arr))

    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)


def test_ocr_pipeline_extract_and_positions(monkeypatch):
    _install_fake_ocr_modules(
        monkeypatch,
        text="  hello world  ",
        data={
            "text": ["hello", "", "world"],
            "conf": ["95", "80", "35"],
            "left": [1, 2, 3],
            "top": [4, 5, 6],
            "width": [7, 8, 9],
            "height": [10, 11, 12],
        },
    )

    pipeline = OCRPipeline()
    image = np.zeros((8, 8, 3), dtype=np.uint8)

    extracted = pipeline.extract(image)
    positions = pipeline.extract_with_positions(image)

    assert extracted == {"full_screen": "hello world"}
    assert positions == [
        {
            "text": "hello",
            "x": 1,
            "y": 4,
            "w": 7,
            "h": 10,
            "confidence": 0.95,
        }
    ]


def test_ocr_pipeline_unavailable_returns_empty_results(monkeypatch):
    monkeypatch.setattr(OCRPipeline, "_check", lambda self: False)
    pipeline = OCRPipeline()

    image = np.zeros((6, 6, 3), dtype=np.uint8)
    assert pipeline.extract(image) == {}
    assert pipeline.extract_with_positions(image) == []


def test_ocr_check_handles_missing_engine(monkeypatch):
    fake_pytesseract = types.SimpleNamespace(
        get_tesseract_version=lambda: (_ for _ in ()).throw(RuntimeError("missing")),
    )
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)

    pipeline = OCRPipeline()

    assert pipeline._check() is False
