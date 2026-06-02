/**
 * Zcash Dynamic Fees — frontend polling and rendering.
 *
 * Fetches /api/fees every 10 seconds and updates the page.
 */

const POLL_INTERVAL = 10_000;
const ZATS_PER_ZEC = 100_000_000;

let priceUsd = 0;

// ---- Polling ----

async function fetchFees() {
  try {
    const res = await fetch("/api/fees", { cache: "no-cache" });
    if (!res.ok) throw new Error(res.statusText);
    const data = await res.json();
    renderHero(data);
    renderResponse(data);
  } catch {
    const text = document.getElementById("status-text");
    const dot = document.getElementById("status-dot");
    if (text) text.textContent = "Connection error";
    if (dot) dot.className = "status-dot red";
  }
}

async function fetchPrice() {
  try {
    const res = await fetch("/api/price", { cache: "no-cache" });
    if (!res.ok) return;
    const data = await res.json();
    priceUsd = data.usd_per_zec || 0;
  } catch {
    // non-critical
  }
}

// ---- Rendering ----

function renderHero(data) {
  const std = data.standard_fee;
  // New RPC contract (post-rename): priority_fee always present, congested flag separate.
  // Backward-compat: old contract used express_fee (Option<u64>, present only when congested).
  const priority = data.priority_fee ?? data.express_fee ?? (Number(std) * 10);
  const congested = data.congested ?? (data.express_fee != null && data.express_fee > 0);

  const standardFee = document.getElementById("standard-fee");
  if (!standardFee) return; // not on the portal page; nothing to render

  standardFee.textContent = Number(std).toLocaleString();
  document.getElementById("standard-usd").textContent = formatUsd(std);

  const priorityFee = document.getElementById("priority-fee");
  const priorityUsd = document.getElementById("priority-usd");
  if (priorityFee) priorityFee.textContent = Number(priority).toLocaleString();
  if (priorityUsd) priorityUsd.textContent = formatUsd(priority);

  // Status bar — informational. Card display is the same regardless.
  const dot = document.getElementById("status-dot");
  const text = document.getElementById("status-text");
  if (dot) dot.className = congested ? "status-dot red" : "status-dot green";
  if (text) text.textContent = congested ? "Network congested" : "Network uncongested";

  const blockHeight = document.getElementById("block-height");
  const estimatorVersion = document.getElementById("estimator-version");
  if (blockHeight) blockHeight.textContent = Number(data.height).toLocaleString();
  if (estimatorVersion) estimatorVersion.textContent = data.version || "--";
}

function renderResponse(data) {
  const el = document.getElementById("live-response");
  if (!el) return;
  el.textContent = JSON.stringify(data, null, 2);
}

function formatUsd(zats) {
  if (!priceUsd || !zats) return "";
  const usd = (zats / ZATS_PER_ZEC) * priceUsd;
  if (usd < 0.01) return `$${usd.toFixed(6)}`;
  return `$${usd.toFixed(4)}`;
}

// ---- Tabs ----

function initTabs() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      const target = document.getElementById("tab-" + btn.dataset.tab);
      if (target) target.classList.add("active");
    });
  });
}

// ---- Copy ----

function initCopy() {
  document.querySelectorAll(".copy-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = document.getElementById(btn.dataset.target);
      if (!el) return;
      navigator.clipboard.writeText(el.textContent).then(() => {
        const orig = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(() => { btn.textContent = orig; }, 1500);
      });
    });
  });
}

// ---- History chart ----

let _chartInstance = null;
const HISTORY_POLL_MS = 60_000;

