// site/app.js
const DATA = {
  latestPrices: "./data/latest_prices.json",
  latestNews: "./data/latest_news.json",
  leaderboard: "./data/leaderboard.json",
  // Optional: if you later add a history file, drop it here:
  // history: "./data/history.json"
};

const el = (id) => document.getElementById(id);

let state = {
  prices: [],
  news: [],
  leaderboard: [],
  sectors: new Set(),
  selected: null,
};

function fmtNum(x, digits = 2) {
  if (x === null || x === undefined || Number.isNaN(Number(x))) return "—";
  return Number(x).toFixed(digits);
}
function fmtInt(x) {
  if (x === null || x === undefined || Number.isNaN(Number(x))) return "—";
  return Math.round(Number(x)).toLocaleString();
}
function pct(a, b) {
  if (!isFinite(a) || !isFinite(b) || b === 0) return null;
  return (a / b) * 100.0;
}

async function fetchJson(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${url} -> HTTP ${r.status}`);
  return await r.json();
}

/**
 * Normalize snapshots into arrays of objects.
 * We accept:
 *  - array
 *  - {data: array}
 *  - {rows: array}
 *  - {items: array}
 */
function asArray(obj) {
  if (Array.isArray(obj)) return obj;
  if (obj && Array.isArray(obj.data)) return obj.data;
  if (obj && Array.isArray(obj.rows)) return obj.rows;
  if (obj && Array.isArray(obj.items)) return obj.items;
  return [];
}

function normalizePriceRow(r) {
  // Try to map various key names to a consistent row schema.
  const ticker = r.ticker ?? r.symbol ?? r.sym ?? r.Ticker ?? r.Symbol;
  const company = r.company_name ?? r.company ?? r.name ?? "";
  const sector = r.sector ?? r.Sector ?? "";
  const last = Number(r.close ?? r.last ?? r.price ?? r.Close ?? r.Last);
  const prev = Number(r.prev_close ?? r.previous_close ?? r.prev ?? r.PrevClose);
  const volume = Number(r.volume ?? r.vol ?? r.Volume);
  const ts = r.timestamp ?? r.time ?? r.bar_time ?? r.date ?? "";

  const last = Number(r.close ?? r.last ?? r.price ?? r.Close ?? r.Last);
  const prev = Number(r.prev_close ?? r.previous_close ?? r.prev ?? r.PrevClose);

  // Accept either snapshot naming: chg/chg_pct OR change/pct_change OR compute from prev_close
  const chgFromSnapshot =
    (r.chg !== undefined && r.chg !== null) ? Number(r.chg) :
    (r.change !== undefined && r.change !== null) ? Number(r.change) :
    null;

  const pctFromSnapshot =
    (r.chg_pct !== undefined && r.chg_pct !== null) ? Number(r.chg_pct) :
    (r.pct_change !== undefined && r.pct_change !== null) ? Number(r.pct_change) :
    null;

  const chg = (isFinite(last) && isFinite(prev)) ? (last - prev) :
              (isFinite(chgFromSnapshot)) ? chgFromSnapshot : null;

  const pctChg =
    (chg !== null && isFinite(prev) && prev !== 0) ? (chg / prev) * 100 :
    (isFinite(pctFromSnapshot)) ? (pctFromSnapshot * 100) : null; // if snapshot stores fraction

  // history series (optional) — if provided by snapshot later
  const series = Array.isArray(r.series) ? r.series : (Array.isArray(r.history) ? r.history : null);

  const seriesTs =
    (Array.isArray(r.series_ts) ? r.series_ts :
     Array.isArray(r.seriesTs) ? r.seriesTs :
     Array.isArray(r.history_ts) ? r.history_ts :
     Array.isArray(r.historyTs) ? r.historyTs :
     null);

  return {
    ticker,
    company,
    sector,
    last: isFinite(last) ? last : null,
    prev: isFinite(prev) ? prev : null,
    chg: (chg !== null && isFinite(chg)) ? chg : null,
    pctChg: (pctChg !== null && isFinite(pctChg)) ? pctChg : null,
    volume: isFinite(volume) ? volume : null,
    timestamp: ts,
    regime: r.regime ?? "",
    macro_headline: r.macro_headline ?? "",
    series,
    series_ts: seriesTs,
    raw: r,
  };
}

function normalizeNewsRow(n) {
  const ticker = n.ticker ?? n.symbol ?? "";
  const company = n.company_name ?? "";
  const headline = n.headline ?? n.title ?? "";
  const ts = n.timestamp ?? n.time ?? n.date ?? "";
  const eventType = n.event_type ?? n.type ?? "";
  const sentiment = n.sentiment ?? "";
  const regime = n.regime ?? "";
  return { ticker, company, headline, timestamp: ts, eventType, sentiment, regime, raw: n };
}

function normalizeLeaderRow(r) {
  return {
    team: r.team ?? r.Team ?? "",
    nav: Number(r.nav ?? r.NAV ?? r.value ?? r.Value),
    cash: Number(r.cash ?? r.Cash),
    realized_pnl: Number(r.realized_pnl ?? r.RealizedPnL ?? r.pnl ?? r.PnL),
  };
}

function fillSectorFilter() {
  const sel = el("sectorFilter");
  const current = sel.value;
  sel.innerHTML = `<option value="">All sectors</option>`;
  [...state.sectors].sort().forEach(s => {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = s;
    sel.appendChild(opt);
  });
  sel.value = current;
}

function renderWatchlist() {
  const tbody = el("watchlistTable").querySelector("tbody");
  const q = (el("searchInput").value || "").trim().toUpperCase();
  const sector = el("sectorFilter").value;

  const rows = state.prices
    .filter(r => r.ticker)
    .filter(r => !sector || r.sector === sector)
    .filter(r => {
      if (!q) return true;
      const hay = `${r.ticker} ${r.company}`.toUpperCase();
      return hay.includes(q);
    })
    .sort((a,b) => (a.ticker > b.ticker ? 1 : -1));

  tbody.innerHTML = "";
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="muted">No tickers found.</td></tr>`;
    return;
  }

  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.style.cursor = "pointer";
    tr.addEventListener("click", () => selectTicker(r.ticker));

    const chgClass = r.chg === null ? "" : (r.chg >= 0 ? "pos" : "neg");
    const pctStr = r.pctChg === null ? "—" : `${fmtNum(r.pctChg, 2)}%`;

    tr.innerHTML = `
      <td>
        <div class="ticker">${r.ticker}</div>
        <div class="small muted">${r.company || r.sector || ""}</div>
      </td>
      <td class="right">${r.last === null ? "—" : fmtNum(r.last, 2)}</td>
      <td class="right ${chgClass}">${r.chg === null ? "—" : fmtNum(r.chg, 2)}</td>
      <td class="right ${chgClass}">${pctStr}</td>
      <td class="right">${r.volume === null ? "—" : fmtInt(r.volume)}</td>
    `;
    tbody.appendChild(tr);
  }

  el("watchlistMeta").textContent = `${rows.length.toLocaleString()} tickers`;
}

