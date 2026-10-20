"use strict";

/* =========================================================================
   Helpers
   ========================================================================= */

const view = document.getElementById("view");

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key === "class") el.className = value;
    else if (key === "style") el.style.cssText = value;
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

const ICONS = {
  pin: '<path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  alert: '<circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
  chevron: '<path d="m6 9 6 6 6-6"/>',
  refresh: '<path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"/><path d="M3 21v-5h5"/><path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5"/>',
  external: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-1"/>',
  globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20"/>',
  box: '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5"/><path d="M12 13v8"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  percent: '<path d="M19 5 5 19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>',
  send: '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
  layers: '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/>',
};

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = ICONS[name] || "";
  return svg;
}

async function api(method, path, body) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("Сервер недоступен");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    let detail = data.detail;
    if (Array.isArray(detail)) detail = detail.map((d) => d.msg).join("; ");
    throw new Error(detail || `Ошибка ${response.status}`);
  }
  return data;
}

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

// Disables the button and shows a spinner in it while the action runs; errors become toasts.
async function busy(button, action) {
  let spinner;
  if (button) {
    button.disabled = true;
    spinner = h("span", { class: "spinner" });
    button.prepend(spinner);
  }
  try {
    return await action();
  } catch (err) {
    toast(err.message, "error");
    return undefined;
  } finally {
    if (button) {
      button.disabled = false;
      spinner.remove();
    }
  }
}

const OFFER_COLORS = ["#4f46e5", "#0e9384", "#f79009", "#e31b54", "#7a5af8", "#2e90fa", "#66c61c", "#dd2590"];

/* =========================================================================
   Toasts
   ========================================================================= */

function toast(text, type = "success") {
  const box = document.getElementById("toasts");
  const iconName = type === "error" ? "alert" : type === "info" ? "info" : "check";
  const close = () => {
    el.classList.add("leaving");
    setTimeout(() => el.remove(), 180);
  };
  const el = h(
    "div",
    { class: `toast ${type}`, role: type === "error" ? "alert" : "status" },
    h("span", { class: "toast-icon" }, icon(iconName)),
    h("div", { class: "toast-text" }, text),
    h("button", { class: "icon-btn", "aria-label": "Закрыть", onclick: close }, icon("x")),
  );
  box.append(el);
  while (box.children.length > 4) box.firstChild.remove();
  setTimeout(close, type === "error" ? 7000 : 3500);
}

/* =========================================================================
   Modal dialogs
   ========================================================================= */

