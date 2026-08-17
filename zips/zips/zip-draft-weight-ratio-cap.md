    ZIP: Unassigned
    Title: Raise the Block Template Weight Ratio Cap to 10
    Owners: Mark Henderson <mark@shieldedlabs.net>
    Status: Draft
    Category: Standards / Mining
    Updates: ZIP 317
    Created: 2026-08-11
    License: MIT
    Discussions-To: <TBD>
    Pull-Request: <TBD>


# Terminology

The key words "MUST", "MUST NOT", "SHOULD NOT", and "RECOMMENDED" in this
document are to be interpreted as described in BCP 14 [^BCP14] when, and only
when, they appear in all capitals.

`weight_ratio_cap`, `weight_ratio`, and `conventional_fee` are as defined in
ZIP 317. [^zip-0317]


# Abstract

This ZIP modifies ZIP 317 [^zip-0317] by raising `weight_ratio_cap` from 4 to 10
in the RECOMMENDED block template construction algorithm. No fee paid by any user
changes; the only effect is on the maximum relative selection probability a
transaction can obtain by overpaying, and only when candidates exceed a block's
capacity.


# Motivation

ZIP 317 defines `weight_ratio_cap` = 4, so a transaction's selection weight is

$$\mathit{tx.weight\_ratio} = \min\!\left(\frac{\max(1,\, \mathit{tx.fee})}{\mathit{conventional\_fee}(\mathit{tx})},\, \mathit{weight\_ratio\_cap}\right)$$

and paying more than 4x the conventional fee buys no further advantage. ZIP 317
describes 4 as a compromise between no prioritization and arbitrary
prioritization by ability to pay: a chosen point, not a derived quantity.

Zebra's `getstandardfee` RPC publishes a standard fee recommendation. A
planned priority lane places the priority fee at 10x the standard fee, the
first step above standard on a powers-of-10 fee alphabet. Under a cap of 4, a
wallet charging a 10x priority fee would deliver at most 4x relative weight,
so 60% of the additional fee would buy nothing. Both `zebrad` and `zcashd` enforce the cap in their block template
code, so the mismatch exists in deployed software, not only in the
specification. Raising the cap to 10 means a user who pays for priority receives
what was purchased.


# Privacy Implications

This ZIP does not change the set of fee values wallets are recommended to pay,
so it does not change fee entropy or any value's anonymity set. It does increase
the value of paying priority under contention, which may increase adoption of
that lane. That effect is not unidirectional: a larger priority population raises
the lane's minimum anonymity set, while a more effective lane sharpens the
separation between users who pay for urgency and those who do not.

Wallets SHOULD NOT expose multipliers outside the published alphabet, which
would widen the fee value space and shrink each value's anonymity set.


# Specification

## Changes to ZIP 317

In the section **Recommended algorithm for block template construction** of
ZIP 317 [^zip-0317], the constant `weight_ratio_cap` = 4 is changed to
`weight_ratio_cap` = 10. The definition of `tx.weight_ratio` references the
constant and reflects the new value automatically. Every step of the algorithm
and every other ZIP 317 parameter are unchanged.

In **Rationale for block template construction algorithm**, the sentence giving
the rationale for choosing 4 is updated to 10, noting that the value matches the
priority tier of the fee alphabet, so a transaction paying the recommended
priority fee receives what it pays for and no more.

## Relation to the priority lane and the marginal fee

The priority multiplier recommended to wallets MUST NOT exceed
`weight_ratio_cap`. With this ZIP deployed a multiplier of up to 10 is honored in
full, and any future change to either value requires a change to the other.

This ZIP is independent of the marginal fee reduction [^zip-draft-marginal-fee]:
`weight_ratio` is a ratio of fee to conventional fee, so it is invariant under a
uniform change to `marginal_fee`, and the two may deploy in either order.

## Node configuration

Node implementations MUST support a configuration option overriding the
`weight_ratio_cap` used in block template construction, defaulting to 10, so
block producers can revert without a software update. This follows the precedent
of `blockunpaidactionlimit`. [^zip-0317]


# Rationale

**Why 10.** 10x is the first step above standard on a powers-of-10 alphabet, and
the only multiplier under which the lanes and the quantization agree: with
`marginal_fee` = 1,000 [^zip-draft-marginal-fee] the lanes are 1,000 and 10,000,
both exact rungs, whereas at 4x they are 1,000 and 4,000, which is not a rung.
That forces either a priority fee quantized away from what wallets charge or an
alphabet of 1,000 x 4^n. Removing the cap would convert discrete lanes into a
continuous auction; 8 or 16 reintroduce the mismatch in the other direction.

**The adversarial argument survives.** Of ZIP 317's two reasons that overpaying
gains no significant advantage, only the first depends on the cap: a bound of
`weight_ratio_cap` times a conventional-fee transaction's probability, loosening
from 4x to 10x but still a bound. The second, that *c* times the
fee on one transaction occupies less block space than *c* transactions and so
leaves more room for others, is cap-independent and carries most of the argument.
The advantage a higher cap does sharpen under contention is bounded: it buys at
most the current block, and standard-fee transactions keep non-zero weight.

**Inert absent contention.** The algorithm discriminates only when candidates
exceed the block size and sigop limits, so the change takes effect only under
sustained full blocks, the regime a priority lane exists for.

**No sunset clause.** Unlike the marginal fee, this parameter is not
price-sensitive and does not change what any user pays; its correct value follows
from the priority multiplier. Reversion is the operator override, applied
immediately and unilaterally with no effect on other participants.


# Deployment

Block producers MUST deploy this change before wallets recommend priority fees
above 4x the standard fee; the opposite order produces the failure this ZIP
exists to remove, where users pay 10x and receive 4x. This matches ZIP 317's
guidance that node policy changes SHOULD NOT precede block template changes.
Deploy on Testnet before Mainnet.

Use of the RECOMMENDED algorithm is voluntary. Under partial adoption a
transaction paying 10x receives 10x weight at upgraded producers and 4x
elsewhere, so the effect scales with their share of hashpower. Producers ordering
candidates greedily by fee are unaffected.


# References

[^BCP14]: [Information on BCP 14 — "RFC 2119: Key words for use in RFCs to Indicate Requirement Levels" and "RFC 8174: Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words"](https://www.rfc-editor.org/info/bcp14)

[^zip-0317]: [ZIP 317: Proportional Transfer Fee Mechanism](zip-0317)

[^zip-draft-marginal-fee]: [ZIP draft: Reduce Marginal Fee to 1000 Zatoshis](zip-draft-marginal-fee)
