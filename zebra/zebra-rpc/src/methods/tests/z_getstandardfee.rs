//! Tests for the `z_getstandardfee` RPC.

use std::{collections::HashMap, sync::Arc};

use futures::FutureExt;
use tower::buffer::Buffer;

use zebra_chain::{
    amount::{Amount, NonNegative},
    block::{tests::generate::block_header, Block, Header, Height},
    chain_sync_status::MockSyncStatus,
    chain_tip::mock::MockChainTip,
    parameters::Network::Mainnet,
    serialization::ZcashSerialize,
    transaction::{LockTime, Transaction},
    transparent,
};
use zebra_network::address_book_peers::MockAddressBookPeers;
use zebra_node_services::BoxError;
use zebra_state::{HashOrHeight, ReadRequest, ReadResponse};
use zebra_test::mock_service::MockService;

use super::super::{bucket_fee_alphabet, calculate_transaction_fee, RpcImpl, RpcServer};
use crate::server::error::LegacyCode;

/// Helper: create a block with a coinbase tx and a spend tx, returning it with its serialized size.
fn make_block_with_size(
    height: u32,
    base_value: i64,
    fee_zats: i64,
    header: &Arc<Header>,
) -> (Arc<Block>, usize) {
    let coinbase_value = base_value + fee_zats;
    let coinbase_tx = make_coinbase_tx(height, coinbase_value);
    let spend_tx = make_spend_tx(coinbase_tx.as_ref(), base_value);

    let block = Arc::new(Block {
        header: header.clone(),
        transactions: vec![coinbase_tx, spend_tx],
    });
    let size = block.zcash_serialize_to_vec().map(|v| v.len()).unwrap_or(0);
    (block, size)
}

fn make_coinbase_tx(height: u32, value_zats: i64) -> Arc<Transaction> {
    let input = transparent::Input::Coinbase {
        height: Height(height),
        data: vec![],
        sequence: 0,
    };
    let output = transparent::Output::new(
        Amount::<NonNegative>::new(value_zats),
        transparent::Script::new(&[]),
    );

    Arc::new(Transaction::V1 {
        inputs: vec![input],
        outputs: vec![output],
        lock_time: LockTime::unlocked(),
    })
}

fn make_spend_tx(prev_tx: &Transaction, output_value_zats: i64) -> Arc<Transaction> {
    let outpoint = transparent::OutPoint::from_usize(prev_tx.hash(), 0);
    let input = transparent::Input::PrevOut {
        outpoint,
        unlock_script: transparent::Script::new(&[]),
        sequence: 0,
    };
    let output = transparent::Output {
        value: Amount::<NonNegative>::new(output_value_zats),
        lock_script: transparent::Script::new(&[]),
    };

    Arc::new(Transaction::V1 {
        inputs: vec![input],
        outputs: vec![output],
        lock_time: LockTime::unlocked(),
    })
}

#[tokio::test(flavor = "multi_thread")]
async fn z_getstandardfee_happy_path() {
    let _init_guard = zebra_test::init();

    let mut mempool: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();
    let mut state: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();
    let mut read_state: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();

    let (chain_tip, chain_tip_sender) = MockChainTip::new();
    chain_tip_sender.send_best_tip_height(Height(55));

    let (_tx, rx) = tokio::sync::watch::channel(None);
    let (rpc, rpc_tx_queue) = RpcImpl::new(
        Mainnet,
        Default::default(),
        Default::default(),
        "0.0.1",
        "RPC test",
        Buffer::new(mempool.clone(), 1),
        Buffer::new(state.clone(), 1),
        Buffer::new(read_state.clone(), 1),
        MockService::build().for_unit_tests(),
        MockSyncStatus::default(),
        chain_tip,
        MockAddressBookPeers::default(),
        rx,
        None,
    );

    let rpc_future = tokio::spawn(async move { rpc.z_getstandardfee().await });

    let header = Arc::new(block_header().0);
    let base_value = 10_000;

    for height in 1u32..=50u32 {
        let fee_zats = i64::from(height) * 2;
        let (block, block_size) = make_block_with_size(height, base_value, fee_zats, &header);

        let request = ReadRequest::BlockAndSize(HashOrHeight::Height(Height(height)));
        read_state
            .expect_request(request)
            .await
            .respond(ReadResponse::BlockAndSize(Some((block, block_size))));
    }

    let response = rpc_future
        .await
        .expect("rpc task should not panic")
        .expect("rpc should succeed");

    // With tiny blocks and 2MB capacity, synthetic fill dominates → median at floor (5000)
    assert_eq!(response.standard_fee, 5000);
    // Priority fee is always 4× standard, regardless of congestion
    assert_eq!(response.priority_fee, 20_000);
    // Not congested (huge synthetic fill)
    assert!(!response.congested);
    assert_eq!(response.version, "v0");
    assert_eq!(response.height, 55);

    mempool.expect_no_requests().await;
    state.expect_no_requests().await;
    read_state.expect_no_requests().await;

    assert!(rpc_tx_queue.now_or_never().is_none());
}

