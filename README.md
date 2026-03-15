# Сервис сокращения ссылок (Link Shortener API)

FastAPI-сервис для создания, управления и аналитики коротких ссылок с кэшированием через Redis.

## Описание API

### Аутентификация

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/auth/register` | Регистрация пользователя |
| POST | `/auth/login` | Вход (получение JWT-токена) |

### Ссылки

| Метод | Endpoint | Описание | Авторизация |
|-------|----------|----------|-------------|
| POST | `/links/shorten` | Создать короткую ссылку | Опционально |
| GET | `/links/{short_code}` | Редирект на оригинальный URL | Нет |
| PUT | `/links/{short_code}` | Обновить URL короткой ссылки | Обязательно |
| DELETE | `/links/{short_code}` | Удалить ссылку | Обязательно |
| GET | `/links/{short_code}/stats` | Статистика по ссылке | Нет |
| GET | `/links/search/?original_url=...` | Поиск по оригинальному URL | Нет |
| GET | `/links/expired/history` | История истекших ссылок | Нет |
| DELETE | `/links/cleanup/unused?days=N` | Удаление неиспользуемых ссылок | Нет |

### Примеры запросов

**Создание короткой ссылки:**
```bash
curl -X POST "http://localhost:8000/links/shorten" \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://example.com/long-url"}'
```

**С кастомным alias и временем жизни:**
```bash
curl -X POST "http://localhost:8000/links/shorten" \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://example.com", "custom_alias": "my-link", "expires_at": "2026-12-31T23:59:00"}'
```

**Регистрация и вход:**
```bash
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username": "user1", "email": "user@example.com", "password": "secret123"}'

curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "user1", "password": "secret123"}'
```

**Обновление/удаление (с токеном):**
```bash
curl -X PUT "http://localhost:8000/links/abc123" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://new-url.com"}'

curl -X DELETE "http://localhost:8000/links/abc123" \
  -H "Authorization: Bearer <token>"
```

## Инструкция по запуску

### Локально (с SQLite и без Redis)

```bash
cd link_shortener
python -m venv venv
source venv/bin/activate  # или venv\Scripts\activate на Windows
pip install -r requirements.txt

# SQLite и фейковый Redis (кэш отключится при недоступности Redis)
uvicorn app.main:app --reload
```

### С Docker

```bash
docker-compose up --build
```

Сервис будет доступен на http://localhost:8000. Документация API: http://localhost:8000/docs

## Описание БД

**Таблица `users`:**
| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER | PK |
| username | VARCHAR(100) | Уникальное имя |
| email | VARCHAR(255) | Уникальный email |
| hashed_password | VARCHAR(255) | Хэш пароля |
| created_at | TIMESTAMP | Дата регистрации |

**Таблица `links`:**
| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER | PK |
| short_code | VARCHAR(50) | Уникальный короткий код |
| original_url | VARCHAR(2048) | Оригинальный URL |
| created_at | TIMESTAMP | Дата создания |
| expires_at | TIMESTAMP | Время истечения (nullable) |
| expired_at | TIMESTAMP | Фактическое время истечения |
| is_expired | BOOLEAN | Флаг истечения |
| click_count | INTEGER | Количество переходов |
| last_used_at | TIMESTAMP | Дата последнего перехода |
| project_name | VARCHAR(100) | Название проекта (группировка) |
| created_by_user_id | INTEGER | FK на users (nullable) |

## Кэширование

- **Редирект** (`redirect:{short_code}`): TTL 1 час
- **Статистика** (`stats:{short_code}`): TTL 1 минута  
- **Поиск** (`search:{url}`): TTL 2 минуты

При обновлении и удалении ссылки соответствующие записи кэша инвалидируются.
