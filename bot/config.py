"""Конфигурация приложения. Загружается из .env, валидируется Pydantic."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

BASE_DIR = Path(__file__).resolve().parent.parent

# .env ищем и в корне проекта, и в корне пакета
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / "bot" / ".env", override=False)


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


class Settings(BaseModel):
    """Все настройки проекта в одном месте."""

    # --- Telegram ---
    bot_token: str = Field(default="", description="Токен бота от @BotFather")

    # --- База данных ---
    db_path: str = "data/bot.sqlite3"

    # --- Админка ---
    admin_ids: List[int] = Field(default_factory=list)

    # --- AI ---
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_base_url: str = "https://openrouter.ai/api/v1/chat/completions"

    # --- Лимиты (базовые значения; переопределяются из админ-панели) ---
    limit_image_per_hour: int = 20
    limit_ai_per_hour: int = 5
    limit_image_per_hour_premium: int = 100
    limit_ai_per_hour_premium: int = 30
    limit_actions_per_minute: int = 60
    max_messages: int = 200
    max_chats: int = 100

    # --- Монетизация (заготовка под Telegram Stars) ---
    premium_enabled: bool = False
    premium_stars_price: int = 250

    # --- Рендерер ---
    fonts_dir: str = "fonts"
    render_width: int = 1080
    render_max_height: int = 20000

    # --- Логи ---
    log_level: str = "INFO"
    log_file: str = ""

    # --- Прочее ---
    ad_text: str = (
        "⭐️ Premium: безлимитные генерации, больше стилей и AI-сценарии. "
        "Поддержать бота: /premium"
    )

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: Any) -> List[int]:
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
        """Проверки перед запуском polling."""
        if not self.bot_token:
            raise RuntimeError(
                "BOT_TOKEN не задан. Скопируйте .env.example в .env и укажите токен от @BotFather."
            )
        if self.render_width < 600:
            raise RuntimeError("RENDER_WIDTH слишком мал (минимум 600).")


settings = Settings()

__all__ = ["settings", "Settings", "BASE_DIR"]
