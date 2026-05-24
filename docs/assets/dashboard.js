/* Gold Breadth dashboard — fetches docs/data/*.json and renders Chart.js views.
 * Cache-bust every fetch so GitHub Pages CDN never serves stale JSON. */

const fmtMoney = n => n == null ? '—' : '$' + Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 });
const fmtInt   = n => n == null ? '—' : Number(n).toLocaleString();
const fmtPct   = n => n == null ? '—' : Number(n).toFixed(1) + '%';
const fmtSigned = n => n == null ? '—' : (n >= 0 ? '+' : '') + Number(n).toFixed(2);

function bust(url) {
  const sep = url.includes('?') ? '&' : '?';
  return url + sep + 'v=' + Date.now();
}

async function fetchJSON(url) {
  try {
    const r = await fetch(bust(url), { cache: 'no-store' });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) {
    return null;
  }
}

/* Select a useful window of strikes around ATM.
 * Returns up to ~18 strikes with the highest combined call+put OI within ±25% of spot. */
function selectStrikes(chain, spot) {
  if (!chain || !chain.length || !spot) return [];
  const inWindow = chain.filter(r =>
    r.strike >= spot * 0.75 && r.strike <= spot * 1.25 &&
    (r.call_oi + r.put_oi) > 0
  );
  if (!inWindow.length) return chain.slice(0, 18);
  // Score: combined OI + volume
  const scored = inWindow.map(r => ({
    ...r,
    _score: (r.call_oi || 0) + (r.put_oi || 0) + ((r.call_vol || 0) + (r.put_vol || 0)) * 2
  }));
  scored.sort((a, b) => b._score - a._score);
  const top = scored.slice(0, 18);
  top.sort((a, b) => a.strike - b.strike);
  return top;
}

function selectGEXStrikes(gexHeatmap, spot) {
  if (!gexHeatmap || !gexHeatmap.length || !spot) return [];
  const inWindow = gexHeatmap
    .filter(r => r.strike >= spot * 0.8 && r.strike <= spot * 1.2)
    .filter(r => Math.abs(r.net_gex || 0) > 0.0001);
  if (!inWindow.length) {
    return gexHeatmap.filter(r => Math.abs(r.net_gex || 0) > 0.0001).slice(0, 15);
  }
  // Pick top 15 by absolute net_gex magnitude
  const scored = [...inWindow].sort((a, b) => Math.abs(b.net_gex) - Math.abs(a.net_gex)).slice(0, 15);
  scored.sort((a, b) => a.strike - b.strike);
  return scored;
}

/* Chart.js defaults */
function configureCharts() {
  Chart.defaults.color = '#545f70';
  Chart.defaults.borderColor = '#1e2530';
  Chart.defaults.font.family = "'IBM Plex Mono', monospace";
  Chart.defaults.font.size = 10;
}

const GC = { color: 'rgba(30,37,48,0.8)', lineWidth: 0.5 };
const TT = { backgroundColor: '#0f1216', borderColor: '#252d3a', borderWidth: 1 };

/* ─── Renderers ─────────────────────────────────────────────────────── */

function renderBanner(latest) {
  const banner = document.getElementById('datasrc-banner');
  const txt = document.getElementById('banner-text');
  if (!latest) {
    banner.classList.add('stale');
    txt.textContent = '⚠ data/latest.json missing — scraper has not produced data yet';
    return;
  }
  const scrapedAt = latest.scraped_at ? new Date(latest.scraped_at) : null;
  const ageHrs = scrapedAt ? (Date.now() - scrapedAt.getTime()) / 3600000 : null;
  const stale = ageHrs == null || ageHrs > 24;
  banner.classList.toggle('stale', stale);
  const isoBkk = scrapedAt
    ? scrapedAt.toLocaleString('en-US', { timeZone: 'Asia/Bangkok', dateStyle: 'medium', timeStyle: 'short' })
    : 'unknown';
  const ageTxt = ageHrs == null ? 'unknown age'
    : ageHrs < 1 ? `${Math.round(ageHrs * 60)} min old`
    : ageHrs < 24 ? `${ageHrs.toFixed(1)} hr old`
    : `${(ageHrs / 24).toFixed(1)} days old (STALE)`;
  txt.textContent = `Scraped ${isoBkk} BKK · ${ageTxt} · Source: ${latest.data_source || 'Barchart'} · ${latest.symbol || ''}`;
}

