// app.js — rendering & interaction logic.
// Expects window.ELECTION_DATA (loaded by data.js before this script).

(function () {
  "use strict";

  // ── Pull data from the global ────────────────────────────────────────────────
  const { parties, questions, answers, reasonings, priorityCategories, rangeEn, meta } =
    window.ELECTION_DATA;

  // ── State ────────────────────────────────────────────────────────────────────
  const activeParties = new Set(parties.map((p) => p.name));
  let activeCat = "all";
  let searchTerm = "";

  // ── Helpers ──────────────────────────────────────────────────────────────────
  function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }

  function getRangeClass(val) {
    const map = {
      "Much lower": "range-0",
      Lower:        "range-1",
      Unchanged:    "range-2",
      Higher:       "range-3",
      "Much higher":"range-4",
      // Icelandic fallbacks (shouldn't be needed but just in case)
      "Mun lægra":  "range-0",
      Lægra:        "range-1",
      Óbreytt:      "range-2",
      Hærra:        "range-3",
      "Mun hærra":  "range-4",
    };
    return map[val.replace("!", "").trim()] || "range-2";
  }

  const AGREE_LABEL = {
    A: "Strongly disagree",
    B: "Disagree",
    C: "Agree",
    D: "Strongly agree",
  };

  const CAT_LABELS = {
    general:     "🏙 General & Governance",
    housing:     "🏠 Housing & Urban Development",
    children:    "👶 Children, Schools & Nurseries",
    welfare:     "❤️ Welfare, Elderly & Culture",
    transport:   "🚌 Transport & Mobility",
    environment: "🌿 Environment",
    rvk:         "📍 Reykjavík-specific",
  };

  // ── Build hero badges dynamically ────────────────────────────────────────────
  function buildHero() {
    const n_q = questions.length;
    const n_p = parties.length;
    const dateStr = meta.generated
      ? new Date(meta.generated).toLocaleDateString("en-GB", {
          day: "numeric", month: "long", year: "numeric",
        })
      : "";
    document.getElementById("badge-questions").textContent =
      `📋 ${n_q} questions · ${n_p} parties`;
    if (dateStr) {
      document.getElementById("badge-date").textContent = `🗓 Generated ${dateStr}`;
    }
  }

  // ── Build filter buttons from categories present in data ─────────────────────
  function buildCategoryFilters() {
    const cats = [...new Set(questions.map((q) => q.cat))];
    const container = document.getElementById("catFilters");
    container.innerHTML = ""; // clear

    const allBtn = makeFilterBtn("All topics", "all", true);
    container.appendChild(allBtn);

    cats.forEach((cat) => {
      container.appendChild(makeFilterBtn(CAT_LABELS[cat] || cat, cat, false));
    });
  }

  function makeFilterBtn(label, cat, active) {
    const btn = document.createElement("button");
    btn.className = "filter-btn" + (active ? " active" : "");
    btn.dataset.cat = cat;
    btn.textContent = label;
    btn.addEventListener("click", () => filterCat(btn, cat));
    return btn;
  }

  // ── Build party header columns ────────────────────────────────────────────────
  function buildPartyHeader() {
    const tr = document.querySelector("#mainTable thead tr");
    parties.forEach((p) => {
      const th = document.createElement("th");
      th.dataset.party = p.name;
      th.innerHTML = `<div class="party-th-inner">
        <div class="party-th-dot" style="background:${p.color}" title="${p.name}">${p.abbr}</div>
        <span class="party-th-label">${p.nameEn}</span>
      </div>`;
      tr.appendChild(th);
    });
  }

  // ── Build party toggle pills ──────────────────────────────────────────────────
  function buildPartyPills() {
    const container = document.getElementById("partyPills");
    parties.forEach((p) => {
      const pill = document.createElement("div");
      pill.className = "party-pill";
      pill.dataset.party = p.name;
      pill.style.background = hexToRgba(p.color, 0.15);
      pill.style.borderColor = hexToRgba(p.color, 0.4);
      pill.style.color = p.color;
      pill.innerHTML = `<span class="abbr" style="background:${p.color}">${p.abbr}</span>${p.nameEn}`;
      pill.addEventListener("click", () => toggleParty(p.name));
      container.appendChild(pill);
    });
  }

  // ── Render a single answer cell ───────────────────────────────────────────────
  function renderAnswerCell(q, rawVal, party, partyIndex) {
    const cell = document.createElement("td");
    cell.className = "answer-cell";
    cell.dataset.party = party.name;

    // Look up reasoning for this party + question
    const reasoning = reasonings?.[q.id]?.[partyIndex] || null;

    // PRIORITY question
    if (q.type === "PRIORITY") {
      const ids = Array.isArray(rawVal) ? rawVal : [];
      const tags = ids
        .map(
          (id) =>
            `<span class="priority-tag">${priorityCategories[id] || id}</span>`
        )
        .join("");
      const tip = reasoning ? reasoning : null;
      cell.innerHTML = `<div class="priority-tags" ${tip ? `data-tip="${escAttr(tip)}"` : ""}>${tags || "—"}</div>`;
      return cell;
    }

    // No answer
    if (!rawVal || rawVal === "_") {
      const tip = reasoning ? escAttr(reasoning) : "No answer";
      const info = reasoning ? '<span class="info-dot">i</span>' : "";
      cell.innerHTML = `<span class="answer-chip no-answer" data-tip="${tip}">${info}—</span>`;
      return cell;
    }

    const important = typeof rawVal === "string" && rawVal.endsWith("!");
    const val = typeof rawVal === "string" ? rawVal.replace("!", "").trim() : rawVal;
    const star = important ? '<span class="star">★</span>' : "";
    const info = reasoning  ? '<span class="info-dot">i</span>' : "";

    // Build tooltip: label on first line, priority flag, then reasoning
    function makeTip(label) {
      let tip = label;
      if (important) tip += "\n⭐ Marked as priority";
      if (reasoning)  tip += "\n\n" + reasoning;
      return escAttr(tip);
    }

    // RANGE question
    if (q.type === "RANGE" || rangeEn[val] || Object.values(rangeEn).includes(val)) {
      const cls = getRangeClass(val);
      cell.innerHTML = `<span class="answer-chip ${cls}" data-tip="${makeTip(val)}">${info}${val}${star}</span>`;
      return cell;
    }

    // PROPOSITION A–D
    const tipText = AGREE_LABEL[val] || val;
    cell.innerHTML = `<span class="answer-chip ans-${val}" data-tip="${makeTip(tipText)}">${info}${val}${star}</span>`;
    return cell;
  }

  // Escape a string for use in a data-tip HTML attribute
  function escAttr(str) {
    return str.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
  }

  // ── Build section header row ──────────────────────────────────────────────────
  function buildSectionHeader(label) {
    const tr = document.createElement("tr");
    tr.className = "section-header";
    const td = document.createElement("td");
    td.colSpan = parties.length + 1;
    td.textContent = label;
    tr.appendChild(td);
    return tr;
  }

  // ── Build all data rows ───────────────────────────────────────────────────────
  function buildRows() {
    const tbody = document.getElementById("tableBody");
    let lastCat = null;

    questions.forEach((q) => {
      if (q.cat !== lastCat) {
        tbody.appendChild(buildSectionHeader(CAT_LABELS[q.cat] || q.cat));
        lastCat = q.cat;
      }

      const tr = document.createElement("tr");
      tr.dataset.cat = q.cat;
      tr.dataset.qid = q.id;
      tr.dataset.searchText = (q.en + " " + q.is).toLowerCase();

      // Question label cell
      const qtd = document.createElement("td");
      qtd.innerHTML = `<div class="q-label">${q.en}</div>
        <div class="q-is">${q.is}</div>`;
      tr.appendChild(qtd);

      // Answer cells — one per party (in party order)
      const rowAnswers = answers[q.id] || [];
      parties.forEach((p, i) => {
        const rawVal = rowAnswers[i] !== undefined ? rowAnswers[i] : "_";
        tr.appendChild(renderAnswerCell(q, rawVal, p, i));
      });

      tbody.appendChild(tr);
    });
  }

  // ── Interactions ─────────────────────────────────────────────────────────────
  function toggleParty(name) {
    if (activeParties.has(name)) {
      if (activeParties.size === 1) return; // keep at least one visible
      activeParties.delete(name);
    } else {
      activeParties.add(name);
    }
    applyPartyFilter();
  }

  function applyPartyFilter() {
    parties.forEach((p) => {
      const on = activeParties.has(p.name);
      const esc = CSS.escape(p.name);
      document.querySelector(`.party-pill[data-party="${esc}"]`)
        ?.classList.toggle("dimmed", !on);
      document.querySelector(`thead th[data-party="${esc}"]`)
        ?.classList.toggle("col-dimmed", !on);
      document.querySelectorAll(`td[data-party="${esc}"]`).forEach((td) =>
        td.classList.toggle("col-dimmed", !on)
      );
    });
  }

  function filterCat(btn, cat) {
    document.querySelectorAll(".filter-btn").forEach((b) =>
      b.classList.remove("active")
    );
    btn.classList.add("active");
    activeCat = cat;
    applyRowFilter();
  }

  function doSearch(val) {
    searchTerm = val.toLowerCase();
    applyRowFilter();
  }

  function applyRowFilter() {
    document.querySelectorAll("#tableBody tr:not(.section-header)").forEach((tr) => {
      const catOk = activeCat === "all" || tr.dataset.cat === activeCat;
      const searchOk =
        !searchTerm || (tr.dataset.searchText || "").includes(searchTerm);
      tr.classList.toggle("hidden-row", !(catOk && searchOk));
    });

    // Show/hide section headers based on whether any of their rows are visible
    document.querySelectorAll("#tableBody tr.section-header").forEach((header) => {
      let next = header.nextElementSibling;
      let hasVisible = false;
      while (next && !next.classList.contains("section-header")) {
        if (!next.classList.contains("hidden-row")) {
          hasVisible = true;
          break;
        }
        next = next.nextElementSibling;
      }
      header.classList.toggle("hidden-row", !hasVisible);
    });
  }

  // ── JS Tooltip ───────────────────────────────────────────────────────────────
  const tooltip = document.getElementById("js-tooltip");

  document.addEventListener("mouseover", (e) => {
    const el = e.target.closest("[data-tip]");
    if (!el) { tooltip.style.display = "none"; return; }
    tooltip.textContent = el.dataset.tip;
    tooltip.style.display = "block";
    positionTooltip(e);
  });

  document.addEventListener("mousemove", (e) => {
    if (tooltip.style.display === "none") return;
    positionTooltip(e);
  });

  document.addEventListener("mouseout", (e) => {
    if (!e.target.closest("[data-tip]")) return;
    tooltip.style.display = "none";
  });

  function positionTooltip(e) {
    const GAP = 12;
    const tw = tooltip.offsetWidth;
    const th = tooltip.offsetHeight;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let x = e.clientX - tw / 2;
    let y = e.clientY - th - GAP;
    // Flip below cursor if too close to top
    if (y < 4) y = e.clientY + GAP;
    // Keep within viewport horizontally
    x = Math.max(6, Math.min(x, vw - tw - 6));
    tooltip.style.left = x + "px";
    tooltip.style.top  = y + "px";
  }

  // ── Cloned fixed header ───────────────────────────────────────────────────────
  //
  // position:sticky on thead does NOT work when the table lives inside an
  // overflow:auto container (the browser spec forbids it). Instead we maintain
  // a second <thead> rendered position:fixed that mirrors the real one.
  //
  const stickyBar   = document.getElementById("sticky-header");
  const stickyTr    = stickyBar.querySelector("tr");
  const tableWrap   = document.getElementById("tableWrap");
  const mainTable   = document.getElementById("mainTable");
  const controls    = document.getElementById("controls");

  // Populate the clone row with th elements matching the real thead
  function buildStickyHeader() {
    stickyTr.innerHTML = "";
    const realThs = mainTable.querySelectorAll("thead th");
    realThs.forEach((th) => {
      const clone = th.cloneNode(true);
      stickyTr.appendChild(clone);
    });
  }

  // Sync widths, position, and horizontal scroll offset
  function syncStickyHeader() {
    const controlsRect  = controls.getBoundingClientRect();
    const wrapRect      = tableWrap.getBoundingClientRect();
    const realThs       = mainTable.querySelectorAll("thead th");
    const cloneThs      = stickyTr.querySelectorAll("th");
    const realTheadRect = mainTable.querySelector("thead").getBoundingClientRect();

    // Show the fixed header only once the real thead has scrolled above viewport
    const shouldShow = realTheadRect.bottom <= controlsRect.bottom;
    stickyBar.style.display = shouldShow ? "block" : "none";

    if (!shouldShow) return;

    // Position: sit just below the controls bar, span the visible table width
    stickyBar.style.top    = controlsRect.bottom + "px";
    stickyBar.style.left   = wrapRect.left + "px";
    stickyBar.style.width  = wrapRect.width + "px";

    // Match each column width to the real thead
    const tableWidth = mainTable.getBoundingClientRect().width;
    stickyBar.querySelector("table").style.width = tableWidth + "px";
    realThs.forEach((th, i) => {
      if (cloneThs[i]) cloneThs[i].style.width = th.getBoundingClientRect().width + "px";
    });

    // Translate to mirror the horizontal scroll of the wrapper
    stickyBar.querySelector("table").style.transform =
      `translateX(${-tableWrap.scrollLeft}px)`;
  }

  // ── Footer source link ────────────────────────────────────────────────────────
  function buildFooter() {
    const el = document.getElementById("footer-source");
    if (el) el.href = `https://${meta.source}`;
    const gen = document.getElementById("footer-generated");
    if (gen && meta.generated) {
      gen.textContent = `Data generated: ${new Date(meta.generated).toLocaleString("en-GB")}`;
    }
  }

  // ── Expose search handler to inline HTML ─────────────────────────────────────
  window.doSearch = doSearch;

  // ── Init ─────────────────────────────────────────────────────────────────────
  buildHero();
  buildCategoryFilters();
  buildPartyHeader();
  buildPartyPills();
  buildRows();
  buildFooter();
  buildStickyHeader();

  window.addEventListener("scroll",  syncStickyHeader, { passive: true });
  tableWrap.addEventListener("scroll", syncStickyHeader, { passive: true });
  window.addEventListener("resize",  syncStickyHeader);
  requestAnimationFrame(() => requestAnimationFrame(syncStickyHeader));
})();
