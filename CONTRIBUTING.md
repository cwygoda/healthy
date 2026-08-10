# Contributing

This project is a small Python CLI using a hexagonal architecture style. Keep changes focused, tested, and usage-oriented.

## Setup

```bash
uv sync
uv run healthy --help
```

Install the command wrapper for manual testing from anywhere:

```bash
./install.sh
healthy --help
```

## Run tests

```bash
uv run python -m unittest discover -s tests
```

Before committing, run the full test command above.

## Project layout

```text
src/healthy/domain.py          # domain models and domain errors
src/healthy/application.py     # use cases
src/healthy/ports.py           # application ports/protocols
src/healthy/adapters/          # Garmin, storage, launchd, notification adapters
src/healthy/cli.py             # Typer CLI adapter
tests/                         # fast unit tests
notes/                         # design notes and implementation plans
```

## Architecture guidelines

- Keep domain/application logic independent from Typer, launchd, filesystem details, subprocesses, and Garmin SDK details.
- Put IO and framework code in adapters.
- Prefer small use cases and plain dataclasses for decision logic.
- Add tests around application logic first; adapter tests should avoid live network and irreversible OS changes.
- Do not prompt for credentials or MFA from background auto-run paths.

## CLI guidelines

- User-facing commands should be safe by default.
- Background commands should log details and show concise result notifications only.
- Keep README examples runnable by a user who installed with `./install.sh`.
- Use `uv run healthy ...` only when documenting local development.

## Auto-run development notes

The macOS auto-run feature uses a user LaunchAgent.

Important files:

```text
src/healthy/autorun.py
src/healthy/adapters/launchd.py
src/healthy/adapters/notifications.py
notes/run-on-wake.md
```

Manual test loop:

```bash
uv run healthy autorun tick --dry-run --sleep-threshold-minutes 1 --network-timeout-minutes 0
```

Install/uninstall loop:

```bash
./install.sh
healthy autorun uninstall
healthy autorun install --sleep-threshold-minutes 30 --network-timeout-minutes 10
healthy autorun status
```

## Commit style

Use Conventional Commits:

```text
feat: add wake-triggered autorun
fix: handle expired Garmin tokens in background sync
docs: clarify autorun setup
```

Keep commit messages concise and human-authored. Do not add AI/agent attribution lines.

## Agent instructions

When acting as a coding agent:

1. Read this file and relevant source/tests before editing.
2. Preserve the architecture boundaries above.
3. Prefer exact, minimal edits.
4. Run `uv run python -m unittest discover -s tests` before reporting success.
5. Do not run install/uninstall commands or modify LaunchAgents unless explicitly asked.
6. Do not use live Garmin credentials or prompt for secrets in automated/background paths.
