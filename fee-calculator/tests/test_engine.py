import unittest

from engine import BLOCK_KB, FakeProvider, FeeEngine


class FeeEngineTests(unittest.TestCase):
    def setUp(self):
        self.provider = FakeProvider()
        self.engine = FeeEngine(self.provider, price_source=lambda: 20.0)

    def test_service_floor_clamps_small_blocks_when_uncongested(self):
        # Observed block size is tiny; effective service should clamp to full 2 MB.
        self.provider.set_blocks(
            [
                {
                    "height": 1,
                    "hash": "h1",
                    "size_bytes": 500 * 1024,  # ~0.5 MB
                    "tx_count": 1,
                    "service_actions": 50,
                    "txs": [{"actions": 50, "fee_zats": 500}],
                }
            ]
        )
        snap = self.engine.snapshot()
        self.assertEqual(snap.block_kb_effective, BLOCK_KB)

    def test_block_entries_include_median_fee_per_action(self):
        self.provider.set_blocks(
            [
                {
                    "height": 1,
                    "hash": "h1",
                    "size_bytes": 2 * 1024 * 1024,
                    "tx_count": 2,
                    "service_actions": 400,
                    "txs": [
                        {"actions": 100, "fee_zats": 1000},  # 10 zats/action
                        {"actions": 100, "fee_zats": 4000},  # 40 zats/action
                    ],
                }
            ]
        )
        self.provider.set_mempool([])
        snap = self.engine.snapshot()
        self.assertEqual(len(snap.block_entries), 1)
        self.assertAlmostEqual(snap.block_entries[0]["median_fee_per_action_zats"], 25)

    def test_snapshot_reports_median_fee_per_action_metric(self):
        self.provider.set_blocks(
            [
                {
                    "height": 10,
                    "hash": "h10",
                    "size_bytes": 2 * 1024 * 1024,
                    "tx_count": 2,
                    "service_actions": 200,
                    "txs": [
                        {"actions": 100, "fee_zats": 1000},
                        {"actions": 100, "fee_zats": 10000},
                    ],
                }
            ]
        )
        self.provider.set_mempool([{"txid": "tx1", "actions": 5, "fee_zats": 500, "size": 400}])
        snap = self.engine.snapshot()
        self.assertIsNotNone(snap.market_hint)
        self.assertEqual(snap.market_hint["median"], 10)
        self.assertEqual(snap.median_fee_per_action, 500 / 5)  # 100 zats/action from mempool only

    def test_market_hint_uses_block_window_median(self):
        self.provider.set_blocks(
            [
                {
                    "height": 10,
                    "hash": "h10",
                    "size_bytes": 2 * 1024 * 1024,
                    "tx_count": 2,
                    "service_actions": 200,
                    "txs": [
                        {"actions": 100, "fee_zats": 1000},
                        {"actions": 100, "fee_zats": 10000},
                    ],
                }
            ]
        )
        self.provider.set_mempool([{"txid": "tx1", "actions": 5, "fee_zats": 500, "size": 400}])
        snap = self.engine.snapshot()
        self.assertIsNotNone(snap.market_hint)
        self.assertEqual(snap.market_hint["median"], 10)


if __name__ == "__main__":
    unittest.main()