async function renderChart() {
  const canvas = document.getElementById("fee-history-chart");
  const empty = document.getElementById("chart-empty");
  if (!canvas || typeof Chart === "undefined") return;
  let entries = [];
  try {
    const res = await fetch("/api/history?limit=1500", { cache: "no-cache" });
    if (res.ok) {
      const data = await res.json();
      entries = data.entries || [];
    }
  } catch {
    // ignore — chart stays empty
  }

  if (entries.length < 2) {
    canvas.style.display = "none";
    if (empty) empty.style.display = "block";
    return;
  }
  canvas.style.display = "block";
  if (empty) empty.style.display = "none";

  const labels = entries.map((e) => new Date(e.ts));
  const standardData = entries.map((e) => e.standard_fee);
  const priorityData = entries.map((e) => e.priority_fee);
  const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const accent = cssVar("--accent") || "#f4b728";
  const muted = cssVar("--text-muted") || "#6b7394";
  const border = cssVar("--border") || "#1e2a45";

  if (_chartInstance) {
    _chartInstance.data.labels = labels;
    _chartInstance.data.datasets[0].data = standardData;
    _chartInstance.data.datasets[1].data = priorityData;
    _chartInstance.update("none");
    return;
  }

  _chartInstance = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Standard",
          data: standardData,
          borderColor: accent,
          backgroundColor: "transparent",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.2,
        },
        {
          label: "Priority",
          data: priorityData,
          borderColor: muted,
          backgroundColor: "transparent",
          borderWidth: 1.5,
          borderDash: [4, 4],
          pointRadius: 0,
          tension: 0.2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: {
          type: "time",
          time: { unit: "hour", displayFormats: { hour: "HH:mm" } },
          grid: { color: border },
          ticks: { color: muted, font: { size: 11 } },
        },
        y: {
          type: "logarithmic",
          grid: { color: border },
          ticks: {
            color: muted,
            font: { size: 11 },
            callback: (v) => Number(v).toLocaleString(),
          },
          title: { display: true, text: "zats per action", color: muted, font: { size: 11 } },
        },
      },
      plugins: {
        legend: {
          position: "top",
          align: "end",
          labels: { color: muted, boxWidth: 12, font: { size: 12 } },
        },
        tooltip: {
          backgroundColor: "rgba(19, 26, 43, 0.95)",
          borderColor: border,
          borderWidth: 1,
          titleColor: "#e0e4ef",
          bodyColor: "#e0e4ef",
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${Number(ctx.parsed.y).toLocaleString()} zats`,
          },
        },
      },
    },
  });
}

// ---- Priority usage (Goal 1) ----

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function formatPct(v) {
  if (v == null) return "--";
  if (v > 0 && v < 0.1) return "<0.1%";
  return `${v.toFixed(v < 10 ? 1 : 0)}%`;
}

const STANDARD_LANE = 5000;
const PRIORITY_LANE = 20000;
let _txData = [];
let _txFilter = "all";

async function fetchUsage() {
  const split = document.getElementById("usage-split");
  if (!split) return;
  let data = null;
  try {
    const res = await fetch("/api/usage", { cache: "no-cache" });
    if (res.ok) data = await res.json();
  } catch {
    // leave placeholders; the bar stays empty
  }
  const total = Number(data && data.total_tx_count);
  if (!total) return; // no transactions in the window yet

  const std = Number(data.standard_count || 0);
  const pri = Number(data.priority_count || 0);
  const non = Number(data.nonstandard_count || 0);
  const pctOf = (n) => (n / total) * 100;

  _txData = data.transactions || []; // stash for the drill-down modal

  split.setAttribute("data-empty", "false");
  setWidth("seg-standard", pctOf(std));
  setWidth("seg-priority", pctOf(pri));
  setWidth("seg-nonstandard", pctOf(non));

  setText("pct-standard", `${std} (${formatPct(pctOf(std))})`);
  setText("pct-priority", `${pri} (${formatPct(pctOf(pri))})`);
  setText("pct-nonstandard", `${non} (${formatPct(pctOf(non))})`);
  setText("stat-total", total.toLocaleString());
}

function setWidth(id, pct) {
  const el = document.getElementById(id);
  if (el) el.style.width = `${pct}%`;
}

let _usageChart = null;

async function renderUsageChart() {
  const canvas = document.getElementById("usage-chart");
  const empty = document.getElementById("usage-empty");
  if (!canvas || typeof Chart === "undefined") return;
  let entries = [];
  try {
    const res = await fetch("/api/usage-history?limit=1500", { cache: "no-cache" });
    if (res.ok) entries = (await res.json()).entries || [];
  } catch {
    // ignore; chart stays empty
  }
  entries = entries.filter((e) => e.total_tx_count && e.nonstandard_count != null);
  if (entries.length < 2) {
    canvas.style.display = "none";
    if (empty) empty.style.display = "block";
    return;
  }
  canvas.style.display = "block";
  if (empty) empty.style.display = "none";

  const labels = entries.map((e) => new Date(e.ts));
  const shareOf = (key) => entries.map((e) => ((e[key] || 0) / e.total_tx_count) * 100);
  const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const accent = cssVar("--accent") || "#f4b728";
  const red = cssVar("--red") || "#f87171";
  const muted = cssVar("--text-muted") || "#6b7394";
  const border = cssVar("--border") || "#1e2a45";
  const bands = [
    ["Standard", shareOf("standard_count"), accent, "rgba(244, 183, 40, 0.18)"],
    ["Priority", shareOf("priority_count"), red, "rgba(248, 113, 113, 0.30)"],
    ["Nonstandard", shareOf("nonstandard_count"), muted, "rgba(107, 115, 148, 0.25)"],
  ];

  if (_usageChart) {
    _usageChart.data.labels = labels;
    bands.forEach((b, i) => {
      _usageChart.data.datasets[i].data = b[1];
    });
    _usageChart.update("none");
    return;
  }

  _usageChart = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: bands.map(([label, data, bc, bg]) => ({
        label,
        data,
        borderColor: bc,
        backgroundColor: bg,
        borderWidth: 1.5,
        pointRadius: 0,
        fill: true,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: {
          type: "time",
          time: { unit: "hour", displayFormats: { hour: "HH:mm" } },
          grid: { color: border },
          ticks: { color: muted, font: { size: 11 } },
        },
        y: {
          stacked: true,
          min: 0,
          max: 100,
          grid: { color: border },
          ticks: { color: muted, font: { size: 11 }, callback: (v) => `${v}%` },
          title: { display: true, text: "share of transactions", color: muted, font: { size: 11 } },
        },
      },
      plugins: {
        legend: { position: "top", align: "end", labels: { color: muted, boxWidth: 12, font: { size: 12 } } },
        tooltip: {
          backgroundColor: "rgba(19, 26, 43, 0.95)",
          borderColor: border,
          borderWidth: 1,
          titleColor: "#e0e4ef",
          bodyColor: "#e0e4ef",
          callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%` },
        },
      },
    },
  });
}

