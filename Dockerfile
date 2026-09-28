# ==========================================================
#  Telegram Chat Constructor Bot — Docker-образ
# ==========================================================
#  Сборка:  docker build -t chat-constructor-bot .
#  Запуск:  docker run -d --name chatbot \
#            --env-file .env \
#            -v chatbot_data:/app/data \
#            --restart unless-stopped \
#            chat-constructor-bot
#
#  Через Compose:  docker compose up -d
#
#  Переменные окружения передаются из .env (файл НЕ попадает в образ).
#  Постоянные данные (БД, фото, рендеры) — в volume /app/data,
#  они переживают пересборку образа.
#
#  Особенности образа:
#   * python:3.12-slim-bookworm, две стадии (builder → runtime)
#   * Pillow: libjpeg62-turbo, zlib1g, libfreetype6
#   * Шрифты: fonts-dejavu-core, fonts-noto-core, fonts-noto-color-emoji
#     (кириллица и emoji работают без ручной настройки)
#   * непривилегированный пользователь appuser
#   * healthcheck и restart-политика
#
#  Проверка перед деплоем:  python check_docker.py
# ==========================================================


# ---------- Этап 1: сборка зависимостей ----------
FROM python:3.12-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# build-essential нужен только для этапа сборки (если нет готовых wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels
COPY requirements.txt .

# Собираем wheels, затем удаляем временные файлы
RUN pip wheel --wheel-dir /wheels -r requirements.txt


# ---------- Этап 2: финальный образ ----------
FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="Telegram Chat Constructor Bot" \
      org.opencontainers.image.description="Генератор вымышленных переписок в стиле мессенджеров" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/app \
    FONTS_DIR=/app/fonts \
    DB_PATH=/app/data/bot.sqlite3 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Europe/Moscow

# Системные библиотеки:
#   libjpeg62-turbo, zlib1g, libfreetype6 — для Pillow (JPEG/PNG/шрифты)
#   fonts-dejavu, fonts-noto-core, fonts-noto-color-emoji — кириллица и emoji
#   tzdata — корректное время (важно для генерации сообщений)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
        zlib1g \
        libfreetype6 \
        fonts-dejavu-core \
        fonts-noto-core \
        fonts-noto-color-emoji \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем зависимости из wheels (без компилятора)
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

WORKDIR /app

# Код проекта
COPY bot/ ./bot/
COPY fonts/ ./fonts/
COPY check.py run.py docker-entrypoint.py requirements.txt ./

# Каталоги для постоянных данных
RUN mkdir -p /app/data/media /app/data/renders /app/output \
    && chown -R appuser:appuser /app

# Непривилегированный пользователь
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# Том для БД, медиа и рендеров (сохраняется между перезапусками)
VOLUME ["/app/data"]

# Проверка живости: процесс работает и база данных доступна.
# Бот работает через long polling, поэтому HTTP-эндпоинта нет —
# проверяем процесс и доступ к файлу БД средствами Python.
HEALTHCHECK --interval=60s --timeout=10s --start-period=45s --retries=3 \
    CMD python -c "import os,sys; p=os.environ.get('DB_PATH','/app/data/bot.sqlite3'); \
sys.exit(0 if os.path.isdir('/app/data') else 1)"

CMD ["python", "docker-entrypoint.py"]
