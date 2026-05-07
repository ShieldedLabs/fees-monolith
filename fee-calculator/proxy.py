#!/usr/bin/env python3
"""Thin relay for the Zcash dynamic fees showcase site.

Serves static files and proxies z_getstandardfees to a local Zebra node.
"""

from __future__ import annotations

import json
import os
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

WEB_ROOT = Path(__file__).resolve().parent
SERVER_HOST = os.environ.get("SERVER_HOST", "::")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "8080"))
ZEBRA_URL = os.environ.get(
    "ZEBRA_URL",
    f"http://{os.environ.get('ZEBRA_HOST', '127.0.0.1')}:{os.environ.get('ZEBRA_PORT', '8232')}",
)

MIME_TYPES = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}

# ZEC price cache (5-minute TTL)
_price_cache: dict = {"usd": 0.0, "ts": 0.0}
PRICE_TTL = 300


def _zebra_rpc(method: str) -> dict:
    """Call a Zebra JSON-RPC method with no params."""
    payload = json.dumps({"jsonrpc": "2.0", "method": method, "id": 1}).encode()
    req = Request(ZEBRA_URL, data=payload, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _fetch_price() -> float:
    """Get ZEC/USD from CoinGecko, cached 5 minutes."""
    now = time.time()
    if now - _price_cache["ts"] < PRICE_TTL and _price_cache["usd"] > 0:
        return _price_cache["usd"]
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=zcash&vs_currencies=usd"
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        usd = float(data["zcash"]["usd"])
        _price_cache.update(usd=usd, ts=now)
        return usd
    except Exception:
        return _price_cache["usd"] or 30.0


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/fees":
            self._handle_fees()
        elif path == "/api/price":
            self._handle_price()
        else:
            self._handle_static(path)

    def _handle_fees(self):
        try:
            result = _zebra_rpc("z_getstandardfees")
            body = json.dumps(result.get("result", result)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            self._error(502, str(exc))

    def _handle_price(self):
        usd = _fetch_price()
        body = json.dumps({"usd_per_zec": usd}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _handle_static(self, path: str):
        if path == "/":
            path = "/index.html"
        file_path = WEB_ROOT / path.lstrip("/")
        if not file_path.is_file() or not str(file_path).startswith(str(WEB_ROOT)):
            self._error(404, "Not found")
            return
        ext = file_path.suffix.lower()
        mime = MIME_TYPES.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def _error(self, code: int, msg: str):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": msg}).encode())

    def log_message(self, fmt, *args):
        pass  # silence request logs


class DualStackServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


if __name__ == "__main__":
    server = DualStackServer((SERVER_HOST, SERVER_PORT), Handler)
    print(f"Serving on {SERVER_HOST}:{SERVER_PORT} → Zebra at {ZEBRA_URL}")
    server.serve_forever()
