"""Sequence similarity matching."""

from __future__ import annotations

from phantom.models import LearnedPattern


class SequenceSimilarity:
    @staticmethod
    def levenshtein(seq1: list[str], seq2: list[str]) -> float:
        n, m = len(seq1), len(seq2)
        if n == 0 or m == 0:
            return 0.0
        dp = [[0] * (m + 1) for _ in range(n + 1)]
        for i in range(n + 1):
            dp[i][0] = i
        for j in range(m + 1):
            dp[0][j] = j
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                cost = 0 if seq1[i - 1] == seq2[j - 1] else 1
                dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
        return 1.0 - (dp[n][m] / max(n, m))

    @staticmethod
    def is_similar(p1: LearnedPattern, p2: LearnedPattern, threshold=0.70):
        return (
            SequenceSimilarity.levenshtein(p1.signature.split("|"), p2.signature.split("|"))
            >= threshold
        )
