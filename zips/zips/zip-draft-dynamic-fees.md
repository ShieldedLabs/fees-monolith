```
ZIP: Unassigned
Title: Dynamic Fee Estimation via z_getstandardfees
Owners: Mark Henderson <mark@shieldedlabs.net>
Status: Draft
Category: Standards / RPC
Created: 2026-03-16
License: MIT
Discussions-To: <https://forum.zcashcommunity.com/c/technology/dynamic-fees/100>
Pull-Request: <TBD>
```


# Terminology

The key words "MUST", "MUST NOT", "SHOULD", "SHOULD NOT", and "MAY" in this
document are to be interpreted as described in BCP 14 [^BCP14] when, and only
when, they appear in all capitals.

The terms "conventional transaction fee", "marginal fee", "logical actions",
and "grace actions" are as defined in ZIP 317. [^zip-0317]

The term "zatoshi" is defined as in the Zcash protocol specification.
[^protocol]


# Abstract

This ZIP specifies `z_getstandardfees`, an RPC endpoint served by indexers
(e.g. Zaino, lightwalletd) that publishes a dynamic fee recommendation derived
from confirmed blocks. The computation runs entirely at the indexer layer — no
changes to full node software (e.g. Zebra) are required. The recommendation is
observational: it reflects what the network has recently accepted, not what it
will accept in the future. No service-level guarantees are made or implied.


# Motivation

ZIP 317 [^zip-0317] defines a fixed marginal fee of 5,000 zatoshis per logical
action. This fee was calibrated to a ZEC price and network conditions that no
longer hold. As ZEC's price rises and adoption increases, the fixed fee becomes
increasingly expensive in fiat terms while offering no mechanism to adjust
downward during periods of low demand, or upward during congestion.

A dynamic fee recommendation, computed from public on-chain data, allows
wallets to suggest fees that reflect current network conditions. By publishing
the recommendation through a standard indexer RPC endpoint, all wallets and
services can converge on the same fee signal, reducing fee entropy and
improving privacy.

This ZIP does not propose consensus changes. It defines an RPC interface and a
reference fee estimation algorithm (Fee Estimator v0) that indexers compute
from confirmed block data and expose to connected wallets as a policy
recommendation. No full node changes are required.


# Requirements

The fee recommendation:

- MUST be computable from public, confirmed block data only.
- MUST NOT require access to mempool state or any non-public information.
- MUST NOT leak information that could be used to segment or fingerprint users
  beyond what is already public.
- SHOULD produce stable outputs — fee changes should be infrequent under normal
  conditions.
- SHOULD be computationally inexpensive and not degrade indexer performance.
- MUST be versioned so that estimator changes are explicit and detectable.


# Specification

## RPC Method

`z_getstandardfees`

Parameters: None.

Result: A JSON object with the following fields:

| Field                    | Type    | Required | Description                                                                 |
|--------------------------|---------|----------|-----------------------------------------------------------------------------|
| `standard_fee`           | integer | Yes      | Recommended fee per logical action, in zatoshis.                            |
| `express_fee`            | integer | No       | Priority fee per logical action, in zatoshis. Present only when congested.  |
| `version`                | string  | Yes      | Estimator version identifier (e.g. `"v0"`).                                |
| `height`                 | integer | Yes      | The chain tip height at the time of computation.                            |
| `how_is_this_calculated` | string  | Yes      | URI pointing to the estimator specification.                                |


### Example Response (uncongested)

```json
{
  "standard_fee": 1000,
  "express_fee": null,
  "version": "v0",
  "height": 2750000,
  "how_is_this_calculated": "https://zips.z.cash/zip-XXXX#fee-estimator-v0"
}
```

### Example Response (congested)

```json
{
  "standard_fee": 10000,
  "express_fee": 100000,
  "version": "v0",
  "height": 2750000,
  "how_is_this_calculated": "https://zips.z.cash/zip-XXXX#fee-estimator-v0"
}
```

### Reserved Fields

The following fields are reserved for future estimator versions.
Implementations MUST NOT include them until a future ZIP or estimator revision
defines their semantics.

- `tiers` — structured fee tier data
- `floor_fee` — the minimum enforceable fee floor
- `window` — lookback window metadata (block heights, buffer size)
- `dispersion` — fee volatility / "fee weather" indicator
- `health` — diagnostic flags (under-sampled, high variance, suspected
  manipulation)

### Non-Claims

This endpoint is observational. Specifically:

1. A returned `standard_fee` is not a guarantee of inclusion in any block.
2. The endpoint does not constitute a service-level agreement between the
   indexer and the wallet.
