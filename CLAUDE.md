# CLAUDE.md — Dynamic Fees

## What this is
Monolith repo for the Zcash dynamic fees effort. Aggregates five git subtrees:
- `zebra/` ← ShieldedLabs/zebra-dynamic-fees (full node — canonical fee estimator)
- `zaino/` ← zingolabs/zaino (indexer — proxies fee RPC to zebrad)
- `lightwalletd/` ← zcash/lightwalletd (indexer — proxies fee gRPC to zebrad)
- `zips/` ← zcash/zips (specs)
- `fee-calculator/` ← ShieldedLabs/fee-playground (simulation + visualization)

## Architecture
The `z_getstandardfee` algorithm lives in zebrad (`zebra/zebra-rpc/src/methods.rs`).
Both indexers are thin proxies:
- Zaino calls zebrad's JSON-RPC and re-exposes it
- lightwalletd calls zebrad's JSON-RPC and exposes it as gRPC

## Voice
RFC-style. Dry, technical, precise. No editorializing. Same voice as the zips repo.

## Cross-repo context
- `~/Projects/Zcash/zips/` — the canonical ZIPs repo (this repo's `zips/` subtree mirrors it)
- `~/wiki/wiki/` — read [[dynamic-fees-roadmap-2026]], [[zcash]], [[crosslink]], [[shielded-labs]] for context
- The marginal fee ZIP and ZIP-235 NSM edit are tightly coupled — changes to one may require updates to the other

## Build
- `zebra/`: `cd zebra && cargo check -p zebra-rpc` / `cargo test -p zebra-rpc z_getstandardfee`
- `zaino/`: `cd zaino && cargo check -p zaino-state`
- `lightwalletd/`: `cd lightwalletd && go build ./...`
- `fee-calculator/`: `make test`, `make lint`, `make docker-build`
- `zips/`: `make all-zips` (from the zips/ subdirectory)
- Docker: `docker compose build && docker compose up -d`

## Subtree commands
```
git subtree pull --prefix=zebra https://github.com/ShieldedLabs/zebra-dynamic-fees.git aphelionz/z_getstandardfee --squash
git subtree pull --prefix=zaino https://github.com/zingolabs/zaino.git dev --squash
git subtree pull --prefix=lightwalletd https://github.com/zcash/lightwalletd.git master --squash
git subtree pull --prefix=zips https://github.com/zcash/zips.git main --squash
git subtree pull --prefix=fee-calculator https://github.com/ShieldedLabs/fee-playground.git main --squash
```

## Forum content
Zcash community forum threads are often too long for WebFetch. Ask Mark to paste the relevant section.
