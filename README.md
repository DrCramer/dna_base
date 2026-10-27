# Лабораторный реестр ДНК

Веб-приложение для ведения лабораторного ДНК-реестра: партии, объекты, этапы работ, исполнители, импорт/экспорт Excel, RT/qPCR-данные, отчёты и аудит изменений.

Проект рассчитан на запуск через Docker Compose: frontend собирается на React/Vite, backend работает на FastAPI, данные хранятся в PostgreSQL, миграции выполняются через Alembic.

## Возможности

- Импорт лабораторных Excel-реестров с preview перед записью в базу.
- Ведение партий и объектов с историей повторяемых этапов.
- Массовое заполнение этапов по выбранным партиям и объектам.
- Создание, сохранение и A4-печать единых протоколов Выделение / RT / PCR / Форез с несколькими 96-луночными плашками.
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

В разделе `Протоколы -> Создать` выберите год и несколько партий, отметьте объекты, заполните четыре этапа прямо в документе и сохраните черновик. После финализации документ открывается из `Протоколы -> Сохранённые` по зафиксированному snapshot; дальнейшее редактирование создаёт новую ревизию. Доступны A4 landscape preview, печать и XLSX-выгрузка `Скачать RT`.

Вкладка `Генетические экспертизы` использует отдельные объекты без партий и записей реестра ЧС. Выберите год экспертизы, вставьте список номеров или загрузите Excel-протокол, уточните неоднозначные имена и примените preview. Одинаковые номера в разных годах не совпадают. Импорт Excel сохраняет реальные лунки, включая самостоятельную PCR-раскладку; смена controls требует явного подтверждения пересборки. Можно применять отдельно даты, наборы, исполнителей, секвенатор и комментарии.

`Импорт RT` принимает до 10 файлов `.xlsx/.xls/.csv` по 20 MiB, позволяет накопительно добавлять файлы, вручную сопоставлять и исключать образцы, сохранять новую попытку или заменять актуальные результаты с сохранением истории. Повтор SHA-256 требует подтверждения. В `Разведения -> Все мишени` можно выбрать Long/Small/Y отдельно для каждого объекта; Small используется по умолчанию, недоступная мишень не подменяется другой. Выбор сохраняется в snapshot и используется общими расчётами, печатью и Excel.

Рабочие концентрации экспертиз округляются до четырёх знаков после запятой, как в ЧС; исходные измерения сохраняются отдельно. При включении всех мишеней `Исх. конц.` содержит внутренние столбцы `Мишень` и `Конц.`. Их пропорции одинаковы на экране и на всех печатных листах; панель команд протокола остаётся сверху при прокрутке.

В раскрытом блоке `Разведения` можно задать `Конечную концентрацию ДНК` в нг/мкл независимо от округления воды. Default 0,1; допустимы запятая и точка. Изменение применяется по Enter или при выходе из поля, пересчитывает весь состав и сохраняется в существующем snapshot. Невалидный ввод оставляет последнюю корректную цель. Если исходная концентрация ниже цели, обычное разведение не выполняется: таблица, печать и XLSX показывают фактическую исходную концентрацию и пояснение. Объём DNA на реакцию и другие реагенты PCR не меняются; известный объём из профиля используется только для справочной оценки массы. Группы воды доступны в `Подробности округления`.

Миграция `0014_genetic_examinations` применяется обычным `alembic upgrade head`. Перед обновлением рабочей БД сделайте резервную копию. Автоматический downgrade запрещён при наличии генетических данных, чтобы исключить их потерю.

Диапазон РЦСМЭ, описание и вставленный список номеров автоматически отмечают объекты; таблица показывает все объекты выбранных партий и позволяет вручную скорректировать выбор. Критерии и фактический состав сохраняются отдельно в snapshot. Кнопка `Скачать список номеров` выгружает UTF-8 TXT в порядке готового протокола, включая ручные корректировки. Общий счётчик учитывает уникальные объекты, независимо от числа этапов и плашек.

