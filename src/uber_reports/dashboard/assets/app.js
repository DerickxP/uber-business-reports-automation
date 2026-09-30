/* Dashboard de corridas: filtros cruzados, gráficos SVG e tabelas, sem dependências externas.
 * Os dados chegam em window.DASHBOARD_DATA (lista de corridas já enriquecidas pelo ETL). */
(function () {
  "use strict";

  const MONTH_ORDER = { jan: 1, fev: 2, mar: 3, abr: 4, mai: 5, jun: 6, jul: 7, ago: 8, set: 9, out: 10, nov: 11, dez: 12 };
  const PERIODS = ["Madrugada", "Manhã", "Tarde", "Noite", "Sem hora"];
  const PERIOD_COLORS = { "Madrugada": "var(--p1)", "Manhã": "var(--p2)", "Tarde": "var(--p3)", "Noite": "var(--p4)", "Sem hora": "var(--p5)" };
  const FIELDS = ["cost_center", "store", "month", "period", "user", "request_hour"];
  const FIELD_LABELS = { cost_center: "centro de custo", store: "loja", month: "mês", period: "período", user: "usuário", request_hour: "hora" };
  const TOP_LIMIT = 30;
  const ROUTES_LIMIT = 100;
  const THEME_KEY = "uber-reports-theme";

  const DATA = Array.isArray(window.DASHBOARD_DATA) ? window.DASHBOARD_DATA : [];
  const SEL = {};
  FIELDS.forEach((field) => { SEL[field] = new Set(); });

  // ---- utilidades -----------------------------------------------------------
  const money = (v) => (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const integer = (v) => (v || 0).toLocaleString("pt-BR");
  const esc = (s) => String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const byId = (id) => document.getElementById(id);
  const attrs = (field, value) => `data-field="${esc(field)}" data-value="${esc(value)}"`;

  function valueOf(row, field) {
    const value = row[field];
    if (value === null || value === undefined || value === "") return "";
    return field === "request_hour" ? String(Number(value)) : String(value);
  }

  function sortValues(field, values) {
    if (field === "month") return [...values].sort((a, b) => (MONTH_ORDER[a] || 99) - (MONTH_ORDER[b] || 99));
    if (field === "period") return [...values].sort((a, b) => PERIODS.indexOf(a) - PERIODS.indexOf(b));
    if (field === "request_hour") return [...values].sort((a, b) => Number(a) - Number(b));
    return [...values].sort((a, b) => a.localeCompare(b, "pt-BR"));
  }

  // ---- filtro ---------------------------------------------------------------
  function matches(row, ignoreField) {
    for (const field of FIELDS) {
      if (field === ignoreField) continue;
      if (SEL[field].size && !SEL[field].has(valueOf(row, field))) return false;
    }
    return true;
  }
  const filtered = (ignoreField = null) => DATA.filter((row) => matches(row, ignoreField));

  function groupBy(rows, field, sumAmount) {
    const map = new Map();
    rows.forEach((row) => {
      const key = valueOf(row, field);
      map.set(key, (map.get(key) || 0) + (sumAmount ? Number(row.amount || 0) : 1));
    });
    return [...map.entries()].map(([label, value]) => ({ label, value }));
  }

  function toggleSel(field, value) {
    if (!SEL[field]) return;
    if (SEL[field].has(value)) SEL[field].delete(value); else SEL[field].add(value);
    refreshAll();
  }
  function clearAll() { FIELDS.forEach((field) => SEL[field].clear()); refreshAll(); }
  function refreshAll() { rebuildSidebar(); renderActiveStrip(); render(); }

  // ---- barra lateral --------------------------------------------------------
  function rebuildSidebar() {
    FIELDS.forEach((field) => {
      const listEl = byId("fl-" + field);
      const countEl = byId("cnt-" + field);
      if (!listEl || !countEl) return;

      const availableRows = filtered(field);
      const available = new Set(availableRows.map((row) => valueOf(row, field)));
      const allValues = sortValues(field, [...new Set(DATA.map((row) => valueOf(row, field)))].filter((v) => v));
      const counts = new Map();
      availableRows.forEach((row) => {
        const key = valueOf(row, field);
        counts.set(key, (counts.get(key) || 0) + 1);
      });

      listEl.innerHTML = allValues.map((value) => {
        const on = SEL[field].has(value);
        const off = !available.has(value) && !on;
        return `<div class="fi${on ? " on" : ""}${off ? " off" : ""}" ${attrs(field, value)}>
          <div class="fi-box"><svg class="fi-check" viewBox="0 0 10 10" fill="none"><path d="M1.5 5l2.5 2.5 4.5-4" stroke="#000" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
          <span class="fi-name" title="${esc(value)}">${esc(value)}</span>
          <span class="fi-n">${counts.get(value) || 0}</span>
        </div>`;
      }).join("");

      const selected = SEL[field].size;
      countEl.textContent = selected;
      countEl.className = "fg-cnt" + (selected ? " show" : "");
    });
  }

  function renderActiveStrip() {
    const strip = byId("af");
    const noneEl = byId("af-none");
    strip.querySelectorAll(".af-tag").forEach((tag) => tag.remove());
    let count = 0;
    FIELDS.forEach((field) => {
      SEL[field].forEach((value) => {
        count += 1;
        const tag = document.createElement("span");
        tag.className = "af-tag";
        const display = esc(value) + (field === "request_hour" ? "h" : "");
        tag.innerHTML = `<span class="af-field">${esc(FIELD_LABELS[field] || field)}</span> ${display}
          <button class="af-x" type="button" title="Remover" ${attrs(field, value)}>×</button>`;
        strip.appendChild(tag);
      });
    });
    noneEl.style.display = count ? "none" : "";
  }

  // ---- gráficos -------------------------------------------------------------
  function renderBars(elId, items, format, field, maxItems = 20) {
    const el = byId(elId);
    if (!items.length) { el.innerHTML = "<div class='empty'>Sem dados</div>"; return; }
    const list = items.slice(0, maxItems);
    const max = Math.max(...list.map((item) => item.value), 1);
    const hasSel = SEL[field] && SEL[field].size > 0;
    el.innerHTML = `<div class="blist">` + list.map((item) => {
      const on = SEL[field] && SEL[field].has(item.label);
      const dim = hasSel && !on;
      const pct = (item.value / max * 100).toFixed(1);
      const background = on ? "var(--accent)" : "var(--border2)";
      return `<div class="brow${on ? " hi" : ""}${dim ? " dim" : ""}" ${attrs(field, item.label)} title="Filtrar: ${esc(item.label)}">
        <div class="btrack">
          <div class="bfill" style="width:${pct}%;background:${background}"></div>
          <div class="blbl">${esc(item.label)}</div>
          <div class="bval">${format(item.value)}</div>
        </div>
      </div>`;
    }).join("") + `</div>`;
  }

  function renderLine(elId, items, format, field) {
    const el = byId(elId);
    if (!items.length) { el.innerHTML = "<div class='empty'>Sem dados</div>"; return; }
    if (items.length === 1) { renderBars(elId, items, format, field); return; }

    const W = 400, H = 116, pl = 6, pr = 6, pt = 8, pb = 30;
    const iW = W - pl - pr, iH = H - pt - pb;
    const values = items.map((item) => item.value);
    const minV = Math.min(...values), maxV = Math.max(...values, 1);
    const points = items.map((item, i) => ({
      x: pl + (i / (items.length - 1)) * iW,
      y: pt + iH - ((item.value - minV) / (maxV - minV || 1)) * iH,
      item,
    }));
    const linePath = points.map((p, i) => (i === 0 ? "M" : "L") + p.x.toFixed(1) + "," + p.y.toFixed(1)).join(" ");
    const areaPath = linePath + ` L${points[points.length - 1].x.toFixed(1)},${(pt + iH).toFixed(1)} L${pl},${(pt + iH).toFixed(1)} Z`;
    const circles = points.map((p) => {
      const on = SEL[field] && SEL[field].has(p.item.label);
      return `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${on ? 6 : 4}"
        fill="${on ? "var(--accent)" : "var(--bg2)"}" stroke="${on ? "var(--accent)" : "var(--border2)"}" stroke-width="1.5"
        ${attrs(field, p.item.label)}><title>${esc(p.item.label)}: ${format(p.item.value)}</title></circle>`;
    }).join("");
    const labels = points.map((p) => `<text x="${p.x.toFixed(1)}" y="${(H - 14).toFixed(1)}" text-anchor="middle"
      font-size="9" fill="var(--text2)" font-weight="500" font-family="'DM Mono',monospace">${esc(p.item.label)}</text>`).join("");
    el.innerHTML = `<svg class="spark" viewBox="0 0 ${W} ${H}">
      <defs><linearGradient id="g_${elId}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--accent)" stop-opacity=".15"/>
        <stop offset="100%" stop-color="var(--accent)" stop-opacity="0"/>
      </linearGradient></defs>
      <path d="${areaPath}" fill="url(#g_${elId})"/>
      <path d="${linePath}" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      ${circles}${labels}
    </svg>`;
  }

  function renderDonut(elId, items, field) {
    const el = byId(elId);
    if (!items.length) { el.innerHTML = "<div class='empty'>Sem dados</div>"; return; }
    const total = items.reduce((acc, item) => acc + item.value, 0) || 1;
    const R = 75, cx = 95, cy = 95, ri = 45;
    const hasSel = SEL[field] && SEL[field].size > 0;
    let paths = "";
    let offset = -90;
    items.forEach((item) => {
      const angle = item.value / total * 360;
      const start = offset, end = offset + angle;
      const x1 = cx + R * Math.cos(start * Math.PI / 180), y1 = cy + R * Math.sin(start * Math.PI / 180);
      const x2 = cx + R * Math.cos(end * Math.PI / 180), y2 = cy + R * Math.sin(end * Math.PI / 180);
      const large = angle > 180 ? 1 : 0;
      const color = PERIOD_COLORS[item.label] || "#555";
      const on = SEL[field] && SEL[field].has(item.label);
      const opacity = hasSel && !on ? 0.15 : 1;
      paths += `<path d="M${cx},${cy} L${x1.toFixed(2)},${y1.toFixed(2)} A${R},${R} 0 ${large},1 ${x2.toFixed(2)},${y2.toFixed(2)} Z"
        fill="${color}" stroke="var(--bg2)" stroke-width="${on ? 2.5 : 1}" opacity="${opacity}" ${attrs(field, item.label)}>
        <title>${esc(item.label)}: ${integer(item.value)}</title></path>`;
      offset += angle;
    });
    const legend = items.map((item) => {
      const on = SEL[field] && SEL[field].has(item.label);
      const dim = hasSel && !on;
      const pct = (item.value / total * 100).toFixed(1);
      return `<div class="dr${on ? " hi" : ""}${dim ? " dim" : ""}" ${attrs(field, item.label)}>
        <div class="dd" style="background:${PERIOD_COLORS[item.label] || "#555"}"></div>
        <span class="dn-lbl">${esc(item.label)}</span>
        <span class="dp">${pct}%&nbsp;(${integer(item.value)})</span>
      </div>`;
    }).join("");
    el.innerHTML = `<div class="dw">
      <svg class="donut" width="190" height="190" viewBox="0 0 190 190" style="flex-shrink:0">
        ${paths}
        <circle cx="${cx}" cy="${cy}" r="${ri}" fill="var(--bg2)"/>
        <text x="${cx}" y="${cy}" text-anchor="middle" dominant-baseline="central"
          font-size="15" font-weight="600" fill="var(--text2)" font-family="'DM Mono',monospace">${integer(total)}</text>
      </svg>
      <div class="dl">${legend}</div>
    </div>`;
  }

  function renderHeatmap(elId, rows) {
    const el = byId(elId);
    const field = "request_hour";
    const counts = Array.from({ length: 24 }, () => 0);
    rows.forEach((row) => {
      const hour = Number(row.request_hour);
      if (Number.isFinite(hour) && hour >= 0 && hour <= 23) counts[hour] += 1;
    });
    const max = Math.max(...counts, 1);
    const hasSel = SEL[field].size > 0;
    const cells = counts.map((count, hour) => {
      const on = SEL[field].has(String(hour));
      const dim = hasSel && !on;
      const alpha = (0.06 + count / max * 0.94).toFixed(2);
      return `<div class="hmc${on ? " on" : ""}${dim ? " dim" : ""}" style="opacity:${alpha}"
        title="${hour}h: ${count} corrida${count === 1 ? "" : "s"}. Clique para filtrar." ${attrs(field, String(hour))}></div>`;
    }).join("");
    const labels = counts.map((_, hour) => `<div class="hml${SEL[field].has(String(hour)) ? " on" : ""}">${hour}</div>`).join("");
    el.innerHTML = `<div class="hmg">${cells}</div><div class="hml-row">${labels}</div>`;
  }

  function renderTable(elId, headers, rows) {
    const el = byId(elId);
    if (!el) return;
    if (!rows || !rows.length) { el.innerHTML = "<div class='empty'>Sem dados</div>"; return; }
    const head = headers.map((h) => `<th>${esc(h)}</th>`).join("");
    const body = rows.map((cells) => `<tr>${cells.map((cell, i) =>
      `<td class="${i === 0 ? "muted" : i === cells.length - 1 ? "mono" : ""}">${esc(cell)}</td>`).join("")}</tr>`).join("");
    el.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }

  function renderRoutes(rows) {
    const el = byId("t_routes");
    if (!el) return;
    if (!rows.length) { el.innerHTML = "<div class='empty'>Nenhuma rota encontrada com os filtros selecionados.</div>"; return; }
    const routes = [...rows]
      .sort((a, b) => String(b.ride_date || "").localeCompare(String(a.ride_date || "")))
      .slice(0, ROUTES_LIMIT);
    const body = routes.map((row) => `<tr>
      <td class="muted mono nowrap">${esc(row.ride_date || "—")}</td>
      <td>${esc(row.user || "—")}</td>
      <td>${esc(row.store || "—")}</td>
      <td class="wrap-cell">${esc(row.pickup_address || "Não informado")}</td>
      <td class="wrap-cell">${esc(row.dropoff_address || "Não informado")}</td>
      <td class="mono nowrap">${money(Number(row.amount || 0))}</td>
    </tr>`).join("");
    el.innerHTML = `<table style="min-width:760px"><thead><tr>
      <th>Data</th><th>Usuário</th><th>Loja / setor</th><th>Partida</th><th>Destino</th><th>Valor</th>
    </tr></thead><tbody>${body}</tbody></table>`;
  }

  // ---- render principal -----------------------------------------------------
  function renderComparison(rows) {
    const byMonth = new Map();
    rows.forEach((row) => {
      const ym = String(row.ride_date || "").slice(0, 7);
      if (!/^\d{4}-\d{2}$/.test(ym)) return;
      if (!byMonth.has(ym)) byMonth.set(ym, { count: 0, amount: 0 });
      const acc = byMonth.get(ym);
      acc.count += 1;
      acc.amount += Number(row.amount || 0);
    });
    const months = [...byMonth.keys()].sort();
    const labelEl = byId("k_cmp_label");
    const deltaEl = byId("k_cmp_delta");
    if (months.length < 2) {
      labelEl.textContent = "—";
      deltaEl.textContent = "Dados insuficientes";
      deltaEl.className = "kpi-d neu";
      return;
    }
    const previous = byMonth.get(months[months.length - 2]);
    const current = byMonth.get(months[months.length - 1]);
    const pctCount = previous.count ? (current.count - previous.count) / previous.count * 100 : null;
    const pctAmount = previous.amount ? (current.amount - previous.amount) / previous.amount * 100 : null;
    const arrow = (v) => (v === null ? "N/A" : (v >= 0 ? "▲ " : "▼ ") + Math.abs(v).toFixed(1) + "%");
    labelEl.textContent = `${months[months.length - 2]} → ${months[months.length - 1]}`;
    deltaEl.innerHTML = `Qtd: ${arrow(pctCount)} &nbsp;|&nbsp; Valor: ${arrow(pctAmount)}`;
    deltaEl.className = "kpi-d " + (pctAmount > 0 ? "up" : pctAmount < 0 ? "dn" : "neu");
  }

  function render() {
    const rows = filtered();
    byId("no-data").style.display = rows.length ? "none" : "block";

    const total = rows.reduce((acc, row) => acc + Number(row.amount || 0), 0);
    const users = new Set(rows.map((row) => row.user)).size;
    byId("k_amount").textContent = money(total);
    byId("k_count").textContent = integer(rows.length);
    byId("k_ticket").textContent = money(rows.length ? total / rows.length : 0);
    byId("k_users").textContent = integer(users);
    renderComparison(rows);

    const byMonthOrder = (a, b) => (MONTH_ORDER[a.label] || 99) - (MONTH_ORDER[b.label] || 99);
    const amountByMonth = groupBy(rows, "month", true).sort(byMonthOrder);
    const countByMonth = groupBy(rows, "month", false).sort(byMonthOrder);
    const byStore = groupBy(rows, "store", true).sort((a, b) => b.value - a.value);
    const byPeriod = groupBy(rows, "period", false).sort((a, b) => PERIODS.indexOf(a.label) - PERIODS.indexOf(b.label));
    const byUser = groupBy(rows, "user", true).sort((a, b) => b.value - a.value);

    renderLine("c_amount_month", amountByMonth, money, "month");
    renderBars("c_count_month", countByMonth, integer, "month");
    renderDonut("c_period", byPeriod, "period");
    renderHeatmap("c_hour", rows);
    renderBars("c_store", byStore, money, "store", TOP_LIMIT);
    renderBars("c_user", byUser, money, "user", TOP_LIMIT);

    renderTable("t_monthly", ["Mês", "Corridas", "Valor"],
      amountByMonth.map((item) => [item.label, integer((countByMonth.find((c) => c.label === item.label) || {}).value || 0), money(item.value)]));
    renderTable("t_users", ["#", "Usuário", "Valor"],
      byUser.slice(0, TOP_LIMIT).map((item, index) => [index + 1, item.label, money(item.value)]));
    renderRoutes(rows);
  }

  // ---- tema e eventos -------------------------------------------------------
  function toggleTheme(save) {
    const isLight = document.body.classList.toggle("light-mode");
    if (!save) return;
    try { localStorage.setItem(THEME_KEY, isLight ? "light" : "dark"); } catch (_) { /* armazenamento indisponível */ }
  }

  document.addEventListener("click", (event) => {
    const target = event.target.closest ? event.target.closest("[data-field]") : null;
    if (!target) return;
    toggleSel(target.dataset.field, target.dataset.value);
  });
  byId("btn-clear").addEventListener("click", clearAll);
  byId("theme-toggle").addEventListener("click", () => toggleTheme(true));
  try { if (localStorage.getItem(THEME_KEY) === "light") toggleTheme(false); } catch (_) { /* ignora */ }

  refreshAll();
})();