3. The fee recommendation reflects recent confirmed history. It does not
   predict future miner behavior.
4. Wallets SHOULD present the fee recommendation to users as an estimate, not
   a promise. Suggested UX language: "estimated fee" or "recommended fee",
   never "required fee" or "guaranteed fee".


## Fee Estimator v0

This section defines the reference algorithm for computing `standard_fee` and
`express_fee`. Implementations MUST produce identical outputs for the same
chain state when using the same estimator version. Conformance is verified by
published test vectors (see [Test Vectors](#test-vectors)).


### Parameters

| Parameter            | Value | Description                                                    |
|----------------------|-------|----------------------------------------------------------------|
| B                    | 50    | Lookback window size in blocks                                 |
| b                    | 5     | Chain-tip buffer in blocks                                     |
| floor                | 100   | Synthetic transaction fee per action, in zatoshis              |
| block_capacity       | 2 MB  | Maximum block size for synthetic fill computation              |
| express_multiplier   | 10    | Multiplier applied to `standard_fee` for the express tier      |


### Lookback Window

Let *h* be the current chain tip height. The lookback window *L* is defined as
the *B* consecutive blocks ending *b* blocks before the tip:

> *L* = { B<sub>h−B−b+1</sub>, …, B<sub>h−b</sub> }

The buffer *b* guards against chain-tip volatility due to reorgs.


### Transaction Set

For each block in *L*, collect all non-coinbase transactions. For each
transaction *tx*, compute:

- `logical_actions(tx)` — as defined in ZIP 317. [^zip-0317]
- `fee_per_action(tx)` = floor( *tx.fee* / max( *grace_actions*,
  *logical_actions(tx)* ) )

This yields a multiset *F* of per-action fees from confirmed transactions.


### Synthetic Fill

To model the network as always occupied (providing a fee signal even during
low-traffic periods), compute the unused capacity in each block and fill it
with synthetic transactions:

1. For each block in *L*, compute `avg_tx_size` as the mean transaction size
   in bytes across all non-coinbase transactions in *L*.
2. For each block, compute `unused_bytes` = `block_capacity` − `block_size`.
3. `synthetic_count` = floor( `unused_bytes` / `avg_tx_size` ) for each block.
4. Add `synthetic_count` entries of `floor` to the fee multiset *F* for each
   block.

If a block contains no non-coinbase transactions, use `avg_tx_size` from the
remaining blocks in *L*. If no block in *L* contains non-coinbase
transactions, the estimator SHOULD return the current ZIP 317 conventional fee
as `standard_fee` and omit `express_fee`.


### Median Computation

Sort *F* in ascending order. The raw fee estimate is the median value of *F*.


### Powers-of-10 Bucketing

Round the raw median to the nearest power of 10:

- Let *raw* be the raw median.
- Let *log* = log<sub>10</sub>(*raw*).
- Let *low* = 10<sup>floor(*log*)</sup>.
- Let *high* = 10<sup>ceil(*log*)</sup>.
- If *raw* − *low* ≤ *high* − *raw*, then *bucketed* = *low*; else
  *bucketed* = *high*.

The `standard_fee` is max(*floor*, *bucketed*).

Bucketing reduces fee entropy and information leakage (privacy goal), makes fee
changes infrequent (UX goal), and ensures fees are divisible by 5 for
compatibility with ZIP 235's NSM contribution rules. [^zip-0235]


### Congestion Detection and Express Fee

When real transactions have displaced all synthetic transactions from the
lookback window, the median is driven entirely by organic demand and the
network is considered congested.

Formally, congestion is detected when the total synthetic count across all
blocks in *L* is zero — i.e. every block in the window is full.

When congested:

> `express_fee` = `standard_fee` × `express_multiplier`

When not congested, `express_fee` is null / omitted.


## Estimator Versioning

The `version` field identifies which algorithm produced the result. This
allows:

- Wallets to detect when an indexer's estimator has changed.
- Test vectors to be scoped to a specific algorithm version.
- Gradual migration: indexers can support multiple versions during transitions.

When the estimator algorithm changes (parameters, formula, or structure), the
`version` string MUST change. The recommended convention is `"v0"`, `"v1"`,
etc.

Indexers MAY support a `version` parameter on the RPC call to request a
specific estimator. If unsupported or unrecognized, the indexer SHOULD return
the default (latest) version.


## Indexer Implementation

The fee estimator is computed by the indexer, not the full node. This means:

1. The indexer MUST have access to confirmed block data for at least *B* + *b*
   blocks behind the current tip. Indexers already maintain this data for
   wallet serving.
2. The indexer MUST recompute the estimate when the indexed tip advances.
   Caching the result per tip height is RECOMMENDED to avoid redundant
   computation across concurrent wallet requests.
3. If the indexer's indexed tip lags the full node's tip by more than *b*
   blocks, the estimator output may be stale. Indexers SHOULD include the
   `height` field so wallets can detect staleness.

The algorithm is defined portably: any implementation with access to confirmed
block data can compute it. Full nodes, alternative indexers, or offline tooling
MAY implement the same algorithm independently. Conformance is verified by test
vectors, not by implementation location.

Wallets that obtain fee data through an indexer should be aware of the trust
implications described in the Zcash Wallet App Threat Model. [^wallet-threat-model]
The indexer computes the fee recommendation from the same confirmed block data
it already serves to wallets; the incremental trust surface is minimal.


## Test Vectors

Published test vectors consist of:

1. A chain slice: an ordered sequence of blocks with their full transaction
   data.
2. The expected `z_getstandardfees` output for that slice under each estimator
   version.

Conformance requirement: given the same chain slice, all implementations using
the same estimator version MUST produce byte-identical JSON output (after
normalization of field ordering and whitespace). This applies across indexer
implementations (e.g. Zaino, lightwalletd) and any offline or full-node
implementations of the algorithm.

Test vector sets will be published alongside this ZIP at \<TBD\>.


# Security and Privacy Considerations

## Privacy

- **Fee entropy.** Powers-of-10 bucketing limits the set of possible fee
  values, reducing the information content of a transaction's fee. This is a
  strict improvement over the status quo where wallets may independently
  compute varying fee amounts.
- **Timing signals.** The lookback window is long enough (≈1 hour) and the
  bucketing coarse enough that fee changes are infrequent. This limits the
  ability of an observer to correlate transactions with specific fee-change
  events.
- **No mempool dependency.** The estimator uses only confirmed block data. It
  does not reveal or depend on mempool contents.

## Denial of Service

- **Spam resistance.** Synthetic fill ensures that the fee floor holds during
  low-traffic periods. An attacker must sustain enough transaction volume to
  displace synthetics across the full lookback window before the fee rises
  organically.
- **Manipulation resistance.** The median is robust to outliers. An attacker
  cannot meaningfully shift the fee recommendation without controlling >50% of
  per-action fee observations in the lookback window.
- **ZIP 317 compatibility.** The action-based accounting from ZIP 317
  [^zip-0317] remains in effect. An attacker cannot generate large-in-kb
  transactions cheaply to skew the average transaction size used for synthetic
  fill.

## Miner Incentives

This ZIP does not change consensus rules or block template construction.
Miners remain free to include transactions at any fee. The recommendation is a
coordination signal: if wallets converge on the recommended fee, miners benefit
from predictable fee behavior and reduced orphan risk from oversized mempools.


# Deployment

## Phase 1: Indexer (Policy-only)

Indexers implementing `z_getstandardfees` SHOULD deploy the endpoint as an
informational RPC call. No full node changes, consensus changes, or relay
policy changes are required.

The reference implementation targets Zaino. Other indexers (e.g. lightwalletd)
MAY implement the same algorithm using the published test vectors for
conformance.

## Phase 2: Wallet Adoption

Wallets SHOULD begin using `z_getstandardfees` to inform fee selection UX.
Wallets MUST NOT treat the returned fee as mandatory — users should retain the
ability to override.

## Future: Full Node and Consensus

If a future ZIP proposes relay policy changes or consensus-level fee rules
(e.g. mandatory bucketing, fee floors, or expiry height constraints), those
rules will be specified in a separate ZIP. Such a ZIP MAY move the fee
estimator into the full node, or MAY continue to rely on the indexer
computation defined here.


# References

[^BCP14]: [Information on BCP 14 — "RFC 2119: Key words for use in RFCs to Indicate Requirement Levels" and "RFC 8174: Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words"](https://www.rfc-editor.org/info/bcp14)

[^protocol]: [Zcash Protocol Specification, Version 2025.6.3 [NU6.1] or later](protocol/protocol.pdf)

[^zip-0235]: [ZIP 235: Remove 60% of Transaction Fees From Circulation](zip-0235.md)

[^zip-0317]: [ZIP 317: Proportional Transfer Fee Mechanism](zip-0317.rst)

[^wallet-threat-model]: [Zcash Wallet App Threat Model](https://zcash.readthedocs.io/en/latest/rtd_pages/wallet_threat_model.html)

[^dynamic-fees-lab]: [Zcash Dynamic Fees Lab](https://github.com/ShieldedLabs/fee-playground)
