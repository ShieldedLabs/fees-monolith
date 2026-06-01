# z_getstandardfee Conformance Vectors

Reference data for verifying that an implementation of the [`z_getstandardfee` RPC](https://zips.z.cash/zip-XXXX#fee-estimator-v0) produces the same response as the canonical implementation.

## What this is — and what it isn't

> [!important] Scope
> These vectors document the **v0 reference candidate as currently shipped**. They verify that an indexer's relay (lightwalletd, zaino) is consistent with the canonical Zebra. They do **not** evaluate whether v0's specific parameter choices are the right ones — that's the optional [parameter-refinement stage](https://fees.shieldedinfra.net/research), driven by observed user behavior.

The v0 candidate has **at least three open design choices** that may be refined later if the data warrants. For now, treat the v0 algorithm as a candidate, not a final spec.

## Files

- **[conformance-vectors-v0.json](conformance-vectors-v0.json)** — captured responses + invariants for the v0 reference candidate.

## Quick verification (indexer relay only)

If you operate an indexer (lightwalletd, zaino) and want to check that your relay matches the canonical Zebra at the same chain tip:

```bash
# Query your indexer
curl -s -X POST http://YOUR_INDEXER:PORT \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"z_getstandardfee","id":1}' | jq '.result'

# Query the canonical Zebra at the same height
curl -s -X POST http://ZEBRA_REFERENCE:8232 \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"z_getstandardfee","id":1}' | jq '.result'

# Diff them. They should be identical (modulo the how_is_this_calculated URI form).
```

The response shape and invariants are documented in `conformance-vectors-v0.json`.

## v0 reference candidate: open design choices

These are the choices currently fixed in v0, with named alternatives and the analysis that informs them:

| Choice | v0 (currently shipped) | Alternative | Informed by |
|---|---|---|---|
| **Oracle type** | action-weighted median | median-of-medians (nikete audit recommendation) | audit favors median-of-medians for manipulation resistance; simulator compares both under median-poisoning + miner-self-dealing |
| **Floor fee** | 1,000 zats/action (assumes the marginal-fee reduction draft has shipped) | 5,000 zats/action (current ZIP-317 mainnet value) | audit notes anti-spam depends on the floor; simulator tests floor saturation |
| **Quantization** | powers-of-10 bucketing | finer rounding (powers of √10), continuous, alternative bucket scales | audit flags bucket-flip timing as a privacy signal; simulator tests bucket-boundary nudging |

**Implication for indexers:** the v0 algorithm in your indexer should match what canonical Zebra emits today. If a parameter is later refined, you'll see a `version` bump (e.g. `v0` → `v0.1` or `v1`), and a new vectors file will be published.

## Related but distinct work

These do **not** verify against the v0 vectors — they are intentionally different mechanisms or modeling tools:

- **[github.com/mnm458/zcash-dyanmic-fee-sim](https://github.com/mnm458/zcash-dyanmic-fee-sim)** — Mohak Nahta's adversarial simulator. Implements `ComparableMedianController` with configurable oracle types (median-of-medians, action-weighted-median, etc.) and runs them against several adversarial scenarios. Its output *informs* the choice between the v0 alternatives above.
- **[github.com/Simulacra-RnD/ZCash-TFM](https://github.com/Simulacra-RnD/ZCash-TFM)** — Miguel's cadCAD framework. Models historical Zcash fee mechanisms (Genesis 10k zat, ZIP-313 1k zat, ZIP-317 weight-based). Useful as comparators / historical context; v0 is not yet implemented as a fourth model.

## Reporting divergence

If you find an implementation that disagrees with the canonical Zebra at the same tip — that's an indexer-relay bug, the kind these vectors are designed to catch. Open an issue at [github.com/ShieldedLabs/fee-playground](https://github.com/ShieldedLabs/fee-playground/issues).

If you find a parameter choice in v0 that you think is wrong on its merits — that's a parameter-refinement conversation, not a vectors issue. Open an issue at the same repo, or see [Further Research](https://fees.shieldedinfra.net/research) for the analysis behind the current choices.