function renderLeaderboard() {
  const tbody = el("leaderTable").querySelector("tbody");
  const rows = state.leaderboard
    .filter(r => r.team)
    .sort((a,b) => (b.nav - a.nav));

  tbody.innerHTML = "";
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="4" class="muted">No leaderboard data yet.</td></tr>`;
    return;
  }

  for (const r of rows) {
    const pnlClass = isFinite(r.realized_pnl) ? (r.realized_pnl >= 0 ? "pos" : "neg") : "";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="ticker">${r.team}</span></td>
      <td class="right">${isFinite(r.nav) ? fmtNum(r.nav, 2) : "—"}</td>
      <td class="right">${isFinite(r.cash) ? fmtNum(r.cash, 2) : "—"}</td>
      <td class="right ${pnlClass}">${isFinite(r.realized_pnl) ? fmtNum(r.realized_pnl, 2) : "—"}</td>
    `;
    tbody.appendChild(tr);
  }
}

function renderNews() {
  const box = el("newsList");
  const rows = state.news.slice(0, 50);

  box.innerHTML = "";
  if (!rows.length) {
    box.innerHTML = `<div class="muted">No news yet.</div>`;
    return;
  }

  for (const n of rows) {
    const title = n.company ? `${n.ticker} (${n.company})` : `${n.ticker}`;
    const item = document.createElement("div");
    item.className = "news-item";
    item.innerHTML = `
      <div class="news-head">
        <div class="news-title">${escapeHtml(title)}</div>
        <div class="news-meta">${escapeHtml(n.timestamp || "")}</div>
      </div>
      <div class="news-type">${escapeHtml(n.eventType || "")}${n.regime ? ` • ${escapeHtml(n.regime)}` : ""}</div>
      <div class="news-body">${escapeHtml(n.headline || "")}</div>
    `;
    item.addEventListener("click", () => {
      if (n.ticker) selectTicker(n.ticker);
    });
    box.appendChild(item);
  }
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#039;");
}

