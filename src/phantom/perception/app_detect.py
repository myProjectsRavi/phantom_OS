"""Active application detection."""

from __future__ import annotations

from phantom.applescript import read_active_app_info
from phantom.models import AppInfo


class AppDetector:
    def detect(self) -> AppInfo:
        try:
            app_name, bundle_id, window_title = read_active_app_info()
            return AppInfo(
                name=app_name,
                bundle_id=bundle_id,
                window_title=window_title,
            )
        except Exception:
            return AppInfo(name="Unknown")
