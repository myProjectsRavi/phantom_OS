# PhantomOS Deployment and Support Guide

PhantomOS v0.1 is a **local macOS desktop runtime**, not a server product.

This document intentionally describes only commands and deployment modes that exist in the public CLI.

## Supported runtime

- macOS desktop session
- Python 3.10-3.13
- foreground daemon started with `phantom start`
- local per-user control socket at `~/.phantom/phantom.sock`

Linux adapters exist in source as experimental building blocks, but Linux desktop automation is not part of the v0.1 support contract.

There is no supported v0.1 REST API, systemd service installer, launchd installer, or remote-control server.

## Install from source

```bash
git clone https://github.com/myProjectsRavi/phantomOS.git
cd phantomOS
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
phantom init
phantom doctor
```

`phantom init` creates `~/.phantom` as an owner-only directory (`0700`) and the initial configuration as `0600`.

## macOS permissions

Grant permissions to the terminal application or Python executable that launches PhantomOS:

1. **Accessibility** for keyboard/application automation.
2. **Screen Recording** for perception capture.
3. **Automation** permissions when macOS prompts for access to System Events or another application.

PhantomOS does not include a CLI command that bypasses or auto-grants these OS permissions.

## Start

```bash
phantom start
```

`phantom start` stays in the foreground. Keep that terminal/session alive or supervise it with an external process manager you already trust.

The daemon owns local state including:

- PID marker: `~/.phantom/phantom.pid` (`0600`)
- singleton lock: `~/.phantom/phantom.lock` (`0600`)
- local control socket: `~/.phantom/phantom.sock` (`0600`)
- exact-action approval hashes/counters: `~/.phantom/approvals.json` (`0600`)
- pattern state: configured `pattern_store` (default `~/.phantom/patterns.json`)
- rotating runtime log: next to the pattern store (default `~/.phantom/phantom.log`)

The daemon singleton lock prevents a second PhantomOS process from unlinking/replacing the active daemon's control socket.

## Runtime control

From another terminal:

```bash
phantom status
phantom stats
phantom perceive
phantom intent
phantom predictions
phantom trust approve_each
phantom emergency-stop
phantom resume-actions
phantom undo
phantom clipboard
```

These commands communicate with the running daemon instead of creating a second daemon state.

Blocking native actions are dispatched off the daemon asyncio event loop, so control requests—including emergency stop—remain responsive while an already-authorized native operation is in flight. Emergency stop blocks subsequent actions; it does not claim to cancel an OS operation that has already been dispatched.

## Stop

```bash
phantom stop
```

The live Unix control channel is the process-identity authority for stopping PhantomOS. The CLI requests daemon status, validates the returned positive integer PID, repairs a stale/missing PID marker to that verified identity, confirms the process exists, and only then sends `SIGTERM`.

If the control socket cannot answer, PhantomOS does **not** signal a PID merely because a PID file happens to exist. Stale PID/socket markers are cleaned instead. This prevents PID reuse plus stale local state from causing an unrelated process to be signalled.

## Configuration

`~/.phantom/config.toml` uses these public sections:

```toml
[phantom]
trust_level = "approve_new"
capture_fps = 1.0
pattern_threshold = 3
max_actions_per_minute = 10
log_level = "info"

[perception]
ocr_enabled = true
element_detection = true

[privacy]
capture_retention = 0
log_retention_days = 30
excluded_apps = ["1Password", "Keychain Access"]
blocked_domains = ["bank", "medical"]

[llm]
provider = "auto"
ollama_host = "http://localhost:11434"
model = "auto"
temperature = 0.3
max_tokens = 1024
timeout = 30
base_url = ""
api_key = ""

[notifications]
style = "ghost"
```

The optional NeuroVault integration is disabled by default and is separately installable with `rtnlabs-phantomos[memory]` on Python 3.11+; it is not required for the core runtime.

Invalid trust levels, non-positive capture FPS, and non-positive action-rate limits fail configuration loading instead of silently reverting to defaults. Existing configuration is tightened to mode `0600` when loaded because it may contain a local provider key.

## `approve_new` state

`approve_new` learns only an **exact** canonical action signature after five explicit approvals. Cross-process learning is persisted in `~/.phantom/approvals.json` so an interactive CLI approval can later be observed by the daemon.

The file stores SHA-256 digests and counters only—not typed text, URLs, command contents, or raw action parameters. Corrupt trust state fails closed.

## Docker

Desktop automation requires host OS APIs and a real desktop session, so Docker is not a production PhantomOS deployment target.

The repository container files perform a package/configuration smoke check only:

```bash
docker compose up --build --abort-on-container-exit
```

No network port or REST health endpoint is exposed.

## Release verification

Before calling a commit release-ready, require the exact commit to pass the configured gates:

- public snapshot safety check
- compile check
- Ruff lint and format check
- mypy
- test suite with 95% coverage gate
- wheel build/install smoke on Python 3.10-3.13
- benchmark harness smoke
- Bandit
- `pip-audit`
- real macOS Accessibility/Screen Recording/AppleScript integration validation for the public desktop support claim

See [OPERATIONS.md](OPERATIONS.md) for runtime operations and [SECURITY.md](SECURITY.md) for vulnerability reporting.
