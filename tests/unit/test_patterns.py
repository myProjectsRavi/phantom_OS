"""Test pattern discovery."""

from phantom.models import LearnedPattern
from phantom.patterns.discovery import PatternDiscovery
from phantom.patterns.similarity import SequenceSimilarity


def test_pattern_discovery(sample_actions):
    discovery = PatternDiscovery()
    patterns = discovery.analyze(sample_actions)
    assert len(patterns) > 0
    found = any(p.frequency >= 3 for p in patterns)
    assert found


def test_levenshtein_identical():
    assert SequenceSimilarity.levenshtein(["a", "b", "c"], ["a", "b", "c"]) == 1.0


def test_levenshtein_completely_different():
    score = SequenceSimilarity.levenshtein(["a", "b"], ["x", "y"])
    assert score < 0.5


def test_is_similar():
    p1 = LearnedPattern(signature="copy@Chrome|paste@Slack")
    p2 = LearnedPattern(signature="copy@Chrome|paste@Slack")
    assert SequenceSimilarity.is_similar(p1, p2)
