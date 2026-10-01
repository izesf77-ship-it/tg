"""Тексты экранов бота.

Все пользовательские сообщения собраны здесь, чтобы логика
хендлеров оставалась читаемой.
"""

from __future__ import annotations

from typing import List

from bot.utils import text_utils as T
from bot.utils.time_utils import numeric_date

DISCLAIMER_SHORT = "Это вымышленная переписка для юмора и контента."

WELCOME = (
    "👋 <b>Конструктор переписок</b>\n\n"
    "Создавай вымышленные диалоги, настраивай участников "
    "и получай готовый скриншот."
)

HOW_IT_WORKS = (
    "📖 <b>Как это работает</b>\n\n"
    "1. <b>Создай переписку</b> — выбери стиль интерфейса.\n"
    "2. <b>Настрой участников</b> — имя, username, фото, статус, Premium.\n"
    "3. <b>Добавь сообщения</b> — текст, фото, голосовое, файл, стикер, "
    "реакции, ответы и пересылки.\n"
    "4. <b>Настрой время</b> — текущее или вручную (12:41).\n"
    "5. <b>Сделай предпросмотр</b> и получи готовое изображение.\n"
    "6. <b>Сохрани</b> — переписка появится в «Мои переписки».\n\n"
    "✨ Можно нажать <b>Создать с AI</b> в меню и получить готовый "
    "вымышленный диалог по короткому описанию.\n\n"
    "⚠️ <b>Важно:</b> бот создаёт вымышленные диалоги для юмора, мемов "
    "и контента. При желании на изображение можно добавить пометку "
    "<i>FICTIONAL CHAT</i> (включается в настройках переписки). "
    "Не используйте переписки для подделки документов, банковских "
    "сообщений или как доказательств."
)

RULES = (
    "🚫 <b>Что нельзя</b>\n\n"
    "• подделывать документы и официальные письма;\n"
    "• создавать фальшивые банковские уведомления;\n"
    "• выдавать переписку за доказательство;\n"
    "• использовать для фишинга и мошенничества.\n\n"
    "✅ <b>Для чего можно</b>\n\n"
    "• мемы и шутки;\n"
    "• сценарии и кастинги;\n"
    "• контент для соцсетей и сторис."
)

EMPTY_CHAT = "Переписка пока пустая.\n\nДобавь первое сообщение."

HELP_AI_DISABLED = (
    "ℹ️ <b>AI-сценарии сейчас недоступны</b>\n\n"
    "Для генерации нужен действующий ключ OpenRouter и доступная модель.\n"
    "Все остальные функции работают: создание переписки вручную, "
    "шаблоны и генерация изображений."
)

INPUT_CANCEL_HINT = "Можно отменить ввод кнопкой ниже или командой /cancel."

FIELD_PROMPTS = {
    "name": "Введите <b>имя</b> участника (до 64 символов):",
    "username": "Введите <b>username</b> без символа @ (например: alexey):",
    "display_name": "Введите <b>отображаемое имя</b> в шапке чата:",
    "status": (
        "Введите <b>статус</b> участника.\n\n"
        "Примеры: <code>в сети</code>, <code>был(а) недавно</code>, "
        "<code>занят</code>, <code>оффлайн</code>"
    ),
    "last_seen": "Введите <b>время последнего входа</b> в формате 12:41:",
    "avatar": "Пришлите <b>фотографию</b> участника из Telegram:",
    "forward": "Введите <b>имя</b>, от кого переслано сообщение:",
    "service": "Введите <b>текст</b> системного сообщения:",
    "date": "Введите <b>подпись</b> разделителя (например: «Сегодня»):",
    "caption": "Введите <b>подпись</b> к фотографии:",
    "time": "Введите <b>время</b> сообщения в формате 12:41:",
    "text": "Введите <b>текст</b> сообщения:",
    "ai_prompt": (
        "Опишите сценарий переписки.\n\n"
        "Пример: <i>Девушка получает сообщение от бывшего, парень это "
        "замечает и начинает ревновать</i>"
    ),
    "broadcast": "Введите <b>текст рассылки</b> для всех пользователей:",
}


