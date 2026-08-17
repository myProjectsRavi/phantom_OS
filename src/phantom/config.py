"""Configuration loader."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

try:
    import tomllib as _tomllib
except ImportError:  # Python 3.10
    import tomli as _tomllib

tomllib: ModuleType = _tomllib


@dataclass
class PhantomConfig:
    trust_level: str = "approve_new"
    capture_fps: float = 1.0
    pattern_threshold: int = 3
    max_actions_per_minute: int = 10
    ocr_enabled: bool = True
    element_detection: bool = True
    capture_retention: int = 0
    log_retention_days: int = 30
    excluded_apps: list[str] = field(default_factory=lambda: ["1Password", "Keychain Access"])
    blocked_domains: list[str] = field(default_factory=lambda: ["bank", "medical"])
    local_llm_helpers_enabled: bool = False
    neurovault_enabled: bool = False
    neurovault_base_dir: str = ""
    recipe_dir: str = field(default_factory=lambda: str(Path.home() / ".phantom" / "recipes"))
    pattern_store: str = field(
        default_factory=lambda: str(Path.home() / ".phantom" / "patterns.json")
    )
    notification_style: str = "ghost"
    log_level: str = "info"

    llm_provider: str = "auto"
    ollama_host: str = "http://localhost:11434"
    llm_model: str = "auto"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 1024
    llm_timeout: float = 30.0
    llm_base_url: str = ""
    llm_api_key: str = ""

    @property
    def excluded_urls(self) -> list[str]:
        return self.blocked_domains

    @classmethod
    def load(cls, path: str | None = None) -> "PhantomConfig":
        config_path = Path(path or Path.home() / ".phantom" / "config.toml")
        if not config_path.exists():
            return cls()

        # Configuration may contain provider credentials; keep it private even if
        # it was created under a permissive umask or by an older PhantomOS build.
        os.chmod(config_path, 0o600)
        raw = tomllib.loads(config_path.read_text())
        phantom = raw.get("phantom", {})
        perception = raw.get("perception", {})
        privacy = raw.get("privacy", {})
        integrations = raw.get("integrations", {})
        notifications = raw.get("notifications", {})
        llm = raw.get("llm", {})

        trust_level = str(phantom.get("trust_level", "approve_new"))
        if trust_level not in {"suggest_only", "approve_each", "approve_new", "auto_execute"}:
            raise ValueError(f"Invalid trust_level: {trust_level}")

        capture_fps = float(phantom.get("capture_fps", 1.0))
        if capture_fps <= 0:
            raise ValueError("capture_fps must be > 0")

        max_actions = int(phantom.get("max_actions_per_minute", 10))
        if max_actions <= 0:
            raise ValueError("max_actions_per_minute must be > 0")

        return cls(
            trust_level=trust_level,
            capture_fps=capture_fps,
            pattern_threshold=int(phantom.get("pattern_threshold", 3)),
            max_actions_per_minute=max_actions,
            ocr_enabled=bool(perception.get("ocr_enabled", True)),
            element_detection=bool(perception.get("element_detection", True)),
            capture_retention=int(privacy.get("capture_retention", 0)),
            log_retention_days=int(privacy.get("log_retention_days", 30)),
            excluded_apps=list(privacy.get("excluded_apps", ["1Password", "Keychain Access"])),
            blocked_domains=list(
                privacy.get("blocked_domains", privacy.get("excluded_urls", ["bank", "medical"]))
            ),
            local_llm_helpers_enabled=bool(integrations.get("local_llm_helpers_enabled", False)),
            neurovault_enabled=bool(integrations.get("neurovault_enabled", False)),
            neurovault_base_dir=str(integrations.get("neurovault_base_dir", "")),
            recipe_dir=str(
                integrations.get("recipe_dir", Path.home() / ".phantom" / "recipes")
            ),
            pattern_store=str(
                integrations.get("pattern_store", Path.home() / ".phantom" / "patterns.json")
            ),
            notification_style=str(notifications.get("style", "ghost")),
            log_level=str(phantom.get("log_level", "info")),
            llm_provider=str(llm.get("provider", "auto")),
            ollama_host=str(llm.get("ollama_host", "http://localhost:11434")),
            llm_model=str(llm.get("model", "auto")),
            llm_temperature=float(llm.get("temperature", 0.3)),
            llm_max_tokens=int(llm.get("max_tokens", 1024)),
            llm_timeout=float(llm.get("timeout", 30.0)),
            llm_base_url=str(llm.get("base_url", "")),
            llm_api_key=str(llm.get("api_key", "")),
        )
