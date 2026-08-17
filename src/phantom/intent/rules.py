"""Rule-based intent recognition."""

from __future__ import annotations

from typing import Optional

from phantom.models import IntentResult, IntentType, PerceptionFrame


class RuleBasedRecognizer:
    """Fast, deterministic intent recognition from screen state."""

    def recognize(self, frames: list[PerceptionFrame]) -> Optional[IntentResult]:
        if len(frames) < 2:
            return None

        current = frames[-1]
        full_text = " ".join(current.text_content.values()).lower()

        # Debug error detection
        error_kw = [
            "error",
            "exception",
            "traceback",
            "failed",
            "stack trace",
            "segfault",
            "panic",
            "fatal",
        ]
        if any(kw in full_text for kw in error_kw):
            if current.app_name in [
                "Code",
                "Terminal",
                "iTerm2",
                "Warp",
                "Google Chrome",
                "Safari",
            ]:
                return IntentResult(
                    intent=IntentType.DEBUG_ERROR,
                    confidence=0.90,
                    source_app=current.app_name,
                    context={"error_detected": True},
                )

        # Coding
        if current.app_name in ["Code", "IntelliJ IDEA", "PyCharm", "Xcode", "Neovim", "Vim"]:
            if current.screen_type == "editor" and current.is_typing:
                return IntentResult(
                    intent=IntentType.CODING,
                    confidence=0.92,
                    source_app=current.app_name,
                )

        # Messaging
        if current.app_name in ["Slack", "Discord", "Messages", "Telegram", "WhatsApp"]:
            if current.is_typing:
                return IntentResult(
                    intent=IntentType.RESPOND_TO_MESSAGE,
                    confidence=0.90,
                    source_app=current.app_name,
                )

        # Web research
        if current.app_name in ["Safari", "Google Chrome", "Firefox", "Arc"]:
            if current.screen_type == "search":
                return IntentResult(
                    intent=IntentType.WEB_RESEARCH,
                    confidence=0.80,
                    source_app=current.app_name,
                )

        # App switching (3+ different apps in last 4 frames)
        if len(frames) >= 4:
            recent_apps = set(f.app_name for f in frames[-4:])
            if len(recent_apps) >= 3:
                return IntentResult(
                    intent=IntentType.APP_SWITCHING,
                    confidence=0.75,
                    source_app=current.app_name,
                )

        # Copy-paste transfer (app switch with clipboard activity)
        if len(frames) >= 3:
            prev = frames[-2]
            if current.app_name != prev.app_name and current.metadata.get("clipboard_changed"):
                return IntentResult(
                    intent=IntentType.COPY_PASTE_TRANSFER,
                    confidence=0.85,
                    source_app=prev.app_name,
                    target_app=current.app_name,
                )

        return None
