# CLAUDE.md: Dynamic Fees

## What this is
Monolith repo for the Zcash dynamic fees effort. Aggregates four git subtrees:
- `zebra/` ← ZcashFoundation/zebra, pristine upstream at v6.3.0 (no fork commits)
- `zaino/` ← zingolabs/zaino, pristine upstream (no fork commits)
- `lightwalletd/` ← zcash/lightwalletd, pristine upstream (no fork commits)
- `zips/` ← zcash/zips (specs; the ZIP drafts are the active work in this repo)

## Architecture
Upstream zebra provides the `getstandardfee` RPC as of v6.3.0
(ZcashFoundation/zebra#10717); it returns the ZIP-317 marginal fee
(`standard_fee` + `version`). The old in-tree fork (`z_getstandardfee`,
synthetic-fill estimator, indexer fee proxies) was removed 2026-08-17;
it survives on branch `archive/fee-node-2026-08`. The indexers carry no
fee code.

## Voice
RFC-style. Dry, technical, precise. No editorializing. Same voice as the zips repo.

## Cross-repo context
- `~/Projects/Zcash/zips/`: the canonical ZIPs repo (this repo's `zips/` subtree mirrors it)
- `~/wiki/wiki/`: read [[dynamic-fees-roadmap-2026]], [[zcash]], [[crosslink]], [[shielded-labs]] for context
- The marginal fee ZIP and ZIP-235 NSM edit are tightly coupled; changes to one may require updates to the other

## Build
- `zebra/`: `cd zebra && cargo check -p zebra-rpc`
- `zaino/`: `cd zaino && cargo check -p zaino-state`
- `lightwalletd/`: `cd lightwalletd && go build ./...`
- `zips/`: `make all-zips` (from the zips/ subdirectory)

## Subtree commands
```
git subtree pull --prefix=zebra https://github.com/ZcashFoundation/zebra.git vX.Y.Z --squash  # upstream release tags only
git subtree pull --prefix=zaino https://github.com/zingolabs/zaino.git dev --squash
git subtree pull --prefix=lightwalletd https://github.com/zcash/lightwalletd.git master --squash
git subtree pull --prefix=zips https://github.com/zcash/zips.git main --squash
```

## Forum content
Zcash community forum threads are often too long for WebFetch. Ask Mark to paste the relevant section.
