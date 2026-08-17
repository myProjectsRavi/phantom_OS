# Contributing to PhantomOS

Thanks for contributing.

## Code of Conduct

All participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Supported development baseline

- Python 3.10-3.13
- Git
- macOS for supported desktop-integration behavior

Linux adapter contributions are welcome, but Linux is not a v0.1 support claim until the real executor path and integration tests prove it.

## Clone and setup

```bash
git clone https://github.com/myProjectsRavi/phantomOS.git
cd phantomOS
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
```

## Required local checks

```bash
make verify
```

For targeted iteration, the component checks are also available individually through the Makefile.

## Public repository safety

Never commit or paste into an issue or pull request:

- API keys, tokens, passwords, credentials, private keys, certificates, or real secret values;
- personal information that is not intentionally public;
- confidential employer/customer material;
- private architecture or design material from another project;
- proprietary datasets or third-party content you are not licensed to redistribute;
- raw logs, screenshots, local database files, backups, dumps, or local paths that expose sensitive information.

Use synthetic fixtures and placeholders that do not resemble real credentials. Check `.gitignore` and `.dockerignore` before introducing new local state or tooling. Security vulnerabilities must be reported privately via [SECURITY.md](SECURITY.md).

## Safety invariant for action changes

All supported OS side effects must enter through `ActionExecutor.execute()`.

Do not call `_dispatch()` directly from new public/action-producing code. Sequence children, undo operations, recipe actions, future integrations, and model-generated actions must preserve the same centralized authorization boundary.

Any action/security change should add a regression test demonstrating the intended allow/deny behavior.

## Documentation contract

User-facing behavior changes must update the matching documentation in the same PR.

Do not document commands, config keys, platforms, services, or APIs that do not exist in the tested runtime.

## Pull requests

- keep changes scoped;
- explain the user/developer impact;
- include tests for behavior changes;
- keep CI green on every supported Python version;
- avoid lowering security or coverage gates to make a PR pass;
- update benchmark methodology when making performance claims;
- keep GitHub Actions pinned to reviewed immutable commit SHAs.

## Reporting bugs

Use the repository issue tracker and include:

- exact commit/version;
- Python version;
- macOS version for desktop behavior;
- reproduction steps with sanitized inputs;
- expected vs actual behavior;
- only relevant redacted logs.

## Security

Do not file public issues for vulnerabilities. Use the private reporting path in [SECURITY.md](SECURITY.md).

## License

By contributing, you agree your contributions are licensed under [MIT](LICENSE).
