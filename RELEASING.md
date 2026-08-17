# PhantomOS Release Process

PhantomOS releases are cut only from a reviewed commit whose required release gates have passed. Validation evidence must correspond to the exact commit being tagged.

## 1. Verify the candidate commit

Require the candidate to pass the release contract on Python 3.10-3.13:

- compile check;
- unit/security tests with the 95% coverage gate;
- Ruff lint and format check;
- mypy;
- benchmark harness smoke;
- Bandit;
- `pip-audit`;
- clean wheel build/install smoke.

The repository CI runs the automated gates. The same core gates can also be reproduced on a trusted checkout:

```bash
make verify
```

`make verify` covers the current interpreter. Repeat it under Python 3.10, 3.11, 3.12, and 3.13 before claiming the full supported Python matrix.

For the supported macOS desktop path, also run a controlled real-device smoke test covering Screen Recording/perception, Accessibility/AppleScript action execution, emergency-stop responsiveness, and graceful daemon shutdown.

Do not lower, bypass, or mark a required gate optional merely to make a release candidate pass. Record the environment and exact commit for release evidence.

## 2. Review the public contract

Before tagging, verify:

- README and Docs describe only supported behavior;
- `pyproject.toml` version and support classifiers are correct;
- no placeholder repository URLs or owners remain;
- no credentials, private keys, personal data, local state, internal artifacts, or confidential material are present;
- benchmark claims are accompanied by reproducible methodology/results;
- `CHANGELOG.md` describes user-visible and security-relevant changes;
- GitHub Actions dependencies remain pinned to reviewed immutable commits.

## 3. Create a signed annotated tag

From a trusted maintainer workstation with Git signing configured:

```bash
git switch main
git pull --ff-only
git tag -s v0.1.0 -m "PhantomOS v0.1.0"
git tag -v v0.1.0
git push origin v0.1.0
```

Do not create release tags from an unreviewed or dirty working tree.

## 4. Release provenance workflow

A `v*` tag triggers `.github/workflows/release-provenance.yml`. The workflow:

1. runs release verification;
2. builds wheel and source distributions;
3. writes `dist/SHA256SUMS`;
4. generates GitHub artifact attestations when supported; and
5. uploads the release build artifacts.

All referenced GitHub Actions are pinned to immutable commit SHAs. Review and deliberately update those pins when adopting a newer upstream release.

## 5. Verify artifacts

Compare downloaded distribution hashes against `SHA256SUMS` before publication. Verify GitHub artifact attestations with GitHub's attestation verification tooling when available.

## 6. Publish release notes

Release notes should state:

- exact version and commit;
- supported OS/Python versions;
- safety model changes;
- known alpha limitations;
- validation environments used;
- reproducible benchmark environment/results where performance is discussed;
- migration/configuration notes when behavior changes.

Never include secrets, raw private logs, local filesystem paths containing personal identifiers, or confidential incident details in release notes.

## 7. Post-release verification

Install the published artifact into a new clean virtual environment and verify at minimum:

```bash
phantom --help
phantom init
phantom doctor
```

For a desktop release, also run a controlled macOS smoke test for perception, a benign explicitly approved action, emergency stop, and daemon shutdown.
