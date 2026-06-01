//! Types for the `z_getfeedistribution` RPC.

use std::collections::BTreeMap;

use derive_getters::Getters;
use derive_new::new;

/// A response to a `z_getfeedistribution` RPC request.
///
/// Reports how the per-action fees paid by real transactions in the estimator
/// lookback window split across the standard and priority tiers. The synthetic
/// floor-fee fill the estimator uses for `z_getstandardfee` is excluded here:
/// only mined, non-coinbase transactions are counted, so the figures describe
/// actual user behaviour.
#[derive(Clone, Debug, Eq, PartialEq, serde::Serialize, serde::Deserialize, Getters, new)]
pub struct ZGetFeeDistributionResponse {
    /// Standard fee per logical action, in zatoshis. Same value `z_getstandardfee` returns.
    #[getter(copy)]
    pub(crate) standard_fee: u64,

    /// Priority fee per logical action, in zatoshis. Always 10x the standard fee.
    #[getter(copy)]
    pub(crate) priority_fee: u64,

    /// Total number of real (mined, non-coinbase) transactions counted in the window.
    #[getter(copy)]
    pub(crate) total_tx_count: u64,

    /// Real transactions paying less than the standard fee per action.
    #[getter(copy)]
    pub(crate) below_standard_count: u64,

    /// Real transactions paying at least the standard fee but less than the
    /// priority fee, per action.
    #[getter(copy)]
    pub(crate) standard_count: u64,

    /// Real transactions paying at least the priority fee per action.
    #[getter(copy)]
    pub(crate) priority_tx_count: u64,

    /// Histogram of per-action fees bucketed to powers of 10: bucket (zatoshis)
    /// mapped to the count of real transactions in that bucket.
    pub(crate) distribution: BTreeMap<u64, u64>,

    /// Estimator version identifier.
    pub(crate) version: String,

    /// Chain tip height at the time of computation.
    #[getter(copy)]
    pub(crate) height: u64,

    /// URI pointing to the estimator specification.
    pub(crate) how_is_this_calculated: String,
}
