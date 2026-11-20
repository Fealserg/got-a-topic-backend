# Перерыв · Backend

Самостоятельный репозиторий FastAPI + SQLAlchemy + SQLite. Фронтенд находится в другом репозитории; общение — только по HTTP `/api/*`.

## Локальный запуск

Python 3.11+ (Docker использует 3.12):

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
alembic upgrade head
python -m app.seed
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Скопируйте `.env.example` в `.env` и экспортируйте необходимые значения перед запуском: приложение читает окружение процесса, не загружает `.env` автоматически. Для development можно использовать `uvicorn ... --reload`. По умолчанию разрешены localhost:3000 и 127.0.0.1:3000.

Swagger: http://localhost:8000/api/docs. Проверка: `/api/health`. POST/PUT/DELETE требуют заголовок `X-Requested-With: pereryv`; в Swagger нажмите Authorize и введите `pereryv`. Сессии — HttpOnly cookie, SameSite=Strict; в production обязателен `COOKIE_SECURE=true` и HTTPS. Фронтенд проксирует запросы на свой домен, поэтому cookie остаётся first-party.

## Демо

```sh
DEMO_MODE=true python -m app.seed --demo
DEMO_MODE=true uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Демо-профили: `anna`, `mikhail`, `elena`, `dmitry`, `olga`, `pavel`; пароль `DemoPass2026!`. Демо-слоты создаются только в пустой таблице, начинаются примерно через 30 минут после seed и помечены как вымышленные. Запускайте демо на отдельной БД; для реального пилота используйте чистую БД, `DEMO_MODE=false` и реальные слоты. Флаг скрывает кнопки входа в демо, но не удаляет уже созданные аккаунты.

Для организатора задайте `ADMIN_USERNAME` и уникальный `ADMIN_PASSWORD` (12+ символов) при `python -m app.seed`. Повторный seed не меняет пароль существующего аккаунта. Восстановление пароля через UI пока отсутствует; пользователь предупреждён при регистрации.

## Проверки

```sh
python -m pytest tests -q
```

Тесты используют отдельную временную БД. Проверяют авторизацию, CSRF, права владельца, подбор, транзакционное принятие, гонки, отмену, обратную связь, удаление и интервалы организатора.

## RelaxDev

Свой Dockerfile, корень этого репозитория. Постоянный диск `/data` с правами записи пользователя приложения. Переменные: `DATABASE_URL=sqlite:////data/pereryv.db`, `FRONTEND_URL=https://<frontend-domain>`, `COOKIE_SECURE=true`, `DEMO_MODE=false`. Порт выдаёт платформа. Один worker и один экземпляр приложения. Сначала деплой backend, затем frontend с `API_BASE_URL=https://<backend-domain>`. После публикации проверить `/api/health` и `/api/docs` через оба домена, сессии и сохранность данных после перезапуска.

SQLite и BEGIN IMMEDIATE сериализуют записи. Встречи занимают уникальные пары `(user_id, slot_id)`, слоты не пересекаются. Лимиты входа и приглашений работают в памяти одного процесса. Для масштаба нужны PostgreSQL, общие лимиты и отдельный план миграции. Пользовательские данные не включаются в репозиторий и образ.
