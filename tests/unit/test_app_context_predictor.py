"""Targeted tests for AppContextPredictor."""

from __future__ import annotations

from phantom.prediction.app_context import AppContextPredictor


def test_predict_returns_empty_without_transitions():
    predictor = AppContextPredictor()
    assert predictor.predict("Unknown", 10) == []


def test_predict_orders_by_transition_count_and_caps_top_three():
    predictor = AppContextPredictor()
    for _ in range(5):
        predictor.observe("Code", "Slack", 10)
    for _ in range(3):
        predictor.observe("Code", "Terminal", 20)
    for _ in range(2):
        predictor.observe("Code", "Browser", 5)
    predictor.observe("Code", "Notes", 8)
    preds = predictor.predict("Code", time_in_app=5)
    assert len(preds) == 3
    assert preds[0].target_app == "Slack"
    assert preds[1].target_app == "Terminal"
    assert preds[2].target_app == "Browser"
    assert abs(sum(p.confidence for p in preds) - (5 + 3 + 2) / 11) < 1e-6


def test_predict_remaining_time_floors_at_zero_and_uses_average():
    predictor = AppContextPredictor()
    predictor.observe("Mail", "Calendar", 10)
    predictor.observe("Mail", "Calendar", 30)
    preds = predictor.predict("Mail", time_in_app=25)
    assert preds and preds[0].expected_in_seconds == 0


def test_observe_caps_duration_history():
    predictor = AppContextPredictor()
    for i in range(120):
        predictor.observe("Code", "Slack", float(i))
    assert len(predictor._durations["Code"]) == 100
