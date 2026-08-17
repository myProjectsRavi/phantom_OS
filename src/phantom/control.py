"""Local-only control channel for the running PhantomOS daemon."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any


class DaemonUnavailable(RuntimeError):
    """Raised when no PhantomOS daemon control socket is reachable."""


def socket_path() -> Path:
    """Return the per-user Unix-domain control socket path."""
    return Path.home() / ".phantom" / "phantom.sock"


def send_command(command: str, **payload: Any) -> dict[str, Any]:
    """Send one JSON command to the local daemon and return its JSON response."""
    path = socket_path()
    if not path.exists():
        raise DaemonUnavailable("PHANTOM daemon is not running")

    request = {"command": command, **payload}
    data = (json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3.0)
            client.connect(str(path))
            client.sendall(data)
            chunks: list[bytes] = []
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\n" in chunk:
                    break
    except (FileNotFoundError, ConnectionError, OSError, socket.timeout) as exc:
        raise DaemonUnavailable("PHANTOM daemon control channel is unavailable") from exc

    raw = b"".join(chunks).split(b"\n", 1)[0]
    if not raw:
        raise DaemonUnavailable("PHANTOM daemon returned no control response")
    response = json.loads(raw.decode("utf-8"))
    if not isinstance(response, dict):
        raise DaemonUnavailable("PHANTOM daemon returned an invalid control response")
    return response