// Resolves with the value given to close(); Esc, the backdrop and × resolve with null.
function openModal({ icon: iconName = "info", tone = "", title, subtitle, body, actions }) {
  return new Promise((resolve) => {
    const previousFocus = document.activeElement;
    const close = (value = null) => {
      document.removeEventListener("keydown", onKey, true);
      backdrop.classList.add("leaving");
      setTimeout(() => backdrop.remove(), 150);
      previousFocus?.focus?.();
      resolve(value);
    };
    const buttons = actions.map((a) =>
      h(
        "button",
        {
          class: `btn ${a.variant || ""}`,
          type: "button",
          onclick: () => (a.onClick ? a.onClick(close) : close(a.value)),
        },
        a.label,
      ),
    );
    const modal = h(
      "div",
      { class: "modal", role: "dialog", "aria-modal": "true", "aria-label": title },
      h(
        "div",
        { class: "modal-head" },
        h("div", { class: `modal-icon ${tone}` }, icon(iconName)),
        h(
          "div",
          { class: "grow" },
          h("h3", { class: "modal-title" }, title),
          subtitle ? h("div", { class: "modal-sub" }, subtitle) : null,
        ),
        h("button", { class: "icon-btn", "aria-label": "Закрыть", onclick: () => close(null) }, icon("x")),
      ),
      body ? h("div", { class: "modal-body" }, body) : null,
      h("div", { class: "modal-foot" }, buttons),
    );
    const backdrop = h("div", { class: "modal-backdrop" }, modal);
    backdrop.addEventListener("mousedown", (e) => {
      if (e.target === backdrop) close(null);
    });
    function onKey(e) {
      if (e.key === "Escape") {
        e.stopPropagation();
        close(null);
      } else if (e.key === "Tab") {
        const focusable = [...modal.querySelectorAll("button, input")].filter((x) => !x.disabled);
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", onKey, true);
    document.getElementById("modal-root").append(backdrop);
    (modal.querySelector("input") || buttons[buttons.length - 1]).focus();
  });
}

function confirmDialog({ title, text, confirmLabel = "Да", danger = false }) {
  return openModal({
    icon: "alert",
    tone: "warn",
    title,
    body: text,
    actions: [
      { label: "Отмена", value: false },
      { label: confirmLabel, variant: danger ? "btn-danger" : "btn-primary", value: true },
    ],
  }).then(Boolean);
}

function shareDialog(offer) {
  const number = h("input", { class: "input", type: "number", min: 0, max: 100, step: 1, value: offer.share });
  const range = h("input", { type: "range", min: 0, max: 100, step: 1, value: offer.share, "aria-label": "Доля" });
  const error = h("div", { class: "field-error" });
  number.addEventListener("input", () => (range.value = number.value));
  range.addEventListener("input", () => (number.value = range.value));

  const submit = (close) => {
    const value = Number(number.value);
    if (number.value.trim() === "" || !Number.isInteger(value) || value < 0 || value > 100) {
      error.textContent = "Нужно целое число от 0 до 100";
      number.classList.add("invalid");
      return;
    }
    close(value);
  };
  const body = h(
    "div",
    { class: "form" },
    h("div", { class: "share-input" }, range, h("div", { class: "num" }, number, h("span", {}, "%"))),
    error,
    h("div", { class: "field-hint" }, "Оффер закрепится на этой доле, остальные незакреплённые пересчитаются поровну."),
  );
  number.addEventListener("keydown", (e) => {
    if (e.key === "Enter") number.closest(".modal").querySelector(".btn-primary").click();
  });
  return openModal({
    icon: "percent",
    title: "Доля оффера",
    subtitle: `#${offer.offer_id} · ${offer.name}`,
    body,
    actions: [
      { label: "Отмена", value: null },
      { label: "Применить", variant: "btn-primary", onClick: submit },
    ],
  });
}

/* =========================================================================
   Custom dropdown (combobox)
   ========================================================================= */

// Wires an input inside `control` to a dropdown list. `load(query)` returns items
// (or a promise of them); `renderOption(item)` returns the option content.
function createCombo({ root, control, input, load, renderOption, onSelect, emptyText = "Ничего не найдено" }) {
  let items = [];
  let active = -1;
  let requestNo = 0;
  let menu = null;
  const listId = `combo-${Math.random().toString(36).slice(2, 8)}`;
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-controls", listId);
  input.setAttribute("aria-expanded", "false");

  function close() {
    menu?.remove();
    menu = null;
    root.classList.remove("open");
    input.setAttribute("aria-expanded", "false");
  }

  function showMenu(content) {
    if (!menu) {
      menu = h("ul", { class: "menu", id: listId, role: "listbox" });
      root.append(menu);
      root.classList.add("open");
      input.setAttribute("aria-expanded", "true");
    }
    menu.replaceChildren(...content);
  }

  function render() {
    if (!items.length) {
      showMenu([h("li", { class: "menu-note" }, emptyText)]);
      return;
    }
    showMenu(
      items.map((item, i) =>
        h(
          "li",
          {
            class: i === active ? "option active" : "option",
            role: "option",
            id: `${listId}-${i}`,
            "aria-selected": String(i === active),
            onmousedown: (e) => {
              e.preventDefault();
              pick(i);
            },
            onmousemove: () => {
              if (active !== i) {
                active = i;
                render();
              }
            },
          },
          renderOption(item),
        ),
      ),
    );
    if (active >= 0) {
      input.setAttribute("aria-activedescendant", `${listId}-${active}`);
      menu.children[active]?.scrollIntoView({ block: "nearest" });
    }
  }

  async function refresh() {
    const mine = ++requestNo;
    const slow = setTimeout(() => {
      if (mine === requestNo) showMenu([h("li", { class: "menu-note" }, h("span", { class: "spinner" }), "Ищу…")]);
    }, 150);
    try {
      const found = await load(input.value.trim());
      if (mine !== requestNo || document.activeElement !== input) return;
      items = found;
      active = items.length ? 0 : -1;
      render();
    } catch (err) {
      if (mine === requestNo) showMenu([h("li", { class: "menu-note" }, err.message)]);
    } finally {
      clearTimeout(slow);
    }
  }

  function pick(i) {
    const item = items[i];
    if (!item) return;
    close();
    onSelect(item);
  }

  const refreshSoon = debounce(refresh, 180);
  input.addEventListener("focus", () => {
    control.classList.add("focused");
    refresh();
  });
  input.addEventListener("blur", () => {
    control.classList.remove("focused");
    close();
  });
  input.addEventListener("input", refreshSoon);
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!menu) return refresh();
      if (!items.length) return;
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      render();
    } else if (e.key === "Enter" && (menu || input.value.trim())) {
      // Enter in a dropdown never submits the surrounding form.
      e.preventDefault();
      if (menu && active >= 0) pick(active);
    } else if (e.key === "Escape" && menu) {
      e.stopPropagation();
      close();
    }
  });
  control.addEventListener("mousedown", (e) => {
    if (e.target === control) {
      e.preventDefault();
      input.focus();
    }
  });
  return { refresh, close };
}

