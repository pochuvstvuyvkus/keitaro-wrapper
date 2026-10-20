# Keitaro wrapper

Тестовое задание AD Robot («Это Легко»): обёртка над Keitaro Admin API на FastAPI + SQLAlchemy.

1. **Создаватор кампаний.** Форма Name / Geo / Offer (автокомплит по офферам Keitaro) создаёт кампанию
   с доменом, группой и источником и двумя потоками: поток 1 ловит указанные страны и редиректит на
   google.com, поток 2 отправляет остальной трафик на выбранный оффер.
2. **Редактор кампании.** Добавление, удаление и возврат офферов в потоке с пересчётом долей,
   как в эталонном редакторе из видео: изменения копятся черновиком и уходят в Keitaro по кнопке.

## Быстрый старт

Нужен Python 3.12+ и [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env          # вписать KEITARO_API_KEY
uv sync                       # зависимости
uv run alembic upgrade head   # миграции (по умолчанию SQLite-файл adrobot.db)
uv run uvicorn app.main:app --reload --port 8000
```

Открыть http://localhost:8000. Документация API (Swagger): http://localhost:8000/docs.

Тесты и линтер:

```bash
uv run pytest
uv run ruff check .
```

Без uv: `python -m venv .venv && . .venv/bin/activate && pip install fastapi "uvicorn[standard]" sqlalchemy alembic httpx pydantic-settings pycountry pytest ruff`, дальше те же команды без `uv run`.

## Настройка (.env)

| Переменная | По умолчанию | Что это |
|---|---|---|
| `KEITARO_URL` | `https://tlgk.host` | адрес трекера |
| `KEITARO_API_KEY` | — | ключ Admin API: админка → Профиль → API ключи |
| `KEITARO_USER_AGENT` | Chrome UA | Cloudflare перед трекером отвечает 403 на небраузерный User-Agent |
| `KEITARO_GROUP_ID` | `4970` | группа новых кампаний (FORTESTS) |
| `KEITARO_TRAFFIC_SOURCE_ID` | `473` | источник (FORTESTS) |
| `KEITARO_DOMAIN_ID` | `4622` | домен (in.posdk.xyz, как у эталонной кампании) |
| `GEO_REDIRECT_URL` | `https://google.com` | куда поток 1 редиректит выбранные страны |
| `DATABASE_URL` | `adrobot.db` в папке проекта | любая БД SQLAlchemy, например `postgresql+psycopg://user:pass@localhost/adrobot` (нужен драйвер `psycopg`) |
| `OFFERS_CACHE_TTL` | `300` | сколько секунд кешировать список офферов для автокомплита |

Настройки читаются из переменных окружения, `.env` и `.env.local`. Оба файла в `.gitignore`.

Id группы и источника видны в API: `GET /admin_api/v1/groups?type=campaigns` и `GET /admin_api/v1/traffic_sources`.
Список доменов у тестового ключа закрыт (`/domains` пустой), поэтому домен задаётся id; 4622 взят у эталонной
кампании из ТЗ (`campaign 2`, id 93212).

## Что создаётся в Keitaro

Структура повторяет эталонную кампанию 93212 (скриншот в ТЗ):

```
POST /campaigns  {name, alias, type: position, group_id, traffic_source_id, domain_id,
                 cost_type: CPC, cost_auto: true, uniqueness_method: ip_ua,
                 parameters: <параметры источника>}
POST /streams    Flow 1: regular, position 1, schema redirect, action http → https://google.com,
                 filters [{name: country, mode: accept, payload: ["MX", "AU"]}]
POST /streams    Flow 2: regular, position 2, schema landings, offers [{offer_id, share: 100}]
```

Параметры кампании (utm_source, sub_id_1 = utm_placement и т.д.) копируются из источника FORTESTS:
админка Keitaro делает это сама при выборе источника, а API нет. У эталонной кампании они совпадают
с параметрами источника один в один. Галочка «Из параметра 'cost'» со скриншота — это `cost_auto`.

Geo принимает один или несколько кодов ISO 3166-1 (`MX`, `mx, au; RO`, `UK` как `GB`); неизвестные
коды отклоняются.
Оффер проверяется по списку активных офферов Keitaro. Если поток создать не удалось, кампания удаляется
(в архив Keitaro), чтобы не оставлять половину.

## Редактор: как считаются доли

Логика снята с видео «keitaro wrapper - test»:

- Закреплённые (📌) офферы сохраняют свою долю. Остаток до 100% делится поровну между остальными
  активными офферами, а остаток от деления по 1% получают последние по порядку добавления:
  3 оффера → 33/33/34, 4 → 25×4, 5 → 20×5.
- **Добавить** оффер → пересчёт. **Удалить** → оффер остаётся в списке серым с 0% и кнопкой
  **Вернуть**; вернувшийся встаёт в конец (как и в Keitaro). Пример из видео: закреплён 25%,
  вернули оффер → 38 / 37 / 25.
- Клик по доле задаёт её вручную, оффер при этом закрепляется, остальные пересчитываются.
- Удалённый и тут же возвращённый в одном черновике оффер встаёт на своё место, доли не меняются.
- Изменения — черновик (жёлтый фон, «было N%»). **Отправить в Keitaro** шлёт
  `PUT /streams/{id}` с полным списком офферов, **Отменить** возвращает состояние Keitaro.
- **Загрузить из Keitaro** подтягивает фактическое состояние. Офферы, которые удалили прямо в Keitaro,
  помечаются удалёнными; доли показываются как есть, даже если не дают 100%, кнопка «Пересчитать»
  выравнивает их.
- Перед отправкой: сумма активных долей должна быть ровно 100% и в потоке должен быть хотя бы один оффер
  (Keitaro сам этого не проверяет). Если поток успели изменить в Keitaro после загрузки, отправка
  отклоняется (409), чтобы не затереть чужие правки.

Сам алгоритм — чистая функция `app/services/shares.py::rebalance`, сценарии из видео покрыты
тестами в `tests/test_shares.py` и `tests/test_api.py::test_editor_replays_reference_video`.

## Устройство

```
app/
  main.py               FastAPI, статика, обработка ошибок
  config.py             настройки (pydantic-settings)
  db.py, models.py      SQLAlchemy 2.0: campaigns, streams, stream_offers, offers_cache, audit_log
  keitaro/client.py     клиент Admin API (httpx)
  keitaro/payloads.py   сборка тел запросов, разбор Geo
  services/shares.py    пересчёт долей
  services/editor.py    черновик потока: add / remove / restore / pin / push / cancel / sync
  services/creator.py   создание кампании
  api/routes.py         REST API (/api/...)
  static/               фронт: HTML + vanilla JS, без сборки
alembic/                миграции
tests/                  pytest; Keitaro подменён in-memory фейком через httpx.MockTransport
```

В БД хранится то, чего нет в Keitaro: черновик долей, закрепления, история удалённых офферов
(чтобы их можно было вернуть), кеш офферов и журнал отправленных запросов (`audit_log`).

REST API:

| Метод | Путь | |
|---|---|---|
| GET | `/api/meta` | группа, источник и домен для новых кампаний |
| GET | `/api/offers?q=` | поиск офферов (id или название) |
| POST | `/api/campaigns` | создать кампанию `{name, geo, offer_id}` |
| GET | `/api/campaigns?q=` | список кампаний Keitaro |
| GET | `/api/campaigns/{id}` | кампания с потоками (при первом открытии загружается из Keitaro) |
| POST | `/api/campaigns/{id}/sync` | загрузить из Keitaro |
| POST | `/api/streams/{id}/offers` | добавить оффер `{offer_id}` |
| POST | `/api/streams/{id}/offers/{offer_id}/remove` / `restore` | удалить / вернуть |
| POST | `/api/streams/{id}/offers/{offer_id}/pin` | закрепить `{pinned}` |
| POST | `/api/streams/{id}/offers/{offer_id}/share` | задать долю вручную `{share}` |
| POST | `/api/streams/{id}/recount` / `cancel` / `push` | пересчитать / отменить / отправить |

## Ограничения

- Офферы, выключенные в самом Keitaro (`state: disabled`), редактор показывает, но не меняет:
  они не входят в 100% и отправляются обратно выключенными.
- Права тестового API-ключа ограничены: `/offers` отдаёт только часть офферов. Офферы, которые
  уже стоят в потоке, но не видны ключу, показываются по id и сохраняются при отправке.
- Однопользовательский режим: черновик один на поток, без авторизации.
