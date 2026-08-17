"""Application control."""

from __future__ import annotations

import subprocess
from urllib.parse import urlparse

from phantom.applescript import escape_applescript, run_osascript
from phantom.models import ActionResult, PhantomActionType


class AppController:
    def activate(self, app_name: str) -> ActionResult:
        try:
            safe_app = escape_applescript(app_name)
            completed = run_osascript(f'tell application "{safe_app}" to activate', timeout=5)
            if completed.returncode != 0:
                return ActionResult(
                    success=False,
                    action_type=PhantomActionType.APP_ACTIVATE,
                    error=f"osascript exited with {completed.returncode}",
                )
            return ActionResult(success=True, action_type=PhantomActionType.APP_ACTIVATE)
        except Exception as exc:
            return ActionResult(
                success=False, action_type=PhantomActionType.APP_ACTIVATE, error=str(exc)
            )

    def open_url(self, url: str) -> ActionResult:
        try:
            parsed = urlparse((url or "").strip())
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
                return ActionResult(
                    success=False,
                    action_type=PhantomActionType.URL_OPEN,
                    error="Only http/https URLs are allowed",
                )
            completed = subprocess.run(["open", url], timeout=5, check=False)
            if completed.returncode != 0:
                return ActionResult(
                    success=False,
                    action_type=PhantomActionType.URL_OPEN,
                    error=f"open exited with {completed.returncode}",
                )
            return ActionResult(success=True, action_type=PhantomActionType.URL_OPEN)
        except Exception as exc:
            return ActionResult(
                success=False, action_type=PhantomActionType.URL_OPEN, error=str(exc)
            )

    def open_file(self, path: str) -> ActionResult:
        try:
            completed = subprocess.run(["open", path], timeout=5, check=False)
            if completed.returncode != 0:
                return ActionResult(
                    success=False,
                    action_type=PhantomActionType.FILE_OPEN,
                    error=f"open exited with {completed.returncode}",
                )
            return ActionResult(success=True, action_type=PhantomActionType.FILE_OPEN)
        except Exception as exc:
            return ActionResult(
                success=False, action_type=PhantomActionType.FILE_OPEN, error=str(exc)
            )

    def list_running(self) -> list[str]:
        result = run_osascript(
            'tell application "System Events" to get name of every application process whose background only is false',
            timeout=5,
            capture_output=True,
        )
        if result.returncode != 0:
            return []
        return [app.strip() for app in (result.stdout or "").split(",") if app.strip()]
