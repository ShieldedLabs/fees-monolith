//! Fee Estimator v0 — implements the dynamic fee estimation algorithm
//! specified in the `z_getstandardfees` ZIP.
//!
//! The estimator computes a fee recommendation from confirmed block data only.
//! It is designed to run at the indexer layer with no consensus or full-node changes.

use serde::{Deserialize, Serialize};
use zebra_rpc::{
    client::{Input, TransactionObject},
    methods::{GetBlock, GetBlockTransaction},
};

/// ZIP 317 conventional fee per logical action (5000 zatoshis).
const ZIP_317_CONVENTIONAL_FEE: u64 = 5000;

/// ZIP 317 grace actions — minimum logical actions for fee computation.
const GRACE_ACTIONS: u64 = 2;

/// Response type for the `z_getstandardfees` RPC method.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct StandardFeesResponse {
    /// Recommended fee per logical action, in zatoshis.
    pub standard_fee: u64,
    /// Priority fee per logical action, in zatoshis. Present only when congested.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub express_fee: Option<u64>,
    /// Estimator version identifier.
    pub version: String,
    /// Chain tip height at the time of computation.
    pub height: u64,
    /// URI pointing to the estimator specification.
    pub how_is_this_calculated: String,
}

/// Per-block data consumed by the fee estimator.
#[derive(Clone, Debug)]
pub struct BlockFeeData {
    /// Total block size in bytes.
    pub size_bytes: u64,
    /// Non-coinbase transactions in this block.
    pub transactions: Vec<TxFeeData>,
}

/// Per-transaction data consumed by the fee estimator.
#[derive(Clone, Debug)]
pub struct TxFeeData {
    /// Transaction fee in zatoshis.
    pub fee_zatoshis: u64,
    /// Serialized transaction size in bytes.
    pub size_bytes: u64,
    /// ZIP 317 logical actions count.
    pub logical_actions: u64,
}

/// Fee Estimator v0 parameters and computation.
#[derive(Clone, Debug)]
pub struct FeeEstimatorV0 {
    /// Lookback window size in blocks.
    pub lookback_window: u64,
    /// Chain-tip buffer in blocks.
    pub tip_buffer: u64,
    /// Synthetic transaction fee per action, in zatoshis.
    pub floor: u64,
    /// Maximum block size for synthetic fill computation, in bytes.
    pub block_capacity: u64,
    /// Multiplier applied to standard_fee for the express tier.
    pub express_multiplier: u64,
}

impl Default for FeeEstimatorV0 {
    fn default() -> Self {
        Self {
            lookback_window: 50,
            tip_buffer: 5,
            floor: 1000,
            block_capacity: 2_000_000,
            express_multiplier: 10,
        }
    }
}

impl FeeEstimatorV0 {
    /// The total number of blocks needed from the chain (window + buffer).
    pub fn required_depth(&self) -> u64 {
        self.lookback_window + self.tip_buffer
    }

