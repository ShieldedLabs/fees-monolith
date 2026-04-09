```
ZIP: Unassigned
Title: Reduce Marginal Fee to 1000 Zatoshis
Owners: Mark Henderson <mark@shieldedlabs.net>
Status: Draft
Category: Standards / Wallet
Updates: ZIP 317
Created: 2026-04-06
License: MIT
Discussions-To: <TBD>
Pull-Request: <TBD>
```


# Terminology

The key words "MUST", "SHOULD", "SHOULD NOT", and "MAY" in this document are
to be interpreted as described in BCP 14 [^BCP14] when, and only when, they
appear in all capitals.

The terms "conventional transaction fee", "marginal fee", "logical actions",
and "grace actions" are as defined in ZIP 317. [^zip-0317]

The term "zatoshi" is defined as in the Zcash protocol specification.
[^protocol]


# Abstract

This ZIP modifies ZIP 317 [^zip-0317] by reducing the `marginal_fee` parameter
from 5,000 to 1,000 zatoshis per logical action. The conventional fee for a
minimal 2-action transaction decreases from 10,000 to 2,000 zatoshis. All other
ZIP 317 parameters and formulae are unchanged.


# Motivation

## Fiat cost escalation

ZIP 317 was designed in late 2022 when ZEC traded near $30. The `marginal_fee`
of 5,000 zatoshis per logical action yields a minimum transaction fee of 10,000
zatoshis (for a 2-action transaction), which at the time cost approximately
$0.003.

As ZEC's market price has risen, the fiat cost of transactions has risen
proportionally while the network's fee parameters have remained static:

| ZEC price | `marginal_fee` | Min. tx fee (2 actions) | Approx. USD cost |
|-----------|----------------|-------------------------|------------------|
| $30       | 5,000          | 10,000 zats             | $0.003           |
| $50       | 5,000          | 10,000 zats             | $0.005           |
| $100      | 5,000          | 10,000 zats             | $0.010           |
| $250      | 5,000          | 10,000 zats             | $0.025           |
| **$250**  | **1,000**      | **2,000 zats**          | **$0.005**       |

The proposed fee restores the fiat-equivalent cost to what it was when ZEC
traded near $50 -- still higher than the $0.003 design point at $30.

## Higher stakes require adaptive defense

ZEC's increased value means that the incentive for sustained denial-of-service
attacks has also grown. A static fee -- whether 5,000 or 1,000 zatoshis -- was
never designed to be the sole defense against adversarial congestion. ZIP 317's
fee mechanism is a wallet convention, not a consensus rule, and cannot
dynamically respond to demand spikes.

The structural defenses against spam are independent of the marginal fee level:

- `block_unpaid_action_limit` (ZIP 317 [^zip-0317]) caps the number of
  underpriced logical actions per block at 50, regardless of the marginal fee
  value.
- ZIP 401 [^zip-0401] provides mempool cost-limiting that evicts low-fee
  transactions under memory pressure.
- ZIP 235 [^zip-0235] removes 60% of all transaction fees from circulation
  permanently, making sustained spam irreversibly costly to the attacker.

The dynamic fee estimator specified in [^zip-draft-dynamic-fees] is the
appropriate mechanism for responding to adversarial congestion. It detects
sustained high demand and raises the recommended fee accordingly. This static
reduction is safe as a bridge because the structural defenses remain intact, and
the dynamic mechanism is under active development and testing.

## Bridge to dynamic fees

The dynamic fee estimator [^zip-draft-dynamic-fees] uses a powers-of-10
bucketing scheme (10, 100, 1,000, 10,000, ...) and would recommend a
`standard_fee` of 1,000 zatoshis per action under current network conditions
(blocks well below capacity). This static reduction front-runs the dynamic
mechanism's recommendation, providing immediate user relief while the full
adaptive system undergoes multi-phase testing and deployment.

The two ZIPs are complementary: this ZIP adjusts the baseline wallet convention
to reflect current economics, while the dynamic fee ZIP builds the adaptive
mechanism that will keep fees appropriate regardless of future price movements
or demand changes.

## Historical precedent

The value `marginal_fee = 1000` was considered during ZIP 317's design and is
documented in ZIP 317's rationale section as "adapted from @madars' proposal"
[^madars-1]. It was not chosen at the time because, at $30/ZEC, the resulting
minimum fee of 2,000 zatoshis ($0.0006) was deemed insufficient for
denial-of-service deterrence. At $250/ZEC, the same 2,000 zatoshis represents
$0.005 -- nearly 10x the fiat cost that was rejected as too low.


# Specification

## Changes to ZIP 317

In the table in the section **Fee calculation** of ZIP 317 [^zip-0317], the
row for `marginal_fee` is changed from:

> `marginal_fee` = 5000 zatoshis per logical action

to:

