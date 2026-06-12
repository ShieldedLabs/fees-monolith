//! Types for the `z_getfeedistribution` RPC.

use std::collections::BTreeMap;

use derive_getters::Getters;
use derive_new::new;

/// A single mined transaction sampled from the estimator lookback window.
#[derive(Clone, Debug, Eq, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct FeeSample {
    /// Transaction id (hex).
    pub(crate) txid: String,
    /// Total fee paid, in zatoshis.
    pub(crate) fee: u64,
    /// ZIP-317 logical (conventional) actions.
    pub(crate) actions: u64,
    /// Fee per action = fee / actions, in zatoshis.
    pub(crate) fee_per_action: u64,
    /// Lane this transaction falls in: "standard", "priority", or "nonstandard".
    pub(crate) tier: String,
}

/// A response to a `z_getfeedistribution` RPC request.
///
/// Reports how the per-action fees paid by real (mined, non-coinbase)
/// transactions in the estimator lookback window split across the fee lanes,
/// alongside a histogram of per-action fees bucketed to powers of ten and the
/// per-transaction breakdown. Shares the `z_getstandardfees` block walk.
#[derive(Clone, Debug, Eq, PartialEq, serde::Serialize, serde::Deserialize, Getters, new)]
pub struct ZGetFeeDistributionResponse {
    /// Suggested standard fee per logical action, in zatoshis.
    #[getter(copy)]
    pub(crate) standard_fee: u64,

    /// Priority fee per logical action, in zatoshis.
    #[getter(copy)]
    pub(crate) priority_fee: u64,

    /// Total number of real (mined, non-coinbase) transactions in the window.
    #[getter(copy)]
    pub(crate) total_tx_count: u64,

    /// Transactions whose per-action fee bucket equals the standard lane.
    #[getter(copy)]
    pub(crate) standard_count: u64,

    /// Transactions whose per-action fee bucket equals the priority lane.
    #[getter(copy)]
    pub(crate) priority_count: u64,

    /// Transactions in any other bucket (under, over, or between the lanes).
    #[getter(copy)]
    pub(crate) nonstandard_count: u64,

    /// Histogram of per-action fees bucketed to powers of ten:
    /// bucket (zatoshis) mapped to the count of real transactions in it.
    pub(crate) distribution: BTreeMap<u64, u64>,

    /// Per-transaction breakdown for the window (capped).
    pub(crate) transactions: Vec<FeeSample>,

    /// Estimator version identifier.
    pub(crate) version: String,

    /// Chain tip height at the time of computation.
    #[getter(copy)]
    pub(crate) height: u64,
}