def field_prompt(field: str) -> str:
    return FIELD_PROMPTS.get(field, "Введите значение:")


def author_labels(config) -> List[str]:
    """Подписи участников для кнопок: «← Алексей» / «→ Алина»."""
    labels = []
    for index, participant in enumerate(config.participants):
        side = "←" if participant.side == 0 else "→"
        labels.append(f"{side} {participant.name or f'Участник {index + 1}'}")
    return labels


def participants_screen(config) -> str:
    lines = ["👤 <b>Настрой участников</b>", ""]
    for index, participant in enumerate(config.participants):
        lines.append(f"<b>{index + 1}. {T.esc(participant.name or 'Участник')}</b>")
        details = []
        if participant.username:
            details.append(f"@{participant.username}")
        if participant.status:
            details.append(T.esc(participant.status))
        if participant.premium:
            details.append("⭐️ Premium")
        if participant.avatar_path:
            details.append("🖼 фото есть")
        lines.append("   " + (" · ".join(details) if details else "не заполнено"))
    lines.append("")
    lines.append("Нажмите на участника, чтобы изменить его данные.")
    return "\n".join(lines)


def participant_screen(index: int, participant) -> str:
    premium = "да ⭐️" if participant.premium else "нет"
    photo = "загружено 🖼" if participant.avatar_path else "не задано"
    return (
        f"👤 <b>Участник {index + 1}: {T.esc(participant.name or '—')}</b>\n\n"
        f"Имя: {T.esc(participant.name or '—')}\n"
        f"Username: @{T.esc(participant.username) if participant.username else '—'}\n"
        f"Отображаемое имя: "
        f"{T.esc(participant.display_name) if participant.display_name else '—'}\n"
        f"Фото: {photo}\n"
        f"Статус: {T.esc(participant.status or '—')}\n"
        f"Последний вход: {T.esc(participant.last_seen or '—')}\n"
        f"Premium: {premium}\n\n"
        "Выберите, что изменить."
    )


def editor_screen(config, page: int = 0, total_pages: int = 1) -> str:
    """Текст экрана редактора со списком сообщений."""
    header = (
        f"✏️ <b>Редактор переписки</b>\n"
        f"Стиль: {T.esc(config.style)} · Сообщений: {len(config.messages)}"
    )
    if not config.messages:
        return f"{header}\n\n{EMPTY_CHAT}"

    lines = [header, ""]
    for index, message in enumerate(config.messages):
        author = (
            config.participants[message.author_index].name
            if 0 <= message.author_index < len(config.participants)
            else "Участник"
        )
        arrow = "←" if message.side == 0 else "→"
        marks = []
        if message.reply_to:
            marks.append("↩️")
        if message.reaction:
            marks.append(f" {message.reaction.emoji}")
        if message.side == 1 and not message.read:
            marks.append(" ⏳")
        lines.append(
            f"{index + 1}. {message.type_icon()} <b>{T.esc(author)}</b> {arrow}"
            + "".join(marks)
        )
        lines.append(f"    <code>{T.esc(message.preview(70) or '—')}</code>")
        lines.append(f"    🕐 {message.time}")
    if total_pages > 1:
        lines.append("")
        lines.append(f"Страница {page + 1} из {total_pages}")
    return "\n".join(lines)


def chat_summary(config) -> str:
    return (
        f"📂 <b>{T.esc(config.title or 'Переписка')}</b>\n"
        f"{config.participants_label()}\n"
        f"{T.messages_word(len(config.messages))} · стиль {T.esc(config.style)}"
    )


