# FastLink Bot

Telegram-бот для продажи VPN-подписок на базе [Marzban](https://github.com/Gozargah/Marzban) + Xray Reality.
Пользователь покупает подписку прямо в Telegram, получает ссылку и QR-код — без регистрации и личного кабинета.

---

## Стек технологий

| Компонент | Технология |
|---|---|
| Bot framework | aiogram 3 (webhook / polling) |
| База данных | PostgreSQL 16 (SQLAlchemy 2.0 async + Alembic) |
| Кэш / координация | Redis 7 (FSM, rate limiting, idempotency, locks, sessions) |
| Планировщик задач | APScheduler + ARQ (worker) |
| HTTP-клиент | httpx (async) |
| VPN backend | Marzban + Xray Reality |
| Платёжная система | YooKassa |
| Конфигурация | Pydantic Settings v2 |
| Логирование | structlog |
| Контейнеризация | Docker + Docker Compose |
| Веб-сервер / прокси | Nginx (reverse proxy + SNI stream routing) |
| TLS | Let's Encrypt (Certbot) |
| Безопасность | UFW + iptables, Fail2ban |

---

## Архитектура

```
Telegram  ──►  Nginx (SNI router, TLS)  ──►  FastLink Bot (webhook :8080)
YooKassa  ──►  Nginx                    ──►  FastLink Bot (webhook :8080)
                     │
                     └──►  Marzban API (host:8000)  ──►  Xray Reality (VPN)

Nginx также проксирует:
  /sub      → Marzban subscription endpoint
  /metrics  → metrics-agent (127.0.0.1:9100)
  /health   → FastLink Bot health endpoint

FastLink Docker stack (bridge-сеть bot-net):
  bot      — Telegram webhook handler, handlers, middlewares
  worker   — APScheduler + ARQ: планировщик, фоновые задачи
  postgres — PostgreSQL 16-alpine
  redis    — Redis 7-alpine

Marzban запущен отдельно в host-network (/opt/marzban).
FastLink обращается к нему через host.docker.internal:8000.
```

---

## Структура проекта

```
fastlink-bot/
├── bot.py                            # Точка входа Telegram-бота
├── worker.py                         # Точка входа worker (scheduler + ARQ)
├── config.py                         # Pydantic Settings — вся конфигурация
├── requirements.txt                  # Runtime-зависимости
├── requirements-dev.txt              # Dev-зависимости (ruff, pre-commit)
├── Dockerfile
├── docker-compose.yml                # Production (VPS)
├── docker-compose.local.example.yml  # Шаблон для локальной разработки
├── .env.example                      # Шаблон переменных окружения
├── .env.production.template          # Шаблон для GitHub Actions (envsubst)
│
├── database/
│   ├── base.py                       # Declarative base SQLAlchemy
│   ├── engine.py                     # Async engine + pool
│   ├── session.py                    # AsyncSessionmaker / dependency
│   ├── models.py                     # ORM-модели (10 таблиц)
│   ├── enums.py                      # Python StrEnum → PostgreSQL Enum
│   ├── repo/                         # Repository layer (CRUD per entity)
│   ├── views.sql                     # SQL views (active_subscriptions, stats)
│   ├── functions.sql                 # SQL functions (get_expiring, renewal)
│   ├── triggers.sql                  # Triggers (last_active_at, status log)
│   └── indexes.sql                   # Дополнительные индексы
│
├── alembic/                          # Миграции Alembic
│   ├── env.py
│   └── versions/
│
├── handlers/
│   ├── client/                       # Клиентские обработчики (/start, покупка, подписки)
│   └── admin/                        # Админ-панель
│
├── middlewares/                      # Auth, throttling, logging, DB session
├── keyboards/                        # Inline / reply клавиатуры
├── services/                         # Бизнес-логика (subscription, payment, marzban, ...)
├── scheduler/                        # APScheduler jobs runner
├── webhooks/                         # Telegram webhook + YooKassa webhook endpoint
├── utils/                            # Форматтеры, QR-код, утилиты
└── logs/                             # Логи (gitignored, кроме .gitkeep)
```

---

## Локальный запуск

### Требования

- Docker Desktop с WSL 2 (или Docker Engine на Linux)
- Git
- Отдельный Telegram-бот для разработки (создать через [@BotFather](https://t.me/BotFather))

### Шаги

**1. Клонировать репозиторий и переключиться на ветку `dev`:**

```bash
git clone git@github.com:Svyatofslav/fastlink-bot.git
cd fastlink-bot
git checkout dev
```

**2. Создать локальный docker-compose из шаблона:**

```bash
cp docker-compose.local.example.yml docker-compose.local.yml
```

**3. Создать файл переменных окружения:**

```bash
cp .env.example .env.local
```

Открыть `.env.local` и заполнить обязательные поля:

```dotenv
BOT_TOKEN=<токен от @BotFather для dev-бота>
OWNER_TELEGRAM_ID=<твой Telegram ID, узнать у @userinfobot>
```

Значения `POSTGRES_*` и `REDIS_PASSWORD` прописаны дефолтными в `docker-compose.local.yml` — менять их не нужно, если нет особых причин. Убедись что в `.env.local` они совпадают с тем, что в `docker-compose.local.yml`.

> **Важно:** `USE_WEBHOOK=false` — бот запускается в режиме polling, webhook и домен не нужны.

**4. Запустить стек:**

```bash
docker compose -f docker-compose.local.yml up --build
```

**5. Применить миграции** (в новом терминале):

```bash
docker compose -f docker-compose.local.yml exec bot alembic upgrade head
```

**6. Проверить:**

- Бот отвечает на `/start` в Telegram
- PostgreSQL доступен на `localhost:5432`
- Redis доступен на `localhost:6379`

### Остановка

```bash
docker compose -f docker-compose.local.yml down
```

Данные PostgreSQL сохраняются в Docker volume `postgres-local-data`.
Для полного сброса (удаление данных):

```bash
docker compose -f docker-compose.local.yml down -v
```

---

## Переменные окружения

Полный список переменных с описанием — в файле [`.env.example`](.env.example).

Обязательные секреты (без них бот не запустится):

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен Telegram-бота от @BotFather |
| `OWNER_TELEGRAM_ID` | Telegram ID владельца (доступ к admin-панели) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Доступ к PostgreSQL |
| `REDIS_PASSWORD` | Пароль Redis |
| `MARZBAN_USERNAME` / `MARZBAN_PASSWORD` | Доступ к Marzban API |
| `WEBHOOK_SECRET` | Секрет Telegram webhook |
| `METRICS_TOKEN` | Bearer-токен для `/metrics` endpoint |
| `YOOKASSA_SHOP_ID` / `YOOKASSA_SECRET_KEY` | Доступ к YooKassa API |

---

## Deploy на VPS

### Инфраструктура

VPS: Ubuntu 22.04 LTS, проект живёт в `/opt/fastlink-bot`.
Деплой происходит автоматически через GitHub Actions при пуше в ветку `main`.

### Первый деплой (ручной)

```bash
# На VPS, в /opt/fastlink-bot
git pull origin main

# Создать .env из шаблона, передав все секреты через окружение
export BOT_TOKEN="..."
export POSTGRES_USER="..."
# ... и остальные переменные из .env.production.template
envsubst < .env.production.template > .env

# Поднять стек
docker compose up --build -d

# Применить миграции
docker compose exec bot alembic upgrade head

# Проверить
curl -fsS https://fastlinkproject.com/health
```

### Автоматический деплой (GitHub Actions)

После настройки CI/CD деплой выглядит так:

```
git push origin dev
# → открыть Pull Request dev → main
# → merge → GitHub Actions автоматически:
#    1. Подключается к VPS по SSH
#    2. git pull origin main
#    3. envsubst < .env.production.template > .env  (секреты из GitHub Secrets)
#    4. docker compose up --build -d
#    5. docker compose exec bot alembic upgrade head
#    6. curl health-check — деплой считается успешным
```

> Настройка GitHub Actions описана в `.github/workflows/deploy.yml` (добавляется отдельно).

### Мониторинг на VPS

```bash
# Статус контейнеров
docker compose ps

# Логи бота в реальном времени
docker compose logs -f bot

# Логи воркера
docker compose logs -f worker

# Health-check
curl -fsS https://fastlinkproject.com/health
```

---

## Git-workflow

```
main   — стабильная production-ветка, деплой только через PR
dev    — основная ветка разработки
```

**Стандартный рабочий процесс:**

```bash
git checkout dev
git pull origin dev

# ... вносим изменения ...

git add .
git commit -m "feat: описание изменения"
git push origin dev

# Когда готово к деплою — открыть PR dev → main на GitHub
```

**Миграции Alembic** генерируются локально и коммитятся в репозиторий:

```bash
# На локалке (WSL)
docker compose -f docker-compose.local.yml exec bot \
  alembic revision --autogenerate -m "описание изменения"

git add alembic/versions/
git commit -m "migration: описание изменения"
```

---

## Полезные команды

```bash
# Пересборка после изменений в коде (production)
docker compose up --build -d

# Пересборка локально
docker compose -f docker-compose.local.yml up --build

# Проверка переменных окружения внутри контейнера
docker compose exec bot env | sort

# Подключение к PostgreSQL (production)
docker compose exec postgres psql -U ${POSTGRES_USER} -d ${POSTGRES_DB}

# Подключение к PostgreSQL (локально, дефолтные значения из docker-compose.local.yml)
docker compose -f docker-compose.local.yml exec postgres \
  psql -U fastlink_local -d fastlink_local

# Подключение к Redis
docker compose exec redis redis-cli -a "$REDIS_PASSWORD"

# Проверка структуры БД
docker compose exec postgres psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c "\dt"
```

---

## Безопасность

- `.env` и `.env.*` добавлены в `.gitignore` — секреты не попадают в репозиторий
- В репозитории хранятся только шаблоны: `.env.example` и `.env.production.template`
- Production-секреты хранятся в GitHub Actions Secrets и подставляются через `envsubst` при деплое
- Токены Marzban API кэшируются в Redis (DB 5, TTL 23 ч) — не хранятся в открытом виде в коде
- Webhook endpoint защищён `WEBHOOK_SECRET`, metrics endpoint — Bearer-токеном