    /// Compute the fee recommendation from a slice of block data.
    ///
    /// `blocks` must contain exactly `lookback_window` blocks, ordered by ascending height.
    /// The caller is responsible for selecting the correct window (skipping the tip buffer).
    /// `tip_height` is the actual chain tip height (used for the response).
    pub fn compute(&self, blocks: &[BlockFeeData], tip_height: u64) -> StandardFeesResponse {
        // Edge case: no blocks provided
        if blocks.is_empty() {
            return self.fallback_response(tip_height);
        }

        // Collect all non-coinbase transactions across the window
        let all_txs: Vec<&TxFeeData> = blocks
            .iter()
            .flat_map(|b| b.transactions.iter())
            .collect();

        // If no non-coinbase transactions in the entire window, return ZIP 317 default
        if all_txs.is_empty() {
            return self.fallback_response(tip_height);
        }

        // Compute average transaction size across all non-coinbase txs in the window
        let total_tx_bytes: u64 = all_txs.iter().map(|tx| tx.size_bytes).sum();
        let avg_tx_size = total_tx_bytes / all_txs.len() as u64;
        // Guard against zero (shouldn't happen with non-empty txs, but be safe)
        let avg_tx_size = avg_tx_size.max(1);

        // Build the fee multiset: real fees + synthetic fills
        let mut fee_multiset: Vec<u64> = Vec::new();
        let mut total_synthetic_count: u64 = 0;

        for block in blocks {
            // Add real transaction fees (fee_per_action)
            for tx in &block.transactions {
                let effective_actions = GRACE_ACTIONS.max(tx.logical_actions);
                let fee_per_action = tx.fee_zatoshis / effective_actions;
                fee_multiset.push(fee_per_action);
            }

            // Compute synthetic fill for this block
            let unused_bytes = self.block_capacity.saturating_sub(block.size_bytes);
            let synthetic_count = unused_bytes / avg_tx_size;
            total_synthetic_count += synthetic_count;

            for _ in 0..synthetic_count {
                fee_multiset.push(self.floor);
            }
        }

        // Edge case: empty multiset (all blocks full, no txs somehow)
        if fee_multiset.is_empty() {
            return self.fallback_response(tip_height);
        }

        // Sort and compute median
        fee_multiset.sort_unstable();
        let raw_median = median(&fee_multiset);

        // Powers-of-10 bucketing
        let bucketed = bucket_to_power_of_10(raw_median);
        let standard_fee = self.floor.max(bucketed);

        // Congestion detection
        let express_fee = if total_synthetic_count == 0 {
            Some(standard_fee * self.express_multiplier)
        } else {
            None
        };

        StandardFeesResponse {
            standard_fee,
            express_fee,
            version: "v0".to_string(),
            height: tip_height,
            how_is_this_calculated: "https://zips.z.cash/zip-XXXX#fee-estimator-v0".to_string(),
        }
    }

    /// Fallback response when insufficient data is available.
    fn fallback_response(&self, tip_height: u64) -> StandardFeesResponse {
        StandardFeesResponse {
            standard_fee: ZIP_317_CONVENTIONAL_FEE,
            express_fee: None,
            version: "v0".to_string(),
            height: tip_height,
            how_is_this_calculated: "https://zips.z.cash/zip-XXXX#fee-estimator-v0".to_string(),
        }
    }
}

/// Compute the median of a sorted slice.
fn median(sorted: &[u64]) -> u64 {
    let len = sorted.len();
    if len == 0 {
        return 0;
    }
    if len % 2 == 1 {
        sorted[len / 2]
    } else {
        // Average of two middle values, rounding down
        (sorted[len / 2 - 1] + sorted[len / 2]) / 2
    }
}

/// Round a value to the nearest power of 10.
///
/// If equidistant, rounds down (toward the lower power of 10).
fn bucket_to_power_of_10(raw: u64) -> u64 {
    if raw == 0 {
        return 0;
    }

    let log = (raw as f64).log10();
    let low = 10u64.pow(log.floor() as u32);
    let high = 10u64.pow(log.ceil() as u32);

    if raw - low <= high - raw {
        low
    } else {
        high
    }
}

/// Compute ZIP 317 logical actions from transaction component counts.
///
/// `logical_actions = max(tin, tout) + sapling_spends + sapling_outputs + orchard_actions`
pub fn compute_logical_actions(
    transparent_inputs: usize,
    transparent_outputs: usize,
    sapling_spends: usize,
    sapling_outputs: usize,
    orchard_actions: usize,
) -> u64 {
    let transparent = transparent_inputs.max(transparent_outputs);
    (transparent + sapling_spends + sapling_outputs + orchard_actions) as u64
}

/// Extract [`BlockFeeData`] from a zebra-rpc [`GetBlock::Object`].
///
/// Skips coinbase transactions. Returns `None` if the block is raw (verbosity=0).
pub fn block_fee_data_from_getblock(block: &GetBlock) -> Option<BlockFeeData> {
    match block {
        GetBlock::Object(boxed) => {
            let block_size = boxed.size().unwrap_or(0) as u64;
            let mut transactions = Vec::new();

            for tx_entry in boxed.tx() {
                if let GetBlockTransaction::Object(txo) = tx_entry {
                    // Skip coinbase transactions
                    let is_coinbase = txo.inputs().iter().any(|input| {
                        matches!(input, Input::Coinbase { .. })
                    });
                    if is_coinbase {
                        continue;
                    }

                    let tx_data = tx_fee_data_from_transaction(txo);
                    transactions.push(tx_data);
                }
            }

            Some(BlockFeeData {
                size_bytes: block_size,
                transactions,
            })
        }
        GetBlock::Raw(_) => None,
    }
}

