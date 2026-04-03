# pm-latency

Incremental build for short-horizon Polymarket CLOB tooling (latency / stale-quote strategy). Work is tracked in GitHub issues on this repo (Phase 1: [#3](https://github.com/bhargavap21/test/issues/3)).

## Requirements

- Python 3.11+

## Install (editable)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Configuration

Copy `.env.example` to `.env` and adjust. Never commit `.env` or private keys.

## Run modes

- **Paper / dry run (default):** `DRY_RUN=1` in `.env`, or pass `--dry-run`.
- **Live (later phases):** set `DRY_RUN=0` and pass `--live` once execution is implemented and funded.

## CLI

```bash
pm-runner --help
# or
python -m pm_latency.ops.runner --help
```

Phase 1 only prints the resolved mode; the market loop arrives in later phases.

## Tests

```bash
pytest
ruff check pm_latency tests
```
