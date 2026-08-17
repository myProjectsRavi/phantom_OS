<div align="center">

# PhantomOS
### Local-first desktop automation runtime with explicit safety controls

![Python](https://img.shields.io/badge/Python-3.10--3.13-blue)
[![CI](https://github.com/myProjectsRavi/phantom_OS/actions/workflows/ci.yml/badge.svg)](https://github.com/myProjectsRavi/phantom_OS/actions/workflows/ci.yml)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-v0.1%20Alpha-orange)

PhantomOS observes local desktop context, learns repeated behavior, predicts likely next actions,
and executes explicitly authorized automations on the user's machine.

</div>

---

## Status and support contract

PhantomOS v0.1 is **alpha software**.

**Supported for v0.1:**

- macOS desktop automation
- Python 3.10, 3.11, 3.12, and 3.13
- local foreground daemon
- per-user local control socket at `~/.phantom/phantom.sock`
- rule-based perception, intent, prediction, triggers, and recipes
- optional local LLM providers through Ollama or an OpenAI-compatible local endpoint

**Not a v0.1 support claim:**

- Linux desktop automation (platform adapters are experimental and not the supported executor path)
- REST/remote-control API
- cloud-hosted PhantomOS service
- containerized desktop automation

The narrow support contract is intentional: public documentation describes only behavior supported by the runtime and release contract.

## What PhantomOS does

PhantomOS follows a local perception-to-action loop:

1. **Perceive** active app/window/OCR/UI signals.
2. **Interpret** current intent using deterministic rules and local context.
3. **Learn** repeated action signatures.
4. **Predict** likely next actions.
5. **Trigger** matching local recipes.
6. **Authorize** every side effect through one safety policy.
7. **Act** through local OS automation primitives.

Core capabilities are separated into dedicated modules for perception, intent, patterns, prediction,
actions, automation, safety, local LLM providers, and explicitly optional integrations.

## Safety model

All side effects are required to enter through `ActionExecutor.execute()`.
Nested sequence steps and undo operations re-enter the same safety boundary instead of dispatching directly.

### Trust levels

| Trust level | Runtime behavior |
| --- | --- |
| `suggest_only` | Execution is blocked. |
| `approve_each` | Every action requires explicit approval. |
| `approve_new` | Exact new actions require approval; five approvals establish trust for that exact action signature. |
| `auto_execute` | Approval prompts are skipped, but unconditional blocklists, rate limits, circuit breaker, and emergency stop still apply. |

Background daemon automation has no implicit approval callback. If a trust mode requires approval and no explicit approval channel is present, the action is denied by default. `PHANTOM_AUTO_APPROVE=true` exists only for controlled development/testing.

`approve_new` learning is shared safely across CLI and daemon processes through `~/.phantom/approvals.json`. PhantomOS stores only SHA-256 digests of exact canonical action signatures and approval counters—not typed text, URLs, command contents, or raw action parameters. Corrupt trust state fails closed.

Additional safeguards include:

- Unicode-normalized, case-insensitive sensitive application blocklist, including modern macOS `System Settings` and helper-name variants
- sensitive filesystem path blocklist with normalized path checks
- dangerous command-pattern blocklist
- deliberately narrow generic command set: `echo`, `date`, `pwd`, `ls`, `open`, and `killall`
- resource-level authorization for `ls`, `open`, and `killall`, including fail-closed native option grammars
- HTTP/HTTPS-only URL targets through generic `open`
- rolling action-rate limit
- circuit breaker after repeated native action failures
- per-user daemon singleton lock
- owner-only control/config/trust/PID/lock state
- daemon control responsiveness while blocking native work runs off the asyncio event loop

See [Docs/safety.md](Docs/safety.md).

## Local daemon control

`phantom start` runs the daemon in the foreground. A second terminal communicates with that same process through a per-user Unix-domain socket created with mode `0600`.

This means commands such as `status`, `trust`, `stats`, `undo`, clipboard history, and emergency stop operate on the running daemon rather than constructing a shadow agent.

```bash
phantom start
```

In another terminal:

```bash
phantom status
phantom perceive
phantom intent
phantom predictions
phantom stats
phantom trust approve_each
phantom emergency-stop
phantom resume-actions
phantom undo
phantom stop
```

A per-user file lock prevents a second PhantomOS daemon from replacing the active daemon's control socket.

## Installation from source

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

For a minimal runtime install from a source checkout:

```bash
pip install .
```

The Python distribution name is `rtnlabs-phantomos`; the import package and CLI remain `phantom`.

### macOS requirements

- grant Screen Recording permission when using perception capture
- grant Accessibility/Automation permissions for the terminal or Python executable that runs PhantomOS
- optional: install Tesseract and `rtnlabs-phantomos[ocr]` for OCR

## LLM support

LLMs are optional. Rule-based operation remains available when no provider is reachable.

Supported provider adapters:

- Ollama
- OpenAI-compatible local endpoints such as LM Studio, vLLM, or llama.cpp server

Example:

```toml
[llm]
provider = "openai_compat"
base_url = "http://localhost:1234"
model = "auto"
```

The v0.1 daemon remains rule-first. Optional local-LLM helper methods for intent disambiguation, recipe generation, and action suggestion are library capabilities; they do not bypass `ActionExecutor` authorization and are not presented as an autonomous daemon decision loop.

## Optional memory integration

The core runtime has no external memory-service requirement. A separately installable NeuroVault integration is available for Python 3.11+:

```bash
pip install 'rtnlabs-phantomos[memory]'
```

Optional integration bridges are disabled by default. The base `rtnlabs-phantomos` distribution remains self-contained apart from the explicitly configured local LLM endpoint and native macOS facilities it uses.

## Recipes

PhantomOS ships with three built-ins:

| Recipe | Trigger | Purpose |
| --- | --- | --- |
| `morning_opener` | Weekday schedule at 09:00 | Open a startup work context. |
| `error_auto_search` | Terminal content match | Copy the current error and search it. |
| `focus_mode` | Manual in v0.1 | Close Slack/Discord and show a notification. |

Manual recipe execution uses an interactive approval callback:

```bash
phantom recipes list
phantom recipes run focus_mode
```

Daemon-supported trigger sources in v0.1 are `app_switch`, `content_match`, `schedule`, and `idle`.
The trigger engine also has programmatic evaluators for `hotkey` and `pattern_match`, but the v0.1 daemon does not claim native event sources for them.

See [Docs/recipes.md](Docs/recipes.md).

## Docker

Desktop automation requires host OS accessibility APIs and a real desktop session.

`Dockerfile` and `docker-compose.yml` are therefore **package/configuration smoke tools only**. They are not a supported production deployment and expose no PhantomOS REST service.

```bash
docker compose up --build --abort-on-container-exit
```

## Development and verification

The release CI is configured for Python 3.10-3.13 and includes compile, lint, formatting, type checking,
a 95% coverage gate, wheel-installation smoke tests, benchmark-harness smoke, Bandit SAST, and `pip-audit` dependency auditing. Public-repo security automation also includes CodeQL and dependency review.

Run the complete local gate for the current interpreter:

```bash
make verify
```

That target also runs the offline public-snapshot hygiene check in `scripts/check_public_snapshot.py`.
Repeat `make verify` on Python 3.10, 3.11, 3.12, and 3.13 before claiming the full interpreter matrix.

Run real microbenchmarks:

```bash
pytest benchmarks -q --benchmark-only --no-cov
```

The benchmark suite measures the current safety-policy, trigger-matching, intent-recognition, and sequence-inspection paths. It intentionally avoids publishing performance claims without reproducible measurements.

## Repository layout

```text
phantom_OS/
├─ src/phantom/
│  ├─ actions/
│  ├─ automation/
│  ├─ integrations/
│  ├─ intent/
│  ├─ llm/
│  ├─ patterns/
│  ├─ perception/
│  ├─ prediction/
│  └─ safety/
├─ tests/
│  ├─ security/
│  └─ unit/
├─ benchmarks/
├─ scripts/
└─ Docs/
```

## Documentation

- [Quickstart](Docs/quickstart.md)
- [Safety model](Docs/safety.md)
- [Recipes](Docs/recipes.md)
- [Deployment/support boundaries](DEPLOYMENT.md)
- [Operations runbook](OPERATIONS.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)

## Security reporting

Do not open a public issue for a vulnerability. Follow [SECURITY.md](SECURITY.md) for private reporting and coordinated disclosure.

## License

MIT. See [LICENSE](LICENSE).
