"""Focused coverage tests for intent and action recording paths."""

from __future__ import annotations

import time

from phantom.intent.recognizer import IntentRecognizer
from phantom.intent.rules import RuleBasedRecognizer
from phantom.intent.sequences import SequenceRecognizer
from phantom.models import ActionType, IntentResult, IntentType, PerceptionFrame, UserAction
from phantom.patterns.recorder import ActionRecorder


def _action(action_type: ActionType, app: str) -> UserAction:
    return UserAction(type=action_type, app_name=app)


def test_rule_recognizer_web_research_intent() -> None:
    recognizer = RuleBasedRecognizer()
    frames = [
        PerceptionFrame(app_name="Google Chrome", screen_type="browser"),
        PerceptionFrame(app_name="Google Chrome", screen_type="search"),
    ]
    result = recognizer.recognize(frames)
    assert result is not None
    assert result.intent == IntentType.WEB_RESEARCH
    assert result.confidence == 0.80


def test_rule_recognizer_app_switching_intent() -> None:
    recognizer = RuleBasedRecognizer()
    frames = [
        PerceptionFrame(app_name="Code"),
        PerceptionFrame(app_name="Terminal"),
        PerceptionFrame(app_name="Google Chrome"),
        PerceptionFrame(app_name="Code"),
    ]
    result = recognizer.recognize(frames)
    assert result is not None
    assert result.intent == IntentType.APP_SWITCHING


def test_rule_recognizer_copy_paste_transfer_intent() -> None:
    recognizer = RuleBasedRecognizer()
    frames = [
        PerceptionFrame(app_name="Google Chrome"),
        PerceptionFrame(app_name="Google Chrome"),
        PerceptionFrame(app_name="Slack", metadata={"clipboard_changed": True}),
    ]
    result = recognizer.recognize(frames)
    assert result is not None
    assert result.intent == IntentType.COPY_PASTE_TRANSFER
    assert result.source_app == "Google Chrome"
    assert result.target_app == "Slack"


def test_rule_recognizer_no_match_returns_none() -> None:
    recognizer = RuleBasedRecognizer()
    frames = [
        PerceptionFrame(app_name="Notes", text_content={"body": "hello"}),
        PerceptionFrame(app_name="Notes", text_content={"body": "still writing"}, is_typing=False),
    ]
    assert recognizer.recognize(frames) is None


def test_sequence_recognizer_history_cap() -> None:
    recognizer = SequenceRecognizer()
    for i in range(550):
        recognizer.add_action(_action(ActionType.APP_SWITCH, f"App-{i}"))
    assert len(recognizer._history) == 500
    assert recognizer._history[0].app_name == "App-50"


def test_sequence_recognizer_learned_sequence_match() -> None:
    recognizer = SequenceRecognizer()
    actions = [
        _action(ActionType.APP_SWITCH, "Code"),
        _action(ActionType.KEYSTROKE, "Code"),
        _action(ActionType.FILE_SAVE, "Code"),
        _action(ActionType.APP_SWITCH, "Terminal"),
        _action(ActionType.COMMAND_RUN, "Terminal"),
    ]
    for action in actions:
        recognizer.add_action(action)

    key = recognizer._key(actions)
    recognizer.learn(key, IntentType.CODING)
    result = recognizer.recognize()
    assert result is not None
    assert result.intent == IntentType.CODING
    assert result.context["sequence_key"] == key


def test_sequence_recognizer_detects_repetition() -> None:
    recognizer = SequenceRecognizer()
    repeated = [
        _action(ActionType.CLIPBOARD_COPY, "Google Chrome"),
        _action(ActionType.CLIPBOARD_PASTE, "Slack"),
    ]
    for _ in range(3):
        for action in repeated:
            recognizer.add_action(action)

    result = recognizer.recognize()
    assert result is not None
    assert result.intent == IntentType.UNKNOWN
    assert result.suggested_automation is not None
    assert result.suggested_automation["type"] == "repeat"
    assert len(result.suggested_automation["steps"]) == 2


def test_sequence_recognizer_no_pattern_returns_none() -> None:
    recognizer = SequenceRecognizer()
    for app in ["Code", "Terminal", "Notes", "Safari", "Messages"]:
        recognizer.add_action(_action(ActionType.APP_SWITCH, app))
    assert recognizer.recognize() is None


