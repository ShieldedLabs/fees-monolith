# Zcash Dynamic Fees Lab

Public-facing site at [fees.shieldedinfra.net](https://fees.shieldedinfra.net) for the Zcash dynamic fee mechanism: live `z_getstandardfee` endpoint, design rationale, falsifiable test suite, and protocol-stack interactions.

## Pages

| Route | File | Purpose |
|---|---|---|
| `/` | `index.html` | Portal — live fee cards + orientation + roadmap + nav to other pages |
| `/design` | `design.html` | Three principles, four-layer stack, RPC tabs, deliberately rejected alternatives, open questions |
| `/adversarial` | `adversarial.html` | Earthquake-test scenarios mapped to nikete falsifiers and roadmap gates |
| `/interactions` | `interactions.html` | How dynamic fees couple with Crosslink and ZIP-235 NSM |

Static research artifacts:
- `/research/nikete-audit-2026.pdf` — mechanism design audit by Nicolás "nikete" Della Penna
- `/research/bao-undercutting-2024.pdf` — Claire Bao's MIT thesis on undercutting attacks

## Backend

Single Python file (`proxy.py`) using `http.server`. No framework. Two API endpoints:

- `GET /api/fees` — proxies `z_getstandardfee` to a local Zebra node
- `GET /api/price` — fetches ZEC/USD from CoinGecko, cached 5 minutes

Static file serving handles clean URLs: `/design` resolves to `design.html` if the bare path doesn't exist.

## Quick start

```bash
# Local: assumes Zebra is running at 127.0.0.1:8232
python3 proxy.py
# Visit http://localhost:8080/

# Docker (with Zebra on the host)
make docker-build
make docker-run
# Visit http://localhost:8081/
```

Environment variables:
- `ZEBRA_HOST` (default `127.0.0.1`)
- `ZEBRA_PORT` (default `8232`)
- `ZEBRA_URL` (overrides the above)
- `SERVER_HOST` (default `::`)
- `SERVER_PORT` (default `8080`)

## Deployment

The site runs as `shieldedmark/fee-lab:latest` on the Vultr Kubernetes cluster, behind nginx ingress with letsencrypt cert. Manifests live in [`shielded-infra`](https://github.com/ShieldedLabs/shielded-infra) at `workspaces/k8s/fee-lab.yaml`.

```bash
# Build, push, restart
make docker-build
make docker-push          # requires Docker Hub login as shieldedmark
cd ~/Projects/Zcash/shielded-infra && just restart-fee-lab
```

The deployment is configured with `imagePullPolicy: Always`, so `restart-fee-lab` triggers a fresh pull of `:latest`.

## Frontend

No build step. Plain HTML/CSS/JS. Dark theme via CSS variables (`:root` in `style.css`).

`app.js` runs on every page but gates side effects:
- Tab init and copy buttons run unconditionally (no-op if elements absent)
- Live fee polling runs only when `#standard-fee` (portal hero) or `#live-response` (design RPC tabs) exists

## Lint and test

```bash
make lint         # htmlhint + stylelint + ruff
```

Lints all four HTML files plus `style.css` and `proxy.py`.