let countriesPromise;
// Cached, but a failed request is retried next time.
const once = (get, set, load) => get() ?? set(load().catch((err) => (set(undefined), Promise.reject(err))));
const loadCountries = () => once(() => countriesPromise, (v) => (countriesPromise = v), () => api("GET", "/api/countries"));

// Geo: several countries as chips, search by code or Russian/English name.
function geoPicker({ onChange }) {
  const selected = [];
  const input = h("input", { type: "text", placeholder: "MX, AU, RO… или название страны", autocomplete: "off" });
  const control = h("div", { class: "control" }, input);
  const root = h("div", { class: "combo" }, control);
  const changed = () => {
    renderChips();
    onChange?.(selected.map((c) => c.code));
  };

  // The input stays in place (moving it would drop the focus); chips go before it.
  function renderChips() {
    [...control.children].forEach((child) => child !== input && child.remove());
    control.insertBefore(icon("globe"), input);
    const chips = selected.map((c) =>
        h(
          "span",
          { class: "chip", title: c.name_en },
          h("span", { class: "chip-code" }, c.code),
          h("span", { class: "chip-name" }, c.name),
          h(
            "button",
            {
              type: "button",
              "aria-label": `Убрать ${c.name}`,
              onmousedown: (e) => e.preventDefault(),
              onclick: () => {
                selected.splice(selected.indexOf(c), 1);
                changed();
                input.focus();
              },
            },
            icon("x"),
          ),
        ),
    );
    chips.forEach((chip) => control.insertBefore(chip, input));
    input.placeholder = selected.length ? "ещё страна…" : "MX, AU, RO… или название страны";
  }

  const add = (country) => {
    if (!selected.some((c) => c.code === country.code)) selected.push(country);
  };

  async function load(q) {
    const all = await loadCountries();
    const taken = new Set(selected.map((c) => c.code));
    const query = q.toLowerCase();
    const upper = q.toUpperCase();
    const rank = (c) => (c.code === upper ? 0 : c.code.startsWith(upper) ? 1 : 2);
    return all
      .filter((c) => !taken.has(c.code))
      .filter((c) => !q || c.code.startsWith(upper) || c.name.toLowerCase().includes(query) || c.name_en.toLowerCase().includes(query))
      .sort((a, b) => rank(a) - rank(b))
      .slice(0, 60);
  }

  const combo = createCombo({
    root,
    control,
    input,
    load,
    emptyText: "Нет такой страны",
    renderOption: (c) => [
      h("span", { class: "code" }, c.code),
      h("div", { class: "option-main" }, h("div", { class: "option-title" }, c.name), h("div", { class: "option-sub" }, c.name_en)),
    ],
    onSelect: (c) => {
      add(c);
      input.value = "";
      changed();
      combo.refresh();
    },
  });

  // Typing or pasting "MX, AU ro" turns known codes into chips.
  input.addEventListener("input", async () => {
    if (!/[\s,;]/.test(input.value)) return;
    const all = await loadCountries();
    const parts = input.value.split(/[\s,;]+/);
    const rest = parts.pop();
    const unknown = [];
    for (const part of parts.filter(Boolean)) {
      const code = part.toUpperCase() === "UK" ? "GB" : part.toUpperCase();
      const country = all.find((c) => c.code === code);
      if (country) add(country);
      else unknown.push(part);
    }
    input.value = [...unknown, rest].filter(Boolean).join(" ");
    changed();
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Backspace" && !input.value && selected.length) {
      selected.pop();
      changed();
    }
  });

  renderChips();
  return {
    el: root,
    get value() {
      return selected.map((c) => c.code);
    },
    get pending() {
      return input.value.trim();
    },
    setInvalid(on) {
      control.classList.toggle("invalid", on);
    },
    clear() {
      selected.length = 0;
      input.value = "";
      changed();
    },
  };
}

