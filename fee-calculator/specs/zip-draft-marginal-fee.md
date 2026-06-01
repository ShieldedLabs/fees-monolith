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


# Terminology

The key words "MUST" and "SHOULD" in this document are to be interpreted as
described in BCP 14 [^BCP14] when, and only when, they appear in all capitals.

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

ZIP 317 was designed in late 2022 when ZEC traded near $30. The `marginal_fee`
of 5,000 zatoshis per logical action yields a minimum transaction fee of 10,000
zatoshis (for a 2-action transaction), which at the time cost approximately
$0.003.

As ZEC's market price rises, the fiat cost of transactions rises proportionally
while the fee parameters remain static. Using the design-point price *P* = $30:

| ZEC price  | `marginal_fee` | Min. tx fee (2 actions) | Fiat cost vs. design point |
|------------|----------------|-------------------------|----------------------------|
| *P*        | 5,000          | 10,000 zats             | 1x (baseline)              |
| 3 *P*      | 5,000          | 10,000 zats             | 3x                         |
| 10 *P*     | 5,000          | 10,000 zats             | 10x                        |
| **10 *P*** | **1,000**      | **2,000 zats**          | **2x**                     |

At any price above ~2 *P*, the proposed fee produces a higher fiat-equivalent
cost than the original design point.

The value `marginal_fee = 1000` was considered during ZIP 317's design
[^madars-1] but rejected as insufficient for denial-of-service deterrence at
the design-point price. At current prices the same 2,000 zatoshis represents a
substantially higher fiat cost than what was rejected as too low.


# Privacy Implications

Reducing `marginal_fee` does not change the fee formula's structure. All wallets
using the updated conventional fee pay the same amount for the same transaction
shape, preserving the property that fees do not leak transaction construction
details beyond what is visible in the transaction's public fields.

During the transition period when some wallets use `marginal_fee = 5000` and
others use `marginal_fee = 1000`, fee heterogeneity could reduce transaction
privacy by allowing an observer to distinguish between wallet implementations.
The mitigation is coordinated deployment across wallet implementations.


# Requirements

The updated marginal fee:

- Restores the fiat-equivalent transaction cost to near ZIP 317's original
  design point, given current ZEC market prices.
- Does not weaken the layered denial-of-service defenses below their original
  design baseline.
- Aligns with a powers-of-10 fee alphabet for low fee entropy.
- Is reversible: includes a sunset clause to force re-evaluation.
- Does not require a consensus change or network upgrade.


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

## Block template construction

The recommended algorithm for block template construction in ZIP 317 is
unchanged. The `block_unpaid_action_limit` of 50 remains. The `unpaid_actions`
formula continues to use `marginal_fee` and automatically reflects the updated
value:

$$\mathit{unpaid\_actions}(\mathit{tx}) = \max\!\left(0,\, \max(\mathit{grace\_actions},\, \mathit{tx.logical\_actions}) - \left\lfloor\frac{\mathit{tx.fee}}{\mathit{marginal\_fee}}\right\rfloor\right)$$

## Interaction with ZIP 235

ZIP 235 [^zip-0235] removes 60% of transaction fees from circulation. This ZIP
does not change that fraction. At the new minimum fee of 2,000 zatoshis: 1,200
zatoshis are burned and 800 zatoshis are paid to the miner.

## Wallet adoption

Wallets SHOULD use `marginal_fee = 1000` for fee calculation upon this ZIP
reaching Active status. Since ZIP 317 fees are a wallet convention (not a
consensus rule), no network upgrade is required.

Users MUST retain the ability to override the recommended fee.

## Node relay policy

Nodes SHOULD update their relay and mempool eviction thresholds to use the
new `marginal_fee` value. Specifically:

- The `txunpaidactionlimit` threshold (default: 50, as documented in ZIP 317
  [^zip-0317]) remains unchanged, but the per-transaction `unpaid_actions`
  computation uses the updated `marginal_fee`.
- The `low_fee_penalty` in ZIP 401 [^zip-0401] mempool eviction SHOULD be
  recalibrated to the new conventional fee.

## Node relay policy configuration

Node implementations MUST support a configuration option that overrides the
default `marginal_fee` used in relay policy calculations (`unpaid_actions`,
`low_fee_penalty`). The default value is 1,000 zatoshis.

This allows node operators to revert to `marginal_fee = 5000` (or any other
value) without a software update if network conditions change. This follows the
existing precedent of `txunpaidactionlimit` and `blockunpaidactionlimit` as
operator-configurable relay policy parameters documented in ZIP 317.
[^zip-0317]


# Rationale

## Why 1,000

