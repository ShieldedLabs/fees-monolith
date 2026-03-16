"""
Core fee calculation and congestion simulation logic for the fee-calculator backend.

This module centralizes the models that were previously implemented in the browser so
they can be exercised server-side (proxy.py) and unit-tested. The focus is on:
  - Market-based fee hints from the recent block window
  - Cramér–Lundberg reserve model for Express lane guidance
  - Paris Metro tier pricing (Standard / Express)
  - Congestion simulation via synthetic backlog duplication

All values are expressed in zatoshis (zats) unless otherwise noted.
"""

from __future__ import annotations

import math
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

ZATS_PER_ZEC = 10**8
BLOCK_BYTES = 2 * 1024 * 1024  # 2 MB
BLOCK_KB = BLOCK_BYTES / 1024
BLOCK_INTERVAL_SECONDS = 75
# Demo floor aligned to 0.1 µZEC = 10 zats (see DISCREPANCIES.md / Market-Based doc)
PRICE_FLOOR_ZATS = 10
PRIORITY_MULTIPLIER = 10
ARRIVAL_WINDOW_SECONDS = 180  # three minutes
BLOCK_LOOKBACK_K = 5
BLOCK_EXPIRY_WINDOW = 50

PARIS_LANES: tuple[dict[str, object], ...] = (
    {"key": "standard", "target_blocks": 50, "capacity_share": 0.7},
    {"key": "priority", "target_blocks": 4, "capacity_share": 0.3},
)


# ----- Helpers --------------------------------------------------------------

def round_power_of_ten_nearest(value: float, floor: int = PRICE_FLOOR_ZATS) -> int:
    """Round to the nearest power of ten; enforce a minimum floor."""
    if not math.isfinite(value) or value <= 0:
        return int(floor)
    log_val = math.log10(value)
    if not math.isfinite(log_val):
        return int(floor)
    rounded = 10 ** int(round(log_val))
    return int(max(floor, rounded))


def median_from_prices(
    prices: Sequence[tuple[float, float]],
    capacity_actions: float,
    used_actions: float,
    sample_count: int,
) -> dict[str, object]:
    """
    Compute the weighted median price per action given capacity and usage.
    Mirrors computeMedianFromPrices in the legacy browser code.
    """
    if not prices or used_actions <= 0:
        return {
            "median": PRICE_FLOOR_ZATS,
            "congested": False,
            "coverage": 0,
            "sample_size": sample_count,
            "used_actions": used_actions,
        }
    # keep deterministic ordering
    ordered = sorted(prices, key=lambda p: p[0])
    coverage = min(1.0, used_actions / max(capacity_actions, 1))
    slack_actions = max(0.0, capacity_actions - used_actions)
    raw_ratio = (0.5 * capacity_actions - slack_actions) / used_actions
    target_ratio = max(0.0, min(1.0, raw_ratio))
    target_weight = target_ratio * used_actions
    cumulative = 0.0
    median_value = ordered[-1][0]
    for fee, weight in ordered:
        cumulative += weight
        if cumulative >= target_weight:
            median_value = fee
            break
    median_value = max(PRICE_FLOOR_ZATS, median_value)
    has_cheaper = any(fee < median_value for fee, _ in ordered)
    congested = slack_actions <= 0 and not has_cheaper
    return {
        "median": median_value,
        "congested": congested,
        "coverage": coverage,
        "sample_size": sample_count,
        "used_actions": used_actions,
    }