function selectTicker(ticker) {
  const r = state.prices.find(x => x.ticker === ticker);
  if (!r) return;

  state.selected = r;
  el("detailTitle").textContent = r.company ? `${r.ticker} (${r.company})` : r.ticker;

  const metaParts = [];
  if (r.timestamp) metaParts.push(r.timestamp);
  if (r.macro_headline) metaParts.push(`Macro: ${r.macro_headline}`);
  el("detailMeta").textContent = metaParts.length ? metaParts.join(" • ") : "—";

  el("chipSector").textContent = r.sector || "—";
  el("chipRegime").textContent = r.regime || "—";

  el("statLast").textContent = r.last === null ? "—" : fmtNum(r.last, 2);
  const chgClass = r.chg === null ? "" : (r.chg >= 0 ? "pos" : "neg");
  el("statChg").textContent = r.chg === null ? "—" : fmtNum(r.chg, 2);
  el("statChg").className = `value ${chgClass}`;
  el("statPct").textContent = r.pctChg === null ? "—" : `${fmtNum(r.pctChg, 2)}%`;
  el("statPct").className = `value ${chgClass}`;
  el("statVol").textContent = r.volume === null ? "—" : fmtInt(r.volume);

  drawSpark(r);
  prefillTradeForm(r.ticker);
}