> `marginal_fee` = 1000 zatoshis per logical action

All other parameters are unchanged:

| Parameter                     | Value | Units                  |
|-------------------------------|-------|------------------------|
| `marginal_fee`                | 1,000 | zatoshis per logical action |
| `grace_actions`               | 2     | logical actions        |
| `p2pkh_standard_input_size`   | 150   | bytes                  |
| `p2pkh_standard_output_size`  | 34    | bytes                  |
| `creation_cost`               | 100   | logical actions        |

The formula for `conventional_fee` is unchanged:

$$\mathit{conventional\_fee} = \mathit{marginal\_fee} \times \max(\mathit{grace\_actions},\, \mathit{logical\_actions})$$

For a minimal 2-action transaction: $1000 \times \max(2, 2) = 2000$ zatoshis.

## No changes to block template construction

The recommended algorithm for block template construction in ZIP 317 is
unchanged. The `block_unpaid_action_limit` of 50 remains. The `unpaid_actions`
formula continues to use `marginal_fee` and automatically reflects the updated
value:

$$\mathit{unpaid\_actions}(\mathit{tx}) = \max\!\left(0,\, \max(\mathit{grace\_actions},\, \mathit{tx.logical\_actions}) - \left\lfloor\frac{\mathit{tx.fee}}{\mathit{marginal\_fee}}\right\rfloor\right)$$

## Interaction with ZIP 235

ZIP 235 [^zip-0235] removes 60% of transaction fees from circulation. This ZIP
does not change that fraction. At the new minimum fee of 2,000 zatoshis: 1,200
zatoshis are burned and 800 zatoshis are paid to the miner. No changes to
ZIP 235 are required.


# Rationale

## Magnitude of the reduction

An 80% reduction in the zatoshi amount is large in nominal terms, but the
relevant metric is the economic cost of a transaction. At $250/ZEC, the proposed
minimum fee of 2,000 zatoshis ($0.005) is still higher than the minimum fee at
the time ZIP 317 was designed ($0.003 at $30/ZEC). In fiat terms, this change
restores the fee to a level consistent with ZIP 317's original design intent.

## Attack economics

The marginal fee sets the floor for the cost of sustained denial-of-service
attacks. A 2 MB block can accommodate approximately 1,000 minimal shielded
transactions (2 actions each), totaling roughly 2,000 logical actions. At
Zcash's target block interval of 75 seconds (~48 blocks/hour):

| Scenario         | `marginal_fee` | ZEC price | Cost to fill blocks for 1 hour |
|------------------|----------------|-----------|-------------------------------|
| Original design  | 5,000          | $30       | ~$144                         |
| Current          | 5,000          | $250      | ~$1,200                       |
| **Proposed**     | **1,000**      | **$250**  | **~$240**                     |

The proposed fee yields an hourly attack cost of ~$240, which is ~1.7x the
attack cost at ZIP 317's original design point. However, the incentive to
attack a $250 ZEC is also higher than for a $30 ZEC. This ZIP does not claim
that the static marginal fee alone is sufficient to deter well-funded
adversaries. Instead, it relies on the layered defense described in the
Motivation section:

1. `block_unpaid_action_limit` structurally caps spam per block.
2. ZIP 401 mempool eviction limits memory-based denial of service.
3. ZIP 235 fee burn makes sustained spam permanently costly.
4. The dynamic fee mechanism [^zip-draft-dynamic-fees] will adaptively raise
   fees under congestion (e.g. `express_fee = standard_fee * 10`).

The marginal fee is one layer in a defense-in-depth stack, not a standalone
spam deterrent.

## Why 1,000 and not another value

- **2,000 or 2,500**: Not a power of 10. Misaligns with the dynamic fee
  estimator's powers-of-10 bucketing scheme, which is designed to reduce fee
  entropy for privacy. [^zip-draft-dynamic-fees]
- **500**: At $250/ZEC, yields a minimum fee of $0.001 -- below the fiat cost
  at ZIP 317's $30 design point. Reduces the attack cost below the original
  design baseline.
- **100**: A 50x reduction. Yields a minimum fee of $0.00005, genuinely too low
  for any spam deterrent purpose.
- **1,000**: The value previously vetted during ZIP 317 development [^madars-1].
  At current prices, restores the fiat fee to a level between the original
  design point and the current overshoot. Aligns with the dynamic fee
  estimator's natural bucketing. The Goldilocks value.


# Deployment

## Wallet deployment

Wallets SHOULD use `marginal_fee = 1000` for fee calculation upon this ZIP
reaching Active status. Since ZIP 317 fees are a wallet convention (not a
consensus rule), no network upgrade is required.

## Node relay policy

Nodes SHOULD update their relay and mempool eviction thresholds to use the
new `marginal_fee` value. Specifically:

