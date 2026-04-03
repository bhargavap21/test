# pm-latency

Incremental build for short-horizon Polymarket CLOB tooling (latency / stale-quote strategy). Tracked in GitHub issues (Phase 1: [#3](https://github.com/bhargavap21/test/issues/3), Phase 2: [#5](https://github.com/bhargavap21/test/issues/5)).

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

Default command prints the resolved `DRY_RUN` mode (stub until the live loop exists).

### Discover short BTC/ETH Up/Down markets (Phase 2)

Probes Polymarket Gamma for `btc|eth-updown-5m|15m-<epoch>` slugs around the current UTC window and upserts rows into SQLite (default `data/markets.db`).

```bash
pm-runner discover
pm-runner discover --registry /tmp/markets.db
```

**Resolution:** these markets typically settle on **Chainlink** streams (see `resolution_source` / description in each row), not CEX spot—use that when wiring fair value in Phase 4.

## Tests

```bash
pytest
ruff check pm_latency tests
```