#[tokio::test(flavor = "multi_thread")]
async fn z_getfeedistribution_happy_path() {
    let _init_guard = zebra_test::init();

    let mut mempool: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();
    let mut state: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();
    let mut read_state: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();

    let (chain_tip, chain_tip_sender) = MockChainTip::new();
    chain_tip_sender.send_best_tip_height(Height(55));

    let (_tx, rx) = tokio::sync::watch::channel(None);
    let (rpc, rpc_tx_queue) = RpcImpl::new(
        Mainnet,
        Default::default(),
        Default::default(),
        "0.0.1",
        "RPC test",
        Buffer::new(mempool.clone(), 1),
        Buffer::new(state.clone(), 1),
        Buffer::new(read_state.clone(), 1),
        MockService::build().for_unit_tests(),
        MockSyncStatus::default(),
        chain_tip,
        MockAddressBookPeers::default(),
        rx,
        None,
    );

    let rpc_future = tokio::spawn(async move { rpc.z_getfeedistribution().await });

    let header = Arc::new(block_header().0);
    let base_value = 10_000;

    for height in 1u32..=50u32 {
        let fee_zats = i64::from(height) * 2;
        let (block, block_size) = make_block_with_size(height, base_value, fee_zats, &header);

        let request = ReadRequest::BlockAndSize(HashOrHeight::Height(Height(height)));
        read_state
            .expect_request(request)
            .await
            .respond(ReadResponse::BlockAndSize(Some((block, block_size))));
    }

    let response = rpc_future
        .await
        .expect("rpc task should not panic")
        .expect("rpc should succeed");

    // Same estimator output as z_getstandardfee over this window.
    assert_eq!(response.standard_fee, 5000);
    assert_eq!(response.priority_fee, 20_000);
    assert_eq!(response.version, "v0");
    assert_eq!(response.height, 55);

    // One real (non-coinbase) tx per block, each paying a tiny off-lane fee
    // (neither exactly 5000 nor 20000), so every real tx is nonstandard.
    assert_eq!(response.total_tx_count, 50);
    assert_eq!(response.standard_count, 0);
    assert_eq!(response.priority_count, 0);
    assert_eq!(response.nonstandard_count, 50);

    // The histogram and the per-tx breakdown both cover exactly the real txs.
    let counted: u64 = response.distribution.values().sum();
    assert_eq!(counted, 50);
    assert_eq!(response.transactions.len(), 50);
    assert!(response
        .transactions
        .iter()
        .all(|sample| sample.tier == "nonstandard"));

    mempool.expect_no_requests().await;
    state.expect_no_requests().await;
    read_state.expect_no_requests().await;

    assert!(rpc_tx_queue.now_or_never().is_none());
}