В `Разведения` доступен явно включаемый режим `Округление объема H₂O`: сервер подбирает общие объёмы H₂O с проверкой конечной концентрации и ограничений каждого объекта. Настройки и результаты сохраняются в snapshot и используются в печати и Excel. Предлагаемый допуск 5% требует утверждения лабораторией. Формулы, ограничения и аудит описаны в [DILUTION_WATER_OPTIMIZATION.md](DILUTION_WATER_OPTIMIZATION.md).

### Ограничение нагрузки протоколов

По умолчанию один создаваемый или пересчитываемый протокол ограничен 2000 уникальных объектов (`PROTOCOL_MAX_OBJECTS`). При большей выборке уточните диапазон или разделите её на несколько протоколов. Уже сохранённые документы не обрезаются. Лимит проверяется до загрузки объектов и расчётов; интерфейс получает его из `/api/protocols/meta`.

Один процесс backend рассчитывает только один протокол одновременно (preview и сохранение используют общий ограничитель). Остальные запросы получают HTTP 429 без очереди; доступна кнопка повторного расчёта. Отмена запроса не освобождает слот, пока поток оптимизации не завершится. Браузер отправляет изменения последовательно и пересчитывает только последние настройки, не накапливая старые ответы preview в mutation cache. Свёрнутые таблицы расчётов и разведений создаются только после раскрытия.