def test_intent_recognizer_uses_high_confidence_rule() -> None:
    recognizer = IntentRecognizer()
    recognizer._rules.recognize = lambda _frames: IntentResult(
        intent=IntentType.CODING, confidence=0.95
    )
    recognizer._sequences.recognize = lambda: IntentResult(
        intent=IntentType.UNKNOWN, confidence=0.99
    )

    result = recognizer.recognize(PerceptionFrame(app_name="Code"))
    assert result.intent == IntentType.CODING


def test_intent_recognizer_uses_sequence_when_rule_low() -> None:
    recognizer = IntentRecognizer()
    recognizer._rules.recognize = lambda _frames: IntentResult(
        intent=IntentType.CODING, confidence=0.30
    )
    recognizer._sequences.recognize = lambda: IntentResult(
        intent=IntentType.WEB_RESEARCH, confidence=0.80
    )

    result = recognizer.recognize(PerceptionFrame(app_name="Google Chrome"))
    assert result.intent == IntentType.WEB_RESEARCH


def test_intent_recognizer_rule_fallback_when_sequence_low() -> None:
    recognizer = IntentRecognizer()
    recognizer._rules.recognize = lambda _frames: IntentResult(
        intent=IntentType.RESPOND_TO_MESSAGE, confidence=0.70
    )
    recognizer._sequences.recognize = lambda: IntentResult(
        intent=IntentType.UNKNOWN, confidence=0.10
    )

    result = recognizer.recognize(PerceptionFrame(app_name="Slack"))
    assert result.intent == IntentType.RESPOND_TO_MESSAGE


def test_intent_recognizer_default_typing_idle_and_browsing() -> None:
    recognizer = IntentRecognizer()
    recognizer._rules.recognize = lambda _frames: None
    recognizer._sequences.recognize = lambda: None

    writing = recognizer.recognize(PerceptionFrame(app_name="Notes", is_typing=True))
    assert writing.intent == IntentType.WRITING

    idle = recognizer.recognize(PerceptionFrame(app_name="Notes", idle_seconds=45))
    assert idle.intent == IntentType.IDLE

    browsing = recognizer.recognize(PerceptionFrame(app_name="Safari"))
    assert browsing.intent == IntentType.BROWSING


def test_intent_recognizer_buffer_limit_and_action_forwarding() -> None:
    recognizer = IntentRecognizer()
    recognizer._rules.recognize = lambda _frames: None
    recognizer._sequences.recognize = lambda: None

    called: list[UserAction] = []
    recognizer._sequences.add_action = lambda action: called.append(action)

    for i in range(40):
        recognizer.recognize(PerceptionFrame(app_name=f"App-{i}"))

    action = _action(ActionType.KEYSTROKE, "Code")
    recognizer.add_action(action)

    assert len(recognizer._buffer) == 30
    assert called == [action]


def test_action_recorder_records_and_trims() -> None:
    recorder = ActionRecorder(max_actions=3)
    for i in range(5):
        recorder.record(_action(ActionType.APP_SWITCH, f"App-{i}"))

    recent = recorder.get_recent(count=10)
    assert len(recent) == 3
    assert [a.app_name for a in recent] == ["App-2", "App-3", "App-4"]


def test_action_recorder_notifies_listeners_and_swallows_exceptions() -> None:
    recorder = ActionRecorder()
    received: list[str] = []

    def listener_ok(action: UserAction) -> None:
        received.append(action.app_name)

    def listener_fail(_action: UserAction) -> None:
        raise RuntimeError("boom")

    recorder.on_action(listener_ok)
    recorder.on_action(listener_fail)
    recorder.record(_action(ActionType.APP_SWITCH, "Code"))

    assert received == ["Code"]


def test_action_recorder_get_window_filters_by_timestamp() -> None:
    recorder = ActionRecorder()
    now = time.time()
    recorder.record(UserAction(type=ActionType.APP_SWITCH, app_name="Old", timestamp=now - 600))
    recorder.record(UserAction(type=ActionType.APP_SWITCH, app_name="New", timestamp=now - 10))

    window = recorder.get_window(seconds=60)
    assert [a.app_name for a in window] == ["New"]