function renderHeader(latest) {
  if (!latest) return;
  document.getElementById('hdr-symbol').textContent = latest.symbol || '—';
  const exp = latest.expiry || {};
  document.getElementById('hdr-dte').textContent = exp.dte ?? '—';
  document.getElementById('hdr-expiry').textContent = exp.label || '—';
  const now = new Date();
  document.getElementById('hdr-date').textContent = now.toLocaleDateString('en-US', { timeZone: 'Asia/Bangkok', year: 'numeric', month: 'short', day: '2-digit' });
  document.getElementById('hdr-time').textContent = now.toLocaleTimeString('en-US', { timeZone: 'Asia/Bangkok', hour: '2-digit', minute: '2-digit', hour12: false }) + ' Bangkok';
}

function renderKPIs(latest) {
  if (!latest) return;
  const spotEl = document.getElementById('kpi-spot');
  spotEl.textContent = fmtMoney(latest.spot);
  const chg = latest.future_chg;
  document.getElementById('kpi-chg').textContent = chg != null
    ? `${chg >= 0 ? '+' : ''}${chg.toFixed(2)} since prev close`
    : '— change unavailable';

  document.getElementById('kpi-oi').textContent = `${fmtInt(latest.total_call_oi)} | ${fmtInt(latest.total_put_oi)}`;
  document.getElementById('kpi-oi-sub').innerHTML = `<span class="c">Call ${fmtInt(latest.total_call_oi)}</span> / <span class="p">Put ${fmtInt(latest.total_put_oi)}</span>`;

  document.getElementById('kpi-vol').textContent = `${fmtInt(latest.total_call_vol)} | ${fmtInt(latest.total_put_vol)}`;
  document.getElementById('kpi-vol-sub').innerHTML = `<span class="c">Call ${fmtInt(latest.total_call_vol)}</span> / <span class="p">Put ${fmtInt(latest.total_put_vol)}</span>`;

  document.getElementById('kpi-iv').textContent = `${fmtPct(latest.iv_atm)} / ${fmtMoney(latest.max_pain)}`;
  document.getElementById('kpi-iv-sub').textContent = `ATM IV  |  Max Pain magnet`;

  const pcr = latest.pc_oi_ratio;
  const pcrLabel = pcr == null ? '—'
    : pcr > 1.1 ? 'Put-heavy'
    : pcr < 0.9 ? 'Call-heavy'
    : 'Balanced';
  document.getElementById('kpi-pcr').textContent = pcr != null ? pcr.toFixed(2) : '—';
  document.getElementById('kpi-pcr-sub').textContent = pcrLabel;
}

function renderStrip(latest) {
  if (!latest) return;
  const onesig = (latest.spot && latest.iv_atm)
    ? (latest.spot * (latest.iv_atm / 100) / Math.sqrt(252)).toFixed(2)
    : null;
  const bits = [
    `Spot: <strong style="color:var(--gold)">${fmtMoney(latest.spot)}</strong>`,
    `Max Pain: <strong style="color:var(--gold)">${fmtMoney(latest.max_pain)}</strong>`,
    `ATM IV: <strong>${fmtPct(latest.iv_atm)}</strong>`,
    `1σ daily: <strong>${onesig != null ? '$' + onesig : '—'}</strong>`,
    `P/C OI: <strong style="color:${latest.pc_oi_ratio > 1 ? 'var(--put)' : 'var(--call)'}">${latest.pc_oi_ratio != null ? latest.pc_oi_ratio.toFixed(2) : '—'}</strong>`,
  ];
  document.getElementById('strip-content').innerHTML = bits.join(' &nbsp; ');
}

