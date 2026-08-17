"""Test intent recognition."""

from phantom.intent.rules import RuleBasedRecognizer
from phantom.models import IntentType, PerceptionFrame


def test_coding_intent():
    recognizer = RuleBasedRecognizer()
    frames = [
        PerceptionFrame(app_name="Code", screen_type="editor", is_typing=False),
        PerceptionFrame(app_name="Code", screen_type="editor", is_typing=True),
    ]
    result = recognizer.recognize(frames)
    assert result is not None
    assert result.intent == IntentType.CODING
    assert result.confidence >= 0.90


def test_debug_intent():
    recognizer = RuleBasedRecognizer()
    frames = [
        PerceptionFrame(app_name="Terminal", text_content={"full_screen": "ok"}),
        PerceptionFrame(
            app_name="Terminal",
            text_content={"full_screen": "Traceback (most recent call last): Error"},
        ),
    ]
    result = recognizer.recognize(frames)
    assert result is not None
    assert result.intent == IntentType.DEBUG_ERROR


def test_messaging_intent():
    recognizer = RuleBasedRecognizer()
    frames = [
        PerceptionFrame(app_name="Slack", is_typing=False),
        PerceptionFrame(app_name="Slack", is_typing=True),
    ]
    result = recognizer.recognize(frames)
    assert result is not None
    assert result.intent == IntentType.RESPOND_TO_MESSAGE


def test_no_intent_with_single_frame():
    recognizer = RuleBasedRecognizer()
    result = recognizer.recognize([PerceptionFrame()])
    assert result is None
