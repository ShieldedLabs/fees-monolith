import http.client
import json
import threading
import unittest

from engine import FakeProvider, FeeEngine
from proxy import FeeRequestHandler, ThreadingHTTPServer


class APISummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        provider = FakeProvider()
        provider.set_blocks(
            [
                {
                    "height": 1,
                    "hash": "h1",
                    "size_bytes": 2 * 1024 * 1024,
                    "tx_count": 2,
                    "service_actions": 400,
                    "txs": [{"actions": 200, "fee_zats": 2000}, {"actions": 200, "fee_zats": 4000}],
                }
            ]
        )
        provider.set_mempool(
            [
                {"txid": "tx1", "actions": 10, "fee_zats": 1000, "size": 800},
                {"txid": "tx2", "actions": 20, "fee_zats": 4000, "size": 1400},
            ]
        )
        engine = FeeEngine(provider=provider, price_source=lambda: 25.0)
        FeeRequestHandler.engine = engine
        try:
            cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FeeRequestHandler)
        except PermissionError:
            raise unittest.SkipTest("binding HTTP server not permitted in this sandbox") from None
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_summary_endpoint_returns_median_and_lanes(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/api/summary")
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        self.assertEqual(resp.status, 200)
        payload = json.loads(body.decode("utf-8"))
        self.assertIn("lanes", payload)
        self.assertIsNotNone(payload["lanes"]["standard"])
        self.assertIsNone(payload["lanes"].get("express"))
        # Median fee per action present (from mempool rows here: 100 and 200 zats/action => median 150)
        self.assertEqual(payload["metrics"]["median_fee_per_action_zats"], 150)


if __name__ == "__main__":
    unittest.main()
