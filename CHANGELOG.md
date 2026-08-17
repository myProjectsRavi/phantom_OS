# Changelog

All notable public changes to PhantomOS are documented here.

## 0.1.0 - 2026-08-16

### Added

- Local-first macOS desktop automation runtime for Python 3.10-3.13.
- Perception, deterministic intent recognition, pattern learning, prediction, triggers, and recipes.
- Optional local LLM adapters for Ollama and OpenAI-compatible local endpoints.
- Foreground daemon with per-user Unix-domain control socket.
- CLI controls for status, trust, perception, intent, predictions, statistics, clipboard history, undo, emergency stop, resume, and graceful shutdown.
- Reproducible microbenchmark harness and package/wheel smoke validation.
- CI matrix, CodeQL analysis, dependency review, Bandit SAST, and dependency vulnerability auditing.
- Tagged release build, SHA-256 checksum, and GitHub artifact-attestation workflow.

### Safety

- Centralized authorization for every supported side effect, including nested sequences and undo operations.
- Four explicit trust modes: `suggest_only`, `approve_each`, `approve_new`, and `auto_execute`.
- Persistent `approve_new` learning using SHA-256 exact-action signatures and counters without storing raw action parameters in the trust store.
- Sensitive application, filesystem, command, and domain protections with normalized comparisons.
- Deliberately narrow generic command surface: `echo`, `date`, `pwd`, `ls`, `open`, and `killall`.
- Fail-closed recipe conditions, native failure propagation, rolling rate limits, circuit breaker, and emergency stop.
- Owner-only local configuration, approval, process-control, and socket state where applicable.
- Per-user daemon singleton lock and live control-channel process identity for graceful stop.

### Security and release hygiene

- MIT-licensed public package metadata with real repository URLs.
- No remote-control REST service or cloud-hosted execution surface in v0.1.
- GitHub Actions dependencies pinned to immutable upstream commit SHAs.
- Public contribution and vulnerability-reporting policies designed to avoid disclosure of secrets or private data.
