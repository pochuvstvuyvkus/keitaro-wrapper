"use strict";

// ---------- helpers ----------

const view = document.getElementById("view");

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key === "class") el.className = value;
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

async function api(method, path, body) {
  const response = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    let detail = data.detail;
    if (Array.isArray(detail)) detail = detail.map((d) => d.msg).join("; ");
    throw new Error(detail || `Ошибка ${response.status}`);
  }
  return data;
}

let toastTimer;
function toast(message, isError = false) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = isError ? "toast error" : "toast";
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), isError ? 7000 : 3000);
}

// Runs an async action with the button disabled; shows errors as a toast.
async function busy(button, action) {
  if (button) button.disabled = true;
  try {
    return await action();
  } catch (err) {
    toast(err.message, true);
  } finally {
    if (button) button.disabled = false;
  }
}

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

// ---------- offer autocomplete ----------

function offerAutocomplete({ placeholder, onPick, exclude = () => new Set() }) {
  let items = [];
  let active = -1;
  let picked = null;

  const input = h("input", { type: "search", placeholder, autocomplete: "off" });
  const list = h("ul", { class: "ac-list", hidden: true });
  const note = h("div", { class: "ac-picked" });
  const root = h("div", { class: "ac" }, input, list, note);

  function render() {
    list.replaceChildren();
    if (!items.length) {
      list.append(h("li", { class: "empty" }, "Ничего не найдено"));
    }
    items.forEach((offer, i) => {
      list.append(
        h(
          "li",
          { class: i === active ? "active" : "", onmousedown: (e) => (e.preventDefault(), pick(offer)) },
          h("span", { class: "id" }, `#${offer.id}`),
          offer.name,
          offer.countries.length ? h("span", { class: "muted" }, ` · ${offer.countries.join(", ")}`) : null,
        ),
      );
    });
    list.hidden = false;
  }

  const search = debounce(async () => {
    try {
      const found = await api("GET", `/api/offers?q=${encodeURIComponent(input.value)}`);
      const skip = exclude();
      items = found.filter((o) => !skip.has(o.id));
      active = items.length ? 0 : -1;
      if (document.activeElement === input) render();
    } catch (err) {
      toast(err.message, true);
    }
  }, 200);

  function pick(offer) {
    picked = offer;
    input.value = `${offer.id} — ${offer.name}`;
    note.textContent = `Выбран оффер #${offer.id}`;
    list.hidden = true;
    onPick?.(offer);
  }

  input.addEventListener("input", () => {
    picked = null;
    note.textContent = "";
    onPick?.(null);
    search();
  });
  input.addEventListener("focus", search);
  input.addEventListener("blur", () => (list.hidden = true));
  input.addEventListener("keydown", (e) => {
    if (list.hidden || !items.length) return;
    if (e.key === "ArrowDown") active = (active + 1) % items.length;
    else if (e.key === "ArrowUp") active = (active - 1 + items.length) % items.length;
    else if (e.key === "Enter") {
      e.preventDefault();
      if (active >= 0) pick(items[active]);
      return;
    } else if (e.key === "Escape") {
      list.hidden = true;
      return;
    } else return;
    e.preventDefault();
    render();
  });

  return {
    el: root,
    get value() {
      return picked;
    },
    clear() {
      picked = null;
      input.value = "";
      note.textContent = "";
    },
  };
}

// ---------- page: new campaign ----------

function pageNew() {
  let offer = null;
  const name = h("input", { type: "text", placeholder: "имя кампании", required: true });
  const geo = h("input", { type: "text", placeholder: "MX, AU, RO, ..." });
  const ac = offerAutocomplete({ placeholder: "поиск по офферам: id или название", onPick: (o) => (offer = o) });
  const submit = h("button", { class: "primary", type: "submit" }, "Create");
  const result = h("div");

  const form = h(
    "form",
    {
      class: "form",
      onsubmit: (e) => {
        e.preventDefault();
        if (!offer) return toast("Выберите оффер из списка", true);
        busy(submit, async () => {
          const created = await api("POST", "/api/campaigns", {
            name: name.value,
            geo: geo.value,
            offer_id: offer.id,
          });
          result.replaceChildren(
            h(
              "div",
              { class: "panel result" },
              h("h2", {}, `Кампания создана: ${created.name} (#${created.id})`),
              h(
                "p",
                {},
                `Поток 1: ${created.countries.join(", ")} → редирект; поток 2: оффер #${offer.id}.`,
              ),
              h(
                "p",
                {},
                h("a", { href: `#/campaigns/${created.id}` }, "Открыть в редакторе"),
                " · ",
                h("a", { href: created.admin_url, target: "_blank", rel: "noopener" }, "Открыть в Keitaro"),
              ),
            ),
          );
          form.reset();
          ac.clear();
          offer = null;
          toast("Кампания создана");
        });
      },
    },
    h("label", {}, "Name"),
    name,
    h("label", {}, "Geo"),
    geo,
    h("div", { class: "hint" }, "Коды стран ISO через запятую: поток 1 ловит их и редиректит на google.com"),
    h("label", {}, "Offer"),
    ac.el,
    h("div", { class: "actions" }, submit),
  );

  view.replaceChildren(h("h1", {}, "Новая кампания"), h("div", { class: "panel" }, form), result);
  name.focus();
}

