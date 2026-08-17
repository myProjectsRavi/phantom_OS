"""Coverage tests for AppStateClassifier heuristics."""

from __future__ import annotations

from phantom.models import AppInfo
from phantom.perception.state import AppStateClassifier


def test_classify_keyword_matches():
    classifier = AppStateClassifier()
    code = AppInfo(name="Code", window_title="main.py")
    terminal = AppInfo(name="Terminal", window_title="zsh")

    assert classifier.classify(code, {"line": "def run() import os"}) == "editor"
    assert classifier.classify(terminal, {"line": "$ ls -la"}) == "shell"


def test_classify_fallbacks_and_unknown():
    classifier = AppStateClassifier()

    unknown = AppInfo(name="CustomApp", window_title="notes.txt")
    editor_like = AppInfo(name="CustomApp", window_title="service.rs")
    browser_like = AppInfo(name="CustomApp", window_title="www.example.com")

    assert classifier.classify(editor_like, {"line": ""}) == "editor"
    assert classifier.classify(browser_like, {"line": ""}) == "browsing"
    assert classifier.classify(unknown, {"line": "hello"}) == "unknown"