// ---- Drill-down modal ----

function tierOf(fpa) {
  if (fpa === PRIORITY_LANE) return "priority";
  if (fpa === STANDARD_LANE) return "standard";
  return "nonstandard";
}

function shortTxid(t) {
  return t && t.length > 18 ? `${t.slice(0, 8)}…${t.slice(-8)}` : t || "";
}

function renderTxTable() {
  const tbody = document.getElementById("tx-tbody");
  const empty = document.getElementById("tx-empty");
  if (!tbody) return;
  const rows = _txData.filter((t) => _txFilter === "all" || tierOf(t.fee_per_action) === _txFilter);
  tbody.innerHTML = "";
  if (!rows.length) {
    if (empty) empty.hidden = false;
    return;
  }
  if (empty) empty.hidden = true;
  const frag = document.createDocumentFragment();
  for (const t of rows) {
    const tier = tierOf(t.fee_per_action);
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td class="mono"><a href="https://cipherscan.app/tx/${t.txid}" target="_blank" rel="noopener">${shortTxid(t.txid)}</a></td>` +
      `<td class="mono num">${Number(t.fee_per_action).toLocaleString()}</td>` +
      `<td class="mono num">${t.actions}</td>` +
      `<td class="mono num">${Number(t.fee).toLocaleString()}</td>` +
      `<td><span class="tier tier-${tier}">${tier}</span></td>`;
    frag.appendChild(tr);
  }
  tbody.appendChild(frag);
}

async function openTxModal() {
  const modal = document.getElementById("tx-modal");
  if (!modal) return;
  modal.hidden = false;
  try {
    const res = await fetch("/api/usage", { cache: "no-cache" });
    if (res.ok) _txData = (await res.json()).transactions || [];
  } catch {
    // fall back to whatever fetchUsage stashed
  }
  const count = (tier) => _txData.filter((t) => tierOf(t.fee_per_action) === tier).length;
  setText("f-all", String(_txData.length));
  setText("f-standard", String(count("standard")));
  setText("f-priority", String(count("priority")));
  setText("f-nonstandard", String(count("nonstandard")));
  renderTxTable();
}

function initTxModal() {
  const btn = document.getElementById("drill-btn");
  const modal = document.getElementById("tx-modal");
  if (!btn || !modal) return;
  const close = () => {
    modal.hidden = true;
  };
  btn.addEventListener("click", openTxModal);
  const closeBtn = document.getElementById("tx-modal-close");
  if (closeBtn) closeBtn.addEventListener("click", close);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) close();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.hidden) close();
  });
  document.querySelectorAll(".filter-btn").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll(".filter-btn").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      _txFilter = b.dataset.tier;
      renderTxTable();
    });
  });
}

// ---- Mobile nav toggle ----

function initNavToggle() {
  const btn = document.querySelector(".nav-toggle");
  const nav = document.querySelector("header nav");
  if (!btn || !nav) return;
  btn.addEventListener("click", () => {
    const open = nav.classList.toggle("open");
    btn.setAttribute("aria-expanded", String(open));
  });
  document.addEventListener("click", (e) => {
    if (!nav.classList.contains("open")) return;
    const path = e.composedPath();
    if (path.includes(btn) || path.includes(nav)) return;
    nav.classList.remove("open");
    btn.setAttribute("aria-expanded", "false");
  });
}

// ---- Init ----

initTabs();
initCopy();
initNavToggle();
initTxModal();

// Polling only runs if the page has live data targets (portal hero or design RPC response).
const needsLiveData =
  document.getElementById("standard-fee") || document.getElementById("live-response");

if (needsLiveData) {
  fetchPrice();
  fetchFees();
  setInterval(fetchFees, POLL_INTERVAL);
  setInterval(fetchPrice, 300_000); // refresh price every 5 min
}

if (document.getElementById("fee-history-chart")) {
  renderChart();
  setInterval(renderChart, HISTORY_POLL_MS);
}

if (document.getElementById("usage-split")) {
  fetchUsage();
  setInterval(fetchUsage, POLL_INTERVAL);
}

if (document.getElementById("usage-chart")) {
  renderUsageChart();
  setInterval(renderUsageChart, HISTORY_POLL_MS);
}
