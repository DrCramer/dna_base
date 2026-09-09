#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [[ ! -w .git || (-e .git/FETCH_HEAD && ! -w .git/FETCH_HEAD) ]]; then
  cat >&2 <<EOF
Нет прав на запись в $PROJECT_DIR/.git.
Один раз исправьте владельца репозитория:
  sudo chown -R "$(id -un):$(id -gn)" "$PROJECT_DIR"
Затем снова запустите ./scripts/update_server.sh без sudo.
EOF
  exit 1
fi

tracked_changes="$(git status --porcelain --untracked-files=no)"
if [[ -n "$tracked_changes" ]]; then
  cat >&2 <<EOF
Обновление остановлено: в репозитории есть локальные изменения:
$tracked_changes

Сохраните их перед обновлением:
  git stash push -m "server-local-before-update"
EOF
  exit 1
fi

echo "Получение обновлений из GitHub..."
git pull --ff-only origin main

if docker info >/dev/null 2>&1; then
  compose=(docker compose)
else
  compose=(sudo docker compose)
fi

echo "Пересборка и запуск контейнеров..."
"${compose[@]}" up -d --build
"${compose[@]}" ps

port="$(sed -n 's/^APP_PORT=//p' .env 2>/dev/null | tail -n 1)"
port="${port:-4001}"
echo "Проверка http://127.0.0.1:${port}/health"
healthy=false
for _attempt in {1..30}; do
  if curl --fail --silent "http://127.0.0.1:${port}/health"; then
    echo
    healthy=true
    break
  fi
  sleep 1
done
if [[ "$healthy" != true ]]; then
  echo "Сервис не ответил за 30 секунд. Проверьте: ${compose[*]} logs --tail=100 backend frontend" >&2
  exit 1
fi
echo "Обновление завершено. Версия: $(git log -1 --oneline)"
