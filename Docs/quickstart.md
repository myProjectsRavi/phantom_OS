# PhantomOS Quickstart

PhantomOS v0.1 is a macOS-first, local-only desktop automation runtime.

## Prerequisites

- Python 3.10-3.13
- macOS for the supported desktop automation path
- Accessibility permission for the terminal/Python process
- Screen Recording permission when using perception capture
- optional: Tesseract for OCR

## Install from source

```bash
git clone https://github.com/myProjectsRavi/phantom_OS.git
cd phantom_OS
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
phantom init
phantom doctor
```

`phantom init` creates owner-only local state: `~/.phantom`/subdirectories are `0700` and the initial config is `0600`.

## Start the daemon

```bash
phantom start
```

Leave that terminal running. The daemon creates a per-user control socket at:

```text
~/.phantom/phantom.sock
```

with mode `0600`, plus an owner-only singleton lock that prevents a second daemon from replacing the control socket.

## Inspect the running daemon

In another terminal:

```bash
phantom status
phantom perceive
phantom intent
phantom predictions
phantom stats
```

These commands query the running daemon; they do not construct a separate agent process.

## Safety controls

```bash
phantom trust approve_each
phantom emergency-stop
phantom resume-actions
phantom undo
```

`approve_each` always requires explicit approval. `approve_new` requires explicit approval for an exact canonical action until that exact action has been approved five times. Learned `approve_new` state is shared between CLI and daemon via `~/.phantom/approvals.json`, which stores SHA-256 action-signature digests/counters only—not raw typed text, URLs, commands, or parameters.

Manual recipe execution uses an interactive approval prompt. Background daemon actions have no implicit self-approval channel and therefore fail closed until the exact action has graduated under `approve_new` or the trust level is deliberately changed.

## Recipes

```bash
phantom recipes list
phantom recipes run focus_mode
```

The v0.1 daemon emits `app_switch`, `content_match`, `schedule`, and `idle` trigger events.
`focus_mode` is manual in v0.1.

## Stop

```bash
phantom stop
```

The live Unix control channel is authoritative for process identity. `phantom stop` signals only the positive integer PID returned by the answering daemon; it does not trust a stale PID file by itself. If no live daemon responds, stale PID/socket markers are cleaned instead of signalling an unrelated process.

## Validate locally without GitHub Actions minutes

```bash
make verify
```

That reproduces the core compile, Ruff lint/format, mypy, 95% coverage, benchmark-smoke, Bandit, `pip-audit`, build, and clean-wheel checks for the current Python interpreter. Before a public release, repeat on Python 3.10-3.13 and run a controlled macOS Accessibility/Screen Recording/AppleScript smoke test.