def compute_market_hint(
    blocks: Sequence[dict[str, object]],
    actions_per_mb: float,
    simulate_blocks: bool = False,
) -> dict[str, object] | None:
    """
    Build the market-based median hint from a recent block window.

    Policy: treat every block as a full 2 MB for pricing, and fill slack with
    synthetic actions priced at half the demo floor (5 zats when the floor is
    10) so uncongested periods pull the median down instead of up. This is
    pricing-only; privacy metrics still use real fees.
    """
    if not blocks:
        return None
    fill_price = max(1, PRICE_FLOOR_ZATS // 2)
    prices: list[tuple[float, float]] = []
    total_actions = 0.0
    sample_count = 0
    for block in blocks:
        txs: Sequence[dict[str, object]] = block.get("txs") or ()
        # Always price against a full 2 MB block
        capacity_per_block = actions_per_mb * (BLOCK_KB / 1024)
        used = 0.0
        for tx in txs:
            fee = tx.get("fee_zats")
            actions = tx.get("actions")
            if not (isinstance(fee, (int, float)) and isinstance(actions, (int, float)) and actions > 0):
                continue
            per_action = fee / actions
            prices.append((per_action, actions))
            total_actions += actions
            used += actions
            sample_count += 1
        remaining = max(0.0, capacity_per_block - used)
        if remaining > 0:
            if simulate_blocks and prices:
                # Fill by duplicating observed prices round-robin.
                idx = 0
                while remaining > 0 and prices:
                    fee, weight = prices[idx % len(prices)]
                    chunk = min(weight, remaining)
                    prices.append((fee, chunk))
                    total_actions += chunk
                    remaining -= chunk
                    idx += 1
            else:
                prices.append((fill_price, remaining))
                total_actions += remaining
    capacity_actions = actions_per_mb * (BLOCK_KB / 1024) * len(blocks)
    return median_from_prices(prices, capacity_actions, total_actions, sample_count)


def weighted_quantile(values: Sequence[float], weights: Sequence[float], q: float) -> float | None:
    if not values or not weights or len(values) != len(weights):
        return None
    pairs = sorted(zip(values, weights), key=lambda x: x[0])  # noqa: B905
    total = sum(weights)
    if total <= 0:
        return None
    target = q * total
    running = 0.0
    for val, w in pairs:
        running += w
        if running >= target:
            return val
    return pairs[-1][0]


def compute_market_quote(
    blocks: Sequence[dict[str, object]],
    actions_per_mb: float,
    q: float = 0.5,
    min_floor: int = 10,
) -> dict[str, object] | None:
    if not blocks:
        return None
    recent = next((b for b in blocks if b.get("txs")), None)
    if not recent or not isinstance(recent.get("txs"), list):
        return None
    txs = recent["txs"]
    capacity = actions_per_mb * (BLOCK_KB / 1024)
    used = sum(tx.get("actions", 0) or 0 for tx in txs)
    if used <= 0 or capacity <= 0:
        return {"fee_zats": min_floor, "q": q, "q_prime": 0, "capacity_actions": capacity, "used_actions": used}
    q_prime = max(0.0, min(1.0, (q * capacity - (capacity - used)) / used))
    prices = []
    weights = []
    for tx in txs:
        fee = tx.get("fee_zats")
        actions = tx.get("actions")
        if isinstance(fee, (int, float)) and isinstance(actions, (int, float)) and actions > 0:
            prices.append(fee / actions)
            weights.append(actions)
    if not prices:
        return {"fee_zats": min_floor, "q": q, "q_prime": q_prime, "capacity_actions": capacity, "used_actions": used}
    if q_prime <= 0:
        raw = min_floor
    else:
        raw = weighted_quantile(prices, weights, q_prime)
        if raw is None:
            raw = min_floor
    fee = round_power_of_ten_nearest(max(min_floor, raw))
    return {
        "fee_zats": fee,
        "q": q,
        "q_prime": q_prime,
        "capacity_actions": capacity,
        "used_actions": used,
    }


def compute_arrival_rate(history: Sequence[tuple[float, float]]) -> float:
    """Arrival rate from backlog samples over ARRIVAL_WINDOW_SECONDS."""
    if len(history) < 2:
        return 0.0
    first_time, first_actions = history[0]
    last_time, last_actions = history[-1]
    span = max(1e-6, last_time - first_time)
    delta = last_actions - first_actions
    if delta < 0:
        return 0.0
    return delta / span


def compute_lane_quote(
    lane: dict[str, object],
    median_per_action: float,
    backlog_actions: float,
    arrival_rate: float,
    actions_per_block: float,
    override_horizon: int | None = None,
) -> dict[str, object]:
    share = float(lane.get("capacity_share", 0.0))
    target_blocks = int(override_horizon or lane.get("target_blocks", 1))
    service_rate = share * actions_per_block / BLOCK_INTERVAL_SECONDS
    reserve = backlog_actions * median_per_action
    claim_rate = arrival_rate * median_per_action
    target_seconds = target_blocks * BLOCK_INTERVAL_SECONDS
    if service_rate <= 0 or median_per_action <= 0:
        return {
            "key": lane["key"],
            "fee": None,
            "raw_fee": None,
            "expected_blocks": None,
            "reason": "Insufficient data",
        }
    numerator = (reserve / max(target_seconds, 1)) + claim_rate
    raw_fee = numerator / service_rate
    if not math.isfinite(raw_fee) or raw_fee <= 0:
        raw_fee = PRICE_FLOOR_ZATS
    raw_fee = max(PRICE_FLOOR_ZATS, raw_fee)
    rounded_fee = round_power_of_ten_nearest(raw_fee)
    drift = service_rate * raw_fee - claim_rate
    expected_blocks = math.inf if drift <= 0 else max(1.0, reserve / drift / BLOCK_INTERVAL_SECONDS)
    return {
        "key": lane["key"],
        "fee": rounded_fee,
        "raw_fee": raw_fee,
        "expected_blocks": expected_blocks,
        "reason": None if drift > 0 else "Backlog exceeds service capacity",
    }


def slack_lane_quote(lane: dict[str, object]) -> dict[str, object]:
    fee = PRICE_FLOOR_ZATS
    return {
        "key": lane["key"],
        "fee": fee,
        "raw_fee": fee,
        "expected_blocks": 1 if lane["key"] == "priority" else 10,
        "reason": "Blocks under capacity; using floor.",
        "slack": True,
    }


def compute_lane_arrival_blocks(
    quote_fee: float,
    backlog_actions: float,
    capacity_actions: float,
    horizon_blocks: int,
) -> dict[str, float]:
    competing = float(backlog_actions) if math.isfinite(backlog_actions) else 0.0
    cap = max(0.0, capacity_actions * horizon_blocks)
    ratio = 0 if cap <= 0 else competing / cap
    blocks_needed = 1 if competing <= 0 else max(1.0, ratio * horizon_blocks)
    if ratio <= 0.5:
        badge = "Very likely"
    elif ratio <= 1:
        badge = "Likely"
    elif ratio <= 2:
        badge = "Uncertain"
    else:
        badge = "Unlikely"
    return {
        "blocks_needed": blocks_needed,
        "capacity_actions": cap,
        "competing_actions": competing,
        "badge": badge,
        "quote_fee": quote_fee,
    }


def average(values: Iterable[float]) -> float | None:
    vals = [v for v in values if math.isfinite(v)]
    if not vals:
        return None
    return sum(vals) / len(vals)


# ----- Synthetic load -------------------------------------------------------

def synthetic_load(
    rows: Sequence[dict[str, object]],
    target_fill_ratio: float,
    std_fee: float,
    express_fee: float,
    avg_bytes_per_action: float,
) -> dict[str, object]:
    """
    Duplicate mempool rows round-robin until target block fill is reached.
    Used when congestion simulation is enabled.
    """
    target_bytes = BLOCK_BYTES * max(0.01, target_fill_ratio)
    rows_out: list[dict[str, object]] = []
    if not rows:
        # baseline synthetic tx: 2 actions, 50 µZEC/action
        actions = 2
        fee_per_action = 50 * 100  # µZEC -> zats
        fee_zats = int(actions * fee_per_action)
        size = int(avg_bytes_per_action * actions) if avg_bytes_per_action else 250
        bytes_accum = 0
        guard = 0
        while bytes_accum < target_bytes and guard < 2000:
            rows_out.append({
                "txid": f"synthetic-baseline-{guard}",
                "actions": actions,
                "size": size,
                "fee_zats": fee_zats,
                "synthetic": True,
                "lane": "standard",
            })
            bytes_accum += size
            guard += 1
    else:
        source: list[dict[str, object]] = []
        for idx, row in enumerate(rows):
            actions = max(1, int(row.get("actions") or 1))
            fee_zats = row.get("fee_zats")
            per_action = (fee_zats / actions) if (fee_zats and actions) else std_fee
            lane = "priority" if per_action >= express_fee else "standard"
            size = row.get("size")
            if not isinstance(size, (int, float)):
                size = avg_bytes_per_action * actions if avg_bytes_per_action else 250 * actions
            source.append({
                "txid": row.get("txid") or f"tx-{idx}",
                "actions": actions,
                "size": int(size),
                "fee_zats": int(fee_zats) if isinstance(fee_zats, (int, float)) else int(per_action * actions),
                "lane": lane,
            })
        bytes_accum = 0
        guard = 0
        while bytes_accum < target_bytes and guard < 10000:
            row = source[guard % len(source)]
            rows_out.append({
                "txid": f"synthetic-dup-{guard}-{row['txid']}",
                "actions": row["actions"],
                "size": row["size"],
                "fee_zats": row["fee_zats"],
                "synthetic": True,
                "lane": row["lane"],
            })
            bytes_accum += row["size"]
            guard += 1
    total_actions = sum(r.get("actions", 0) for r in rows_out)
    total_bytes = sum(r.get("size", 0) for r in rows_out)
    arrival_boost = total_actions / BLOCK_INTERVAL_SECONDS
    return {
        "rows": rows_out,
        "actions": total_actions,
        "bytes": total_bytes,
        "arrival_boost": arrival_boost,
    }


# ----- Engine ---------------------------------------------------------------

@dataclass
class Snapshot:
    updated_at: float
    price_usd: float | None
    block_kb_observed: float | None
    block_kb_effective: float
    actions_per_mb: float
    mempool_rows: list[dict[str, object]]
    arrival_rate: float
    backlog_actions: float
    median_fee_per_action: float | None
    market_hint: dict[str, object] | None
    standard_quote: dict[str, object]
    standard_arrival: dict[str, object] | None
    block_entries: list[dict[str, object]] = field(default_factory=list)
    market_quote: dict[str, object] | None = None
    avg_tx_size_bytes: float | None = None
    total_fee_zats: int = 0
    recycle_zats: int = 0
    privacy_bits: dict[str, object] | None = None
    horizon_blocks: int = 4


class FeeEngine:
    """
    Stateful calculator. It accepts a data provider (RPC-backed or fake) so it
    can be used in production and tests.
    """

    def __init__(self, provider, price_source=None):
        self.provider = provider
        self.price_source = price_source
        self.arrival_history: list[tuple[float, float]] = []

    # -- core API ---------------------------------------------------------
    def snapshot(self) -> Snapshot:
        now = time.time()
        price_usd = self._get_price_usd()
        mempool_rows = self.provider.mempool_rows()
        block_window = self.provider.block_window()
        lookback_blocks = self._lookback_blocks(block_window)
        total_fee_zats = self._total_fees(lookback_blocks)
        recycle_zats = int(total_fee_zats * 0.6)
        privacy_bits = self._privacy_bits(lookback_blocks)
        actions_per_mb = self._actions_per_mb(lookback_blocks)
        block_kb_observed = self._avg_block_kb(lookback_blocks)
        block_kb_effective = self._effective_block_kb(block_kb_observed, False)

        market_hint = compute_market_hint(lookback_blocks, actions_per_mb, simulate_blocks=False)
        standard_fee = round_power_of_ten_nearest(market_hint["median"]) if market_hint else PRICE_FLOOR_ZATS

        backlog_actions = sum(row.get("actions", 0) for row in mempool_rows)
        arrival_rate = 0.0  # Congestion/arrival estimation is frontend-only

        median_fee_per_action = self._median_fee_per_action(mempool_rows)
        actions_per_block = actions_per_mb * (block_kb_effective / 1024)
        market_quote = compute_market_quote(lookback_blocks, actions_per_mb, q=0.5, min_floor=PRICE_FLOOR_ZATS)

        # Standard: market median only (no CL drift/backlog coupling)
        standard_quote = {
            "key": "standard",
            "fee": standard_fee,
            "raw_fee": market_hint["median"] if market_hint else standard_fee,
            "expected_blocks": None,
            "reason": "Market median; backlog ignored",
            "slack": backlog_actions < actions_per_block,
        }

        # Arrival/block assignment estimation is purely frontend.
        standard_arrival = None

        return Snapshot(
            updated_at=now,
            price_usd=price_usd,
            block_kb_observed=block_kb_observed,
            block_kb_effective=block_kb_effective,
            actions_per_mb=actions_per_mb,
            mempool_rows=mempool_rows,
            arrival_rate=arrival_rate,
            backlog_actions=backlog_actions,
            median_fee_per_action=median_fee_per_action,
            market_hint=market_hint,
            standard_quote=standard_quote,
            standard_arrival=standard_arrival,
            block_entries=self._block_entries(block_window),
            market_quote=market_quote,
            avg_tx_size_bytes=self._avg_tx_size_bytes(mempool_rows, lookback_blocks),
            total_fee_zats=total_fee_zats,
            recycle_zats=recycle_zats,
            privacy_bits=privacy_bits,
            horizon_blocks=PARIS_LANES[1]["target_blocks"],
        )

    # -- helpers ----------------------------------------------------------
    def _get_price_usd(self) -> float | None:
        if not self.price_source:
            return None
        try:
            return float(self.price_source())
        except Exception:
            return None

    def _avg_bytes_per_action(self, rows: Sequence[dict[str, object]]) -> float | None:
        bytes_total = 0.0
        actions_total = 0.0
        for row in rows:
            size = row.get("size")
            actions = row.get("actions")
            if not (isinstance(size, (int, float)) and isinstance(actions, (int, float)) and actions > 0):
                continue
            bytes_total += size
            actions_total += actions
        if actions_total <= 0:
            return None
        return bytes_total / actions_total

    def _median_fee_per_action(self, rows: Sequence[dict[str, object]]) -> float | None:
        fees = []
        for row in rows:
            fee = row.get("fee_zats")
            actions = row.get("actions")
            if isinstance(fee, (int, float)) and isinstance(actions, (int, float)) and actions > 0:
                fees.append(fee / actions)
        if not fees:
            return None
        fees.sort()
        mid = len(fees) // 2
        if len(fees) % 2:
            return fees[mid]
        return (fees[mid - 1] + fees[mid]) / 2

    def _actions_per_mb(self, block_window: Sequence[dict[str, object]]) -> float:
        """
        Derive service capacity from the recent K blocks; fall back to 420 actions/MB.
        """
        recent = []
        for block in block_window or []:
            if block.get("tier") == "recent" or len(recent) < BLOCK_LOOKBACK_K:
                recent.append(block)
            if len(recent) >= BLOCK_LOOKBACK_K:
                break
        total_actions = 0.0
        total_bytes = 0.0
        for block in recent:
            actions = block.get("service_actions")
            size_bytes = block.get("size_bytes")
            if isinstance(actions, (int, float)) and isinstance(size_bytes, (int, float)) and size_bytes > 0:
                total_actions += actions
                total_bytes += size_bytes
        if total_bytes > 0:
            mb = total_bytes / (1024 * 1024)
            if mb > 0:
                return total_actions / mb
        return 420.0

    def _avg_block_kb(self, block_window: Sequence[dict[str, object]]) -> float | None:
        recent = []
        for block in block_window or []:
            if block.get("tier") == "recent" or len(recent) < BLOCK_LOOKBACK_K:
                recent.append(block)
            if len(recent) >= BLOCK_LOOKBACK_K:
                break
        bytes_vals = [block.get("size_bytes") for block in recent if isinstance(block.get("size_bytes"), (int, float))]
        if not bytes_vals:
            return None
        return average([b / 1024 for b in bytes_vals])

    def _lookback_blocks(self, block_window: Sequence[dict[str, object]]) -> list[dict[str, object]]:
        if not block_window:
            return []
        has_tier = any(isinstance(block, dict) and block.get("tier") for block in block_window)
        if has_tier:
            filtered = [block for block in block_window if block.get("tier") != "recent"]
            return filtered or list(block_window)
        if len(block_window) > BLOCK_EXPIRY_WINDOW:
            return list(block_window[BLOCK_LOOKBACK_K:])
        return list(block_window)

    def _effective_block_kb(self, observed_kb: float | None, simulate: bool) -> float:
        if simulate:
            return BLOCK_KB
        if not observed_kb or observed_kb <= 0:
            return BLOCK_KB
        kb = min(observed_kb, BLOCK_KB)
        if kb < BLOCK_KB * 0.75:
            return BLOCK_KB
        return kb

    def _block_entries(self, block_window: Sequence[dict[str, object]]) -> list[dict[str, object]]:
        entries = []
        for block in block_window or []:
            txs = block.get("txs") or []
            per_action = []
            for tx in txs:
                fee = tx.get("fee_zats")
                actions = tx.get("actions")
                if isinstance(fee, (int, float)) and isinstance(actions, (int, float)) and actions > 0:
                    per_action.append(fee / actions)
            median_fee = None
            mean_fee = None
            if per_action:
                per_action.sort()
                mid = len(per_action) // 2
                if len(per_action) % 2:
                    median_fee = per_action[mid]
                else:
                    median_fee = (per_action[mid - 1] + per_action[mid]) / 2
                mean_fee = sum(per_action) / len(per_action)
            entries.append({
                "height": block.get("height"),
                "hash": block.get("hash"),
                "bytes": block.get("size_bytes"),
                "tx_count": block.get("tx_count"),
                "tier": block.get("tier"),
                "median_fee_per_action_zats": median_fee,
                "mean_fee_per_action_zats": mean_fee,
            })
        return entries

    def _avg_tx_size_bytes(
        self,
        mempool_rows: Sequence[dict[str, object]],
        block_window: Sequence[dict[str, object]],
    ) -> float | None:
        sizes = []
        for row in mempool_rows or []:
            size = row.get("size")
            if isinstance(size, (int, float)) and size > 0:
                sizes.append(size)
        for block in block_window or []:
            for tx in block.get("txs") or []:
                size = tx.get("size")
                if isinstance(size, (int, float)) and size > 0:
                    sizes.append(size)
        if not sizes:
            return None
        return sum(sizes) / len(sizes)

    def _total_fees(self, block_window: Sequence[dict[str, object]]) -> int:
        total = 0
        for block in block_window or []:
            for tx in block.get("txs") or []:
                fee = tx.get("fee_zats")
                if isinstance(fee, (int, float)):
                    total += int(fee)
        return total

    def _privacy_bits(self, block_window: Sequence[dict[str, object]]) -> dict[str, object] | None:
        samples: list[tuple[float, float]] = []
        for block in block_window or []:
            for tx in block.get("txs") or []:
                fee = tx.get("fee_zats")
                actions = tx.get("actions")
                if not (isinstance(fee, (int, float)) and isinstance(actions, (int, float)) and actions > 0):
                    continue
                per_action = fee / actions
                samples.append((per_action, actions))
        if not samples:
            return None
        raw = self._entropy_bits(samples, lambda v: v)
        bucketed = self._entropy_bits(samples, lambda v: round_power_of_ten_nearest(max(v, PRICE_FLOOR_ZATS)))
        return {
            "raw_bits": raw["bits"],
            "bucket_bits": bucketed["bits"],
            "samples": raw["total"],
            "buckets": bucketed["count"],
        }

    @staticmethod
    def _entropy_bits(samples: Sequence[tuple[float, float]], bucket_fn) -> dict[str, float | int]:
        weight_by_bucket: dict[float, float] = {}
        total = 0.0
        for fee, weight in samples:
            bucket = bucket_fn(fee)
            weight_by_bucket[bucket] = weight_by_bucket.get(bucket, 0.0) + weight
            total += weight
        if total <= 0 or not weight_by_bucket:
            return {"bits": 0.0, "total": 0.0, "count": 0}
        entropy = 0.0
        for w in weight_by_bucket.values():
            p = w / total
            entropy -= p * math.log2(p)
        return {"bits": entropy, "total": total, "count": len(weight_by_bucket)}


# ----- Fake provider for tests ---------------------------------------------

class FakeProvider:
    """
    Deterministic provider used by unit and integration tests.
    """

    def __init__(self):
        self._mempool_rows = []
        self._blocks = []

    def set_mempool(self, rows: list[dict[str, object]]):
        self._mempool_rows = rows

    def set_blocks(self, blocks: list[dict[str, object]]):
        self._blocks = blocks

    def mempool_rows(self) -> list[dict[str, object]]:
        return list(self._mempool_rows)

    def block_window(self) -> list[dict[str, object]]:
        return list(self._blocks)