// Offer: search Keitaro offers by id or name, one picked offer shown as a card.
function offerPicker({ onChange, exclude = () => new Set(), placeholder = "Поиск оффера: id или название" }) {
  let picked = null;
  const input = h("input", { type: "text", placeholder, autocomplete: "off" });
  const control = h("div", { class: "control" });
  const root = h("div", { class: "combo" }, control);

  function renderControl() {
    if (picked) {
      control.replaceChildren(
        h(
          "div",
          { class: "picked" },
          h("span", { class: "badge badge-id" }, `#${picked.id}`),
          h("span", { class: "picked-name", title: picked.name }, picked.name),
          picked.countries.length ? h("span", { class: "badge" }, picked.countries.join(", ")) : null,
          h(
            "button",
            {
              type: "button",
              class: "icon-btn",
              "aria-label": "Выбрать другой оффер",
              onclick: () => {
                set(null);
                input.focus();
              },
            },
            icon("x"),
          ),
        ),
      );
    } else {
      control.replaceChildren(icon("search"), input, h("span", { class: "caret" }, icon("chevron")));
    }
  }

  function set(offer) {
    picked = offer;
    input.value = "";
    renderControl();
    onChange?.(offer);
  }

  createCombo({
    root,
    control,
    input,
    load: async (q) => {
      const found = await api("GET", `/api/offers?q=${encodeURIComponent(q)}&limit=50`);
      const skip = exclude();
      return found.filter((o) => !skip.has(o.id));
    },
    emptyText: "Офферов не найдено",
    renderOption: (o) => [
      h("span", { class: "code" }, o.id),
      h(
        "div",
        { class: "option-main" },
        h("div", { class: "option-title", title: o.name }, o.name),
        o.countries.length ? h("div", { class: "option-sub" }, o.countries.join(", ")) : null,
      ),
    ],
    onSelect: set,
  });

  renderControl();
  return {
    el: root,
    get value() {
      return picked;
    },
    setInvalid(on) {
      control.classList.toggle("invalid", on);
    },
    clear: () => set(null),
  };
}

/* =========================================================================
   Pages
   ========================================================================= */

// Each navigation gets a number; async pages render only if still current.
let routeNo = 0;
const isCurrent = (no) => no === routeNo;

let metaPromise;
const loadMeta = () => once(() => metaPromise, (v) => (metaPromise = v), () => api("GET", "/api/meta"));

// ---------- new campaign ----------