function renderOIChart(latest, strikes) {
  if (!strikes.length) return;
  const labels = strikes.map(r => '$' + r.strike.toLocaleString());
  const callOI = strikes.map(r => r.call_oi || 0);
  const putOI = strikes.map(r => r.put_oi || 0);

  document.getElementById('oi-subtitle').textContent =
    `${strikes.length} strikes · ATM-centered window · ${latest.symbol || ''}`;

  document.getElementById('mp-line').innerHTML =
    `◆ Max Pain: <strong>${fmtMoney(latest.max_pain)}</strong>` +
    ` &nbsp;|&nbsp; Spot: <strong>${fmtMoney(latest.spot)}</strong>` +
    ` &nbsp;|&nbsp; Top Put Wall: <strong>${fmtMoney(strikes.slice().sort((a,b) => b.put_oi - a.put_oi)[0].strike)}</strong>` +
    ` &nbsp;|&nbsp; Top Call Wall: <strong>${fmtMoney(strikes.slice().sort((a,b) => b.call_oi - a.call_oi)[0].strike)}</strong>`;

  new Chart(document.getElementById('oiChart'), {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Put OI', data: putOI, backgroundColor: 'rgba(255,107,53,0.65)', borderColor: 'rgba(255,107,53,0.9)', borderWidth: 1 },
        { label: 'Call OI', data: callOI, backgroundColor: 'rgba(77,159,255,0.6)', borderColor: 'rgba(77,159,255,0.85)', borderWidth: 1 },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: 500 },
      plugins: { legend: { display: false }, tooltip: { ...TT, callbacks: { label: ctx => ' ' + ctx.dataset.label + ': ' + ctx.raw.toLocaleString() } } },
      scales: {
        x: { grid: GC, ticks: { maxRotation: 45, font: { size: 9 } } },
        y: { grid: GC, title: { display: true, text: 'OI (Contracts)', color: '#545f70', font: { size: 9 } }, ticks: { callback: v => v >= 1000 ? (v / 1000).toFixed(1) + 'K' : v } },
      }
    }
  });
}

function renderVolChart(latest, strikes) {
  if (!strikes.length) return;
  const labels = strikes.map(r => '$' + r.strike.toLocaleString());
  const callVol = strikes.map(r => r.call_vol || 0);
  const putVol = strikes.map(r => r.put_vol || 0);

  document.getElementById('vol-subtitle').textContent =
    `Total EOD vol — Call ${fmtInt(latest.total_call_vol)} / Put ${fmtInt(latest.total_put_vol)}`;

  new Chart(document.getElementById('volChart'), {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Put Volume', data: putVol, backgroundColor: 'rgba(255,107,53,0.7)', borderColor: 'rgba(255,107,53,1)', borderWidth: 1 },
        { label: 'Call Volume', data: callVol, backgroundColor: 'rgba(77,159,255,0.65)', borderColor: 'rgba(77,159,255,0.9)', borderWidth: 1 },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: 500 },
      plugins: { legend: { display: false }, tooltip: TT },
      scales: {
        x: { grid: GC, ticks: { maxRotation: 45, font: { size: 9 } } },
        y: { grid: GC, title: { display: true, text: 'Volume', color: '#545f70', font: { size: 9 } }, ticks: { callback: v => v >= 1000 ? (v / 1000).toFixed(1) + 'K' : v } },
      }
    }
  });
}