В Docker Compose память backend вместе с дочерними процессами ограничена 2 GiB без дополнительного swap (`BACKEND_MEMORY_LIMIT=2g`, `BACKEND_MEMORY_SWAP_LIMIT=2g`). Это аварийная граница, а не гарантия выполнения любого задания: при её превышении контейнер может быть перезапущен OOM-killer. Учитывайте память LibreOffice и число `PRINT_CONVERT_WORKERS`. Ограничение не распространяется на процессы сборки и другие приложения сервера. Docker-сборка frontend отдельно ограничивает V8 heap до 512 MiB (build arg `NODE_OPTIONS`), но полный RSS процесса может быть больше. На машине с небольшим запасом RAM собирайте backend и frontend последовательно, не запускайте несколько сборок одновременно.

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
PRINT_CONVERT_WORKERS=auto
APP_PORT=4001
```

Для сервера обязательно поменяйте `POSTGRES_PASSWORD` и `SECRET_KEY`.

`PRINT_CONVERT_WORKERS=auto` использует до четырёх параллельных процессов LibreOffice
при сборке DOCX в PDF. На сервере с 8 CPU и 8 GB RAM рекомендуется оставить `auto`
или явно указать `PRINT_CONVERT_WORKERS=4`. Увеличивать значение выше числа доступных
ядер и выше `4` без запаса оперативной памяти не рекомендуется.

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

## Обновление сервера через GitHub

Обычное обновление выполняется из каталога проекта:

```bash
cd ~/dna_base
git status --short
git branch --show-current
git pull --ff-only origin main
docker compose up -d --build
docker compose ps
```

После первого исправного обновления можно пользоваться готовой командой:

```bash
cd ~/dna_base
./scripts/update_server.sh
```

Если Docker на сервере доступен только через `sudo`, используйте
`sudo docker compose` во всех командах выше.

Что происходит при обновлении:

- `git pull --ff-only origin main` загружает последнюю версию из ветки `main` на GitHub;
- `docker compose up -d --build` пересобирает изменившиеся образы и перезапускает контейнеры;
- backend автоматически выполняет `alembic upgrade head`, поэтому миграции базы применяются при запуске;
- файл `.env`, база PostgreSQL и загруженные файлы находятся вне Git и при обычном обновлении не удаляются.

Не копируйте `.env.example` поверх существующего `.env`: пример нужен только при
первом запуске. После появления новых настроек сравните файлы и добавьте только
недостающие строки вручную.

Проверить установленную версию и работу сервиса:

```bash
git log -1 --oneline
curl -f http://127.0.0.1:4001/health
docker compose logs --tail=100 backend frontend
```

Ожидаемый ответ проверки: `{"status":"ok"}`. Если интерфейс после обновления
выглядит по-старому, выполните жёсткое обновление страницы в браузере:
`Ctrl+F5` или `Ctrl+Shift+R`.

Перед крупным обновлением можно сделать резервную копию базы:

```bash
mkdir -p backups
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  > "backups/dna_registry_$(date +%Y-%m-%d_%H-%M).sql"
```

Если `git status --short` показывает изменённые файлы проекта, сначала разберитесь
с этими изменениями. Не используйте `git reset --hard`, чтобы случайно не потерять
локальные правки.

### Ошибка `detected dubious ownership` или `FETCH_HEAD: Permission denied`

Она означает, что репозиторий был скопирован или распакован через `sudo` и принадлежит
пользователю `root`. Один раз верните каталог текущему пользователю:

```bash
cd /home/dna
sudo chown -R "$USER:$(id -gn)" /home/dna/dna_base
cd /home/dna/dna_base
git status --short
```

После этого запускайте `git status`, `git pull` и скрипт обновления **без `sudo`**.
`sudo` может использовать другой Git-конфиг, SSH-ключи и настройки сети.

Если перед обновлением отображаются локальные изменения, безопасно отложите их:

```bash
git stash push -m "server-local-before-update"
git pull --ff-only origin main
```

Рабочий `.env` не отслеживается Git и в stash не попадёт. Старые изменения
`docker-compose.yml` обычно не нужно возвращать: настройки сервера следует хранить
в `.env`. Посмотреть сохранённую разницу можно командой `git stash show -p`.

### Ошибка GitHub `511`

Сначала убедитесь, что `git pull` выполняется обычным пользователем, а не через
`sudo`. Затем проверьте доступ сервера к GitHub:

```bash
curl -I https://github.com
git ls-remote https://github.com/DrCramer/dna_base.git HEAD
git config --global --get-regexp 'http\..*proxy|https\..*proxy' || true
```

Если и `curl` возвращает `511`, запрос блокирует прокси, шлюз или авторизация сети
сервера. Это не ошибка репозитория: сначала нужно восстановить HTTPS-доступ к
`github.com`. Не запускайте `sudo git pull` в качестве обходного решения.

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

Playwright smoke для раздела протоколов (приложение должно быть запущено на порту `4001`):

```bash
cd frontend
npm run test:e2e
```

Миграционные/API-тесты экспертиз запускайте только на отдельной пустой PostgreSQL-базе с именем `dna_genetic_test_*`, передав `DNA_TEST_DATABASE_NAME`; без этой переменной тесты пропускаются. Набор проверяет upgrade/downgrade без генетических данных, старый snapshot ЧС, годы, независимые номера, FK, RT commit/rollback, историю и Excel.

Для браузерных проверок на отдельном тестовом backend можно задать `PLAYWRIGHT_BASE_URL`. Excel-fixture генерируется командой `python backend/tests/create_genetic_e2e_excel.py /tmp/genetic-e2e.xlsx`; путь передайте как `GENETIC_E2E_EXCEL`. Запуск `npx playwright test genetic-protocols.spec.ts --workers=1` использует реальные API и создаёт тестовые экспертизы/протоколы, поэтому не запускайте его на рабочей БД. Фикстура не содержит лабораторных персональных данных.

Для `protocol-concentration.spec.ts` на том же изолированном backend сначала выполните `PYTHONPATH=/app python /app/tests/create_protocol_concentration_e2e.py` с подключённым каталогом `backend/tests`. Скрипт откажется работать с БД без префикса `dna_genetic_test_`. Затем задайте `DNA_E2E_ISOLATED=1` и `PLAYWRIGHT_BASE_URL` при запуске Playwright. Сценарии создают искусственные объекты и проверяют оба режима, ввод цели, PCR-профили DNA 1/15 мкл, сохранение, неизменность final snapshot, ревизию и PDF.

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
