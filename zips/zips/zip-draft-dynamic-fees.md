    ZIP: Unassigned
    Title: Dynamic Fee Estimation via getstandardfee
    Owners: Mark Henderson <mark@shieldedlabs.net>
    Status: Draft
    Category: Standards / RPC
    Created: 2026-03-16
    License: MIT
    Discussions-To: <https://forum.zcashcommunity.com/c/technology/dynamic-fees/100>
    Pull-Request: <TBD>


# Terminology

The key words "MUST", "MUST NOT", "SHOULD", "SHOULD NOT", and "MAY" in this
document are to be interpreted as described in BCP 14 [^BCP14] when, and only
when, they appear in all capitals.

The terms "conventional transaction fee", "marginal fee", "logical actions",
and "grace actions" are as defined in ZIP 317. [^zip-0317]

The term "zatoshi" is defined as in the Zcash protocol specification.
[^protocol]


# Abstract

This ZIP specifies `getstandardfee`, a full node RPC endpoint (computed by
the full node, e.g. Zebra) that publishes a dynamic fee recommendation derived
from confirmed blocks. Indexers (e.g. Zaino, lightwalletd) relay the result to
wallets over gRPC. The recommendation is observational: it reflects what the
network has recently accepted, not what it will accept in the future. No
service-level guarantees are made or implied.


# Motivation

ZIP 317 [^zip-0317] defines a fixed marginal fee of 5,000 zatoshis per logical
action. This fee was calibrated to a ZEC price and network conditions that no
longer hold. As ZEC's price rises and adoption increases, the fixed fee becomes
increasingly expensive in fiat terms while offering no mechanism to adjust
downward during periods of low demand, or upward during congestion.

A dynamic fee recommendation, computed from public on-chain data, allows
wallets to suggest fees that reflect current network conditions. By publishing
the recommendation through a standard full node RPC endpoint, all wallets and
services can converge on the same fee signal, reducing fee entropy and
improving privacy.

This ZIP does not propose consensus changes. It defines an RPC interface and a
reference fee estimation algorithm (Fee Estimator v0) that the full node
computes from confirmed block data and exposes via RPC; indexers relay the
result to connected wallets as a policy recommendation.


# Privacy Implications

**Fee entropy.** Powers-of-10 bucketing limits the set of possible fee values,
reducing the information content of a transaction's fee. This is a strict
improvement over the status quo where wallets may independently compute varying
fee amounts.

**Timing signals.** The lookback window is long enough (~1 hour) and the
bucketing coarse enough that fee changes are infrequent. This limits the
ability of an observer to correlate transactions with specific fee-change
events.

**No mempool dependency.** The estimator uses only confirmed block data. It
does not reveal or depend on mempool contents.


# Requirements

The fee recommendation:

- Is computable from public, confirmed block data only.
- Does not require access to mempool state or any non-public information.
- Does not leak information that could be used to segment or fingerprint users
  beyond what is already public.
- Produces stable outputs -- fee changes are infrequent under normal
  conditions.
- Is computationally inexpensive and does not degrade indexer performance.
- Is versioned so that estimator changes are explicit and detectable.


# Non-requirements

This endpoint is observational. Specifically:

1. A returned `standard_fee` is not a guarantee of inclusion in any block.
2. The endpoint does not constitute a service-level agreement between the
   wallet and the user.
3. The fee recommendation reflects recent confirmed history. It does not
   predict future miner behavior.


# Status

This ZIP defines a **v0 reference candidate** for `getstandardfee`. The algorithm
parameters specified below are currently fixed in the canonical Zebra implementation,
but at least three choices are open to **optional refinement** &mdash; they would change
only if observed user behavior warrants it. Independent analysis and simulation inform
how:

- **Oracle:** v0 uses an action-weighted median; median-of-medians has been proposed
  as a more manipulation-resistant alternative. Adversarial simulation compares both
  under median-poisoning and miner-self-dealing strategies.
