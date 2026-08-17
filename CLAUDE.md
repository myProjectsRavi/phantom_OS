# CLAUDE.md

Project: PHANTOMOS

## Tests
- `python -m pytest` (use `.venv/bin/python -m pytest` if a local venv is present)

## Quality bar
- Keep public APIs backward compatible unless explicitly versioned.
- Add or update tests for behavior changes.
- Preserve type hints and docstrings when editing core modules.

## Notes
- Prefer deterministic tests (no network, no real LLM calls).
- Update README/Docs when user-visible behavior changes.
