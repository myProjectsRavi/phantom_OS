#!/usr/bin/env python3
"""Fail closed on sensitive material in reachable Git history.

The scan is deterministic and offline. It checks commit metadata plus text files in
all commits reachable from the refs available in the checkout. Public CI output is
intentionally non-diagnostic: matched values, commit messages, filenames, paths,
and other repository-derived finding details are never printed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path, PurePosixPath

import check_public_snapshot as snapshot

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_EXACT_EMAILS = {
    "noreply" + "@github.com",
    "support" + "@github.com",
}


def _git(*args: str) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def _allowed_email(email: str) -> bool:
    lowered = email.lower()
    return lowered in ALLOWED_EXACT_EMAILS or lowered.endswith(snapshot.ALLOWED_EMAIL_SUFFIXES)


def _text_has_finding(text: str) -> bool:
    if any(pattern.search(text) for pattern in snapshot.SECRET_PATTERNS.values()):
        return True
    return any(not _allowed_email(email) for email in snapshot.EMAIL_PATTERN.findall(text))


def _has_blocked_dir(relative: PurePosixPath) -> bool:
    posix = relative.as_posix()
    return any(
        posix == blocked or posix.startswith(f"{blocked}/") or f"/{blocked}/" in f"/{posix}/"
        for blocked in snapshot.BLOCKED_DIRS
    )


def _path_has_finding(relative: PurePosixPath) -> bool:
    lower_name = relative.name.lower()
    return (
        lower_name in snapshot.BLOCKED_NAMES
        or lower_name.startswith(".env.")
        or relative.suffix.lower() in snapshot.BLOCKED_SUFFIXES
        or _has_blocked_dir(relative)
    )


def main() -> int:
    finding_detected = False
    scanned_blobs: set[str] = set()

    try:
        commits = list(dict.fromkeys(_git("rev-list", "--all", "HEAD").decode().splitlines()))
        if not commits:
            raise RuntimeError("no reachable commits found")

        for commit in commits:
            metadata = _git("show", "-s", "--format=%ae%x00%ce%x00%B", commit).decode(
                "utf-8", errors="replace"
            )
            author_email, committer_email, message = metadata.split("\x00", 2)

            if author_email and not _allowed_email(author_email.strip()):
                finding_detected = True
            if committer_email and not _allowed_email(committer_email.strip()):
                finding_detected = True
            if _text_has_finding(message):
                finding_detected = True

            tree = _git("ls-tree", "-r", "-z", "--full-tree", commit)
            for entry in tree.split(b"\x00"):
                if not entry:
                    continue
                header, path_bytes = entry.split(b"\t", 1)
                _mode, object_type, blob_sha = header.decode("ascii").split()
                if object_type != "blob":
                    continue

                path_text = path_bytes.decode("utf-8", errors="surrogateescape")
                relative = PurePosixPath(path_text)
                if _path_has_finding(relative):
                    finding_detected = True

                if (
                    relative.suffix.lower() not in snapshot.TEXT_SUFFIXES
                    and relative.name not in snapshot.TEXT_NAMES
                ):
                    continue
                if blob_sha in scanned_blobs:
                    continue
                scanned_blobs.add(blob_sha)

                data = _git("cat-file", "blob", blob_sha)
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                if _text_has_finding(text):
                    finding_detected = True
    except (OSError, subprocess.CalledProcessError, UnicodeError, ValueError, RuntimeError) as exc:
        print(f"Full-history safety gate failed closed: {type(exc).__name__}", file=sys.stderr)
        return 1

    if finding_detected:
        print(
            "Full-history secret and privacy gate failed. "
            "Reproduce the scan locally for private diagnostics.",
            file=sys.stderr,
        )
        return 1

    print(f"Full-history secret and privacy gate passed ({len(commits)} commits scanned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
