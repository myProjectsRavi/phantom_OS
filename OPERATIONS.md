# PhantomOS Operations Runbook

This runbook covers the supported v0.1 local macOS daemon.

## Start

```bash
phantom start
```

The daemon runs in the foreground. Use a second terminal for control commands. A per-user file lock prevents a second PhantomOS daemon from taking over the active control socket.

## Health and state

```bash
phantom status
phantom stats
phantom doctor
```

`status` and `stats` query the active daemon through the per-user Unix-domain control socket rather than constructing a new agent.

## Inspect perception and decisions

```bash
phantom perceive
phantom intent
phantom predictions
```

## Trust policy

```bash
phantom trust suggest_only
phantom trust approve_each
phantom trust approve_new
phantom trust auto_execute
```

The selected trust level is applied to the running daemon and persisted into `~/.phantom/config.toml`.

Recommended normal setting:

```bash
phantom trust approve_new
```

For high-sensitivity work:

```bash
phantom trust approve_each
```

`approve_new` learns an exact action only after five explicit approvals. Cross-process learning is stored as SHA-256 action-signature digests and counters in `~/.phantom/approvals.json`; raw typed text, URLs, commands, and action parameters are not persisted there.

## Emergency response

### Stop all future actions without terminating the daemon

```bash
phantom emergency-stop
```

Confirm:

```bash
phantom status
```

The status field `emergency_stopped` should be `True`.

Blocking native dispatch runs outside the daemon asyncio event loop, so the control socket remains responsive while an already-authorized native operation is in flight. Emergency stop prevents subsequent actions; it does not claim to cancel a native operation already handed to the OS.

### Resume after investigation

```bash
phantom resume-actions
```

### Terminate the daemon

```bash
phantom stop
```

`phantom stop` treats the live control socket response as the process-identity authority. It signals only the positive integer PID returned by that live daemon, repairing a stale/missing PID marker to match. If no live control response exists, it cleans stale PID/socket state and does not signal an arbitrary PID.

If the process must be terminated outside PhantomOS, use normal operating-system process tools. Avoid `kill -9` unless graceful termination is impossible because it prevents normal shutdown persistence/cleanup.

## Undo

```bash
phantom undo
```

Undo is available only when the last action contains undo metadata. Undo actions re-enter the same safety/approval path as normal actions.

## Clipboard history

```bash
phantom clipboard
```

The command reads the clipboard history owned by the running daemon process.

## Recipe operation

List recipes:

```bash
phantom recipes list
```

Run a recipe manually:

```bash
phantom recipes run focus_mode
```

Manual recipe execution uses an interactive approval callback. Background recipe execution has no implicit approval and is denied when the active trust mode requires approval unless the exact action has already graduated under `approve_new`.

## Runtime files

Default local state:

```text
~/.phantom/config.toml
~/.phantom/approvals.json
~/.phantom/phantom.pid
~/.phantom/phantom.lock
~/.phantom/phantom.sock
~/.phantom/patterns.json
~/.phantom/phantom.log
~/.phantom/recipes/*.toml
```

`~/.phantom`, recipe, and log directories are owner-only. Config, approval, PID, lock, and socket state are mode `0600` where applicable.

## Backup

PhantomOS has no server database. Back up the local state directory only when you intentionally want to preserve local recipes/configuration/patterns/trust state:

```bash
cp -R ~/.phantom ~/.phantom-backup
```

Be aware that this directory can contain local workflow metadata, provider configuration, persisted action-signature hashes, and clipboard-derived recipe state. Protect backups with the same care as the source profile.

## Recovery

1. Try graceful stop:

```bash
phantom stop
```

2. Restore only known-good configuration/recipe/pattern files.
3. If you have independently confirmed no daemon is running, remove stale process-control files:

```bash
rm -f ~/.phantom/phantom.pid ~/.phantom/phantom.sock ~/.phantom/phantom.lock
```

Do not delete `approvals.json` unless you intentionally want to reset learned `approve_new` trust.

4. Validate configuration:

```bash
phantom doctor
```

5. Restart:

```bash
phantom start
```

## Circuit breaker

Three consecutive native action failures set the action policy to stopped mode.
Investigate the underlying accessibility/app/process failure before running:

```bash
phantom resume-actions
```

## Logs

The current agent logging path uses a rotating file handler next to the configured pattern store. With defaults:

```text
~/.phantom/phantom.log
```

Rotation is bounded by the runtime handler; no separate `/var/log/phantom` deployment is assumed.

## Zero-cost local release validation

GitHub-hosted runners are not required to reproduce the core release gates. On a trusted local checkout with development dependencies installed:

```bash
make verify
```

That runs compile, Ruff lint/format check, mypy, the 95% coverage suite, benchmark smoke, Bandit, `pip-audit`, build, and clean-wheel smoke for the current interpreter. Repeat it under Python 3.10, 3.11, 3.12, and 3.13 for the supported interpreter matrix. macOS desktop releases also require a controlled real-device Accessibility/Screen Recording/AppleScript smoke test.

## Incident checklist

For a runaway or unexpected automation:

1. `phantom emergency-stop`
2. `phantom status`
3. capture the relevant `~/.phantom/phantom.log` section
4. inspect the recipe/config that produced the action
5. reduce trust to `approve_each` or `suggest_only`
6. reproduce only in a controlled test environment
7. report security-sensitive behavior privately per [SECURITY.md](SECURITY.md)

## Unsupported operational assumptions

The v0.1 CLI does **not** claim built-in:

- launchd/systemd installation
- REST health endpoints
- remote action API
- log export service
- email/Slack emergency notifications
- automatic permission granting
- native hotkey emergency listener

Keeping these out of the runbook is intentional until they exist and are tested.
