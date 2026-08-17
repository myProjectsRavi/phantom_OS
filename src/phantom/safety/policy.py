"""Safety policy enforcement."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import tempfile
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from phantom.models import ActionRequest, PhantomActionType, TrustLevel


class SafetyPolicy:
    """Apply trust, rate limits, command grammar, and blocklists to actions."""

    ALLOWED_COMMANDS = frozenset({"echo", "date", "pwd", "ls", "open", "killall"})
    BLOCKED_APPS = frozenset(["1Password", "Keychain Access", "System Preferences", "System Settings", "Disk Utility"])
    BLOCKED_PATHS = ["~/.ssh/", "~/.aws/", "~/.gnupg/", "/etc/", "/System/"]
    BLOCKED_COMMANDS = ["rm -rf", "sudo", "chmod 777", "mkfs", "dd if=", "curl | sh", "wget | sh"]

    def __init__(self, approval_callback: Optional[Callable[[ActionRequest], bool]] = None, *, blocked_apps: list[str] | None = None, blocked_paths: list[str] | None = None, blocked_commands: list[str] | None = None, blocked_domains: list[str] | None = None, max_actions_per_minute: int = 10, approval_store_path: str | Path | None = None):
        self.trust_level = TrustLevel.APPROVE_NEW
        self._approved: set[str] = set()
        self._counts: dict[str, int] = defaultdict(int)
        self._rate: list[float] = []
        self._errors = 0
        self._stopped = False
        self._approval_callback = approval_callback
        self._max_actions_per_minute = max_actions_per_minute
        if approval_store_path is None:
            configured_store = os.environ.get("PHANTOM_APPROVAL_STORE")
            approval_store_path = configured_store if configured_store is not None else Path.home() / ".phantom" / "approvals.json"
        self._approval_store_path = Path(approval_store_path).expanduser() if approval_store_path else None
        self._approval_store_mtime_ns: int | None = None
        self.blocked_apps = set(self.BLOCKED_APPS)
        if blocked_apps:
            self.blocked_apps.update(blocked_apps)
        self.blocked_paths = list(self.BLOCKED_PATHS)
        if blocked_paths:
            self.blocked_paths.extend(blocked_paths)
        self.blocked_commands = list(self.BLOCKED_COMMANDS)
        if blocked_commands:
            self.blocked_commands.extend(blocked_commands)
        self.blocked_domains = [domain.lower() for domain in (blocked_domains or []) if domain]
        self._load_approval_store(force=True)

    def allow(self, request: ActionRequest) -> bool:
        if self._stopped:
            return False
        if not self._check_blocklists(request):
            return False
        if self.trust_level == TrustLevel.SUGGEST_ONLY:
            return False
        return self._check_rate()

    def requires_approval(self, request: ActionRequest) -> bool:
        if request.requires_approval:
            return True
        if self.trust_level == TrustLevel.APPROVE_EACH:
            return True
        if self.trust_level == TrustLevel.APPROVE_NEW:
            self._load_approval_store()
            return self._approval_key(request) not in self._approved
        return False

    async def request_approval(self, request: ActionRequest) -> bool:
        if self.trust_level == TrustLevel.APPROVE_NEW:
            self._load_approval_store(force=True)
        key = self._approval_key(request)
        if self.trust_level == TrustLevel.SUGGEST_ONLY:
            return False
        if self.trust_level == TrustLevel.AUTO_EXECUTE and not request.requires_approval:
            return True
        if self.trust_level == TrustLevel.APPROVE_NEW and not request.requires_approval and key in self._approved:
            return True
        approved = False
        if self._approval_callback is not None:
            approved = bool(self._approval_callback(request))
        elif os.environ.get("PHANTOM_AUTO_APPROVE", "").lower() in {"1", "true", "yes"}:
            approved = True
        if approved and self.trust_level == TrustLevel.APPROVE_NEW:
            self._counts[key] += 1
            if self._counts[key] >= 5:
                self._approved.add(key)
                self._counts.pop(key, None)
            self._persist_approval_store()
        return approved

    def record_success(self): self._errors = 0
    def record_error(self):
        self._errors += 1
        if self._errors >= 3: self._stopped = True
    def emergency_stop(self): self._stopped = True
    def resume(self): self._stopped = False; self._errors = 0
    @property
    def is_stopped(self): return self._stopped

    def _approval_key(self, request: ActionRequest) -> str:
        try: params = json.dumps(request.params, sort_keys=True, separators=(",", ":"), default=str)
        except (TypeError, ValueError): params = repr(request.params)
        raw = f"{request.type.value}:{request.source}:{params}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _load_approval_store(self, *, force: bool = False) -> None:
        path = self._approval_store_path
        if path is None or not path.exists(): return
        try:
            stat_result = path.stat()
            if not force and stat_result.st_mtime_ns == self._approval_store_mtime_ns: return
            os.chmod(path, 0o600)
            payload = json.loads(path.read_text())
            approved = payload.get("approved", []) if isinstance(payload, dict) else []
            counts = payload.get("counts", {}) if isinstance(payload, dict) else {}
            self._approved = {item for item in approved if isinstance(item, str) and len(item) == 64 and all(ch in "0123456789abcdef" for ch in item)}
            self._counts = defaultdict(int, {key: int(value) for key, value in counts.items() if isinstance(key, str) and len(key) == 64 and all(ch in "0123456789abcdef" for ch in key) and isinstance(value, int) and 0 < value < 5})
            self._approval_store_mtime_ns = path.stat().st_mtime_ns
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self._approved = set(); self._counts = defaultdict(int); self._approval_store_mtime_ns = None

    def _persist_approval_store(self) -> None:
        path = self._approval_store_path
        if path is None: return
        path.parent.mkdir(parents=True, exist_ok=True); os.chmod(path.parent, 0o700)
        payload = {"version": 1, "approved": sorted(self._approved), "counts": dict(sorted(self._counts.items()))}
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
                temp_path = Path(handle.name); json.dump(payload, handle, sort_keys=True, separators=(",", ":")); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
            if temp_path is None: raise RuntimeError("Failed to create approval store temporary file")
            os.chmod(temp_path, 0o600); os.replace(temp_path, path); os.chmod(path, 0o600); self._approval_store_mtime_ns = path.stat().st_mtime_ns
        finally:
            if temp_path is not None:
                try: temp_path.unlink(missing_ok=True)
                except OSError: pass

    def _check_rate(self):
        now = time.time(); self._rate = [timestamp for timestamp in self._rate if now - timestamp < 60]
        if len(self._rate) >= self._max_actions_per_minute: return False
        self._rate.append(now); return True

    def _check_blocklists(self, request: ActionRequest) -> bool:
        if request.type == PhantomActionType.SEQUENCE:
            steps = request.params.get("steps", [])
            if not isinstance(steps, list): return False
            for step in steps:
                if not isinstance(step, dict) or "type" not in step: return False
                try: child = ActionRequest(type=PhantomActionType(step["type"]), params=step.get("params", {}), source=request.source or "sequence")
                except (TypeError, ValueError): return False
                if not self._check_blocklists(child): return False
            return True
        app = str(request.params.get("app", "") or "")
        if self._is_blocked_app(app): return False
        path = str(request.params.get("path", "") or "")
        if path and self._is_blocked_path(path): return False
        command_value = request.params.get("command", ""); text_value = request.params.get("text", "")
        command_text = (self._command_text(command_value) or str(text_value or "")).lower()
        if any(blocked.lower() in command_text for blocked in self.blocked_commands): return False
        if request.type == PhantomActionType.RUN_COMMAND:
            argv = self._command_argv(command_value)
            if not argv or argv[0] not in self.ALLOWED_COMMANDS: return False
            executable = argv[0]; targets = argv[1:]
            if executable == "killall" and not self._killall_targets_allowed(targets): return False
            if executable == "open" and not self._open_targets_allowed(targets): return False
            if executable == "ls" and not self._ls_targets_allowed(targets): return False
        url = str(request.params.get("url", "") or "")
        return not self._is_blocked_url(url)

    def _killall_targets_allowed(self, args: list[str]) -> bool:
        if not args or any(not arg or arg.startswith("-") for arg in args): return False
        return not any(self._is_blocked_app(target) for target in args)

    def _open_targets_allowed(self, args: list[str]) -> bool:
        index = 0
        while index < len(args):
            arg = args[index]
            if arg in {"-n", "-g"}: index += 1; continue
            if arg == "-a":
                if index + 1 >= len(args): return False
                if self._is_blocked_app(args[index + 1]): return False
                index += 2; continue
            if arg.startswith("-"): return False
            parsed = urlparse(arg)
            if parsed.scheme:
                if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc: return False
                if self._is_blocked_url(arg): return False
            else:
                if arg.lower().endswith(".app"):
                    app_name = Path(arg).name[:-4]
                    if self._is_blocked_app(app_name): return False
                if self._is_blocked_path(arg): return False
            index += 1
        return bool(args)

    def _ls_targets_allowed(self, args: list[str]) -> bool:
        safe_short_flags = frozenset("alh1GF")
        for arg in args:
            if arg == "--": continue
            if arg.startswith("-"):
                flags = arg[1:]
                if not flags or any(flag not in safe_short_flags for flag in flags): return False
                continue
            if self._is_blocked_path(arg): return False
        return True

    @staticmethod
    def _normalize_app_name(app: str) -> str: return unicodedata.normalize("NFKC", str(app)).strip().casefold()
    def _is_blocked_app(self, app: str) -> bool:
        candidate = self._normalize_app_name(app)
        if not candidate: return False
        for blocked in self.blocked_apps:
            normalized = self._normalize_app_name(blocked)
            if candidate == normalized or candidate.startswith(f"{normalized} ") or candidate.startswith(f"{normalized}-"): return True
        return False
    def _is_blocked_path(self, path: str) -> bool:
        if not path: return False
        try: candidate = Path(path).expanduser().resolve(strict=False)
        except (OSError, RuntimeError, ValueError): return True
        for blocked in self.blocked_paths:
            try: root = Path(blocked).expanduser().resolve(strict=False)
            except (OSError, RuntimeError, ValueError): continue
            if candidate == root or root in candidate.parents: return True
        return False
    @staticmethod
    def _command_text(raw: object) -> str: return " ".join(str(part) for part in raw) if isinstance(raw, list) else str(raw or "")
    @staticmethod
    def _command_argv(raw: object) -> list[str]:
        if isinstance(raw, list): return [str(part) for part in raw if str(part)]
        if not isinstance(raw, str) or not raw.strip(): return []
        try: return shlex.split(raw)
        except ValueError: return []
    def _is_blocked_url(self, url: str) -> bool:
        if not url or not self.blocked_domains: return False
        normalized = url if "://" in url else f"https://{url}"; parsed = urlparse(normalized)
        value = f"{parsed.netloc}{parsed.path}".lower(); full = normalized.lower()
        return any(domain in value or domain in full for domain in self.blocked_domains)
