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
    /// ZIP-317 logical actions.
    pub(crate) actions: u64,
    /// Fee per action = fee / max(grace_actions, actions), in zatoshis.
    pub(crate) fee_per_action: u64,
    /// Lane this transaction falls in: "standard", "priority", or "nonstandard".
    pub(crate) tier: String,
}

/// A response to a `z_getfeedistribution` RPC request.
///
/// Reports how the per-action fees paid by real (mined, non-coinbase)
/// transactions in the estimator lookback window split across the fee lanes.
/// Synthetic floor-fee fill is excluded, so the figures describe actual usage.
/// `transactions` is the per-transaction breakdown for the same window.
/// Shares the `z_getstandardfee` block walk.
#[allow(clippy::too_many_arguments)]
#[derive(Clone, Debug, Eq, PartialEq, serde::Serialize, serde::Deserialize, Getters, new)]
pub struct ZGetFeeDistributionResponse {
    /// Suggested standard fee per logical action, in zatoshis (the ZIP-317 conventional fee today).
    #[getter(copy)]
    pub(crate) standard_fee: u64,

    /// Priority fee per logical action, in zatoshis. Always 4x the standard fee.
    #[getter(copy)]
    pub(crate) priority_fee: u64,

    /// Total number of real (mined, non-coinbase) transactions in the window.
    #[getter(copy)]
    pub(crate) total_tx_count: u64,

    /// Transactions paying exactly the standard lane (the ZIP-317 conventional fee per action).
    #[getter(copy)]
    pub(crate) standard_count: u64,

    /// Transactions paying exactly the priority lane (4x the standard fee per action).
    #[getter(copy)]
    pub(crate) priority_count: u64,

    /// Transactions paying anything else (under, over, or between the two lanes).
    #[getter(copy)]
    pub(crate) nonstandard_count: u64,

    /// Histogram of per-action fees bucketed to the fee alphabet (5000 * 4^n):
    /// bucket (zatoshis) mapped to the count of real transactions in that bucket.
    pub(crate) distribution: BTreeMap<u64, u64>,

    /// Per-transaction breakdown for the window (capped). If shorter than
    /// `total_tx_count`, it was truncated.
    pub(crate) transactions: Vec<FeeSample>,

    /// Estimator version identifier.
    pub(crate) version: String,

    /// Chain tip height at the time of computation.
    #[getter(copy)]
    pub(crate) height: u64,

    /// URI pointing to the estimator specification.
    pub(crate) how_is_this_calculated: String,
}
