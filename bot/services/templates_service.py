"""Готовые шаблоны переписок.

Каждый шаблон — демонстрационная вымышленная история для юмора,
мемов и контента. Шаблоны не предназначены для подделки документов,
банковских сообщений или иных доказательств.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from bot.schemas import (
    ChatConfig,
    MediaItem,
    Message,
    MessageKind,
    Participant,
    Reaction,
)
from bot.schemas.template import TemplatePreview


@dataclass
class Template:
    """Шаблон переписки."""

    key: str
    title: str
    emoji: str
    description: str
    builder: Optional[Callable[[], ChatConfig]] = None
    premium_only: bool = False
    tags: List[str] = field(default_factory=list)

    def build(self) -> ChatConfig:
        if self.builder is None:  # pragma: no cover - defensive
            raise ValueError(f"У шаблона {self.key} нет билдера")
        config = self.builder()
        config.template = self.key
        return config

    def preview(self) -> TemplatePreview:
        config = self.build() if self.builder else ChatConfig()
        return TemplatePreview(
            key=self.key,
            title=self.title,
            emoji=self.emoji,
            description=self.description,
            preview=" → ".join(m.preview(28) for m in config.messages[:3]),
            participants=[p.name for p in config.participants],
            message_count=len(config.messages),
            premium_only=self.premium_only,
            style=config.style,
        )


def _pair(first: str, second: str, style: str = "telegram") -> List[Participant]:
    return [
        Participant(name=first, side=0, status="в сети"),
        Participant(name=second, side=1, status="в сети"),
    ]


def _msg(
    text: str,
    side: int,
    time: str,
    author: int,
    **kwargs,
) -> Message:
    return Message(kind=MessageKind.TEXT, text=text, side=side, time=time,
                   author_index=author, **kwargs)


def _service(text: str, time: str) -> Message:
    return Message(kind=MessageKind.SERVICE, text=text, time=time, side=0)


def _date(text: str, time: str) -> Message:
    return Message(kind=MessageKind.DATE, text=text, time=time, side=0)


def _voice(side: int, time: str, author: int, duration: str) -> Message:
    return Message(
        kind=MessageKind.VOICE, time=time, side=side, author_index=author,
        media=MediaItem(kind=MessageKind.VOICE, duration=duration),
    )


def _sticker(side: int, time: str, author: int, emoji: str) -> Message:
    return Message(
        kind=MessageKind.STICKER, time=time, side=side, author_index=author,
        media=MediaItem(kind=MessageKind.STICKER, emoji=emoji),
    )


def _file(side: int, time: str, author: int, name: str, size: str) -> Message:
    return Message(
        kind=MessageKind.FILE, time=time, side=side, author_index=author,
        media=MediaItem(kind=MessageKind.FILE, file_name=name, file_size=size),
    )


def _image(side: int, time: str, author: int, caption: str) -> Message:
    return Message(
        kind=MessageKind.IMAGE, time=time, side=side, author_index=author,
        media=MediaItem(kind=MessageKind.IMAGE, caption=caption),
    )


def _forward(side: int, time: str, author: int, src: str, text: str) -> Message:
    return Message(
        kind=MessageKind.FORWARD, forward_from=src, text=text, time=time,
        side=side, author_index=author,
    )


def build_revenge() -> ChatConfig:
    """Ревность: девушка получила сообщение от бывшего."""
    cfg = ChatConfig(title="Ревность", style="telegram")
    cfg.participants = _pair("Максим", "Лена")
    cfg.messages = [
        _msg("Привет! Ты где?", 0, "19:02", 0),
        _msg("На кухне, чайник свистит", 1, "19:03", 1),
        _voice(0, "19:03", 0, "0:04"),
        _msg("Понял, иду к тебе", 1, "19:05", 1),
        _date("Сегодня", "19:20"),
        _msg("Кстати, мне тут Сергей написал", 1, "19:20", 1,
             reaction=Reaction(emoji="👀", count=1)),
        _msg("Сергей? тот, который на прошлой встрече?", 0, "19:21", 0),
        _msg("Да, он", 1, "19:21", 1),
        _msg("И что ты ему ответила?", 0, "19:22", 0),
        _msg("Пока ничего 🙂", 1, "19:22", 1),
        _voice(0, "19:23", 0, "0:27"),
        _msg("Ладно, я не дурак", 0, "19:25", 0),
        _msg("Макс, ты чего? 😅", 1, "19:26", 1),
        _msg("Ничего. Просто interesting", 0, "19:27", 0),
        _msg("Интересно — отстой от слов «не дурак»", 1, "19:28", 1),
        _sticker(0, "19:28", 0, "😏"),
        _msg("Всё, я понял. Спокойной ночи", 0, "19:40", 0),
        _msg("Спокойной ночи 💔", 1, "19:41", 1),
        _service("Максим заблокировал Сергея", "19:42"),
    ]
    return cfg


def build_unexpected() -> ChatConfig:
    """Неожиданное сообщение от знакомого."""
    cfg = ChatConfig(title="Неожиданное сообщение", style="telegram_dark")
    cfg.participants = _pair("Дима", "Катя")
    cfg.messages = [
        _msg("Ты не поверишь, кого я сейчас встретил", 1, "22:10", 1),
        _msg("Кого?", 0, "22:10", 0),
        _msg("Твоего бывшего. В «Пятницу». С девушкой", 1, "22:11", 1),
        _sticker(0, "22:11", 0, "😳"),
        _msg("Серьёзно?", 0, "22:12", 0),
        _image(1, "22:12", 1, "Вот, издалека"),
        _msg("Ага, вон тот, в кепке", 1, "22:13", 1),
        _msg("Я в шоке", 0, "22:13", 0),
        _msg("Ну и как он?", 0, "22:14", 0),
        _msg("Живой. Смеялся громко", 1, "22:14", 1),
        _msg("Просто пойдём в кино?", 1, "22:16", 1),
        _msg("Ок, но ты меня потом забаннишь", 1, "22:17", 1,
             reaction=Reaction(emoji="😂", count=2)),
        _msg("Нет, но чай поставлю", 0, "22:18", 0),
    ]
    return cfg


def build_exes() -> ChatConfig:
    """Бывшие: неловкое общение спустя год."""
    cfg = ChatConfig(title="Бывшие", style="telegram")
    cfg.participants = _pair("Аня", "Илья")
    cfg.messages = [
        _date("Год спустя", "11:02"),
        _msg("Привет! Давно не виделись", 0, "11:02", 0),
        _msg("Привет-привет", 1, "11:05", 1),
        _msg("Ты как? Работаешь ещё в той конторе?", 0, "11:06", 0),
        _msg("Ушла. Теперь в другой", 1, "11:08", 1),
        _msg("И как там?", 0, "11:09", 0),
        _msg("Лучше. Клиенты адекватные", 1, "11:10", 1),
        _msg("Ну и отлично", 0, "11:11", 0),
        _msg("А помнишь, ты мне тут картину рисовал?", 1, "11:14", 1),
        _msg("Помню 🙂", 0, "11:15", 0),
        _msg("Я сохранила. Повесила в коридоре", 1, "11:16", 1,
             reaction=Reaction(emoji="❤️", count=1)),
        _sticker(0, "11:17", 0, "🥺"),
        _msg("…продолжим разговор в пятницу?", 0, "11:20", 0),
        _msg("Договорились", 1, "11:21", 1),
    ]
    return cfg


def build_friend_joke() -> ChatConfig:
    """Дружеский прикол."""
    cfg = ChatConfig(title="Дружеский прикол", style="whatsapp")
    cfg.participants = _pair("Олег", "Витя")
    cfg.messages = [
        _msg("Слушай, а ты когда нибудь смотрел в зеркало?", 1, "15:02", 1),
        _msg("Нет", 0, "15:05", 0),
        _msg("Смотри. Просто посмотри", 1, "15:05", 1),
        _msg("Витя, ты меня пугаешь", 0, "15:06", 0),
        _sticker(1, "15:06", 1, "😏"),
        _msg("Ааааа, я не смотрел 😱", 0, "15:07", 0),
        _msg("Иди и посмотри. Прямо сейчас", 1, "15:07", 1),
        _msg("Ты серьёзно?", 0, "15:08", 0),
        _msg("Абсолютно", 1, "15:08", 1),
        _voice(0, "15:09", 0, "0:06"),
        _msg("Всё, понял. Молодец, что сказал", 1, "15:10", 1),
        _msg("Спасибо, брат 🤝", 0, "15:10", 0),
    ]
    return cfg


def build_prank() -> ChatConfig:
    """Розыгрыш."""
    cfg = ChatConfig(title="Розыгрыш", style="messenger")
    cfg.participants = _pair("Настя", "Артём")
    cfg.messages = [
        _msg("У меня тут заказ, я через 5 минут выхожу", 1, "18:40", 1),
        _msg("Беги", 0, "18:41", 0),
        _file(1, "18:41", 1, "счёт_на_оплату.pdf", "2,4 МБ"),
        _msg("Слушай, а курьер не приедет час", 1, "18:42", 1),
        _msg("Он уже у подъезда", 0, "18:43", 0),
        _msg("Подожди", 0, "18:43", 0),
        _msg("Не выходи пока", 0, "18:43", 0),
        _sticker(1, "18:44", 1, "🎉"),
        _msg("У меня там сюрприз 🎁", 1, "18:44", 1),
        _msg("С днём рождения, Насть!", 0, "18:45", 0),
        _msg("ТЫ СЕРЬЁЗНО 😭", 1, "18:45", 1),
        _msg("С 8 утра собирал", 1, "18:46", 1),
        _msg("Я думала, ты просто в дверь долбишься 😅", 1, "18:46", 1,
             reaction=Reaction(emoji="😂", count=1)),
        _msg("Все, открывай", 0, "18:47", 0),
    ]
    return cfg


def build_dating() -> ChatConfig:
    """Знакомство."""
    cfg = ChatConfig(title="Знакомство", style="telegram")
    cfg.participants = _pair("Саша", "Игорь")
    cfg.messages = [
        _msg("Привет! Ты из «Ботанического сада»?", 1, "17:30", 1),
        _msg("Нет, я из ГЭС 😄", 0, "17:32", 0),
        _msg("А, ну ты знаешь это место?", 1, "17:33", 1),
        _msg("Я там каждый вторник", 0, "17:34", 0),
        _msg("Кстати, у меня там паук огромный", 1, "17:35", 1,
             reaction=Reaction(emoji="🕷", count=1)),
        _image(1, "17:36", 1, "Вот этот самый"),
        _msg("Не вижу паука", 0, "17:37", 0),
        _msg("Слева в углу", 1, "17:37", 1),
        _msg("А, вижу. Привет, паук", 0, "17:38", 0),
        _msg("Саша, ты смешной", 1, "17:40", 1),
        _msg("Это комплимент или нет?", 0, "17:41", 0),
        _msg("Оба варианта 🙂", 1, "17:42", 1),
        _msg("Тогда давай ещё раз пересечёмся", 1, "17:44", 1),
    ]
    return cfg


def build_work() -> ChatConfig:
    """Рабочая переписка."""
    cfg = ChatConfig(title="Рабочая переписка", style="telegram")
    cfg.participants = _pair("Работодатель", "Сотрудник")
    cfg.messages = [
        _msg("Коллеги, напоминаю про дедлайн", 0, "09:00", 0),
        _msg("Кстати, у нас тут проблема с отчётом", 1, "09:12", 1),
        _file(0, "09:12", 0, "протокол_совещания.docx", "480 КБ"),
        _msg("Посмотрите, пожалуйста", 0, "09:13", 0),
        _msg("Ок, открываю", 1, "09:15", 1),
        _msg("Спасибо!", 0, "09:15", 0),
        _voice(1, "09:31", 1, "0:22"),
        _msg("Понял, поправлю до обеда", 0, "09:33", 0),
        _msg("Супер, тогда в 15:00 скину версию", 1, "09:34", 1),
        _msg("Принято 👍", 0, "09:35", 0),
        _service("Отчёт принят и передан в бухгалтерию", "15:12"),
    ]
    return cfg


def build_strange() -> ChatConfig:
    """Странное сообщение."""
    cfg = ChatConfig(title="Странное сообщение", style="simple")
    cfg.participants = _pair("Кто-то", "Ты")
    cfg.messages = [
        _msg("Привет", 0, "03:14", 0),
        _msg("Сейчас 3 ночи. Ты не спишь?", 1, "03:14", 1),
        _msg("Мне показалось, что ты тоже не спишь", 0, "03:15", 0),
        _msg("Кто ты?", 1, "03:15", 1),
        _msg("Не знаю. Но я знаю, что ты сейчас читаешь это", 0, "03:16", 0),
        _msg("Это странно", 1, "03:17", 1),
        _msg("Я забыл, как тебя зовут", 0, "03:17", 0),
        _msg("Я тоже не помню", 1, "03:18", 1),
        _msg("Тогда просто побудем", 0, "03:19", 0),
        _msg("Хорошо", 1, "03:19", 1),
        _msg("Спокойной ночи", 0, "03:40", 0),
        _msg("Спокойной ночи", 1, "03:40", 1),
    ]
    return cfg


def build_stranger() -> ChatConfig:
    """Переписка с незнакомым номером."""
    cfg = ChatConfig(title="Незнакомый номер", style="telegram")
    cfg.participants = _pair("Неизвестный", "Ты")
    cfg.messages = [
        _date("Сегодня", "20:15"),
        _msg("Здравствуйте, это служба доставки", 0, "20:15", 0),
        _msg("Мы не заказывали", 1, "20:16", 1),
        _msg("Проверьте номер, пожалуйста", 0, "20:17", 0),
        _msg("А это вообще кто?", 1, "20:17", 1),
        _msg("Служба поддержки", 0, "20:18", 0),
        _msg("Поддержки чего?", 1, "20:18", 1),
        _msg("Вашего пакета", 0, "20:19", 0),
        _msg("Спасибо, я разберусь", 1, "20:20", 1),
        _msg("Будьте бдительны", 0, "20:20", 0),
        _sticker(1, "20:21", 1, "🤔"),
    ]
    return cfg


def build_meme() -> ChatConfig:
    """Мемная переписка."""
    cfg = ChatConfig(title="Мем", style="telegram")
    cfg.participants = _pair("Работник", "Дедлайн")
    cfg.messages = [
        _msg("Осталось 5 минут до дедлайна", 0, "08:55", 0),
        _msg("Спокойно", 1, "08:55", 1),
        _msg("Осталось 4 минуты", 0, "08:56", 0),
        _msg("Я справлюсь", 1, "08:56", 1),
        _msg("Осталось 3 минуты", 0, "08:57", 0),
        _msg("Успеваю", 1, "08:57", 1),
        _msg("Осталось 2 минуты", 0, "08:58", 0),
        _msg("Почти закончил", 1, "08:58", 1),
        _msg("Осталась 1 минута", 0, "08:59", 0),
        _msg("Я на сдаче", 1, "08:59", 1),
        _msg("Время вышло", 0, "09:00", 0),
        _msg("…я забыл сохранить файл", 1, "09:01", 1),
        _sticker(0, "09:01", 0, "🗿"),
        _msg("F5 не поможет", 0, "09:02", 0),
        _msg("Всё, ушёл спать", 1, "09:03", 1),
    ]
    return cfg


TEMPLATES: List[Template] = [
    Template("revenge", "Ревность", "😈", "Бывший пишет, парень ревнует",
             build_revenge, ["юмор", "сценка"]),
    Template("unexpected", "Неожиданное сообщение", "😳", "Встретил бывшего в кафе",
             build_unexpected, ["юмор"]),
    Template("exes", "Бывшие", "💔", "Неловкий разговор спустя год",
             build_exes, ["мелодрама"]),
    Template("friend_joke", "Дружеский прикол", "😂", "Шутка между друзьями",
             build_friend_joke, ["мем", "друзья"]),
    Template("prank", "Розыгрыш", "🎉", "Сюрприз ко дню рождения",
             build_prank, ["праздник"]),
    Template("dating", "Знакомство", "☕", "Разговор в парке",
             build_dating, ["знакомство"]),
    Template("work", "Рабочая переписка", "💼", "Планёрка и дедлайны",
             build_work, ["работа"]),
    Template("strange", "Странное сообщение", "🌙", "Ночное сообщение от незнакомца",
             build_strange, ["хоррор", "стиль"]),
    Template("stranger", "Переписка с неизвестным", "📱", "Сообщение с незнакомого номера",
             build_stranger, ["юмор"]),
    Template("meme", "Мемная переписка", "🗿", "Бесконечный дедлайн",
             build_meme, ["мем"]),
]

_BY_KEY: Dict[str, Template] = {t.key: t for t in TEMPLATES}


class TemplatesService:
    """Доступ к шаблонам."""

    def all(self) -> List[Template]:
        return list(TEMPLATES)

    def get(self, key: str) -> Optional[Template]:
        return _BY_KEY.get((key or "").lower())

    def available(self, premium: bool = False) -> List[Template]:
        return [t for t in TEMPLATES if premium or not t.premium_only]

    def previews(self, premium: bool = False) -> List[TemplatePreview]:
        return [t.preview() for t in self.available(premium)]

    def build(self, key: str) -> ChatConfig:
        template = self.get(key)
        if template is None:
            raise KeyError(f"Шаблон {key} не найден")
        return template.build()

    def title(self, key: str) -> str:
        template = self.get(key)
        return template.title if template else key


templates_service = TemplatesService()

__all__ = ["Template", "TEMPLATES", "TemplatesService", "templates_service"]