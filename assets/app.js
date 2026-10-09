(() => {
  "use strict";

  const SECTIONS = window.BR_CONFIG.sections;
  const SECTION_BY_ID = Object.fromEntries(SECTIONS.map(s => [s.id, s]));
  const $ = sel => document.querySelector(sel);

  const els = {
    sidebar: $("#sidebar"),
    main: $("#main"),
    detail: $("#detail"),
    backdrop: $("#backdrop"),
    search: $("#globalSearch"),
    results: $("#searchResults"),
  };

  // ---------- storage ----------

  const store = {
    get(key, fallback) {
      try {
        const v = localStorage.getItem("brwiki:" + key);
        return v == null ? fallback : JSON.parse(v);
      } catch { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem("brwiki:" + key, JSON.stringify(value)); } catch { /* ignore */ }
    },
  };

  const favorites = new Set(store.get("favorites", []));
  const toggleFavorite = id => {
    favorites.has(id) ? favorites.delete(id) : favorites.add(id);
    store.set("favorites", [...favorites]);
  };

  // ---------- helpers ----------

  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const norm = s => String(s ?? "").toLowerCase().replace(/ё/g, "е").trim();
  const num = v => {
    const m = String(v ?? "").replace(",", ".").match(/-?\d+(\.\d+)?/);
    return m ? parseFloat(m[0]) : NaN;
  };
  const plural = (n, one, few, many) => {
    const m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
  };
  // \b в JS не работает с кириллицей, поэтому граница слова задаётся явно.
  const isLevelLabel = k => /^(требуемый уровень|уровень|ур\.?|lvl|level)(\s|:|$)/i.test(String(k).trim());
  const stripTags = html => String(html ?? "").replace(/<[^>]*>/g, " ");
  const countLabel = n => `${n} ${plural(n, "запись", "записи", "записей")}`;

  function iconHtml(entry, cls = "") {
    const letter = esc((entry.name || "?").trim().charAt(0).toUpperCase());
    if (!entry.icon) return `<div class="ico ico-empty ${cls}">${letter}</div>`;
    return `<div class="ico ${cls}"><img src="${esc(entry.icon)}" alt="" loading="lazy"
      onerror="this.parentNode.classList.add('ico-empty');this.parentNode.textContent='${letter}'"></div>`;
  }

  // ---------- data ----------

  const db = { sections: {}, all: [], byId: new Map(), byName: new Map(), demo: false };

  function loadScript(src) {
    return new Promise(resolve => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = () => resolve(true);
      s.onerror = () => resolve(false);
      document.head.appendChild(s);
    });
  }

  async function loadData() {
    window.BR_DATA = window.BR_DATA || {};
    await Promise.all(SECTIONS.map(s => loadScript(`data/${s.id}.js`)));
    const hasReal = SECTIONS.some(s => window.BR_DATA[s.id]?.entries?.length);
    if (!hasReal) {
      db.demo = await loadScript("data/demo.js");
    }

    for (const sec of SECTIONS) {
      const raw = window.BR_DATA[sec.id] || {};
      const entries = (raw.entries || []).map((e, i) => normalizeEntry(e, sec.id, i));

      // Категории: сначала из конфига, затем найденные парсером, затем встреченные в записях.
      const cats = [];
      const seen = new Set();
      const addCat = c => {
        if (!c || !c.id || seen.has(c.id)) return;
        seen.add(c.id);
        cats.push({ id: c.id, name: c.name || c.id, source: c.source });
      };
      sec.categories.forEach(addCat);
      (raw.categories || []).forEach(addCat);
      entries.forEach(e => addCat({ id: e.category, name: e.category === "_" ? "Прочее" : e.category }));
      for (const c of cats) c.count = entries.filter(e => e.category === c.id).length;
      // Раздел без настоящих категорий («Питомцы», «НПС») показываем одним списком.
      if (cats.length === 1 && cats[0].id === "_") cats.length = 0;

      db.sections[sec.id] = { ...sec, categories: cats, entries, updated: raw.updated };
      for (const e of entries) {
        db.all.push(e);
        db.byId.set(e.id, e);
        const key = norm(e.name);
        if (!db.byName.has(key)) db.byName.set(key, e);
      }
    }
  }

  function normalizeEntry(e, sectionId, index) {
    const fields = Array.isArray(e.fields)
      ? e.fields.filter(f => Array.isArray(f) && f.length >= 2)
      : Object.entries(e.fields || {});
    let level = e.level ?? null;
    if (level == null) {
      const lf = fields.find(([k]) => isLevelLabel(k));
      if (lf && !isNaN(num(lf[1]))) level = num(lf[1]);
    }
    const name = e.name || "Без названия";
    return {
      id: e.id || `${sectionId}/${e.category || "_"}/${index}`,
      section: sectionId,
      category: e.category || "_",
      name,
      icon: e.icon || "",
      level,
      fields,
      description: e.description || "",
      lists: Array.isArray(e.lists) ? e.lists : [],
      blocks: Array.isArray(e.blocks) ? e.blocks : [],
      image: e.image || "",
      nameEN: e.nameEN || "",
      sourceUrl: e.sourceUrl || "",
      search: norm(name + " " + (e.nameEN || "")),
      searchFull: norm([name, e.nameEN, e.description, ...fields.flat(),
        ...(e.blocks || []).map(b => stripTags(b.html))].join(" ")),
    };
  }

  // ---------- routing ----------

  // #/                         — главная
  // #/s/<section>[/<category>] — раздел / категория
  // #/fav                      — избранное
  // ?e=<entryId>               — открытая карточка
  function parseRoute() {
    const [path, query = ""] = location.hash.replace(/^#/, "").split("?");
    const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
    const params = new URLSearchParams(query);
    return { parts, entryId: params.get("e") };
  }

  function href(parts, entryId) {
    const p = "#/" + parts.map(encodeURIComponent).join("/");
    return entryId ? `${p}?e=${encodeURIComponent(entryId)}` : p;
  }

  function entryHref(e) {
    return href(["s", e.section, e.category], e.id);
  }

  // ---------- view state ----------

  const view = {
    query: "",
    sort: store.get("sort", "name"),
    sortDir: 1,
    mode: store.get("mode", "grid"),
    list: [],           // текущий отображаемый список (для навигации стрелками)
    routeKey: "",
  };

  // ---------- sidebar ----------

  function renderSidebar(route) {
    const [kind, secId, catId] = route.parts;
    let html = `<div class="nav-group">`;
    html += `<a class="nav-item ${!kind ? "active" : ""}" href="#/"><span class="nav-ico">🏠</span>Главная</a>`;
    html += `<a class="nav-item ${kind === "fav" ? "active" : ""}" href="#/fav"><span class="nav-ico">⭐</span>Избранное
      <span class="count">${favorites.size}</span></a>`;
    html += `</div><div class="nav-title">Разделы</div><div class="nav-group">`;

    for (const sec of SECTIONS) {
      const data = db.sections[sec.id];
      const open = kind === "s" && secId === sec.id;
      html += `<a class="nav-item ${open && !catId ? "active" : ""} ${open ? "open" : ""}" href="${href(["s", sec.id])}">
        <span class="nav-ico">${sec.icon}</span>${esc(sec.title)}<span class="count">${data.entries.length}</span></a>`;
      if (open && data.categories.length) {
        html += `<div class="nav-sub">`;
        for (const c of data.categories) {
          html += `<a class="nav-subitem ${catId === c.id ? "active" : ""}" href="${href(["s", sec.id, c.id])}">
            ${esc(c.name)}<span class="count">${c.count}</span></a>`;
        }
        html += `</div>`;
      }
    }
    html += `</div>`;
    els.sidebar.innerHTML = html;
  }

  // ---------- main views ----------

  function renderHome() {
    let html = "";
    if (db.demo) html += demoBanner();
    html += `<h1 class="page-title">Broken Ranks Wiki</h1>
      <p class="page-sub">Личная база по игре: экипировка, питомцы, противники, предметы и НПС.</p>
      <div class="home-grid">`;
    for (const sec of SECTIONS) {
      const data = db.sections[sec.id];
      html += `<div class="home-card">
        <a class="home-card-head" href="${href(["s", sec.id])}">
          <span class="home-ico">${sec.icon}</span>
          <span><b>${esc(sec.title)}</b><small>${countLabel(data.entries.length)}</small></span>
        </a>
        <div class="chips">${data.categories.map(c =>
          `<a class="chip" href="${href(["s", sec.id, c.id])}">${esc(c.name)} <i>${c.count}</i></a>`).join("")
          || `<span class="muted">Все записи одним списком</span>`}</div>
      </div>`;
    }
    html += `</div>`;
    els.main.innerHTML = html;
    view.list = [];
  }

  function demoBanner() {
    return `<div class="banner">Показаны <b>демо-данные</b> — настоящих данных ещё нет.
      Запусти парсер (<code>python scraper/scrape.py</code>), он создаст файлы в <code>data/</code>.</div>`;
  }

  function renderList(title, subtitle, entries, opts = {}) {
    const q = norm(view.query);
    let list = q
      ? entries.filter(e => e.search.includes(q) || e.searchFull.includes(q))
      : entries.slice();

    const dir = view.sortDir;
    if (view.sort === "name") list.sort((a, b) => dir * a.name.localeCompare(b.name, "ru"));
    else if (view.sort === "level") list.sort((a, b) => dir * ((a.level ?? 1e9) - (b.level ?? 1e9)) || a.name.localeCompare(b.name, "ru"));
    else if (view.sort.startsWith("f:")) {
      const label = view.sort.slice(2);
      const val = e => e.fields.find(([k]) => k === label)?.[1];
      list.sort((a, b) => {
        const va = val(a), vb = val(b);
        if (va == null) return 1;
        if (vb == null) return -1;
        const na = num(va), nb = num(vb);
        if (!isNaN(na) && !isNaN(nb) && na !== nb) return dir * (na - nb);
        return dir * String(va).localeCompare(String(vb), "ru");
      });
    }
    view.list = list;

    const hasLevels = entries.some(e => e.level != null);
    let html = db.demo ? demoBanner() : "";
    html += `<div class="list-head">
      <div>
        <h1 class="page-title">${esc(title)}</h1>
        <p class="page-sub">${subtitle}</p>
      </div>
      ${opts.source ? `<a class="src-link" href="${esc(opts.source)}" target="_blank" rel="noopener">Источник ↗</a>` : ""}
    </div>`;

    if (opts.categories?.length) {
      html += `<div class="chips cat-chips">
        <a class="chip ${!opts.activeCat ? "active" : ""}" href="${href(["s", opts.sectionId])}">Все <i>${opts.total}</i></a>
        ${opts.categories.map(c => `<a class="chip ${opts.activeCat === c.id ? "active" : ""}"
          href="${href(["s", opts.sectionId, c.id])}">${esc(c.name)} <i>${c.count}</i></a>`).join("")}
      </div>`;
    }

    html += `<div class="toolbar">
      <input class="local-search" id="localSearch" type="search" placeholder="Фильтр по названию и характеристикам…"
        value="${esc(view.query)}" autocomplete="off">
      <select id="sortSel" title="Сортировка">
        <option value="name" ${view.sort === "name" ? "selected" : ""}>По названию</option>
        ${hasLevels ? `<option value="level" ${view.sort === "level" ? "selected" : ""}>По уровню</option>` : ""}
      </select>
      <button class="icon-btn" id="dirBtn" title="Направление сортировки">${view.sortDir > 0 ? "↑" : "↓"}</button>
      <div class="seg">
        <button data-mode="grid" class="${view.mode === "grid" ? "active" : ""}" title="Карточки">▦</button>
        <button data-mode="table" class="${view.mode === "table" ? "active" : ""}" title="Таблица">☰</button>
      </div>
    </div>
    <div class="result-count">${q ? `Найдено: ${list.length} из ${entries.length}` : countLabel(list.length)}</div>`;

    if (!list.length) {
      html += `<div class="empty">${entries.length ? "Ничего не найдено" : "Здесь пока пусто"}</div>`;
    } else if (view.mode === "table") {
      html += renderTable(list, opts.showSection);
    } else {
      html += `<div class="grid">${list.map(e => renderCard(e, opts.showSection)).join("")}</div>`;
    }

    els.main.innerHTML = html;
    bindToolbar();
  }

  const PREVIEW_SKIP = /^(тип|улучшения|атаки|зоны атаки|шанс дропа|группа боссов)/i;

  function renderCard(e, showSection) {
    const sec = db.sections[e.section];
    const cat = sec.categories.find(c => c.id === e.category);
    const preview = e.fields.filter(([k]) => !isLevelLabel(k) && !PREVIEW_SKIP.test(k)).slice(0, 3);
    return `<a class="card ${favorites.has(e.id) ? "fav" : ""}" href="${entryHref(e)}" data-id="${esc(e.id)}">
      ${iconHtml(e)}
      <div class="card-body">
        <div class="card-name">${esc(e.name)}</div>
        <div class="card-meta">
          ${e.level != null ? `<span class="lvl">ур. ${esc(e.level)}</span>` : ""}
          <span>${showSection ? esc(sec.title) + " · " : ""}${esc(cat?.name || "")}</span>
        </div>
        ${preview.length ? `<div class="card-fields">${preview.map(([k, v]) =>
          `<span><em>${esc(k)}:</em> ${esc(v)}</span>`).join("")}</div>` : ""}
      </div>
    </a>`;
  }

  function renderTable(list, showSection) {
    const freq = new Map();
    for (const e of list) for (const [k] of e.fields) freq.set(k, (freq.get(k) || 0) + 1);
    // Колонки с одинаковым у всех значением ничего не дают для сравнения.
    const varies = k => list.length < 2 ||
      new Set(list.map(e => e.fields.find(([l]) => l === k)?.[1] ?? "")).size > 1;
    const cols = [...freq.entries()]
      .filter(([k]) => !isLevelLabel(k) && varies(k))
      .sort((a, b) => b[1] - a[1]).slice(0, 10).map(([k]) => k);
    const hasLevels = list.some(e => e.level != null);
    const arrow = key => view.sort === key ? (view.sortDir > 0 ? " ↑" : " ↓") : "";

    let html = `<div class="table-wrap"><table class="tbl"><thead><tr>
      <th class="sortable" data-sort="name">Название${arrow("name")}</th>
      ${showSection ? "<th>Раздел</th>" : ""}
      ${hasLevels ? `<th class="sortable num" data-sort="level">Ур.${arrow("level")}</th>` : ""}
      ${cols.map(c => `<th class="sortable" data-sort="f:${esc(c)}">${esc(c)}${arrow("f:" + c)}</th>`).join("")}
    </tr></thead><tbody>`;
    for (const e of list) {
      const fm = new Map(e.fields);
      html += `<tr data-href="${esc(entryHref(e))}">
        <td class="tname"><a href="${entryHref(e)}">${iconHtml(e, "ico-sm")}<span>${esc(e.name)}</span></a></td>
        ${showSection ? `<td>${esc(db.sections[e.section].title)}</td>` : ""}
        ${hasLevels ? `<td class="num">${esc(e.level ?? "")}</td>` : ""}
        ${cols.map(c => `<td>${esc(fm.get(c) ?? "")}</td>`).join("")}
      </tr>`;
    }
    html += `</tbody></table></div>`;
    return html;
  }

  function bindToolbar() {
    const ls = $("#localSearch");
    if (ls) {
      ls.addEventListener("input", () => {
        view.query = ls.value;
        const pos = ls.selectionStart;
        renderMain(parseRoute());
        const again = $("#localSearch");
        again.focus();
        again.setSelectionRange(pos, pos);
      });
    }
    $("#sortSel")?.addEventListener("change", ev => {
      view.sort = ev.target.value;
      store.set("sort", view.sort);
      renderMain(parseRoute());
    });
    $("#dirBtn")?.addEventListener("click", () => {
      view.sortDir *= -1;
      renderMain(parseRoute());
    });
    document.querySelectorAll(".seg button").forEach(b => b.addEventListener("click", () => {
      view.mode = b.dataset.mode;
      store.set("mode", view.mode);
      renderMain(parseRoute());
    }));
    document.querySelectorAll("th.sortable").forEach(th => th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (view.sort === key) view.sortDir *= -1;
      else { view.sort = key; view.sortDir = 1; }
      renderMain(parseRoute());
    }));
    document.querySelectorAll("tr[data-href]").forEach(tr => tr.addEventListener("click", ev => {
      if (ev.target.closest("a")) return;
      location.hash = tr.dataset.href;
    }));
  }

  function renderMain(route) {
    const [kind, secId, catId] = route.parts;
    const key = route.parts.join("/");
    if (key !== view.routeKey) {
      view.routeKey = key;
      view.query = "";
      if (view.sort.startsWith("f:")) view.sort = "name";
      els.main.scrollTop = 0;
    }

    if (kind === "s" && db.sections[secId]) {
      const sec = db.sections[secId];
      const cat = sec.categories.find(c => c.id === catId);
      const entries = cat ? sec.entries.filter(e => e.category === cat.id) : sec.entries;
      renderList(cat ? cat.name : sec.title, cat ? esc(sec.title) : "Все категории", entries, {
        sectionId: sec.id,
        categories: sec.categories,
        activeCat: cat?.id,
        total: sec.entries.length,
        source: cat?.source || sec.source,
        showSection: false,
      });
    } else if (kind === "fav") {
      const entries = [...favorites].map(id => db.byId.get(id)).filter(Boolean);
      renderList("Избранное", "Отмечай записи звёздочкой в карточке", entries, { showSection: true });
    } else {
      renderHome();
    }
  }

  // ---------- detail ----------

  function linkify(text) {
    const target = db.byName.get(norm(text));
    return target
      ? `<a href="${entryHref(target)}">${esc(text)}</a>`
      : esc(text);
  }

  function renderDetail(route) {
    const e = route.entryId && db.byId.get(route.entryId);
    if (!e) {
      els.detail.hidden = true;
      els.backdrop.hidden = !document.body.classList.contains("nav-open");
      document.body.classList.remove("detail-open");
      return;
    }
    const sec = db.sections[e.section];
    const cat = sec.categories.find(c => c.id === e.category);
    const idx = view.list.findIndex(x => x.id === e.id);
    const prev = idx > 0 ? view.list[idx - 1] : null;
    const next = idx >= 0 && idx < view.list.length - 1 ? view.list[idx + 1] : null;

    els.detail.innerHTML = `
      <div class="detail-bar">
        <a class="icon-btn" ${prev ? `href="${entryHref(prev)}"` : "aria-disabled=true"} title="Предыдущая (←)">‹</a>
        <a class="icon-btn" ${next ? `href="${entryHref(next)}"` : "aria-disabled=true"} title="Следующая (→)">›</a>
        <span class="spacer"></span>
        <button class="icon-btn fav-btn ${favorites.has(e.id) ? "on" : ""}" id="favBtn" title="В избранное">★</button>
        <button class="icon-btn" id="closeDetail" title="Закрыть (Esc)">✕</button>
      </div>
      <div class="detail-head">
        ${iconHtml(e, "ico-lg")}
        <div>
          <h2>${esc(e.name)}</h2>
          ${e.nameEN && e.nameEN !== e.name ? `<div class="name-en">${esc(e.nameEN)}</div>` : ""}
          <div class="crumbs">
            <a href="${href(["s", sec.id])}">${esc(sec.title)}</a>
            ${cat ? ` / <a href="${href(["s", sec.id, cat.id])}">${esc(cat.name)}</a>` : ""}
          </div>
          ${e.level != null ? `<span class="lvl">Уровень ${esc(e.level)}</span>` : ""}
        </div>
      </div>
      ${e.image ? `<div class="model"><img src="${esc(e.image)}" alt="" onerror="this.parentNode.remove()"></div>` : ""}
      ${e.fields.length ? `<table class="props">${e.fields.map(([k, v]) =>
        `<tr><th>${esc(k)}</th><td>${linkify(v)}</td></tr>`).join("")}</table>` : ""}
      ${e.description ? `<div class="desc">${esc(e.description).replace(/\n/g, "<br>")}</div>` : ""}
      ${e.blocks.map(b => `<div class="block">
        <h3>${esc(b.title)}</h3>
        <div class="block-html">${b.html}</div>
      </div>`).join("")}
      ${e.lists.map(l => `<div class="detail-list">
        <h3>${esc(l.title)}</h3>
        <ul>${(l.items || []).map(it => `<li>${linkify(it)}</li>`).join("")}</ul>
      </div>`).join("")}
      ${e.sourceUrl ? `<a class="src-link" href="${esc(e.sourceUrl)}" target="_blank" rel="noopener">Открыть на источнике ↗</a>` : ""}
    `;
    els.detail.hidden = false;
    els.detail.scrollTop = 0;
    document.body.classList.add("detail-open");
    els.backdrop.hidden = false;

    bindRefs(els.detail);
    $("#closeDetail").addEventListener("click", closeDetail);
    $("#favBtn").addEventListener("click", ev => {
      toggleFavorite(e.id);
      ev.currentTarget.classList.toggle("on", favorites.has(e.id));
      renderSidebar(parseRoute());
      document.querySelector(`.card[data-id="${CSS.escape(e.id)}"]`)?.classList.toggle("fav", favorites.has(e.id));
    });
    document.querySelectorAll(".card.selected, tr.selected").forEach(n => n.classList.remove("selected"));
    document.querySelector(`.card[data-id="${CSS.escape(e.id)}"]`)?.classList.add("selected");
  }

  // Иконки с data-items в HTML-блоках — ссылки на другие записи вики.
  function bindRefs(root) {
    root.querySelectorAll(".block-html [data-items]").forEach(node => {
      const target = db.byId.get(node.getAttribute("data-items"));
      if (!target) return;
      node.classList.add("ref");
      node.setAttribute("title", target.name);
      node.addEventListener("click", ev => {
        ev.preventDefault();
        location.hash = entryHref(target);
      });
    });
    root.querySelectorAll(".block-html img").forEach(img => {
      img.loading = "lazy";
      img.addEventListener("error", () => {
        const t = img.getAttribute("title") || db.byId.get(img.getAttribute("data-items"))?.name;
        if (t) {
          const span = document.createElement("span");
          span.className = "img-missing" + (img.classList.contains("ref") ? " ref" : "");
          span.textContent = t;
          const target = db.byId.get(img.getAttribute("data-items"));
          if (target) span.addEventListener("click", () => { location.hash = entryHref(target); });
          img.replaceWith(span);
        } else img.remove();
      }, { once: true });
    });
  }

  function closeDetail() {
    const { parts } = parseRoute();
    location.hash = href(parts);
  }

  // ---------- global search ----------

  let activeResult = -1;

  function renderSearch() {
    const q = norm(els.search.value);
    if (!q) { els.results.hidden = true; return; }
    const starts = [], contains = [], deep = [];
    for (const e of db.all) {
      if (e.search.startsWith(q)) starts.push(e);
      else if (e.search.includes(q)) contains.push(e);
      else if (e.searchFull.includes(q)) deep.push(e);
    }
    const found = [...starts, ...contains, ...deep];
    const shown = found.slice(0, 40);
    activeResult = shown.length ? 0 : -1;
    els.results.innerHTML = shown.length
      ? shown.map((e, i) => `<a class="sr ${i === 0 ? "active" : ""}" href="${entryHref(e)}">
          ${iconHtml(e, "ico-sm")}<span class="sr-name">${esc(e.name)}</span>
          <span class="sr-sec">${esc(db.sections[e.section].title)}</span></a>`).join("")
        + (found.length > shown.length ? `<div class="sr-more">…и ещё ${found.length - shown.length}</div>` : "")
      : `<div class="sr-more">Ничего не найдено</div>`;
    els.results.hidden = false;
  }

  function moveResult(delta) {
    const items = els.results.querySelectorAll(".sr");
    if (!items.length) return;
    activeResult = (activeResult + delta + items.length) % items.length;
    items.forEach((n, i) => n.classList.toggle("active", i === activeResult));
    items[activeResult].scrollIntoView({ block: "nearest" });
  }

  els.search.addEventListener("input", renderSearch);
  els.search.addEventListener("focus", renderSearch);
  els.search.addEventListener("keydown", ev => {
    if (ev.key === "ArrowDown") { ev.preventDefault(); moveResult(1); }
    else if (ev.key === "ArrowUp") { ev.preventDefault(); moveResult(-1); }
    else if (ev.key === "Enter") {
      const a = els.results.querySelectorAll(".sr")[activeResult];
      if (a) { location.hash = a.getAttribute("href"); els.results.hidden = true; els.search.blur(); }
    } else if (ev.key === "Escape") { els.results.hidden = true; els.search.blur(); }
  });
  els.results.addEventListener("click", ev => {
    if (ev.target.closest(".sr")) { els.results.hidden = true; els.search.value = ""; }
  });
  document.addEventListener("click", ev => {
    if (!ev.target.closest(".global-search")) els.results.hidden = true;
  });

  // ---------- global keys / chrome ----------

  document.addEventListener("keydown", ev => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName);
    if (ev.key === "/" && !typing) { ev.preventDefault(); els.search.focus(); return; }
    if (typing) return;
    if (ev.key === "Escape" && !els.detail.hidden) closeDetail();
    if (!els.detail.hidden && (ev.key === "ArrowLeft" || ev.key === "ArrowRight")) {
      const a = els.detail.querySelectorAll(".detail-bar a.icon-btn")[ev.key === "ArrowLeft" ? 0 : 1];
      if (a?.getAttribute("href")) location.hash = a.getAttribute("href");
    }
  });

  $("#menuBtn").addEventListener("click", () => {
    document.body.classList.toggle("nav-open");
    els.backdrop.hidden = !document.body.classList.contains("nav-open") && els.detail.hidden;
  });
  els.backdrop.addEventListener("click", () => {
    if (document.body.classList.contains("nav-open")) {
      document.body.classList.remove("nav-open");
      els.backdrop.hidden = els.detail.hidden;
    } else closeDetail();
  });

  const applyTheme = t => {
    if (t) document.documentElement.dataset.theme = t;
    else delete document.documentElement.dataset.theme;
  };
  applyTheme(store.get("theme", null));
  $("#themeBtn").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    const t = dark ? "light" : "dark";
    applyTheme(t);
    store.set("theme", t);
  });

  // ---------- boot ----------

  let lastListKey = null;
  function onRoute() {
    const route = parseRoute();
    document.body.classList.remove("nav-open");
    renderSidebar(route);
    const listKey = route.parts.join("/");
    // Перерисовываем список только при смене раздела, чтобы карточка открывалась без прыжков.
    if (listKey !== lastListKey) {
      renderMain(route);
      lastListKey = listKey;
    }
    renderDetail(route);
  }

  loadData().then(() => {
    window.addEventListener("hashchange", onRoute);
    onRoute();
  });
})();
