//! Response type for the `z_getstandardfee` RPC.
//!
//! The fee estimation algorithm lives in zebrad; Zaino is a thin proxy.
//! This struct must mirror zebrad's `ZGetStandardFeeResponse` field-for-field
//! (`zebra-rpc/src/methods/types/z_getstandardfee.rs`).

use std::convert::Infallible;

use serde::{Deserialize, Serialize};
use zaino_fetch::jsonrpsee::connector::ResponseToError;

/// Response type for the `z_getstandardfee` RPC method.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct StandardFeesResponse {
    /// Recommended fee per logical action, in zatoshis.
    pub standard_fee: u64,
    /// Priority fee per logical action, in zatoshis. Always present.
    pub priority_fee: u64,
    /// Whether the network is currently congested. When true, paying the
    /// priority fee actually buys faster inclusion.
    pub congested: bool,
    /// Estimator version identifier.
    pub version: String,
    /// Chain tip height at the time of computation.
    pub height: u64,
    /// URI pointing to the estimator specification.
    pub how_is_this_calculated: String,
}

impl ResponseToError for StandardFeesResponse {
    type RpcError = Infallible;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_response_matches_zebrad_wire_shape() {
        // Canonical response shape produced by zebrad's z_getstandardfee.
        // If this test breaks, the proxy is silently dropping or renaming fields.
        let wire = r#"{"standard_fee":5000,"priority_fee":20000,"congested":false,"version":"v0","height":3375493,"how_is_this_calculated":"https://zips.z.cash/zip-XXXX#fee-estimator-v0"}"#;

        let parsed: StandardFeesResponse =
            serde_json::from_str(wire).expect("zebrad wire shape deserializes");
        assert_eq!(parsed.standard_fee, 5000);
        assert_eq!(parsed.priority_fee, 20000);
        assert!(!parsed.congested);

        let reserialized = serde_json::to_string(&parsed).expect("response serializes");
        assert_eq!(reserialized, wire);
    }
}
