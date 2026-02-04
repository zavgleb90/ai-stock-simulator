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

  const chg = isFinite(last) && isFinite(prev) ? (last - prev) : (isFinite(r.change) ? Number(r.change) : null);
  const pctChg = (chg !== null && isFinite(prev) && prev !== 0) ? (chg / prev) * 100 : (isFinite(r.pct_change) ? Number(r.pct_change) : null);

  // history series (optional) — if provided by snapshot later
  const series = Array.isArray(r.series) ? r.series : (Array.isArray(r.history) ? r.history : null);

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

  // Determine series:
  // 1) if snapshot includes series/history array -> use it
  // 2) else fallback to flat line at last price
  let series = null;
  if (Array.isArray(priceRow.series) && priceRow.series.length) {
    series = priceRow.series.map(Number).filter(x => isFinite(x));
  }
  if (!series || series.length < 2) {
    const v = priceRow.last ?? 100;
    series = Array.from({length: 24}, () => Number(v));
  }

  const w = 600, h = 220, pad = 14;
  const min = Math.min(...series), max = Math.max(...series);
  const span = (max - min) || 1;

  const pts = series.map((v, i) => {
    const x = pad + (i * (w - 2*pad) / (series.length - 1));
    const y = pad + ((max - v) * (h - 2*pad) / span);
    return [x,y];
  });

  // Area
  const areaPath = [
    `M ${pts[0][0]} ${h-pad}`,
    `L ${pts[0][0]} ${pts[0][1]}`,
    ...pts.slice(1).map(p => `L ${p[0]} ${p[1]}`),
    `L ${pts[pts.length-1][0]} ${h-pad}`,
    "Z"
  ].join(" ");

  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", pts.map((p,i)=> (i===0?`M ${p[0]} ${p[1]}`:`L ${p[0]} ${p[1]}`)).join(" "));
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "rgba(93,214,255,.95)");
  path.setAttribute("stroke-width", "2.5");

  const area = document.createElementNS("http://www.w3.org/2000/svg", "path");
  area.setAttribute("d", areaPath);
  area.setAttribute("fill", "rgba(93,214,255,.12)");
  area.setAttribute("stroke", "none");

  svg.appendChild(area);
  svg.appendChild(path);

  // Last dot
  const last = pts[pts.length-1];
  const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  dot.setAttribute("cx", last[0]);
  dot.setAttribute("cy", last[1]);
  dot.setAttribute("r", "4");
  dot.setAttribute("fill", "rgba(93,214,255,.95)");
  svg.appendChild(dot);
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