function pageNew() {
  const nameInput = h("input", { class: "input", type: "text", placeholder: "Например, tg-test MX", maxlength: 200 });
  const errors = { name: h("div", { class: "field-error" }), geo: h("div", { class: "field-error" }), offer: h("div", { class: "field-error" }) };
  const preview = h("div", { class: "preview" });
  const result = h("div");

  const geo = geoPicker({ onChange: () => (updatePreview(), clearError("geo")) });
  const offer = offerPicker({ onChange: () => (updatePreview(), clearError("offer")) });
  nameInput.addEventListener("input", () => (updatePreview(), clearError("name")));

  function clearError(key) {
    errors[key].textContent = "";
    if (key === "name") nameInput.classList.remove("invalid");
    if (key === "geo") geo.setInvalid(false);
    if (key === "offer") offer.setInvalid(false);
  }

  function updatePreview() {
    loadMeta()
      .catch(() => null)
      .then((meta) => {
        const countries = geo.value;
        const picked = offer.value;
        preview.replaceChildren(
          row("Название", nameInput.value.trim() || h("span", { class: "placeholder" }, "не задано")),
          row("Группа", meta ? h("span", { class: "badge" }, meta.group) : "—"),
          row("Источник", meta ? h("span", { class: "badge" }, meta.traffic_source) : "—"),
          row("Домен", meta ? h("span", { class: "badge badge-id" }, `#${meta.domain_id}`) : "—"),
          h(
            "div",
            { class: "preview-flow" },
            h("div", { class: "flow-title" }, h("span", { class: "flow-num" }, "1"), "Flow 1 · гео-редирект"),
            h(
              "div",
              { class: "flow-line" },
              countries.length
                ? countries.map((c) => h("span", { class: "badge badge-accent" }, c))
                : h("span", { class: "placeholder" }, "страны не выбраны"),
              icon("arrow"),
              h("span", { class: "mono" }, meta ? meta.geo_redirect_url : "https://google.com"),
            ),
          ),
          h(
            "div",
            { class: "preview-flow" },
            h("div", { class: "flow-title" }, h("span", { class: "flow-num alt" }, "2"), "Flow 2 · остальной трафик"),
            h(
              "div",
              { class: "flow-line" },
              picked
                ? [h("span", { class: "badge badge-id" }, `#${picked.id}`), h("span", {}, picked.name), h("span", { class: "badge badge-success" }, "100%")]
                : h("span", { class: "placeholder" }, "оффер не выбран"),
            ),
          ),
        );
      });
  }
  const row = (k, v) => h("div", { class: "preview-row" }, h("span", { class: "k" }, k), h("div", {}, v));

  const submit = h("button", { class: "btn btn-primary btn-lg btn-block", type: "submit" }, icon("plus"), "Создать кампанию");
  const form = h(
    "form",
    { class: "form", novalidate: true, onsubmit: onSubmit },
    h("label", { class: "field" }, h("span", { class: "field-label" }, "Название кампании"), nameInput, errors.name),
    h(
      "div",
      { class: "field" },
      h("span", { class: "field-label" }, "Geo"),
      geo.el,
      h("span", { class: "field-hint" }, "Коды стран ISO, можно несколько: поток 1 ловит их и редиректит на google.com"),
      errors.geo,
    ),
    h("div", { class: "field" }, h("span", { class: "field-label" }, "Оффер"), offer.el, errors.offer),
    submit,
  );

  async function onSubmit(e) {
    e.preventDefault();
    let ok = true;
    const fail = (key, text, mark) => {
      errors[key].textContent = text;
      mark();
      ok = false;
    };
    if (!nameInput.value.trim()) fail("name", "Укажите название", () => nameInput.classList.add("invalid"));
    if (geo.pending) fail("geo", `Не распознано: «${geo.pending}». Выберите страну из списка`, () => geo.setInvalid(true));
    else if (!geo.value.length) fail("geo", "Выберите хотя бы одну страну", () => geo.setInvalid(true));
    if (!offer.value) fail("offer", "Выберите оффер из списка", () => offer.setInvalid(true));
    if (!ok) return;

    const picked = offer.value;
    const created = await busy(submit, () =>
      api("POST", "/api/campaigns", { name: nameInput.value.trim(), geo: geo.value.join(","), offer_id: picked.id }),
    );
    if (!created) return;
    toast("Кампания создана в Keitaro");
    result.replaceChildren(
      h(
        "div",
        { class: "card success-card", style: "margin-bottom:20px" },
        h(
          "div",
          { class: "card-body" },
          h(
            "div",
            { class: "success-title" },
            h("span", { class: "success-icon" }, icon("check")),
            h(
              "div",
              {},
              h("h2", {}, `Кампания «${created.name}» создана`),
              h(
                "div",
                { class: "subtitle" },
                h("span", { class: "badge badge-id" }, `#${created.id}`),
                h("span", { class: "badge badge-id" }, created.alias),
                `Flow 1: ${created.countries.join(", ")} → редирект · Flow 2: оффер #${picked.id}`,
              ),
            ),
          ),
          h(
            "div",
            { class: "actions-row" },
            h("a", { class: "btn btn-primary", href: `#/campaigns/${created.id}` }, icon("layers"), "Открыть в редакторе"),
            h("a", { class: "btn", href: created.admin_url, target: "_blank", rel: "noopener" }, icon("external"), "Открыть в Keitaro"),
          ),
        ),
      ),
    );
    nameInput.value = "";
    geo.clear();
    offer.clear();
    updatePreview();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  view.replaceChildren(
    h(
      "div",
      { class: "page-head" },
      h("div", { class: "grow" }, h("h1", {}, "Новая кампания"), h("div", { class: "subtitle" }, "Кампания с двумя потоками создаётся в Keitaro через Admin API")),
    ),
    result,
    h(
      "div",
      { class: "grid-2" },
      h("div", { class: "card" }, h("div", { class: "card-body" }, form)),
      h(
        "div",
        { class: "card" },
        h("div", { class: "card-head" }, h("h2", {}, "Что будет создано")),
        h("div", { class: "card-body" }, preview),
      ),
    ),
  );
  updatePreview();
  nameInput.focus();
}

// ---------- campaign list ----------

async function pageCampaigns(no) {
  const search = h("input", { class: "input input-search", type: "search", placeholder: "Поиск по названию, id или alias" });
  const body = h("tbody");
  const count = h("span");
  const table = h(
    "table",
    { class: "table" },
    h(
      "thead",
      {},
      h("tr", {}, h("th", {}, "ID"), h("th", {}, "Название"), h("th", { class: "hide-sm" }, "Alias"), h("th", { class: "hide-sm" }, "Группа"), h("th", { class: "hide-sm" }, "Создана")),
    ),
    body,
  );
  view.replaceChildren(
    h(
      "div",
      { class: "page-head" },
      h("div", { class: "grow" }, h("h1", {}, "Кампании Keitaro"), h("div", { class: "subtitle" }, "Выберите кампанию, чтобы открыть редактор офферов", count)),
    ),
    h("div", { class: "search-wrap", style: "margin-bottom:16px" }, icon("search"), search),
    h("div", { class: "card" }, table),
  );
  body.append(
    ...Array.from({ length: 6 }, () =>
      h("tr", {}, ...[60, 220, 160, 90, 120].map((w, i) => h("td", { class: i > 1 ? "hide-sm" : "" }, h("div", { class: "skeleton", style: `width:${w}px` })))),
    ),
  );

  let all = [];
  function render() {
    const q = search.value.trim().toLowerCase();
    const rows = all.filter((c) => !q || c.name.toLowerCase().includes(q) || String(c.id).includes(q) || c.alias.toLowerCase().includes(q));
    count.textContent = ` · ${rows.length} из ${all.length}`;
    body.replaceChildren(
      ...rows.map((c) =>
        h(
          "tr",
          { class: "clickable", onclick: () => (location.hash = `#/campaigns/${c.id}`) },
          h("td", { class: "mono" }, c.id),
          h(
            "td",
            {},
            h(
              "div",
              { class: "name-cell" },
              h("a", { href: `#/campaigns/${c.id}`, onclick: (e) => e.stopPropagation() }, c.name || "(без названия)"),
              c.created_here ? h("span", { class: "badge badge-success" }, "создана здесь") : null,
            ),
          ),
          h("td", { class: "mono muted hide-sm" }, c.alias),
          h("td", { class: "hide-sm" }, c.group ? h("span", { class: "badge" }, c.group) : ""),
          h("td", { class: "muted hide-sm" }, c.created_at || ""),
        ),
      ),
    );
    if (!rows.length) body.append(h("tr", {}, h("td", { colspan: 5, class: "empty" }, "Ничего не найдено")));
  }
  search.addEventListener("input", render);
  try {
    all = await api("GET", "/api/campaigns");
    if (!isCurrent(no)) return;
    render();
    search.focus();
  } catch (err) {
    if (isCurrent(no)) body.replaceChildren(h("tr", {}, h("td", { colspan: 5, class: "empty" }, err.message)));
  }
}

// ---------- campaign editor ----------

async function pageCampaign(id, no) {
  view.replaceChildren(h("div", { class: "card" }, h("div", { class: "empty" }, h("span", { class: "spinner", style: "display:inline-block;vertical-align:middle;margin-right:8px" }), "Загружаю кампанию из Keitaro…")));
  let campaign;
  try {
    campaign = await api("GET", `/api/campaigns/${id}`);
  } catch (err) {
    if (isCurrent(no)) view.replaceChildren(h("div", { class: "card" }, h("div", { class: "empty" }, err.message)));
    return;
  }
  if (isCurrent(no)) renderCampaign(campaign, no);
}

function renderCampaign(campaign, no) {
  const fetchBtn = h("button", { class: "btn" }, icon("refresh"), "Загрузить из Keitaro");
  fetchBtn.addEventListener("click", async () => {
    if (campaign.streams.some((s) => s.dirty)) {
      const ok = await confirmDialog({
        title: "Загрузить состояние из Keitaro?",
        text: "Несохранённый черновик будет потерян: офферы и доли станут такими, как сейчас в Keitaro.",
        confirmLabel: "Загрузить",
      });
      if (!ok) return;
    }
    const fresh = await busy(fetchBtn, () => api("POST", `/api/campaigns/${campaign.id}/sync`));
    if (!fresh || !isCurrent(no)) return;
    renderCampaign(fresh, no);
    toast("Состояние загружено из Keitaro", "info");
  });

  const streamsBox = h("div");
  const update = (stream) => {
    const i = campaign.streams.findIndex((s) => s.id === stream.id);
    campaign.streams[i] = stream;
    drawStreams();
  };
  const drawStreams = () => streamsBox.replaceChildren(...campaign.streams.map((s) => renderStream(s, update)));
  drawStreams();

  const synced = campaign.synced_at ? new Date(campaign.synced_at).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" }) : null;
  view.replaceChildren(
    h(
      "div",
      { class: "page-head" },
      h(
        "div",
        { class: "grow" },
        h("h1", {}, campaign.name),
        h(
          "div",
          { class: "subtitle" },
          h("span", { class: "badge badge-id" }, `#${campaign.id}`),
          h("span", { class: "badge badge-id" }, campaign.alias),
          campaign.created_here ? h("span", { class: "badge badge-success" }, "создана здесь") : null,
          synced ? h("span", {}, `загружено ${synced}`) : null,
        ),
      ),
      h("div", { class: "actions-row", style: "margin-top:0" }, fetchBtn, h("a", { class: "btn", href: campaign.admin_url, target: "_blank", rel: "noopener" }, icon("external"), "Открыть в Keitaro")),
    ),
    streamsBox,
  );
}

function filterBadges(stream) {
  if (!stream.filters.length) return [h("span", { class: "badge" }, "без фильтров")];
  return stream.filters.map((f) =>
    h("span", { class: "badge badge-accent" }, icon(f.name === "country" ? "globe" : "info"), `${f.name} ${f.mode === "reject" ? "≠" : "="} ${(f.payload || []).join(", ")}`),
  );
}

function renderStream(stream, update) {
  let card;
  const call = (button, path, body) =>
    busy(button, async () => {
      card.classList.add("locked");
      try {
        const fresh = await api("POST", `/api/streams/${stream.id}${path}`, body);
        update(fresh);
        return fresh;
      } finally {
        card.classList.remove("locked");
      }
    });

  const head = h(
    "div",
    { class: "card-head" },
    h("div", { class: "stream-title grow" }, h("h2", {}, stream.name), h("span", { class: "badge badge-id" }, `#${stream.id}`), h("span", { class: "badge" }, stream.type), ...filterBadges(stream)),
  );

  if (!stream.editable) {
    return h(
      "section",
      { class: "card stream" },
      head,
      h(
        "div",
        { class: "redirect-body" },
        h("span", { class: "muted" }, "Действие:"),
        h("span", { class: "badge" }, stream.action_type || "—"),
        icon("arrow"),
        stream.action_payload ? h("a", { class: "mono", href: stream.action_payload, target: "_blank", rel: "noopener" }, stream.action_payload) : "—",
      ),
    );
  }

  // Stable colours: by offer id rank within the stream.
  const colorOf = new Map([...stream.offers].sort((a, b) => a.offer_id - b.offer_id).map((o, i) => [o.offer_id, OFFER_COLORS[i % OFFER_COLORS.length]]));
  const active = stream.offers.filter((o) => o.state === "active");

  let draftBar = null;
  if (stream.dirty) {
    const push = h("button", { class: "btn btn-primary btn-sm" }, icon("send"), "Отправить в Keitaro");
    const cancel = h("button", { class: "btn btn-sm" }, "Отменить");
    push.addEventListener("click", async () => {
      const ok = await openModal({ icon: "send", title: "Отправить изменения в Keitaro?", subtitle: `Поток ${stream.name} · #${stream.id}`, body: changesList(stream, colorOf), actions: [{ label: "Отмена", value: false }, { label: "Отправить", variant: "btn-primary", value: true }] });
      if (!ok) return;
      const fresh = await call(push, "/push");
      if (fresh) toast("Изменения отправлены в Keitaro");
    });
    cancel.addEventListener("click", () => call(cancel, "/cancel").then((fresh) => fresh && toast("Черновик отменён", "info")));
    draftBar = h("div", { class: "draft-bar" }, icon("info"), h("span", { class: "grow" }, "Черновик: изменения ещё не отправлены в Keitaro"), cancel, push);
  }

  const bar = h(
    "div",
    { class: "share-bar", role: "img", "aria-label": active.map((o) => `${o.name}: ${o.share}%`).join(", ") },
    active.filter((o) => o.share > 0).map((o) => h("span", { style: `width:${o.share}%;background:${colorOf.get(o.offer_id)}`, title: `#${o.offer_id} · ${o.share}%` })),
  );

  const rows = stream.offers.map((offer) => {
    const removed = offer.state === "removed";
    const disabled = offer.state === "disabled";
    const inactive = removed || disabled;

    const shareBtn = h("button", { class: "share-pill", disabled: inactive, title: inactive ? null : "Задать долю вручную" }, `${offer.share}%`);
    shareBtn.addEventListener("click", async () => {
      const value = await shareDialog(offer);
      if (value === null || value === offer.share) return;
      call(shareBtn, `/offers/${offer.offer_id}/share`, { share: value });
    });
    const pin = h("button", { class: offer.pinned ? "pin-btn on" : "pin-btn", disabled: inactive, title: offer.pinned ? "Открепить долю" : "Закрепить долю", "aria-pressed": String(offer.pinned) }, icon("pin"));
    pin.addEventListener("click", () => call(pin, `/offers/${offer.offer_id}/pin`, { pinned: !offer.pinned }));

    let action;
    if (disabled) {
      action = h("span", { class: "badge", title: "Включите оффер в самом Keitaro" }, "выключен в Keitaro");
    } else if (removed) {
      action = h("button", { class: "btn btn-sm" }, icon("undo"), "Вернуть");
      action.addEventListener("click", () => call(action, `/offers/${offer.offer_id}/restore`));
    } else {
      action = h("button", { class: "btn btn-sm btn-danger-text" }, icon("trash"), "Удалить");
      action.addEventListener("click", () => call(action, `/offers/${offer.offer_id}/remove`));
    }

    let note = null;
    if (removed) note = offer.kt_share !== null ? "удалён в черновике" : "удалён";
    else if (disabled) note = "не участвует в распределении";
    else if (offer.kt_share === null) note = "новый в черновике";
    const was = offer.changed && offer.kt_share !== null && !disabled ? h("span", { class: "share-was" }, "было ", h("s", {}, `${offer.kt_share}%`)) : h("span", { class: "share-was" });

    return h(
      "li",
      { class: `offer-row ${offer.state}` },
      h(
        "div",
        { class: "offer-main" },
        h("span", { class: "offer-dot", style: `background:${colorOf.get(offer.offer_id)}` }),
        h("span", { class: "badge badge-id" }, `#${offer.offer_id}`),
        h("div", { class: "offer-text" }, h("div", { class: "offer-name", title: offer.name }, offer.name), note ? h("div", { class: "offer-note" }, note) : null),
      ),
      h("div", { class: "share" }, was, shareBtn, pin),
      h("div", { class: "row-actions" }, action),
    );
  });

  const addBtn = h("button", { class: "btn" }, icon("plus"), "Добавить");
  const picker = offerPicker({
    placeholder: "Добавить оффер: id или название",
    exclude: () => new Set(stream.offers.filter((o) => o.state !== "removed").map((o) => o.offer_id)),
  });
  addBtn.addEventListener("click", () => {
    if (!picker.value) {
      picker.setInvalid(true);
      return toast("Выберите оффер из списка", "error");
    }
    call(addBtn, "/offers", { offer_id: picker.value.id });
  });

  const totalOk = stream.total === 100;
  const recount = h("button", { class: "btn btn-sm" }, icon("refresh"), "Пересчитать");
  recount.addEventListener("click", () => call(recount, "/recount"));

  card = h(
    "section",
    { class: stream.dirty ? "card stream dirty" : "card stream" },
    head,
    draftBar,
    active.length ? bar : null,
    h("ul", { class: "offers" }, rows.length ? rows : h("li", { class: "empty" }, "В потоке нет офферов")),
    h(
      "div",
      { class: "stream-foot" },
      picker.el,
      addBtn,
      h("span", { class: totalOk ? "total" : "total bad" }, `Итого ${stream.total}%`),
      !totalOk && active.length ? recount : null,
    ),
  );
  return card;
}

// What a push will change, for the confirmation dialog.
function changesList(stream, colorOf) {
  const lines = stream.offers
    .filter((o) => o.state !== "disabled")
    .filter((o) => o.changed || (o.state === "active" && o.kt_share === null))
    .map((o) => {
      let text;
      if (o.state === "removed") text = "удалить из потока";
      else if (o.kt_share === null) text = `добавить, ${o.share}%`;
      else text = `${o.kt_share}% → ${o.share}%`;
      return h(
        "div",
        { class: "flow-line", style: "padding:4px 0" },
        h("span", { class: "offer-dot", style: `background:${colorOf.get(o.offer_id)}` }),
        h("span", { class: "badge badge-id" }, `#${o.offer_id}`),
        h("span", { style: "flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" }, o.name),
        h("strong", {}, text),
      );
    });
  return h("div", {}, lines.length ? lines : "Изменений нет");
}

/* =========================================================================
   Router
   ========================================================================= */

function route() {
  const no = ++routeNo;
  const hash = location.hash || "#/new";
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", hash.startsWith(`#/${a.dataset.nav}`)));
  const match = hash.match(/^#\/campaigns\/(\d+)/);
  if (match) return pageCampaign(match[1], no);
  if (hash.startsWith("#/campaigns")) return pageCampaigns(no);
  return pageNew(no);
}

async function showMeta() {
  const box = document.getElementById("meta");
  try {
    const meta = await loadMeta();
    box.replaceChildren(
      h("span", { class: "badge" }, "Группа: ", h("strong", {}, meta.group)),
      h("span", { class: "badge" }, "Источник: ", h("strong", {}, meta.traffic_source)),
      h("span", { class: "badge badge-id" }, `домен #${meta.domain_id}`),
    );
  } catch (err) {
    box.replaceChildren(h("span", { class: "badge badge-warning" }, err.message));
  }
}

window.addEventListener("hashchange", route);
route();
showMeta();
