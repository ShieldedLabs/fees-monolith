//! Types for the `z_getstandardfee` RPC.

use derive_getters::Getters;
use derive_new::new;

/// A response to a `z_getstandardfee` RPC request.
#[derive(Clone, Debug, Eq, PartialEq, serde::Serialize, serde::Deserialize, Getters, new)]
pub struct ZGetStandardFeeResponse {
    /// Recommended fee per logical action, in zatoshis.
    #[getter(copy)]
    pub(crate) standard_fee: u64,

    /// Priority fee per logical action, in zatoshis. Always 10× the standard fee.
    /// Wallets may surface this as a higher-priority option for users who want
    /// faster inclusion when the network is congested.
    #[getter(copy)]
    pub(crate) priority_fee: u64,

    /// Whether the network is currently congested. When true, paying the priority
    /// fee actually buys faster inclusion; when false, both tiers see equivalent
    /// inclusion times. Determined by whether all blocks in the lookback window
    /// were full (no synthetic floor-fee entries needed to fill capacity).
    #[getter(copy)]
    pub(crate) congested: bool,

    /// Estimator version identifier.
    pub(crate) version: String,

    /// Chain tip height at the time of computation.
    #[getter(copy)]
    pub(crate) height: u64,

    /// URI pointing to the estimator specification.
    pub(crate) how_is_this_calculated: String,
}
