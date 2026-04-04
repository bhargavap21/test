"""FastAPI dashboard for paper ledger (run with uvicorn)."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from pm_latency.connectors.gamma import DEFAULT_GAMMA_BASE
from pm_latency.paperdash.ledger import PaperLedger, settle_all_open_from_gamma

app = FastAPI(title="Paper trading dashboard")


def _ledger() -> PaperLedger:
    path = Path(os.environ.get("PAPER_LEDGER_DB", "data/paper_ledger.db"))
    taker = float(os.environ.get("PAPER_TAKER_FEE_BPS", "0"))
    redeem = float(os.environ.get("PAPER_REDEEM_FEE_BPS", "0"))
    return PaperLedger(path, taker_fee_bps=taker, redeem_fee_bps=redeem)


@app.get("/api/summary")
def api_summary() -> JSONResponse:
    led = _ledger()
    gamma = os.environ.get("GAMMA_API_BASE", DEFAULT_GAMMA_BASE)
    settle_all_open_from_gamma(led, gamma_base=gamma)
    return JSONResponse(led.summary())


@app.get("/api/trades")
def api_trades(limit: int = 100) -> JSONResponse:
    led = _ledger()
    return JSONResponse({"trades": led.trades(limit=limit)})


@app.get("/api/refresh-settlement")
def api_refresh() -> JSONResponse:
    led = _ledger()
    gamma = os.environ.get("GAMMA_API_BASE", DEFAULT_GAMMA_BASE)
    n = settle_all_open_from_gamma(led, gamma_base=gamma)
    return JSONResponse({"settled_rows": n, "summary": led.summary()})


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Paper trading</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 1.5rem; background: #0f1419; color: #e6edf3; }
    h1 { font-size: 1.25rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px,1fr)); gap: 1rem; margin: 1rem 0; }
    .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1rem; }
    .card b { color: #58a6ff; }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; margin-top: 1rem; }
    th, td { text-align: left; padding: 0.4rem 0.5rem; border-bottom: 1px solid #30363d; }
    th { color: #8b949e; }
    .pos { color: #3fb950; }
    .neg { color: #f85149; }
    button { background: #238636; color: #fff; border: 0; padding: 0.5rem 1rem; border-radius: 6px; cursor: pointer; }
    button:hover { filter: brightness(1.1); }
    .note { color: #8b949e; font-size: 0.8rem; max-width: 48rem; line-height: 1.4; }
  </style>
</head>
<body>
  <h1>Paper trading ledger</h1>
  <p class="note">
    Simulated buys at best ask when <code>risk_allowed</code> in the paper loop. Fees use
    <code>PAPER_TAKER_FEE_BPS</code> on entry notional and <code>PAPER_REDEEM_FEE_BPS</code> on winning payout.
    Settlement pulls Gamma when markets close. MTM uses last Polymarket mid from the running paper process.
  </p>
  <button type="button" onclick="refresh()">Refresh + settle from Gamma</button>
  <div class="grid" id="summary"></div>
  <h2>Recent trades</h2>
  <table><thead><tr>
    <th>ID</th><th>Status</th><th>Slug</th><th>Side</th><th>Contracts</th><th>Entry</th><th>Cost+fees</th>
    <th>Realized</th><th>Winning</th>
  </tr></thead><tbody id="trades"></tbody></table>
  <script>
    function fmt(n) { return n == null ? '—' : Number(n).toFixed(4); }
    function cls(n) { return n > 0 ? 'pos' : (n < 0 ? 'neg' : ''); }
    async function load() {
      const s = await fetch('/api/summary').then(r => r.json());
      document.getElementById('summary').innerHTML = `
        <div class="card"><b>Open trades</b><br/>${s.open_trades}</div>
        <div class="card"><b>Open cost (USD)</b><br/>${fmt(s.open_cost_usd)}</div>
        <div class="card"><b>Unrealized (MTM est.)</b><br/><span class="${cls(s.unrealized_pnl_usd_estimate)}">${fmt(s.unrealized_pnl_usd_estimate)}</span></div>
        <div class="card"><b>Settled trades</b><br/>${s.settled_trades}</div>
        <div class="card"><b>Realized P&amp;L</b><br/><span class="${cls(s.realized_pnl_usd)}">${fmt(s.realized_pnl_usd)}</span></div>
        <div class="card"><b>Settled fees</b><br/>${fmt(s.settled_fees_usd)}</div>
        <div class="card"><b>Taker / redeem bps</b><br/>${s.taker_fee_bps} / ${s.redeem_fee_bps}</div>
      `;
      const t = await fetch('/api/trades?limit=80').then(r => r.json());
      const rows = t.trades.map(x => `<tr>
        <td>${x.id}</td><td>${x.status}</td><td>${(x.event_slug||'').slice(0,28)}</td>
        <td>${x.outcome}</td><td>${fmt(x.contracts)}</td><td>${fmt(x.entry_price)}</td>
        <td>${fmt(Number(x.notional_gross)+Number(x.fee_entry_usd))}</td>
        <td class="${cls(x.realized_pnl_usd)}">${x.realized_pnl_usd==null?'—':fmt(x.realized_pnl_usd)}</td>
        <td>${x.winning_outcome||'—'}</td>
      </tr>`).join('');
      document.getElementById('trades').innerHTML = rows || '<tr><td colspan="9">No trades yet</td></tr>';
    }
    async function refresh() {
      await fetch('/api/refresh-settlement');
      await load();
    }
    load();
    setInterval(load, 10000);
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return HTML_PAGE