#[tokio::test(flavor = "multi_thread")]
async fn z_getstandardfee_not_enough_blocks_end_underflow() {
    let _init_guard = zebra_test::init();

    let mut mempool: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();
    let mut state: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();
    let mut read_state: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();

    let (chain_tip, chain_tip_sender) = MockChainTip::new();
    chain_tip_sender.send_best_tip_height(Height(4));

    let (_tx, rx) = tokio::sync::watch::channel(None);
    let (rpc, rpc_tx_queue) = RpcImpl::new(
        Mainnet,
        Default::default(),
        Default::default(),
        "0.0.1",
        "RPC test",
        Buffer::new(mempool.clone(), 1),
        Buffer::new(state.clone(), 1),
        Buffer::new(read_state.clone(), 1),
        MockService::build().for_unit_tests(),
        MockSyncStatus::default(),
        chain_tip,
        MockAddressBookPeers::default(),
        rx,
        None,
    );

    let error = rpc
        .z_getstandardfee()
        .await
        .expect_err("expected not enough blocks error");

    assert_eq!(error.code(), i32::from(LegacyCode::Misc));
    assert_eq!(error.message(), "not enough blocks to calculate median fee");

    mempool.expect_no_requests().await;
    state.expect_no_requests().await;
    read_state.expect_no_requests().await;

    assert!(rpc_tx_queue.now_or_never().is_none());
}

#[tokio::test(flavor = "multi_thread")]
async fn z_getstandardfee_not_enough_blocks_start_underflow() {
    let _init_guard = zebra_test::init();

    let mut mempool: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();
    let mut state: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();
    let mut read_state: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();

    let (chain_tip, chain_tip_sender) = MockChainTip::new();
    chain_tip_sender.send_best_tip_height(Height(52));

    let (_tx, rx) = tokio::sync::watch::channel(None);
    let (rpc, rpc_tx_queue) = RpcImpl::new(
        Mainnet,
        Default::default(),
        Default::default(),
        "0.0.1",
        "RPC test",
        Buffer::new(mempool.clone(), 1),
        Buffer::new(state.clone(), 1),
        Buffer::new(read_state.clone(), 1),
        MockService::build().for_unit_tests(),
        MockSyncStatus::default(),
        chain_tip,
        MockAddressBookPeers::default(),
        rx,
        None,
    );

    let error = rpc
        .z_getstandardfee()
        .await
        .expect_err("expected not enough blocks error");

    assert_eq!(error.code(), i32::from(LegacyCode::Misc));
    assert_eq!(error.message(), "not enough blocks to calculate median fee");

    mempool.expect_no_requests().await;
    state.expect_no_requests().await;
    read_state.expect_no_requests().await;

    assert!(rpc_tx_queue.now_or_never().is_none());
}

#[tokio::test(flavor = "multi_thread")]
async fn z_getstandardfee_no_chain_tip() {
    let _init_guard = zebra_test::init();

    let mut mempool: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();
    let mut state: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();
    let mut read_state: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();

    let (chain_tip, _chain_tip_sender) = MockChainTip::new();

    let (_tx, rx) = tokio::sync::watch::channel(None);
    let (rpc, rpc_tx_queue) = RpcImpl::new(
        Mainnet,
        Default::default(),
        Default::default(),
        "0.0.1",
        "RPC test",
        Buffer::new(mempool.clone(), 1),
        Buffer::new(state.clone(), 1),
        Buffer::new(read_state.clone(), 1),
        MockService::build().for_unit_tests(),
        MockSyncStatus::default(),
        chain_tip,
        MockAddressBookPeers::default(),
        rx,
        None,
    );

    let error = rpc
        .z_getstandardfee()
        .await
        .expect_err("expected no chain tip error");

    assert_eq!(error.code(), i32::from(LegacyCode::Misc));
    assert_eq!(error.message(), "No blocks in state");

    mempool.expect_no_requests().await;
    state.expect_no_requests().await;
    read_state.expect_no_requests().await;

    assert!(rpc_tx_queue.now_or_never().is_none());
}

#[tokio::test(flavor = "multi_thread")]
async fn z_getstandardfee_block_not_found() {
    let _init_guard = zebra_test::init();

    let mut mempool: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();
    let mut state: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();
    let mut read_state: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();

    let (chain_tip, chain_tip_sender) = MockChainTip::new();
    chain_tip_sender.send_best_tip_height(Height(55));

    let (_tx, rx) = tokio::sync::watch::channel(None);
    let (rpc, rpc_tx_queue) = RpcImpl::new(
        Mainnet,
        Default::default(),
        Default::default(),
        "0.0.1",
        "RPC test",
        Buffer::new(mempool.clone(), 1),
        Buffer::new(state.clone(), 1),
        Buffer::new(read_state.clone(), 1),
        MockService::build().for_unit_tests(),
        MockSyncStatus::default(),
        chain_tip,
        MockAddressBookPeers::default(),
        rx,
        None,
    );

    let rpc_future = tokio::spawn(async move { rpc.z_getstandardfee().await });

    let request = ReadRequest::BlockAndSize(HashOrHeight::Height(Height(1)));
    read_state
        .expect_request(request)
        .await
        .respond(ReadResponse::BlockAndSize(None));

    let error = rpc_future
        .await
        .expect("rpc task should not panic")
        .expect_err("expected block not found error");

    assert_eq!(error.code(), i32::from(LegacyCode::Misc));
    assert_eq!(
        error.message(),
        "block not found while calculating median fee"
    );

    mempool.expect_no_requests().await;
    state.expect_no_requests().await;
    read_state.expect_no_requests().await;

    assert!(rpc_tx_queue.now_or_never().is_none());
}

