//! Types for the `z_getstandardfees` RPC.

use derive_getters::Getters;
use derive_new::new;

/// A response to a `z_getstandardfees` RPC request.
#[derive(Clone, Debug, Eq, PartialEq, serde::Serialize, serde::Deserialize, Getters, new)]
pub struct ZGetStandardFeesResponse {
    /// Recommended fee per logical action, in zatoshis.
    #[getter(copy)]
    pub(crate) standard_fee: u64,

    /// Priority fee per logical action, in zatoshis.
    /// Present only when the network is congested (all blocks in the lookback window are full).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) express_fee: Option<u64>,

    /// Estimator version identifier.
    pub(crate) version: String,

    /// Chain tip height at the time of computation.
    #[getter(copy)]
    pub(crate) height: u64,

    /// URI pointing to the estimator specification.
    pub(crate) how_is_this_calculated: String,
}