/* Bucket each chain strike's intraday volume into delta zones. */
function renderDeltaChart(latest) {
  const spot = latest.spot;
  const iv = (latest.iv_atm || 20) / 100;
  const dte = (latest.expiry && latest.expiry.dte) || 14;
  const sigma = spot * iv * Math.sqrt(dte / 365);

  // 11 buckets: P5,P15,P25,P35,P45,ATM,C45,C35,C25,C15,C5
  // Bucket bounds in z-score multiples (~ delta proxies)
  const buckets = [
    { key: 'P5Δ',   lo: -Infinity, hi: -2.0, label: `P5Δ<br/>≤ $${(spot - 2*sigma).toFixed(0)}` },
    { key: 'P15Δ',  lo: -2.0,      hi: -1.2, label: `P15Δ<br/>~ $${(spot - 1.5*sigma).toFixed(0)}` },
    { key: 'P25Δ',  lo: -1.2,      hi: -0.7, label: `P25Δ<br/>~ $${(spot - 0.9*sigma).toFixed(0)}` },
    { key: 'P35Δ',  lo: -0.7,      hi: -0.3, label: `P35Δ<br/>~ $${(spot - 0.5*sigma).toFixed(0)}` },
    { key: 'P45Δ',  lo: -0.3,      hi: -0.1, label: `P45Δ<br/>~ $${(spot - 0.2*sigma).toFixed(0)}` },
    { key: 'ATM',   lo: -0.1,      hi:  0.1, label: `ATM<br/>$${spot.toFixed(0)}` },
    { key: 'C45Δ',  lo:  0.1,      hi:  0.3, label: `C45Δ<br/>~ $${(spot + 0.2*sigma).toFixed(0)}` },
    { key: 'C35Δ',  lo:  0.3,      hi:  0.7, label: `C35Δ<br/>~ $${(spot + 0.5*sigma).toFixed(0)}` },
    { key: 'C25Δ',  lo:  0.7,      hi:  1.2, label: `C25Δ<br/>~ $${(spot + 0.9*sigma).toFixed(0)}` },
    { key: 'C15Δ',  lo:  1.2,      hi:  2.0, label: `C15Δ<br/>~ $${(spot + 1.5*sigma).toFixed(0)}` },
    { key: 'C5Δ',   lo:  2.0,      hi: Infinity, label: `C5Δ<br/>≥ $${(spot + 2*sigma).toFixed(0)}` },
  ];

  const putVols = buckets.map(() => 0);
  const callVols = buckets.map(() => 0);

  (latest.chain || []).forEach(row => {
    const z = (row.strike - spot) / sigma;
    const idx = buckets.findIndex(b => z >= b.lo && z < b.hi);
    if (idx < 0) return;
    putVols[idx] += row.put_vol || 0;
    callVols[idx] += row.call_vol || 0;
  });

  // Render the zone-color bar
  const cls = ['dp','mp','np','np','np','atm','nc','nc','nc','mc','dc'];
  document.getElementById('delta-zone-bar').innerHTML = buckets.map((b, i) =>
    `<div class="zh ${cls[i]}" style="flex:${i===5?0.8:1}">${b.label}</div>`
  ).join('');

  document.getElementById('delta-subtitle').textContent =
    `Spot $${spot.toFixed(2)} · ATM IV ${fmtPct(latest.iv_atm)} · DTE ${dte} · 1σ ≈ $${sigma.toFixed(0)}`;

  new Chart(document.getElementById('deltaChart'), {
    type: 'bar',
    data: {
      labels: buckets.map(b => b.key),
      datasets: [
        { label: 'Put Volume', data: putVols, backgroundColor: 'rgba(255,107,53,0.7)', borderColor: 'rgba(255,107,53,1)', borderWidth: 1 },
        { label: 'Call Volume', data: callVols, backgroundColor: 'rgba(77,159,255,0.65)', borderColor: 'rgba(77,159,255,0.9)', borderWidth: 1 },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: 500 },
      plugins: { legend: { display: false }, tooltip: TT },
      scales: {
        x: { grid: GC, ticks: { font: { size: 9 } } },
        y: { grid: GC, title: { display: true, text: 'Volume', color: '#545f70', font: { size: 9 } }, ticks: { callback: v => v >= 1000 ? (v / 1000).toFixed(1) + 'K' : v } },
      }
    }
  });
}