- **Power of 10.** A fee alphabet with discrete levels (100, 1,000, 10,000,
  ...) reduces fee entropy for privacy, simplifies UX, and provides natural
  tier boundaries for any future dynamic fee mechanism.
- **Historical precedent.** The value was vetted during ZIP 317 development
  [^madars-1] and rejected only because the fiat cost was too low at the
  design-point price.
- **Not 500 or lower.** At current prices, 500 yields a fiat cost near or
  below the ZIP 317 design point. 100 is a 50x reduction -- too low for
  meaningful spam deterrence at any reasonable price.
- **Not 2,000 or 2,500.** Not a power of 10; misaligns with a powers-of-10
  fee alphabet.

## Why reducing the fee is safe

The marginal fee is one layer in a defense-in-depth stack:

1. `block_unpaid_action_limit` (ZIP 317 [^zip-0317]) caps underpriced actions
   per block at 50. Zebra currently enforces 0, rejecting any transaction that
   does not fully pay for its logical actions.
2. ZIP 401 [^zip-0401] mempool eviction limits memory-based denial of service.
3. ZIP 235 [^zip-0235] fee burn makes sustained spam permanently costly.

These defenses are independent of the marginal fee level.

## Attack economics

A 2 MB block holds ~1,000 minimal shielded transactions (~2,000 logical
actions). At 75-second blocks (~48 blocks/hour), the hourly cost to fill
blocks scales linearly with `marginal_fee` and ZEC price:

| Scenario                      | `marginal_fee` | ZEC price  | Hourly cost      |
|-------------------------------|----------------|------------|------------------|
| ZIP 317 design point          | 5,000          | *P*        | *C*              |
| Price at *N* x *P*            | 5,000          | *N* x *P*  | *N* x *C*        |
| **Proposed at *N* x *P***     | **1,000**      | *N* x *P*  | ***N* x *C* / 5**|

At *P* ~$30, *C* ~$144/hour. At *N* = 10 the proposed hourly cost (~$288)
exceeds the original design point by ~2x. Zebra's strict
`BLOCK_UNPAID_ACTION_LIMIT = 0` makes this table conservative: an attacker
cannot exploit the unpaid action budget to reduce spam costs.


# Deployment

## Ordering

Node relay policy updates should be deployed before or concurrently with wallet
updates. A transaction paying 2,000 zatoshis evaluated by a node still using
`marginal_fee = 5000` would compute:

$$\mathit{unpaid\_actions} = \max(2, 2) - \left\lfloor\frac{2000}{5000}\right\rfloor = 2 - 0 = 2$$

Such a transaction would still be relayed and mined (it counts against the
`block_unpaid_action_limit` budget of 50), but would incur the `low_fee_penalty`
in ZIP 401 mempool eviction on nodes that have not yet updated.

## Testnet

The reduced fee should be deployed on Testnet before Mainnet.

## Sunset clause

This ZIP expires 12 months after reaching Active status. At expiration, the
`marginal_fee` reverts to 5,000 zatoshis unless:

1. A follow-up ZIP renews or replaces this parameter change, or
2. A dynamic fee mechanism has reached Active status, in which case the static
   `marginal_fee` serves only as a fallback value.

The sunset ensures the reduced fee is re-evaluated as conditions change -- the
same failure mode that motivated this ZIP in the first place.


# Open issues

- The `Discussions-To` field needs a GitHub issue URL before this ZIP advances
  beyond Draft.
- Whether the 12-month sunset clause duration is appropriate.
- The node relay policy configuration option name and format need alignment
  with each node implementation's conventions (e.g. Zebra uses TOML
  configuration files, zcashd uses CLI flags).
- Coordination timeline with wallet teams for synchronized deployment.


# References

[^BCP14]: [Information on BCP 14 — "RFC 2119: Key words for use in RFCs to Indicate Requirement Levels" and "RFC 8174: Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words"](https://www.rfc-editor.org/info/bcp14)

[^protocol]: [Zcash Protocol Specification, Version 2025.6.3 [NU6.1] or later](protocol/protocol.pdf)

[^zip-0235]: [ZIP 235: Remove 60% of Transaction Fees From Circulation](zip-0235)

[^zip-0313]: [ZIP 313: Reduce Conventional Transaction Fee to 1000 zatoshis](zip-0313)

[^zip-0317]: [ZIP 317: Proportional Transfer Fee Mechanism](zip-0317)

[^zip-0401]: [ZIP 401: Addressing Mempool Denial-of-Service](zip-0401)

[^madars-1]: [Madars Virza, concrete soft-fork proposal](https://forum.zcashcommunity.com/t/zip-reduce-default-shielded-transaction-fee-to-1000-zats/37566/89)
