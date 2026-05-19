# AURORA Release Checklist

Use this checklist before publishing a GitHub release.

## Pre-Release

- Start from a fresh clone.
- Create and activate a virtual environment.
- Install dependencies with `pip install -r requirements.txt`.
- Install the package locally with `pip install -e .`.
- Run `python3 -m pytest`.
- Run `PYTHONPATH=src python3 -m aurora.cli.app reports status --latest-test-count 293`.
- For v2 local workflow checks, run `PYTHONPATH=src python3 -m aurora.cli.app demo run --output-root data/demo --latest-test-count 293`.
- Run `PYTHONPATH=src python3 -m aurora.cli.app reports safety-audit --no-fail-on-critical`.
- Inspect `git diff`.
- Confirm no real secrets or API keys are present.
- Confirm local data artifacts are not committed.
- Confirm README commands match the CLI.
- Confirm example strategy configs validate.

## Release

- Commit release documentation and final checks.
- Tag the release.
- Push the branch and tag.
- Create the GitHub release.
- Attach or paste `RELEASE_NOTES.md`.

## Post-Release

- Open issues for v1.1/v2 improvements.
- Keep future broker/API work explicitly paper-trading-first.
- Do not add live trading without a separate safety design and review process.