function drawSpark(priceRow) {
  const svg = el("spark");
  svg.innerHTML = "";

  // 1) Determine series + timestamps (best-effort)
  let series = null;
  if (Array.isArray(priceRow.series) && priceRow.series.length) {
    series = priceRow.series.map(Number).filter(x => isFinite(x));
  }
  if (!series || series.length < 2) {
    const v = priceRow.last ?? 100;
    series = Array.from({ length: 24 }, () => Number(v));
  }

  let ts = null;
  if (Array.isArray(priceRow.series_ts) && priceRow.series_ts.length) {
    ts = priceRow.series_ts.map(String);
    // If timestamps mismatch length, ignore
    if (ts.length !== series.length) ts = null;
  }

  const w = 600, h = 220, pad = 14;
  const min = Math.min(...series), max = Math.max(...series);
  const span = (max - min) || 1;

  const n = series.length;
  const pts = series.map((v, i) => {
    const x = pad + (i * (w - 2 * pad) / (n - 1));
    const y = pad + ((max - v) * (h - 2 * pad) / span);
    return [x, y];
  });

  // Helpers
  const NS = "http://www.w3.org/2000/svg";
  const make = (tag) => document.createElementNS(NS, tag);

  function addText(x, y, text, anchor = "start", opacity = 0.75, size = 12) {
    const t = make("text");
    t.setAttribute("x", String(x));
    t.setAttribute("y", String(y));
    t.setAttribute("fill", `rgba(231,236,255,${opacity})`);
    t.setAttribute("font-size", String(size));
    t.setAttribute("font-family", "ui-sans-serif, system-ui, Segoe UI, Roboto, Arial");
    t.setAttribute("text-anchor", anchor);
    t.textContent = text;
    svg.appendChild(t);
    return t;
  }

  function fmtTime(s) {
    // Try to show readable time: "YYYY-MM-DD HH:MM"
    // Works for "2026-02-09 14:00:00" or ISO.
    if (!s) return "";
    const ss = String(s);
    if (ss.length >= 16) return ss.slice(0, 16);
    return ss;
  }

  // 2) Plot line + area
  const areaPath = [
    `M ${pts[0][0]} ${h - pad}`,
    `L ${pts[0][0]} ${pts[0][1]}`,
    ...pts.slice(1).map(p => `L ${p[0]} ${p[1]}`),
    `L ${pts[n - 1][0]} ${h - pad}`,
    "Z"
  ].join(" ");

  const area = make("path");
  area.setAttribute("d", areaPath);
  area.setAttribute("fill", "rgba(93,214,255,.12)");
  area.setAttribute("stroke", "none");
  svg.appendChild(area);

  const path = make("path");
  path.setAttribute("d", pts.map((p, i) => (i === 0 ? `M ${p[0]} ${p[1]}` : `L ${p[0]} ${p[1]}`)).join(" "));
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "rgba(93,214,255,.95)");
  path.setAttribute("stroke-width", "2.5");
  svg.appendChild(path);

  // Last dot (static)
  const lastPt = pts[n - 1];
  const lastDot = make("circle");
  lastDot.setAttribute("cx", lastPt[0]);
  lastDot.setAttribute("cy", lastPt[1]);
  lastDot.setAttribute("r", "4");
  lastDot.setAttribute("fill", "rgba(93,214,255,.95)");
  svg.appendChild(lastDot);

  // 3) Value labels (min/max/last)
  addText(pad, pad + 12, `max ${max.toFixed(2)}`, "start", 0.7, 12);
  addText(pad, h - pad - 4, `min ${min.toFixed(2)}`, "start", 0.7, 12);
  addText(w - pad, pad + 12, `last ${series[n - 1].toFixed(2)}`, "end", 0.7, 12);

  // 4) Time labels (start / mid / end)
  const yAxis = h - 6;
  if (ts && ts.length === n) {
    const i0 = 0;
    const im = Math.floor((n - 1) / 2);
    const i1 = n - 1;

    addText(pad, yAxis, fmtTime(ts[i0]), "start", 0.55, 11);
    addText(w / 2, yAxis, fmtTime(ts[im]), "middle", 0.55, 11);
    addText(w - pad, yAxis, fmtTime(ts[i1]), "end", 0.55, 11);
  } else {
    addText(pad, yAxis, "start", "start", 0.55, 11);
    addText(w - pad, yAxis, "end", "end", 0.55, 11);
  }

  // 5) Hover crosshair + tooltip (SVG overlay)
  const cross = make("line");
  cross.setAttribute("x1", "0");
  cross.setAttribute("y1", String(pad));
  cross.setAttribute("x2", "0");
  cross.setAttribute("y2", String(h - pad));
  cross.setAttribute("stroke", "rgba(231,236,255,.35)");
  cross.setAttribute("stroke-width", "1");
  cross.setAttribute("visibility", "hidden");
  svg.appendChild(cross);

  const hoverDot = make("circle");
  hoverDot.setAttribute("cx", "0");
  hoverDot.setAttribute("cy", "0");
  hoverDot.setAttribute("r", "4");
  hoverDot.setAttribute("fill", "rgba(231,236,255,.95)");
  hoverDot.setAttribute("visibility", "hidden");
  svg.appendChild(hoverDot);

  const tipG = make("g");
  tipG.setAttribute("visibility", "hidden");

  const tipBg = make("rect");
  tipBg.setAttribute("rx", "8");
  tipBg.setAttribute("ry", "8");
  tipBg.setAttribute("fill", "rgba(0,0,0,.65)");
  tipBg.setAttribute("stroke", "rgba(255,255,255,.12)");
  tipBg.setAttribute("stroke-width", "1");
  tipG.appendChild(tipBg);

  const tipT1 = make("text");
  tipT1.setAttribute("fill", "rgba(231,236,255,.95)");
  tipT1.setAttribute("font-size", "12");
  tipT1.setAttribute("font-family", "ui-sans-serif, system-ui, Segoe UI, Roboto, Arial");
  tipT1.textContent = "";
  tipG.appendChild(tipT1);

  const tipT2 = make("text");
  tipT2.setAttribute("fill", "rgba(231,236,255,.80)");
  tipT2.setAttribute("font-size", "12");
  tipT2.setAttribute("font-family", "ui-sans-serif, system-ui, Segoe UI, Roboto, Arial");
  tipT2.textContent = "";
  tipG.appendChild(tipT2);

  svg.appendChild(tipG);

  function showAtIndex(i) {
    i = Math.max(0, Math.min(n - 1, i));
    const [x, y] = pts[i];
    const v = series[i];
    const t = ts ? fmtTime(ts[i]) : `bar ${i + 1}/${n}`;

    cross.setAttribute("x1", String(x));
    cross.setAttribute("x2", String(x));
    cross.setAttribute("visibility", "visible");

    hoverDot.setAttribute("cx", String(x));
    hoverDot.setAttribute("cy", String(y));
    hoverDot.setAttribute("visibility", "visible");

    tipT1.textContent = `${v.toFixed(2)}`;
    tipT2.textContent = `${t}`;

    // Position tooltip near the point, with bounds checks
    const padding = 8;
    const boxW = 160;
    const boxH = 48;

    let tx = x + 10;
    let ty = y - boxH - 10;

    if (tx + boxW > w - pad) tx = x - boxW - 10;
    if (ty < pad) ty = y + 10;

    tipBg.setAttribute("x", String(tx));
    tipBg.setAttribute("y", String(ty));
    tipBg.setAttribute("width", String(boxW));
    tipBg.setAttribute("height", String(boxH));

    tipT1.setAttribute("x", String(tx + padding));
    tipT1.setAttribute("y", String(ty + 18));

    tipT2.setAttribute("x", String(tx + padding));
    tipT2.setAttribute("y", String(ty + 36));

    tipG.setAttribute("visibility", "visible");
  }

  function hideHover() {
    cross.setAttribute("visibility", "hidden");
    hoverDot.setAttribute("visibility", "hidden");
    tipG.setAttribute("visibility", "hidden");
  }

  function clientToSvgX(evt) {
    const rect = svg.getBoundingClientRect();
    const clientX = evt.touches ? evt.touches[0].clientX : evt.clientX;
    const x = ((clientX - rect.left) / rect.width) * w;
    return x;
  }

  svg.addEventListener("mousemove", (evt) => {
    const x = clientToSvgX(evt);
    const i = Math.round(((x - pad) / (w - 2 * pad)) * (n - 1));
    showAtIndex(i);
  });

  svg.addEventListener("mouseleave", hideHover);

  // Touch support
  svg.addEventListener("touchstart", (evt) => {
    evt.preventDefault();
    const x = clientToSvgX(evt);
    const i = Math.round(((x - pad) / (w - 2 * pad)) * (n - 1));
    showAtIndex(i);
  }, { passive: false });

  svg.addEventListener("touchmove", (evt) => {
    evt.preventDefault();
    const x = clientToSvgX(evt);
    const i = Math.round(((x - pad) / (w - 2 * pad)) * (n - 1));
    showAtIndex(i);
  }, { passive: false });

  svg.addEventListener("touchend", hideHover);
}