#[tokio::test(flavor = "multi_thread")]
async fn calculate_transaction_fee_uses_tx_cache() {
    let _init_guard = zebra_test::init();

    let mut read_state: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();
    let mut tx_cache: HashMap<_, _> = HashMap::new();
    let block_outputs: HashMap<_, _> = HashMap::new();

    let prev_tx = make_coinbase_tx(1, 10);
    let spend_tx = make_spend_tx(prev_tx.as_ref(), 8);

    tx_cache.insert(prev_tx.hash(), (prev_tx.clone(), Height(1)));

    let fee = calculate_transaction_fee(&mut read_state, &mut tx_cache, &spend_tx, &block_outputs)
        .await
        .expect("fee should be computed")
        .expect("non-coinbase fee should exist");

    assert_eq!(fee.zatoshis(), 2);
    read_state.expect_no_requests().await;
}

#[tokio::test(flavor = "multi_thread")]
async fn calculate_transaction_fee_fetches_prev_tx_from_read_state() {
    let _init_guard = zebra_test::init();

    let mut read_state: MockService<_, _, _, BoxError> = MockService::build().for_unit_tests();
    let mut read_state_handle = read_state.clone();
    let mut tx_cache: HashMap<_, _> = HashMap::new();
    let block_outputs: HashMap<_, _> = HashMap::new();

    let prev_tx = make_coinbase_tx(1, 10);
    let prev_hash = prev_tx.hash();
    let spend_tx = make_spend_tx(prev_tx.as_ref(), 8);

    let fee_fut =
        calculate_transaction_fee(&mut read_state, &mut tx_cache, &spend_tx, &block_outputs);
    let respond_fut = async move {
        let responder = read_state_handle
            .expect_request(ReadRequest::Transaction(prev_hash))
            .await;
        let mined_tx = zebra_state::MinedTx::new(prev_tx, Height(1), 1, chrono::Utc::now());
        responder.respond(ReadResponse::Transaction(Some(mined_tx)));
    };

    let (fee_result, _) = tokio::join!(fee_fut, respond_fut);
    let fee = fee_result
        .expect("fee should be computed")
        .expect("non-coinbase fee should exist");

    assert_eq!(fee.zatoshis(), 2);
    assert!(tx_cache.contains_key(&prev_hash));
    read_state.expect_no_requests().await;
}

#[test]
fn test_bucket_fee_alphabet() {
    // The fee alphabet is 5000 * 4^n = {5000, 20000, 80000, 320000, ...}.
    assert_eq!(bucket_fee_alphabet(0), 0);
    // At or below the base maps to the base.
    assert_eq!(bucket_fee_alphabet(1), 5000);
    assert_eq!(bucket_fee_alphabet(5000), 5000);
    // 5000..20000: midpoint 12500, ties go to the lower rung.
    assert_eq!(bucket_fee_alphabet(5001), 5000);
    assert_eq!(bucket_fee_alphabet(12500), 5000);
    assert_eq!(bucket_fee_alphabet(12501), 20000);
    assert_eq!(bucket_fee_alphabet(20000), 20000);
    // 20000..80000: midpoint 50000.
    assert_eq!(bucket_fee_alphabet(50000), 20000);
    assert_eq!(bucket_fee_alphabet(50001), 80000);
    assert_eq!(bucket_fee_alphabet(80000), 80000);
    assert_eq!(bucket_fee_alphabet(320000), 320000);
}
