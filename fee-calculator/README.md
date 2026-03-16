# Zcash Dynamic Fees Lab

A no-build, three-page web app plus a tiny Python API that visualizes live Zcash fee signals and proposes a two-lane "Paris Metro" quoting model (Standard + Express).

## What you get
- **Static UI (index.html / proposal.html / calculator.html / zip-proposal.html / style.css / mempool.js)**:
  - `index.html` = tool-first live dashboard
  - `proposal.html` = long-form design rationale
  - `calculator.html` = attack modeling + exploratory ideas (including difficulty/price chart)
  - `zip-proposal.html` = raw ZIP draft text
- **Backend (engine.py / proxy.py)**: Pure-Python fee engine that computes weighted medians, entropy, bucketed prices, and lane quotes. The proxy serves the SPA and exposes `/api/summary` for the frontend.
- **Docker + tests**: Container entrypoint runs the proxy; unit tests cover the engine and HTTP surface.

## Quick start (live data)
1) Make sure Zebra is running and you can read its auth cookie (`~/.cache/zebra/.cookie` by default).
2) Start the proxy:
   ```bash
   python3 proxy.py
   # or: make docker-build && make docker-run
   ```
   Env vars: `ZEBRA_HOST` (default `127.0.0.1`), `ZEBRA_PORT` (default `8232`), `ZEBRA_COOKIE_PATH` (default `~/.cache/zebra/.cookie`), `SERVER_PORT` (default `8080`).
3) Visit `http://localhost:8080/` to load the live dashboard (`/proposal.html`, `/calculator.html`, and `/zip-proposal.html` are linked in the header nav).

## Offline / static viewing
Open `index.html` directly in a browser. Live sections will show placeholders unless `/api/summary` is reachable. The difficulty/price chart in `calculator.html` still loads from the local CSV.

## API surface
- `GET /api/summary` – JSON snapshot with:
  - `lanes.standard` and `lanes.express` fee quotes (zats, µZEC, USD when available)
  - `market` median hint, `metrics` (fee entropy, median fee/action, tx size), `blocks.entries` (last ~50 blocks), `mempool.rows` (top 200 by fee/action)
  - `nsm` fields showing total/recycled fees if Network Sustainability Mechanism were active
The frontend polls this endpoint every ~4 seconds.

## Repo layout
- `index.html`, `proposal.html`, `calculator.html`, `zip-proposal.html`, `style.css`, `mempool.js` – static pages and styling (no build step).
- `engine.py` – fee math (medians, quantiles, entropy, Paris lanes, synthetic fill helpers).
- `proxy.py` – Zebra RPC wrapper, cache, HTTP server, `/api/summary` wiring.
- `tests/` – API smoke test using the FakeProvider.
- `zcash_difficulty_price.csv` – data for the difficulty/price chart.
- `Makefile` – `make lint` (htmlhint, stylelint, ruff), `make test`, docker helpers.

## Design highlights reflected in the UI
- Standard lane = action-weighted median fee over the recent block window, rounded to the nearest power of ten (ZIP-317 style).
- Express lane = 10× the Standard median placeholder (UI showcase); backend also exposes drift/backlog context for future tuning.
- Live dashboard surfaces lane quotes, block congestion, entropy stats, and ZIP-317 quick estimates.
- Block bars show recent utilization and a single congestion percentage.
- ZIP-317 calculator lets you plug in an action count and see total fee in zats/USD.
- Difficulty vs. price chart renders the bundled CSV and displays Pearson r values.

## Development
- Lint everything: `make lint`
- Tests: `make test`
- Ruff config now lives under `[lint]` in `.ruff.toml`; stylelint rules are in `.stylelintrc.json` (modern color syntax, BEM-ish selectors allowed).

## Notes / limitations
- The Express card currently mirrors a 10× multiplier; real Cramér–Lundberg tuning is implemented in `engine.py` but not wired into the UI yet.
- If Zebra is unreachable or the cookie is missing, `/api/summary` returns HTTP 500 and the UI will stay in placeholder state.
- The page is intentionally dark-themed and mobile-friendly; the media query uses modern range syntax `(width <= 768px)`.

## Contributing
Issues and PRs welcome—please keep calculations aligned with ZIP-317 and avoid adding build tooling.