function prefillTradeForm(ticker) {
  el("fTicker").value = ticker || "";
}

function openTradeModal() {
  el("modalBackdrop").hidden = false;
  el("tradeModal").hidden = false;
}
function closeTradeModal() {
  el("modalBackdrop").hidden = true;
  el("tradeModal").hidden = true;
}

function issueBodyFromForm() {
  const team = (el("fTeam").value || "").trim() || "team1";
  const side = el("fSide").value;
  const ticker = (el("fTicker").value || "").trim().toUpperCase();
  const qty = Number(el("fQty").value || 0);
  const type = el("fType").value;
  const limit = (el("fLimit").value || "").trim();
  const notes = (el("fNotes").value || "").trim();

  const lines = [
    `team: ${team}`,
    `side: ${side}`,
    `ticker: ${ticker}`,
    `qty: ${qty}`,
    `order_type: ${type}`,
  ];
  if (type === "LIMIT" && limit) lines.push(`limit_price: ${limit}`);
  if (notes) lines.push(`notes: ${notes}`);
  return lines.join("\n");
}

/**
 * Open GitHub new issue page with prefilled title/body and label.
 * This uses a classic issue template approach (markdown templates support prefill).
 * Issue FORMS (YAML) cannot be reliably prefilled by URL.
 */
