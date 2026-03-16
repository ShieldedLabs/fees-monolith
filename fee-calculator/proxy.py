#!/usr/bin/env python3
"""
Purpose-built calculation + relay service for the fee-calculator app.

Key responsibilities:
- Serve the static SPA assets
- Expose a single JSON endpoint (/api/summary) that returns Paris Metro lane
  quotes, Cramér–Lundberg context, congestion simulation output, and recent
  block/mempool snapshots.
- Keep RPC plumbing internal; the browser now consumes derived data only.
"""

from __future__ import annotations

import base64
import http.client
import json
import mimetypes
import os
import socket
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from engine import (
    BLOCK_BYTES,
    BLOCK_EXPIRY_WINDOW,
    BLOCK_INTERVAL_SECONDS,
    BLOCK_LOOKBACK_K,
    ZATS_PER_ZEC,
    FeeEngine,
)

WEB_ROOT = Path(__file__).resolve().parent
DEFAULT_FILE = "index.html"
LOG_PATH = WEB_ROOT / "proxy.log"
SERVER_HOST = os.environ.get("SERVER_HOST", "::")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "8080"))
ZEBRA_HOST = os.environ.get("ZEBRA_HOST", "127.0.0.1")
ZEBRA_PORT = int(os.environ.get("ZEBRA_PORT", "8232"))
ZEBRA_COOKIE_PATH = Path(os.environ.get("ZEBRA_COOKIE_PATH", "~/.cache/zebra/.cookie")).expanduser()


# --------------------------------------------------------------------------- #
# Utilities