/// Extract [`TxFeeData`] from a zebra-rpc [`TransactionObject`].
pub fn tx_fee_data_from_transaction(txo: &TransactionObject) -> TxFeeData {
    let tx_size = txo.size().unwrap_or(0) as u64;

    // Compute fee: sum(transparent_inputs) - sum(transparent_outputs)
    //              + sapling_value_balance + orchard_value_balance
    //
    // value_balance is defined as spends - outputs, so it contributes positively to fee.
    let input_total: i64 = txo
        .inputs()
        .iter()
        .filter_map(|input| match input {
            Input::NonCoinbase { value_zat, .. } => *value_zat,
            Input::Coinbase { .. } => None,
        })
        .sum();

    let output_total: i64 = txo.outputs().iter().map(|out| out.value_zat()).sum();

    let sapling_value_balance = txo.value_balance_zat().unwrap_or(0);

    let orchard_value_balance = txo
        .orchard()
        .as_ref()
        .map(|o| o.value_balance_zat())
        .unwrap_or(0);

    // fee = inputs - outputs + sapling_balance + orchard_balance
    // All value_balance fields are (spends - outputs), so positive means more going in.
    let fee = (input_total - output_total + sapling_value_balance + orchard_value_balance).max(0)
        as u64;

    // Compute logical actions
    let transparent_inputs = txo
        .inputs()
        .iter()
        .filter(|i| matches!(i, Input::NonCoinbase { .. }))
        .count();
    let transparent_outputs = txo.outputs().len();
    let sapling_spends = txo.shielded_spends().len();
    let sapling_outputs = txo.shielded_outputs().len();
    let orchard_actions = txo
        .orchard()
        .as_ref()
        .map(|o| o.actions().len())
        .unwrap_or(0);

    let logical_actions = compute_logical_actions(
        transparent_inputs,
        transparent_outputs,
        sapling_spends,
        sapling_outputs,
        orchard_actions,
    );

    TxFeeData {
        fee_zatoshis: fee,
        size_bytes: tx_size,
        logical_actions,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bucket_to_power_of_10() {
        assert_eq!(bucket_to_power_of_10(1), 1);
        assert_eq!(bucket_to_power_of_10(5), 1); // 5 - 1 = 4 <= 10 - 5 = 5
        assert_eq!(bucket_to_power_of_10(6), 10); // 6 - 1 = 5 > 10 - 6 = 4
        assert_eq!(bucket_to_power_of_10(10), 10);
        assert_eq!(bucket_to_power_of_10(50), 10); // 50 - 10 = 40 <= 100 - 50 = 50
        assert_eq!(bucket_to_power_of_10(51), 10); // 51 - 10 = 41 <= 100 - 51 = 49
        assert_eq!(bucket_to_power_of_10(55), 10); // 55 - 10 = 45 <= 100 - 55 = 45 (tie → low)
        assert_eq!(bucket_to_power_of_10(56), 100); // 56 - 10 = 46 > 100 - 56 = 44
        assert_eq!(bucket_to_power_of_10(100), 100);
        assert_eq!(bucket_to_power_of_10(150), 100);
        assert_eq!(bucket_to_power_of_10(550), 100); // 550 - 100 = 450 <= 1000 - 550 = 450 (tie → low)
        assert_eq!(bucket_to_power_of_10(551), 1000); // 551 - 100 = 451 > 1000 - 551 = 449
        assert_eq!(bucket_to_power_of_10(999), 1000);
        assert_eq!(bucket_to_power_of_10(1000), 1000);
        assert_eq!(bucket_to_power_of_10(5000), 1000);
        assert_eq!(bucket_to_power_of_10(5500), 1000); // tie → low
        assert_eq!(bucket_to_power_of_10(5501), 10000);
        assert_eq!(bucket_to_power_of_10(0), 0);
    }

    #[test]
    fn test_median() {
        assert_eq!(median(&[1, 2, 3]), 2);
        assert_eq!(median(&[1, 2, 3, 4]), 2); // (2+3)/2 = 2 (floor)
        assert_eq!(median(&[1, 2, 3, 4, 5]), 3);
        assert_eq!(median(&[100]), 100);
        assert_eq!(median(&[]), 0);
    }

    #[test]
    fn test_compute_logical_actions() {
        // Pure transparent: max(2 in, 3 out) = 3
        assert_eq!(compute_logical_actions(2, 3, 0, 0, 0), 3);
        // Mixed: max(1, 1) + 2 spends + 2 outputs + 0 orchard = 5
        assert_eq!(compute_logical_actions(1, 1, 2, 2, 0), 5);
        // Orchard only: max(0, 0) + 0 + 0 + 5 = 5
        assert_eq!(compute_logical_actions(0, 0, 0, 0, 5), 5);
    }

    fn make_block(size_bytes: u64, txs: Vec<(u64, u64, u64)>) -> BlockFeeData {
        BlockFeeData {
            size_bytes,
            transactions: txs
                .into_iter()
                .map(|(fee, size, actions)| TxFeeData {
                    fee_zatoshis: fee,
                    size_bytes: size,
                    logical_actions: actions,
                })
                .collect(),
        }
    }

    #[test]
    fn test_uncongested_low_traffic() {
        let estimator = FeeEstimatorV0::default();

        // 50 blocks, each with 1 small tx (1000 bytes, 5000 zat fee, 2 actions)
        // block_capacity=2MB, so lots of synthetic fill at floor=1000
        let blocks: Vec<BlockFeeData> = (0..50)
            .map(|_| make_block(1000, vec![(5000, 1000, 2)]))
            .collect();

        let result = estimator.compute(&blocks, 100);

        // With massive synthetic fill, median should be at the floor (1000)
        // Bucketed: 1000 → 1000. standard_fee = max(1000, 1000) = 1000
        assert_eq!(result.standard_fee, 1000);
        assert_eq!(result.express_fee, None);
        assert_eq!(result.version, "v0");
        assert_eq!(result.height, 100);
    }

    #[test]
    fn test_congested_all_blocks_full() {
        let estimator = FeeEstimatorV0::default();

        // 50 blocks, each exactly at capacity (2MB), with txs paying 5000 zat/action
        let blocks: Vec<BlockFeeData> = (0..50)
            .map(|_| {
                // Fill block to capacity with 100 txs of 20KB each = 2MB
                let txs: Vec<(u64, u64, u64)> =
                    (0..100).map(|_| (10000, 20000, 2)).collect();
                make_block(2_000_000, txs)
            })
            .collect();

        let result = estimator.compute(&blocks, 200);

        // All blocks full → no synthetic fill → congested
        // fee_per_action = 10000/2 = 5000 for each tx
        // Median = 5000, bucketed = 1000 (since 5000 - 1000 = 4000 <= 10000 - 5000 = 5000)
        assert_eq!(result.standard_fee, 1000);
        assert!(result.express_fee.is_some());
        assert_eq!(result.express_fee.unwrap(), 10000); // 1000 * 10
    }

    #[test]
    fn test_no_transactions_returns_zip317_default() {
        let estimator = FeeEstimatorV0::default();

        // 50 empty blocks
        let blocks: Vec<BlockFeeData> = (0..50)
            .map(|_| make_block(0, vec![]))
            .collect();

        let result = estimator.compute(&blocks, 300);

        assert_eq!(result.standard_fee, ZIP_317_CONVENTIONAL_FEE);
        assert_eq!(result.express_fee, None);
    }

    #[test]
    fn test_empty_blocks_returns_zip317_default() {
        let estimator = FeeEstimatorV0::default();
        let result = estimator.compute(&[], 400);

        assert_eq!(result.standard_fee, ZIP_317_CONVENTIONAL_FEE);
        assert_eq!(result.express_fee, None);
    }

    #[test]
    fn test_moderate_traffic() {
        let estimator = FeeEstimatorV0::default();

        // 50 blocks, each ~500KB with mixed fees
        let blocks: Vec<BlockFeeData> = (0..50)
            .map(|_| {
                make_block(
                    500_000,
                    vec![
                        (2000, 5000, 2),  // fee_per_action = 1000
                        (10000, 5000, 2), // fee_per_action = 5000
                        (600, 5000, 2),   // fee_per_action = 300
                    ],
                )
            })
            .collect();

        let result = estimator.compute(&blocks, 500);

        // 150 real txs + synthetic fill from 1.5MB unused per block
        // avg_tx_size = 5000, unused = 1_500_000, synthetic_count = 300 per block
        // Total: 150 real + 15000 synthetic = 15150 entries
        // Most entries are floor (1000), so median should be 1000
        assert_eq!(result.standard_fee, 1000);
        assert_eq!(result.express_fee, None);
    }
}
