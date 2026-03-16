(() => {
  const POLL_INTERVAL_MS = 4000;
  const BLOCK_BYTES = 2 * 1024 * 1024;
  const BLOCK_INTERVAL_SECONDS = 75;
  const BLOCK_KB = BLOCK_BYTES / 1024;
  const DEFAULT_FLOOR_ZATS = 10;
  const FLOOR_OPTIONS = [5, 10, 100, 1000];
  const EXPRESS_TARGET_BLOCKS = 4;
  const EXPRESS_SHARE = 0.3;
  const els = {
    tableBody: document.getElementById('mempool-likely-body'),
    stdValue: document.getElementById('pmp-standard-fee'),
    stdDesc: document.getElementById('pmp-standard-desc'),
    stdBucketValue: document.getElementById('pmp-standard-fee-bucketed'),
    stdBucketDesc: document.getElementById('pmp-standard-desc-bucketed'),
    exprValue: document.getElementById('pmp-priority-fee'),
    exprDesc: document.getElementById('pmp-priority-desc'),
    // note removed (element no longer in DOM)
    blocksBars: document.getElementById('blocks-chart-bars'),
    blocksCongestion: document.getElementById('blocks-congestion'),
    blocksNote: document.getElementById('blocks-chart-note'),
    spikeButton: document.getElementById('mempool-spike-button'),
    utilBar: null,
    nsmRecycle: document.getElementById('nsm-recycle'),
    nsmWindow: document.getElementById('nsm-window'),
    floorSelect: document.getElementById('floor-price-select'),
  };

  const state = {
    timer: null,
    fetching: false,
    last: null,
    floorZats: DEFAULT_FLOOR_ZATS,
    arrivalSnapshot: null,
  };

  function effectiveBlockWindow(entries = []) {
    if (!Array.isArray(entries)) return [];
    if (entries.length > 50) return entries.slice(5, 55);
    return entries;
  }

  function fmtMicro(zats) {
    if (!Number.isFinite(zats)) return '—';
    return `${(zats / 100).toLocaleString('en-US', { maximumFractionDigits: 2, minimumFractionDigits: 0 })} µZEC`;
  }

  function fmtBlocks(value) {
    if (!Number.isFinite(value)) return '≈∞ blocks';
    return `≈${Math.max(1, Math.ceil(value)).toLocaleString('en-US')} blocks`;
  }

  function fmtUsd(zats, usdPerZec) {
    if (!Number.isFinite(zats) || !Number.isFinite(usdPerZec) || usdPerZec <= 0) return 'USD unavailable';
    const usd = (zats / 1e8) * usdPerZec;
    const places = 5;
    return `$${usd.toFixed(places)}`;
  }

  function renderCards(data, sim) {
    const lanes = data.lanes || {};
    const std = lanes.standard;
    const expr = lanes.express;
    const usdPerZec = Number(data.price?.usd_per_zec);
    const observedMedian = data.market?.median;
    const medianBase = observedMedian;
    const medianActual = Number(data.metrics?.median_fee_per_action_zats);
    const stdFloor = state.floorZats || DEFAULT_FLOOR_ZATS;
    const stdBase = medianBase ? roundPowerOfTenNearest(Math.max(stdFloor, medianBase), stdFloor) : null;
    const stdFeeOverride = stdBase;
    const exprFeeOverride = stdFeeOverride ? Math.max(stdFeeOverride * 10, stdFeeOverride) : null;
    renderStandardWalkthrough({ medianBase, stdBase, usdPerZec: usdPerZec, stdFee: stdFeeOverride });
    renderExpressWalkthrough({
      stdFee: stdFeeOverride,
      tunedFee: exprFeeOverride,
      usdPerZec,
    });

    // Prepare shared arrival/backlog context for quiet Express tuning.
    const actionsPerBlock = (Number(data.service?.actions_per_mb) || 420) * ((Number(data.service?.block_kb_effective) || BLOCK_KB) / 1024);
    const backlogActions = (data.mempool?.rows || []).reduce((sum, r) => sum + (Number(r.actions) || 0), 0)
      || Number(data.arrival?.backlog_actions) || 0;
    const arrivalRate = (Number(data.arrival?.arrival_rate_actions_per_s) || 0) + (sim.syntheticArrivalBoost || 0);
    // Standard
    if (std && (Number.isFinite(std.fee_zats) || Number.isFinite(stdFeeOverride))) {
      const feeZats = Number.isFinite(stdFeeOverride) ? stdFeeOverride : std.fee_zats;
      const usdLabel = Number.isFinite(stdFeeOverride) ? fmtUsd(feeZats, usdPerZec) : (std.usd || fmtUsd(feeZats, usdPerZec));
      if (els.stdValue) els.stdValue.innerHTML = `<div class=\"lane-price-zec\">${fmtMicro(feeZats)}</div><div class=\"lane-price-usd\">${usdLabel}</div>`;
      const blocksLabel = 'Median fee; likely within the next ~50 blocks.';
      if (els.stdDesc) els.stdDesc.textContent = blocksLabel;
    } else {
      if (els.stdValue) els.stdValue.textContent = '—';
      if (els.stdDesc) els.stdDesc.textContent = 'Waiting for block window data.';
    }
    const exprCard = document.querySelector('[data-lane="priority"]');
    if (exprCard) exprCard.style.display = '';

    const congestedMedian = (() => {
      const fee = data.metrics?.median_fee_per_action_zats
        ?? data.metrics?.mean_fee_per_action_zats
        ?? data.metrics?.avg_fee_per_action_zats
        ?? data.market?.median;
      return Number.isFinite(fee) ? fee : null;
    })();

    const stdMedianFee = Number.isFinite(congestedMedian)
      ? roundPowerOfTenNearest(congestedMedian, stdFloor)
      : stdFeeOverride;
    const exprMedianFee = Number.isFinite(stdMedianFee) ? stdMedianFee * 10 : null;

    if (els.stdBucketValue) {
      if (Number.isFinite(stdMedianFee)) {
        const usdLabel = fmtUsd(stdMedianFee, usdPerZec);
        els.stdBucketValue.innerHTML = `<div class="lane-price-zec">${fmtMicro(stdMedianFee)}</div><div class="lane-price-usd">${usdLabel}</div>`;
      } else {
        els.stdBucketValue.textContent = '—';
      }
    }
    if (els.stdBucketDesc) {
      els.stdBucketDesc.textContent = 'Median of last 50 blocks (no synthetic fill), rounded to power of ten.';
    }

    if (els.exprValue) {
      if (Number.isFinite(exprMedianFee)) {
        const usdLabel = fmtUsd(exprMedianFee, usdPerZec);
        els.exprValue.innerHTML = `<div class="lane-price-zec">${fmtMicro(exprMedianFee)}</div><div class="lane-price-usd">${usdLabel}</div>`;
      } else {
        els.exprValue.textContent = '—';
      }
    }
    if (els.exprDesc) {
      els.exprDesc.textContent = 'Fast lane = 10× the duplicated-tx median fee per action.';
    }
    // Note removed; no DOM target remains.

  }

  function renderTable(rows = []) {
    if (!els.tableBody) return;
    const target = rows.slice(0, 100);
    if (!target.length) {
      els.tableBody.innerHTML = '<tr><td colspan=\"3\">Waiting for mempool…</td></tr>';
      return;
    }
    const html = target
      .map((row) => {
        const feeCell = Number.isFinite(row.per_action_zats)
          ? (row.per_action_zats / 100).toLocaleString('en-US', { maximumFractionDigits: 2 })
          : '—';
        const sizeCell = Number.isFinite(row.size)
          ? (row.size / 1024).toFixed(2)
          : '—';
        const link = row.txid ? `https://mainnet.zcashexplorer.app/transactions/${row.txid}` : '#';
        return `<tr><td title=\"${row.txid || ''}\"><a href=\"${link}\" target=\"_blank\" rel=\"noopener\">${row.txid_short || '—'}</a></td><td>${feeCell}</td><td>${sizeCell}</td></tr>`;
      })
      .join('');
    els.tableBody.innerHTML = html;
  }

  function renderBlocks(entries = []) {
    if (!els.blocksBars) return;
    const windowEntries = effectiveBlockWindow(entries);
    if (!windowEntries.length) {
      els.blocksBars.innerHTML = '<div class="blocks-chart__empty">Waiting for block data…</div>';
      els.blocksBars.style.removeProperty('--block-count');
      if (els.blocksCongestion) els.blocksCongestion.textContent = '—';
      if (els.blocksNote) els.blocksNote.textContent = 'Waiting for block data…';
      return;
    }
    els.blocksBars.style.setProperty('--block-count', windowEntries.length);

    if (els.blocksCongestion) {
      const used = windowEntries.reduce((sum, entry) => {
        const bytes = Number(entry.bytes);
        return Number.isFinite(bytes) && bytes > 0
          ? sum + Math.min(bytes, BLOCK_BYTES)
          : sum;
      }, 0);
      const capacity = windowEntries.length * BLOCK_BYTES;
      const pct = capacity > 0 ? (used / capacity) * 100 : null;
      els.blocksCongestion.textContent = Number.isFinite(pct) ? `${pct.toFixed(1)}%` : '—';
    }

    const bars = windowEntries.map((entry) => {
      const bytes = Number(entry.bytes) || 0;
      const pct = Math.min(1, bytes / BLOCK_BYTES) * 100;
      const heightLabel = entry.height != null ? `#${entry.height}` : '—';
      const label = `${(bytes / 1024 / 1024).toFixed(2)} MB (${pct.toFixed(1)}%)`;
      const title = `${heightLabel} · ${label}`;
      const tierClass = entry.tier === 'recent' ? 'block-bar--recent' : 'block-bar--frozen';
      return `<abbr class="block-bar ${tierClass}" style="--used:${pct.toFixed(1)};" title="${title}" aria-label="${title}"><div class="block-bar__fill"></div></abbr>`;
    }).join('');
    els.blocksBars.innerHTML = bars;
    if (els.blocksNote) els.blocksNote.textContent = '';
  }

  function renderBlocksTable(entries = []) {
    const body = document.getElementById('blocks-recent-body');
    if (!body) return;
    const windowEntries = effectiveBlockWindow(entries);
    if (!windowEntries.length) {
      body.innerHTML = '<tr><td colspan="3">Waiting for block data…</td></tr>';
      return;
    }
    const rows = windowEntries.map((entry) => {
      const bytes = Number(entry.bytes) || 0;
      const util = Math.min(100, (bytes / BLOCK_BYTES) * 100);
      const hash = entry.hash || '—';
      const median = entry.median_fee_per_action_zats ?? entry.mean_fee_per_action_zats;
      const medianCell = Number.isFinite(median) ? `${(median / 100).toFixed(3)} µZEC` : '—';
      const shortHash = hash && hash.length > 10 ? `${hash.slice(0, 8)}…${hash.slice(-4)}` : hash;
      const link = hash && hash !== '—'
        ? `<a href="https://mainnet.zcashexplorer.app/blocks/${hash}" target="_blank" rel="noopener" title="${hash}">${shortHash}</a>`
        : shortHash;
      return `<tr><td>${link}</td><td>${util.toFixed(1)}%</td><td>${medianCell}</td></tr>`;
    }).join('');
    body.innerHTML = rows;
  }

  function medianPerAction(rows = []) {
    const values = rows
      .map((row) => {
        if (!Number.isFinite(row.fee_zats) || !Number.isFinite(row.actions) || row.actions <= 0) return null;
        return row.fee_zats / row.actions;
      })
      .filter((v) => Number.isFinite(v) && v > 0)
      .sort((a, b) => a - b);
    if (!values.length) return null;
    const mid = Math.floor(values.length / 2);
    if (values.length % 2) return values[mid];
    return (values[mid - 1] + values[mid]) / 2;
  }

  function roundPowerOfTenNearest(value, floor = state.floorZats || DEFAULT_FLOOR_ZATS) {
    if (!Number.isFinite(value) || value <= 0) return floor;
    const log = Math.log10(value);
    if (!Number.isFinite(log)) return floor;
    const rounded = 10 ** Math.round(log);
    return Math.max(floor, rounded);
  }

  function computeExpectedBlocks({ fee, backlogActions, arrivalRate, medianPerAction, actionsPerBlock, share }) {
    if (!Number.isFinite(fee) || fee <= 0) return null;
    const serviceRate = share * actionsPerBlock / BLOCK_INTERVAL_SECONDS;
    const perAction = Number.isFinite(medianPerAction) && medianPerAction > 0 ? medianPerAction : fee;
    const reserve = (Number(backlogActions) || 0) * perAction;
    const claimRate = (Number(arrivalRate) || 0) * perAction;
    const drift = serviceRate * fee - claimRate;
    const laneCapacityPerBlock = actionsPerBlock * share;
    const backlogOnly = laneCapacityPerBlock > 0 ? (Number(backlogActions) || 0) / laneCapacityPerBlock : Infinity;
    if (!Number.isFinite(drift) || drift <= 0) {
      // If arrivals exceed service, backlog grows; show a pessimistic finite bound instead of stale server ETA.
      return Number.isFinite(backlogOnly) ? Math.max(1, backlogOnly) : Infinity;
    }
    const blocks = reserve / drift / BLOCK_INTERVAL_SECONDS;
    if (!Number.isFinite(blocks)) return Infinity;
    return Math.max(1, blocks);
  }

  function renderArrival(data, sim) {
    const arrival = Number(data.arrival?.arrival_rate_actions_per_s) || 0;
    const arrivalTotal = arrival;
    const actionsPerMb = Number(data.service?.actions_per_mb) || 420;
    const blockKb = Number(data.service?.block_kb_effective) || BLOCK_KB;
    const serviceActions = actionsPerMb * (blockKb / 1024);
    const serviceRate = serviceActions / BLOCK_INTERVAL_SECONDS;
    let status = 'Waiting for samples…';
    const ratio = serviceRate > 0 ? arrivalTotal / serviceRate : Infinity;
    if (Number.isFinite(ratio)) {
      if (ratio < 0.9) status = 'Below capacity';
      else if (ratio <= 1.1) status = 'Near capacity';
      else status = 'Over capacity';
    }
    state.arrivalSnapshot = {
      arrivalTotal,
      serviceRate,
      ratio,
      status,
    };
  }

  function renderSyntheticTable(payload) {
    const setText = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    };

    const blocks = effectiveBlockWindow(payload?.blocks?.entries || []);
    const memRows = payload?.mempool?.rows || [];

    // Preserve original real count
    const realCountRaw = blocks.reduce((sum, block) => {
      const count = Number(block.tx_count);
      return Number.isFinite(count) ? sum + count : sum;
    }, 0);
    const realCount = realCountRaw > 0 ? realCountRaw : memRows.length;

    const realFee =
      payload?.metrics?.median_fee_per_action_zats ??
      payload?.metrics?.mean_fee_per_action_zats ??
      payload?.metrics?.avg_fee_per_action_zats ??
      payload?.market?.median;
    const floorZats = state.floorZats || DEFAULT_FLOOR_ZATS;
    const realFeeSafe = Number.isFinite(realFee) && realFee > 0 ? realFee : floorZats;

    // Avg tx bytes: metrics -> mempool -> block tx sizes -> actions estimate, then clamp.
    let avgTxBytes = Number.isFinite(payload?.metrics?.avg_tx_size_kb)
      ? payload.metrics.avg_tx_size_kb * 1024
      : null;
    if ((!avgTxBytes || avgTxBytes <= 0) && memRows.length) {
      const szSum = memRows.reduce((s, r) => s + (Number(r.size) || 0), 0);
      avgTxBytes = szSum > 0 ? szSum / memRows.length : null;
    }
    if ((!avgTxBytes || avgTxBytes <= 0) && blocks.length) {
      const sizes = [];
      blocks.forEach((b) => {
        (b.txs || []).forEach((t) => {
          const sz = Number(t.size);
          if (Number.isFinite(sz) && sz > 0) sizes.push(sz);
        });
      });
      if (sizes.length) {
        const sum = sizes.reduce((s, v) => s + v, 0);
        avgTxBytes = sum / sizes.length;
      }
    }
    if (!Number.isFinite(avgTxBytes) || avgTxBytes <= 0) {
      const avgActionsPerTx = Number(payload?.metrics?.avg_actions_per_tx);
      const actionsPerMb = Number(payload?.service?.actions_per_mb);
      if (Number.isFinite(avgActionsPerTx) && Number.isFinite(actionsPerMb) && actionsPerMb > 0) {
        const bytesPerAction = (1024 * 1024) / actionsPerMb;
        avgTxBytes = bytesPerAction * avgActionsPerTx;
      }
    }
    const avgBytesSafe = Number.isFinite(avgTxBytes) && avgTxBytes > 0
      ? Math.max(500, Math.min(avgTxBytes, 100000))
      : 1000;

    let syntheticCount = null;
    if (Number.isFinite(avgBytesSafe) && blocks.length) {
      syntheticCount = 0;
      blocks.forEach((block) => {
        const usedBytes = Number(block.bytes);
        if (!Number.isFinite(usedBytes) || usedBytes <= 0) return;
        const slackBytes = Math.max(0, BLOCK_BYTES - usedBytes);
        if (slackBytes <= 0) return;
        syntheticCount += Math.round(slackBytes / avgBytesSafe);
      });
    }

    setText('real-transaction-count', `${realCount.toLocaleString('en-US')} tx`);
    setText('real-avg-fee-per-action', Number.isFinite(realFeeSafe) ? fmtMicro(realFeeSafe) : '—');

    const syntheticCountLabel = syntheticCount === null
      ? '—'
      : `${Math.max(0, syntheticCount).toLocaleString('en-US')} tx`;
    setText('synthetic-transaction-count', syntheticCountLabel);

    // Congested example: duplicate live txs across last 55 blocks until full; no synthetic remain.
    const totalBlockBytes = Math.max(1, Math.min(55, blocks.length || 55)) * BLOCK_BYTES;
    const usedBlockBytes = blocks.reduce((sum, b) => sum + (Number(b.bytes) || 0), 0);
    let dupCount = 0;
    if (Number.isFinite(avgBytesSafe)) {
      const slack = Math.max(0, totalBlockBytes - usedBlockBytes);
      dupCount = Math.max(0, Math.ceil(slack / avgBytesSafe));
    }
    const congestedCount = memRows.length + dupCount;
    const congestedLabel = `${congestedCount.toLocaleString('en-US')} tx`;
    const feeLabel = Number.isFinite(realFeeSafe) ? fmtMicro(realFeeSafe) : '—';
    setText('real-transaction-count-congested', congestedLabel);
    setText('real-avg-fee-per-action-congested', feeLabel);
    setText('congested-synthetic-tx-count', '0 tx');
    setText('synthetic-avg-fee-per-action', fmtMicro(floorZats));
  }

  function applySummary(payload, { skipHistory = false } = {}) {
    state.last = payload;
    const simulated = {
      mempoolRows: payload.mempool?.rows || [],
      blockEntries: payload.blocks?.entries || [],
      syntheticActions: 0,
      syntheticBytes: 0,
      syntheticArrivalBoost: 0,
    };
    const tableRows = simulated.mempoolRows;
    renderCards(payload, simulated);
    renderTable(tableRows);
    renderBlocks(simulated.blockEntries);
    renderBlocksTable(simulated.blockEntries);
    renderAvgFromPayload(payload);
    renderArrival(payload, simulated);
    renderSyntheticTable(payload);
    renderNsm(payload);
    renderPrivacy(payload);
    
  }

  function setFloorZats(zats) {
    const value = Number(zats);
    if (!Number.isFinite(value) || !FLOOR_OPTIONS.includes(value)) return;
    state.floorZats = value;
    if (els.floorSelect && els.floorSelect.value !== String(value)) {
      els.floorSelect.value = String(value);
    }
    if (state.last) applySummary(state.last, { skipHistory: true });
  }

  function fetchSummary(force = false) {
    if (state.fetching && !force) return;
    state.fetching = true;
    const params = new URLSearchParams();
    fetch(`/api/summary?${params.toString()}`, { cache: 'no-cache' })
      .then((res) => res.json())
      .then(applySummary)
      .catch((err) => {
        console.error('[mempool] summary failed', err);
        if (els.tableBody) {
          els.tableBody.innerHTML = `<tr><td colspan=\"3\">${err?.message || 'Unable to load data.'}</td></tr>`;
        }
      })
      .finally(() => { state.fetching = false; });
  }

  function renderNsm(data) {
    const nsm = data.nsm || {};
    if (els.nsmWindow) {
      const count = Number(nsm.window_blocks) || 0;
      els.nsmWindow.textContent = count ? count.toString() : '55';
    }
    if (!els.nsmRecycle) return;
    const zats = Number(nsm.recycle_zats) || 0;
    const zec = zats / 1e8;
    const usd = nsm.recycle_usd;
    if (zats <= 0) {
      els.nsmRecycle.textContent = '—';
      return;
    }
    const zecLabel = zec.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
    const usdLabel = usd || 'USD N/A';
    els.nsmRecycle.textContent = `${zecLabel} ZEC (${usdLabel})`;
  }

  function renderPrivacy(data) {
    const privacy = data.privacy || {};
    const raw = Number(privacy.raw_bits);
    const bucket = Number(privacy.bucket_bits);
    const rawElTable = document.getElementById('fee-entropy-current-table');
    const bucketElTable = document.getElementById('fee-entropy-bucketed-table');
    if (rawElTable) rawElTable.textContent = Number.isFinite(raw) ? raw.toFixed(2) : '—';
    if (bucketElTable) bucketElTable.textContent = Number.isFinite(bucket) ? bucket.toFixed(2) : '—';
  }


  function bindFloorSelect() {
    const select = els.floorSelect;
    if (!select) return;
    // Ensure only allowed options remain; fallback to default if mismatched.
    if (!FLOOR_OPTIONS.map(String).includes(select.value)) {
      select.value = String(DEFAULT_FLOOR_ZATS);
    }
    select.addEventListener('change', (e) => {
      const next = Number(e.target.value);
      setFloorZats(next);
    });
  }


  function renderStandardWalkthrough({ medianBase, stdBase, usdPerZec, stdFee }) {
    const setText = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    };
    setText('std-step-rounded', Number.isFinite(stdBase) ? `${(stdBase / 100).toFixed(3)} µZEC` : '—');
    const fee = Number.isFinite(stdFee) ? stdFee : stdBase;
    setText('std-step-final', Number.isFinite(fee) ? `${(fee / 100).toFixed(3)} µZEC` : '—');
    setText('std-step-usd', Number.isFinite(fee) ? fmtUsd(fee, usdPerZec) : '—');
  }

  function renderExpressWalkthrough({ stdFee, tunedFee, usdPerZec }) {
    const setText = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    };
    const base = Number.isFinite(stdFee) ? stdFee * 10 : null;
    setText('expr-step-base', Number.isFinite(base) ? `${(base / 100).toFixed(3)} µZEC` : '—');
    setText('expr-step-tuned', Number.isFinite(tunedFee) ? `${(tunedFee / 100).toFixed(3)} µZEC` : '—');
    const finalFee = Number.isFinite(tunedFee) ? tunedFee : base;
    setText('expr-step-final', Number.isFinite(finalFee) ? `${(finalFee / 100).toFixed(3)} µZEC` : '—');
    setText('expr-step-usd', Number.isFinite(finalFee) ? fmtUsd(finalFee, usdPerZec) : '—');
  }

  function renderAvgFromPayload(payload) {
    const kb = payload?.metrics?.avg_tx_size_kb;
    const fee = payload?.metrics?.median_fee_per_action_zats
      || payload?.metrics?.mean_fee_per_action_zats
      || payload?.metrics?.avg_fee_per_action_zats;
    const entropy = payload?.metrics?.entropy_raw_bits;
    const totalTx = (payload?.blocks?.entries || []).reduce((sum, entry) => {
      const count = Number(entry.tx_count);
      return Number.isFinite(count) ? sum + count : sum;
    }, 0);
    const set = (id, val, fmt = (v) => v) => {
      const el = document.getElementById(id);
      if (!el) return;
      if (val == null || !Number.isFinite(val)) {
        el.textContent = '—';
      } else {
        el.textContent = fmt(val);
      }
    };
    set('avg-tx-size-kb', kb, (v) => v.toFixed(2));
    set('avg-fee-per-action', fee, (v) => (v / 100).toFixed(2)); // µZEC = zats / 100
    set('total-tx-count', totalTx, (v) => v.toLocaleString('en-US'));
    const usdSpan = document.getElementById('avg-fee-per-action-usd');
    if (usdSpan && Number.isFinite(fee) && Number.isFinite(window.latestPriceUsd)) {
      const usd = (fee / 1e8) * window.latestPriceUsd;
      usdSpan.textContent = `($${usd.toFixed(4)})`;
    } else if (usdSpan) {
      usdSpan.textContent = '';
    }
    set('fee-entropy-raw', entropy, (v) => v.toFixed(2));
  }

  function startPolling() {
    fetchSummary();
    state.timer = window.setInterval(fetchSummary, POLL_INTERVAL_MS);
  }

  bindFloorSelect();
  setFloorZats(els.floorSelect ? Number(els.floorSelect.value) : DEFAULT_FLOOR_ZATS);
  startPolling();
})();