def chats_list_text(chats, total: int, page: int, page_size: int) -> str:
    if not chats:
        return (
            "📂 <b>Мои переписки</b>\n\n"
            "Здесь пока пусто.\n\n"
            "Нажмите «➕ Создать переписку», чтобы сделать первую."
        )
    lines = ["📂 <b>Мои переписки</b>", ""]
    for chat in chats:
        lines.append(
            f"<b>Переписка #{chat.id}</b>\n"
            f"{T.esc(chat.title or 'Переписка')}\n"
            f"{T.messages_word(chat.message_count)} · {numeric_date(chat.created_at)}\n"
        )
    pages = max(1, (total + page_size - 1) // page_size)
    lines.append(f"Страница {page + 1} из {pages} · всего: {total}")
    return "\n".join(lines)


def chat_card(chat, config) -> str:
    return (
        f"📂 <b>Переписка #{chat.id}</b>\n\n"
        f"{config.participants_label()}\n"
        f"{T.messages_word(len(config.messages))}\n"
        f"Стиль: {T.esc(config.style)}\n"
        f"Создана: {numeric_date(chat.created_at)}\n"
        f"Обновлена: {numeric_date(chat.updated_at)}\n\n"
        f"<i>{DISCLAIMER_SHORT}</i>"
    )


def template_card(template) -> str:
    return (
        f"{template.emoji} <b>{T.esc(template.title)}</b>\n\n"
        f"{T.esc(template.description)}\n\n"
        "Это демонстрационная вымышленная переписка для юмора и контента."
    )


def ai_result(config) -> str:
    return (
        "✨ <b>Сценарий готов</b>\n\n"
        f"{config.participants_label()}\n"
        f"{T.messages_word(len(config.messages))}\n\n"
        "Сценарий вымышленный и предназначен для юмора, мемов и контента.\n"
        "Проверьте его в редакторе и при необходимости поправьте."
    )


def limits_screen(image: str, ai: str) -> str:
    return (
        "📊 <b>Мои лимиты</b>\n\n"
        f"🖼 Генераций изображений: {image}\n"
        f"✨ AI-сценариев: {ai}\n\n"
        "Лимиты обновляются каждый час."
    )


def settings_screen(user, limits_image, limits_ai, ai_status: str) -> str:
    status = "⭐️ Premium активен" if getattr(user, "is_premium", False) else "Бесплатная версия"
    return (
        "⚙️ <b>Настройки</b>\n\n"
        f"Статус: {status}\n"
        f"🖼 Генераций в час: {limits_image}\n"
        f"✨ AI-запросов в час: {limits_ai}\n"
        f"🤖 {T.esc(ai_status)}\n\n"
        "Выберите раздел ниже."
    )


def premium_screen(features, price: int) -> str:
    lines = ["⭐️ <b>Premium</b>", ""]
    for feature in features:
        lines.append(f"• <b>{T.esc(feature.title)}</b>: {feature.free} → {feature.premium}")
    lines.append("")
    lines.append(f"Оплата через Telegram Stars: {price} ⭐️")
    lines.append("")
    lines.append(
        "Платёжная система подготовлена, но пока не подключена. "
        "Архитектура бота уже поддерживает Premium-возможности."
    )
    return "\n".join(lines)


def done_text() -> str:
    return "Готово.\n\nЭто фиктивная переписка, созданная в конструкторе."


def message_card(index: int, message, author: str) -> str:
    """Карточка одного сообщения в редакторе."""
    marks = []
    if message.reply_to:
        marks.append("↩️ это ответ")
    if message.reaction:
        marks.append(f"{message.reaction.emoji} реакция")
    if message.side == 1 and not message.read:
        marks.append("⏳ не прочитано")
    if message.kind.value == "forward" and message.forward_from:
        marks.append(f"↪ от {message.forward_from}")
    lines = [
        f"✏️ <b>Сообщение {index + 1}</b>",
        "",
        f"Автор: {T.esc(author)} ({'←' if message.side == 0 else '→'})",
        f"Тип: {message.type_icon()} {message.kind.value}",
        f"Время: {message.time}",
    ]
    if message.text:
        lines.append("")
        lines.append(f"<code>{T.esc(message.preview(300))}</code>")
    if marks:
        lines.append("")
        lines.append(" · ".join(T.esc(m) for m in marks))
    return "\n".join(lines)


__all__ = [
    "DISCLAIMER_SHORT", "WELCOME", "HOW_IT_WORKS", "RULES", "EMPTY_CHAT",
    "HELP_AI_DISABLED", "INPUT_CANCEL_HINT", "field_prompt", "author_labels",
    "participants_screen", "participant_screen", "editor_screen", "chat_summary",
    "chats_list_text", "chat_card", "template_card", "ai_result", "limits_screen",
    "settings_screen", "premium_screen", "done_text", "message_card",
]