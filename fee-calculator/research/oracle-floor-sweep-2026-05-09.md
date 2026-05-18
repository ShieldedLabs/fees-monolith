# Oracle × Floor Sweep Results

Comparing four mechanism variants against Mohak Nahta's adversarial scenarios.

**Variants:**
- A: median-of-medians + floor=5000 (Mohak default; nikete oracle, current mainnet floor)
- B: median-of-medians + floor=1000 (nikete oracle + marginal-fee draft floor)
- C: action-weighted-median + floor=5000 (v0 oracle, current mainnet floor)
- D: action-weighted-median + floor=1000 (v0 oracle + marginal-fee draft floor — what we shipped)

## Harm ratio per scenario × variant (lower is better)

| scenario | A (mom/5000) | B (mom/1000) | C (awm/5000) | D (awm/1000) |
|---|---|---|---|---|
| `burst_spam_persistence` | 0.0 | 0.0 | 0.0 | 0.0 |
| `low_volume_median_poisoning` | 0.0004 | 0.0 | 0.0004 | 0.0 |
| `fast_lane_flap` | 0.0 | 0.0 | 0.0 | 0.0 |
| `miner_self_dealing` | 0.0 | 0.0 | 0.3591 | 0.0 |
| `floor_fee_saturation` | 0.0 | 0.0 | 0.0 | 0.0 |

## Fee bucket jumps (lower = more stable)

| scenario | A | B | C | D |
|---|---|---|---|---|
| `burst_spam_persistence` | 1 | 0 | 1 | 0 |
| `low_volume_median_poisoning` | 1 | 0 | 1 | 0 |
| `fast_lane_flap` | 0 | 0 | 0 | 0 |
| `miner_self_dealing` | 0 | 0 | 2 | 0 |
| `floor_fee_saturation` | 1 | 0 | 1 | 0 |
