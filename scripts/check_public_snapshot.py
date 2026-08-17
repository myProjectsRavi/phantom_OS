#!/usr/bin/env python3
"""Fail-closed pre-publication hygiene checks for the current repository tree.

This intentionally complements, rather than replaces, dedicated secret scanners.
It is deterministic, offline, and safe to run in forks and local development.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    ".verify-wheel-venv",
    "build",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

BLOCKED_NAMES = {
    ".env",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".ds_store",
    "thumbs.db",
    "id_rsa",
    "id_ed25519",
}

BLOCKED_DIRS = {
    ".aws",
    ".claude",
    ".config/gcloud",
    ".kube",
    ".phantom",
}

BLOCKED_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
    ".mobileprovision",
    ".ovpn",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".dump",
    ".bak",
    ".backup",
}

SECRET_PATTERNS = {
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "GitHub fine-grained token": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    "GitLab token": re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "OpenAI/Anthropic-style secret": re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}\b"),
    "Stripe live secret": re.compile(r"\bsk_live_[A-Za-z0-9]{16,}\b"),
    "Hugging Face token": re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    "npm access token": re.compile(r"\bnpm_[A-Za-z0-9]{20,}\b"),
    "JWT-shaped token": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    "private key header": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
}

EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![A-Za-z0-9._%+-])"
)
ALLOWED_EMAIL_SUFFIXES = (
    "@example.com",
    "@example.org",
    "@example.net",
    "@example.test",
    "@users.noreply.github.com",
)

TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".toml",
    ".yml",
    ".yaml",
    ".json",
    ".txt",
    ".cfg",
    ".ini",
    ".sh",
}
TEXT_NAMES = {"Dockerfile", "Makefile", ".gitignore", ".dockerignore", ".coveragerc"}


def _iter_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.resolve() == SELF:
            continue
        relative = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        yield path, relative


def _has_blocked_dir(relative: Path) -> bool:
    posix = relative.as_posix()
    return any(
        posix == blocked or posix.startswith(f"{blocked}/") or f"/{blocked}/" in f"/{posix}/"
        for blocked in BLOCKED_DIRS
    )


def main() -> int:
    failures: list[str] = []

    for path, relative in _iter_files():
        lower_name = path.name.lower()
        if lower_name in BLOCKED_NAMES or lower_name.startswith(".env."):
            failures.append(f"blocked local/secret filename: {relative}")
        if path.suffix.lower() in BLOCKED_SUFFIXES:
            failures.append(f"blocked local/credential artifact: {relative}")
        if _has_blocked_dir(relative):
            failures.append(f"blocked local state/credential directory: {relative}")

        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"{label} shaped content: {relative}")

        for email in EMAIL_PATTERN.findall(text):
            lowered = email.lower()
            if not lowered.endswith(ALLOWED_EMAIL_SUFFIXES):
                failures.append(f"non-synthetic email address: {relative}")
                break

    if failures:
        print("Public snapshot safety gate failed:", file=sys.stderr)
        for failure in sorted(set(failures)):
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Public snapshot safety gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
