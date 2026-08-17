# PhantomOS Troubleshooting

This guide covers the supported v0.1 macOS runtime.

## `phantom status` says the daemon is unavailable

Start PhantomOS in another terminal:

```bash
phantom start
```

The daemon must keep running in that terminal. It creates local process-control state including:

```text
~/.phantom/phantom.pid
~/.phantom/phantom.lock
~/.phantom/phantom.sock
```

A per-user lock prevents a second PhantomOS daemon from replacing the active control socket.

If no daemon is running but stale process-control files remain, remove them only after independently confirming there is no active PhantomOS process:

```bash
rm -f ~/.phantom/phantom.pid ~/.phantom/phantom.sock ~/.phantom/phantom.lock
```

Then start again.

## `phantom stop` does not signal a stale PID

This is intentional. `phantom stop` asks the **live local control socket** for the daemon PID and treats that response as authoritative. It does not trust a PID file by itself.

If the control socket cannot answer, PhantomOS cleans stale PID/socket markers rather than signalling a process that may have reused an old PID.

If the socket answers with a valid daemon PID, the CLI repairs the PID marker to that live identity and signals only that process.

## Actions are rejected with `Rejected by user`

Check the current trust policy:

```bash
phantom status
```

`approve_each` always requires explicit approval. `approve_new` requires approval for an exact action until that exact canonical action has been approved five times.

Cross-process `approve_new` learning is stored in `~/.phantom/approvals.json` using SHA-256 signature digests and counters only. Raw typed text, URLs, commands, and parameters are not stored there.

For interactive manual recipe execution, use:

```bash
phantom recipes run <name>
```

which provides a terminal approval prompt.

`PHANTOM_AUTO_APPROVE=true` is for controlled development/testing only and should not be a normal runtime configuration.

If `approvals.json` is malformed or unreadable, PhantomOS fails closed and requires approval again.

## Actions are blocked by safety

Common reasons:

- `suggest_only` trust mode
- emergency stop/circuit breaker active
- blocked application or sensitive app-name variant
- blocked filesystem root
- blocked command executable/resource/option grammar
- blocked configured domain
- action-rate limit reached

Inspect:

```bash
phantom status
```

After resolving the underlying issue, an emergency/circuit stop can be resumed with:

```bash
phantom resume-actions
```

## Generic `RUN_COMMAND` is rejected

The generic command surface is deliberately small. v0.1 authorizes only:

```text
echo date pwd ls open killall
```

`open`, `killall`, and `ls` also have fail-closed argument grammars and resource checks. For example:

- `open` accepts HTTP/HTTPS or non-sensitive paths and a small app-launch option subset;
- `killall` accepts literal process names, not regex/user/signal selector options;
- `ls` rejects recursive/unknown option forms and sensitive filesystem targets.

`screencapture` and `tesseract` are not exposed as generic recipe commands.

## Emergency stop

Stop future action execution in the running daemon:

```bash
phantom emergency-stop
```

This command communicates with the active daemon over `~/.phantom/phantom.sock`; it does not construct a separate agent.

Blocking native dispatch runs outside the daemon event loop so the control channel remains responsive while an already-authorized native operation is in flight. Emergency stop blocks subsequent actions; it does not claim to cancel an OS operation that is already running.

## Accessibility or automation errors

On macOS, grant Accessibility/Automation permission to the terminal application or Python executable running PhantomOS.

If AppleScript/native commands return non-zero exit codes, PhantomOS records them as action failures. Three consecutive failures trip the circuit breaker.

## Screen perception is empty

Check:

1. Screen Recording permission is granted.
2. PhantomOS is running in a real desktop session.
3. `phantom doctor` reports a valid Python/runtime setup.
4. optional OCR dependencies are installed if you expect OCR text.

Docker is not a supported desktop-perception environment.

## OCR is unavailable

OCR is optional. Install the Python extra and native Tesseract package appropriate for macOS, then verify with:

```bash
phantom doctor
```

Core rule-based operation does not require OCR.

## No LLM is detected

LLM support is optional.

```bash
phantom models
```

If no provider is available, PhantomOS remains in rule-based mode.

For Ollama, ensure the configured host is reachable and the desired local model is installed.

## A recipe condition fails

Condition errors fail closed. PhantomOS returns a recipe failure rather than executing the guarded action.

Check the expression against the supported restricted syntax documented in [Docs/recipes.md](Docs/recipes.md).

## `error_auto_search` searches the wrong value

The current runner updates `{clipboard}` immediately after a successful `clipboard_copy`. If you see stale behavior, capture the recipe result and open a bug report with the exact commit and reproduction steps.

## Python 3.10 configuration issues

Python 3.10 uses the declared `tomli` dependency. A normal wheel/source install includes it automatically.

Configuration parse errors are not silently replaced by defaults. Fix malformed TOML and rerun:

```bash
phantom doctor
```

## Local validation without GitHub Actions minutes

Install the development dependencies in a local virtual environment and run:

```bash
make verify
```

This reproduces the core compile/lint/format/type/95%-coverage/benchmark/security/build/wheel checks for the current Python interpreter without consuming GitHub-hosted runner minutes. Repeat under Python 3.10-3.13 before a release.

## Linux

Linux adapters exist as experimental source code, but Linux desktop automation is not a supported v0.1 runtime. Do not treat successful import/unit tests as a Linux product-support guarantee.

## Docker

`docker-compose.yml` runs a one-shot package/configuration smoke check only. It intentionally exposes no port and no REST health endpoint.

## Security issues

Do not publish vulnerability details in a public issue. Follow [SECURITY.md](SECURITY.md) for private coordinated reporting.
