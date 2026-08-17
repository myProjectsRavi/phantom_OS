## Summary

- Describe what this PR changes.
- Link related issue(s) if applicable.

## Changes

- [ ] Code changes
- [ ] Tests added/updated
- [ ] Documentation updated

## Validation

List commands run and outcomes.

```bash
pytest -q
python -m ruff check src tests scripts benchmarks
python -m ruff format --check src tests scripts benchmarks
python -m mypy --ignore-missing-imports src/phantom
```

## Security and privacy

- [ ] No API keys, tokens, passwords, private keys, credentials, or real secrets are included.
- [ ] No personal information, confidential employer/customer material, private third-party architecture, or proprietary datasets are included.
- [ ] Logs, screenshots, fixtures, paths, and examples are sanitized.
- [ ] New local secret/state files are covered by `.gitignore` and `.dockerignore` where applicable.
- [ ] GitHub Actions are pinned to reviewed immutable commit SHAs.

## Risk Assessment

- Backward compatibility impact:
- Operational/security impact:

## Release Notes

Include any user-facing notes for `CHANGELOG.md`.
