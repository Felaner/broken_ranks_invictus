(() => {
  "use strict";

  const SECTIONS = window.BR_CONFIG.sections;
  const $ = sel => document.querySelector(sel);
  const $$ = sel => document.querySelectorAll(sel);

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

  // Наборы id, которые хранятся в браузере: избранное, «есть у меня», сравнение.
  function idSet(key) {
    const set = new Set(store.get(key, []));
    return {
      has: id => set.has(id),
      get size() { return set.size; },
      values: () => [...set],
      toggle(id, limit) {
        if (set.has(id)) set.delete(id);
        else {
          if (limit && set.size >= limit) set.delete(set.values().next().value);
          set.add(id);
        }
        store.set(key, [...set]);
      },
      clear() { set.clear(); store.set(key, []); },
    };
  }
  const favorites = idSet("favorites");
  const marks = idSet("marks");
  const compare = idSet("compare");
  const notes = store.get("notes", {});
  const COMPARE_MAX = 4;

  // ---------- helpers ----------

  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const norm = s => String(s ?? "").toLowerCase().replace(/ё/g, "е").trim();
  const num = v => {
    const m = String(v ?? "").replace(/\s/g, "").replace(",", ".").match(/-?\d+(\.\d+)?/);
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

  // Значение поля может зависеть от сложности босса: {e, n, h}.
  const DIFFS = [["e", "Лёгкая"], ["n", "Нормальная"], ["h", "Тяжёлая"]];
  const isDiff = v => v && typeof v === "object";
  const fv = v => isDiff(v) ? (v[view.diff] ?? v.n ?? "") : v;
  const hasDiff = e => e.fields.some(([, v]) => isDiff(v));

  function iconHtml(entry, cls = "") {
    const letter = esc((entry.name || "?").trim().charAt(0).toUpperCase());
    if (!entry.icon) return `<div class="ico ico-empty ${cls}">${letter}</div>`;
    return `<div class="ico ${cls}"><img src="${esc(entry.icon)}" alt="" loading="lazy"
      onerror="this.parentNode.classList.add('ico-empty');this.parentNode.textContent='${letter}'"></div>`;
  }

  // ---------- data ----------

  const db = { sections: {}, all: [], byId: new Map(), byName: new Map(), demo: false,
               maps: [], mapById: new Map(), mapsOf: new Map() };

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
    await Promise.all([...SECTIONS.map(s => loadScript(`data/${s.id}.js`)), loadScript("data/maps.js")]);
    const hasReal = SECTIONS.some(s => window.BR_DATA[s.id]?.entries?.length);
    if (!hasReal) db.demo = await loadScript("data/demo.js");

    for (const sec of SECTIONS) {
      const raw = window.BR_DATA[sec.id] || {};
      const entries = (raw.entries || []).map((e, i) => normalizeEntry(e, sec.id, i));

      // Категории: сначала из конфига, затем из данных, затем встреченные в записях.
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
      // Раздел без настоящих категорий («НПС», «Навыки») показываем одним списком.
      if (cats.length === 1 && cats[0].id === "_") cats.length = 0;

      db.sections[sec.id] = { ...sec, categories: cats, entries, updated: raw.updated };
      for (const e of entries) {
        db.all.push(e);
        db.byId.set(e.id, e);
        const key = norm(e.name);
        if (!db.byName.has(key)) db.byName.set(key, e);
      }
    }

    db.maps = window.BR_MAPS || [];
    for (const m of db.maps) {
      db.mapById.set(m.id, m);
      for (const p of m.points) {
        if (!db.mapsOf.has(p.id)) db.mapsOf.set(p.id, []);
        if (!db.mapsOf.get(p.id).includes(m.id)) db.mapsOf.get(p.id).push(m.id);
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
      if (lf && !isNaN(num(fv(lf[1])))) level = num(lf[1]);
    }
    const name = e.name || "Без названия";
    const flatVals = fields.flatMap(([k, v]) => [k, ...(isDiff(v) ? Object.values(v) : [v])]);
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
      backrefs: Array.isArray(e.backrefs) ? e.backrefs : [],
      attacks: e.attacks || null,
      skillClass: e.skillClass || "",
      skillOrder: e.skillOrder ?? 99,
      skillReq: Array.isArray(e.skillReq) ? e.skillReq : null,
      namePL: e.namePL || "",
      lang: e.lang || "",
      image: e.image || "",
      nameEN: e.nameEN || "",
      sourceUrl: e.sourceUrl || "",
      search: norm([name, e.nameEN, e.namePL].filter(Boolean).join(" ")),
      searchFull: norm([name, e.nameEN, e.namePL, e.description, ...flatVals,
        ...(e.blocks || []).map(b => stripTags(b.html))].join(" ")),
    };
  }

  const fieldOf = (e, label) => e.fields.find(([k]) => k === label)?.[1];

  // ---------- routing ----------

  // #/                         — главная
  // #/s/<section>[/<category>] — раздел / категория
  // #/fav, #/marks, #/cmp      — избранное, отмеченное, сравнение
  // #/maps[/<mapId>]           — карты
  // ?e=<entryId>&hl=<entryId>  — открытая карточка / подсветка на карте
  function parseRoute() {
    const [path, query = ""] = location.hash.replace(/^#/, "").split("?");
    const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
    const params = new URLSearchParams(query);
    return { parts, entryId: params.get("e"), hl: params.get("hl"), b: params.get("b") };
  }

  function href(parts, entryId, extra = {}) {
    const p = "#/" + parts.map(encodeURIComponent).join("/");
    const q = new URLSearchParams();
    if (entryId) q.set("e", entryId);
    for (const [k, v] of Object.entries(extra)) if (v) q.set(k, v);
    const qs = q.toString();
    return qs ? `${p}?${qs}` : p;
  }

  const entryHref = e => href(["s", e.section, e.category], e.id);
  // Внутри карты, сравнения и т.п. карточка открывается поверх текущей страницы.
  const entryHrefHere = e => {
    const { parts } = parseRoute();
    return ["maps", "cmp", "fav", "marks"].includes(parts[0]) ? href(parts, e.id) : entryHref(e);
  };
  const mapHref = (mid, hl, e) => href(["maps", mid], e, { hl });

  // ---------- view state ----------

  const view = {
    query: "",
    sort: store.get("sort", "name"),
    sortDir: 1,
    mode: store.get("mode", "grid"),
    diff: store.get("diff", "n"),
    myLevel: store.get("myLevel", ""),
    onlyMine: false,
    lvlMin: "",
    lvlMax: "",
    facets: {},
    mark: "all",
    atk: "",
    mapZoom: 1,
    wide: store.get("wide", false),
    list: [],           // текущий отображаемый список (для навигации стрелками)
    routeKey: "",
  };

  function resetFilters() {
    view.query = "";
    view.lvlMin = view.lvlMax = "";
    view.facets = {};
    view.mark = "all";
    view.atk = "";
    view.onlyMine = false;
  }

  // Типы атак моба значками: ближние / дальние / ментальные.
  const ATK = [["b", "Ближние"], ["d", "Дальние"], ["m", "Ментальные"]];
  function atkHtml(e, cls = "") {
    if (!e.attacks) return "";
    return `<span class="atk ${cls}">${ATK.map(([k, n]) =>
      `<i class="atk-${k} ${e.attacks[k] ? "on" : "off"}" title="${n} атаки: ${e.attacks[k] ? "да" : "нет"}"></i>`).join("")}</span>`;
  }

  // Перерисовка с сохранением фокуса и курсора в поле ввода.
  function refresh() {
    const a = document.activeElement;
    const id = a && a.id && /^(INPUT|SELECT|TEXTAREA)$/.test(a.tagName) ? a.id : null;
    const pos = id && a.selectionStart != null ? a.selectionStart : null;
    const route = parseRoute();
    renderSidebar(route);
    renderMain(route);
    renderDetail(route);
    if (id) {
      const again = document.getElementById(id);
      if (again) {
        again.focus();
        if (pos != null && again.setSelectionRange) try { again.setSelectionRange(pos, pos); } catch { /* number */ }
      }
    }
  }

  // ---------- sidebar ----------

  function renderSidebar(route) {
    const [kind, secId, catId] = route.parts;
    const item = (active, link, ico, title, count) =>
      `<a class="nav-item ${active ? "active" : ""}" href="${link}"><span class="nav-ico">${ico}</span>${title}
        ${count != null ? `<span class="count">${count}</span>` : ""}</a>`;
    let html = `<div class="nav-group">`;
    html += item(!kind, "#/", "🏠", "Главная");
    html += item(kind === "fav", "#/fav", "⭐", "Избранное", favorites.size);
    html += item(kind === "marks", "#/marks", "✅", "Есть у меня", marks.size);
    html += item(kind === "cmp", "#/cmp", "⚖️", "Сравнение", compare.size);
    html += item(kind === "maps", "#/maps", "🗺️", "Карты", db.maps.length || null);
    html += item(kind === "build", "#/build", "🧥", "Переодевалка", Object.keys(build.items).length || null);
    html += item(kind === "s" && secId === "equipment" && catId === "kits", href(["s", "equipment", "kits"]), "🧩",
      "Комплекты", db.sections.equipment?.categories.find(c => c.id === "kits")?.count);
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
    html += `</div>
      <div class="side-note">Неофициальная фанатская вики. Не связана с Whitemoon Games.
        <a href="#/about" class="${kind === "about" ? "active" : ""}">О сайте</a>
        <a href="e/index.html">Все страницы списком</a>
        <div class="side-contact">Идеи и вопросы — в Telegram: ${TG}</div></div>`;
    els.sidebar.innerHTML = html;
  }

  // ---------- main views ----------

  const TG = `<a href="https://t.me/felaner" target="_blank" rel="noopener">@felaner</a>`;

  function renderHome() {
    let html = db.demo ? demoBanner() : "";
    html += `<h1 class="page-title">Broken Ranks Fandom Wiki</h1>
      <p class="page-sub">Личная база по игре: экипировка, питомцы, противники, предметы, НПС и навыки.</p>
      <div class="notice">Это <b>неофициальная</b> фанатская вики, сделанная игроками. Она не связана с разработчиком
        игры и не одобрена им. <a href="#/about">Подробнее</a><br>
        Есть идея, нашли ошибку или хотите что-то спросить — пишите в Telegram: ${TG}</div>
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
    if (db.maps.length) {
      html += `<div class="home-card">
        <a class="home-card-head" href="#/maps">
          <span class="home-ico">🗺️</span>
          <span><b>Карты</b><small>${db.maps.length} ${plural(db.maps.length, "локация", "локации", "локаций")}</small></span>
        </a>
        <span class="muted">Локации с порталами, НПС, предметами и противниками</span>
      </div>`;
    }
    html += `</div>`;
    els.main.innerHTML = html;
    view.list = [];
  }

  function demoBanner() {
    return `<div class="banner">Показаны <b>демо-данные</b> — настоящих данных ещё нет.
      Запусти <code>python scraper/build.py</code>, он создаст файлы в <code>data/</code>.</div>`;
  }

  // Поля, по которым можно фильтровать выпадающим списком.
  const FACETS = ["Редкость", "Требуемый класс", "Тип урона", "Тип", "Аспект", "Путь сложности", "Группа боссов"];

  function applyFilters(entries) {
    const q = norm(view.query);
    const min = num(view.lvlMin), max = num(view.lvlMax), mine = num(view.myLevel);
    return entries.filter(e => {
      if (q && !e.search.includes(q) && !e.searchFull.includes(q)) return false;
      if (!isNaN(min) && !(e.level >= min)) return false;
      if (!isNaN(max) && !(e.level <= max)) return false;
      if (view.onlyMine && !isNaN(mine) && e.level != null && e.level > mine) return false;
      for (const [label, val] of Object.entries(view.facets)) {
        if (val && String(fv(fieldOf(e, label)) ?? "") !== val) return false;
      }
      if (view.atk && !(e.attacks && e.attacks[view.atk])) return false;
      if (view.mark === "have" && !marks.has(e.id)) return false;
      if (view.mark === "no" && marks.has(e.id)) return false;
      return true;
    });
  }

  function sortList(list) {
    const dir = view.sortDir;
    const byName = (a, b) => a.name.localeCompare(b.name, "ru");
    if (view.sort === "name") list.sort((a, b) => dir * byName(a, b));
    else if (view.sort === "level") list.sort((a, b) => dir * ((a.level ?? 1e9) - (b.level ?? 1e9)) || byName(a, b));
    else if (view.sort.startsWith("f:")) {
      const label = view.sort.slice(2);
      list.sort((a, b) => {
        const va = fv(fieldOf(a, label)), vb = fv(fieldOf(b, label));
        if (va == null || va === "") return 1;
        if (vb == null || vb === "") return -1;
        const na = num(va), nb = num(vb);
        if (!isNaN(na) && !isNaN(nb) && na !== nb) return dir * (na - nb);
        return dir * String(va).localeCompare(String(vb), "ru");
      });
    }
    return list;
  }

  function diffSwitch(id) {
    return `<div class="seg diff-seg" id="${id}" title="Сложность босса">
      ${DIFFS.map(([k, n]) => `<button data-diff="${k}" class="${view.diff === k ? "active" : ""}">${n}</button>`).join("")}
    </div>`;
  }

  function renderList(title, subtitle, entries, opts = {}) {
    const list = sortList(applyFilters(entries));
    view.list = list;

    const hasLevels = entries.some(e => e.level != null);
    const anyDiff = entries.some(hasDiff);
    const facetOpts = FACETS.map(label => {
      const vals = [...new Set(entries.map(e => fieldOf(e, label)).filter(v => v != null && v !== "").map(v => String(fv(v))))];
      return vals.length >= 2 ? [label, vals.sort((a, b) => a.localeCompare(b, "ru"))] : null;
    }).filter(Boolean);
    const anyAtk = entries.some(e => e.attacks);
    const filtersActive = view.query || view.lvlMin || view.lvlMax || view.onlyMine || view.mark !== "all" || view.atk ||
      Object.values(view.facets).some(Boolean);

    let html = db.demo ? demoBanner() : "";
    html += `<div class="list-head">
      <div>
        <h1 class="page-title">${esc(title)}</h1>
        <p class="page-sub">${subtitle}</p>
      </div>
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
    <div class="filters">
      ${hasLevels ? `<label class="flt">Ур.
          <input id="lvlMin" type="number" min="0" placeholder="от" value="${esc(view.lvlMin)}">
          <input id="lvlMax" type="number" min="0" placeholder="до" value="${esc(view.lvlMax)}"></label>
        <label class="flt">Мой ур.
          <input id="myLevel" type="number" min="0" placeholder="—" value="${esc(view.myLevel)}"></label>
        <label class="flt chk"><input id="onlyMine" type="checkbox" ${view.onlyMine ? "checked" : ""}
          ${view.myLevel ? "" : "disabled"}> не выше моего</label>` : ""}
      ${facetOpts.map(([label, vals]) => `<select class="facet" data-facet="${esc(label)}" id="facet-${esc(label)}">
          <option value="">${esc(label)}: все</option>
          ${vals.map(v => `<option value="${esc(v)}" ${view.facets[label] === v ? "selected" : ""}>${esc(v)}</option>`).join("")}
        </select>`).join("")}
      ${anyAtk ? `<select id="atkSel" title="Тип атаки">
        <option value="">Атакует: любые</option>
        ${ATK.map(([k, n]) => `<option value="${k}" ${view.atk === k ? "selected" : ""}>${n.toLowerCase()}</option>`).join("")}
      </select>` : ""}
      <select id="markSel" title="Отметки">
        <option value="all" ${view.mark === "all" ? "selected" : ""}>Отметки: все</option>
        <option value="have" ${view.mark === "have" ? "selected" : ""}>✓ есть у меня</option>
        <option value="no" ${view.mark === "no" ? "selected" : ""}>✗ нет у меня</option>
      </select>
      ${anyDiff ? diffSwitch("diffList") : ""}
      ${filtersActive ? `<button class="link-btn" id="resetFlt">Сбросить фильтры</button>` : ""}
    </div>
    <div class="result-count">${list.length !== entries.length ? `Найдено: ${list.length} из ${entries.length}` : countLabel(list.length)}</div>`;

    if (!list.length) {
      html += `<div class="empty">${entries.length ? "Ничего не найдено" : (opts.empty || "Здесь пока пусто")}</div>`;
    } else if (view.mode === "table") {
      html += renderTable(list, opts.showSection);
    } else {
      html += `<div class="grid">${list.map(e => renderCard(e, opts.showSection)).join("")}</div>`;
    }

    els.main.innerHTML = html;
    bindToolbar();
  }

  // В карточке — только редкость, цена и требуемый класс (если он есть).
  const TIP_SKIP = /^(тип|улучшения|атаки|зоны атаки|шанс дропа|группа боссов)/i;
  const PREVIEW = [/^редкость$/i, /^(цена|стоимость)$/i, /^требуемый класс$/i];

  function renderCard(e, showSection) {
    const sec = db.sections[e.section];
    const cat = sec.categories.find(c => c.id === e.category);
    const preview = PREVIEW.map(rx => e.fields.find(([k, v]) => rx.test(k) && !/^(0|-|)$/.test(String(fv(v)).trim())))
      .filter(Boolean);
    const lvl = fv(fieldOf(e, "Уровень")) || e.level;
    return `<a class="card ${favorites.has(e.id) ? "fav" : ""} ${marks.has(e.id) ? "have" : ""}"
        href="${entryHrefHere(e)}" data-id="${esc(e.id)}">
      ${iconHtml(e)}
      <div class="card-body">
        <div class="card-name">${esc(e.name)}</div>
        <div class="card-meta">
          ${lvl != null && lvl !== "" ? `<span class="lvl">ур. ${esc(lvl)}</span>` : ""}
          <span>${showSection ? esc(sec.title) + " · " : ""}${esc(cat?.name || "")}</span>
          ${atkHtml(e, "atk-sm")}
        </div>
        ${preview.length ? `<div class="card-fields">${preview.map(([k, v]) =>
          `<span><em>${esc(k)}:</em> ${esc(fv(v))}</span>`).join("")}</div>` : ""}
      </div>
    </a>`;
  }

  function renderTable(list, showSection) {
    const freq = new Map();
    for (const e of list) for (const [k] of e.fields) freq.set(k, (freq.get(k) || 0) + 1);
    // Колонки с одинаковым у всех значением ничего не дают для сравнения.
    const varies = k => list.length < 2 || new Set(list.map(e => String(fv(fieldOf(e, k)) ?? ""))).size > 1;
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
      html += `<tr data-href="${esc(entryHrefHere(e))}" class="${marks.has(e.id) ? "have" : ""}">
        <td class="tname"><a href="${entryHrefHere(e)}">${iconHtml(e, "ico-sm")}<span>${esc(e.name)}</span></a></td>
        ${showSection ? `<td>${esc(db.sections[e.section].title)}</td>` : ""}
        ${hasLevels ? `<td class="num">${esc(fv(fieldOf(e, "Уровень")) || (e.level ?? ""))}</td>` : ""}
        ${cols.map(c => `<td>${esc(fv(fieldOf(e, c)) ?? "")}</td>`).join("")}
      </tr>`;
    }
    html += `</tbody></table></div>`;
    return html;
  }

  function bindToolbar() {
    const on = (sel, ev, fn) => $(sel)?.addEventListener(ev, fn);
    on("#localSearch", "input", ev => { view.query = ev.target.value; refresh(); });
    on("#sortSel", "change", ev => { view.sort = ev.target.value; store.set("sort", view.sort); refresh(); });
    on("#dirBtn", "click", () => { view.sortDir *= -1; refresh(); });
    on("#lvlMin", "input", ev => { view.lvlMin = ev.target.value; refresh(); });
    on("#lvlMax", "input", ev => { view.lvlMax = ev.target.value; refresh(); });
    on("#myLevel", "input", ev => {
      view.myLevel = ev.target.value;
      store.set("myLevel", view.myLevel);
      if (view.myLevel && !view.onlyMine) view.onlyMine = true;
      refresh();
    });
    on("#onlyMine", "change", ev => { view.onlyMine = ev.target.checked; refresh(); });
    on("#markSel", "change", ev => { view.mark = ev.target.value; refresh(); });
    on("#atkSel", "change", ev => { view.atk = ev.target.value; refresh(); });
    on("#resetFlt", "click", () => { resetFilters(); refresh(); });
    $$(".facet").forEach(s => s.addEventListener("change", () => { view.facets[s.dataset.facet] = s.value; refresh(); }));
    $$(".main .seg:not(.diff-seg) button").forEach(b => b.addEventListener("click", () => {
      view.mode = b.dataset.mode;
      store.set("mode", view.mode);
      refresh();
    }));
    bindDiff(els.main);
    $$("th.sortable").forEach(th => th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (view.sort === key) view.sortDir *= -1;
      else { view.sort = key; view.sortDir = 1; }
      refresh();
    }));
    $$("tr[data-href]").forEach(tr => tr.addEventListener("click", ev => {
      if (ev.target.closest("a")) return;
      location.hash = tr.dataset.href;
    }));
  }

  function bindDiff(root) {
    root.querySelectorAll(".diff-seg button").forEach(b => b.addEventListener("click", () => {
      view.diff = b.dataset.diff;
      store.set("diff", view.diff);
      refresh();
    }));
  }

  // ---------- about ----------

  function renderAbout() {
    view.list = [];
    els.main.innerHTML = `<div class="about">
      <h1 class="page-title">О сайте</h1>
      <p>Это <b>неофициальная фанатская вики</b> по игре Broken Ranks, созданная игроками для собственного удобства
        и помощи другим игрокам.</p>
      <h3>Отношение к разработчику</h3>
      <p>Сайт не связан с компанией Whitemoon Games (разработчик и издатель Broken Ranks), не одобрен, не спонсирован
        и не поддерживается ею. Мнения и сведения на сайте не являются официальной позицией разработчика.</p>
      <p>Слово «Fandom» в названии означает «фанатская» вики. Сайт не связан с платформой Fandom (Fandom, Inc.)
        и не размещён на ней.</p>
      <h3>Права на материалы</h3>
      <p>Broken Ranks, названия, логотипы, изображения, тексты и другие игровые материалы являются собственностью
        их правообладателей. Они используются здесь исключительно в информационных, некоммерческих целях —
        для справки об игре.</p>
      <h3>Некоммерческий характер</h3>
      <p>Сайт бесплатный, не содержит рекламы, ничего не продаёт и не собирает персональные данные. Избранное,
        отметки и заметки хранятся только в вашем браузере и никуда не отправляются.</p>
      <h3>Точность информации</h3>
      <p>Сведения собраны из общедоступных источников и могут быть неполными, неточными или устаревшими.
        Актуальную информацию смотрите в самой игре и на официальных ресурсах разработчика. Сайт не несёт
        ответственности за решения, принятые на основе его материалов.</p>
      <h3>Связь</h3>
      <p>Идеи, вопросы, найденные ошибки — пишите в Telegram: ${TG}</p>
      <h3>Для правообладателей</h3>
      <p>Если вы правообладатель и считаете, что какой-либо материал размещён неправомерно, сообщите об этом —
        он будет оперативно исправлен или удалён: Telegram ${TG} или
        <a href="https://github.com/Felaner/felaner.github.io/issues" target="_blank" rel="noopener">GitHub</a>.</p>
    </div>`;
  }

  // ---------- compare ----------

  // Для этих характеристик меньшее значение лучше.
  const LOWER_BETTER = /^(требуем|цена|стоимость|ремонт|вес)/i;

  function renderCompare() {
    const items = compare.values().map(id => db.byId.get(id)).filter(Boolean);
    view.list = items;
    let html = `<div class="list-head"><div>
        <h1 class="page-title">Сравнение</h1>
        <p class="page-sub">Добавляй записи кнопкой ⚖ в карточке (до ${COMPARE_MAX})</p>
      </div>
      ${items.length ? `<button class="link-btn" id="cmpClear">Очистить</button>` : ""}
    </div>`;
    if (!items.length) {
      els.main.innerHTML = html + `<div class="empty">Пока ничего не выбрано</div>`;
      $("#cmpClear")?.addEventListener("click", () => { compare.clear(); refresh(); });
      return;
    }
    const labels = [];
    for (const e of items) for (const [k] of e.fields) if (!labels.includes(k)) labels.push(k);
    const anyDiff = items.some(hasDiff);
    html += anyDiff ? `<div class="filters">${diffSwitch("diffCmp")}</div>` : "";
    html += `<div class="table-wrap"><table class="tbl cmp"><thead><tr><th></th>
      ${items.map(e => `<th><div class="cmp-head">
          <a href="${href(["cmp"], e.id)}">${iconHtml(e, "ico-sm")}<span>${esc(e.name)}</span></a>
          <button class="x" data-rm="${esc(e.id)}" title="Убрать">✕</button>
        </div><small>${esc(db.sections[e.section].title)}</small></th>`).join("")}
    </tr></thead><tbody>`;
    for (const label of labels) {
      const vals = items.map(e => fv(fieldOf(e, label)));
      const nums = vals.map(v => (v == null || v === "" ? NaN : num(v)));
      const valid = nums.filter(n => !isNaN(n));
      const differ = new Set(vals.map(v => String(v ?? ""))).size > 1;
      let best = null;
      if (differ && valid.length >= 2) best = LOWER_BETTER.test(label) ? Math.min(...valid) : Math.max(...valid);
      html += `<tr class="${differ ? "differ" : ""}"><th>${esc(label)}</th>
        ${vals.map((v, i) => `<td class="${best != null && nums[i] === best ? "best" : ""}">${esc(v ?? "—")}</td>`).join("")}
      </tr>`;
    }
    html += `</tbody></table></div>`;
    els.main.innerHTML = html;
    $("#cmpClear")?.addEventListener("click", () => { compare.clear(); refresh(); });
    $$("[data-rm]").forEach(b => b.addEventListener("click", ev => {
      ev.preventDefault();
      compare.toggle(b.dataset.rm);
      refresh();
    }));
    bindDiff(els.main);
  }

  // ---------- maps ----------

  function renderMapsList() {
    const q = norm(view.query);
    const list = db.maps.filter(m => !q || norm(m.name).includes(q) ||
      m.points.some(p => norm(db.byId.get(p.id)?.name).includes(q)));
    view.list = [];
    let html = `<div class="list-head"><div>
        <h1 class="page-title">Карты</h1>
        <p class="page-sub">Поиск по названию локации или по тому, что на ней находится</p>
      </div></div>
      <div class="toolbar"><input class="local-search" id="localSearch" type="search"
        placeholder="Локация, НПС, предмет…" value="${esc(view.query)}" autocomplete="off"></div>
      <div class="result-count">${list.length} ${plural(list.length, "локация", "локации", "локаций")}</div>`;
    if (!db.maps.length) html += `<div class="empty">Данных карт нет — запусти <code>python scraper/build.py</code></div>`;
    html += `<div class="map-grid">${list.map(m => `<a class="map-card" href="${mapHref(m.id)}">
        <div class="map-thumb">${m.image ? `<img src="${esc(m.image)}" alt="" loading="lazy" onerror="this.remove()">` : ""}</div>
        <div class="map-card-body"><b>${esc(m.name)}</b>
          <small>${m.points.length ? `${m.points.length} ${plural(m.points.length, "объект", "объекта", "объектов")} · ` : ""}${m.portals.length} ${plural(m.portals.length, "переход", "перехода", "переходов")}</small>
        </div></a>`).join("")}</div>`;
    els.main.innerHTML = html;
    $("#localSearch")?.addEventListener("input", ev => { view.query = ev.target.value; refresh(); });
  }

  function renderMap(mid, hl) {
    const m = db.mapById.get(mid);
    if (!m) { els.main.innerHTML = `<div class="empty">Карта не найдена</div>`; return; }
    const pts = m.points.map(p => ({ ...p, e: db.byId.get(p.id) })).filter(p => p.e);
    view.list = [...new Map(pts.map(p => [p.e.id, p.e])).values()];
    const z = view.mapZoom;
    let html = `<div class="list-head"><div>
        <h1 class="page-title">${esc(m.name)}</h1>
        <p class="page-sub"><a href="#/maps">Карты</a> / ${esc(m.name)}</p>
      </div>
      <div class="zoom">
        <button class="icon-btn" data-zoom="-1" title="Уменьшить">−</button>
        <span>${Math.round(z * 100)}%</span>
        <button class="icon-btn" data-zoom="1" title="Увеличить">+</button>
      </div></div>
      <div class="map-wrap"><div class="map-canvas ${m.image ? "" : "noimg"}" style="width:${z * 100}%">
        ${m.image ? `<img class="map-img" src="${esc(m.image)}" alt=""
          onerror="this.parentNode.classList.add('noimg');this.remove()">` : ""}
        ${m.portals.map(p => `<a class="marker portal" href="${mapHref(p.to)}" style="left:${p.x}%;top:${p.y}%"
            title="→ ${esc(p.name)}"><span>➜</span><em>${esc(p.name)}</em></a>`).join("")}
        ${pts.map(p => `<a class="marker point ${p.id === hl ? "hl" : ""}" data-items="${esc(p.id)}"
            href="${mapHref(mid, hl, p.id)}" style="left:${p.x}%;top:${p.y}%">${iconHtml(p.e, "ico-sm")}</a>`).join("")}
      </div></div>`;
    if (hl && !pts.some(p => p.id === hl)) {
      const elsewhere = (db.mapsOf.get(hl) || []).filter(x => x !== mid);
      const name = db.byId.get(hl)?.name || hl;
      html += `<p class="muted small">«${esc(name)}» на этой карте точкой не отмечен${elsewhere.length
        ? ` — он есть на: ${elsewhere.map(x => `<a href="${mapHref(x, hl, hl)}">${esc(db.mapById.get(x)?.name || x)}</a>`).join(", ")}`
        : " (точное место на карте не отмечено)"}.</p>`;
    }
    if (m.portals.length) {
      html += `<div class="block"><h3>Переходы</h3><div class="chips">${[...new Map(m.portals.map(p => [p.to, p])).values()]
        .map(p => `<a class="chip" href="${mapHref(p.to)}">→ ${esc(p.name)}</a>`).join("")}</div></div>`;
    }
    if (pts.length) {
      html += `<div class="block"><h3>На карте</h3><div class="brefs">${view.list.map(e =>
        `<a class="bref ${e.id === hl ? "hl" : ""}" href="${mapHref(mid, hl, e.id)}" data-items="${esc(e.id)}">
          ${iconHtml(e, "ico-sm")}<span>${esc(e.name)}</span></a>`).join("")}</div></div>`;
    }
    els.main.innerHTML = html;
    $$("[data-zoom]").forEach(b => b.addEventListener("click", () => {
      view.mapZoom = Math.min(4, Math.max(1, view.mapZoom + Number(b.dataset.zoom) * 0.5));
      refresh();
    }));
    const hlNode = els.main.querySelector(".marker.hl");
    if (hlNode) setTimeout(() => hlNode.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" }), 50);
  }

  // ---------- переодевалка ----------

  const WEAPON_CATS = ["axe", "axe_th", "sword", "sword_th", "hammer", "hammer_th", "knuckles", "stick", "bow", "epic", "sets"];
  const SLOTS = [
    { id: "helmet", name: "Шлем", cats: ["helmets"] },
    { id: "amulet", name: "Амулет", cats: ["amulets"] },
    { id: "gloves", name: "Перчатки / наручи", cats: ["gloves", "bracers"] },
    { id: "ring1", name: "Кольцо", cats: ["rings"] },
    { id: "ring2", name: "Кольцо", cats: ["rings"] },
    { id: "offhand", name: "Щит", cats: ["shield", "sets"] },
    { id: "boots", name: "Сапоги", cats: ["boots"] },
    { id: "weapon", name: "Оружие", cats: WEAPON_CATS },
    { id: "pants", name: "Штаны", cats: ["pants"] },
    { id: "belt", name: "Пояс", cats: ["belts"] },
    { id: "armor", name: "Броня", cats: ["armors"] },
    { id: "cape", name: "Плащ", cats: ["capes"] },
  ];
  const BASE_STATS = [["Здоровье", "hp", "❤"], ["Мана", "mana", "✷"], ["Выносливость", "stam", "🏃"],
    ["Сила", "sila", "💪"], ["Ловкость", "lov", "✋"], ["Мощь", "mosh", "🌀"], ["Знание", "zn", "📖"], ["Интеллект", "int", "🧠"]];
  const RESISTS = [["Сопр. рубящим", "Рубящие"], ["Сопр. дробящим", "Дробящие"], ["Сопр. колющим", "Колющие"],
    ["Сопр. огню", "Огонь"], ["Сопр. холоду", "Холод"], ["Сопр. энергии", "Энергия"], ["Сопр. менталу", "Ментал"]];
  const REQS = [["Требуемая сила", "Сила"], ["Требуемая ловкость", "Ловкость"], ["Требуемая мощь", "Мощь"], ["Требуемое знание", "Знание"]];
  const CLASS_NAMES = ["Варвар", "Вуду", "Друид", "Лучник", "Огненный маг", "Рыцарь", "Шид"];
  // Доля бонуса комплекта от числа надетых частей (по статье «Сеты»).
  const SET_SHARE = { 3: [0, 0, 0.4, 1], 4: [0, 0, 0.25, 0.5, 1], 5: [0, 0, 0.2, 0.4, 0.6, 1] };

  // Модификаторы в процентах и их базовые значения (из окна игры: крит 2%, восстановление ресурсов 5%).
  const PCT_MOD = /^(Шанс|Восстановление|Модификатор|Уменьшение|Получаемый|Расход|Вытягивание|Дополнительный урон)/i;
  const MOD_BASE = { "Шанс критического удара": 2, "Восстановление маны": 5, "Восстановление выносливости": 5 };

  // Очки развития характеристик: старт 210 здоровья/маны/выносливости и по 10 остальных;
  // 1 очко = +10 здоровья/маны/выносливости или +1 к остальным. За уровни 2…L по 4 очка и 2 стартовых
  // (сверено с персонажем 26 уровня: вложено 102 очка, свободных 0).
  const STAT_START = { hp: 210, mana: 210, stam: 210, sila: 10, lov: 10, mosh: 10, zn: 10, int: 10 };
  const STAT_STEP = { hp: 10, mana: 10, stam: 10 };
  const statPointsTotal = lvl => 4 * (Math.max(1, lvl) - 1) + 2;
  const statPointsSpent = () => Object.entries(STAT_START).reduce((s, [k, v]) =>
    s + Math.max(0, (num(build.base[k]) || v) - v) / (STAT_STEP[k] || 1), 0);

  const emptyBuild = () => ({ cls: "", lvl: 1, base: { ...STAT_START }, items: {}, skills: {} });
  let build = Object.assign(emptyBuild(), store.get("build", {}));
  build.skills = build.skills || {};
  if (build.items.bracers) { build.items.gloves = build.items.gloves || build.items.bracers; delete build.items.bracers; }
  const saveBuild = () => store.set("build", build);

  const fnum = (e, label) => {
    const v = num(fv(fieldOf(e, label)));
    return isNaN(v) ? 0 : v;
  };
  const itemType = e => String(fv(fieldOf(e, "Тип")) || "");
  const isShield = e => /щит/i.test(itemType(e));
  const isTwoHanded = e => /двуручн|лук/i.test(itemType(e)) || /_th$|^bow$/.test(e.category);
  function fitsSlot(e, slot) {
    if (e.section !== "equipment" || !slot.cats.includes(e.category)) return false;
    if (e.category === "sets") return slot.id === "offhand" ? isShield(e) : !isShield(e);
    return true;
  }
  const slotFor = e => SLOTS.find(s => fitsSlot(e, s) && (s.id !== "ring1" || !build.items.ring1)) ||
    SLOTS.find(s => fitsSlot(e, s));

  // Снижение урона от очков сопротивления. Подобрано по игре: 41 → 35,5%, 80 → 52,5%, 82 → 53,25%.
  // Выше 82 очков формула не проверена — показываем «≈».
  function resistPct(p) {
    let left = Math.max(0, p), pct = 0;
    for (const [len, k] of [[20, 1], [20, 0.75], [20, 0.5], [Infinity, 0.375]]) {
      const d = Math.min(left, len);
      pct += d * k;
      left -= d;
      if (!left) break;
    }
    return Math.min(pct, 100);
  }

  function parseMods(html) {
    const out = [];
    for (const line of stripTags(String(html || "").replace(/<br\s*\/?>/gi, "\n")).split("\n")) {
      const m = line.trim().match(/^(.+?)\s*([+-]\s*[\d.,]+)\s*(%?)$/);
      if (m) out.push([m[1].trim(), num(m[2].replace(/\s/g, "")), m[3]]);
    }
    return out;
  }

  function computeBuild() {
    const items = SLOTS.map(s => [s, db.byId.get(build.items[s.id])]).filter(([, e]) => e);
    const total = {}, fromItems = {}, mods = new Map(), res = {};
    for (const [label, key] of BASE_STATS) total[label] = num(build.base[key]) || STAT_START[key] || 0;
    const addMod = (name, val, pct, k = 1) => {
      if (!pct && name in total) {
        // Характеристики игра округляет вниз (Сила +8 × 40% = +3), проценты — нет.
        const v = Math.floor(val * k);
        total[name] += v;
        fromItems[name] = (fromItems[name] || 0) + v;
        return;
      }
      const key = name + (pct || PCT_MOD.test(name) ? " %" : "");
      mods.set(key, (mods.get(key) || 0) + val * k);
    };
    for (const [name, v] of Object.entries(MOD_BASE)) mods.set(name + " %", v);
    for (const [label] of RESISTS) res[label] = 0;
    let weaponDmg = 0;
    for (const [slot, e] of items) {
      for (const [label] of BASE_STATS) {
        const v = fnum(e, label);
        total[label] += v;
        if (v) fromItems[label] = (fromItems[label] || 0) + v;
      }
      for (const [label] of RESISTS) res[label] += fnum(e, label);
      if (slot.id === "weapon") weaponDmg = fnum(e, "Урон");
      // У частей комплекта блок «Модификаторы» — это бонус всего комплекта, он считается ниже.
      const inKit = e.blocks.some(b => b.title === "Комплект");
      if (!inKit) for (const b of e.blocks) if (b.title === "Модификаторы") for (const [n, v, p] of parseMods(b.html)) addMod(n, v, p);
    }
    // Комплекты.
    const equippedIds = new Set(items.map(([, e]) => e.id));
    const sets = [];
    for (const kit of db.sections.equipment?.entries.filter(e => e.category === "kits") || []) {
      const partsBlock = kit.blocks.find(b => b.title === "Части комплекта");
      const parts = partsBlock ? [...new Set([...partsBlock.html.matchAll(/data-items="([^"]+)"/g)].map(m => m[1]))] : [];
      const have = parts.filter(id => equippedIds.has(id)).length;
      if (!have) continue;
      const share = (SET_SHARE[parts.length] || [])[have] ?? (have === parts.length ? 1 : 0);
      const bonus = kit.blocks.find(b => b.title === "Бонус комплекта" || b.title === "Модификаторы");
      const list = bonus ? parseMods(bonus.html) : [];
      if (share) for (const [n, v, p] of list) addMod(n, v, p, share);
      sets.push({ kit, have, total: parts.length, share, list });
    }
    // Требования.
    const problems = [];
    for (const [slot, e] of items) {
      const lvl = fnum(e, "Требуемый уровень");
      if (lvl > (num(build.lvl) || 0)) problems.push([slot, e, `нужен ${lvl} уровень`]);
      const cls = fv(fieldOf(e, "Требуемый класс"));
      if (cls && build.cls && cls !== build.cls) problems.push([slot, e, `только для класса «${cls}»`]);
      for (const [rl, stat] of REQS) {
        const need = fnum(e, rl);
        if (need > total[stat]) problems.push([slot, e, `нужно ${stat.toLowerCase()} ${need} (сейчас ${Math.floor(total[stat])})`]);
      }
    }
    const w = items.find(([s]) => s.id === "weapon")?.[1];
    if (w && isTwoHanded(w) && build.items.offhand) problems.push([SLOTS.find(s => s.id === "offhand"),
      db.byId.get(build.items.offhand), "двуручное оружие занимает обе руки"]);
    // Power (по статье «Сила (PvE)»), без бонусов психо и орбов.
    const lvl = num(build.lvl) || 0;
    const power = Math.round(
      (total["Сила"] + total["Ловкость"] + total["Мощь"] + total["Знание"] + total["Интеллект"]) + 2 * weaponDmg +
      (total["Здоровье"] + total["Выносливость"] + total["Мана"]) / 10 +
      0.4 * (res["Сопр. рубящим"] + res["Сопр. дробящим"] + res["Сопр. колющим"]) +
      0.3 * (res["Сопр. огню"] + res["Сопр. холоду"] + res["Сопр. энергии"]) + 0.6 * res["Сопр. менталу"] +
      lvl * (lvl + 1) / 8);
    return { items, total, fromItems, res, mods, sets, problems, power, weaponDmg };
  }

  const fmtN = v => {
    const r = Math.round(v * 100) / 100;
    return Math.abs(r) >= 10000 ? r.toLocaleString("ru-RU") : String(r).replace(".", ",");
  };

  function buildLink() {
    const data = { c: build.cls, l: build.lvl, b: build.base, i: build.items, s: build.skills };
    const b64 = btoa(unescape(encodeURIComponent(JSON.stringify(data)))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    return location.href.split("#")[0] + "#/build?b=" + b64;
  }
  function importBuild(b64) {
    try {
      const s = decodeURIComponent(escape(atob(b64.replace(/-/g, "+").replace(/_/g, "/"))));
      const d = JSON.parse(s);
      build = { cls: d.c || "", lvl: d.l || 1, base: d.b || {}, items: d.i || {}, skills: d.s || {} };
      saveBuild();
    } catch { /* битая ссылка — оставляем текущую сборку */ }
  }

  const bon = (sel, ev, fn) => $(sel)?.addEventListener(ev, fn);

  // ----- навыки: очки ученика / адепта / мастера -----
  // Очки ученика к уровню L: за каждый новый уровень столько очков, какой это уровень (2 + 3 + … + L).
  // Особые навыки изначально стоят на 1 уровне бесплатно. Сверено с персонажем 26 уровня: 350 очков.
  // 14 очков ученика = 1 очко адепта, 14 адепта = 1 мастера. Уровень N внутри ступени стоит N очков этой ступени.
  const TIERS = [["ученик", "t1"], ["адепт", "t2"], ["мастер", "t3"]];
  const skillPointsTotal = lvl => Math.max(0, lvl * (lvl + 1) / 2 - 1);
  const isSpecial = e => e.skillClass === "Особые";
  const minLevel = e => isSpecial(e) ? 1 : 0;
  const skillLevel = e => Math.max(minLevel(e), build.skills[e.id] || 0);
  const skillSpent = e => skillCost(skillLevel(e)) - skillCost(minLevel(e));
  const levelCost = j => ((j - 1) % 7 + 1) * 14 ** Math.floor((j - 1) / 7);
  const skillCost = lv => { let c = 0; for (let j = 1; j <= lv; j++) c += levelCost(j); return c; };
  const splitPoints = p => [p % 14, Math.floor(p / 14) % 14, Math.floor(p / 196)];
  const skillLevelLabel = lv => lv ? `${(lv - 1) % 7 + 1}` : "0";
  const tierOf = lv => lv ? TIERS[Math.min(2, Math.floor((lv - 1) / 7))][1] : "t0";
  // Значок ступени как в игре: три кружка треугольником, нужный закрашен цветом ступени.
  function tierIcon(i) {
    const pts = [[4, 13], [9, 4], [14, 13]]; // ученик — левый нижний, адепт — верхний, мастер — правый нижний
    const on = [0, 1, 2][i];
    return `<svg class="sp-ico" viewBox="0 0 18 17" aria-hidden="true">
      <path d="M4 13 L9 4 L14 13" fill="none" stroke="currentColor" stroke-opacity=".35" stroke-width="1.2"/>
      ${pts.map(([x, y], k) => `<circle cx="${x}" cy="${y}" r="3.2" ${k === on
        ? 'fill="var(--sp-c)" stroke="var(--sp-c)"' : 'fill="var(--panel)" stroke="currentColor" stroke-opacity=".7"'} stroke-width="1.4"/>`).join("")}
    </svg>`;
  }
  const pointsHtml = (p, compact) => {
    const parts = splitPoints(p).map((n, i) => [n, i]).filter(([n], i) => !compact || n || (p === 0 && i === 0));
    return parts.map(([n, i]) => `<span class="sp ${TIERS[i][1]}" title="Очки: ${TIERS[i][0]}">${tierIcon(i)}<b>${n}</b></span>`).join("");
  };
  function classSkills() {
    return db.sections.skills.entries.filter(e => e.skillReq && (e.skillClass === build.cls || e.skillClass === "Особые"))
      .sort((a, b) => (a.skillClass === "Особые") - (b.skillClass === "Особые") || a.skillOrder - b.skillOrder);
  }
  function skillsState() {
    const lvl = num(build.lvl) || 1;
    const list = classSkills();
    const spent = list.reduce((s, e) => s + skillSpent(e), 0);
    return { lvl, list, total: skillPointsTotal(lvl), spent, free: skillPointsTotal(lvl) - spent };
  }
  function renderSkills() {
    if (!build.cls) return `<p class="muted">Выберите класс, чтобы распределить очки навыков.</p>`;
    const st = skillsState();
    const row = e => {
      const lv = skillLevel(e);
      const nextReq = e.skillReq[lv], nextCost = levelCost(lv + 1);
      const canUp = lv < e.skillReq.length && nextReq <= st.lvl && nextCost <= st.free;
      const why = lv >= e.skillReq.length ? "максимум" : nextReq > st.lvl ? `нужен ${nextReq} ур.` : nextCost > st.free ? "не хватает очков" : "";
      return `<div class="sk-row">
        <img class="sk-ico" src="${esc(e.icon)}" alt="" data-items="${esc(e.id)}">
        <div class="sk-main"><a href="${entryHref(e)}">${esc(e.name)}</a>
          <small>${lv < e.skillReq.length ? `след.: ${nextReq} ур., ${pointsHtml(nextCost, true)}` : "максимальный уровень"}${why && lv < e.skillReq.length ? ` · <em>${why}</em>` : ""}</small></div>
        <button class="btn sk-btn" data-sk="${esc(e.id)}" data-d="-1" ${lv > minLevel(e) ? "" : "disabled"}>−</button>
        <span class="sk-lv ${tierOf(lv)}">${skillLevelLabel(lv)}</span>
        <button class="btn sk-btn" data-sk="${esc(e.id)}" data-d="1" ${canUp ? "" : "disabled"} title="${esc(why)}">+</button>
      </div>`;
    };
    const cls = st.list.filter(e => e.skillClass !== "Особые"), spec = st.list.filter(e => e.skillClass === "Особые");
    return `<div class="sk-head">
        <span>Свободные очки: ${pointsHtml(Math.max(0, st.free))}</span>
        <span class="muted small">всего на ${st.lvl} уровне: ${pointsHtml(st.total, true)} · вложено: ${pointsHtml(st.spent, true)}</span>
        <button class="btn" id="skReset">Сбросить навыки</button>
      </div>
      ${st.free < 0 ? `<div class="b-warn">Вложено больше, чем доступно на ${st.lvl} уровне — снизьте навыки или поднимите уровень.</div>` : ""}
      <div class="sk-cols"><div><h4>Классовые</h4>${cls.map(row).join("")}</div>
        <div><h4>Особые</h4>${spec.map(row).join("")}</div></div>
      <p class="muted small">Очки ученика (жёлтые): за каждый уровень персонажа L — L очков (к 26 уровню всего 350).
        14 очков ученика = 1 очко адепта (оранжевые), 14 адепта = 1 мастера (красные). Уровень навыка 1–7 стоит 1–7 очков своей ступени. Особые навыки изначально на 1 уровне бесплатно.</p>`;
  }

  function renderBuild(route) {
    if (route.b) {
      importBuild(route.b);
      history.replaceState(null, "", "#/build");
    }
    const r = computeBuild();
    const bad = new Set(r.problems.map(([s]) => s.id));
    const n = SLOTS.length;
    const slotHtml = SLOTS.map((s, i) => {
      const a = (i / n) * 2 * Math.PI - Math.PI / 2;
      const x = 50 + 42 * Math.cos(a), y = 50 + 42 * Math.sin(a);
      const e = db.byId.get(build.items[s.id]);
      const blocked = s.id === "offhand" && (() => { const w = db.byId.get(build.items.weapon); return w && isTwoHanded(w); })();
      return `<button class="doll-slot ${e ? "filled" : ""} ${bad.has(s.id) ? "bad" : ""} ${blocked && !e ? "blocked" : ""}"
          style="left:${x}%;top:${y}%" data-slot="${s.id}" ${e ? `data-items="${esc(e.id)}"` : ""}
          title="${esc(e ? e.name : s.name + (blocked ? " — занято двуручным оружием" : ""))}">
        ${e ? `<img src="${esc(e.icon)}" alt="">` : `<span>${esc(s.name)}</span>`}
        ${e ? `<i class="doll-x" data-unequip="${s.id}" title="Снять">×</i>` : ""}
      </button>`;
    }).join("");

    const statRows = BASE_STATS.map(([label, key, ico]) => `<tr>
        <th><span class="st-ico">${ico}</span>${label}</th>
        <td class="b-base"><button class="st-btn" data-st="${key}" data-d="-1" title="−1 очко">−</button><input class="b-in" type="number"
          min="${STAT_START[key]}" step="${STAT_STEP[key] || 1}" data-base="${key}" value="${esc(build.base[key] ?? STAT_START[key])}"
          placeholder="${STAT_START[key]}"><button class="st-btn" data-st="${key}" data-d="1" title="+1 очко">+</button></td>
        <td class="sum">${fmtN(r.total[label])}</td>
        <td class="plus">${r.fromItems[label] ? "+" + fmtN(r.fromItems[label]) : ""}</td></tr>`).join("");
    const resRows = RESISTS.map(([label, name]) => {
      const p = r.res[label], pct = resistPct(p);
      return `<tr><th>${name}</th><td class="sum">${fmtN(p)}</td>
        <td><div class="res-bar"><i style="width:${Math.min(100, pct)}%"></i></div></td>
        <td class="pct">${p > 82 ? "≈" : ""}${fmtN(Math.round(pct * 100) / 100)}%</td></tr>`;
    }).join("");
    const modRows = [...r.mods.entries()].sort((a, b) => a[0].localeCompare(b[0], "ru"))
      .map(([k, v]) => `<li>${esc(k.replace(/ %$/, ""))}${MOD_BASE[k.replace(/ %$/, "")] != null ? "*" : ""}
        <b>${v > 0 ? "+" : ""}${fmtN(v)}${k.endsWith(" %") ? "%" : ""}</b></li>`).join("");
    const setRows = r.sets.map(s => `<li><a href="${entryHref(s.kit)}">${esc(s.kit.name)}</a> — ${s.have}/${s.total},
        бонус ${Math.round(s.share * 100)}%</li>`).join("");

    els.main.innerHTML = `<h1 class="page-title">Переодевалка</h1>
      <p class="page-sub">Соберите комплект и посмотрите итоговые характеристики, сопротивления и требования.
        Базу (колонка «Основа») распределите кнопками − / + или введите из игры — всё сохранится в браузере.</p>
      <div class="builder">
        <section class="b-panel">
          <div class="b-row">
            <label>Класс <select id="bCls"><option value="">— любой —</option>
              ${CLASS_NAMES.map(c => `<option ${build.cls === c ? "selected" : ""}>${c}</option>`).join("")}</select></label>
            <label>Уровень <input id="bLvl" type="number" min="1" max="300" value="${esc(build.lvl)}"></label>
          </div>
          <table class="b-stats"><thead><tr><th>Характеристики</th><th>Основа</th><th>Сумма</th><th></th></tr></thead>
            <tbody>${statRows}</tbody></table>
          ${(() => {
            const lvl = num(build.lvl) || 1, free = statPointsTotal(lvl) - statPointsSpent();
            const sk = build.cls ? skillsState() : null;
            return `<div class="b-free ${free < 0 ? "bad" : ""}">Свободных очков развития: <b>${fmtN(free)}</b>
                <small class="muted">из ${statPointsTotal(lvl)} на ${lvl} уровне</small>
                <button class="btn btn-sm" id="stReset" title="Вернуть стартовые значения">Сброс</button></div>
              ${free < 0 ? `<p class="b-warn">Распределено больше очков, чем доступно на ${lvl} уровне.</p>` : ""}
              <div class="b-free">Нераспределённые очки навыков: ${sk ? `<span class="nowrap">${pointsHtml(Math.max(0, sk.free))}</span>` : `<small class="muted">выберите класс</small>`}</div>`;
          })()}
          <table class="b-res"><thead><tr><th>Устойчивости</th><th>Очки</th><th></th><th>Уменьшение</th></tr></thead>
            <tbody>${resRows}</tbody></table>
          <p class="muted small">Уменьшение урона рассчитано по формуле, подобранной по игре; значения выше 82 очков — приблизительные (≈).</p>
        </section>
        <section class="b-doll">
          <div class="doll">
            ${slotHtml}
            <div class="doll-center">
              <b>${esc(build.cls || "Персонаж")}</b>
              <span>${esc(build.lvl || 1)} уровень</span>
              <span class="doll-power" title="Сила персонажа (Power) без бонусов психо и орбов">Power ≈ ${fmtN(r.power)}</span>
            </div>
          </div>
          <div class="b-actions">
            <button class="btn" id="bShare">🔗 Ссылка на сборку</button>
            <button class="btn" id="bClear">Снять всё</button>
          </div>
          <p class="muted small">Нажмите на слот, чтобы выбрать вещь. Вещь можно надеть и из её карточки кнопкой 👕.</p>
        </section>
        <section class="b-panel">
          ${r.problems.length ? `<div class="b-warn"><b>Не подходит:</b><ul>${r.problems.map(([s, e, why]) =>
            `<li>${esc(e?.name || s.name)} — ${esc(why)}</li>`).join("")}</ul></div>` : ""}
          <h3>Комплекты</h3>
          ${setRows ? `<ul class="b-list">${setRows}</ul>` : `<p class="muted small">Нет надетых частей комплектов.</p>`}
          <h3>Модификаторы</h3>
          <ul class="b-list">${modRows}</ul>
          <p class="muted small">* с учётом базового значения (крит 2%, восстановление ресурсов в бою 5%).</p>
          <h3>Прочее</h3>
          <ul class="b-list">
            <li>Урон оружия <b>${fmtN(r.weaponDmg)}</b></li>
            <li>Power <b>≈ ${fmtN(r.power)}</b> <small class="muted">(без психо и орбов)</small></li>
          </ul>
        </section>
      </div>
      <section class="b-panel b-skills"><h3>Навыки</h3>${renderSkills()}</section>
      <div class="picker" id="picker" hidden></div>`;

    const rerender = () => { saveBuild(); refresh(); };
    bon("#bCls", "change", ev => { build.cls = ev.target.value; rerender(); });
    bon("#bLvl", "change", ev => { build.lvl = Math.max(1, num(ev.target.value) || 1); rerender(); });
    $$(".b-in").forEach(inp => inp.addEventListener("change", () => {
      const k = inp.dataset.base;
      build.base[k] = inp.value === "" ? STAT_START[k] : Math.max(STAT_START[k], num(inp.value) || 0);
      rerender();
    }));
    $$(".st-btn").forEach(b => b.addEventListener("click", () => {
      const k = b.dataset.st, d = Number(b.dataset.d), step = STAT_STEP[k] || 1;
      const cur = num(build.base[k]) || STAT_START[k];
      const free = statPointsTotal(num(build.lvl) || 1) - statPointsSpent();
      if (d > 0 && free < 1) return;
      build.base[k] = Math.max(STAT_START[k], cur + d * step);
      rerender();
    }));
    bon("#stReset", "click", () => { build.base = { ...STAT_START }; rerender(); });
    bon("#bClear", "click", () => { build.items = {}; rerender(); });
    bon("#bShare", "click", ev => {
      const link = buildLink();
      (navigator.clipboard?.writeText(link) || Promise.reject()).then(
        () => { ev.target.textContent = "✓ Ссылка скопирована"; },
        () => { prompt("Ссылка на сборку:", link); });
    });
    $$(".doll-x").forEach(x => x.addEventListener("click", ev => {
      ev.stopPropagation();
      delete build.items[x.dataset.unequip];
      rerender();
    }));
    $$(".sk-btn").forEach(b => b.addEventListener("click", () => {
      const e = db.byId.get(b.dataset.sk), id = e.id, lv = skillLevel(e) + Number(b.dataset.d);
      if (lv > minLevel(e)) build.skills[id] = lv; else delete build.skills[id];
      rerender();
    }));
    bon("#skReset", "click", () => { build.skills = {}; rerender(); });
    $$(".doll-slot").forEach(btn => btn.addEventListener("click", () => openPicker(SLOTS.find(s => s.id === btn.dataset.slot))));
  }

  function openPicker(slot) {
    const box = $("#picker");
    let q = "", onlyFit = true;
    const all = db.sections.equipment.entries.filter(e => fitsSlot(e, slot));
    const statLine = e => [...BASE_STATS.map(([l]) => [l, fnum(e, l)]), ...RESISTS.map(([l, n]) => [n, fnum(e, l)])]
      .filter(([, v]) => v).slice(0, 6).map(([l, v]) => `${l} ${v > 0 ? "+" : ""}${fmtN(v)}`).join(" · ");
    const draw = () => {
      const lvl = num(build.lvl) || 0;
      const list = all.filter(e => (!q || norm(e.name).includes(q)) &&
        (!onlyFit || ((fnum(e, "Требуемый уровень") <= lvl) &&
          (!build.cls || !fv(fieldOf(e, "Требуемый класс")) || fv(fieldOf(e, "Требуемый класс")) === build.cls))))
        .sort((a, b) => fnum(b, "Требуемый уровень") - fnum(a, "Требуемый уровень") || a.name.localeCompare(b.name, "ru"));
      box.querySelector(".pk-list").innerHTML = list.length ? list.map(e => `<button class="pk-item" data-pick="${esc(e.id)}">
          ${iconHtml(e, "ico-sm")}<span class="pk-main"><b>${esc(e.name)}</b>
          <small>${fnum(e, "Требуемый уровень") ? "ур. " + fnum(e, "Требуемый уровень") + " · " : ""}${esc(fv(fieldOf(e, "Редкость")) || "")}
          ${fv(fieldOf(e, "Требуемый класс")) ? " · " + esc(fv(fieldOf(e, "Требуемый класс"))) : ""}</small>
          <small class="pk-stats">${esc(statLine(e))}</small></span></button>`).join("")
        : `<p class="muted">Ничего не найдено${onlyFit ? " — снимите галочку «только подходящие»" : ""}.</p>`;
      box.querySelectorAll("[data-pick]").forEach(b => b.addEventListener("click", () => {
        build.items[slot.id] = b.dataset.pick;
        const e = db.byId.get(b.dataset.pick);
        if (slot.id === "weapon" && isTwoHanded(e)) delete build.items.offhand;
        box.hidden = true;
        saveBuild();
        refresh();
      }));
    };
    box.innerHTML = `<div class="pk-card">
        <div class="pk-head"><b>${esc(slot.name)}</b>
          <input type="search" id="pkQ" placeholder="Поиск по названию…" autocomplete="off">
          <label class="flt chk"><input type="checkbox" id="pkFit" checked> только подходящие</label>
          <button class="icon-btn" id="pkClose" title="Закрыть">✕</button></div>
        <div class="pk-list"></div>
        ${build.items[slot.id] ? `<button class="btn" id="pkOff">Снять</button>` : ""}
      </div>`;
    box.hidden = false;
    draw();
    const qi = box.querySelector("#pkQ");
    qi.focus();
    qi.addEventListener("input", () => { q = norm(qi.value); draw(); });
    box.querySelector("#pkFit").addEventListener("change", ev => { onlyFit = ev.target.checked; draw(); });
    box.querySelector("#pkClose").addEventListener("click", () => { box.hidden = true; });
    box.querySelector("#pkOff")?.addEventListener("click", () => { delete build.items[slot.id]; box.hidden = true; saveBuild(); refresh(); });
    box.addEventListener("click", ev => { if (ev.target === box) box.hidden = true; });
  }

  // ---------- main router ----------

  function renderMain(route) {
    const [kind, secId, catId] = route.parts;
    const key = route.parts.join("/");
    if (key !== view.routeKey) {
      view.routeKey = key;
      resetFilters();
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
      const entries = favorites.values().map(id => db.byId.get(id)).filter(Boolean);
      renderList("Избранное", "Отмечай записи звёздочкой ★ в карточке", entries, { showSection: true });
    } else if (kind === "marks") {
      const entries = marks.values().map(id => db.byId.get(id)).filter(Boolean);
      renderList("Есть у меня", "Отмечай записи кнопкой ✓ в карточке", entries,
        { showSection: true, empty: "Пока ничего не отмечено" });
    } else if (kind === "cmp") {
      renderCompare();
    } else if (kind === "about") {
      renderAbout();
    } else if (kind === "build") {
      renderBuild(route);
    } else if (kind === "maps") {
      secId ? renderMap(secId, route.hl) : renderMapsList();
    } else {
      renderHome();
    }
  }

  // ---------- detail ----------

  function linkify(text) {
    const target = db.byName.get(norm(text));
    return target ? `<a href="${entryHrefHere(target)}">${esc(text)}</a>` : esc(text);
  }

  const BACKREF_LIMIT = 40;

  // Полоски здоровья / маны / выносливости.
  const BAR_LABELS = { "Здоровье": "hp", "Мана": "mana", "Выносливость": "stam" };
  function barsHtml(e) {
    const bars = e.fields.filter(([k]) => BAR_LABELS[k]);
    if (!bars.length) return "";
    return `<div class="bars">${bars.map(([k, v]) => `<div class="bar ${BAR_LABELS[k]}"><span>${esc(k)}</span>
      <b>${esc(fv(v))}</b>${isDiff(v) ? `<small>${esc(DIFFS.find(d => d[0] === view.diff)[1].toLowerCase())}</small>` : ""}</div>`).join("")}</div>`;
  }

  function renderBackrefs(e) {
    return e.backrefs.map((g, gi) => {
      const items = g.ids.map(id => db.byId.get(id)).filter(Boolean);
      if (!items.length) return "";
      const shown = items.slice(0, BACKREF_LIMIT);
      return `<div class="block">
        <h3>${esc(g.title)} <i>${items.length}</i></h3>
        <div class="brefs" data-group="${gi}">${shown.map(t =>
          `<a class="bref" href="${entryHrefHere(t)}" data-items="${esc(t.id)}">${iconHtml(t, "ico-sm")}<span>${esc(t.name)}</span></a>`).join("")}
          ${items.length > shown.length ? `<button class="link-btn" data-more="${gi}">ещё ${items.length - shown.length}</button>` : ""}
        </div>
      </div>`;
    }).join("");
  }

  function renderDetail(route) {
    const e = route.entryId && db.byId.get(route.entryId);
    if (!e) {
      els.detail.hidden = true;
      els.backdrop.hidden = !document.body.classList.contains("nav-open");
      document.body.classList.remove("detail-open", "detail-wide");
      return;
    }
    const sec = db.sections[e.section];
    const cat = sec.categories.find(c => c.id === e.category);
    const idx = view.list.findIndex(x => x.id === e.id);
    const prev = idx > 0 ? view.list[idx - 1] : null;
    const next = idx >= 0 && idx < view.list.length - 1 ? view.list[idx + 1] : null;
    const lvl = fv(fieldOf(e, "Уровень")) || fv(fieldOf(e, "Требуемый уровень"));
    // Карты, где объект отмечен точкой, но которых нет в его блоках «Где найти» / «Путь».
    const linkedMaps = new Set(e.blocks.flatMap(b => [...b.html.matchAll(/data-maps="([^"]+)"/g)].map(m => m[1])));
    const extraMaps = (db.mapsOf.get(e.id) || []).filter(mid => !linkedMaps.has(mid));

    els.detail.innerHTML = `
      <div class="detail-bar">
        <a class="icon-btn" ${prev ? `href="${entryHrefHere(prev)}"` : "aria-disabled=true"} title="Предыдущая (←)">‹</a>
        <a class="icon-btn" ${next ? `href="${entryHrefHere(next)}"` : "aria-disabled=true"} title="Следующая (→)">›</a>
        <span class="spacer"></span>
        <a class="icon-btn" href="e/${esc(e.id.replace(/[^A-Za-z0-9_.-]/g, "_"))}.html" target="_blank" rel="noopener"
          title="Отдельная страница — удобно делиться ссылкой">🔗</a>
        ${slotFor(e) ? `<button class="icon-btn" id="wearBtn" title="Надеть в переодевалке">👕</button>` : ""}
        <button class="icon-btn" id="wideBtn" title="Шире / уже">⤢</button>
        <button class="icon-btn mark-btn ${marks.has(e.id) ? "on" : ""}" id="markBtn" title="Есть у меня">✓</button>
        <button class="icon-btn cmp-btn ${compare.has(e.id) ? "on" : ""}" id="cmpBtn" title="Сравнить">⚖</button>
        <button class="icon-btn fav-btn ${favorites.has(e.id) ? "on" : ""}" id="favBtn" title="В избранное">★</button>
        <button class="icon-btn" id="closeDetail" title="Закрыть (Esc)">✕</button>
      </div>
      <div class="detail-head">
        ${iconHtml(e, "ico-lg")}
        <div>
          <h2>${esc(e.name)}</h2>
          <div class="crumbs">
            <a href="${href(["s", sec.id])}">${esc(sec.title)}</a>
            ${cat ? ` / <a href="${href(["s", sec.id, cat.id])}">${esc(cat.name)}</a>` : ""}
          </div>
          ${lvl ? `<span class="lvl">Уровень ${esc(lvl)}</span>` : ""}
          ${e.attacks ? `<div class="atk-line">Атакует: ${atkHtml(e)}</div>` : ""}
        </div>
      </div>
      ${hasDiff(e) ? diffSwitch("diffDetail") : ""}
      ${e.image ? `<div class="model"><img src="${esc(e.image)}" alt="" onerror="this.parentNode.remove()"></div>` : ""}
      ${barsHtml(e)}
      ${e.fields.filter(([k]) => !BAR_LABELS[k]).length ? `<table class="props">${e.fields.filter(([k]) => !BAR_LABELS[k]).map(([k, v]) =>
        `<tr><th>${fieldLabel(k)}</th><td>${FIELD_HELP[k] ? esc(fv(v)) : linkify(fv(v))}${isDiff(v) ? ` <small class="muted">(${esc(DIFFS.find(d => d[0] === view.diff)[1].toLowerCase())})</small>` : ""}</td></tr>`).join("")}</table>` : ""}
      ${e.description ? `<div class="desc">${esc(e.description).replace(/\n/g, "<br>")}</div>` : ""}
      ${e.blocks.map(b => `<div class="block">
        ${b.title && b.title !== "Статья" ? `<h3>${esc(b.title)}</h3>` : ""}
        <div class="block-html">${b.html}</div>
      </div>`).join("")}
      ${extraMaps.length ? `<div class="block"><h3>На карте</h3><div class="block-html">${extraMaps.map(mid =>
        `<span data-maps="${esc(mid)}">${esc(db.mapById.get(mid)?.name || mid)}</span>`).join(", ")}</div></div>` : ""}
      ${renderBackrefs(e)}
      ${e.lists.map(l => `<div class="detail-list">
        <h3>${esc(l.title)}</h3>
        <ul>${(l.items || []).map(it => `<li>${linkify(it)}</li>`).join("")}</ul>
      </div>`).join("")}
      <div class="block note">
        <h3>Моя заметка</h3>
        <textarea id="noteText" rows="3" placeholder="Например: где фармлю, сколько уже собрано…">${esc(notes[e.id] || "")}</textarea>
      </div>
    `;
    const wasHidden = els.detail.hidden;
    els.detail.hidden = false;
    if (wasHidden || els.detail.dataset.id !== e.id) els.detail.scrollTop = 0;
    els.detail.dataset.id = e.id;
    document.body.classList.add("detail-open");
    els.backdrop.hidden = false;

    bindRefs(els.detail, e);
    bindDiff(els.detail);
    $("#closeDetail").addEventListener("click", closeDetail);
    $("#favBtn").addEventListener("click", () => { favorites.toggle(e.id); refresh(); });
    $("#markBtn").addEventListener("click", () => { marks.toggle(e.id); refresh(); });
    $("#wearBtn")?.addEventListener("click", () => {
      const slot = slotFor(e);
      build.items[slot.id] = e.id;
      if (slot.id === "weapon" && isTwoHanded(e)) delete build.items.offhand;
      if (slot.id === "offhand") { const w = db.byId.get(build.items.weapon); if (w && isTwoHanded(w)) delete build.items.weapon; }
      saveBuild();
      location.hash = "#/build";
    });
    $("#wideBtn").addEventListener("click", () => {
      view.wide = !document.body.classList.contains("detail-wide");
      store.set("wide", view.wide);
      document.body.classList.toggle("detail-wide", view.wide);
    });
    // Длинные статьи читать удобнее в широкой панели.
    document.body.classList.toggle("detail-wide", e.section === "guides" || !!view.wide);
    $("#cmpBtn").addEventListener("click", () => { compare.toggle(e.id, COMPARE_MAX); refresh(); });
    $("#noteText").addEventListener("input", ev => {
      const t = ev.target.value;
      if (t.trim()) notes[e.id] = t; else delete notes[e.id];
      store.set("notes", notes);
    });
    els.detail.querySelectorAll("[data-more]").forEach(b => b.addEventListener("click", () => {
      const g = e.backrefs[Number(b.dataset.more)];
      const box = b.parentNode;
      b.remove();
      box.insertAdjacentHTML("beforeend", g.ids.slice(BACKREF_LIMIT).map(id => db.byId.get(id)).filter(Boolean)
        .map(t => `<a class="bref" href="${entryHrefHere(t)}" data-items="${esc(t.id)}">${iconHtml(t, "ico-sm")}<span>${esc(t.name)}</span></a>`).join(""));
    }));
    $$(".card.selected").forEach(n => n.classList.remove("selected"));
    document.querySelector(`.card[data-id="${CSS.escape(e.id)}"]`)?.classList.add("selected");
  }

  // Иконки с data-items в HTML-блоках — ссылки на другие записи; data-maps — ссылки на карты.
  function bindRefs(root, e) {
    root.querySelectorAll(".block-html [data-items]").forEach(node => {
      const target = db.byId.get(node.getAttribute("data-items"));
      if (!target) return;
      node.classList.add("ref");
      node.removeAttribute("title");
      node.addEventListener("click", ev => {
        ev.preventDefault();
        location.hash = entryHrefHere(target);
      });
    });
    root.querySelectorAll(".block-html [data-maps]").forEach(node => {
      const mid = node.getAttribute("data-maps");
      if (!db.mapById.has(mid)) return;
      node.classList.add("map-link");
      node.title = "Открыть карту";
      node.addEventListener("click", () => { location.hash = mapHref(mid, e?.id, e?.id); });
    });
    root.querySelectorAll(".block-html img").forEach(img => {
      img.loading = "lazy";
      img.addEventListener("error", () => {
        const target = db.byId.get(img.getAttribute("data-items"));
        const t = img.getAttribute("title") || target?.name;
        if (t) {
          const span = document.createElement("span");
          span.className = "img-missing" + (target ? " ref" : "");
          span.textContent = t;
          if (target) span.addEventListener("click", () => { location.hash = entryHrefHere(target); });
          img.replaceWith(span);
        } else img.remove();
      }, { once: true });
    });
  }

  function closeDetail() {
    const { parts, hl } = parseRoute();
    location.hash = href(parts, null, { hl });
  }

  // ---------- hover tooltip ----------

  const tip = document.createElement("div");
  tip.className = "tip";
  tip.hidden = true;
  document.body.appendChild(tip);
  let tipFor = null;

  // Пояснения к непонятным полям: подсказка и ссылка на статью.
  const FIELD_HELP = {
    "Аспект": ["Аспект противника для механики Насыщения: Насыщение действует только против противников с аспектом, а за победы над ними копятся очки мастерства этого аспекта.", "wb_nasycenie"],
    "Путь сложности": ["Путь сложности в механике Насыщения: Тень → Мрак → Глубина → Бездна. Чем дальше путь, тем больше очков мастерства аспекта даёт победа.", "wb_nasycenie"],
    "Сила (PvE)": ["Оценка силы противника в PvE-боях.", "wb_power"],
  };
  function fieldLabel(k) {
    const h = FIELD_HELP[k];
    if (!h) return esc(k);
    const target = db.byId.get(h[1]);
    return `${esc(k)} <span class="help" title="${esc(h[0])}"${target ? ` data-help="${esc(h[1])}"` : ""}>?</span>`;
  }

  // Текст блока одной строкой (для подсказки).
  const blockText = (e, rx) => {
    const b = e.blocks.find(b => rx.test(b.title));
    const t = b ? stripTags(b.html).replace(/\s+/g, " ").trim() : "";
    return t && !/^[-—]$/.test(t) ? t : "";
  };
  const cut = (t, n) => t.length > n ? t.slice(0, n).replace(/\s+\S*$/, "") + "…" : t;

  function showTip(node, x, y) {
    const e = db.byId.get(node.getAttribute("data-items"));
    if (!e) return;
    if (tipFor !== e.id) {
      tipFor = e.id;
      const sec = db.sections[e.section];
      const cat = sec.categories.find(c => c.id === e.category);
      const rows = e.fields.filter(([k, v]) => !TIP_SKIP.test(k) && !/^(0|-|)$/.test(String(fv(v)).trim())).slice(0, 6);
      const usage = blockText(e, /^(Применение|Использование|Назначение)$/);
      const where = blockText(e, /^Локация$/);
      const desc = blockText(e, /^Описание$/);
      tip.innerHTML = `<div class="tip-head">${iconHtml(e, "ico-sm")}<div><b>${esc(e.name)}</b>
          <small>${esc(sec.title)}${cat ? " · " + esc(cat.name) : ""}</small></div></div>
        ${rows.length ? `<table>${rows.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(fv(v))}</td></tr>`).join("")}</table>` : ""}
        ${usage ? `<p class="tip-desc"><b>Для чего:</b> ${esc(cut(usage, 220))}</p>` : ""}
        ${where ? `<p class="tip-desc"><b>Где:</b> ${esc(cut(where, 140))}</p>` : ""}
        ${desc && (!usage || rows.length < 3) ? `<p class="tip-desc">${esc(cut(desc, 180))}</p>` : ""}
        ${!usage && !where && !desc && rows.length < 3 && e.blocks[0] ? `<p class="tip-desc">${esc(cut(stripTags(e.blocks[0].html).replace(/\s+/g, " ").trim(), 180))}</p>` : ""}`;
    }
    tip.hidden = false;
    const r = tip.getBoundingClientRect();
    let left = x + 14, top = y + 14;
    if (left + r.width > innerWidth - 8) left = x - r.width - 14;
    if (top + r.height > innerHeight - 8) top = y - r.height - 14;
    tip.style.left = Math.max(8, left) + "px";
    tip.style.top = Math.max(8, top) + "px";
  }

  if (matchMedia("(hover: hover)").matches) {
    document.addEventListener("mousemove", ev => {
      const node = ev.target.closest?.(".ref[data-items], .bref[data-items], .marker[data-items], .img-missing.ref");
      if (node && node.getAttribute("data-items")) showTip(node, ev.clientX, ev.clientY);
      else if (!tip.hidden) { tip.hidden = true; tipFor = null; }
    });
    window.addEventListener("hashchange", () => { tip.hidden = true; tipFor = null; });
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
    const mapsFound = db.maps.filter(m => norm(m.name).includes(q)).slice(0, 5);
    const found = [...starts, ...contains, ...deep];
    const shown = found.slice(0, 40);
    activeResult = shown.length || mapsFound.length ? 0 : -1;
    const mapRows = mapsFound.map(m => `<a class="sr" href="${mapHref(m.id)}"><div class="ico ico-sm ico-empty">🗺</div>
      <span class="sr-name">${esc(m.name)}</span><span class="sr-sec">Карта</span></a>`).join("");
    els.results.innerHTML = shown.length || mapsFound.length
      ? shown.map(e => `<a class="sr" href="${entryHref(e)}">
          ${iconHtml(e, "ico-sm")}<span class="sr-name">${esc(e.name)}</span>
          <span class="sr-sec">${esc(db.sections[e.section].title)}</span></a>`).join("") + mapRows
        + (found.length > shown.length ? `<div class="sr-more">…и ещё ${found.length - shown.length}</div>` : "")
      : `<div class="sr-more">Ничего не найдено</div>`;
    els.results.querySelector(".sr")?.classList.add("active");
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
    const help = ev.target.closest(".help[data-help]");
    if (help) {
      const t = db.byId.get(help.dataset.help);
      if (t) location.hash = entryHref(t);
    }
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
    const listKey = route.parts.join("/") + "|" + (route.hl || "");
    // Перерисовываем список только при смене страницы, чтобы карточка открывалась без прыжков.
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
