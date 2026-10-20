/* Demo backend for the GitHub Pages build.

   Answers the same /api/... calls as the FastAPI app, in the browser, on made-up data:
   nothing is sent to Keitaro. The share and draft logic mirrors app/services/shares.py and
   app/services/editor.py; tests/test_demo_parity.py checks both give the same numbers. */

(function (root) {
  "use strict";

  const TOTAL = 100;
  const ACTIVE = "active";
  const REMOVED = "removed";
  const DISABLED = "disabled";
  const STORAGE_KEY = "kw-demo-v1";

  class DemoError extends Error {}

  // ---------- shares (app/services/shares.py) ----------

  function rebalance(slots) {
    const active = slots.map((s, i) => (s.active ? i : -1)).filter((i) => i >= 0);
    let pinned = active.filter((i) => slots[i].pinned);
    let free = active.filter((i) => !slots[i].pinned);
    const result = slots.map(() => 0);
    if (!active.length) return result;
    if (!free.length) {
      free = active;
      pinned = [];
    }
    const pinnedTotal = pinned.reduce((sum, i) => sum + slots[i].share, 0);
    if (pinnedTotal > TOTAL) throw new DemoError(`Закреплённые доли дают ${pinnedTotal}%, больше ${TOTAL}%`);
    for (const i of pinned) result[i] = slots[i].share;
    const rest = TOTAL - pinnedTotal;
    const base = Math.floor(rest / free.length);
    const remainder = rest % free.length;
    free.forEach((i, n) => (result[i] = base + (n >= free.length - remainder ? 1 : 0)));
    return result;
  }

  function validateTotal(shares) {
    if (!shares.length) throw new DemoError("В потоке должен остаться хотя бы один активный оффер");
    if (shares.some((s) => s < 0 || s > TOTAL)) throw new DemoError("Доля должна быть от 0 до 100");
    const total = shares.reduce((a, b) => a + b, 0);
    if (total !== TOTAL) throw new DemoError(`Сумма долей ${total}%, а должна быть ${TOTAL}%`);
  }

  // ---------- seed data ----------

  const OFFERS = [
    { id: 101, name: "Glowa Cream [BEAUTY-RO] лендинг с таймером", state: "active", countries: ["Romania"] },
    { id: 102, name: "Glowa Serum [BEAUTY-CZ] прелендинг-квиз", state: "active", countries: ["Czech Republic"] },
    { id: 103, name: "FitLine Capsules [DIET-MX] VSL", state: "active", countries: ["Mexico"] },
    { id: 104, name: "JointFlex Gel [JOINT-PE] лендинг", state: "active", countries: ["Peru"] },
    { id: 105, name: "Visiomax Drops [EYE-AU] статья", state: "active", countries: ["Australia"] },
    { id: 106, name: "CardioBalance [HEART-RO] колесо фортуны", state: "active", countries: ["Romania"] },
    { id: 107, name: "SlimTea [DIET-HR] лендинг", state: "active", countries: ["Croatia"] },
    { id: 108, name: "HairPro Oil [HAIR-PL] отзывы", state: "active", countries: ["Poland"] },
    { id: 109, name: "Old Offer [ARCHIVE]", state: "disabled", countries: [] },
  ];

  function seed() {
    const db = { campaigns: {}, kt: {}, nextId: 5000, nextLink: 90000, createdAt: {} };
    seedCampaign(db, 1001, "demo: campaign 2", "wVqN1R", ["AU"], [[101, 33], [102, 33], [103, 34]], false);
    seedCampaign(db, 1002, "demo: MX launch", "mx-launch-3f9a1c", ["MX"], [[103, 100]], false);
    return db;
  }

  function seedCampaign(db, id, name, alias, countries, offers, createdHere) {
    const geoId = id * 10 + 1;
    const offerId = id * 10 + 2;
    db.kt[geoId] = [];
    db.kt[offerId] = offers.map(([offer_id, share]) => ({ id: db.nextLink++, offer_id, share, state: ACTIVE }));
    db.createdAt[id] = new Date().toISOString().slice(0, 19).replace("T", " ");
    db.campaigns[id] = {
      id,
      name,
      alias,
      created_here: createdHere,
      synced_at: null,
      streams: [
        stream(geoId, "Flow 1", 1, "redirect", "https://google.com", [{ name: "country", mode: "accept", payload: countries }]),
        stream(offerId, "Flow 2", 2, "landings", "", []),
      ],
    };
    syncCampaign(db, id);
  }

  function stream(id, name, position, schema, payload, filters) {
    return { id, name, type: "regular", position, schema, action_type: "http", action_payload: payload, filters, offers: [] };
  }

  // ---------- editor (app/services/editor.py) ----------

  const offerName = (id) => OFFERS.find((o) => o.id === id)?.name || `Оффер #${id}`;
  const ordered = (s) => [...s.offers].sort((a, b) => a.position - b.position);
  const nextPosition = (s) => Math.max(0, ...s.offers.map((r) => r.position)) + 1;
  const isEditable = (s) => s.schema === "landings";

  function applyKt(s, ktOffers) {
    const rows = new Map(s.offers.map((r) => [r.offer_id, r]));
    const present = new Set();
    for (const item of ktOffers) {
      present.add(item.offer_id);
      let row = rows.get(item.offer_id);
      if (!row) {
        row = { offer_id: item.offer_id, offer_name: "", position: 0, pinned: false };
        s.offers.push(row);
      }
      row.offer_name = offerName(item.offer_id);
      row.state = (item.state || ACTIVE) === ACTIVE ? ACTIVE : DISABLED;
      row.share = item.share;
      row.kt_share = item.share;
      row.kt_link_id = item.id;
      row.synced = true;
      if (row.state === DISABLED) row.pinned = false;
    }
    for (const row of [...s.offers]) {
      if (present.has(row.offer_id)) continue;
      if (!row.synced) {
        s.offers.splice(s.offers.indexOf(row), 1);
        continue;
      }
      Object.assign(row, { state: REMOVED, share: 0, kt_share: null, kt_link_id: null, pinned: false });
    }
    renumber(s);
  }

  function renumber(s) {
    const inKt = s.offers
      .filter((r) => r.kt_share !== null)
      .sort((a, b) => (a.kt_link_id || 0) - (b.kt_link_id || 0) || a.position - b.position);
    const rest = s.offers.filter((r) => r.kt_share === null).sort((a, b) => a.position - b.position);
    [...inKt, ...rest].forEach((r, i) => (r.position = i + 1));
  }

  function recount(s) {
    const rows = ordered(s).filter((r) => r.state !== DISABLED);
    const active = rows.filter((r) => r.state === ACTIVE);
    if (active.length && active.every((r) => r.pinned)) active.forEach((r) => (r.pinned = false));
    const shares = rebalance(rows.map((r) => ({ share: r.share, active: r.state === ACTIVE, pinned: r.pinned })));
    rows.forEach((r, i) => (r.share = shares[i]));
  }

  function syncCampaign(db, id) {
    const c = db.campaigns[id];
    for (const s of c.streams) applyKt(s, db.kt[s.id] || []);
    c.synced_at = new Date().toISOString();
  }

  function findStream(db, streamId) {
    for (const c of Object.values(db.campaigns)) {
      const s = c.streams.find((x) => x.id === streamId);
      if (s) {
        if (!isEditable(s)) throw new DemoError("В этом потоке нет офферов: он делает редирект");
        return s;
      }
    }
    throw new DemoError(`Поток ${streamId} не найден`);
  }

  const findRow = (s, offerId) => s.offers.find((r) => r.offer_id === offerId);
  function requireRow(s, offerId) {
    const row = findRow(s, offerId);
    if (!row) throw new DemoError(`Оффера ${offerId} нет в потоке`);
    return row;
  }
  function requireKnownOffer(offerId) {
    const offer = OFFERS.find((o) => o.id === offerId);
    if (!offer || offer.state !== ACTIVE) throw new DemoError(`Оффер ${offerId} не найден среди активных офферов Keitaro`);
  }
  function requireNotDisabled(row) {
    if (row.state === DISABLED) throw new DemoError(`Оффер ${row.offer_id} выключен в самом Keitaro: включите его там`);
  }

  // Each operation works on a copy, so a failed recount leaves the draft as it was.
  function withStream(db, streamId, fn) {
    const s = findStream(db, streamId);
    const backup = JSON.stringify(s.offers);
    try {
      fn(s);
    } catch (err) {
      s.offers = JSON.parse(backup);
      throw err;
    }
    return s;
  }

  const ops = {
    add(s, offerId) {
      const row = findRow(s, offerId);
      if (row) {
        if (row.state === REMOVED) return ops.restore(s, offerId);
        requireNotDisabled(row);
        throw new DemoError(`Оффер ${offerId} уже есть в потоке`);
      }
      requireKnownOffer(offerId);
      s.offers.push({ offer_id: offerId, offer_name: offerName(offerId), position: nextPosition(s), state: ACTIVE, share: 0, pinned: false, kt_share: null, synced: false, kt_link_id: null });
      recount(s);
    },
    remove(s, offerId) {
      const row = requireRow(s, offerId);
      requireNotDisabled(row);
      if (row.state === REMOVED) throw new DemoError(`Оффер ${offerId} уже удалён`);
      if (!row.synced) s.offers.splice(s.offers.indexOf(row), 1);
      else Object.assign(row, { state: REMOVED, share: 0, pinned: false });
      recount(s);
    },
    restore(s, offerId) {
      const row = requireRow(s, offerId);
      if (row.state !== REMOVED) throw new DemoError(`Оффер ${offerId} и так в потоке`);
      row.state = ACTIVE;
      if (row.kt_share === null) row.position = nextPosition(s);
      renumber(s);
      recount(s);
    },
    pin(s, offerId, pinned) {
      const row = requireRow(s, offerId);
      if (row.state !== ACTIVE) throw new DemoError("Закрепить можно только активный оффер");
      row.pinned = pinned;
    },
    share(s, offerId, share) {
      const row = requireRow(s, offerId);
      if (row.state !== ACTIVE) throw new DemoError("Долю можно задать только активному офферу");
      if (!Number.isInteger(share) || share < 0 || share > TOTAL) throw new DemoError("Доля должна быть от 0 до 100");
      if (!s.offers.some((r) => r.state === ACTIVE && !r.pinned && r !== row)) throw new DemoError("Нет других незакреплённых офферов, чтобы забрать остаток");
      row.share = share;
      row.pinned = true;
      recount(s);
    },
    cancel(s) {
      for (const row of [...s.offers]) {
        if (row.state === DISABLED) continue;
        if (row.kt_share !== null) Object.assign(row, { state: ACTIVE, share: row.kt_share });
        else if (row.synced) Object.assign(row, { state: REMOVED, share: 0, pinned: false });
        else s.offers.splice(s.offers.indexOf(row), 1);
      }
      renumber(s);
    },
    push(db, s) {
      const rows = ordered(s);
      const active = rows.filter((r) => r.state === ACTIVE);
      validateTotal(active.map((r) => r.share));
      active.filter((r) => r.kt_share === null).forEach((r) => requireKnownOffer(r.offer_id));
      const old = new Map((db.kt[s.id] || []).map((o) => [o.offer_id, o]));
      db.kt[s.id] = rows
        .filter((r) => r.state === ACTIVE || r.state === DISABLED)
        .map((r) => ({
          id: old.get(r.offer_id)?.id ?? db.nextLink++,
          offer_id: r.offer_id,
          share: r.state === ACTIVE ? r.share : r.kt_share,
          state: r.state,
        }))
        .sort((a, b) => a.id - b.id);
      applyKt(s, db.kt[s.id]);
    },
  };

  function isDirty(s) {
    return s.offers.some((r) => {
      if (r.state === DISABLED) return false;
      const inKt = r.kt_share !== null;
      const active = r.state === ACTIVE;
      return active !== inKt || (active && r.share !== r.kt_share);
    });
  }

  const GROUP = { [ACTIVE]: 0, [DISABLED]: 1, [REMOVED]: 2 };
  function streamOut(s) {
    const rows = ordered(s).sort((a, b) => GROUP[a.state] - GROUP[b.state] || (a.state === ACTIVE ? b.share - a.share : 0));
    return {
      id: s.id,
      name: s.name,
      type: s.type,
      position: s.position,
      schema: s.schema,
      action_type: s.action_type,
      action_payload: s.action_payload,
      filters: s.filters,
      editable: isEditable(s),
      dirty: isDirty(s),
      total: rows.filter((r) => r.state === ACTIVE).reduce((sum, r) => sum + r.share, 0),
      offers: rows.map((r) => ({
        offer_id: r.offer_id,
        name: r.offer_name,
        share: r.share,
        kt_share: r.kt_share,
        pinned: r.pinned,
        state: r.state,
        changed: (r.state === ACTIVE && r.share !== r.kt_share) || (r.state === REMOVED && r.kt_share !== null),
      })),
    };
  }

  function campaignOut(c) {
    const streams = [...c.streams].sort((a, b) => Number(!isEditable(a)) - Number(!isEditable(b)) || a.position - b.position);
    return { id: c.id, name: c.name, alias: c.alias, created_here: c.created_here, synced_at: c.synced_at, admin_url: "", streams: streams.map(streamOut) };
  }

  // ---------- creator (app/services/creator.py) ----------

  function parseCountries(raw, countries) {
    const codes = [];
    for (const part of String(raw).trim().split(/[\s,;]+/)) {
      if (!part) continue;
      const code = part.toUpperCase() === "UK" ? "GB" : part.toUpperCase();
      if (!countries.some((c) => c.code === code)) throw new DemoError(`Неизвестный код страны: ${part}`);
      if (!codes.includes(code)) codes.push(code);
    }
    if (!codes.length) throw new DemoError("Укажите хотя бы одну страну, например MX");
    return codes;
  }

  function makeAlias(name) {
    const slug = name.normalize("NFKD").replace(/[^\x00-\x7f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "campaign";
    return `${slug}-${Math.random().toString(16).slice(2, 8)}`;
  }

  function createCampaign(db, body, countries) {
    const name = String(body.name || "").trim();
    if (!name) throw new DemoError("Укажите название кампании");
    const codes = parseCountries(body.geo || "", countries);
    requireKnownOffer(body.offer_id);
    const id = db.nextId++;
    const alias = makeAlias(name);
    seedCampaign(db, id, name, alias, codes, [[body.offer_id, 100]], true);
    return { id, name, alias, countries: codes, admin_url: "" };
  }

  // ---------- request router ----------

  function createBackend({ storage, countries }) {
    let db = load();

    function load() {
      try {
        const saved = storage && storage.getItem(STORAGE_KEY);
        if (saved) return JSON.parse(saved);
      } catch {
        /* private mode or broken data: start over */
      }
      return seed();
    }
    function save() {
      try {
        storage && storage.setItem(STORAGE_KEY, JSON.stringify(db));
      } catch {
        /* storage unavailable: the demo just forgets on reload */
      }
    }

    async function handle(method, path, body) {
      const url = new URL(path, "http://demo.local");
      const p = url.pathname;
      const q = url.searchParams;
      let m;

      if (method === "GET" && p === "/api/meta") {
        return { keitaro_admin_url: "", group: "FORTESTS", traffic_source: "FORTESTS", domain_id: 4622, geo_redirect_url: "https://google.com" };
      }
      if (method === "GET" && p === "/api/countries") return countries();
      if (method === "GET" && p === "/api/offers") {
        const query = (q.get("q") || "").trim().toLowerCase();
        const limit = Number(q.get("limit") || 20);
        return OFFERS.filter((o) => o.state === ACTIVE)
          .filter((o) => !query || String(o.id).includes(query) || o.name.toLowerCase().includes(query))
          .slice(0, limit)
          .map(({ id, name, countries: c }) => ({ id, name, countries: c }));
      }
      if (method === "POST" && p === "/api/campaigns") {
        const created = createCampaign(db, body, await countries());
        save();
        return created;
      }
      if (method === "GET" && p === "/api/campaigns") {
        return Object.values(db.campaigns)
          .map((c) => ({ id: c.id, name: c.name, alias: c.alias, group: "FORTESTS", state: "active", created_at: db.createdAt[c.id], created_here: c.created_here }))
          .sort((a, b) => b.id - a.id);
      }
      if ((m = p.match(/^\/api\/campaigns\/(\d+)(\/sync)?$/))) {
        const c = db.campaigns[Number(m[1])];
        if (!c) throw new DemoError("Keitaro 404: Not found");
        if (m[2]) syncCampaign(db, c.id);
        save();
        return campaignOut(c);
      }
      if ((m = p.match(/^\/api\/streams\/(\d+)\/(offers|recount|cancel|push)$/))) {
        const id = Number(m[1]);
        const s = withStream(db, id, (st) => {
          if (m[2] === "offers") ops.add(st, Number(body.offer_id));
          else if (m[2] === "recount") recount(st);
          else if (m[2] === "cancel") ops.cancel(st);
          else ops.push(db, st);
        });
        save();
        return streamOut(s);
      }
      if ((m = p.match(/^\/api\/streams\/(\d+)\/offers\/(\d+)\/(remove|restore|pin|share)$/))) {
        const offerId = Number(m[2]);
        const s = withStream(db, Number(m[1]), (st) => {
          if (m[3] === "remove") ops.remove(st, offerId);
          else if (m[3] === "restore") ops.restore(st, offerId);
          else if (m[3] === "pin") ops.pin(st, offerId, Boolean(body.pinned));
          else ops.share(st, offerId, Number(body.share));
        });
        save();
        return streamOut(s);
      }
      throw new DemoError(`Демо: неизвестный запрос ${method} ${p}`);
    }

    return {
      handle,
      reset() {
        db = seed();
        save();
      },
      // For tests: change a stream "in Keitaro", as someone editing it in the admin.
      setKt(streamId, offers) {
        db.kt[streamId] = offers.map(([offer_id, share, state]) => ({ id: db.nextLink++, offer_id, share, state: state || ACTIVE }));
      },
    };
  }

  const api = { rebalance, createBackend, OFFERS };
  if (typeof module !== "undefined" && module.exports) module.exports = api;

  // ---------- browser wiring ----------

  if (typeof document !== "undefined") {
    let countriesPromise;
    const countries = () => (countriesPromise ??= fetch("static/countries.json").then((r) => r.json()));
    let storage = null;
    try {
      storage = root.localStorage;
    } catch {
      storage = null;
    }
    const backend = createBackend({ storage, countries });
    root.KW_DEMO_API = async (method, path, body) => {
      await new Promise((r) => setTimeout(r, 120 + Math.random() * 180));
      return JSON.parse(JSON.stringify(await backend.handle(method, path, body)));
    };
    document.addEventListener("DOMContentLoaded", () => {
      const reset = document.createElement("button");
      reset.className = "demo-reset";
      reset.type = "button";
      reset.textContent = "Сбросить демо";
      reset.addEventListener("click", () => {
        backend.reset();
        location.hash = "#/new";
        location.reload();
      });
      const banner = document.createElement("div");
      banner.className = "demo-banner";
      banner.innerHTML =
        '<span><strong>Демо-версия.</strong> Офферы и кампании тестовые, запросы в Keitaro не уходят: сервер имитируется в браузере. ' +
        'Код и запуск с настоящим Keitaro: <a href="https://github.com/pochuvstvuyvkus/keitaro-wrapper" target="_blank" rel="noopener">GitHub</a>.</span>';
      banner.append(reset);
      document.body.prepend(banner);
    });
  }
})(typeof window !== "undefined" ? window : globalThis);
