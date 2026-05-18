#!/usr/bin/env python3
"""Thin relay for the Zcash dynamic fees showcase site.

Serves static files and proxies z_getstandardfees to a local Zebra node.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

WEB_ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("FEE_LAB_DATA_DIR", str(WEB_ROOT / "data")))
HISTORY_FILE = DATA_DIR / "fees.jsonl"
SAMPLE_INTERVAL = int(os.environ.get("FEE_LAB_SAMPLE_INTERVAL", "75"))  # ~1 block
HISTORY_DEFAULT_LIMIT = 1500
HISTORY_MAX_LIMIT = 5000

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
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}

# ZEC price cache (5-minute TTL)
_price_cache: dict = {"usd": 0.0, "ts": 0.0}
PRICE_TTL = 300


def _sample_loop() -> None:
    """Poll z_getstandardfees on each new block; append to JSONL history."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    last_height: int | None = None
    while True:
        try:
            response = _zebra_rpc("z_getstandardfees")
            data = response.get("result", {})
            height = data.get("height")
            if height is not None and height != last_height:
                entry = {
                    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "height": height,
                    "standard_fee": data.get("standard_fee"),
                    "priority_fee": data.get("priority_fee"),
                    "congested": bool(data.get("congested", False)),
                    "version": data.get("version"),
                }
                with HISTORY_FILE.open("a") as f:
                    f.write(json.dumps(entry) + "\n")
                last_height = height
        except Exception:
            pass  # silent — Zebra may be briefly unreachable
        time.sleep(SAMPLE_INTERVAL)


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
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/fees":
            self._handle_fees()
        elif path == "/api/price":
            self._handle_price()
        elif path == "/api/history":
            self._handle_history(parsed.query)
        elif path == "/api/history.csv":
            self._handle_history_csv()
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

    def _read_history(self, limit: int) -> list:
        if not HISTORY_FILE.exists():
            return []
        entries: list = []
        with HISTORY_FILE.open() as f:
            lines = f.readlines()
        for line in lines[-limit:]:
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
        return entries

    def _handle_history(self, query: str):
        try:
            params = parse_qs(query)
            limit = HISTORY_DEFAULT_LIMIT
            if "limit" in params:
                try:
                    limit = max(1, min(HISTORY_MAX_LIMIT, int(params["limit"][0])))
                except ValueError:
                    pass
            entries = self._read_history(limit)
            body = json.dumps({"entries": entries, "count": len(entries)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            self._error(500, str(exc))

    def _handle_history_csv(self):
        try:
            entries = self._read_history(HISTORY_MAX_LIMIT)
            rows = ["ts,height,standard_fee,priority_fee,congested,version"]
            for e in entries:
                rows.append(
                    f"{e.get('ts','')},{e.get('height','')},{e.get('standard_fee','')},"
                    f"{e.get('priority_fee','')},{e.get('congested','')},{e.get('version','')}"
                )
            body = ("\n".join(rows) + "\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Disposition", 'attachment; filename="fees.csv"')
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            self._error(500, str(exc))

    def _handle_static(self, path: str):
        if path == "/":
            path = "/index.html"
        file_path = (WEB_ROOT / path.lstrip("/")).resolve()
        # Try clean URL: if /design and design.html exists, serve it
        if not file_path.is_file() and not file_path.suffix:
            html_candidate = file_path.with_suffix(".html")
            if html_candidate.is_file():
                file_path = html_candidate
        try:
            file_path.relative_to(WEB_ROOT.resolve())
        except ValueError:
            self._error(404, "Not found")
            return
        if not file_path.is_file():
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
    threading.Thread(target=_sample_loop, daemon=True).start()
    server = DualStackServer((SERVER_HOST, SERVER_PORT), Handler)
    print(f"Serving on {SERVER_HOST}:{SERVER_PORT} → Zebra at {ZEBRA_URL}")
    print(f"History sampler: {SAMPLE_INTERVAL}s interval → {HISTORY_FILE}")
    server.serve_forever()
