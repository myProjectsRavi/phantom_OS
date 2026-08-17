# PhantomOS Safety Model

PhantomOS treats OS side effects as a single security boundary. Every supported action must enter through `phantom.actions.executor.ActionExecutor.execute()` before reaching a native adapter.

## Trust levels

| Level | Behavior |
| --- | --- |
| `suggest_only` | Blocks execution. |
| `approve_each` | Every action requires explicit approval. |
| `approve_new` | Exact new action signatures require approval; five approvals establish trust for that exact signature. |
| `auto_execute` | Skips trust prompts while preserving unconditional safety checks. |

The trust level itself determines whether approval is required. Callers do not opt out by forgetting to set a per-request flag.

An explicit `requires_approval=true` request remains approval-gated even under `auto_execute`.

## Approval behavior

Approval is deny-by-default when required.

Approval can come from:

- an explicit callback supplied by an interactive embedding application; or
- `PHANTOM_AUTO_APPROVE=true` for controlled development/testing only.

The background daemon has no implicit self-approval callback.

### Privacy-preserving `approve_new` learning

`approve_new` trust must work across the interactive CLI process and the long-running daemon, so learned exact-action trust is persisted locally in `~/.phantom/approvals.json`.

The store does **not** persist typed text, URLs, command contents, or raw action parameters. PhantomOS canonicalizes the exact action signature and stores only its SHA-256 digest plus an approval counter. The store is written atomically, the file is mode `0600`, and its parent directory is restricted to the current user.

The daemon reloads the store when it changes, so an exact action can graduate into trusted execution without restarting the daemon or switching the whole system to `auto_execute`.

Malformed or unreadable approval state fails closed: no action becomes trusted because a trust file is corrupt.

Tests isolate the approval store with `PHANTOM_APPROVAL_STORE` so development/test runs never mutate a user's real trust state.

## Blocklists and normalization

The safety policy rejects:

- sensitive applications such as 1Password, Keychain Access, System Settings/System Preferences, and Disk Utility;
- helper/name variants of sensitive applications after Unicode normalization and case folding;
- sensitive filesystem roots such as `~/.ssh`, `~/.aws`, `~/.gnupg`, `/etc`, and `/System`;
- dangerous command patterns such as `sudo`, `rm -rf`, `mkfs`, and pipe-to-shell forms;
- configured sensitive domains.

Filesystem targets are expanded and resolved before comparison so traversal forms such as `../../etc/...` cannot bypass a root blocklist.

## Generic command execution

`RUN_COMMAND` is deliberately narrow. Authorization and dispatch share one executable allowlist:

- `echo`
- `date`
- `pwd`
- `ls`
- `open`
- `killall`

Unknown executables are denied by policy before approval.

The allowlist is not sufficient by itself: PhantomOS authorizes command **resources and grammar** as well.

### `open`

Only a small explicit subset is accepted:

- direct HTTP/HTTPS URL or non-sensitive filesystem targets;
- `-a <literal app name>`;
- `-n` and `-g` modifiers.

Sensitive app names and `.app` paths are blocked. Bundle-ID launch (`-b`), `--args`, unknown options, `file://`, FTP, and other URL schemes fail closed.

### `killall`

Only literal process-name operands are accepted. Selector, signal, user, and regular-expression options are rejected. This prevents native option semantics from broadening an apparently literal request into a different process target.

### `ls`

Only common non-recursive display flags are accepted, and every path operand is normalized through the sensitive-path policy. Recursive/unknown option forms fail closed.

Tools such as `screencapture` and `tesseract` are not exposed through generic recipe command execution; internal perception tooling should not become a general filesystem-capable action surface.

## Sequence and undo safety

Nested sequence children re-enter `ActionExecutor.execute()` individually.

Undo metadata is also executed through the normal safety/approval path.

Direct `_dispatch()` is only for requests that have already passed authorization and is not the public action boundary.

## Rate limiting

Default limit: 10 allowed actions per rolling 60 seconds.

Requests rejected by unconditional blocklists do not consume the allowed-action budget.

## Circuit breaker

Three consecutive action failures stop subsequent action execution until actions are explicitly resumed.

Native non-zero process/AppleScript exits are represented as failures rather than successful actions, so the circuit breaker receives real adapter outcomes.

## Emergency stop and control responsiveness

The running daemon exposes emergency stop over its per-user Unix-domain control socket:

```bash
phantom emergency-stop
```

Resume explicitly with:

```bash
phantom resume-actions
```

The socket is created under `~/.phantom/phantom.sock` with mode `0600` and is not a network listener.

Blocking native adapters execute off the daemon's asyncio event loop. This keeps the control socket responsive while an already-authorized native action is in flight; emergency stop can latch immediately and blocks subsequent actions rather than waiting for a long subprocess/AppleScript call to return.

A per-user `flock`-based daemon lock prevents a second PhantomOS daemon from unlinking/replacing the first daemon's control socket. Lock and PID state files are mode `0600`.

## Local state permissions

`config.toml` may contain a local LLM API key, so existing configuration is tightened to mode `0600` when loaded. Trust, PID, lock, and control-socket state are also owner-only.

## Recommended configuration

```toml
[phantom]
trust_level = "approve_new"
max_actions_per_minute = 10

[privacy]
capture_retention = 0
excluded_apps = ["1Password", "Keychain Access"]
blocked_domains = ["bank", "medical"]
```

For high-sensitivity environments use `suggest_only` or `approve_each`.

## Security test expectations

Release validation exercises the live executor for:

- trust enforcement and deny-by-default approval;
- cross-process exact-action trust persistence without raw-action storage;
- sequence-child and undo authorization;
- alternate command-target and native-option bypass attempts;
- filesystem traversal and sensitive-resource aliases;
- circuit-breaker behavior;
- explicit approval under `auto_execute`;
- sensitive URL/application/path blocks;
- daemon singleton locking;
- emergency-control responsiveness while native work is in flight.

Security findings should be reported privately according to [../SECURITY.md](../SECURITY.md).