def log_event(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    try:
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def usd_from_zats(zats: float | None, usd_per_zec: float | None) -> str | None:
    if zats is None or usd_per_zec is None:
        return None
    usd = (zats / ZATS_PER_ZEC) * usd_per_zec
    if not isinstance(usd, (int, float)):
        return None
    places = 4 if usd < 0.01 else 2
    return f"${usd:.{places}f}"


def short_txid(txid: str) -> str:
    if not txid or len(txid) < 8:
        return txid or "—"
    return f"{txid[:6]}…{txid[-4:]}"


def normalize_host(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return "0.0.0.0"
    return value


# --------------------------------------------------------------------------- #
# RPC data provider


class ZebraProvider:
    """
    Light wrapper around Zebra RPC. Expensive calls (tx lookups, prevouts) are
    cached in-memory to make repeated summary requests cheaper.
    """

    def __init__(self, host: str, port: int, auth_header: str):
        self.host = host
        self.port = port
        self.auth_header = auth_header
        self._tx_cache: dict[tuple[str, int], dict] = {}
        self._prevout_cache: dict[tuple[str, int], int] = {}
        self._tx_lock = threading.Lock()

    # -- Public API ------------------------------------------------------
    def mempool_rows(self) -> list[dict[str, object]]:
        result = self._rpc("getrawmempool", [True])
        if not isinstance(result, dict):
            return []
        rows: list[dict[str, object]] = []
        for txid, info in result.items():
            tx = self._get_transaction(txid, verbose=2)
            actions = self._count_actions(tx)
            fee_zats = self._fee_from_mempool_entry(info)
            size = self._size_from_entry(info, tx)
            rows.append(
                {
                    "txid": txid,
                    "actions": actions,
                    "fee_zats": fee_zats,
                    "size": size,
                }
            )
        rows.sort(key=lambda r: (r.get("fee_zats", 0) / max(1, r.get("actions", 1))), reverse=True)
        return rows

    def block_window(self, k: int = BLOCK_LOOKBACK_K, expiry: int = BLOCK_EXPIRY_WINDOW) -> list[dict[str, object]]:
        tip = self._rpc("getblockcount", [])
        if not isinstance(tip, int):
            return []
        recent_start = tip - (k - 1)
        window_start = tip - (k + expiry - 1)
        heights = list(range(tip, max(-1, window_start - 1), -1))
        blocks: list[dict[str, object]] = []
        for height in heights:
            try:
                block = self._block_at_height(height)
                if block:
                    block["tier"] = "recent" if height >= recent_start else "frozen"
                    blocks.append(block)
            except Exception as exc:
                log_event(f"block fetch failed at height {height}: {exc}")
        return blocks

    # -- Internals -------------------------------------------------------
    def _rpc(self, method: str, params: list) -> object:
        payload = json.dumps({"jsonrpc": "2.0", "id": method, "method": method, "params": params})
        headers = {"Content-Type": "application/json", "Authorization": self.auth_header}
        conn = http.client.HTTPConnection(self.host, self.port, timeout=30)
        try:
            conn.request("POST", "/", body=payload, headers=headers)
            response = conn.getresponse()
            data = response.read()
            if response.status != 200:
                raise RuntimeError(f"RPC {method} -> {response.status}")
            parsed = json.loads(data.decode("utf-8"))
            return parsed.get("result")
        finally:
            conn.close()

    def _block_at_height(self, height: int) -> dict[str, object] | None:
        block_hash = self._rpc("getblockhash", [height])
        if not isinstance(block_hash, str):
            return None
        block = self._rpc("getblock", [block_hash, 2])
        if not isinstance(block, dict):
            return None
        txs = []
        for tx in block.get("tx") or []:
            breakdown = self._action_breakdown(tx)
            actions = breakdown["total_actions"]
            fee = self._compute_fee_zats(tx)
            sz = tx.get("size") or tx.get("vsize") or tx.get("weight")
            txs.append({
                "actions": actions,
                "fee_zats": fee,
                "size": sz,
                "transparent_actions": breakdown["transparent_actions"],
                "shielded_actions": breakdown["shielded_actions"],
                "has_shielded": breakdown["has_shielded"],
            })
        non_coinbase_actions = sum(t["actions"] for t in txs[1:]) if len(txs) > 1 else 0
        size_bytes = block.get("size") or block.get("strippedsize") or BLOCK_BYTES
        return {
            "height": height,
            "hash": block_hash,
            "size_bytes": size_bytes,
            "tx_count": block.get("nTx") or len(block.get("tx") or []),
            "txs": txs[1:],  # exclude coinbase for fees/actions
            "service_actions": non_coinbase_actions,
        }

    def _get_transaction(self, txid: str, verbose: int = 2) -> dict:
        key = (txid, verbose)
        with self._tx_lock:
            if key in self._tx_cache:
                return self._tx_cache[key]
        tx = self._rpc("getrawtransaction", [txid, verbose])
        if isinstance(tx, dict):
            with self._tx_lock:
                self._tx_cache[key] = tx
        return tx or {}

    def _prevout_value(self, txid: str, vout: int) -> int | None:
        key = (txid, vout)
        with self._tx_lock:
            if key in self._prevout_cache:
                return self._prevout_cache[key]
        tx = self._get_transaction(txid, verbose=1)
        if not isinstance(tx, dict):
            return None
        outputs = tx.get("vout") or []
        for out in outputs:
            if out.get("n") == vout:
                value = out.get("value")
                if isinstance(value, (int, float)):
                    zats = int(round(value * ZATS_PER_ZEC))
                    with self._tx_lock:
                        self._prevout_cache[key] = zats
                    return zats
        return None

    def _count_actions(self, tx: dict) -> int:
        return self._action_breakdown(tx)["total_actions"]

    def _action_breakdown(self, tx: dict) -> dict[str, int | bool]:
        if not isinstance(tx, dict):
            return {
                "transparent_inputs": 0,
                "transparent_outputs": 0,
                "sapling_spends": 0,
                "sapling_outputs": 0,
                "orchard_actions": 0,
                "transparent_actions": 0,
                "shielded_actions": 0,
                "total_actions": 0,
                "has_shielded": False,
            }
        vin = [i for i in (tx.get("vin") or []) if not i.get("coinbase")]
        vout = tx.get("vout") or []
        sapling_spends = len(tx.get("vShieldedSpend") or [])
        sapling_outputs = len(tx.get("vShieldedOutput") or [])
        orchard_actions = self._orchard_actions(tx)
        transparent_actions_raw = len(vin) + len(vout)
        shielded_actions_raw = sapling_spends + sapling_outputs + orchard_actions
        has_shielded = shielded_actions_raw > 0 or bool(tx.get("vjoinsplit"))
        total_actions = transparent_actions_raw + shielded_actions_raw
        transparent_actions = total_actions if not has_shielded else 0
        shielded_actions = total_actions if has_shielded else 0
        return {
            "transparent_inputs": len(vin),
            "transparent_outputs": len(vout),
            "sapling_spends": sapling_spends,
            "sapling_outputs": sapling_outputs,
            "orchard_actions": orchard_actions,
            "transparent_actions": transparent_actions,
            "shielded_actions": shielded_actions,
            "total_actions": total_actions,
            "has_shielded": has_shielded,
        }

    @staticmethod
    def _orchard_actions(tx: dict) -> int:
        if isinstance(tx.get("orchardActions"), list):
            return len(tx["orchardActions"])
        if isinstance(tx.get("actionsOrchard"), list):
            return len(tx["actionsOrchard"])
        if isinstance(tx.get("orchard"), dict) and isinstance(tx["orchard"].get("actions"), list):
            return len(tx["orchard"]["actions"])
        return 0

    def _fee_from_mempool_entry(self, entry: dict) -> int | None:
        if not isinstance(entry, dict):
            return None
        fee = entry.get("fee")
        if isinstance(fee, (int, float)):
            return int(round(fee * ZATS_PER_ZEC))
        return None

    def _size_from_entry(self, entry: dict, tx: dict) -> int | None:
        for key in ("size", "vsize", "weight"):
            val = entry.get(key)
            if isinstance(val, (int, float)) and val > 0:
                return int(val)
        for key in ("size", "vsize", "weight"):
            val = tx.get(key) if isinstance(tx, dict) else None
            if isinstance(val, (int, float)) and val > 0:
                return int(val)
        return None

    def _compute_fee_zats(self, tx: dict) -> int | None:
        if not isinstance(tx, dict):
            return None
        vin = tx.get("vin") or []
        if any(inp.get("coinbase") for inp in vin):
            return None
        input_sum = 0
        for inp in vin:
            txid = inp.get("txid")
            vout = inp.get("vout")
            if not isinstance(txid, str) or not isinstance(vout, int):
                continue
            val = self._prevout_value(txid, vout)
            if val is None:
                continue
            input_sum += val
        output_sum = 0
        for out in tx.get("vout") or []:
            value = out.get("value")
            if isinstance(value, (int, float)):
                output_sum += int(round(value * ZATS_PER_ZEC))
        fee = input_sum + self._balance_zats(tx) - output_sum
        return fee if isinstance(fee, int) else None

    @staticmethod
    def _balance_zats(tx: dict) -> int:
        # Sprout, Sapling, Orchard value balances
        def to_zats(holder: dict, field: str) -> int:
            if not isinstance(holder, dict):
                return 0
            if isinstance(holder.get(f"{field}Zat"), (int, float)):
                return int(holder[f"{field}Zat"])
            if isinstance(holder.get(field), (int, float)):
                return int(round(holder[field] * ZATS_PER_ZEC))
            return 0

        sapling = to_zats(tx, "valueBalance")
        orchard = to_zats(tx.get("orchard") or {}, "valueBalance")
        joins = tx.get("vjoinsplit") or []
        sprout = 0
        for join in joins:
            sprout += to_zats(join, "vpub_old") - to_zats(join, "vpub_new")
        return sapling + orchard + sprout


# --------------------------------------------------------------------------- #
# HTTP handler


class FeeRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    engine: FeeEngine
    static_root: Path = WEB_ROOT
    default_file: str = DEFAULT_FILE

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/summary":
            self.handle_summary(parsed.query)
            return
        if parsed.path == "/rpc":
            self._json({"error": "Deprecated endpoint. Use /api/summary."}, status=410)
            return
        self.serve_static(include_body=True)

    def do_HEAD(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/api/summary", "/rpc"):
            self.send_response(405)
            self.end_headers()
            return
        self.serve_static(include_body=False)

    # -- API handlers ----------------------------------------------------
    def handle_summary(self, query: str):
        try:
            snapshot = self.engine.snapshot()
        except Exception as exc:
            log_event(f"/api/summary failed: {exc}")
            self._json({"error": "calculation_failed", "details": str(exc)}, status=500)
            return
        payload = snapshot_to_payload(snapshot)
        # Override averages with last 55 blocks (difficulty uses 55 blocks too).
        block_metrics = compute_block_metrics(getattr(self.engine, "provider", None), limit=55)
        if block_metrics:
            payload.setdefault("metrics", {}).update(block_metrics)
        self._json(payload, status=200)

    # -- Static files ----------------------------------------------------
    def serve_static(self, include_body: bool):
        path_only = self.path.split("?", 1)[0]
        relative = self.default_file if path_only in {"", "/"} else unquote(path_only.lstrip("/"))
        candidate = (self.static_root / relative).resolve()
        try:
            candidate.relative_to(self.static_root)
        except ValueError:
            self._json({"error": "Not found"}, status=404)
            return
        if not candidate.is_file():
            self._json({"error": "Not found"}, status=404)
            return
        mime, _ = mimetypes.guess_type(str(candidate))
        try:
            data = candidate.read_bytes() if include_body else b""
            size = candidate.stat().st_size
        except OSError as exc:
            self._json({"error": f"Failed to read file: {exc}"}, status=500)
            return
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.end_headers()
        if include_body:
            self.wfile.write(data)

    # -- Response helpers ------------------------------------------------
    def _json(self, payload: dict, status: int = 200):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


# --------------------------------------------------------------------------- #
# Payload shaping


def snapshot_to_payload(snapshot) -> dict:
    price_usd = snapshot.price_usd

    def lane_payload(key: str, quote: dict | None, arrival: dict | None):
        if not quote:
            return None
        fee = quote.get("fee")
        micro = (fee / 100.0) if fee is not None else None
        usd = usd_from_zats(fee, price_usd)
        blocks = arrival.get("blocks_needed") if arrival else quote.get("expected_blocks")
        return {
            "key": key,
            "fee_zats": fee,
            "fee_microzec": micro,
            "usd": usd,
            "expected_blocks": blocks,
            "reason": quote.get("reason"),
            "slack": quote.get("slack", False),
        }

    lanes = {
        "standard": lane_payload("standard", snapshot.standard_quote, snapshot.standard_arrival),
    }

    def row_payload(row: dict):
        fee = row.get("fee_zats")
        actions = row.get("actions") or 0
        per_action = (fee / actions) if fee and actions else None
        return {
            "txid": row.get("txid"),
            "txid_short": short_txid(row.get("txid")),
            "actions": actions,
            "fee_zats": fee,
            "per_action_zats": per_action,
            "size": row.get("size"),
        }

    return {
        "updated_at": snapshot.updated_at,
        "price": {"usd_per_zec": price_usd},
        "flags": {},
        "market": snapshot.market_hint or {},
        "service": {
            "block_kb_observed": snapshot.block_kb_observed,
            "block_kb_effective": snapshot.block_kb_effective,
            "actions_per_mb": snapshot.actions_per_mb,
            "block_interval_seconds": BLOCK_INTERVAL_SECONDS,
        },
        "arrival": {
            "arrival_rate_actions_per_s": snapshot.arrival_rate,
            "backlog_actions": snapshot.backlog_actions,
        },
        "lanes": lanes,
        "mempool": {
            "rows": [row_payload(row) for row in snapshot.mempool_rows][:200],
        },
        "blocks": {
            "entries": snapshot.block_entries,
        },
        "metrics": {
            "avg_tx_size_kb": (snapshot.avg_tx_size_bytes / 1024) if snapshot.avg_tx_size_bytes else None,
            "entropy_raw_bits": (snapshot.privacy_bits or {}).get("raw_bits") if snapshot.privacy_bits else None,
            "median_fee_per_action_zats": snapshot.median_fee_per_action,
        },
        "nsm": {
            "window_blocks": (len([b for b in snapshot.block_entries if b.get("tier") != "recent"])
                              if any(b.get("tier") for b in (snapshot.block_entries or []))
                              else len(snapshot.block_entries)),
            "total_fee_zats": snapshot.total_fee_zats,
            "recycle_zats": snapshot.recycle_zats,
            "recycle_zec": (snapshot.recycle_zats / ZATS_PER_ZEC) if snapshot.recycle_zats else 0,
            "recycle_usd": usd_from_zats(snapshot.recycle_zats, price_usd),
        },
        "privacy": snapshot.privacy_bits or {},
    }


# --------------------------------------------------------------------------- #
# Server selection


class DualStackServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self):
        if self.address_family == socket.AF_INET6:
            try:
                self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            except OSError:
                pass
        super().server_bind()


# --------------------------------------------------------------------------- #
# Bootstrap


def build_auth_header(cookie_path: Path) -> str:
    raw = cookie_path.read_text(encoding="utf-8").strip()
    username, password = raw.split(":", 1)
    token = f"{username}:{password}".encode()
    return f"Basic {base64.b64encode(token).decode('ascii')}"


def price_source_env() -> float | None:
    val = os.environ.get("USD_PER_ZEC")
    if val is None:
        return None
    try:
        return float(val)
    except Exception:
        return None


_price_cache = {"ts": 0.0, "value": None}


def price_source_http() -> float | None:
    """
    Lightweight HTTPS fetch for USD/ZEC. Cached for 60 seconds.
    """
    now = time.time()
    if _price_cache["value"] is not None and now - _price_cache["ts"] < 60:
        return _price_cache["value"]
    try:
        conn = http.client.HTTPSConnection("api.coingecko.com", timeout=5, context=ssl.create_default_context())
        headers = {
            "User-Agent": "ZcashFeeLab/1.0 (+https://github.com/ShieldedLabs/fee-calculator)",
            "Accept": "application/json",
        }
        conn.request("GET", "/api/v3/simple/price?ids=zcash&vs_currencies=usd", headers=headers)
        resp = conn.getresponse()
        if resp.status != 200:
            return None
        data = json.loads(resp.read().decode("utf-8"))
        price = data.get("zcash", {}).get("usd")
        if price is None:
            return None
        _price_cache["value"] = float(price)
        _price_cache["ts"] = now
        return float(price)
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def price_source_combined() -> float | None:
    # Prefer env override; else HTTP.
    env = price_source_env()
    if env is not None:
        return env
    return price_source_http()


def compute_block_metrics(provider, limit: int = 55) -> dict[str, float | None]:
    if not provider or not hasattr(provider, "block_window"):
        return {}
    try:
        blocks = provider.block_window(k=BLOCK_LOOKBACK_K, expiry=BLOCK_EXPIRY_WINDOW)
    except Exception as exc:
        log_event(f"compute_block_metrics failed: {exc}")
        return {}
    if blocks:
        filtered = [block for block in blocks if isinstance(block, dict) and block.get("tier") != "recent"]
        if filtered:
            blocks = filtered
    tx_sizes = []
    per_action_list = []
    tx_actions = []
    tx_fees = []
    transparent_actions = 0
    shielded_actions = 0
    transparent_bytes = 0.0
    shielded_bytes = 0.0
    for block in blocks or []:
        for tx in block.get("txs") or []:
            actions = tx.get("actions")
            fee = tx.get("fee_zats")
            size = tx.get("size")
            t_actions = tx.get("transparent_actions")
            s_actions = tx.get("shielded_actions")
            has_shielded = tx.get("has_shielded")
            if isinstance(actions, (int, float)) and actions > 0 and isinstance(fee, (int, float)):
                tx_actions.append(actions)
                tx_fees.append(fee)
                per_action_list.append(fee / actions)
            if isinstance(size, (int, float)) and size > 0:
                tx_sizes.append(size)
            if isinstance(t_actions, (int, float)) and isinstance(s_actions, (int, float)):
                transparent_actions += t_actions
                shielded_actions += s_actions
                if isinstance(size, (int, float)) and size > 0 and isinstance(has_shielded, bool):
                    if has_shielded:
                        shielded_bytes += size
                    else:
                        transparent_bytes += size
    avg_size_kb = (sum(tx_sizes) / len(tx_sizes) / 1024) if tx_sizes else None
    total_actions = sum(tx_actions)
    avg_actions_per_tx = (sum(tx_actions) / len(tx_actions)) if tx_actions else None
    avg_fee_per_action = (sum(tx_fees) / total_actions) if total_actions else None
    median_fee_per_action = None
    if per_action_list:
        per_action_list.sort()
        mid = len(per_action_list) // 2
        if len(per_action_list) % 2:
            median_fee_per_action = per_action_list[mid]
        else:
            median_fee_per_action = (per_action_list[mid - 1] + per_action_list[mid]) / 2
    total_action_mix = transparent_actions + shielded_actions
    shielded_share = (shielded_actions / total_action_mix) if total_action_mix > 0 else None
    transparent_share = (transparent_actions / total_action_mix) if total_action_mix > 0 else None
    shielded_bpa = (shielded_bytes / shielded_actions) if shielded_actions > 0 else None
    transparent_bpa = (transparent_bytes / transparent_actions) if transparent_actions > 0 else None
    return {
        "avg_tx_size_kb": avg_size_kb,
        "avg_actions_per_tx": avg_actions_per_tx,
        "avg_fee_per_action_zats": avg_fee_per_action,
        "median_fee_per_action_zats": median_fee_per_action,
        "shielded_actions": shielded_actions if total_action_mix > 0 else None,
        "transparent_actions": transparent_actions if total_action_mix > 0 else None,
        "shielded_action_share": shielded_share,
        "transparent_action_share": transparent_share,
        "shielded_bytes_per_action": shielded_bpa,
        "transparent_bytes_per_action": transparent_bpa,
    }


def build_engine():
    auth_header = build_auth_header(ZEBRA_COOKIE_PATH)
    provider = ZebraProvider(ZEBRA_HOST, ZEBRA_PORT, auth_header)
    return FeeEngine(provider=provider, price_source=price_source_combined)


def main():
    engine = build_engine()
    FeeRequestHandler.engine = engine
    host = normalize_host(SERVER_HOST)
    server_cls = DualStackServer if ":" in host else ThreadingHTTPServer
    try:
        server = server_cls((host, SERVER_PORT), FeeRequestHandler)
    except OSError as exc:
        fallback_host = "0.0.0.0"
        log_event(f"Bind failed on {host}:{SERVER_PORT} ({exc}); retrying on {fallback_host}")
        server = ThreadingHTTPServer((fallback_host, SERVER_PORT), FeeRequestHandler)
    server.daemon_threads = True
    print(f"Fee service listening on {server.server_address[0]}:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
