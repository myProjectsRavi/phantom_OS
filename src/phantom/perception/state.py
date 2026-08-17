"""Application state classification based on app and OCR text."""

from __future__ import annotations

from phantom.models import AppInfo


class AppStateClassifier:
    """Classify application state from app info and screen content."""

    APP_SCREENS = {
        "Code": {"screens": {"editor": ["def ", "class ", "import ", "const ", "function "], "terminal": ["$", ">>>", "❯", "zsh", "bash"], "settings": ["Settings", "Preferences", "Configuration"], "git": ["git ", "commit", "branch", "merge"], "search": ["Search", "Find", "Replace"]}},
        "Safari": {"screens": {"browsing": [], "search": ["Google", "Search", "Bing"], "reading": [], "video": ["YouTube", "Watch", "Play"]}},
        "Google Chrome": {"screens": {"browsing": [], "dev_tools": ["Elements", "Console", "Network", "Sources"], "search": ["Google", "Search"]}},
        "Slack": {"screens": {"messaging": ["#", "Direct Messages", "Threads"], "call": ["Huddle", "Call"]}},
        "Terminal": {"screens": {"shell": ["$", "❯", "%"], "vim": [":w", ":q", "-- INSERT --", "NORMAL"], "ssh": ["ssh", "Welcome to"]}},
    }

    def classify(self, app_info: AppInfo, text_content: dict) -> str:
        app_name = app_info.name
        full_text = " ".join(text_content.values()).lower()
        screens = self.APP_SCREENS.get(app_name, {}).get("screens", {})
        best_screen = "unknown"
        best_score = 0
        for screen_name, keywords in screens.items():
            if not keywords:
                continue
            score = sum(1 for keyword in keywords if keyword.lower() in full_text)
            if score > best_score:
                best_score = score
                best_screen = screen_name
        if best_screen == "unknown":
            title = app_info.window_title.lower()
            if any(ext in title for ext in (".py", ".js", ".ts", ".go", ".rs")):
                best_screen = "editor"
            elif "http" in title or "www" in title:
                best_screen = "browsing"
        return best_screen