function renderGEXChart(latest) {
  const gexStrikes = selectGEXStrikes(latest.gex_heatmap, latest.spot);
  if (!gexStrikes.length) return;

  const labels = gexStrikes.map(r => '$' + r.strike.toLocaleString());
  const gex = gexStrikes.map(r => r.net_gex || 0);

  new Chart(document.getElementById('gexChart'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Net GEX',
        data: gex,
        backgroundColor: gex.map(v => v < 0 ? 'rgba(255,77,106,0.7)' : 'rgba(0,212,168,0.65)'),
        borderColor: gex.map(v => v < 0 ? 'rgba(255,77,106,1)' : 'rgba(0,212,168,1)'),
        borderWidth: 1
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: 500 },
      plugins: { legend: { display: false }, tooltip: { ...TT, callbacks: { label: ctx => ' GEX: ' + (ctx.raw > 0 ? '+' : '') + ctx.raw.toFixed(2) + (ctx.raw < 0 ? ' [Short Gamma]' : ' [Long Gamma]') } } },
      scales: {
        x: { grid: GC, ticks: { maxRotation: 45, font: { size: 9 } } },
        y: { grid: GC, title: { display: true, text: 'Net GEX', color: '#545f70', font: { size: 9 } }, ticks: { callback: v => (v > 0 ? '+' : '') + v.toFixed(1) } },
      }
    }
  });

  // Summary chips
  const totalGEX = gex.reduce((a, b) => a + b, 0);
  const negStrike = gexStrikes.reduce((a, b) => (b.net_gex || 0) < (a.net_gex || 0) ? b : a);
  const posStrike = gexStrikes.reduce((a, b) => (b.net_gex || 0) > (a.net_gex || 0) ? b : a);

  // Gamma flip: where cumulative net GEX crosses zero, scanning low->high
  let cum = 0, flip = null;
  for (const r of gexStrikes) {
    const prev = cum;
    cum += r.net_gex || 0;
    if (prev <= 0 && cum > 0) { flip = r.strike; break; }
    if (prev >= 0 && cum < 0) { flip = r.strike; break; }
  }

  document.getElementById('gex-summary').innerHTML = `
    <div class="gex-item"><div class="gex-lbl">Net GEX Sign</div><div class="gex-val ${totalGEX >= 0 ? 'pos' : ''}">${totalGEX >= 0 ? 'POSITIVE' : 'NEGATIVE'}</div></div>
    <div class="gex-item"><div class="gex-lbl">Sum (window)</div><div class="gex-val neu">${fmtSigned(totalGEX)}</div></div>
    <div class="gex-item"><div class="gex-lbl">Gamma Flip</div><div class="gex-val neu">${flip != null ? fmtMoney(flip) : '—'}</div></div>
    <div class="gex-item"><div class="gex-lbl">Max -GEX Strike</div><div class="gex-val">${fmtMoney(negStrike.strike)}</div></div>
    <div class="gex-item"><div class="gex-lbl">Max +GEX Strike</div><div class="gex-val pos">${fmtMoney(posStrike.strike)}</div></div>
    <div class="gex-item"><div class="gex-lbl">Dealer Behavior</div><div class="gex-val neu">${totalGEX < 0 ? 'Sell dips / chase trends' : 'Buy dips / fade extremes'}</div></div>
  `;
}

function renderZones(latest) {
  const chain = latest.chain || [];
  const topPut = [...chain].sort((a, b) => (b.put_oi || 0) - (a.put_oi || 0)).slice(0, 3);
  const topCall = [...chain].sort((a, b) => (b.call_oi || 0) - (a.call_oi || 0)).slice(0, 3);

  document.getElementById('zone-support').innerHTML =
    `Largest put OI concentration at <strong>${fmtMoney(topPut[0].strike)}</strong> (${fmtInt(topPut[0].put_oi)} contracts) — primary gamma absorption floor. ` +
    (topPut[1] ? `Secondary at <strong>${fmtMoney(topPut[1].strike)}</strong> (${fmtInt(topPut[1].put_oi)}) ` : '') +
    (topPut[2] ? `and <strong>${fmtMoney(topPut[2].strike)}</strong> (${fmtInt(topPut[2].put_oi)}). ` : '') +
    `<br><br>A sustained close below ${fmtMoney(topPut[0].strike)} would trigger a dealer delta-unwind cascade. Max pain ${fmtMoney(latest.max_pain)} acts as the gravitational magnet.`;
  document.getElementById('zone-support-primary').textContent =
    `${fmtMoney(topPut[0].strike)} → ${fmtMoney(topPut[1] ? topPut[1].strike : topPut[0].strike)}`;

  document.getElementById('zone-resistance').innerHTML =
    `Dominant call OI at <strong>${fmtMoney(topCall[0].strike)}</strong> (${fmtInt(topCall[0].call_oi)} contracts) — structural ceiling. ` +
    (topCall[1] ? `Secondary at <strong>${fmtMoney(topCall[1].strike)}</strong> (${fmtInt(topCall[1].call_oi)}) ` : '') +
    (topCall[2] ? `and <strong>${fmtMoney(topCall[2].strike)}</strong> (${fmtInt(topCall[2].call_oi)}). ` : '') +
    `<br><br>A high-volume break above ${fmtMoney(topCall[0].strike)} forces dealers into delta-buying, potentially accelerating the move toward ${fmtMoney(topCall[1] ? topCall[1].strike : topCall[0].strike)}.`;
  document.getElementById('zone-resistance-primary').textContent =
    `${fmtMoney(topCall[0].strike)} → ${fmtMoney(topCall[1] ? topCall[1].strike : topCall[0].strike)}`;
}

