(function () {
  const els = {
    health: document.getElementById("healthStatus"),
    snapdirVal: document.getElementById("snapdirVal"),
    device: document.getElementById("deviceSelect"),
    table: document.getElementById("tableSelect"),
    vrf: document.getElementById("vrfSelect"),
    afi: document.getElementById("afiSelect"),
    refresh: document.getElementById("refreshBtn"),
    tabs: document.querySelectorAll(".tab"),
    panels: document.querySelectorAll(".tab-panel"),
    latestFilter: document.getElementById("latestFilter"),
    latestSummary: document.getElementById("latestSummary"),
    latestTable: document.getElementById("latestTable"),
    diffList: document.getElementById("diffList"),
    diffDetails: document.getElementById("diffDetails"),
    historyList: document.getElementById("historyList"),
    historyDetails: document.getElementById("historyDetails"),
  };

  const state = {
    devices: [],
    deviceTables: null, // { rib: [[vrf,afi],...], bgp: [[vrf,afi],...] }
    latestData: [],
  };

  // Utils
  function formatTs(ts) {
    // ts = YYYYMMDDHHMMSS (UTC)
    if (!/^\d{14}$/.test(ts || "")) return ts || "";
    const y = ts.slice(0, 4);
    const m = ts.slice(4, 6);
    const d = ts.slice(6, 8);
    const hh = ts.slice(8, 10);
    const mm = ts.slice(10, 12);
    const ss = ts.slice(12, 14);
    return `${y}-${m}-${d} ${hh}:${mm}:${ss}Z`;
  }

  async function api(path) {
    const res = await fetch(path, { headers: { "Accept": "application/json" } });
    if (!res.ok) {
      let msg = `${res.status} ${res.statusText}`;
      try {
        const j = await res.json();
        if (j && j.detail) msg += ` - ${j.detail}`;
      } catch (_) {}
      throw new Error(msg);
    }
    // some endpoints return arrays
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      return res.json();
    }
    return res.text();
  }

  function setHealth(status, snapdir, count) {
    els.health.textContent = status === "ok" ? `Healthy - ${count} device(s)` : "Unhealthy";
    els.health.classList.remove("ok", "warn");
    els.health.classList.add(status === "ok" ? "ok" : "warn");
    els.snapdirVal.textContent = snapdir || "-";
  }

  function setOptions(select, values, keepIfPossible = true) {
    const prev = keepIfPossible ? select.value : null;
    select.innerHTML = "";
    for (const v of values) {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      select.appendChild(opt);
    }
    if (keepIfPossible && prev && values.includes(prev)) {
      select.value = prev;
    }
  }

  function uniq(arr) {
    return Array.from(new Set(arr));
  }

  function combosFor(tableKind) {
    const combos = (state.deviceTables && state.deviceTables[tableKind]) || [];
    // state.deviceTables[tableKind] is list of tuples but came through JSON -> arrays
    return combos.map((t) => Array.isArray(t) ? t : [t[0], t[1]]);
  }

  function updateVrfAfiOptions() {
    const t = els.table.value;
    const combos = combosFor(t);
    const vrfs = uniq(combos.map((c) => c[0])).sort();
    setOptions(els.vrf, vrfs);

    const selectedVrf = els.vrf.value;
    const afis = uniq(combos.filter((c) => c[0] === selectedVrf).map((c) => c[1])).sort();
    setOptions(els.afi, afis);
  }

  // Renderers
  function summarizeLatest(tableKind, rows) {
    const parts = [];
    parts.push(chip(`Rows: ${rows.length}`));
    parts.push(chip(`Table: ${tableKind.toUpperCase()}`));
    parts.push(chip(`Device: ${els.device.value}`));
    parts.push(chip(`VRF: ${els.vrf.value}`));
    parts.push(chip(`AFI: ${els.afi.value}`));
    els.latestSummary.innerHTML = parts.join(" ");
  }

  function chip(text) {
    return `<span class="chip">${escapeHtml(text)}</span>`;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (m) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    }[m]));
  }

  function renderTableRIB(rows) {
    const headers = ["prefix", "protocol", "distance", "metric", "best", "nexthops"];
    const thead = `<thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>`;
    const tbody = `<tbody>${rows.map((r) => {
      const nhs = (r.nexthops || []).map((n) => `${n.nh}${n.iface ? "@" + n.iface : ""}`).join(", ");
      return `<tr>
        <td><code>${escapeHtml(r.prefix)}</code></td>
        <td>${escapeHtml(r.protocol || "")}</td>
        <td>${r.distance ?? ""}</td>
        <td>${r.metric ?? ""}</td>
        <td>${r.best ? "true" : "false"}</td>
        <td><code>${escapeHtml(nhs)}</code></td>
      </tr>`;
    }).join("")}</tbody>`;
    els.latestTable.innerHTML = `<div class="table-wrap"><table>${thead}${tbody}</table></div>`;
  }

  function renderTableBGP(rows) {
    const headers = ["prefix", "best", "nh", "as_path", "local_pref", "med", "origin", "peer"];
    const thead = `<thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>`;
    const tbody = `<tbody>${rows.map((r) => {
      return `<tr>
        <td><code>${escapeHtml(r.prefix)}</code></td>
        <td>${r.best ? "true" : "false"}</td>
        <td><code>${escapeHtml(r.nh ?? "")}</code></td>
        <td><code>${escapeHtml(r.as_path ?? "")}</code></td>
        <td>${r.local_pref ?? ""}</td>
        <td>${r.med ?? ""}</td>
        <td>${escapeHtml(r.origin ?? "")}</td>
        <td><code>${escapeHtml(r.peer ?? "")}</code></td>
      </tr>`;
    }).join("")}</tbody>`;
    els.latestTable.innerHTML = `<div class="table-wrap"><table>${thead}${tbody}</table></div>`;
  }

  function filterRows(rows, q) {
    if (!q) return rows;
    const s = q.toLowerCase();
    return rows.filter((r) => JSON.stringify(r).toLowerCase().includes(s));
  }

  // Diffs rendering
  function renderDiffList(items) {
    if (!items.length) {
      els.diffList.innerHTML = `<div class="list"><div class="row"><span class="meta">No diffs found</span></div></div>`;
      return;
    }
    const rows = items.map((e) => {
      const title = `${e.vrf}.${e.afi}.${formatTs(e.ts)}`;
      const size = (e.size || 0);
      return `<div class="row" data-ts="${e.ts}">
        <div class="title">${escapeHtml(title)}</div>
        <div class="meta">${size} B</div>
      </div>`;
    }).join("");
    els.diffList.innerHTML = `<div class="list">${rows}</div>`;
    els.diffList.querySelectorAll(".row").forEach((row) => {
      row.addEventListener("click", async () => {
        const ts = row.getAttribute("data-ts");
        await loadDiffDetails(ts);
      });
    });
  }

  function renderDeltaKV(delta) {
    const lines = [];
    for (const [k, v] of Object.entries(delta || {})) {
      if (Array.isArray(v) && v.length === 2) {
        const from = typeof v[0] === "object" ? JSON.stringify(v[0]) : String(v[0]);
        const to = typeof v[1] === "object" ? JSON.stringify(v[1]) : String(v[1]);
        lines.push(`<div class="delta"><span class="from">- ${escapeHtml(from)}</span><br/><span class="to">+ ${escapeHtml(to)}</span></div>`);
      } else {
        lines.push(`<div class="delta"><span class="to">~ ${escapeHtml(JSON.stringify(v))}</span></div>`);
      }
    }
    return lines.join("");
  }

  function renderDiffDetails(payload) {
    // payload: {"device","vrf","afi","rib":{"adds":[],"rems":[],"chgs":[]},"bgp":{...}}
    const rib = payload.rib || { adds: [], rems: [], chgs: [] };
    const bgp = payload.bgp || { adds: [], rems: [], chgs: [] };

    const summary = `
      <div class="diff-grid">
        <div class="diff-card">
          <h4>RIB</h4>
          <div>adds: <span class="badge">${rib.adds.length}</span></div>
          <div>removes: <span class="badge">${rib.rems.length}</span></div>
          <div>changes: <span class="badge">${rib.chgs.length}</span></div>
        </div>
        <div class="diff-card">
          <h4>BGP</h4>
          <div>adds: <span class="badge">${bgp.adds.length}</span></div>
          <div>removes: <span class="badge">${bgp.rems.length}</span></div>
          <div>changes: <span class="badge">${bgp.chgs.length}</span></div>
        </div>
        <div class="diff-card">
          <h4>Context</h4>
          <div class="kv">
            <div class="k">Device</div><div class="v"><code>${escapeHtml(payload.device || els.device.value)}</code></div>
            <div class="k">VRF</div><div class="v"><code>${escapeHtml(payload.vrf || els.vrf.value)}</code></div>
            <div class="k">AFI</div><div class="v"><code>${escapeHtml(payload.afi || els.afi.value)}</code></div>
          </div>
        </div>
      </div>
    `;

    function section(title, rows, kind) {
      if (!rows.length) return "";
      const list = rows.slice(0, 50).map((r) => {
        const head = kind === "bgp"
          ? `${r.prefix} ${r.best ? "(best)" : ""} via ${r.nh || ""}`
          : `${r.prefix} ${r.protocol || ""}`;
        const delta = r.delta ? renderDeltaKV(r.delta) : "";
        return `<div class="diff-card">
          <h4>${escapeHtml(head)}</h4>
          ${delta}
        </div>`;
      }).join("");
      return `<h4 style="color:#c9d7ee;margin:8px 0">${escapeHtml(title)}</h4>${list}`;
    }

    els.diffDetails.innerHTML = `
      ${summary}
      ${section("RIB changes", rib.chgs, "rib")}
      ${section("RIB adds", rib.adds, "rib")}
      ${section("RIB removes", rib.rems, "rib")}
      ${section("BGP changes", bgp.chgs, "bgp")}
      ${section("BGP adds", bgp.adds, "bgp")}
      ${section("BGP removes", bgp.rems, "bgp")}
    `;
  }

  function renderHistoryList(items) {
    if (!items.length) {
      els.historyList.innerHTML = `<div class="list"><div class="row"><span class="meta">No archives found</span></div></div>`;
      return;
    }
    const rows = items.map((e) => {
      const title = `${formatTs(e.ts)} (${e.name})`;
      return `<div class="row" data-ts="${e.ts}">
        <div class="title">${escapeHtml(title)}</div>
        <div class="meta">${e.size} B</div>
      </div>`;
    }).join("");
    els.historyList.innerHTML = `<div class="list">${rows}</div>`;
    els.historyList.querySelectorAll(".row").forEach((row) => {
      row.addEventListener("click", async () => {
        const ts = row.getAttribute("data-ts");
        await loadHistoryItem(ts);
      });
    });
  }

  function renderHistoryDetails(tableKind, rows) {
    const data = rows.slice(0, 200);
    if (tableKind === "rib") renderTableRIB(data);
    else renderTableBGP(data);
    els.historyDetails.innerHTML = els.latestTable.innerHTML;
  }

  // Loaders
  async function loadHealth() {
    try {
      const h = await api("/api/health");
      setHealth(h.status, h.snapdir, h.devices);
    } catch (e) {
      setHealth("error", "-", 0);
      console.warn("Health check failed:", e);
    }
  }

  async function loadDevices() {
    const d = await api("/api/devices");
    state.devices = d.devices || [];
    setOptions(els.device, state.devices, false);
  }

  async function loadDeviceTables() {
    if (!els.device.value) {
      state.deviceTables = { rib: [], bgp: [] };
      updateVrfAfiOptions();
      return;
    }
    state.deviceTables = await api(`/api/devices/${encodeURIComponent(els.device.value)}/tables`);
    updateVrfAfiOptions();
  }

  async function loadLatest() {
    if (!els.device.value) {
      els.latestSummary.innerHTML = "";
      els.latestTable.innerHTML = "";
      return;
    }
    const params = new URLSearchParams({
      table: els.table.value,
      vrf: els.vrf.value,
      afi: els.afi.value,
    });
    try {
      const rows = await api(`/api/devices/${encodeURIComponent(els.device.value)}/latest?` + params.toString());
      state.latestData = Array.isArray(rows) ? rows : [];
      summarizeLatest(els.table.value, state.latestData);
      const filtered = filterRows(state.latestData, els.latestFilter.value);
      if (els.table.value === "rib") renderTableRIB(filtered);
      else renderTableBGP(filtered);
    } catch (e) {
      state.latestData = [];
      summarizeLatest(els.table.value, state.latestData);
      els.latestTable.innerHTML = `<div class="badge warn">Failed to load latest: ${escapeHtml(e.message)}</div>`;
    }
  }

  async function loadDiffIndex() {
    if (!els.device.value) {
      els.diffList.innerHTML = "";
      els.diffDetails.innerHTML = "";
      return;
    }
    const params = new URLSearchParams({
      vrf: els.vrf.value,
      afi: els.afi.value,
      limit: "100",
    });
    try {
      const d = await api(`/api/devices/${encodeURIComponent(els.device.value)}/diffs?` + params.toString());
      renderDiffList(d.items || []);
      els.diffDetails.innerHTML = "";
    } catch (e) {
      els.diffList.innerHTML = `<div class="list"><div class="row"><span class="meta">Failed to load diffs: ${escapeHtml(e.message)}</span></div></div>`;
      els.diffDetails.innerHTML = "";
    }
  }

  async function loadDiffDetails(ts) {
    const params = new URLSearchParams({
      vrf: els.vrf.value,
      afi: els.afi.value,
    });
    try {
      const d = await api(`/api/devices/${encodeURIComponent(els.device.value)}/diffs/${encodeURIComponent(ts)}?` + params.toString());
      renderDiffDetails(d);
    } catch (e) {
      els.diffDetails.innerHTML = `<div class="badge warn">Failed to load diff details: ${escapeHtml(e.message)}</div>`;
    }
  }

  async function loadHistoryIndex() {
    if (!els.device.value) {
      els.historyList.innerHTML = "";
      els.historyDetails.innerHTML = "";
      return;
    }
    const params = new URLSearchParams({
      table: els.table.value,
      vrf: els.vrf.value,
      afi: els.afi.value,
      limit: "200",
    });
    try {
      const d = await api(`/api/devices/${encodeURIComponent(els.device.value)}/history?` + params.toString());
      renderHistoryList(d.items || []);
      els.historyDetails.innerHTML = "";
    } catch (e) {
      els.historyList.innerHTML = `<div class="list"><div class="row"><span class="meta">Failed to load history: ${escapeHtml(e.message)}</span></div></div>`;
      els.historyDetails.innerHTML = "";
    }
  }

  async function loadHistoryItem(ts) {
    const params = new URLSearchParams({
      table: els.table.value,
      vrf: els.vrf.value,
      afi: els.afi.value,
    });
    try {
      const rows = await api(`/api/devices/${encodeURIComponent(els.device.value)}/history/${encodeURIComponent(ts)}?` + params.toString());
      const data = Array.isArray(rows) ? rows : [];
      renderHistoryDetails(els.table.value, data);
    } catch (e) {
      els.historyDetails.innerHTML = `<div class="badge warn">Failed to load archive: ${escapeHtml(e.message)}</div>`;
    }
  }

  // Events
  els.tabs.forEach((btn) => {
    btn.addEventListener("click", async () => {
      els.tabs.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const tab = btn.getAttribute("data-tab");
      els.panels.forEach((p) => p.classList.remove("active"));
      document.getElementById(tab).classList.add("active");
      if (tab === "latest") await loadLatest();
      if (tab === "diffs") await loadDiffIndex();
      if (tab === "history") await loadHistoryIndex();
    });
  });

  els.device.addEventListener("change", async () => {
    await loadDeviceTables();
    await loadLatest();
    await loadDiffIndex();
    await loadHistoryIndex();
  });

  els.table.addEventListener("change", async () => {
    updateVrfAfiOptions();
    await loadLatest();
    await loadDiffIndex();
    await loadHistoryIndex();
  });

  els.vrf.addEventListener("change", async () => {
    updateVrfAfiOptions(); // update AFI options constrained by VRF
    await loadLatest();
    await loadDiffIndex();
    await loadHistoryIndex();
  });

  els.afi.addEventListener("change", async () => {
    await loadLatest();
    await loadDiffIndex();
    await loadHistoryIndex();
  });

  els.refresh.addEventListener("click", async () => {
    const active = document.querySelector(".tab.active")?.getAttribute("data-tab");
    if (active === "latest") await loadLatest();
    if (active === "diffs") await loadDiffIndex();
    if (active === "history") await loadHistoryIndex();
  });

  let filterTimer = null;
  els.latestFilter.addEventListener("input", () => {
    clearTimeout(filterTimer);
    filterTimer = setTimeout(() => {
      const filtered = filterRows(state.latestData, els.latestFilter.value);
      if (els.table.value === "rib") renderTableRIB(filtered);
      else renderTableBGP(filtered);
    }, 120);
  });

  // Boot
  (async function init() {
    await loadHealth();
    await loadDevices();
    if (state.devices.length) {
      await loadDeviceTables();
      await loadLatest();
      await loadDiffIndex();
      await loadHistoryIndex();
    } else {
      els.latestSummary.innerHTML = `<span class="badge warn">No devices found under SNAPDIR.</span>`;
    }
  })();
})();
