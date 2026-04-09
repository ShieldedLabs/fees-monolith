# CLAUDE.md — Dynamic Fees

## What this is
Monolith repo for the Zcash dynamic fees effort. Aggregates three git subtrees:
- `zaino/` ← zingolabs/zaino (indexer)
- `zips/` ← zcash/zips (specs)
- `fee-calculator/` ← ShieldedLabs/fee-playground (simulation + visualization)

## Voice
RFC-style. Dry, technical, precise. No editorializing. Same voice as the zips repo.

## Cross-repo context
- `~/Projects/Zcash/zips/` — the canonical ZIPs repo (this repo's `zips/` subtree mirrors it)
- `~/wiki/wiki/` — read [[dynamic-fees-roadmap-2026]], [[zcash]], [[crosslink]], [[shielded-labs]] for context
- The marginal fee ZIP and ZIP-235 NSM edit are tightly coupled — changes to one may require updates to the other

## Build
- `fee-calculator/`: `make test`, `make lint`, `make docker-build`
- `zips/`: `make all-zips` (from the zips/ subdirectory)

## Subtree commands
```
git subtree pull --prefix=zaino https://github.com/zingolabs/zaino.git dev --squash
git subtree pull --prefix=zips https://github.com/zcash/zips.git main --squash
git subtree pull --prefix=fee-calculator https://github.com/ShieldedLabs/fee-playground.git main --squash
```

## Forum content
Zcash community forum threads are often too long for WebFetch. Ask Mark to paste the relevant section.
