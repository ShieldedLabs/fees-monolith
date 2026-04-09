//! Standalone fee estimator that talks directly to Zebra via JSON-RPC.
//!
//! Usage: cargo run -p zaino-state --example fee_estimate

use zaino_fetch::jsonrpsee::{
    connector::JsonRpSeeConnector,
    response::{GetBlockResponse, GetTransactionResponse},
};
use zaino_state::fee_estimator::{
    tx_fee_data_from_transaction, BlockFeeData, FeeEstimatorV0,
};
use zebra_chain::block::Height;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Connect directly to Zebra JSON-RPC
    let fetcher = JsonRpSeeConnector::new_with_basic_auth(
        "http://127.0.0.1:8232".parse()?,
        String::new(),
        String::new(),
    )?;

    let estimator = FeeEstimatorV0::default();

    // Get tip height
    let tip: Height = fetcher.get_block_count().await?.into();
    let tip_height = tip.0 as u64;
    println!("Chain tip: {tip_height}");

    let required_depth = estimator.required_depth();
    if tip_height < required_depth {
        println!("Chain too short ({tip_height} < {required_depth})");
        return Ok(());
    }

    let window_end = tip_height - estimator.tip_buffer;
    let window_start = window_end - estimator.lookback_window + 1;
    println!("Lookback window: blocks {window_start}..={window_end}");

    let mut blocks = Vec::with_capacity(estimator.lookback_window as usize);
    for h in window_start..=window_end {
        let block_resp = fetcher.get_block(h.to_string(), Some(1)).await?;
        if let GetBlockResponse::Object(block_obj) = block_resp {
            let block_size = block_obj.size.unwrap_or(0).max(0) as u64;
            let tx_ids = &block_obj.tx;
            let non_coinbase_count = tx_ids.len().saturating_sub(1);

            let mut transactions = Vec::new();
            for txid in tx_ids.iter().skip(1) {
                let tx_resp = fetcher
                    .get_raw_transaction(txid.clone(), Some(1))
                    .await?;
                if let GetTransactionResponse::Object(txo) = tx_resp {
                    transactions.push(tx_fee_data_from_transaction(&txo));
                }
            }

            if h % 10 == 0 || h == window_end {
                println!(
                    "  Block {h}: size={block_size} bytes, {non_coinbase_count} txs"
                );
            }

            blocks.push(BlockFeeData {
                size_bytes: block_size,
                transactions,
            });
        }
    }

    let result = estimator.compute(&blocks, tip_height);

    println!("\n=== z_getstandardfees ===");
    println!("{}", serde_json::to_string_pretty(&result)?);

    Ok(())
}
