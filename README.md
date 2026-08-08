# Лабораторный реестр ДНК

Веб-приложение для ведения лабораторного ДНК-реестра: партии, объекты, этапы работ, исполнители, импорт/экспорт Excel, RT/qPCR-данные, отчёты и аудит изменений.

Проект рассчитан на запуск через Docker Compose: frontend собирается на React/Vite, backend работает на FastAPI, данные хранятся в PostgreSQL, миграции выполняются через Alembic.

## Возможности

- Импорт лабораторных Excel-реестров с preview перед записью в базу.
- Ведение партий и объектов с историей повторяемых этапов.
- Массовое заполнение этапов по выбранным партиям и объектам.
- Импорт RT/qPCR-файлов `.xls`, `.xlsx`, `.csv`.
- Экспорт реестра обратно в Excel-формат.
- Пакетная сортировка DOCX по списку номеров и сборка PDF для печати.
- Справочники сотрудников и лабораторных значений.
- Поиск по объектам, партиям, этапам, исполнителям и RT-результатам.
- Отчёты по партиям, ходу работ, статистике и контрольным полям.
- Ролевая модель доступа: `admin`, `user`, `viewer`.

Подробная карта системы находится в [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md), история изменений - в [CHANGELOG.md](CHANGELOG.md).

## Стек

- Backend: FastAPI, SQLAlchemy async, Alembic.
- Database: PostgreSQL 16.
- Frontend: React, TypeScript, Vite.
- Excel: `python-calamine`, `openpyxl`.
- PDF/печать: LibreOffice headless, `pypdf`, PyMuPDF.
- Runtime: Docker Compose, nginx.

## Быстрый запуск

```bash
git clone https://github.com/DrCramer/dna_base.git
cd dna_base
cp .env.example .env
docker compose up -d --build
```

Открыть приложение:

```text
http://localhost:4001
```

Dev-логины при стандартной локальной сборке:

```text
admin / admin123
user / user123
viewer / viewer123
```

## Настройка окружения

Файл `.env` не хранится в Git. Для локального запуска достаточно скопировать пример:

```bash
cp .env.example .env
```

Основные переменные:

```env
POSTGRES_DB=dna_registry
POSTGRES_USER=dna
POSTGRES_PASSWORD=replace-with-a-strong-db-password
SECRET_KEY=replace-with-a-long-random-secret
PRINT_DATA_DIR=/app/data/print
APP_PORT=4001
```

Для сервера обязательно поменяйте `POSTGRES_PASSWORD` и `SECRET_KEY`.

Если нужен другой внешний порт:

```env
APP_PORT=4010
```

## Запуск на сервере

```bash
git clone https://github.com/DrCramer/dna_base.git
cd dna_base
cp .env.example .env
nano .env
docker compose up -d --build
```

Проверить контейнеры:

```bash
docker compose ps
```

Посмотреть логи:

```bash
docker compose logs -f backend
docker compose logs -f frontend
```

Обновить приложение после новых коммитов:

```bash
git pull
docker compose up -d --build
```

## Production admin

В dev-режиме тестовые пользователи создаются автоматически. Для production можно создать или обновить администратора:

```bash
docker compose exec backend python -m app.commands.create_admin admin 'new-password'
```

## Локальная разработка без Docker

Backend:

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+asyncpg://dna:dna@localhost:5432/dna_registry
alembic -c ../alembic.ini upgrade head
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Vite будет доступен на `http://localhost:5173` и проксирует `/api` в backend.

## Проверки

Backend-тесты:

```bash
APP_PORT=4001 docker compose run --rm \
  -e PYTHONPATH=/app \
  -v "$PWD/backend/tests:/app/tests" \
  backend pytest tests
```

Frontend-сборка:

```bash
cd frontend
npm run build
```

Smoke-проверка запущенного сервиса:

```bash
curl http://localhost:4001/
```

Проверить compose-конфигурацию:

```bash
docker compose config --quiet
```

## Backup

Сделать дамп базы:

```bash
docker compose exec postgres pg_dump -U dna -d dna_registry > backup.sql
```

Сохранить файловое хранилище:

```bash
docker run --rm \
  -v dna_base_storage:/data \
  -v "$PWD":/backup \
  alpine tar czf /backup/storage-backup.tgz -C /data .
```

Восстановить базу:

```bash
docker compose exec -T postgres psql -U dna -d dna_registry < backup.sql
```

## Структура проекта

```text
backend/app/api          FastAPI routes
backend/app/models       SQLAlchemy models
backend/app/parsers      Excel and RT/qPCR parsers
backend/app/services     Business logic
backend/tests            Backend tests
frontend/src             React application
alembic/versions         Database migrations
docker/nginx             Frontend nginx config
```

## Что не публикуется в Git

Репозиторий публичный, поэтому в `.gitignore` исключены локальные и чувствительные данные:

- `.env`;
- `realtime/`;
- `ready_dna_base/`;
- `storage/`, `postgres_data/`;
- `node_modules/`, `frontend/dist/`;
- `.venv/`, `__pycache__/`, pytest/cache-файлы;
- локальные логи, скриншоты и временные QA-снимки.

Реальные лабораторные файлы, дампы базы и production-секреты должны оставаться вне репозитория.