function renderStrikeMatrix(latest, strikes) {
  const tbody = document.getElementById('strike-tbody');
  tbody.innerHTML = '';
  const spot = latest.spot;
  const maxPain = latest.max_pain;
  const topPut = [...latest.chain].sort((a, b) => (b.put_oi || 0) - (a.put_oi || 0))[0];
  const topCall = [...latest.chain].sort((a, b) => (b.call_oi || 0) - (a.call_oi || 0))[0];

  // GEX lookup by strike
  const gexByStrike = {};
  (latest.gex_heatmap || []).forEach(r => { gexByStrike[r.strike] = r.net_gex; });

  strikes.forEach(r => {
    const isATM = Math.abs(r.strike - spot) < (spot * 0.015);
    const isMaxPain = r.strike === maxPain;
    const isTopPut = topPut && r.strike === topPut.strike;
    const isTopCall = topCall && r.strike === topCall.strike;

    let zone, badge;
    if (isATM) { zone = 'ATM — current spot level'; badge = '<span class="ib neu">ATM</span>'; }
    else if (isMaxPain) { zone = 'MAX PAIN — gravitational magnet'; badge = '<span class="ib bko">Max Pain</span>'; }
    else if (isTopCall) { zone = 'Primary call wall (resistance)'; badge = '<span class="ib sres">Call Wall</span>'; }
    else if (isTopPut) { zone = 'Primary put wall (support / GAX)'; badge = '<span class="ib ssup">Put Wall</span>'; }
    else if (r.strike > spot) { zone = 'Above spot · call-heavy zone'; badge = '<span class="ib secsup">Above ATM</span>'; }
    else { zone = 'Below spot · put-heavy zone'; badge = '<span class="ib secsup">Below ATM</span>'; }

    const gex = gexByStrike[r.strike];
    const totalVol = (r.call_vol || 0) + (r.put_vol || 0);
    const arrow = isATM ? '▶ ' : '';
    const cls = isATM ? 'atm-row' : '';

    tbody.insertAdjacentHTML('beforeend',
      `<tr class="${cls}">
        <td>${arrow}$${r.strike.toLocaleString()}</td>
        <td>${zone}</td>
        <td style="color:var(--call)">${fmtInt(r.call_oi)}</td>
        <td style="color:var(--put)">${fmtInt(r.put_oi)}</td>
        <td class="tvol">${fmtInt(totalVol)}</td>
        <td style="color:${gex == null ? 'var(--text3)' : gex < 0 ? 'var(--red)' : 'var(--green)'}">${gex != null ? fmtSigned(gex) : '—'}</td>
        <td>${badge}</td>
      </tr>`
    );
  });
}

/* ─── 5-day history ─────────────────────────────────────────────── */

