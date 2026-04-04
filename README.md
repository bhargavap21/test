# pm-latency

Incremental build for short-horizon Polymarket CLOB tooling (latency / stale-quote strategy). Tracked in GitHub issues (Phase 1: [#3](https://github.com/bhargavap21/test/issues/3), Phase 2: [#5](https://github.com/bhargavap21/test/issues/5), Phase 3: [#6](https://github.com/bhargavap21/test/issues/6), Phase 4: [#1](https://github.com/bhargavap21/test/issues/1), Phase 5: [#7](https://github.com/bhargavap21/test/issues/7), Phase 6: [#2](https://github.com/bhargavap21/test/issues/2)).

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

### Ingest CEX + Polymarket CLOB (Phase 3)

Runs **Binance** combined `bookTicker` stream (`BTCUSDT` / `ETHUSDT` from registry assets) and **Polymarket** CLOB market WebSocket for all `token_id`s in the registry. Prints periodic JSON summaries (tick counts, receive-minus-exchange delay percentiles, last-tick age). Use `--verbose` for one JSON line per tick.

```bash
pm-runner discover
pm-runner ingest --duration 30
# If Binance WS returns HTTP 451 in your region:
pm-runner ingest --no-cex
```

Environment: `BINANCE_WS_BASE`, `POLYMARKET_CLOB_WS`, `PM_REGISTRY_PATH`.

### Fair value & edge (Phase 4)

Resolution-aware **contract** metadata (oracle hint from description + window bounds from slug epoch). **Model:** GBM with **zero drift**, EWMA vol from CEX mid (proxy—real settlement follows Chainlink per market text). **Edge** vs asks when you pass `--quotes-json`.

```bash
pm-runner fairvalue --cex-mid 95000.5 \
  --quotes-json '{"TOKEN_ID":{"bid":0.48,"ask":0.52}}'
```

Use `--condition-id` to target one row. Anchor = first CEX mid **on or after** `window_start_ts` (simulated time advances via ticks in tests; live use feeds timestamps consistently).

### Risk engine (Phase 5)

- **Limits** from env: `BANKROLL_USD`, `MAX_NOTIONAL_USD` (total exposure), `MAX_MARKET_NOTIONAL_USD`, `MAX_ORDER_NOTIONAL_USD`, `DAILY_LOSS_LIMIT_USD`, `KELLY_FRACTION`, `MAX_ORDERS_PER_MINUTE`.
- **Kill switch:** `PM_KILL_SWITCH=1` or create the file `PM_KILL_FILE` (default `data/kill`) via `pm-runner risk kill`.
- **State:** `PM_RISK_STATE_PATH` (default `data/risk_state.json`) stores daily realized PnL, per-`condition_id` exposure, and recent order timestamps for rate limiting.

```bash
pm-runner risk status
pm-runner risk dry-order --condition-id 0xabc --model-prob 0.58 --ask 0.52
pm-runner risk kill && pm-runner risk unkill
```

### Paper trading loop (Phase 6)

Runs the same WebSocket feeds as `ingest`, maintains per-market fair value + Polymarket quotes, evaluates **`model_prob - ask >= min_edge`**, runs **`RiskEngine`** sequentially, and prints **one JSON line per intent** to stdout (optional `--log-file`). Does **not** post orders.

```bash
pm-runner discover
pm-runner paper --duration 300 --min-edge 0.02 --log-file data/paper_intents.jsonl
```

`paper` needs a **CEX mid** for the model. Default **`--cex auto`** tries **Binance**, then **Coinbase Exchange** (`BTC-USD` / `ETH-USD`) if Binance returns HTTP **451** or otherwise fails. Force one venue: `--cex coinbase` or `--cex binance`. Env: `CEX_PROVIDER`, `COINBASE_WS_URL`.

Use `pm-runner risk kill` to verify intents show `risk_allowed: false`.

Paper mode does **not** increment the risk engine’s orders-per-minute counter (so high `eval-interval` traffic does not false-trigger `rate_limit_orders_per_minute`). Live execution will call `record_order_sent()` on real submits only.

### Paper ledger + dashboard (simulated P&L)

When `risk_allowed` is true, the paper loop can record **simulated fills** (buy at `ask`, size = Kelly `contracts`) into **`PAPER_LEDGER_DB`** (default `data/paper_ledger.db`).

- **Fees:** `PAPER_TAKER_FEE_BPS` on entry notional, `PAPER_REDEEM_FEE_BPS` on winning payout at settlement (set to your best estimate of Polymarket taker + redemption costs).
- **Unrealized:** mark-to-mid from the **same** Polymarket WS feed (approximate).
- **Realized:** dashboard calls Gamma `/markets?condition_ids=…` and settles when `outcomePrices` show a winner (`~1` / `~0`).

```bash
pip install -e ".[dashboard]"
pm-runner paper --ledger-db data/paper_ledger.db --taker-fee-bps 50 --redeem-fee-bps 10 \
  --duration 0 --log-file data/paper_intents.jsonl
# other terminal:
pm-runner dashboard --port 8765
# open http://127.0.0.1:8765
```

Use **`--no-simulate`** to log intents without recording fills, or **`--no-ledger`** to disable the ledger file entirely.

## Tests

```bash
pytest
ruff check pm_latency tests
```
