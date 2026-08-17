"""Test prediction engine."""

from phantom.models import ActionType, UserAction
from phantom.prediction.engine import PredictionEngine
from phantom.prediction.markov import MarkovPredictor


def test_markov_basic():
    m = MarkovPredictor()
    m.observe("copy@Chrome", "paste@Slack")
    m.observe("copy@Chrome", "paste@Slack")
    m.observe("copy@Chrome", "paste@Discord")
    preds = m.predict("copy@Chrome")
    assert len(preds) > 0
    assert preds[0].target_app == "Slack"
    assert preds[0].confidence > 0.5


def test_prediction_engine():
    engine = PredictionEngine()
    actions = [
        UserAction(type=ActionType.CLIPBOARD_COPY, app_name="Chrome"),
        UserAction(type=ActionType.APP_SWITCH, app_name="Slack"),
        UserAction(type=ActionType.CLIPBOARD_PASTE, app_name="Slack"),
    ]
    for a in actions:
        engine.observe(a)
    preds = engine.predict()
    assert len(preds) > 0
    top = preds[0]
    assert top.confidence > 0
    assert top.source in {"markov", "time_pattern", "app_context"}