function renderHistory(history) {
  if (!history || !history.days || !history.days.length) {
    document.getElementById('history-summary').textContent = 'Insufficient history — need at least 2 snapshots.';
    return;
  }
  const days = history.days;
  const last = days[days.length - 1];
  const first = days[0];

  document.getElementById('history-summary').textContent =
    `${days.length} sessions · ${first.date} → ${last.date}`;

  // Sparkline configs
  const sparkOpts = (color) => ({
    responsive: true, maintainAspectRatio: false,
    animation: { duration: 300 },
    plugins: { legend: { display: false }, tooltip: { ...TT, callbacks: { label: ctx => ' ' + ctx.parsed.y.toFixed(2) } } },
    scales: { x: { display: false, grid: { display: false } }, y: { display: false, grid: { display: false } } },
    elements: { line: { borderColor: color, borderWidth: 2, tension: 0.3 }, point: { radius: 2, backgroundColor: color } },
  });

  const mkSpark = (id, key, color, formatter) => {
    const series = days.map(d => d[key]);
    const labels = days.map(d => d.date);
    new Chart(document.getElementById(id), {
      type: 'line',
      data: { labels, datasets: [{ data: series, fill: false }] },
      options: sparkOpts(color),
    });
    const chg = series[0] != null && series[series.length - 1] != null
      ? series[series.length - 1] - series[0]
      : null;
    const chgEl = document.getElementById(id.replace('spark', 'spark').toLowerCase());
    return { last: series[series.length - 1], chg };
  };

  const spotResult = mkSpark('sparkSpot', 'spot', '#f5c842');
  const mpResult = mkSpark('sparkMP', 'max_pain', '#4d9fff');
  const pcrResult = mkSpark('sparkPCR', 'pc_oi_ratio', '#ff6b35');
  const ivResult = mkSpark('sparkIV', 'atm_iv', '#00d4a8');

  const writeSpark = (valId, chgId, fmtVal, result, fmtChg) => {
    document.getElementById(valId).textContent = fmtVal(result.last);
    const el = document.getElementById(chgId);
    if (result.chg == null) { el.textContent = '—'; return; }
    el.textContent = fmtChg(result.chg) + ' over window';
    el.classList.toggle('pos', result.chg > 0);
    el.classList.toggle('neg', result.chg < 0);
  };

  writeSpark('spark-spot-val', 'spark-spot-chg', fmtMoney, spotResult, v => (v >= 0 ? '+' : '') + '$' + v.toFixed(2));
  writeSpark('spark-mp-val', 'spark-mp-chg', fmtMoney, mpResult, v => (v >= 0 ? '+' : '') + '$' + v.toFixed(0));
  writeSpark('spark-pcr-val', 'spark-pcr-chg', v => v == null ? '—' : v.toFixed(2), pcrResult, v => (v >= 0 ? '+' : '') + v.toFixed(2));
  writeSpark('spark-iv-val', 'spark-iv-chg', fmtPct, ivResult, v => (v >= 0 ? '+' : '') + v.toFixed(2) + ' pp');

  // History table
  const rows = days.map(d => `
    <tr>
      <td>${d.date}</td>
      <td>${fmtMoney(d.spot)}</td>
      <td>${fmtMoney(d.max_pain)}</td>
      <td style="color:${d.gex_sign === 'positive' ? 'var(--green)' : 'var(--red)'}">${(d.gex_sign || '—').toUpperCase()}</td>
      <td>${fmtMoney(d.put_wall)}</td>
      <td>${fmtMoney(d.call_wall)}</td>
      <td>${d.pc_oi_ratio != null ? d.pc_oi_ratio.toFixed(2) : '—'}</td>
      <td>${fmtPct(d.atm_iv)}</td>
    </tr>
  `).join('');

  document.getElementById('history-table-wrap').innerHTML = `
    <table class="history-table">
      <thead><tr><th>Date</th><th>Spot</th><th>Max Pain</th><th>GEX</th><th>Put Wall</th><th>Call Wall</th><th>P/C OI</th><th>ATM IV</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

/* ─── AI narrative ──────────────────────────────────────────────── */

function renderAnalysis(analysis) {
  if (!analysis) return; // Leave placeholder content in place.
  const body = document.getElementById('analysis-body');
  body.innerHTML = '';
  document.getElementById('analysis-stamp').textContent =
    analysis.generated_at
      ? 'Generated ' + new Date(analysis.generated_at).toLocaleString('en-US', { timeZone: 'Asia/Bangkok', dateStyle: 'medium', timeStyle: 'short' }) + ' BKK'
      : 'Today\'s analysis';

  const sections = [];

  if (analysis.today_summary) {
    sections.push({ label: 'Today\'s Setup', html: `<p>${analysis.today_summary}</p>` });
  }
  if (analysis.five_day_thesis) {
    sections.push({ label: '5-Day Thesis', html: `<p>${analysis.five_day_thesis}</p>` });
  }
  if (analysis.what_changed && analysis.what_changed.length) {
    sections.push({
      label: 'What Changed (Last 5 Days)',
      html: '<ul>' + analysis.what_changed.map(s => `<li>${s}</li>`).join('') + '</ul>'
    });
  }
  if (analysis.prediction) {
    sections.push({ label: 'Prediction & Bias', html: `<p>${analysis.prediction}</p>` });
  }

  sections.forEach(s => {
    body.insertAdjacentHTML('beforeend',
      `<div class="aisec"><div class="ailbl">${s.label}</div><div class="aitxt">${s.html}</div></div>`
    );
  });

  // CTA block
  const cta = analysis.day_trade_cta;
  if (cta) {
    const ctaBody = document.getElementById('cta-body');
    ctaBody.innerHTML = `
      <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--gold);background:rgba(245,200,66,.06);border:1px solid rgba(245,200,66,.2);border-radius:2px;padding:10px 14px;margin-bottom:14px;">
        ⚡ STRUCTURE BIAS: ${cta.bias || '—'} · Entry ${cta.entry_zone || '—'} · Pivot ${cta.pivot || '—'}
      </div>
      <div class="ctagrid">
        <div class="ctac"><div class="ctact">Directional Bias</div><div class="ctav">${cta.bias || '—'}</div><div class="ctad">${cta.bias_note || ''}</div></div>
        <div class="ctac"><div class="ctact">Entry Zone</div><div class="ctav">${cta.entry_zone || '—'}</div><div class="ctad">${cta.entry_note || ''}</div></div>
        <div class="ctac"><div class="ctact">Key Pivot</div><div class="ctav">${cta.pivot || '—'}</div><div class="ctad">${cta.pivot_note || ''}</div></div>
        <div class="ctac"><div class="ctact">Stop Loss</div><div class="ctav" style="color:var(--red)">${cta.stop || '—'}</div><div class="ctad">${cta.stop_note || ''}</div></div>
        <div class="ctac"><div class="ctact">Targets</div><div class="ctav">${(cta.targets || []).join(' / ') || '—'}</div><div class="ctad">${cta.target_note || ''}</div></div>
        <div class="ctac"><div class="ctact">Risk</div><div class="ctav" style="color:var(--red)">${cta.risk_label || '—'}</div><div class="ctad">${cta.risk_note || ''}</div></div>
      </div>
    `;
  }
}

/* ─── Main ──────────────────────────────────────────────────────── */

(async () => {
  configureCharts();

  const [latest, history, analysis] = await Promise.all([
    fetchJSON('./data/latest.json'),
    fetchJSON('./data/history.json'),
    fetchJSON('./data/analysis.json'),
  ]);

  if (!latest) {
    renderBanner(null);
    return;
  }

  const strikes = selectStrikes(latest.chain, latest.spot);

  renderBanner(latest);
  renderHeader(latest);
  renderKPIs(latest);
  renderStrip(latest);
  try { renderOIChart(latest, strikes); } catch (e) { console.error('oi', e); }
  try { renderVolChart(latest, strikes); } catch (e) { console.error('vol', e); }
  try { renderDeltaChart(latest); } catch (e) { console.error('delta', e); }
  try { renderGEXChart(latest); } catch (e) { console.error('gex', e); }
  try { renderZones(latest); } catch (e) { console.error('zones', e); }
  try { renderStrikeMatrix(latest, strikes); } catch (e) { console.error('matrix', e); }
  try { renderHistory(history); } catch (e) { console.error('history', e); }
  try { renderAnalysis(analysis); } catch (e) { console.error('analysis', e); }
})();
