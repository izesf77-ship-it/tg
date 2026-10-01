"""Конфигурация приложения. Загружается из .env, валидируется Pydantic.

КРИТИЧНО: используется BaseSettings, а не BaseModel. BaseModel НЕ читает
переменные окружения — при запуске в Docker (где конфигурация приходит
через ENV, а не из файла .env) бот получал пустой BOT_TOKEN и падал.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any, List

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

# .env ищем в корне проекта; переменные из окружения имеют приоритет
load_dotenv(BASE_DIR / ".env", override=False)


def _split_ids(raw: Any) -> List[int]:
    """'1, 2,3' -> [1, 2, 3]"""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        raw = ",".join(str(x) for x in raw)
    result: List[int] = []
    for chunk in str(raw).replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            result.append(int(chunk))
        except ValueError:
            continue
    return result


class Settings(BaseSettings):
    """Все настройки проекта в одном месте.

    Значения берутся из переменных окружения, .env служит запасным
    источником. Имена переменных заданы через ``validation_alias``.
    """

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Telegram ---
    bot_token: str = Field(
        default="",
        validation_alias="BOT_TOKEN",
        description="Токен бота от @BotFather",
    )

    # --- База данных ---
    # В контейнере путь задаётся через ENV (см. Dockerfile/compose) и должен
    # быть абсолютным: иначе рабочий каталог процесса определяет, где
    # окажется файл БД, и volume /app/data перестаёт использоваться.
    db_path: str = Field(default="data/bot.sqlite3", validation_alias="DB_PATH")

    @field_validator("db_path")
    @classmethod
    def _db_path_is_absolute_in_container(cls, v: str) -> str:
        raw = (v or "").strip() or "data/bot.sqlite3"
        if Path(raw).is_absolute():
            return raw
        # В контейнере (маркер — каталог /app) путь обязан быть абсолютным
        if Path("/app").is_dir():
            return f"/app/{raw.lstrip('/')}"
        return raw

    # --- Админка ---
    # NoDecode отключает попытку разобрать значение как JSON: иначе
    # ADMIN_IDS="111,222" приводил бы к падению SettingsError.
    admin_ids: Annotated[List[int], NoDecode] = Field(
        default_factory=list, validation_alias="ADMIN_IDS"
    )

    # --- AI ---
    openrouter_api_key: str = Field(default="", validation_alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(
        default="openai/gpt-4o-mini", validation_alias="OPENROUTER_MODEL"
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1/chat/completions",
        validation_alias="OPENROUTER_BASE_URL",
    )

    # --- Лимиты (базовые значения; переопределяются из админ-панели) ---
    limit_image_per_hour: int = Field(default=20, validation_alias="LIMITS_IMAGE_PER_HOUR")
    limit_ai_per_hour: int = Field(default=5, validation_alias="LIMITS_AI_PER_HOUR")
    limit_image_per_hour_premium: int = Field(
        default=100, validation_alias="LIMITS_IMAGE_PER_HOUR_PREMIUM"
    )
    limit_ai_per_hour_premium: int = Field(
        default=30, validation_alias="LIMITS_AI_PER_HOUR_PREMIUM"
    )
    limit_actions_per_minute: int = Field(
        default=60, validation_alias="LIMITS_ACTIONS_PER_MINUTE"
    )
    max_messages: int = Field(default=200, ge=1, validation_alias="LIMITS_MAX_MESSAGES")
    max_chats: int = Field(default=100, ge=1, validation_alias="LIMITS_MAX_CHATS")

    # --- Монетизация (заготовка под Telegram Stars) ---
    premium_enabled: bool = Field(default=False, validation_alias="PREMIUM_ENABLED")
    premium_stars_price: int = Field(default=250, validation_alias="PREMIUM_STARS_PRICE")

    # --- Рендерер ---
    fonts_dir: str = Field(default="fonts", validation_alias="FONTS_DIR")
    render_width: int = Field(default=1080, validation_alias="RENDER_WIDTH")
    render_max_height: int = Field(
        default=20000, ge=0, validation_alias="RENDER_MAX_HEIGHT"
    )

    # --- Логи ---
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_file: str = Field(default="", validation_alias="LOG_FILE")

    # --- Прочее ---
    ad_text: str = Field(
        default=(
            "⭐️ Premium: безлимитные генерации, больше стилей и AI-сценарии. "
            "Поддержать бота: /premium"
        ),
        validation_alias="AD_TEXT",
    )

    # --- Сеть ---
    # Прокси нужен, если api.telegram.org недоступен из сети хостинга.
    # Формат: socks5://user:password@host:1080
    telegram_proxy: str = Field(default="", validation_alias="TELEGRAM_PROXY")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: Any) -> List[int]:
        """Список ID принимается как «111,222», «111; 222» или JSON-массив."""
        return _split_ids(v)

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, v: Any) -> str:
        return str(v or "INFO").upper()

    @field_validator("openrouter_base_url", mode="before")
    @classmethod
    def _clean_url(cls, v: Any) -> str:
        return str(v or "").strip().rstrip("/") or "https://openrouter.ai/api/v1/chat/completions"

    # --- Производные пути -------------------------------------------------
    @property
    def base_dir(self) -> Path:
        return BASE_DIR

    @property
    def data_dir(self) -> Path:
        return BASE_DIR / "data"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def renders_dir(self) -> Path:
        return self.data_dir / "renders"

    @property
    def db_file(self) -> Path:
        p = Path(self.db_path)
        return p if p.is_absolute() else (BASE_DIR / p)

    @property
    def fonts_path(self) -> Path:
        p = Path(self.fonts_dir)
        return p if p.is_absolute() else (BASE_DIR / p)

    @property
    def log_file_path(self) -> Path | None:
        if not self.log_file:
            return None
        p = Path(self.log_file)
        return p if p.is_absolute() else (BASE_DIR / p)

    @property
    def _proxy_parts(self):
        """Разобрать TELEGRAM_PROXY на (host, port, user, password)."""
        from urllib.parse import urlparse

        raw = (self.telegram_proxy or "").strip()
        if not raw:
            return None, 0, None, None
        if "://" not in raw:
            raw = f"socks5://{raw}"
        parsed = urlparse(raw)
        try:
            port = parsed.port or 1080
        except ValueError:
            port = 1080
        return parsed.hostname or "", port, parsed.username, parsed.password

    @property
    def telegram_proxy_host(self) -> str:
        return self._proxy_parts[0]

    @property
    def telegram_proxy_port(self) -> int:
        return self._proxy_parts[1]

    @property
    def telegram_proxy_user(self) -> str:
        return self._proxy_parts[2] or ""

    @property
    def telegram_proxy_password(self) -> str:
        return self._proxy_parts[3] or ""

    def setup_dirs(self) -> None:
        """Создать необходимые каталоги (идемпотентно)."""
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.renders_dir.mkdir(parents=True, exist_ok=True)
        self.fonts_path.mkdir(parents=True, exist_ok=True)
        if self.log_file_path:
            self.log_file_path.parent.mkdir(parents=True, exist_ok=True)

    def is_admin(self, user_id: int) -> bool:
        return int(user_id) in self.admin_ids

    def validate_runtime(self) -> None:
        """Проверки перед запуском polling.

        Здесь же выявляется ситуация «переменная окружения задана, но
        настройка её не подхватила» — раньше это приводило к молчаливому
        падению с пустым токеном.
        """
        if not self.bot_token:
            in_env = (os.environ.get("BOT_TOKEN") or "").strip()
            if in_env:
                raise RuntimeError(
                    "BOT_TOKEN присутствует в переменных окружения, но не был "
                    "прочитан конфигурацией. Проверьте, что импортируется "
                    "bot.config.Settings, а не пустой объект, и что версия "
                    "pydantic-settings установлена (pip install pydantic-settings)."
                )
            raise RuntimeError(
                "BOT_TOKEN не задан. Укажите переменную окружения BOT_TOKEN "
                "в панели хостинга или добавьте её в файл .env."
            )
        if ":" not in self.bot_token:
            raise RuntimeError(
                "BOT_TOKEN имеет неверный формат (ожидается 123456789:AA...)."
            )
        if self.render_width < 600:
            raise RuntimeError("RENDER_WIDTH слишком мал (минимум 600).")


settings = Settings()

__all__ = ["settings", "Settings", "BASE_DIR"]
