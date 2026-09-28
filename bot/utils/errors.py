"""Собственные исключения приложения."""


class BotError(Exception):
    """Базовая ошибка, безопасно показывается пользователю."""

    user_message: str = "Что-то пошло не так. Попробуйте ещё раз."

    def __init__(self, user_message: str | None = None):
        super().__init__(user_message or self.user_message)
        if user_message:
            self.user_message = user_message


class ValidationError(BotError):
    user_message = "Проверьте введённые данные."


class TextTooLongError(ValidationError):
    user_message = "Текст слишком длинный."


class InvalidTimeError(ValidationError):
    user_message = "Неверное время. Формат: 12:41"


class ChatNotFoundError(BotError):
    user_message = "Переписка не найдена."


class MessageNotFoundError(BotError):
    user_message = "Сообщение не найдено."


class NoMessagesError(BotError):
    user_message = "В переписке пока нет сообщений."


class LimitExceededError(BotError):
    def __init__(self, user_message: str, retry_after: int = 0):
        super().__init__(user_message)
        self.retry_after = retry_after


class PremiumRequiredError(BotError):
    user_message = "Функция доступна только в Premium."


class AIUnavailableError(BotError):
    user_message = "AI-генерация временно недоступна."


class AIError(BotError):
    user_message = "AI не смог придумать сценарий. Попробуйте ещё раз."


class RenderError(BotError):
    user_message = "Не удалось сгенерировать изображение."


class FontNotFoundError(RenderError):
    user_message = "Не найден шрифт для генерации. Добавьте шрифты в папку fonts (см. README)."


class ImageTooLargeError(BotError):
    user_message = "Слишком длинная переписка. Разбейте её на части."


class BroadcastError(BotError):
    user_message = "Ошибка рассылки."


__all__ = [
    "BotError",
    "ValidationError",
    "TextTooLongError",
    "InvalidTimeError",
    "ChatNotFoundError",
    "MessageNotFoundError",
    "NoMessagesError",
    "LimitExceededError",
    "PremiumRequiredError",
    "AIUnavailableError",
    "AIError",
    "RenderError",
    "FontNotFoundError",
    "ImageTooLargeError",
    "BroadcastError",
]