- **Floor fee:** v0 uses 1,000 zats per action, which assumes the marginal-fee reduction
  draft (5,000 → 1,000) has shipped on mainnet. Until that draft lands, the operative
  floor on mainnet is 5,000. Anti-spam resilience depends on the floor.
- **Quantization:** v0 uses powers-of-10 bucketing. Alternatives (powers of √10,
  continuous-with-dispersion, alternative bucket scales) are under consideration;
  coarse-bucket flip timing is a potential privacy signal.

Implementations of v0 should match the algorithm below exactly. If user-behavior data
prompts a refinement to any of these choices, the `version` field will increment (e.g.
0 → 1) and a new conformance vectors file will be published.

Exploratory sweep results (2026-05-09) and the supporting analysis are documented at
[fees.shieldedinfra.net/research/](https://fees.shieldedinfra.net/research/).

# Specification

## RPC Method

`getstandardfee`

Parameters: None.

Result: A JSON object with the following fields:

| Field          | Type    | Required | Description                                       |
|----------------|---------|----------|---------------------------------------------------|
| `standard_fee` | integer | Yes      | Recommended fee per logical action, in zatoshis.  |
| `priority_fee` | integer | Yes      | Priority lane fee per logical action, in zatoshis. Always `priority_multiplier` times `standard_fee`. |
| `congested`    | boolean | Yes      | Whether every block in the lookback window was full, so that no synthetic fill was needed. |
| `version`      | integer | Yes      | Estimator version identifier (e.g. `0`).          |


### Example Response

```json
{
  "standard_fee": 1000,
  "priority_fee": 10000,
  "congested": false,
  "version": 0
}
```

### The priority lane

`priority_fee` = `standard_fee` × `priority_multiplier`, where
`priority_multiplier` = 10.

The multiplier MUST NOT exceed the `weight_ratio_cap` of the RECOMMENDED block
template construction algorithm in ZIP 317 [^zip-0317]. A multiplier above the
cap would recommend a fee for which conforming block producers deliver no
corresponding increase in selection probability. ZIP 317 defines
`weight_ratio_cap` = 4; raising it to 10 is specified separately.
[^zip-draft-weight-ratio-cap]

`congested` reports whether the priority lane currently buys anything. When
every block in the lookback window was full, no synthetic fill was required and
block space is genuinely scarce. When `congested` is false, the standard and
priority lanes see equivalent inclusion times and wallets SHOULD NOT present
priority as buying speed.

### Wallet Integration

Wallets SHOULD present the fee recommendation to users as an estimate, not a
promise. Suggested UX language: "estimated fee" or "recommended fee", never
"required fee" or "guaranteed fee".

Wallets MUST NOT treat the returned fee as mandatory -- users MUST retain the
ability to override.

## Fee Estimator v0

This section defines the reference algorithm for computing `standard_fee`.
Implementations MUST produce identical outputs for the same chain state when
using the same estimator version. Conformance is verified by published test
vectors (see [Test Vectors](#test-vectors)).


### Parameters

| Parameter      | Value | Description                                                        |
|----------------|-------|--------------------------------------------------------------------|
| B              | 50    | Lookback window size in blocks                                     |
| b              | 5     | Chain-tip buffer in blocks (3× longer if ZIP 218 ships, see below) |
| floor          | 1,000 | Synthetic transaction fee per action, in zatoshis                 |
| block_capacity | 2 MB  | Maximum block size for synthetic fill computation                 |
| priority_multiplier | 10 | Multiple of `standard_fee` defining the priority lane          |


### Lookback Window

Let *h* be the current chain tip height. The lookback window *L* is defined as
the *B* consecutive blocks ending *b* blocks before the tip:

> *L* = { B<sub>h-B-b+1</sub>, ..., B<sub>h-b</sub> }

The buffer *b* guards against chain-tip volatility due to reorgs.


### Transaction Set

For each block in *L*, collect all non-coinbase transactions. For each
transaction *tx*, compute:

- `logical_actions(tx)` -- as defined in ZIP 317. [^zip-0317]
- `fee_per_action(tx)` = floor( *tx.fee* / max( *grace_actions*,
  *logical_actions(tx)* ) )

This yields a multiset *F* of per-action fees from confirmed transactions.


### Synthetic Fill

To model the network as always occupied (providing a fee signal even during
low-traffic periods), compute the unused capacity in each block and fill it
with synthetic transactions:

1. For each block in *L*, compute `avg_tx_size` as the mean transaction size
   in bytes across all non-coinbase transactions in *L*.
2. For each block, compute `unused_bytes` = `block_capacity` - `block_size`.
3. `synthetic_count` = floor( `unused_bytes` / `avg_tx_size` ) for each block.
4. Add `synthetic_count` entries of `floor` to the fee multiset *F* for each
   block.

If a block contains no non-coinbase transactions, use `avg_tx_size` from the
remaining blocks in *L*. If no block in *L* contains non-coinbase
transactions, the estimator SHOULD return the current ZIP 317 conventional fee
as `standard_fee`.

> [!note]
> **Interaction with ZIP 218.** Synthetic fill is currently sized by bytes
> (`block_capacity` / `avg_tx_size`). If ZIP 218 ships, synthetic fill MAY
> instead be sized by ZIP 128 action limits, modeling unused capacity in
> actions rather than bytes. ZIP 218 has not shipped as of this draft.


### Median Computation

Sort *F* in ascending order. The raw fee estimate is the median value of *F*.


### Powers-of-10 Bucketing

Round the raw median to the nearest power of 10:

- Let *raw* be the raw median.
- Let *log* = log<sub>10</sub>(*raw*).
- Let *low* = 10<sup>floor(*log*)</sup>.
- Let *high* = 10<sup>ceil(*log*)</sup>.
- If *raw* - *low* &le; *high* - *raw*, then *bucketed* = *low*; else
  *bucketed* = *high*.

The `standard_fee` is max(*floor*, *bucketed*).


## Estimator Versioning

The `version` field identifies which algorithm produced the result. This
allows:

- Wallets to detect when an indexer's estimator has changed.
- Test vectors to be scoped to a specific algorithm version.
- Gradual migration: indexers can support multiple versions during transitions.

When the estimator algorithm changes (parameters, formula, or structure), the
`version` integer MUST change. Versions increment monotonically: `0`, `1`,
etc.

Indexers MAY relay a `version` parameter on the RPC call to request a
specific estimator. If unsupported or unrecognized, the full node SHOULD return
the default (latest) version.


## Heuristics

The `standard_fee` answers "what should I pay?" It does not answer "what does
paying more, or less, reveal about me?" That second question matters: the
per-transaction privacy cost of deviating from the common fee is not uniform.
A user in a time window where almost nobody pays a higher "priority" fee leaks
far more by paying it than a user in a window where priority payment is common --
the same one-bit choice is much more identifying in the sparse case.

This generalizes to a single observable: the **anonymity set of a fee choice**.
For a given fee level, that is the number of confirmed logical actions in the
lookback window that paid the same fee. A fee shared by many recent actions
blends in; one shared by few stands out. This is the rigorous form of the
intuition above, and -- like `standard_fee` itself -- it is derived entirely
from confirmed block data and is observational: it characterizes the window just
past, not the block into which a transaction will actually be mined.

The aim of this section is to sketch, not to specify, the heuristics a future
estimator version could expose so wallets can give users an informed view of the
privacy impact of a fee choice *before* they send. Any such heuristic would be
returned as one or more additional fields on `getstandardfee`, gated behind a
future `version`; v0 returns none of them. The candidate signals below are all
views of the same anonymity-set quantity:

- **Tier occupancy.** For each fee level in use (at minimum `standard_fee` and
  any higher "priority" levels), how many recent actions paid it -- so a wallet
  can warn when a chosen tier is sparsely populated, and therefore identifying.
- **Congestion.** Whether organic transactions have displaced synthetic fill
  across the window (every block full), indicating whether paying above
  `standard_fee` actually buys faster inclusion rather than only a larger fee
  footprint.
- **Dispersion.** A coarse summary of how spread out fee choices currently are
  ("fee weather"), conveying at a glance whether the network has converged on a
  single fee or fragmented across many.

A returned heuristic is itself a disclosure. A fine-grained fee distribution
could help an adversary model the network, or coach a user toward a deceptively
"safe" fee that an attacker has anticipated. A future ZIP specifying these fields
must weigh their resolution against that risk, keep them coarse by default, and
publish exact derivations and conformance vectors before any wallet relies on
them. None of this is normative here.

### UX framing: the "Priority" lane

When wallets surface a faster-but-pricier option, the suggested label is
**"Priority"** and the suggested metaphor is **airport security**: during normal
operation both the standard and priority lanes move quickly, and priority is
meaningfully faster *only* during congestion. Framing it this way sets the
correct expectation -- most of the time priority buys nothing but a larger fee
footprint -- and pairs naturally with the privacy guidance above.


## Test Vectors

Published test vectors consist of:

1. A chain slice: an ordered sequence of blocks with their full transaction
   data.
2. The expected `getstandardfee` output for that slice under each estimator
   version.

Conformance requirement: given the same chain slice, all implementations using
the same estimator version MUST produce byte-identical JSON output (after
normalization of field ordering and whitespace). This applies across indexer
implementations (e.g. Zaino, lightwalletd) and any offline or full-node
implementations of the algorithm.

Test vector sets will be published alongside this ZIP at \<TBD\>.


# Rationale

## Why powers-of-10 bucketing

Bucketing reduces fee entropy and information leakage (privacy goal), makes fee
changes infrequent (UX goal), and ensures fees are divisible by 5 for
compatibility with ZIP 235's NSM contribution rules. [^zip-0235] Continuous fee
values would allow observers to distinguish transactions by their exact fee,
potentially fingerprinting wallet implementations or revealing urgency.

## Why synthetic fill

Without synthetic fill, the estimator would produce no signal during low-traffic
periods -- the median of an empty set is undefined, and the median of a sparse
set is noisy. Synthetic transactions at the `floor` fee model the network's
unused capacity and anchor the fee recommendation to a predictable baseline.
The estimator only rises above the floor when organic demand displaces the
synthetics.

## Why the median

The median is robust to outliers. An attacker cannot meaningfully shift the fee
recommendation without controlling >50% of per-action fee observations in the
lookback window. Mean-based estimators are vulnerable to manipulation by a
small number of high-fee transactions.

## Why a 50-block lookback window

At Zcash's 75-second block interval, 50 blocks represents approximately 1 hour
of network activity. This is long enough to smooth out short-term variance, but
short enough to respond to sustained demand changes within a reasonable horizon.

## Why a 5-block chain-tip buffer

Reorgs at the chain tip are common (1-2 blocks). The buffer ensures the
estimator is not recomputed on data that may be rolled back. A 5-block buffer
(~6 minutes) provides margin against typical reorg depths without introducing
excessive latency.

If ZIP 218 ships and shortens the block interval, *b* should be roughly tripled
(to ~15 blocks) to preserve the same wall-clock margin against reorgs.

## Interaction with node relay policy

The fee estimator observes confirmed blocks, which reflect the intersection of
mempool policy and miner behavior. Zebra currently enforces
`BLOCK_UNPAID_ACTION_LIMIT = 0` in its mempool acceptance logic, meaning every
transaction in the mempool has paid at least its full conventional fee as
defined by ZIP 317. [^zip-0317] This is stricter than the spec value of 50,
which would permit a limited number of underpaying transactions per block.

Under Zebra's current policy, the fee distribution observed by the estimator is
homogeneous: nearly all transactions pay exactly the conventional fee. The
estimator correctly reflects this -- producing a `standard_fee` at the floor
(100 zatoshis, bucketed to the conventional fee level) during uncongested
periods.

If a future change aligns Zebra's relay policy with the spec value of 50, the
fee distribution would include some underpaying transactions, which would lower
the observed median. The estimator's synthetic fill mechanism compensates for
this: synthetic transactions at the `floor` fee already model the low end of
the distribution. The median would still be anchored by the majority of
full-paying transactions.

The estimator's behavior is correct under both the current Zebra policy and the
spec value. However, implementors should be aware that fee distribution
characteristics may change if relay policy changes, and test vectors should
cover both scenarios.


# Security Considerations

## Denial of Service

**Spam resistance.** Synthetic fill ensures that the fee floor holds during
low-traffic periods. An attacker must sustain enough transaction volume to
displace synthetics across the full lookback window before the fee rises
organically.

**Manipulation resistance.** The median is robust to outliers. An attacker
cannot meaningfully shift the fee recommendation without controlling >50% of
per-action fee observations in the lookback window.

**ZIP 317 compatibility.** The action-based accounting from ZIP 317
[^zip-0317] remains in effect. An attacker cannot generate large-in-kb
transactions cheaply to skew the average transaction size used for synthetic
fill.

## Miner Incentives

This ZIP does not change consensus rules or block template construction.
Miners remain free to include transactions at any fee. The recommendation is a
coordination signal: if wallets converge on the recommended fee, miners benefit
from predictable fee behavior and reduced orphan risk from oversized mempools.


# Deployment

## Phase 1: Full node + indexer relay (Policy-only)

The full node (e.g. Zebra) computes `getstandardfee` and exposes it as an
informational RPC call. Indexers relay the result to wallets: Zaino re-exposes
the JSON-RPC method, and lightwalletd exposes it over gRPC. No consensus changes
or relay policy changes are required.

The reference implementation targets Zebra, with relay support in Zaino and
lightwalletd. Conformance across implementations is verified by the published
test vectors.

## Phase 2: Wallet Adoption

Wallets should begin using `getstandardfee` to inform fee selection UX.

## Future: Consensus

If a future ZIP proposes relay policy changes or consensus-level fee rules
(e.g. mandatory bucketing, fee floors, or expiry height constraints), those
rules will be specified in a separate ZIP. Such a ZIP may make the estimator's
output consensus-relevant, or may continue to treat it as the policy
recommendation defined here.


# Open issues

- The `Discussions-To` field should reference a GitHub issue URL in addition to
  or instead of the forum category.
- Test vector sets are TBD. At minimum, vectors should cover: an empty window,
  an all-synthetic window, a congestion threshold boundary, a bucketing
  boundary, and a window with mixed fee levels.
- The Heuristics section is a sketch, not a specification. The exact derivations,
  field shapes, and conformance vectors for any returned heuristic must be
  defined before a wallet relies on them.
- Reference implementation status and links (Zebra, Zaino, lightwalletd) should
  be added when available.
- Whether the estimator should account for the
  `BLOCK_UNPAID_ACTION_LIMIT` divergence between Zebra (0) and the ZIP 317
  spec (50), or whether this is purely a relay policy concern outside the
  estimator's scope.


# References

[^BCP14]: [Information on BCP 14 — "RFC 2119: Key words for use in RFCs to Indicate Requirement Levels" and "RFC 8174: Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words"](https://www.rfc-editor.org/info/bcp14)

[^protocol]: [Zcash Protocol Specification, Version 2025.6.3 [NU6.1] or later](protocol/protocol.pdf)

[^zip-0235]: [ZIP 235: Remove 60% of Transaction Fees From Circulation](zip-0235)

[^zip-0317]: [ZIP 317: Proportional Transfer Fee Mechanism](zip-0317)

[^zip-0401]: [ZIP 401: Addressing Mempool Denial-of-Service](zip-0401)

[^zip-draft-weight-ratio-cap]: [ZIP draft: Raise the Block Template Weight Ratio Cap to 10](zip-draft-weight-ratio-cap)

[^dynamic-fees-lab]: [Zcash Dynamic Fees Lab](https://github.com/ShieldedLabs/fee-playground)