- The `txunpaidactionlimit` threshold (default: 50, as documented in ZIP 317
  [^zip-0317]) remains unchanged, but the per-transaction `unpaid_actions`
  computation uses the updated `marginal_fee`.
- The `low_fee_penalty` in ZIP 401 [^zip-0401] mempool eviction SHOULD be
  recalibrated to the new conventional fee.

## Deployment ordering

Node relay policy updates SHOULD be deployed before or concurrently with wallet
updates. A transaction paying 2,000 zatoshis evaluated by a node still using
`marginal_fee = 5000` would compute:

$$\mathit{unpaid\_actions} = \max(2, 2) - \left\lfloor\frac{2000}{5000}\right\rfloor = 2 - 0 = 2$$

Such a transaction would still be relayed and mined (it counts against the
`block_unpaid_action_limit` budget of 50), but would incur the `low_fee_penalty`
in ZIP 401 mempool eviction on nodes that have not yet updated. Coordinating
node updates first avoids this friction.

## Testnet

The reduced fee SHOULD be deployed on Testnet before Mainnet.

## Node configuration override

Node implementations MUST support a `-marginalfee` configuration option that
overrides the default `marginal_fee` used in relay policy calculations
(`unpaid_actions`, `low_fee_penalty`). The default value is 1,000 zatoshis.

This allows node operators to revert to `marginal_fee = 5000` (or any other
value) without a software update if network conditions change. For example:

```
zebrad -marginalfee=5000
```

This follows the existing precedent of `-txunpaidactionlimit` and
`-blockunpaidactionlimit` as operator-configurable relay policy parameters
documented in ZIP 317 [^zip-0317].

Node operators SHOULD consider reverting to `marginal_fee = 5000` if the
hourly cost to fill blocks with spam falls below $100, which would occur at
approximately ZEC = $50 at the proposed fee level. (See the attack cost table
in the Rationale section.)

## Sunset clause

This ZIP expires 12 months after reaching Active status. At expiration, the
`marginal_fee` reverts to 5,000 zatoshis unless one of the following has
occurred:

1. A follow-up ZIP renews or replaces this parameter change.
2. The dynamic fee mechanism [^zip-draft-dynamic-fees] has reached Active
   status, in which case the static `marginal_fee` serves only as a fallback
   value and this ZIP's expiration has no practical effect on wallet behavior.

The sunset ensures that the reduced fee is re-evaluated in light of future
price movements, network conditions, and progress on the dynamic fee mechanism.
It prevents a static parameter from silently becoming inappropriate as
conditions change — the same failure mode that motivated this ZIP in the first
place.


# Security and Privacy Considerations

## Privacy

Reducing `marginal_fee` does not change the fee formula's structure. All wallets
using the updated conventional fee will pay the same amount for the same
transaction shape, preserving the property that fees do not leak transaction
construction details beyond what is visible in the transaction's public fields.

## Denial of service

The 5x reduction in the per-action fee is offset by the layered structural
defenses described in the Motivation and Rationale sections.
`block_unpaid_action_limit` provides a hard cap on underpriced actions per block
that is independent of the marginal fee level. ZIP 401 provides mempool-level
defense. ZIP 235's 60% fee burn makes sustained spam permanently costly. The
dynamic fee mechanism [^zip-draft-dynamic-fees], when deployed, will raise fees
adaptively during congestion.

## Fee transition

During the transition period when some wallets use 5,000 and others use 1,000,
fee heterogeneity could reduce transaction privacy. This is the same concern
noted in ZIP 317's own deployment section. The mitigation is the same:
coordinated deployment across wallet implementations. Once the dynamic fee
mechanism is active, all wallets converge on a single published fee signal,
eliminating this source of heterogeneity.


# References

[^BCP14]: [Information on BCP 14 — "RFC 2119: Key words for use in RFCs to Indicate Requirement Levels" and "RFC 8174: Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words"](https://www.rfc-editor.org/info/bcp14)

[^protocol]: [Zcash Protocol Specification, Version 2025.6.3 [NU6.1] or later](protocol/protocol.pdf)

[^zip-0235]: [ZIP 235: Remove 60% of Transaction Fees From Circulation](zip-0235)

[^zip-0313]: [ZIP 313: Reduce Conventional Transaction Fee to 1000 zatoshis](zip-0313)

[^zip-0317]: [ZIP 317: Proportional Transfer Fee Mechanism](zip-0317)

[^zip-0401]: [ZIP 401: Addressing Mempool Denial-of-Service](zip-0401)

[^zip-draft-dynamic-fees]: [ZIP Draft: Dynamic Fee Estimation via z_getstandardfees](zip-draft-dynamic-fees)

[^madars-1]: [Madars Virza, concrete soft-fork proposal](https://forum.zcashcommunity.com/t/zip-reduce-default-shielded-transaction-fee-to-1000-zats/37566/89)