// ---------- page: campaign list ----------

async function pageCampaigns() {
  const search = h("input", { type: "search", placeholder: "поиск по названию, id или alias" });
  const body = h("tbody");
  const table = h(
    "table",
    {},
    h("thead", {}, h("tr", {}, h("th", {}, "ID"), h("th", {}, "Название"), h("th", {}, "Alias"), h("th", {}, "Создана"))),
    body,
  );
  view.replaceChildren(
    h("h1", {}, "Кампании Keitaro"),
    h("div", { class: "toolbar" }, h("div", { class: "grow" }, search)),
    h("div", { class: "panel" }, table),
  );

  let all = [];
  function render() {
    const q = search.value.trim().toLowerCase();
    const rows = all.filter(
      (c) => !q || c.name.toLowerCase().includes(q) || String(c.id).includes(q) || c.alias.toLowerCase().includes(q),
    );
    body.replaceChildren(
      ...rows.map((c) =>
        h(
          "tr",
          {},
          h("td", {}, c.id),
          h(
            "td",
            {},
            h("a", { href: `#/campaigns/${c.id}` }, c.name || "(без названия)"),
            c.created_here ? h("span", { class: "badge" }, " создана здесь") : null,
          ),
          h("td", { class: "muted" }, c.alias),
          h("td", { class: "muted" }, c.created_at || ""),
        ),
      ),
    );
    if (!rows.length) body.append(h("tr", {}, h("td", { colspan: 4, class: "muted" }, "Нет кампаний")));
  }
  search.addEventListener("input", render);
  body.append(h("tr", {}, h("td", { colspan: 4, class: "muted" }, "Загрузка…")));
  try {
    all = await api("GET", "/api/campaigns");
    render();
  } catch (err) {
    body.replaceChildren(h("tr", {}, h("td", { colspan: 4, class: "error" }, err.message)));
  }
}

// ---------- page: campaign editor ----------

async function pageCampaign(id) {
  view.replaceChildren(h("p", { class: "muted" }, "Загрузка кампании…"));
  let campaign;
  try {
    campaign = await api("GET", `/api/campaigns/${id}`);
  } catch (err) {
    view.replaceChildren(h("p", { class: "error" }, err.message));
    return;
  }
  renderCampaign(campaign);
}

function renderCampaign(campaign) {
  const fetchBtn = h("button", {}, "Загрузить из Keitaro");
  fetchBtn.addEventListener("click", () =>
    busy(fetchBtn, async () => {
      renderCampaign(await api("POST", `/api/campaigns/${campaign.id}/sync`));
      toast("Состояние загружено из Keitaro");
    }),
  );

  const streamsBox = h("div");
  const update = (stream) => {
    const i = campaign.streams.findIndex((s) => s.id === stream.id);
    campaign.streams[i] = stream;
    drawStreams();
  };
  function drawStreams() {
    streamsBox.replaceChildren(...campaign.streams.map((s) => renderStream(s, update)));
  }
  drawStreams();

  view.replaceChildren(
    h("h1", {}, `${campaign.name} `, h("span", { class: "muted" }, `#${campaign.id} · ${campaign.alias}`)),
    h(
      "div",
      { class: "toolbar" },
      fetchBtn,
      h("a", { href: campaign.admin_url, target: "_blank", rel: "noopener" }, h("button", {}, "Открыть в Keitaro")),
      h("span", { class: "grow" }),
      h("span", { class: "muted" }, campaign.synced_at ? `Загружено: ${new Date(campaign.synced_at).toLocaleString()}` : ""),
    ),
    streamsBox,
  );
}

function describeFilters(stream) {
  if (!stream.filters.length) return "без фильтров";
  return stream.filters
    .map((f) => `${f.name} ${f.mode === "reject" ? "≠" : "="} ${(f.payload || []).join(", ")}`)
    .join("; ");
}