function openIssuePrefilled() {
  const body = issueBodyFromForm();
  const ticker = (el("fTicker").value || "").trim().toUpperCase();
  const side = el("fSide").value;
  const qty = el("fQty").value;

  // Derive repo base from current Pages URL:
  // https://USERNAME.github.io/REPO/ -> repo = REPO
  const parts = window.location.pathname.split("/").filter(Boolean);
  const repo = parts.length ? parts[0] : "ai-stock-simulator";
  const owner = window.location.hostname.split(".")[0];

  const title = encodeURIComponent(`Order: ${side} ${qty} ${ticker}`);
  const bodyEnc = encodeURIComponent(body);

  // We point to a markdown template "order.md" you will add in .github/ISSUE_TEMPLATE/order.md
  const url =
    `https://github.com/${owner}/${repo}/issues/new?labels=order&template=order.md&title=${title}&body=${bodyEnc}`;

  window.open(url, "_blank");
}

async function copyIssueBody() {
  const body = issueBodyFromForm();
  await navigator.clipboard.writeText(body);
  alert("Copied order body to clipboard. Paste it into the GitHub Issue if needed.");
}

async function refresh() {
  try {
    const [pRaw, nRaw, lRaw] = await Promise.all([
      fetchJson(DATA.latestPrices).catch(() => ({})),
      fetchJson(DATA.latestNews).catch(() => ({})),
      fetchJson(DATA.leaderboard).catch(() => ({})),
    ]);

    const pArr = asArray(pRaw).map(normalizePriceRow).filter(r => r.ticker);
    const nArr = asArray(nRaw).map(normalizeNewsRow);
    const lArr = asArray(lRaw).map(normalizeLeaderRow);

    // Newest news first if timestamps exist (string compare works for ISO)
    nArr.sort((a,b) => String(b.timestamp).localeCompare(String(a.timestamp)));

    state.prices = pArr;
    state.news = nArr;
    state.leaderboard = lArr;
    state.sectors = new Set(pArr.map(r => r.sector).filter(Boolean));

    fillSectorFilter();
    renderWatchlist();
    renderNews();
    renderLeaderboard();

    // Subtitle (market time)
    const any = pArr[0];
    const ts = any?.timestamp || any?.raw?.timestamp || "";
    el("subtitle").textContent = ts ? `Latest bar: ${ts}` : "Latest bar: (not available yet)";

    // Auto-select first ticker if none
    if (!state.selected && pArr.length) selectTicker(pArr[0].ticker);
    // Keep selection if still exists
    if (state.selected) {
      const still = pArr.find(x => x.ticker === state.selected.ticker);
      if (still) selectTicker(still.ticker);
    }
  } catch (e) {
    el("subtitle").textContent = `Error loading snapshots: ${e.message}`;
    el("watchlistTable").querySelector("tbody").innerHTML =
      `<tr><td colspan="5" class="muted">No snapshot files found yet. Run one exchange tick.</td></tr>`;
    el("newsList").innerHTML = `<div class="muted">No news snapshot yet.</div>`;
    el("leaderTable").querySelector("tbody").innerHTML =
      `<tr><td colspan="4" class="muted">No leaderboard snapshot yet.</td></tr>`;
  }
}

function wireUI() {
  el("refreshBtn").addEventListener("click", refresh);
  el("searchInput").addEventListener("input", renderWatchlist);
  el("sectorFilter").addEventListener("change", renderWatchlist);

  el("tradeBtn").addEventListener("click", openTradeModal);
  el("modalBackdrop").addEventListener("click", closeTradeModal);
  el("closeModalBtn").addEventListener("click", closeTradeModal);

  el("openIssueBtn").addEventListener("click", openIssuePrefilled);
  el("copyBodyBtn").addEventListener("click", copyIssueBody);
}

wireUI();
refresh();