function renderStream(stream, update) {
  const call = (button, method, path, body) =>
    busy(button, async () => update(await api(method, `/api/streams/${stream.id}${path}`, body)));

  const head = h(
    "div",
    { class: "stream-head" },
    h("h2", {}, `Поток: ${stream.name} `, h("span", { class: "muted" }, `(#${stream.id}, ${stream.type})`)),
    h("span", { class: "muted" }, describeFilters(stream)),
    h("span", { class: "grow" }),
  );

  if (!stream.editable) {
    return h(
      "section",
      { class: "panel stream" },
      head,
      h("div", { class: "stream-body muted" }, `Действие: ${stream.action_type} → ${stream.action_payload || "—"}`),
    );
  }

  if (stream.dirty) {
    const push = h("button", { class: "primary" }, "Отправить в Keitaro");
    const cancel = h("button", {}, "Отменить");
    push.addEventListener("click", () =>
      busy(push, async () => {
        update(await api("POST", `/api/streams/${stream.id}/push`));
        toast("Изменения отправлены в Keitaro");
      }),
    );
    cancel.addEventListener("click", () => call(cancel, "POST", "/cancel"));
    head.append(h("span", { class: "muted" }, "черновик"), push, cancel);
  }

  const rows = stream.offers.map((offer) => {
    const removed = offer.state !== "active";
    const shareBtn = h("button", { class: "link", title: "Задать долю вручную (оффер закрепится)" }, `${offer.share}%`);
    shareBtn.addEventListener("click", () => {
      if (removed) return;
      const value = prompt(`Доля для оффера #${offer.offer_id}, %`, offer.share);
      if (value === null) return;
      const share = Number.parseInt(value, 10);
      if (Number.isNaN(share)) return toast("Нужно целое число", true);
      call(shareBtn, "POST", `/offers/${offer.offer_id}/share`, { share });
    });
    const pin = h(
      "button",
      { class: offer.pinned ? "pin on" : "pin", title: offer.pinned ? "Открепить долю" : "Закрепить долю", disabled: removed },
      "📌",
    );
    pin.addEventListener("click", () => call(pin, "POST", `/offers/${offer.offer_id}/pin`, { pinned: !offer.pinned }));

    const action = removed
      ? h("button", {}, "↺ Вернуть")
      : h("button", { class: "danger" }, "Удалить");
    action.addEventListener("click", () =>
      call(action, "POST", `/offers/${offer.offer_id}/${removed ? "restore" : "remove"}`),
    );

    const was = offer.changed && offer.kt_share !== null ? h("span", { class: "changed" }, `было ${offer.kt_share}%`) : null;
    return h(
      "tr",
      { class: removed ? "removed" : "" },
      h("td", {}, h("span", { class: "muted" }, `#${offer.offer_id} `), h("span", { class: "name" }, offer.name)),
      h("td", { class: "share" }, shareBtn, pin, was),
      h("td", { class: "actions" }, action),
    );
  });

  const table = h(
    "table",
    {},
    h("thead", {}, h("tr", {}, h("th", {}, "Оффер"), h("th", {}, "Доля"), h("th", {}, ""))),
    h("tbody", {}, rows.length ? rows : h("tr", {}, h("td", { colspan: 3, class: "muted" }, "В потоке нет офферов"))),
  );

  let toAdd = null;
  const addBtn = h("button", {}, "Добавить");
  const ac = offerAutocomplete({
    placeholder: "добавить оффер: id или название",
    onPick: (o) => (toAdd = o),
    exclude: () => new Set(stream.offers.filter((o) => o.state === "active").map((o) => o.offer_id)),
  });
  addBtn.addEventListener("click", () => {
    if (!toAdd) return toast("Выберите оффер из списка", true);
    call(addBtn, "POST", "/offers", { offer_id: toAdd.id });
  });

  const totalOk = stream.total === 100;
  const recount = h("button", {}, "Пересчитать");
  recount.addEventListener("click", () => call(recount, "POST", "/recount"));

  const foot = h(
    "div",
    { class: "stream-foot" },
    ac.el,
    addBtn,
    h("span", { class: totalOk ? "total muted" : "total bad" }, `Итого: ${stream.total}%`),
    totalOk ? null : recount,
  );

  return h("section", { class: stream.dirty ? "panel stream dirty" : "panel stream" }, head, table, foot);
}

// ---------- router ----------

function route() {
  const hash = location.hash || "#/new";
  document.querySelectorAll("[data-nav]").forEach((a) => {
    a.classList.toggle("active", hash.startsWith(`#/${a.dataset.nav}`));
  });
  const match = hash.match(/^#\/campaigns\/(\d+)/);
  if (match) return pageCampaign(match[1]);
  if (hash.startsWith("#/campaigns")) return pageCampaigns();
  return pageNew();
}

async function loadMeta() {
  try {
    const meta = await api("GET", "/api/meta");
    document.getElementById("meta").textContent =
      `Группа: ${meta.group} · Источник: ${meta.traffic_source} · Домен #${meta.domain_id}`;
  } catch (err) {
    document.getElementById("meta").textContent = err.message;
  }
}

window.addEventListener("hashchange", route);
route();
loadMeta();
